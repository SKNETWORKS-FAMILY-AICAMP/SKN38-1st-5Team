import altair as alt
import pandas as pd
import streamlit as st

from db import queries as q
from ui import date_text, display_table, load_frame, load_options, number


NAVY = "#27336B"
MID_NAVY = "#8E98CF"
INK = "#1B2340"
MUTED = "#4A5270"
BORDER = "#C8CDE3"


def _polish_chart(chart: alt.Chart) -> alt.Chart:
    return chart.configure_view(stroke=None).configure_axis(
        labelFont="Noto Sans KR", titleFont="Noto Sans KR",
        labelFontSize=14, titleFontSize=14, labelColor=INK, titleColor=MUTED,
        gridColor=BORDER, domainColor=BORDER, tickColor=BORDER,
    )


def registration_details(region_id: int) -> None:
    st.subheader("우리 동네 차량 구성", anchor=False)
    scope = st.segmented_control(
        "등록 자료 범위", ["all", "electric"],
        format_func=lambda value: "전체 차량" if value == "all" else "전기차",
        default="all", key="detail_fuel",
    ) or "all"
    summary = load_frame(q.get_summary_metrics, region_id)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    with st.grid(3, min_column_width=200, gap="small"):
        st.metric("전체 등록 차량", number(row.get("vehicle_count"), suffix="대"), border=True)
        st.metric("전기차", number(row.get("electric_count"), suffix="대"), border=True)
        st.metric("전기차 비중", number(row.get("electric_share_pct"), 1, "%"), border=True)
    st.caption(
        f"등록 기준 {date_text(row.get('stat_month'), month=True)} · "
        "전기차는 전체 차량에 포함돼요. 휘발유·경유 등 다른 연료별 자료는 없어요."
    )
    frame = load_frame(q.get_registration_breakdown, region_id)
    if not frame.empty:
        frame = frame.loc[frame.fuel_scope_code == scope].copy()
    if frame.empty:
        st.info("선택한 범위의 차량 구성은 자료가 없어요.")
        return
    chart_data = frame.loc[frame.vehicle_count.notna()].copy()
    if not chart_data.empty:
        chart_data["vehicle_count"] = chart_data.vehicle_count.astype("int64")
        chart = alt.Chart(chart_data).mark_bar(
            color=NAVY, cornerRadiusEnd=6, size=26,
        ).encode(
            x=alt.X("vehicle_count:Q", title="등록 대수", axis=alt.Axis(format=",d", tickCount=5)),
            y=alt.Y("vehicle_type_name:N", title=None, sort=None),
            tooltip=[alt.Tooltip("vehicle_type_name:N", title="차종"),
                     alt.Tooltip("vehicle_count:Q", title="등록 대수", format=",d")],
        ).properties(height=200)
        with st.container(border=True, gap="small", key="detail_registration_chart"):
            st.markdown("**차종별 등록 현황**")
            st.altair_chart(_polish_chart(chart), width="stretch",
                            alt="선택한 구의 차종별 등록 차량 수")
    with st.container(border=True, gap="small", key="detail_registration_table"):
        st.markdown("**차종별 등록 대수**")
        display_table(
            frame, {"vehicle_type_name": "차종", "vehicle_count": "등록 대수"},
            "선택한 구의 차종별 등록 대수와 자료 없는 항목",
            column_config={"등록 대수": st.column_config.NumberColumn(format="localized")},
        )


def _facility_map(points: pd.DataFrame, kind: str) -> None:
    for coverage in points.attrs.get("coverage", []):
        st.caption(
            f"지도 표시 {number(coverage.get('point_count'), suffix='곳')} · "
            f"좌표 없음·범위 밖 {number(coverage.get('invalid_coordinate_count'), suffix='곳')} · "
            f"관리번호 겹침 {number(coverage.get('identifier_conflict_count'), suffix='건')} 제외"
        )
    if points.empty:
        st.info("원본 자료에 위치(좌표) 정보가 없어 지도에 표시할 수 없어요. 아래 목록에서 주소로 확인해 주세요.")
        return
    # 지도에는 좌표 범위와 관리번호 중복을 걸러낸 조회 결과만 사용한다.
    st.map(
        points.loc[:, ["latitude", "longitude"]], color=NAVY, size=35, height=280,
        alt=f"선택한 구에서 위치를 확인할 수 있는 {kind} 지도",
    )


