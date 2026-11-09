import base64
from html import escape
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import streamlit as st


ASSETS = Path(__file__).parent / "assets"

CSS = """
<style>
/* 기본 머리말에는 key를 지정할 수 없어 test id로 숨긴다. */
[data-testid="stHeader"] { display: none; }
[data-testid="stMainBlockContainer"] { padding-top: 0; }
/* caption에는 key가 없어 test id로 선택하고 기본 투명도를 해제한다. */
.st-key-site_root [data-testid="stCaptionContainer"] {
  color: #4A5270; font-size: 14px; line-height: 1.5; opacity: 1;
}
.st-key-site_root { --site-navy: #27336B; --site-ink: #1B2340; }
.st-key-site_root h1, .st-key-site_root h2, .st-key-site_root h3,
.st-key-site_root p { word-break: keep-all; overflow-wrap: anywhere; }
.st-key-site_navbar { position: relative; padding: 15px 0; background: #fff; }
.st-key-site_navbar::after {
  content: ""; position: absolute; bottom: 0; left: 0; right: 0; height: 2px;
  background: #C8CDE3;
  /* 컨테이너 바깥까지 배경 띠를 펼치기 위해 그림자를 쓴다. */
  box-shadow: 0 0 0 100vmax #C8CDE3; clip-path: inset(0 -100vmax);
}
/* key 블록의 부모가 세로 flex이므로 basis를 고정하지 않는다. */
.st-key-site_brand { flex: 0 0 auto; }
.st-key-site_brand .brand-home, .st-key-footer_brand .brand-home {
  display: inline-flex; align-items: center; gap: 8px; padding: 0; margin: 0;
  color: #27336B; font: 400 34px/1.15 Jua, sans-serif; text-decoration: none; white-space: nowrap;
}
.st-key-site_menu { gap: 4px; overflow: visible; }
.st-key-site_menu a {
  border-radius: 999px; min-height: 44px; padding: 9px 10px;
  color: #1B2340; white-space: nowrap;
}
/* Jua는 굵기가 하나뿐이라 합성 굵기를 쓰지 않는다. */
.st-key-site_menu a p, .st-key-site_menu button p, .st-key-site_more_links a p {
  font-family: Jua, sans-serif; font-size: 17px; font-weight: 400;
}
.st-key-site_menu [data-testid="stIconMaterial"] { font-size: 18px; color: #27336B; }
.st-key-site_menu a:hover { color: #27336B; background: #EEF0FA; }
.st-key-site_menu button {
  min-height: 44px; padding: 9px 10px; border-radius: 999px;
  color: #1B2340; font-size: 14px; white-space: nowrap;
}
.st-key-nav_more_current button { background: #EEF0FA; border-color: #27336B; }
.st-key-site_more_links a {
  min-height: 44px; padding: 9px 12px; border-radius: 16px; color: #1B2340;
}
.st-key-site_more_links a:hover { background: #EEF0FA; color: #27336B; }
.st-key-site_more_links [class*="st-key-more_"] { min-height: 48px; }
.st-key-site_more_links [class*="st-key-more_current_"] a {
  background: #EEF0FA; color: #27336B; text-decoration: underline;
}
.st-key-site_more_links a:focus-visible { outline: 3px solid #27336B; }
.st-key-site_menu [class*="st-key-nav_current_"] a {
  color: #27336B; background: #EEF0FA;
}

.st-key-site_menu [class*="st-key-nav_current_"] a p {
  text-decoration: underline; text-underline-offset: 5px; text-decoration-thickness: 2px;
}
.st-key-site_picker { flex: 0 0 auto; }
.st-key-site_hero {
  background: #EEF0FA; padding: 16px 0;
  box-shadow: 0 0 0 100vmax #EEF0FA; clip-path: inset(0 -100vmax);
}
.st-key-hero_copy { flex: 0 0 auto; }
.st-key-hero_copy h1 { color: #1B2340; line-height: 1.22; padding: 0; margin: 0; }
.st-key-hero_copy p { font-size: 17px; line-height: 1.65; }
.st-key-hero_art { flex: 0 0 auto; }
/* 장식용 이미지의 확대 도구는 st.image의 공개 옵션으로 끌 수 없다. */
.st-key-site_brand [data-testid="stElementToolbar"],
.st-key-footer_brand [data-testid="stElementToolbar"],
.st-key-hero_art [data-testid="stElementToolbar"] { display: none; }
.st-key-hero_eyebrow p { font-size: 14px; color: #27336B; font-weight: 600; }
.st-key-judgment_deck { position: relative; margin-top: 18px; padding-bottom: 12px; }
.st-key-judgment_ownership, .st-key-judgment_parking, .st-key-judgment_need {
  background: #fff; border: 2px solid #C8CDE3; border-radius: 24px; padding: 14px 18px;
}
.st-key-judgment_deck [data-testid="stMetricValue"] {
  color: #27336B; font-size: 38px; line-height: 1.25; font-variant-numeric: tabular-nums;
}
.st-key-judgment_deck a { font-size: 13px; min-height: 36px; padding: 5px 0; }
.st-key-judgment_deck a p { font-size: 13px; }
/* wrap=False가 만드는 가로 스크롤을 이 영역에서 해제한다. */
.st-key-judgment_deck [class*="st-key-judgment_line_"] { overflow: visible; }
.st-key-judgment_deck [class*="st-key-judgment_evidence_"] p {
  display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 8px;
  color: #4A5270; font-size: 14px; line-height: 1.4;
}
.st-key-judgment_deck [class*="st-key-judgment_evidence_"] strong {
  color: #27336B; font-size: 32px; font-weight: 800; line-height: 1.2;
  font-variant-numeric: tabular-nums;
}
.st-key-judgment_deck button {
  min-height: 36px; border: 0; padding: 5px 12px; border-radius: 999px;
  justify-content: flex-start; color: #1B2340; background: #EEF0FA;
}
.st-key-judgment_deck button p { font-size: 16px; font-weight: 600; }
.st-key-judgment_deck button:hover { color: #27336B; outline: 1px solid #27336B; }
.st-key-judgment_deck [class*="st-key-tab_active_"] button { color: #fff; background: #27336B; }
.st-key-judgment_deck [class*="st-key-tab_active_"] button p { font-weight: 700; }
.st-key-judgment_ownership:has(.st-key-tab_active_ownership),
.st-key-judgment_parking:has(.st-key-tab_active_parking),
.st-key-judgment_need:has(.st-key-tab_active_need) { border-color: #27336B; }
.st-key-judgment_deck [class*="st-key-signal_level_"] {
  border-radius: 999px; padding: 4px; height: 32px; align-items: center; justify-content: center;
}
.st-key-judgment_deck [class*="st-key-signal_level_"] p { line-height: 24px; }
.st-key-judgment_deck [class*="st-key-signal_level_0_"],
.st-key-summary_signals [class*="st-key-summary_level_0_"] { background: #27336B; color: #fff; }
.st-key-judgment_deck [class*="st-key-signal_level_1_"],
.st-key-summary_signals [class*="st-key-summary_level_1_"] { background: #8E98CF; color: #1B2340; }
.st-key-judgment_deck [class*="st-key-signal_level_2_"],
.st-key-summary_signals [class*="st-key-summary_level_2_"] { background: #EEF0FA; color: #1B2340; border: 1px solid #C8CDE3; }
.st-key-judgment_deck [class*="st-key-signal_level_3_"],
.st-key-summary_signals [class*="st-key-summary_level_3_"] { background: #E4E7E6; color: #4A5270; }
.st-key-site_content { padding-bottom: 32px; }
.st-key-site_page_header {
  background: #EEF0FA; padding: 25px 0; margin-bottom: 24px;
  box-shadow: 0 0 0 100vmax #EEF0FA; clip-path: inset(0 -100vmax);
}
.st-key-site_page_header h1 { padding: 0; line-height: 1.3; font-size: 36px; }
.st-key-site_page_header p { color: #4A5270; font-size: 16px; }
.st-key-map_panel { background: #fff; border: 2px solid #C8CDE3; border-radius: 24px; padding: 14px 16px; }
.st-key-map_panel p { font-size: 16px; }
.st-key-map_panel strong { color: #27336B; }
.st-key-reading_panel { padding-left: 4px; }
.st-key-neighborhood_summary { background: #EEF0FA; border: none; padding: 16px 18px; border-radius: 24px; }
.st-key-neighborhood_summary p { word-break: keep-all; overflow-wrap: normal; }
.st-key-neighborhood_summary h2 { padding: 0 0 6px; margin: 0; line-height: 1.25; }
.st-key-summary_signals { margin-top: 4px; }
.st-key-summary_signals [class*="st-key-summary_level_"] { border-radius: 999px; padding: 4px 9px; }
.st-key-summary_signals p { font-size: 14px; line-height: 1.5; }
.st-key-b_details { margin-top: 10px; }
.st-key-site_footer {
  position: relative; background: #1B2340; color: #fff; padding: 33px 0;
  box-shadow: 0 0 0 100vmax #1B2340;
  clip-path: inset(0 -100vmax);
}
.st-key-site_footer::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: #FF7A66; box-shadow: 0 0 0 100vmax #FF7A66;
  clip-path: inset(0 -100vmax); pointer-events: none;
}
.st-key-footer_brand .brand-home { color: #fff; font-size: 30px; }
.st-key-site_footer p { font-size: 14px; line-height: 1.7; color: #EEF0FA; margin: 8px 0 0; }
.st-key-footer_menu { max-width: 680px; }
.st-key-footer_menu a { color: #fff; min-height: 44px; padding: 6px 10px; border-radius: 999px; }
.st-key-footer_menu a:hover { background: #27336B; }
.st-key-footer_menu a p { color: #fff; margin: 0; font-size: 15px; }
.footer-intro { max-width: 420px; }
.st-key-site_root a:focus-visible, .st-key-site_root button:focus-visible {
  outline: 3px solid #27336B; outline-offset: 3px;
}
.st-key-site_footer a:focus-visible { outline-color: #FF7A66; }
/* ── 디자인 다듬기: 카드 그림자, 얇은 테두리, 일관된 모서리 ── */
.st-key-site_root { --site-line: #DDE1F0; --site-shadow: 0 6px 20px rgba(39, 51, 107, .07);
  --site-shadow-hover: 0 12px 28px rgba(39, 51, 107, .12); }
.st-key-judgment_ownership, .st-key-judgment_parking, .st-key-judgment_need, .st-key-map_panel {
  border-width: 1px; border-color: var(--site-line); box-shadow: var(--site-shadow);
  transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}
.st-key-judgment_ownership:hover, .st-key-judgment_parking:hover, .st-key-judgment_need:hover {
  transform: translateY(-2px); box-shadow: var(--site-shadow-hover);
}
.st-key-judgment_ownership:has(.st-key-tab_active_ownership),
.st-key-judgment_parking:has(.st-key-tab_active_parking),
.st-key-judgment_need:has(.st-key-tab_active_need) {
  border-color: #27336B; box-shadow: 0 0 0 1px #27336B, var(--site-shadow-hover);
}
.st-key-site_root [data-testid="stMetric"] {
  background: #fff; border-color: var(--site-line); border-radius: 18px; box-shadow: var(--site-shadow);
  transition: box-shadow .18s ease, transform .18s ease;
}
.st-key-site_root [data-testid="stMetric"]:hover { transform: translateY(-2px); box-shadow: var(--site-shadow-hover); }
.st-key-site_root [data-testid="stMetricLabel"] p { color: #4A5270; font-weight: 600; }
.st-key-site_root [data-testid="stMetricValue"] {
  color: #27336B; font-weight: 800; letter-spacing: -.02em; font-variant-numeric: tabular-nums;
}
.st-key-site_page_header h1::after {
  content: ""; display: block; width: 44px; height: 5px; margin-top: 12px;
  border-radius: 3px; background: #FF7A66;
}
.st-key-site_root [data-testid="stAlertContainer"] {
  border-radius: 16px; background: #F5F6FB; color: #1B2340; border: 1px solid var(--site-line);
}
.st-key-site_root [data-testid="stAlertContainer"] [data-testid="stIconMaterial"] { color: #27336B; }
.st-key-site_root [data-testid="stExpander"] details {
  border-radius: 18px; border-color: var(--site-line); background: #fff; box-shadow: var(--site-shadow);
}
.st-key-site_root [data-testid="stExpander"] summary:hover { background: #F5F6FB; color: #27336B; }
.st-key-site_root [data-testid="stDataFrame"] {
  border: 1px solid var(--site-line); border-radius: 14px; overflow: hidden;
}
.st-key-site_root [data-testid="stVegaLiteChart"], .st-key-site_root [data-testid="stDeckGlJsonChart"] {
  border-radius: 16px; overflow: hidden;
}
.st-key-site_root [data-testid="stPageLink-NavLink"] { transition: background-color .15s ease, color .15s ease; }
.st-key-judgment_deck a:hover p { color: #27336B; text-decoration: underline; text-underline-offset: 4px; }
.st-key-site_root [data-testid="stTextInputRootElement"], .st-key-site_root [data-baseweb="select"] > div {
  border-radius: 12px;
}
@media (prefers-reduced-motion: reduce) {
  .st-key-site_root * { transition: none !important; }
  .st-key-judgment_ownership:hover, .st-key-judgment_parking:hover, .st-key-judgment_need:hover,
  .st-key-site_root [data-testid="stMetric"]:hover { transform: none; }
}
@media (max-width: 1100px) {
  /* 가로 배치의 flex 항목은 key 블록 바깥의 래퍼다. */
  .st-key-site_root [data-testid="stLayoutWrapper"]:has(> .st-key-site_brand) { flex: 1 1 145px; order: 0; }
  .st-key-site_root [data-testid="stLayoutWrapper"]:has(> .st-key-site_picker) { flex: 0 0 164px; order: 1; }
  .st-key-site_root [data-testid="stLayoutWrapper"]:has(> .st-key-site_menu) { flex: 1 0 100%; order: 2; }
  .st-key-site_menu { justify-content: space-between; }
  .st-key-site_menu a { padding: 9px 8px; }
  .st-key-site_root [data-testid="stLayoutWrapper"]:has(> .st-key-hero_copy) { flex-basis: 480px; }
  .st-key-site_root [data-testid="stLayoutWrapper"]:has(> .st-key-hero_art) { flex-basis: 230px; }
  .st-key-hero_copy h1 { font-size: 36px; }
  .st-key-judgment_ownership, .st-key-judgment_parking, .st-key-judgment_need { padding: 12px; }
}
@media (max-width: 700px) {
  .st-key-site_navbar { padding: 12px 0; gap: 10px; }
  .st-key-site_root [data-testid="stLayoutWrapper"]:has(> .st-key-site_brand) { flex: 1 1 130px; order: 0; }
  .st-key-site_brand .brand-home { font-size: 29px; }
  .st-key-site_root [data-testid="stLayoutWrapper"]:has(> .st-key-site_picker) { flex: 0 0 148px; order: 1; }
  .st-key-site_root [data-testid="stLayoutWrapper"]:has(> .st-key-site_menu) { flex: 1 0 100%; order: 2; }
  .st-key-site_menu { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); grid-auto-rows: minmax(44px, auto); gap: 2px; overflow: visible; }
  .st-key-site_menu > * { width: 100%; min-width: 0; }
  .st-key-site_menu a { padding: 5px 3px; font-size: 12px; min-height: 44px; justify-content: center; flex-direction: column; gap: 1px; }
  .st-key-site_menu a p { font-size: 14px; white-space: normal; overflow: visible; text-overflow: clip; }
  .st-key-site_menu button { padding: 7px 3px; width: 100%; }
  .st-key-site_menu button p { font-size: 14px; }
  .st-key-site_hero { padding: 24px 0; }
  .st-key-site_root [data-testid="stLayoutWrapper"]:has(> .st-key-hero_copy) { flex-basis: 100%; }
  .st-key-hero_copy h1 { font-size: 33px; line-height: 1.3; max-width: 330px; }
  .st-key-hero_copy p { font-size: 15px; }
  .st-key-hero_eyebrow p { font-size: 14px; }
  .st-key-site_root [data-testid="stLayoutWrapper"]:has(> .st-key-hero_art) { flex: 0 1 240px; margin: 0 auto; }
  .st-key-judgment_deck { margin-top: 12px; padding-bottom: 10px; }
  .st-key-judgment_ownership, .st-key-judgment_parking, .st-key-judgment_need { padding: 14px; }
  .st-key-site_page_header { padding: 24px 0; margin-bottom: 18px; }
  .st-key-site_page_header h1 { font-size: 30px; }
  .st-key-map_panel { padding: 12px 4px; }
  .st-key-reading_panel { padding: 0; }
  .st-key-site_footer { padding: 28px 0; }
  .st-key-footer_menu { gap: 0; }
  .st-key-footer_menu a { padding: 7px 8px; }
}
</style>
"""


