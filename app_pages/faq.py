from urllib.parse import urlsplit

import streamlit as st

from content_faq import FAQ_ITEMS
from db import queries as q
from ui import date_text, load_frame, load_options, word


def reset_filters() -> None:
    st.session_state.faq_keyword = ""
    st.session_state.faq_company = None
    st.session_state.faq_category = None


def source_link(value: object) -> str | None:
    url = word(value, "").strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    return url if parts.scheme in ("https", "http") and parts.netloc else None


faq_kind = st.segmented_control(
    "FAQ 종류", ["기업 FAQ", "차차차 FAQ"], default="기업 FAQ",
    required=True, key="faq_kind", label_visibility="collapsed",
)

if faq_kind == "차차차 FAQ":
    st.subheader("차차차, 이렇게 읽어요", anchor=False)
    st.caption("서비스 이용부터 판정 기준, 자료와 개인정보까지 궁금한 질문을 펼쳐 보세요.")
    columns = st.columns(2, gap="medium")
    rows_per_column = (len(FAQ_ITEMS) + 1) // 2
    for index, column in enumerate(columns):
        with column:
            for item in FAQ_ITEMS[index * rows_per_column:(index + 1) * rows_per_column]:
                with st.expander(item.question, key=f"chachacha_faq_{item.key}"):
                    st.markdown(item.answer)
else:
    options = load_options()
    companies = options.get("faq_companies")
    company_names = (dict(zip(companies.company_id.astype("int64"), companies.company_name.map(word)))
                     if companies is not None and not companies.empty else {})
    with st.container(border=True, gap="small", key="faq_search_panel"):
        st.subheader("질문 검색", anchor=False)
        search_column, company_column, category_column = st.columns(
            [2, 1, 1], gap="small", vertical_alignment="bottom"
        )
        with search_column:
            keyword = st.text_input("질문과 답변 검색", placeholder="충전, 배터리, 이용 방법이 궁금해요",
                                    max_chars=500, key="faq_keyword", icon=":material/search:",
                                    persist_state="page")
        with company_column:
            company = st.selectbox("기업", [None, *company_names],
                                   format_func=lambda value: company_names.get(value, "전체 기업"),
                                   key="faq_company", persist_state="page")
        with category_column:
            category = st.selectbox("분류", [None, *options.get("faq_categories", [])],
                                    format_func=lambda value: "전체 분류" if value is None else value,
                                    key="faq_category", persist_state="page")
    frame = load_frame(q.search_faq, keyword.strip(), company_id=company, category=category, limit=50)
    if frame.empty:
        with st.container(border=True, gap="small", key="faq_empty"):
            if keyword.strip() or company is not None or category is not None:
                st.info("조건에 맞는 질문이 없어요. 검색어를 짧게 바꾸거나, 조건을 풀고 다시 검색해 주세요.",
                        title="찾는 질문이 안 보이나요?", icon=":material/search:")
                st.button("검색 조건 다시 고르기", key="faq_reset", on_click=reset_filters,
                          icon=":material/restart_alt:")
            else:
                st.info("다른 메뉴에서 우리 동네 자동차 생활을 먼저 살펴보세요.",
                        title="아직 모아 둔 질문이 없어요", icon=":material/chat_bubble:")
                st.caption("기업 FAQ · 자료 없음")
    else:
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.caption(f"질문 {len(frame):,}개")
            st.caption("질문을 누르면 답변이 펼쳐져요. 답변은 수집 당시 기업 안내 그대로예요.")
        columns = st.columns(min(2, len(frame)), gap="medium")
        rows_per_column = (len(frame) + len(columns) - 1) // len(columns)
        for index, column in enumerate(columns):
            with column:
                for _, row in frame.iloc[index * rows_per_column:(index + 1) * rows_per_column].iterrows():
                    with st.expander(word(row.question), key=f"faq_{row.company_id}_{row.faq_key}"):
                        answer = word(row.answer_text)
                        st.markdown(answer if answer.strip() else "자료 없음")
                        st.caption(f"{word(row.company_name)} · {word(row.category)} · 수집 {date_text(row.fetched_on)}")
                        url = source_link(row.source_url)
                        if url:
                            st.link_button("기업 원문에서 확인", url, icon=":material/open_in_new:")
                        else:
                            st.caption("원문 링크: 자료 없음")
