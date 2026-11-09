from pathlib import Path

import streamlit as st

from idle_nudge import add_idle_nudge
from security import add_noindex, add_view_deterrent, guard_request

# 차단 대상 요청이 조회 모듈에 접근하지 않도록 import 전에 검사한다.
guard_request()

from ui import TOPICS, load_options, remember_region
from site_shell import footer, hero, navbar, page_header, styles

st.set_page_config(
    page_title="차차차 · 서울에서 차와 살기",
    page_icon=(
        Path(__file__).parent / "assets" / "chachacha-icons-v1" / "navy" / "favicon-64.png"
    ),
    layout="wide",
)

pages = [
    st.Page("app_pages/home.py", title="우리 동네", icon=":material/map:",
            default=True, help="서울 지도에서 차량 보유, 주차 여건, 차 필요성을 확인해요."),
    st.Page("app_pages/ownership.py", title="차량 보유", url_path="ownership",
            icon=":material/directions_car:", help="서울 25구의 차량 보유 현황을 입체 지도로 살펴볼 수 있어요."),
    st.Page("app_pages/parking.py", title="주차 찾기", url_path="parking",
            icon=":material/local_parking:", help="동네의 주차 여건과 주차장 위치를 찾을 수 있어요."),
    st.Page("app_pages/charging.py", title="전기차 충전", url_path="charging",
            icon=":material/ev_station:", help="충전기 구성과 충전소 위치를 살펴볼 수 있어요. 실시간 빈자리 정보는 아니에요."),
    st.Page("app_pages/transit.py", title="대중교통", url_path="transit",
            icon=":material/directions_bus:", help="차 없이 다닐 때의 좋은 점과 동네 대중교통 흐름을 살펴볼 수 있어요."),
    st.Page("app_pages/roads.py", title="도로와 날씨", url_path="roads",
            icon=":material/traffic:", help="수록된 시간대별 교통량과 날씨 표본을 살펴볼 수 있어요."),
    st.Page("app_pages/compare.py", title="두 동네 비교", url_path="compare",
            icon=":material/compare_arrows:", help="두 구의 세 판정과 근거를 같은 기준으로 비교해요."),
    st.Page("app_pages/national.py", title="전국 등록 조회", url_path="national",
            icon=":material/directions_car:", help="시도, 차종, 용도별 자동차 등록 자료를 조회해요."),
    st.Page("app_pages/faq.py", title="차차차 FAQ", url_path="faq",
            icon=":material/help:", help="차차차 이용 안내와 기업이 안내한 자동차 질문을 확인해요."),
    st.Page("app_pages/ask.py", title="물어보기", url_path="ask",
            icon=":material/chat_bubble:", help="궁금한 동네와 자동차 생활을 물어보고 근거 자료를 확인해요."),
    st.Page("app_pages/about.py", title="자료 안내", url_path="about",
            icon=":material/info:", help="자료 출처, 기준 시점, 판정 규칙과 자료의 한계를 확인해요."),
]
page = st.navigation(pages, position="hidden")
styles()

st.session_state.setdefault("topic", "ownership")
st.session_state.setdefault("map_epoch", 0)
if st.session_state.topic not in TOPICS:
    st.session_state.topic = "ownership"

with st.container(gap=0, key="site_root"):
    add_noindex()
    add_view_deterrent()
    add_idle_nudge(page.url_path)
    options = load_options()
    navbar(pages, page, options, remember_region)
    regions = options.get("regions")
    content = st.container(gap="small", key="site_content")
    with content:
        if page.url_path == "":
            names = (dict(zip(regions.region_id.astype(int), regions.district_name.astype(str)))
                     if regions is not None and not regions.empty else {})
            hero(names.get(st.session_state.get("district_id"), "자료 없음"))
        elif page.url_path not in ("ownership", "parking", "transit"):
            page_header(page.url_path)
    # st.stop()으로 페이지가 끝나도 푸터가 남도록 먼저 그린다.
    footer(pages)
    with content:
        if (regions is None or regions.empty) and page.url_path not in ("national", "faq", "ask", "about"):
            st.info("조회할 동네 자료가 없어요. 위 메뉴에서 다른 자료를 살펴보세요.")
        else:
            page.run()