def styles() -> None:
    st.html(CSS)


def brand() -> None:
    base_path = str(st.get_option("server.baseUrlPath") or "").strip("/")
    home_url = f"/{base_path}/" if base_path else "/"
    logo = base64.b64encode((ASSETS / "logo.svg").read_bytes()).decode("ascii")
    st.html(
        f'<a class="brand-home" href="{escape(home_url, quote=True)}" target="_self" '
        'aria-label="차차차 메인 화면으로 이동">'
        f'<img src="data:image/svg+xml;base64,{logo}" width="42" height="42" alt="" aria-hidden="true">'
        '<span>차차차</span></a>'
    )


def navbar(pages: Sequence[st.Page], current: st.Page,
           options: dict[str, Any], on_change: Callable[[], None]) -> None:
    primary_paths = {"", "ownership", "parking", "transit"}
    more_pages = [page for page in pages if page.url_path not in primary_paths]
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="site_navbar"):
        with st.container(width=156, key="site_brand"):
            brand()
        with st.container(horizontal=True, vertical_alignment="center", gap="xxsmall", wrap=False, key="site_menu"):
            for index, page in enumerate(pages):
                if page.url_path not in primary_paths:
                    continue
                active = "current" if page.url_path == current.url_path else "other"
                with st.container(width="content", key=f"nav_{active}_{index}"):
                    st.page_link(page, label=page.title, icon=page.icon, width="content")
            if more_pages:
                active = "current" if current.url_path not in primary_paths else "other"
                with st.container(width="content", key=f"nav_more_{active}"):
                    with st.popover("더 보기"):
                        with st.container(gap="xxsmall", key="site_more_links"):
                            for index, page in enumerate(more_pages):
                                selected = "current" if page.url_path == current.url_path else "other"
                                with st.container(key=f"more_{selected}_{index}"):
                                    st.page_link(page, label=page.title, icon=page.icon, width="stretch")
        with st.container(width=164, key="site_picker"):
            regions = options.get("regions")
            if regions is not None and not regions.empty:
                names = dict(zip(regions.region_id.astype(int), regions.district_name.astype(str)))
                ids = list(names)
                default = next((key for key, name in names.items() if name == "마포구"), ids[0])
                if st.session_state.get("selected_region_id") not in ids:
                    st.session_state.selected_region_id = default
                st.session_state.district_id = st.session_state.selected_region_id
                st.selectbox("살펴볼 동네", ids, format_func=lambda value: names[value],
                             key="district_id", icon=":material/location_on:",
                             on_change=on_change, label_visibility="collapsed", persist_state="session")


