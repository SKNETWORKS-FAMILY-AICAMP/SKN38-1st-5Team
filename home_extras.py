"""홈 아래쪽 화면: 공공 사이트 연결, 자주 찾는 메뉴, 서울 자동차 현황, 25구 순위."""
from dataclasses import dataclass
from html import escape

import pandas as pd
import streamlit as st


@dataclass(frozen=True)
class PublicLink:
    title: str
    description: str
    site: str
    organization: str
    url: str


# 공식 주소는 2026-11-10에 접속해 확인했다. 민간 업체는 넣지 않는다.
CAR365_USED = "https://www.car365.go.kr/ccpt/cmmn/menu/redirectMenu.do?menuId=M630101000"
LINKS = {
    "used": PublicLink("중고차 시세 알아보기", "차종·연식별 중고차 시세와 평균 매매가를 확인해요.",
                       "자동차365", "국토교통부", CAR365_USED),
    "sell": PublicLink("내 차 시세 확인하기", "팔기 전에 같은 차종의 중고차 시세부터 확인해요.",
                       "자동차365", "국토교통부", CAR365_USED),
    "newcar": PublicLink("신차 등록비용·이력 조회", "신차 등록비용 계산과 차량 통합이력 조회를 한곳에서 해요.",
                         "자동차365", "국토교통부", "https://www.car365.go.kr/"),
    "insure": PublicLink("자동차보험료 비교", "여러 보험사의 자동차보험료를 한 번에 비교해요.",
                         "보험다모아", "생명·손해보험협회", "https://www.e-insmarket.or.kr/"),
    "topis": PublicLink("실시간 교통·대중교통 정보", "도로 소통과 버스·지하철 정보를 실시간으로 봐요.",
                        "서울 TOPIS", "서울특별시", "https://topis.seoul.go.kr/"),
    "parking": PublicLink("주변 공영주차장 찾기", "공영·민영 주차장 위치와 혼잡도를 지도에서 찾아요.",
                          "서울시 주차정보안내시스템", "서울특별시", "https://parking.seoul.go.kr/"),
    "ev": PublicLink("전기차 구매 보조금 현황", "지자체별 전기차 보조금 공고와 남은 대수를 확인해요.",
                     "무공해차 통합누리집", "정부",
                     "https://ev.or.kr/nportal/buySupprt/initSubsidyPaymentCheckAction.do"),
}
# 대중교통 이용 지표별 참고 링크. 내부 단계 이름은 ui.TOPICS와 호환한다.
PLANS = {
    "차가 필요한 편": ("주민 대비 대중교통 이용 지표가 낮은 편이에요. 실제 이동 경로와 주차 여건, 차량 비용을 함께 확인해 보세요.",
                  "차를 살지 고민이라면", ("used", "newcar", "insure")),
    "있으면 편함": ("주민 대비 대중교통 이용 지표는 보통이에요. 통근 경로와 주차 가능 여부를 확인하고 이동 비용을 비교해 보세요.",
               "비용부터 따져 보려면", ("used", "insure", "topis")),
    "대중교통으로 충분": ("주민 대비 대중교통 이용 지표가 높은 편이에요. 실제 노선과 운행 시간, 목적지 주차 여건을 함께 확인해 보세요.",
                   "이동 방법과 비용을 비교하려면", ("topis", "used", "insure")),
}
QUICK_MENU = (
    ("app_pages/home.py", "우리 동네", ":material/map:"),
    ("app_pages/finder.py", "동네 찾기", ":material/travel_explore:"),
    ("app_pages/ownership.py", "차량 보유", ":material/directions_car:"),
    ("app_pages/parking.py", "주차 찾기", ":material/local_parking:"),
    ("app_pages/charging.py", "전기차 충전", ":material/ev_station:"),
    ("app_pages/transit.py", "대중교통", ":material/directions_bus:"),
    ("app_pages/compare.py", "두 동네 비교", ":material/compare_arrows:"),
    ("app_pages/ask.py", "물어보기", ":material/chat_bubble:"),
)
RANKS = (
    ("차가 많은 구", "세대당 차량 (대)", "vehicle_per_household", 1, 2),
    ("주차 여유가 있는 구", "차 100대당 수록 주차면 (면)", "parking_value", 100, 1),
    ("충전 여건이 좋은 구", "전기차 1대당 충전기 (기)", "charger_per_electric_vehicle", 1, 2),
    ("대중교통을 많이 타는 구", "주민 1명당 하루 승객 (명)", "need_value", 1, 2),
)
# 출퇴근 유입으로 주민 기준 값이 커지는 구는 순위에 표시를 붙인다.
COMMUTER_DISTRICTS = {"중구", "종로구"}
COMMUTER_COLUMNS = {"parking_value", "need_value"}

