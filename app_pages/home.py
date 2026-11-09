import streamlit as st

from db import queries as q
from details import facility_details, registration_details, transit_details
from ui import (date_text, district_row, incomplete_transit, judgment_tabs, load_frame,
                ranking_list, source_notes)

ranking = load_frame(q.get_district_ranking)
if ranking.empty:
    st.info("동네 판정 자료가 없어요.")
    st.stop()

region_id = int(st.session_state.district_id)
row = district_row(ranking, region_id)
judgment_tabs(row)
st.caption("이사 후보 두 곳의 차량, 주차, 대중교통을 나란히 비교해 보세요.")
st.page_link("app_pages/compare.py", label="이사 후보 두 동네 비교하기", icon=":material/compare_arrows:")
topic = st.session_state.topic

with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
    with st.popover("판정 기준과 출처", icon=":material/info:"):
        source_notes(row)
    st.caption(f"등록 {date_text(row.get('stat_month'), month=True)} · 차 필요성은 {date_text(row.get('need_stat_date'))} 하루 이용으로 추정 · 주차는 수록 주차장만 집계(아파트 제외)")

if incomplete_transit(row):
    st.caption("이 구의 승객 수에는 일부 행정동 자료가 빠져 있어요. 실제 이용 규모보다 적게 집계될 수 있어요.")

with st.expander("자세한 자료 보기", icon=":material/table_chart:",
                 on_change="rerun", key="b_details") as details:
    if details.open:
        detail = st.segmented_control("자료 종류", ["25구 순위", "차량 구성", "주차·충전 시설", "시간대별 승객"],
                                      default="25구 순위", key="detail_topic") or "25구 순위"
        if detail == "25구 순위":
            ranking_list(ranking, topic)
        elif detail == "차량 구성":
            registration_details(region_id)
        elif detail == "주차·충전 시설":
            facility_details(region_id)
        else:
            transit_details(region_id, row)
