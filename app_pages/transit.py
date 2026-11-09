from datetime import date
from math import isfinite

import altair as alt
import pandas as pd
import streamlit as st

from db import queries as q
from scene_drive import render_hero
from ui import (date_text, district_row, incomplete_transit, load_frame,
                load_options, number, rank_text, word)


TRANSIT_DAYS = {date(2026, 10, 30): "평일 · 10.30 (금)", date(2026, 10, 31): "토요일 · 10.31"}
MODES = {"bus": "버스", "subway": "지하철"}
PARTIAL_NOTICE = "이 구의 승객 수에는 일부 행정동 자료가 빠져 있어요. 실제 이용 규모보다 적게 집계될 수 있어요."
BENEFITS = (
    ("local_parking", "주차 걱정 없음", "목적지의 주차 공간을 찾거나 주차장을 오갈 필요가 없어요."),
    ("savings", "차 유지 부담 없음", "차를 소유하지 않으면 보험료와 정비를 챙길 부담을 덜 수 있어요."),
    ("menu_book", "이동 시간 활용", "직접 운전하지 않는 동안 책을 읽거나 음악을 듣고 쉬어갈 수 있어요."),
)


def _passenger_series(frame: pd.DataFrame, mode: str, day: date) -> pd.DataFrame:
    columns = ["hour_of_day", "known_passenger_sum", "valid_dong_count", "expected_dong_count"]
    if frame.empty:
        selected = pd.DataFrame({column: pd.Series(dtype="float64") for column in columns})
    else:
        selected = frame.loc[
            (frame.series_type == "passenger") & (frame.mode_code == mode)
            & (frame.stat_date == day) & (frame.analysis_type == "4"), columns,
        ].copy()
    selected = selected.set_index("hour_of_day").reindex(range(24)).reset_index()
    # Altair 5의 null 필터가 결측 양옆을 잇지 않도록 연속 구간을 구분한다.
    selected["segment"] = selected.known_passenger_sum.isna().cumsum()
    selected["day_label"] = TRANSIT_DAYS[day]
    selected["mode_code"] = mode
    return selected


def _passenger_chart(frame: pd.DataFrame) -> alt.Chart:
    labels = list(TRANSIT_DAYS.values())
    return alt.Chart(frame).mark_line(
        strokeWidth=3, point=alt.OverlayMarkDef(size=30, filled=True),
        invalid="filter",
    ).encode(
        x=alt.X("hour_of_day:Q", title="시간", scale=alt.Scale(domain=[0, 23]),
                axis=alt.Axis(values=[0, 6, 12, 18, 23], labelExpr="datum.value + '시'")),
        y=alt.Y("known_passenger_sum:Q", title="수록 승객 수(명)",
                scale=alt.Scale(zero=True), axis=alt.Axis(format=",d", tickCount=5)),
        color=alt.Color("day_label:N", title=None, sort=labels,
                        scale=alt.Scale(domain=labels, range=["#27336B", "#FF7A66"]),
                        legend=alt.Legend(orient="top", labelLimit=180)),
        strokeDash=alt.StrokeDash("day_label:N", title=None, sort=labels,
                                  scale=alt.Scale(domain=labels, range=[[1, 0], [5, 3]])),
        detail=alt.Detail("segment:O"),
        tooltip=[alt.Tooltip("day_label:N", title="날짜"),
                 alt.Tooltip("hour_of_day:Q", title="시작 시각", format="d"),
                 alt.Tooltip("known_passenger_sum:Q", title="수록 승객 수(명)", format=",d"),
                 alt.Tooltip("valid_dong_count:Q", title="관측 행정동", format="d"),
                 alt.Tooltip("expected_dong_count:Q", title="전체 행정동", format="d")],
    ).properties(height=255).configure_view(stroke=None).configure_axis(
        labelFont="Noto Sans KR", titleFont="Noto Sans KR", labelColor="#4A5270",
        titleColor="#4A5270", gridColor="#EEF0FA", domain=False,
    ).configure_legend(labelFont="Noto Sans KR", labelColor="#1B2340")


def _peak_text(frame: pd.DataFrame) -> str:
    known = frame.dropna(subset=["known_passenger_sum"])
    if known.empty:
        return "자료 없음"
    maximum = known.known_passenger_sum.max()
    if maximum == 0:
        return "수록 승객 모두 0명 · 붐비는 시간 없음"
    hours = known.loc[known.known_passenger_sum == maximum, "hour_of_day"].tolist()
    times = ", ".join(f"{int(hour):02d}~{int(hour)+1:02d}시" for hour in hours)
    if len(hours) == 24:
        times = "모든 시간 동일"
    elif len(hours) > 1:
        times += " (공동)"
    prefix = "수록된 시간 중 " if len(known) < 24 else ""
    return f"{prefix}**{times}** · {number(maximum)}명"


