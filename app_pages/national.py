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


def share_text(part: int | None, total: int | None) -> str:
    if part is None or total is None or pd.isna(part) or pd.isna(total) or total <= 0:
        return "자료 없음"
    return f"{part / total * 100:.1f}%"


options = load_options()
vehicle_types = options.get("vehicle_types")
type_names = (dict(zip(vehicle_types.vehicle_type_code, vehicle_types.vehicle_type_name))
              if vehicle_types is not None else {})
usage_names = {"private": "자가용", "commercial": "영업용", "official": "관용"}
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
capital_rows = frame.loc[frame.province_name.astype(str).str.startswith(("서울", "경기", "인천"))]
capital_total = complete_total(capital_rows.vehicle_count)
commercial_total = (0 if usage is not None and usage != "commercial" else
                    complete_total(frame.loc[frame.usage_code.eq("commercial"), "vehicle_count"]))
passenger_total = (0 if vehicle_type is not None and vehicle_type != "passenger" else
                   complete_total(frame.loc[frame.vehicle_type_code.eq("passenger"), "vehicle_count"]))
province_count = frame.province_name.nunique()

st.caption(
    f"자료 기준 {date_text(frame.iloc[0].stat_month, month=True)} · "
    f"원자료 수록 지역 중 현재 조건의 {province_count:,}개 지역 · "
    "이륜차는 제외해요. 한 달 자료라 월별 증감은 알 수 없어요."
)
st.caption(
    f"현재 조건: {province or '전체 시도'} · {type_names.get(vehicle_type, '전체 차종')} · "
    f"{usage_names.get(usage, '전체 용도')} · 합계와 비중은 모두 현재 조건 기준이며, "
    f"비중의 분모는 현재 조건 합계 {count_text(total)}예요."
)
with st.grid(4 if province is None else 3, min_column_width=280, gap="medium"):
    with st.container(border=True):
        st.metric("전국 합계" if province is None else "선택 조건 합계", count_text(total))
        st.caption(f"원자료 수록 {province_count:,}개 지역 합계")
    if province is None:
        with st.container(border=True):
            st.metric("수도권 비중", share_text(capital_total, total))
            st.caption(f"서울·경기·인천 · {count_text(capital_total)}")
    with st.container(border=True):
        st.metric("영업용 비중", share_text(commercial_total, total))
        st.caption(f"현재 조건 중 영업용 · {count_text(commercial_total)}")
    with st.container(border=True):
        st.metric("승용 비중", share_text(passenger_total, total))
        st.caption(f"현재 조건 중 승용 · {count_text(passenger_total)}")
if frame.province_name.eq("전남광주").any():
    st.caption("지역 이름은 원본 자료를 따라요. '전남광주'는 한 지역으로 세어요.")

totals = (
    frame.groupby("province_name", observed=True, sort=False)["vehicle_count"]
    .agg(complete_total).reset_index()
)
valid_totals = totals.loc[totals.vehicle_count.notna()].copy()
if not valid_totals.empty:
    valid_totals["vehicle_count"] = valid_totals.vehicle_count.astype("int64")
    valid_totals = valid_totals.sort_values("vehicle_count", ascending=False, kind="stable")

chart_column, table_column = st.columns([3, 2], gap="medium")
with chart_column:
    with st.container(border=True, key="national_chart_card"):
        st.markdown("**시도마다 차가 얼마나 있을까요?**")
        split = st.segmented_control(
            "막대 구성", ["용도별", "차종별"], default="용도별",
            key="national_split", required=True, persist_state="session",
        )
        st.caption("현재 선택 조건의 시도별 등록 대수 · 합계가 많은 순으로 표시해요.")
        if valid_totals.empty:
            st.caption("시도별 합계 자료 없음")
        else:
            segment_column = "usage_code" if split == "용도별" else "vehicle_type_code"
            segment_names = usage_names if split == "용도별" else type_names
            segments = (
                frame.loc[frame.province_name.isin(valid_totals.province_name)]
                .groupby(["province_name", segment_column], observed=True, sort=False)["vehicle_count"]
                .agg(complete_total).reset_index()
            )
            segments["vehicle_count"] = segments.vehicle_count.astype("int64")
            segments["segment_name"] = segments[segment_column].astype(object).map(segment_names)
            segment_labels = [name for name in segment_names.values() if name in segments.segment_name.values]
            segments["segment_order"] = segments.segment_name.map(
                {name: index for index, name in enumerate(segment_names.values())}
            )
            province_labels = valid_totals.province_name.astype(str).tolist()
            plot_height = max(160, len(valid_totals) * 28)
            chart = (
                alt.Chart(segments).mark_bar(cornerRadiusEnd=6).encode(
                    x=alt.X("vehicle_count:Q", title="등록 대수", stack="zero",
                            axis=alt.Axis(format=",.0f", tickCount=4, labelFontSize=15, titleFontSize=15)),
                    y=alt.Y("province_name:N", title=None, sort=province_labels,
                            axis=alt.Axis(values=province_labels, labelLimit=150, labelFontSize=15,
                                          labelOverlap=False, labelBound=False)),
                    color=alt.Color(
                        "segment_name:N", title=None, sort=segment_labels,
                        scale=alt.Scale(domain=list(segment_names.values()),
                                        range=["#27336B", "#FF7A66", "#8E98CF", "#C8CDE3"][:len(segment_names)]),
                        legend=alt.Legend(orient="top", columns=2, labelFontSize=15,
                                          labelFont="Noto Sans KR", labelColor="#1B2340"),
                    ),
                    order=alt.Order("segment_order:Q", sort="ascending"),
                    tooltip=[alt.Tooltip("province_name:N", title="시도"),
                             alt.Tooltip("segment_name:N", title="구분"),
                             alt.Tooltip("vehicle_count:Q", title="등록 대수", format=",.0f")],
                ).properties(height=plot_height, padding={"left": 5, "top": 5, "bottom": 5, "right": 16}).configure_view(stroke=None).configure_axis(
                    labelFontSize=15, titleFontSize=15, labelColor="#1B2340", titleColor="#4A5270",
                    labelFont="Noto Sans KR", titleFont="Noto Sans KR",
                    gridColor="#C8CDE3", domainColor="#C8CDE3", tickColor="#C8CDE3",
                )
            )
            # Streamlit이 축까지 포함한 높이에 맞추므로 눈금 공간을 별도로 확보한다.
            st.altair_chart(chart, key="national_province_chart", width="stretch",
                            height=plot_height + 112,
                            alt=f"선택한 조건의 {len(valid_totals)}개 시도별 자동차 등록 대수와 {split} 구성. 합계가 많은 순이며 모든 시도 이름을 표시해요.")
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