def hero(district_name: str) -> None:
    from scene_seoul import render_hero

    with st.container(key="site_hero"):
        render_hero(district_name)


def page_header(path: str) -> None:
    headings = {
        "charging": ("우리 동네 충전 여건은 어떨까요?", "전기차 대비 충전기 수와 충전소 위치를 살펴볼 수 있어요. 실시간 빈자리 정보는 아니에요."),
        "roads": ("어느 시간에 길이 붐빌까요?", "평일과 주말의 수록 교통량을 비교하고, 날씨 표본도 함께 살펴볼 수 있어요."),
        "about": ("차차차가 사용하는 자료", "자료 출처와 기준 시점, 세 가지 판정의 규칙과 한계를 확인할 수 있어요."),
        "compare": ("어느 동네가 더 잘 맞을까요?", "두 동네의 차량 보유, 주차 여건, 차 필요성을 나란히 비교해요."),
        "national": ("전국에는 차가 얼마나 있을까요?", "시도와 차종, 용도를 선택해 자동차 등록 현황을 조회할 수 있어요."),
        "faq": ("자주 묻는 질문", "차차차 이용 안내와 기업이 안내한 자동차 질문을 확인할 수 있어요."),
        "ask": ("차차차에게 물어보세요", "우리 동네 자동차 생활, 차차차 자료에서 답을 찾아 드려요."),
    }
    title, description = headings[path]
    with st.container(gap="xsmall", key="site_page_header"):
        st.title(title, anchor=False)
        st.markdown(description)


def footer(pages: Sequence[st.Page]) -> None:
    with st.container(gap="medium", key="site_footer"):
        with st.container(horizontal=True, vertical_alignment="center", gap="large"):
            with st.container(width="stretch"):
                with st.container(key="footer_brand"):
                    brand()
                st.html('<p class="footer-intro">차차차 · 서울에서 차와 살기<br>서울 25구의 차량 보유, 주차 여건, 차 필요성을 한눈에 비교할 수 있어요.</p>')
            with st.container(horizontal=True, gap="xsmall", wrap=True, width="stretch", key="footer_menu"):
                for page in pages:
                    st.page_link(page, label=page.title, icon="", width="content")