def facility_details(region_id: int) -> None:
    st.subheader("주차장과 충전소 위치", anchor=False)
    kind = st.segmented_control(
        "시설 종류", ["주차장", "충전기"], default="주차장", key="detail_facility",
    ) or "주차장"
    if kind == "주차장":
        points = load_frame(q.get_place_points, region_id, kinds=("parking",))
        st.caption(
            "이름 대신 관리번호를 쓰며, 아파트 주차장과 실제 빈자리는 포함하지 않아요."
        )
        with st.container(border=True, gap="small", key="detail_parking_map"):
            st.markdown("**주차장 지도**")
            _facility_map(points, "주차장")
        # 빈 검색어로 충전소가 100건을 채우지 않도록 주차장 대체 이름으로 검색한다.
        parking = load_frame(q.search_places, "주차장 [", region_id=region_id, limit=100)
        if not parking.empty:
            parking = parking.loc[parking.kind == "parking_site"].copy()
            parking["map_note"] = parking.map_eligible.map(
                lambda value: "자료 없음" if pd.isna(value) else "지도 표시" if value else "지도 제외"
            )
        with st.container(border=True, gap="small", key="detail_parking_table"):
            st.markdown("**주차장 목록**")
            st.caption("목록은 최대 100건이며 좌표가 없는 주차장도 포함해요. 관리번호가 겹치는 항목은 지도에서 제외해요.")
            display_table(
                parking, {"display_name": "주차장", "address": "주소", "space_count": "주차면", "map_note": "지도"},
                "선택한 구의 수록 주차장과 주차면 수. 좌표가 없는 항목도 포함해요.",
            )
        return

    speed_names = {"all": "전체", "fast": "급속", "slow": "완속", "unknown": "속도 미상"}
    speed = st.pills(
        "충전 속도", list(speed_names), format_func=lambda value: speed_names[value],
        default="all", key="detail_speed",
    ) or "all"
    summary = load_frame(q.get_charger_summary, [region_id], speed=speed)
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    with st.grid(3, min_column_width=200, gap="small"):
        st.metric("급속 충전기", number(row.get("fast_count"), suffix="기"), border=True)
        st.metric("완속 충전기", number(row.get("slow_count"), suffix="기"), border=True)
        st.metric("속도 미상", number(row.get("unknown_count"), suffix="기"), border=True)
    st.caption(
        f"선택 조건의 수록 충전기 {number(row.get('listed_count'), suffix='기')} · "
        f"충전소 운영묶음 {number(row.get('listed_station_count'), suffix='곳')} · 환경공단 자료"
    )
    points = load_frame(q.get_place_points, region_id, kinds=("charger",), speed=speed)
    with st.container(border=True, gap="small", key="detail_charger_map"):
        st.markdown("**충전소 지도**")
        _facility_map(points, "충전소")
        st.caption("지도 점 하나는 같은 운영자가 묶어 관리하는 충전소예요. 좌표가 없는 충전기도 아래 목록에는 나와요.")
    frame = load_frame(q.get_charger_detail, region_id, speed=speed, limit=200)
    if not frame.empty:
        frame = frame.copy()
        frame["speed_name"] = frame.speed_code.astype(object).map(speed_names)
    with st.container(border=True, gap="small", key="detail_charger_table"):
        st.markdown("**방문 전 확인할 이용 안내**")
        st.caption(
            "충전기 목록은 최대 200기예요. 이용제한·운영시간은 수집 당시 안내이며, "
            "실시간 사용 가능 여부가 아니에요. 제한 안내가 없어도 자유 이용을 뜻하지 않아요."
        )
        display_table(
            frame,
            {"station_name": "충전소", "source_charger_id": "기기번호", "speed_name": "속도",
             "address": "주소", "capacity_text": "출력", "connector_text": "충전 방식",
             "operating_time_text": "운영시간", "restriction_note": "이용제한"},
            "선택한 구와 속도에 맞는 충전기 목록 및 이용 안내",
        )


