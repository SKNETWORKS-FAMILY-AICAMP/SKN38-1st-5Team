"""대중교통 페이지의 '더 싸게 타는 법' 한 줄 안내와 팝업 창."""
from math import ceil

import streamlit as st

# 서울 교통카드 기본요금(2026-11 확인). 요금이 바뀌면 여기만 고친다.
BUS_FARE = 1500
SUBWAY_FARE = 1550
SUBWAY_SINGLE_TICKET = 1650
EARLY_RATE = 0.2  # 첫차~06:30 조조할인
KPASS_RATE = 0.2  # K-패스 일반 환급률
KPASS_MIN_RIDES = 15
KPASS_URL = "https://korea-pass.kr/"
SEOUL_TRAFFIC_URL = "https://news.seoul.go.kr/traffic/"
PRESETS = {"가끔 (20번)": 20, "출퇴근 (44번)": 44, "매일 여러 번 (60번)": 60}

CSS = """<style>
.st-key-transit_save_teaser { background:#F5F6FB; border:1px solid #E2E5F0; border-radius:16px; padding:14px 18px; }
.st-key-transit_save_teaser:hover { border-color:#8E98CF; background:#EEF0FA; }
.ts-teaser { display:flex; align-items:center; gap:14px; min-width:0; }
.ts-teaser .i { font-size:26px; line-height:1; }
.ts-teaser b { display:block; font-size:18px; color:#27336B; }
.ts-teaser small { display:block; font-size:15px; color:#4A5270; }
.ts-new { display:inline-block; margin-left:8px; padding:3px 8px; border-radius:999px; background:#FF7A66; color:#fff;
  font-size:12px; font-weight:700; vertical-align:middle; }
.ts-grid { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:14px; }
.ts-card { border:1px solid #E2E5F0; border-radius:16px; padding:18px 20px; background:#fff; display:flex; flex-direction:column; gap:8px; }
.ts-card .n { font-size:13px; font-weight:800; color:#E0604C; letter-spacing:.04em; }
.ts-card h4 { margin:0; font-size:19px; color:#1B2340; }
.ts-card p, .ts-card li { margin:0; font-size:15px; line-height:1.6; color:#3D4560; }
.ts-card ul { margin:0; padding-left:18px; }
.ts-chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:auto; padding-top:4px; }
.ts-chip { font-size:14px; font-weight:700; padding:5px 10px; border-radius:10px; background:#F5F6FB; color:#27336B; }
.ts-chip.g { background:#DCFCE7; color:#166534; }
.ts-card .s { font-size:14px; color:#4A5270; }
.ts-card a { margin-top:auto; font-weight:700; color:#27336B; }
.ts-total { font-size:34px; font-weight:800; color:#1B2340; font-variant-numeric:tabular-nums; line-height:1.3; }
.ts-row { display:flex; justify-content:space-between; gap:12px; padding:10px 0; border-bottom:1px solid #F0F2F6; font-size:16px; }
.ts-row b { font-variant-numeric:tabular-nums; color:#166534; }
.ts-row b.off { color:#4A5270; font-weight:500; }
.ts-tip { padding:12px 14px; border-radius:12px; background:#DCFCE7; color:#166534; font-weight:700; margin-top:10px; }
@media (max-width:700px) {
  .ts-grid { grid-template-columns:1fr; }
  .ts-teaser small { display:none; }
}
</style>"""


def _won(value: float) -> str:
    return f"{round(value):,}원"


def estimate(rides: int) -> dict[str, float | None]:
    """한 달 탑승 횟수로 교통비와 할인별 금액을 어림한다. 두 할인은 서로 따로 계산한다."""
    cost = rides * BUS_FARE
    # 출근(하루 한 번)만 조조할인으로 탄다고 본다.
    early = ceil(rides / 2) * BUS_FARE * EARLY_RATE
    kpass = cost * KPASS_RATE if rides >= KPASS_MIN_RIDES else None
    return {"cost": cost, "with_early": cost - early,
            "with_kpass": None if kpass is None else cost - kpass}