CSS = """
<style>
.st-key-home_extras h2 { font-family: Jua, sans-serif; font-weight: 400; color: #27336B; font-size: 30px; }
.st-key-home_next p.home-lead { color: #4A5270; font-size: 16px; margin: -6px 0 4px; }
.st-key-home_next [class*="st-key-next_card_"] {
  border: 1px solid #E2E5F0; border-radius: 16px; background: #fff; padding: 18px; height: 100%;
  min-height: 280px; display: flex; flex-direction: column;
}
.st-key-home_next [data-testid="stColumn"] { display: flex; align-items: stretch; }
.st-key-home_next [data-testid="stLinkButton"] { margin-top: auto; }
.st-key-home_next [class*="st-key-next_card_"]:hover { border-color: #8E98CF; }
.next-why { display: inline-block; padding: 3px 10px; border-radius: 999px; background: #EEF0FA;
  color: #27336B; font-size: 13px; font-weight: 700; }
.next-title { display: block; margin-top: 10px; font-size: 18px; font-weight: 800; color: #1B2340; }
.next-desc { display: block; margin-top: 4px; font-size: 15px; line-height: 1.55; color: #3D4560; }
.next-src { display: block; margin-top: 10px; font-size: 16px; color: #4A5270; line-height: 1.5; }
.home-ext { font-size: 16px; color: #4A5270; line-height: 1.5; }
.st-key-home_quick { gap: 12px; }
.st-key-home_quick [data-testid="stPageLink"] { flex: 1 1 0; min-width: 104px; }
.st-key-home_quick a {
  flex-direction: column; justify-content: center; gap: 10px; min-height: 120px; border-radius: 20px;
  background: #EEF0FA; color: #1B2340;
}
.st-key-home_quick a:hover { background: #E1E5F6; }
.st-key-home_quick a [data-testid="stIconMaterial"] { font-size: 34px; color: #27336B; }
.st-key-home_quick a p { font-size: 16px; font-weight: 700; }
.home-stats { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); border: 1px solid #E2E5F0;
  border-radius: 18px; overflow: hidden; }
.home-stats > div { padding: 22px 20px; border-right: 1px solid #E2E5F0; min-width: 0; display: flex; flex-direction: column; background: #F7F8FC; }
.home-stats > div:last-child { border-right: none; }
.home-stats dt { font-size: 16px; font-weight: 600; line-height: 1.5; min-height: 3em; color: #1B2340; }
.home-stats dd { margin: 8px 0 0; font-size: 26px; line-height: 1.4; font-weight: 800; color: #27336B; font-variant-numeric: tabular-nums; }
.home-stats dd small { font-size: 14px; font-weight: 500; color: #4A5270; margin-left: 2px; }
.home-stats .s { display: block; margin-top: 8px; font-size: 16px; line-height: 1.5; font-weight: 400; color: #4A5270; }
.home-ranks { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid #E2E5F0;
  border-radius: 18px; overflow: hidden; }
.home-ranks > div { padding: 22px 20px; border-right: 1px solid #E2E5F0; display: flex; flex-direction: column; gap: 14px; min-width: 0; height: 100%; }
.home-ranks .home-rank-heading { min-height: 76px; }
.home-ranks > div:last-child { border-right: none; }
.home-ranks h3 { margin: 0; font-size: 18px; color: #1B2340; }
.home-ranks .m { font-size: 16px; color: #4A5270; line-height: 1.5; }
.home-ranks ol { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.home-ranks li { display: grid; grid-template-columns: 22px minmax(64px, auto) minmax(12px, 1fr) 48px; align-items: center; gap: 6px; font-size: 16px; min-height: 44px; padding: 4px; border-radius: 8px; }
.home-ranks .n { font-size: 13px; font-weight: 800; color: #4A5270; text-align: center; }
.home-ranks .rank-first { color: #166534; background: #DCFCE7; }
.home-ranks .rank-first .n, .home-ranks .rank-first .v { color: #166534; }
.home-ranks .rank-first .t span { background: #15803D; }
.home-ranks .rank-caution { color: #854D0E; background: #FEF9C3; }
.home-ranks .rank-caution .n, .home-ranks .rank-caution .v { color: #854D0E; }
.home-ranks .rank-caution .t span { background: #CA8A04; }
.home-ranks .rank-other .t span { background: #8E98CF; }
.home-ranks .t { height: 7px; background: #EEF0F4; border-radius: 4px; overflow: hidden; }
.home-ranks .t span { display: block; height: 100%; }
.home-ranks .v { text-align: right; font-weight: 800; font-variant-numeric: tabular-nums; }
.home-ranks sup { color: #C24C38; }
.home-ranks .last { margin-top: auto; padding: 12px 8px; border-top: 1px solid #F0F2F6; border-radius: 8px; font-size: 16px; line-height: 1.5; color: #991B1B; background: #FEE2E2; }
@media (max-width: 1100px) {
  .home-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .home-stats > div:nth-child(3n) { border-right: none; }
  .home-stats > div:nth-child(-n+3) { border-bottom: 1px solid #E2E5F0; }
  .home-ranks { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .home-ranks > div:nth-child(2n) { border-right: none; }
  .home-ranks > div:nth-child(-n+2) { border-bottom: 1px solid #E2E5F0; }
}
@media (max-width: 700px) {
  .home-stats, .home-ranks { grid-template-columns: 1fr; }
  .home-stats > div, .home-ranks > div { border-right: none; border-bottom: 1px solid #E2E5F0; }
  .st-key-home_quick [data-testid="stPageLink"] { flex: 1 1 40%; }
}
</style>
"""