def _weather_details() -> None:
    st.subheader("서울 날씨", anchor=False)
    weather = load_frame(q.get_weather)
    if weather.empty:
        st.info("날씨는 자료가 없어요.")
        return
    row = weather.iloc[0]
    observed = row.get("observed_at")
    timestamp = pd.Timestamp(observed) if pd.notna(observed) else None
    observed_text = (timestamp.strftime("%Y.%m.%d %H:%M")
                     if isinstance(timestamp, pd.Timestamp) else "자료 없음")
    st.caption(f"수록된 최신 관측 {observed_text} · 서울 공통 관측값으로 구별 날씨가 아니에요.")
    with st.grid(4, min_column_width=180, gap="small"):
        st.metric("기온", number(row.get("temperature_c"), 1, "℃"), border=True)
        st.metric("강수량", number(row.get("rain_mm"), 1, "mm"), border=True)
        st.metric("적설량", number(row.get("snow_cm"), 1, "cm"), border=True)
        st.metric("풍속", number(row.get("wind_speed_ms"), 1, "m/s"), border=True)
    st.caption("승객 자료와 날씨의 관측 시각은 다를 수 있어요. 강수·적설 자료 없음은 비나 눈이 없었다는 뜻이 아니에요.")


def transit_details(region_id: int, row: pd.Series) -> None:
    st.subheader("버스와 지하철, 언제 많이 탈까요?", anchor=False)
    options = load_options()
    dates = options.get("transit_dates", [])
    if not dates:
        st.info("시간대별 승객은 자료가 없어요.")
        _weather_details()
        return
    chosen_day = row.get("need_stat_date")
    default = dates.index(chosen_day) if pd.notna(chosen_day) and chosen_day in dates else 0
    day = st.selectbox("관측 날짜", dates, index=default, format_func=date_text, key="detail_day")
    types = options.get("analysis_types", [])
    chosen_type = row.get("need_analysis_type")
    if len(types) > 1:
        default_type = types.index(chosen_type) if pd.notna(chosen_type) and chosen_type in types else 0
        analysis_type = st.selectbox("집계 구분", types, index=default_type, key="detail_analysis")
    else:
        analysis_type = types[0] if types else None
    labels = {"total": "전체", "bus": "버스", "subway": "지하철"}
    mode = st.pills(
        "교통수단", list(labels), format_func=lambda value: labels[value],
        default="total", key="detail_mode",
    ) or "total"
    st.caption(
        f"승객 관측 {date_text(day)} · 등록·주민 기준 {date_text(row.get('stat_month'), month=True)} · "
        f"차 필요성 판정 기준일: {date_text(row.get('need_stat_date'))}"
    )
    frame = load_frame(q.get_trend_data, region_id, stat_date=day, analysis_type=analysis_type)
    if not frame.empty:
        frame = frame.loc[(frame.series_type == "passenger") & (frame.mode_code == mode)].copy()
    if frame.empty or not frame.known_passenger_sum.notna().any():
        st.info("선택한 날짜와 교통수단의 승객은 자료가 없어요.")
    else:
        counts = frame.loc[:, ["valid_dong_count", "expected_dong_count"]].dropna()
        if not counts.empty:
            counts = counts.astype("int64")
            if (counts.valid_dong_count < counts.expected_dong_count).any():
                st.caption("이 구의 승객 수에는 일부 행정동 자료가 빠져 있어요. 실제 이용 규모보다 적게 집계될 수 있어요.")
        chart = alt.Chart(frame).mark_line(
            color=NAVY, strokeWidth=3,
            point=alt.OverlayMarkDef(filled=True, fill=MID_NAVY, size=50),
        ).encode(
            x=alt.X("hour_of_day:Q", title="시간", axis=alt.Axis(values=[0, 6, 12, 18, 23])),
            y=alt.Y("known_passenger_sum:Q", title="수록 승객 수(명)", axis=alt.Axis(format=",d", tickCount=5)),
            tooltip=[alt.Tooltip("hour_of_day:Q", title="시간"),
                     alt.Tooltip("known_passenger_sum:Q", title="수록 승객 수", format=",d"),
                     alt.Tooltip("valid_dong_count:Q", title="관측 동 수"),
                     alt.Tooltip("expected_dong_count:Q", title="기대 동 수")],
        ).properties(height=240)
        with st.container(border=True, gap="small", key="detail_transit_chart"):
            st.markdown("**시간대별 이동**")
            st.altair_chart(_polish_chart(chart), width="stretch",
                            alt="선택한 구와 날짜의 시간대별 수록 대중교통 승객 수")
            st.caption("전체에는 버스·지하철이 포함돼요. 일부 동이 빠진 시간은 수록된 부분합이며, 이 하루를 평소 이용량으로 일반화하지 않아요.")
    _weather_details()
