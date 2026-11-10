import pandas as pd
import streamlit as st

from db import queries as q
from ui import (date_text, district_row, incomplete_transit, judgment_tabs, load_frame,
                number, ranking_list, source_notes, word)


def complete_sum(values: pd.Series) -> int | None:
    if values.empty or values.isna().any():
        return None
    # 좁은 정수형의 넘침을 피하려고 int64로 합산한다.
    return int(values.astype("int64").sum())


def ratio(part: int | None, whole: int | None, scale: int = 1) -> float | None:
    return None if part is None or not whole else scale * part / whole


ranking = load_frame(q.get_district_ranking)
if ranking.empty:
    st.info("동네 판정 자료가 없어요.")
    st.stop()

row = district_row(ranking, int(st.session_state.district_id))
st.subheader(f":orange[**{word(row.get('district_name'))}**]의 세 가지 판정", anchor=False)
judgment_tabs(row)

seoul = ranking.reindex(columns=[
    "district_name", "vehicle_count", "household_count", "electric_count", "listed_count",
    "listed_station_count", "fast_count", "unique_space_count", "unique_missing_space_count",
    "listed_row_count", "transit_passenger_count", "transit_passenger_per_resident", "population",
])
vehicles, households, electric = (complete_sum(seoul[name]) for name in ("vehicle_count", "household_count", "electric_count"))
chargers, stations, fast = (complete_sum(seoul[name]) for name in ("listed_count", "listed_station_count", "fast_count"))
population = complete_sum(seoul.population)
# 24시간이 다 관측되지 않은 구가 있으면 줄어든 승객 합계를 내지 않는다.
passengers = complete_sum(seoul.transit_passenger_count.where(seoul.transit_passenger_per_resident.notna()))
# 면수를 모르는 주차장이 있는 구가 있으면 합계를 확정하지 않는다.
spaces = complete_sum(seoul.unique_space_count.where(seoul.unique_missing_space_count.eq(0)))
partial_transit = [word(item.district_name) for _, item in ranking.iterrows() if incomplete_transit(item)]
passenger_note = (f"{date_text(row.get('need_stat_date'))} 하루 · "
                  f"주민 1명당 {number(ratio(passengers, population), 2, '명')}")
if partial_transit:
    passenger_note += f" · {', '.join(partial_transit)}는 일부 행정동이 빠진 값이에요"

st.subheader("서울 자동차 현황", anchor=False)
with st.grid(3, min_column_width=260, gap="small"):
    for label, value, note in (
        ("등록 차량", number(vehicles, suffix="대"),
         f"서울 {len(ranking)}구 합계 · 등록 기준 {date_text(row.get('stat_month'), month=True)}"),
        ("세대당 차량", number(ratio(vehicles, households), 2, "대"), f"세대수 {number(households)}"),
        ("전기차", number(electric, suffix="대"), f"등록 차량의 {number(ratio(electric, vehicles, 100), 1, '%')}"),
        ("수록 충전기", number(chargers, suffix="기"),
         f"환경공단 자료 · 충전소 운영묶음 {number(stations, suffix='곳')} · 급속 {number(fast, suffix='기')}"),
        ("수록 주차면", number(spaces, suffix="면"),
         f"차 100대당 {number(ratio(spaces, vehicles, 100), 1, '면')} · 아파트 주차장 제외"),
        ("하루 대중교통 승객", number(passengers, suffix="명"), passenger_note),
    ):
        with st.container(border=True, height="stretch", gap="xsmall"):
            st.metric(label, value)
            st.caption(note)

st.subheader("항목별 25구 순위", anchor=False)
st.caption("항목마다 상위 5개와 가장 낮은 곳을 보여 드려요. 순위는 반올림 전 값으로 정하고, 행을 누르면 그 동네를 골라요.")
ranked = ranking.copy().assign(charging_value=ranking.get("charger_per_electric_vehicle"),
                        charging_rank=ranking.get("charger_per_electric_vehicle_rank"))
with st.grid(4, min_column_width=270, gap="small"):
    for topic, title in (("ownership", "차량"), ("parking", "주차"), ("charging", "충전"), ("need", "대중교통")):
        with st.container(border=True, height="stretch", gap="xsmall"):
            st.markdown(f"**{title}**")
            ranking_list(ranked, topic)

st.caption("중구·종로구는 출퇴근 유입으로 주민 수에 비해 승객 값이 커질 수 있어요.")
single_lot = seoul.loc[seoul.listed_row_count.eq(1), "district_name"].astype(str).tolist()
if single_lot:
    st.caption(f"{', '.join(single_lot)}는 수록 주차장이 1곳뿐이라 주차 순위를 그대로 비교하기 어려워요.")
if incomplete_transit(row):
    st.caption("이 구의 승객 수에는 일부 행정동 자료가 빠져 있어요. 실제 이용 규모보다 적게 집계될 수 있어요.")

with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
    with st.popover("판정 기준과 출처", icon=":material/info:"):
        source_notes(row)
    st.caption(f"등록 {date_text(row.get('stat_month'), month=True)} · 차 필요성은 {date_text(row.get('need_stat_date'))} 하루 이용으로 추정 · 주차는 수록 주차장만 집계(아파트 제외)")

with st.container(horizontal=True, gap="medium"):
    st.page_link("app_pages/compare.py", label="두 동네 비교하기", icon=":material/compare_arrows:")
    st.page_link("app_pages/parking.py", label="주차·충전 찾기", icon=":material/local_parking:")
