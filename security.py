from collections import deque
from collections.abc import Mapping
from ipaddress import ip_address
import math
import os
from threading import Lock
from time import monotonic
from uuid import uuid4

import streamlit as st


BOT_MARKERS = (
    "curl", "wget", "python-requests", "python-httpx", "httpx", "aiohttp",
    "scrapy", "go-http-client", "headlesschrome", "phantomjs", "playwright",
    "puppeteer", "selenium", "gptbot", "chatgpt-user", "oai-searchbot",
    "claudebot", "claude-user", "claude-searchbot", "anthropic-ai", "ccbot",
    "bytespider", "perplexitybot", "perplexity-user", "amazonbot", "ahrefsbot",
    "semrushbot", "mj12bot", "googlebot", "googleother", "bingbot",
    "applebot", "duckduckbot", "yandexbot", "baiduspider", "petalbot",
    "facebookexternalhit", "twitterbot", "slurp", "scraper", "crawler",
)
WINDOW_SECONDS = 60.0
SESSION_LIMIT = 120
IP_LIMIT = 300
BOT_NOTICE = "자동 수집 요청은 이용할 수 없어요. 일반 브라우저에서 차차차를 열어 주세요."


def is_blocked_user_agent(user_agent: str | None) -> bool:
    # User-Agent는 위조할 수 있으므로 인증 수단으로 쓰지 않는다.
    if os.environ.get("CHACHACHA_ALLOW_BOTS") == "1":
        return False
    value = (user_agent or "").strip().lower()
    return not value or any(marker in value for marker in BOT_MARKERS)


def client_ip(headers: Mapping[str, str], direct_ip: str | None) -> str | None:
    # 주소 위조를 막으려면 프록시가 X-Forwarded-For를 덮어써야 한다.
    forwarded = next((value for key, value in headers.items()
                      if key.lower() == "x-forwarded-for"), "")
    for candidate in (direct_ip, forwarded.split(",", 1)[0].strip()):
        if candidate:
            try:
                return str(ip_address(candidate))
            except ValueError:
                pass
    return None


# 여러 프로세스에서 제한을 공유하려면 별도 저장소가 필요하다.
class RequestLimiter:
    def __init__(self) -> None:
        self.sessions: dict[str, deque[float]] = {}
        self.ips: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._last_cleanup = -math.inf

    def check(self, session_id: str, address: str | None, *, now: float | None = None) -> int:
        with self._lock:
            timestamp = monotonic() if now is None else now
            cutoff = timestamp - WINDOW_SECONDS
            if timestamp - self._last_cleanup >= WINDOW_SECONDS:
                for buckets in (self.sessions, self.ips):
                    stale = [key for key, values in buckets.items()
                             if not values or values[-1] <= cutoff]
                    for key in stale:
                        del buckets[key]
                self._last_cleanup = timestamp

            session = self.sessions.get(session_id, deque())
            ip_events = self.ips.get(address, deque()) if address else deque()
            limits = [(session, SESSION_LIMIT)]
            if address:
                limits.append((ip_events, IP_LIMIT))
            retry_after = 0
            for events, limit in limits:
                while events and events[0] <= cutoff:
                    events.popleft()
                if len(events) >= limit:
                    retry_after = max(retry_after, math.ceil(events[0] + WINDOW_SECONDS - timestamp))
            if retry_after:
                return retry_after

            session.append(timestamp)
            self.sessions[session_id] = session
            if address:
                ip_events.append(timestamp)
                self.ips[address] = ip_events
            return 0


@st.cache_resource(show_spinner=False, max_entries=1)
def request_limiter() -> RequestLimiter:
    return RequestLimiter()


def guard_request() -> None:
    headers = st.context.headers
    user_agent = next((value for key, value in headers.items()
                       if key.lower() == "user-agent"), None)
    if is_blocked_user_agent(user_agent):
        st.info(BOT_NOTICE)
        st.stop()
    if "_security_session_id" not in st.session_state:
        st.session_state["_security_session_id"] = uuid4().hex
    retry_after = request_limiter().check(
        st.session_state["_security_session_id"], client_ip(headers, st.context.ip_address)
    )
    if retry_after:
        st.info(f"요청이 잠시 몰렸어요. {retry_after}초 뒤에 다시 이용해 주세요.")
        st.stop()


NOINDEX_SCRIPT = """
<script>
(() => {
  let meta = document.head.querySelector('meta[name="robots"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.name = 'robots';
    document.head.appendChild(meta);
  }
  meta.content = 'noindex, nofollow, noarchive';
})();
</script>
"""


def add_noindex() -> None:
    st.html(NOINDEX_SCRIPT, unsafe_allow_javascript=True)


# 개발자 도구와 오른쪽 클릭 제한은 억제책일 뿐 보안 장치가 아니다.
DETERRENT_SCRIPT = """
<script>
(() => {
  window.__chachachaViewGuard?.abort();
  const controller = new AbortController();
  window.__chachachaViewGuard = controller;
  const options = {capture: true, signal: controller.signal};
  document.addEventListener('contextmenu', (event) => {
    if (event.composedPath().some((node) => node instanceof HTMLElement &&
        (node.matches('input, textarea') || node.isContentEditable))) return;
    event.preventDefault();
  }, options);
  document.addEventListener('keydown', (event) => {
    // macOS의 Option+I는 event.key가 특수문자라서 물리 키 코드로 판단한다.
    const code = event.code;
    const modifier = event.ctrlKey || event.metaKey;
    if (code === 'F12' ||
        (modifier && (event.shiftKey || event.altKey) && ['KeyI', 'KeyJ', 'KeyC'].includes(code)) ||
        (modifier && code === 'KeyU')) {
      event.preventDefault();
    }
  }, options);
})();
</script>
"""


def add_view_deterrent() -> None:
    if os.environ.get("CHACHACHA_DEV") == "1":
        st.html("<script>window.__chachachaViewGuard?.abort();</script>", unsafe_allow_javascript=True)
        return
    st.html(DETERRENT_SCRIPT, unsafe_allow_javascript=True)