def _value(row: pd.Series, column: str) -> float | None:
    value = pd.to_numeric(row.get(column), errors="coerce")
    return None if pd.isna(value) else float(value)


def _josa(word: str) -> str:
    last = word[-1] if word else ""
    has_final = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return "이라면" if has_final else "라면"


def next_steps(row: pd.Series, ranking: pd.DataFrame) -> None:
    plan = PLANS.get(str(row.get("need_level")))
    if plan is None:
        return
    lead, why, keys = plan
    name = str(row.get("district_name"))
    charger = _value(row, "charger_per_electric_vehicle")
    seoul_charger = pd.to_numeric(ranking.get("charger_per_electric_vehicle"), errors="coerce").mean()
    if str(row.get("parking_level")) == "빠듯함":
        extra = ("parking", "주차가 빠듯한 동네라면")
    elif charger is not None and pd.notna(seoul_charger) and charger >= seoul_charger:
        extra = ("ev", "충전 여건이 괜찮은 동네라면")
    else:
        extra = ("parking", "주차할 곳을 미리 보려면")
    cards = [(key, why) for key in keys] + [extra]
    with st.container(gap="small", key="home_next"):
        st.subheader(f"{name}{_josa(name)} 이렇게 알아보세요", anchor=False)
        st.html(f'<p class="home-lead">{escape(lead)}</p>')
        for column, (key, reason) in zip(st.columns(len(cards)), cards):
            link = LINKS[key]
            with column.container(gap="small", key=f"next_card_{key}"):
                st.html(f'<span class="next-why">{escape(reason)}</span>'
                        f'<span class="next-title">{escape(link.title)}</span>'
                        f'<span class="next-desc">{escape(link.description)}</span>'
                        f'<span class="next-src">{escape(link.site)} · {escape(link.organization)}</span>')
                st.link_button("바로가기", link.url, icon=":material/open_in_new:", width="stretch",
                               help=f"{link.site} 공식 사이트가 새 창으로 열려요.")
        st.html('<p class="home-ext">공공기관 사이트가 새 창으로 열려요. 차차차와 관계없는 외부 사이트예요.</p>')


def quick_menu() -> None:
    st.subheader("자주 찾는 메뉴", anchor=False)
    with st.container(horizontal=True, gap="small", key="home_quick"):
        for page, label, icon in QUICK_MENU:
            st.page_link(page, label=label, icon=icon)


def _column(ranking: pd.DataFrame, column: str) -> pd.Series:
    if column not in ranking:
        return pd.Series(float("nan"), index=ranking.index)
    return pd.to_numeric(ranking[column], errors="coerce").astype("float64")


def _complete_total(values: pd.Series) -> float | None:
    if len(values) != 25 or values.isna().any():
        return None
    return float(values.sum())


def _total(ranking: pd.DataFrame, column: str) -> float | None:
    return _complete_total(_column(ranking, column))