region_id = st.session_state.get("district_id")
if region_id is None:
    st.info("위에서 살펴볼 동네를 골라 주세요.")
    st.stop()
region_id = int(region_id)
ranking = load_frame(q.get_district_ranking)
row = district_row(ranking, region_id)
district_name = word(row.get("district_name"))
if row.empty:
    regions = load_options().get("regions", pd.DataFrame())
    district_name = word(district_row(regions, region_id).get("district_name"))

with st.container(key="transit_hero"):
    render_hero(ranking, region_id, district_name)

st.subheader(f"{district_name}, 차 없이 다니기 어떨까요?", anchor=False)
with st.container(border=True, gap="small", key="transit_judgment"):
    value = row.get("need_value")
    valid_need = value is not None and pd.notna(value) and isfinite(float(value))
    judgment, evidence, rank = st.columns([1.6, 1, 1], gap="medium")
    judgment.metric("차 필요 판정", word(row.get("need_level")) if valid_need else "자료 없음")
    evidence.metric("주민 1명당 하루 승객", number(value, 2, "명") if valid_need else "자료 없음")
    rank.metric("서울 25구 중 이용 순위", number(row.get("need_rank"), suffix="위") if valid_need else "자료 없음")
    st.caption(rank_text(row, "need") if valid_need else "순위 자료 없음")
    st.caption(
        f"판정은 {date_text(row.get('need_stat_date'))} 하루 승객 · 주민은 {date_text(row.get('stat_month'), month=True)} 기준이에요. "
        "승객 수를 주민 수로 나눈 서울 25구 안의 상대적 추정이며, 실제 차량 구매 필요를 확정하지 않아요."
    )
    st.caption("승객 수는 고유 주민 수나 주민만의 이용 횟수가 아니에요. 나의 출퇴근 경로와 이동 불편도 함께 살펴보세요.")
    if incomplete_transit(row):
        st.info(PARTIAL_NOTICE, icon=":material/info:")

st.caption("중구·종로구는 출퇴근 유입으로 주민 수에 비해 승객 값이 커질 수 있어요.")

st.subheader("버스와 지하철, 언제 많이 탈까요?", anchor=False)
st.caption("2026.10.30 금요일(평일)과 2026.10.31 토요일의 하루를 비교해요. 차 필요 판정은 10월 30일 기준으로 유지돼요.")
trends = {day: load_frame(q.get_trend_data, region_id, stat_date=day, analysis_type="4")
          for day in TRANSIT_DAYS}

for column, (mode, label) in zip(st.columns(2, gap="medium"), MODES.items()):
    with column.container(border=True, gap="small", key=f"transit_chart_{mode}"):
        st.markdown(f"### :material/{'directions_bus' if mode == 'bus' else 'subway'}: {label}")
        series = {day: _passenger_series(frame, mode, day) for day, frame in trends.items()}
        combined = pd.concat(series.values(), ignore_index=True)
        if combined.known_passenger_sum.notna().any():
            st.altair_chart(_passenger_chart(combined), width="stretch", key=f"transit_{mode}",
                            alt=f"{district_name} {label} 시간대별 수록 승객. 2026년 10월 30일 평일과 31일 토요일 비교.")
            coverage = combined.dropna(subset=["valid_dong_count", "expected_dong_count"])
            if (coverage.valid_dong_count < coverage.expected_dong_count).any():
                st.caption(PARTIAL_NOTICE)
            if combined.known_passenger_sum.isna().any():
                st.caption("승객 자료가 없는 시간은 선을 잇지 않았어요. 가장 붐비는 시간도 수록된 시간 안에서만 비교해요.")
        else:
            st.info(f"{label} 시간대별 승객은 자료 없음")
        st.markdown("**가장 붐비는 시간**")
        for day, frame in series.items():
            st.markdown(f"{TRANSIT_DAYS[day]} · {_peak_text(frame)}")

st.caption("버스와 지하철은 각 수단의 수록 승객 수예요. 전체 승객과 중복해서 더하지 않아요. 가장 붐비는 시간은 승객 수가 가장 많았던 때이며, 차량 안 혼잡도나 평소 이용량을 뜻하지 않아요.")

st.subheader("대중교통을 타면 이런 점이 좋아요", anchor=False)
for column, (icon, title, description) in zip(st.columns(3, gap="medium"), BENEFITS):
    with column.container(border=True, height="stretch", gap="small"):
        st.markdown(f"### :material/{icon}: {title}")
        st.write(description)
