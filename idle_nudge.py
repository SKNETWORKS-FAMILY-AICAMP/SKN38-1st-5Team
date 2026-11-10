import json

import streamlit as st


IDLE_MS = 8000
VISIBLE_MS = 5000

MESSAGES = {
    "": (
        "지도에서 궁금한 구를 눌러 보세요.",
        "세 가지 판정을 눌러 지도 색을 바꿔 보세요.",
    ),
    "ranking": (
        "순위 막대를 눌러 다른 동네를 골라 보세요.",
        "전체 25구 보기를 켜서 모든 구의 순위를 살펴보세요.",
    ),
    "finder": (
        "차가 있는지와 가장 중요하게 보는 기준을 바꿔 보세요.",
        "표의 열 이름을 누르면 원하는 기준으로 다시 정렬돼요.",
    ),
    "ownership": (
        "차종 구성에서 전기차를 눌러 종류별 대수를 살펴보세요.",
        "아래 순위 막대를 눌러 다른 동네를 골라 보세요.",
    ),
    "parking": (
        "주소 검색에 도로명이나 동 이름을 입력해 보세요.",
        "찾을 시설에서 충전소를 눌러 위치를 살펴보세요.",
    ),
    "transit": (
        "위의 살펴볼 동네를 눌러 다른 구의 대중교통도 살펴보세요.",
        "승객 그래프의 점에 마우스를 올려 시간별 수치를 확인해 보세요.",
    ),
    "roads": (
        "위의 살펴볼 동네를 눌러 다른 구의 교통량도 살펴보세요.",
        "날씨 그래프에 마우스를 올려 시간별 값을 확인해 보세요.",
    ),
    "compare": (
        "함께 비교할 동네를 눌러 궁금한 구를 골라 보세요.",
        "비교 기준을 눌러 세 판정의 뜻을 확인해 보세요.",
    ),
    "national": (
        "시도를 눌러 궁금한 지역의 등록 대수를 살펴보세요.",
        "차종과 용도를 골라 원하는 차량만 살펴보세요.",
    ),
    "faq": (
        "궁금한 질문을 눌러 답변을 펼쳐 보세요.",
        "차차차 FAQ를 눌러 서비스 이용 안내를 살펴보세요.",
    ),
    "ask": (
        "예시 질문을 눌러 동네 자동차 생활을 물어보세요.",
        "답변이 나오면 답변의 근거 자료 보기를 눌러 확인해 보세요.",
    ),
    "about": (
        "판정 기준을 눌러 세 가지 판정의 뜻을 살펴보세요.",
        "자료의 한계를 눌러 숫자를 읽을 때 주의할 점을 확인해 보세요.",
    ),
}

NUDGE_SCRIPT = """
<script>
(() => {
  const page = __PAGE__;
  // 재실행 때 안내 횟수와 남은 표시 시간이 초기화되지 않도록 한다.
  if (window.__chachachaIdleNudgePage === page) return;
  window.__chachachaIdleNudge?.abort();
  const controller = new AbortController();
  window.__chachachaIdleNudge = controller;
  window.__chachachaIdleNudgePage = page;
  const messages = __MESSAGES__;
  let shown = 0;
  let visible = false;
  let idleTimer;
  let visibleTimer;

  const style = document.createElement('style');
  style.textContent = `
    #chachacha-idle-nudge {
      position: fixed;
      right: 16px;
      bottom: 24px;
      z-index: 2147483647;
      box-sizing: border-box;
      display: flex;
      align-items: flex-start;
      gap: 10px;
      width: max-content;
      max-width: calc(100vw - 32px);
      padding: 16px 18px;
      border-radius: 16px;
      background: #27336B;
      color: #FFFFFF;
      font-family: "Noto Sans KR", sans-serif;
      font-size: 15px;
      line-height: 1.6;
      font-weight: 400;
      overflow-wrap: anywhere;
      pointer-events: none;
      box-shadow: 0 10px 32px rgba(27, 35, 64, 0.2);
      animation: chachacha-idle-nudge-in 180ms ease-out;
    }
    #chachacha-idle-nudge[hidden] { display: none; }
    #chachacha-idle-nudge::before {
      content: '';
      flex: 0 0 7px;
      width: 7px;
      height: 7px;
      margin-top: 8px;
      border-radius: 50%;
      background: #FF7A66;
    }
    @keyframes chachacha-idle-nudge-in {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @media (max-width: 480px) {
      #chachacha-idle-nudge { left: 16px; right: 16px; width: auto; }
    }
    @media (prefers-reduced-motion: reduce) {
      #chachacha-idle-nudge { animation: none; }
    }
  `;
  document.head.appendChild(style);
  const nudge = document.createElement('div');
  nudge.id = 'chachacha-idle-nudge';
  nudge.setAttribute('role', 'status');
  nudge.setAttribute('aria-live', 'polite');
  nudge.hidden = true;
  document.body.appendChild(nudge);

  controller.signal.addEventListener('abort', () => {
    clearTimeout(idleTimer);
    clearTimeout(visibleTimer);
    nudge.remove();
    style.remove();
  }, {once: true});

  function schedule() {
    clearTimeout(idleTimer);
    if (controller.signal.aborted || visible || document.hidden) return;
    idleTimer = setTimeout(show, __IDLE_MS__);
  }

  function hide() {
    clearTimeout(visibleTimer);
    nudge.hidden = true;
    nudge.textContent = '';
    visible = false;
    if (shown === messages.length) controller.abort();
    else schedule();
  }

  function show() {
    if (controller.signal.aborted || document.hidden) return;
    nudge.hidden = false;
    nudge.textContent = messages[shown++];
    visible = true;
    visibleTimer = setTimeout(hide, __VISIBLE_MS__);
  }

  const options = {capture: true, passive: true, signal: controller.signal};
  for (const event of ['mousemove', 'click', 'scroll', 'keydown', 'touchstart', 'touchmove']) {
    document.addEventListener(event, schedule, options);
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearTimeout(idleTimer);
      if (visible) hide();
    } else {
      schedule();
    }
  }, {signal: controller.signal});
  schedule();
})();
</script>
"""


def add_idle_nudge(url_path: str) -> None:
    script = (NUDGE_SCRIPT
              .replace("__PAGE__", json.dumps(url_path))
              .replace("__MESSAGES__", json.dumps(MESSAGES[url_path], ensure_ascii=False))
              .replace("__IDLE_MS__", str(IDLE_MS))
              .replace("__VISIBLE_MS__", str(VISIBLE_MS)))
    st.html(script, unsafe_allow_javascript=True)
