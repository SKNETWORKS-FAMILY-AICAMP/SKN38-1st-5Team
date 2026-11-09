import altair as alt
import pandas as pd
import streamlit as st

from db import queries as q
from ui import date_text, display_table, load_frame, load_options


def complete_total(values: pd.Series) -> int | None:
    if values.empty or values.isna().any():
        return None
    # 좁은 정수형의 넘침을 피하려고 int64로 합산한다.
    return int(values.astype("int64").sum())


def count_text(value: int | None) -> str:
    return "자료 없음" if value is None or pd.isna(value) else f"{int(value):,}대"


options = load_options()
vehicle_types = options.get("vehicle_types")
type_names = (dict(zip(vehicle_types.vehicle_type_code, vehicle_types.vehicle_type_name))
              if vehicle_types is not None else {})
usage_names = {"official": "관용", "private": "자가용", "commercial": "영업용"}
with st.container(border=True, gap="small", key="national_filters"):
    st.markdown("**조회 조건**")
    province_picker, type_picker, usage_picker = st.columns(3, gap="medium")
    with province_picker:
        province = st.selectbox(
            "시도", [None, *options.get("provinces", [])],
            format_func=lambda value: "전체 시도" if value is None else value,
            key="national_province", width="stretch", persist_state="session",
        )
    with type_picker:
        vehicle_type = st.selectbox(
            "차종", [None, *type_names],
            format_func=lambda value: type_names.get(value, "전체 차종"),
            key="national_type", width="stretch", persist_state="session",
        )
    with usage_picker:
        usage = st.selectbox(
            "용도", [None, *options.get("usage_codes", [])],
            format_func=lambda value: usage_names.get(value, "전체 용도"),
            key="national_usage", width="stretch", persist_state="session",
        )

frame = load_frame(q.get_national_registrations, province_name=province,
                   vehicle_type_code=vehicle_type, usage_code=usage)
if frame.empty:
    st.info("선택한 조건의 등록 자료가 없어요. 필터를 바꿔 살펴보세요.")
    st.stop()

frame = frame.copy()
total = complete_total(frame.vehicle_count)
seoul_rows = frame.loc[frame.province_name.astype(str).str.startswith("서울")]
seoul_total = complete_total(seoul_rows.vehicle_count)
province_count = frame.province_name.nunique()

st.caption(
    f"자료 기준 {date_text(frame.iloc[0].stat_month, month=True)} · "
    "원본에 수록된 시도만 포함해요. 한 달 자료라 월별 증감은 알 수 없어요."
)
seoul_text = (
    "선택에서 제외" if seoul_rows.empty and province is not None
    and not str(province).startswith("서울") else count_text(seoul_total)
)
with st.grid(3, min_column_width=280, gap="medium"):
    st.metric("선택 조건 합계", count_text(total), border=True,
              help="현재 시도·차종·용도 조건의 등록 대수를 합한 값이에요.")
    st.metric("서울 등록", seoul_text, border=True,
              help="현재 선택 조건에 포함된 서울의 등록 대수예요.")
    st.metric("자료에 있는 지역", f"{province_count:,}개", border=True,
              help="현재 조건의 원본 자료에 실제로 수록된 지역 수예요.")
if frame.province_name.eq("전남광주").any():
    st.caption("지역 이름은 원본 자료를 따라요. '전남광주'는 한 지역으로 세어요.")

totals = (
    frame.groupby("province_name", observed=True, sort=False)["vehicle_count"]
    .agg(complete_total).reset_index()
)
totals["is_seoul"] = totals.province_name.astype(str).str.startswith("서울")
valid_totals = totals.loc[totals.vehicle_count.notna()].copy()
if not valid_totals.empty:
    valid_totals["vehicle_count"] = valid_totals.vehicle_count.astype("int64")

chart_column, table_column = st.columns([3, 2], gap="medium")
with chart_column:
    with st.container(border=True, key="national_chart_card"):
        st.markdown("**시도마다 차가 얼마나 있을까요?**")
        st.caption("현재 선택 조건 기준 · 서울은 코랄색 막대로 표시했어요."
                   if valid_totals.is_seoul.any() else "현재 선택 조건의 시도별 등록 대수예요.")
        if valid_totals.empty:
            st.caption("시도별 합계 자료 없음")
        else:
            province_labels = valid_totals.province_name.astype(str).tolist()
            plot_height = max(160, len(valid_totals) * 28)
            chart = (
                alt.Chart(valid_totals).mark_bar(cornerRadiusEnd=6).encode(
                    x=alt.X("vehicle_count:Q", title="등록 대수",
                            axis=alt.Axis(format=",.0f", tickCount=4, labelFontSize=15, titleFontSize=15)),
                    y=alt.Y("province_name:N", title=None, sort="-x",
                            axis=alt.Axis(values=province_labels, labelLimit=150, labelFontSize=15,
                                          labelOverlap=False, labelBound=False)),
                    color=alt.condition(alt.datum.is_seoul, alt.value("#FF7A66"), alt.value("#27336B")),
                    tooltip=[alt.Tooltip("province_name:N", title="시도"),
                             alt.Tooltip("vehicle_count:Q", title="등록 대수", format=",.0f")],
                ).properties(height=plot_height, padding={"left": 5, "top": 5, "bottom": 5, "right": 16}).configure_view(stroke=None).configure_axis(
                    labelFontSize=15, titleFontSize=15, labelColor="#1B2340", titleColor="#4A5270",
                    labelFont="Noto Sans KR", titleFont="Noto Sans KR",
                    gridColor="#C8CDE3", domainColor="#C8CDE3", tickColor="#C8CDE3",
                )
            )
            # Streamlit이 축까지 포함한 높이에 맞추므로 눈금 공간을 별도로 확보한다.
            highlight_text = " 서울을 코랄색으로 강조해요." if valid_totals.is_seoul.any() else ""
            st.altair_chart(chart, key="national_province_chart", width="stretch",
                            height=plot_height + 64,
                            alt=f"선택한 조건의 {len(valid_totals)}개 시도별 자동차 등록 대수. 모든 시도 이름을 표시해요.{highlight_text}")
        missing = totals.loc[totals.vehicle_count.isna(), "province_name"].astype(str).tolist()
        if missing:
            st.caption(f"합계 자료 없음: {', '.join(missing)}. 빠진 항목이 있어 막대와 전체 합계를 확정하지 않았어요.")

with table_column:
    with st.container(border=True, key="national_table_card"):
        st.markdown("**등록 자료 표**")
        st.caption(f"선택 조건에 맞는 {len(frame):,}개 항목 · 단위: 대")
        frame["usage_name"] = frame.usage_code.astype(object).map(usage_names)
        count_column = st.column_config.NumberColumn(format="localized")
        if frame.vehicle_count.isna().any():
            # Arrow 직렬화를 위해 숫자와 결측 표시를 같은 문자열 타입으로 맞춘다.
            frame["vehicle_count"] = frame.vehicle_count.map(
                lambda value: "자료 없음" if pd.isna(value) else f"{int(value):,}"
            )
            count_column = st.column_config.TextColumn(alignment="right")
        display_table(
            frame, {"province_name": "시도", "vehicle_type_name": "차종",
                    "usage_name": "용도", "vehicle_count": "등록 대수"},
            "시도와 차종, 용도별 등록 차량 수",
            column_config={"등록 대수": count_column},
        )