def _tips() -> None:
    st.html(CSS + f"""<div class="ts-grid">
<div class="ts-card"><span class="n">STEP 1</span><h4>교통카드가 아직 없다면</h4>
<ul><li>편의점에서 티머니 카드를 사서 충전</li><li>휴대폰에 모바일 티머니 설치</li>
<li>후불 교통 기능이 있는 신용·체크카드</li></ul>
<div class="ts-chips"><span class="ts-chip">버스 {_won(BUS_FARE)}</span><span class="ts-chip">지하철 {_won(SUBWAY_FARE)}</span></div>
<span class="s">지하철 1회용 승차권({_won(SUBWAY_SINGLE_TICKET)})보다 카드가 {SUBWAY_SINGLE_TICKET - SUBWAY_FARE}원 싸요.</span></div>
<div class="ts-card"><span class="n">TIP 2</span><h4>갈아탈 땐 내릴 때도 찍기</h4>
<p>내릴 때 카드를 찍어야 다음 버스·지하철이 환승으로 이어져요. 한 번 요금으로 최대 다섯 번까지 타요.</p>
<div class="ts-chips"><span class="ts-chip g">환승하면 기본요금 다시 안 내요</span></div>
<span class="s">같은 번호 버스를 다시 타는 건 환승이 아니에요.</span></div>
<div class="ts-card"><span class="n">TIP 3</span><h4>아침 일찍이면 조조할인</h4>
<p>첫차부터 오전 6시 30분 전에 카드로 타면 기본요금이 20% 싸져요.</p>
<div class="ts-chips"><span class="ts-chip g">버스 {_won(BUS_FARE * (1 - EARLY_RATE))}</span>
<span class="ts-chip g">지하철 {_won(SUBWAY_FARE * (1 - EARLY_RATE))}</span></div></div>
<div class="ts-card"><span class="n">TIP 4</span><h4>많이 탄다면 모두의카드</h4>
<p>K-패스 카드로 타면 한 달 이용액에 맞춰 더 유리한 환급 방식이 자동으로 적용돼요. 기후동행카드는 9월부터 모두의카드(기후동행패스)로 합쳐졌어요.</p>
<a href="{KPASS_URL}" target="_blank" rel="noopener noreferrer">K-패스 공식 사이트에서 신청하기 ↗</a></div>
</div>""")


def _apply_preset() -> None:
    choice = st.session_state.get("transit_save_preset")
    if choice in PRESETS:
        st.session_state.transit_save_rides = PRESETS[choice]


def _calculator() -> None:
    st.session_state.setdefault("transit_save_rides", 44)
    with st.container(border=True, key="transit_save_calc"):
        left, right = st.columns([1.1, 1], gap="large")
        with left:
            st.segmented_control("한 달에 몇 번 타세요?", list(PRESETS), key="transit_save_preset",
                                 on_change=_apply_preset)
            rides = st.slider("한 달 탑승 횟수", 4, 90, key="transit_save_rides", format="%d번",
                              label_visibility="collapsed")
            st.caption(f"갈아탄 건 한 번으로 세요. 버스 기본요금 {_won(BUS_FARE)}으로 어림해요.")
        result = estimate(rides)
        with right:
            kpass = result["with_kpass"]
            st.html(
                f'<span class="s" style="color:#4A5270">한 달 교통비 (어림)</span>'
                f'<div class="ts-total">{_won(result["cost"])}</div>'
                f'<div class="ts-row"><span>조조할인으로 출근하면</span><b>{_won(result["with_early"])}</b></div>'
                f'<div class="ts-row"><span>K-패스 기본 환급 (일반 20%)</span>'
                + (f'<b>{_won(kpass)}</b>' if kpass is not None
                   else f'<b class="off">해당 없음 (월 {KPASS_MIN_RIDES}번부터)</b>')
                + '</div>'
                + ('<div class="ts-tip">한 달 15번 넘게 타니 K-패스나 모두의카드를 꼭 챙겨 보세요.</div>'
                   if kpass is not None else
                   '<div class="ts-tip">가끔 탄다면 교통카드 하나면 충분해요. 갈아탈 때 내리면서 찍는 것만 기억하세요.</div>'))
            st.caption("실제 환급은 나이·소득과 모두의카드 기준금액에 따라 달라요. 정확한 금액은 공식 사이트에서 확인해 주세요.")


@st.dialog("버스·지하철, 이렇게 타면 더 아껴요", width="large")
def savings_dialog() -> None:
    st.caption("처음 타는 분도 바로 쓸 수 있는 네 가지예요. 요금은 서울 교통카드 기준이에요.")
    _tips()
    _calculator()
    st.caption(f"요금 안내: [서울시 교통 누리집]({SEOUL_TRAFFIC_URL}) · [K-패스]({KPASS_URL})")


def teaser() -> None:
    """혜택 카드 아래에 한 줄로 두고, 누르면 절약 팁 창을 연다."""
    st.html(CSS)
    with st.container(horizontal=True, vertical_alignment="center", gap="medium", key="transit_save_teaser"):
        st.html('<div class="ts-teaser"><span class="i" aria-hidden="true">🚌</span><span>'
                '<b>대중교통 이용하실 예정이시라면?<span class="ts-new">NEW</span></b>'
                '<small>교통카드 만들기부터 더 싸게 타는 법까지</small></span></div>', width="stretch")
        if st.button("더보기", icon=":material/chevron_right:", icon_position="right", type="tertiary",
                     key="transit_save_open", help="교통카드 만들기와 할인 방법을 창으로 보여 드려요."):
            savings_dialog()