def seoul_overview(ranking: pd.DataFrame) -> None:
    required = ("vehicle_count", "household_count", "electric_count", "population", "listed_count",
                "listed_station_count", "fast_count", "parking_value", "need_value")
    if any(column not in ranking for column in required):
        return
    vehicles, households = _total(ranking, "vehicle_count"), _total(ranking, "household_count")
    electric, population = _total(ranking, "electric_count"), _total(ranking, "population")
    chargers, stations = _total(ranking, "listed_count"), _total(ranking, "listed_station_count")
    fast = _total(ranking, "fast_count")
    spaces = _complete_total(_column(ranking, "parking_value") * _column(ranking, "vehicle_count"))
    riders = _complete_total(_column(ranking, "need_value") * _column(ranking, "population"))

    def formatted(value, digits=0, scale=1, prefix=""):
        return "자료 없음" if value is None else f"{prefix}{value * scale:,.{digits}f}"

    def ratio(part, whole, digits, scale=1):
        value = None if part is None or whole is None or whole == 0 else part / whole
        return formatted(value, digits, scale)

    cells = (
        ("등록 차량", formatted(vehicles), "대", "25구 합계"),
        ("세대당 차량", ratio(vehicles, households, 2), "대", f"{formatted(households)} 세대 기준"),
        ("전기차", formatted(electric), "대", f"등록 차량의 {ratio(electric, vehicles, 1, 100)}%"),
        ("수록 충전기", formatted(chargers), "기", f"충전소 {formatted(stations)}곳 · 급속 {formatted(fast)}기"),
        ("수록 주차면", formatted(spaces, scale=1e-4, prefix="약 "), "만 면", f"차 100대당 {ratio(spaces, vehicles, 1, 100)}면"),
        ("하루 대중교통 승객", formatted(riders, scale=1e-4, prefix="약 "), "만 명", f"주민 1명당 {ratio(riders, population, 2)}명"),
    )
    st.subheader("서울 자동차 현황", anchor=False)
    st.html('<dl class="home-stats">' + "".join(
        f"<div><dt>{label}</dt><dd>{value}<small>{unit}</small><span class=\"s\">{note}</span></dd></div>"
        for label, value, unit, note in cells) + "</dl>")


def top_ranks(ranking: pd.DataFrame) -> None:
    blocks = []
    for title, metric, column, scale, digits in RANKS:
        if column not in ranking or "district_name" not in ranking:
            continue
        values = pd.to_numeric(ranking[column], errors="coerce") * scale
        frame = pd.DataFrame({"name": ranking.get("district_name"), "value": values}).dropna()
        if frame.empty:
            continue
        frame = frame.sort_values(["value", "name"], ascending=[False, True])
        top, last = frame.head(5), frame.iloc[-1]
        highest = float(top.value.iloc[0]) or 1.0
        rows = "".join(
            f'<li class="{"rank-first" if rank == 1 else "rank-caution" if rank in (2, 3) else "rank-other"}"><span class="n">{rank}</span><span>{escape(str(item.name))}'
            f'{"<sup>*</sup>" if column in COMMUTER_COLUMNS and item.name in COMMUTER_DISTRICTS else ""}</span>'
            f'<span class="t"><span style="width:{100 * item.value / highest:.1f}%"></span></span>'
            f'<span class="v">{item.value:.{digits}f}</span></li>'
            for rank, item in enumerate(top.itertuples(), start=1))
        # 작은 양수가 0으로 보이면 수록 자료가 없는 것처럼 읽힌다.
        last_digits = 2 if 0 < last.value < 0.1 else digits
        blocks.append(f'<div class="home-rank-card"><div class="home-rank-heading"><h3>{title}</h3><span class="m">{metric}</span></div><ol>{rows}</ol>'
                      f'<span class="last">가장 낮은 곳 · {escape(str(last["name"]))} {last.value:.{last_digits}f}</span></div>')
    if not blocks:
        return
    st.subheader("25구 순위", anchor=False)
    st.html('<div class="home-ranks">' + "".join(blocks) + "</div>")
    st.caption("* 중구·종로구는 출퇴근 인구가 몰려 주민 기준 값이 체감보다 크게 나와요.")


def render(row: pd.Series, ranking: pd.DataFrame) -> None:
    st.html(CSS)
    with st.container(gap="large", key="home_extras"):
        next_steps(row, ranking)
        quick_menu()
        seoul_overview(ranking)
        top_ranks(ranking)
