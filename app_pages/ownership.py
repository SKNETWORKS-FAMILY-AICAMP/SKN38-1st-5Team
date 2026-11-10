from functools import partial

import altair as alt
import pandas as pd
import streamlit as st

import readable

from db import queries as q
from scene_city3d import render_hero
from ui import (RANK_HEIGHT, date_text, display_table, district_row, load_frame,
                number, rank_text, ranking_chart, select_rank_region, top_three, word)


def _comparison(row: pd.Series, field: str, digits: int, unit: str) -> tuple[str, str]:
    values = [row.get(field), row.get(f"{field}_seoul_avg"), row.get(f"{field}_vs_seoul")]
    if any(value is None or pd.isna(value) for value in values):
        return "서울 평균 비교 자료 없음", "off"
    arrow = "auto" if round(float(values[2]), digits) else "off"
    return f"{float(values[2]):+,.{digits}f}{unit}", arrow


def _metric(row: pd.Series, field: str, label: str, digits: int, unit: str) -> None:
    delta, arrow = _comparison(row, field, digits, "%p" if field == "electric_share_pct" else unit)
    with st.container(border=True, height="stretch", gap="xsmall", key=f"ownership_metric_{field}"):
        st.metric(label, number(row.get(field), digits, unit), delta=delta,
                  delta_color="off", delta_arrow=arrow, delta_description="서울 평균 대비")
        average = number(row.get(f"{field}_seoul_avg"), digits, unit)
        count = row.get(f"{field}_seoul_count")
        included = f" · {int(count)}개 구 기준" if count is not None and pd.notna(count) else ""
        st.caption(f"서울 평균 {average}{included}")


def _polish(chart: alt.Chart | alt.LayerChart) -> alt.Chart | alt.LayerChart:
    return chart.configure_view(stroke=None).configure_axis(
        labelFont="Noto Sans KR", titleFont="Noto Sans KR", labelFontSize=15, titleFontSize=15,
        labelColor="#1B2340", titleColor="#4A5270", gridColor="#EEF0FA",
    ).configure_legend(labelFont="Noto Sans KR", labelFontSize=15, labelColor="#1B2340")


def _vehicle_composition(frame: pd.DataFrame, scope: str, district_name: str) -> None:
    required = {"fuel_scope_code", "vehicle_type_name", "vehicle_count"}
    if frame.empty or not required.issubset(frame.columns):
        st.info("차종 구성은 자료 없음이에요.")
        return
    # all에 전기차가 포함되므로 두 범위를 합산하지 않는다.
    rows = frame.loc[frame.fuel_scope_code == scope].copy()
    missing = rows.loc[rows.vehicle_count.isna(), "vehicle_type_name"].astype(str).tolist()
    if missing:
        st.caption(f"자료 없음: {', '.join(missing)}")
    table = rows
    rows = rows.loc[rows.vehicle_count.notna()]
    if rows.empty:
        st.info("선택한 범위의 차종 구성은 자료 없음이에요.")
        return
    rows = top_three(rows, "vehicle_count", "ownership_vehicle")
    base = alt.Chart(rows).encode(
        y=alt.Y("vehicle_type_name:N", title=None, sort=None),
        x=alt.X("vehicle_count:Q", title="등록 대수", axis=alt.Axis(format=",d", tickCount=4),
                scale=alt.Scale(zero=True)),
        tooltip=[alt.Tooltip("vehicle_type_name:N", title="차종"),
                 alt.Tooltip("vehicle_count:Q", title="등록 대수", format=",d")],
    )
    highest = int(rows.vehicle_count.max())
    bars = base.mark_bar(size=26, cornerRadiusEnd=5).encode(
        color=alt.condition(alt.datum.vehicle_count == highest, alt.value("#E76F51"), alt.value("#8E98CF")),
    )
    labels = base.mark_text(align="left", x=5, dx=0, dy=-23, color="#1B2340", fontSize=15).encode(
        x=alt.value(5), text=alt.Text("vehicle_count:Q", format=",d"),
    )
    chart = (bars + labels).properties(height=310, padding={"left": 5, "top": 5, "bottom": 5, "right": 16})
    st.altair_chart(_polish(chart), width="stretch", key="ownership_vehicle_types",
                    alt=f"{district_name} {'전체 차량' if scope == 'all' else '전기차'}의 차종별 등록 대수")
    with st.expander("상세보기 · 차종별 전체 등록 대수"):
        display_table(table, {"vehicle_type_name": "차종", "vehicle_count": "등록 대수"},
                      f"{district_name} 차종별 등록 대수와 자료 없는 항목",
                      column_config={"등록 대수": st.column_config.NumberColumn(format="localized")})


def _fuel_composition(row: pd.Series, district_name: str) -> None:
    total, electric, share = (row.get(field) for field in ("vehicle_count", "electric_count", "electric_share_pct"))
    if (any(value is None or pd.isna(value) for value in (total, electric, share))
            or total <= 0 or electric < 0 or electric > total or not 0 <= share <= 100):
        st.info("연료 구성은 자료 없음이에요.")
        return
    # 작은 unsigned 정수형의 넘침을 피하려고 Python int로 계산한다.
    fuel = pd.DataFrame({
        "fuel": ["전기차", "전기차 외"],
        "count": [int(electric), int(total) - int(electric)],
        "share": [float(share), 100 - float(share)],
    })
    chart = alt.Chart(fuel).mark_arc(innerRadius=58).encode(
        theta=alt.Theta("count:Q", stack=True),
        color=alt.Color("fuel:N", title=None, sort=None,
                        scale=alt.Scale(domain=["전기차", "전기차 외"], range=["#FF7A66", "#8E98CF"]),
                        legend=alt.Legend(orient="bottom")),
        order=alt.Order("share:Q", sort="ascending"),
        tooltip=[alt.Tooltip("fuel:N", title="연료 범위"),
                 alt.Tooltip("count:Q", title="등록 대수", format=",d"),
                 alt.Tooltip("share:Q", title="비중 (%)", format=".2f")],
    ).properties(height=310)
    st.altair_chart(_polish(chart), width="stretch", key="ownership_fuel_composition",
                    alt=f"{district_name} 전체 차량 중 전기차와 전기차 외 차량의 구성")
    st.caption(f"전기차 {number(electric, suffix='대')} · 전기차 외 {number(int(total) - int(electric), suffix='대')}")


region_id = int(st.session_state.district_id)
ranking = load_frame(q.get_district_ranking)
summary = load_frame(q.get_summary_metrics, region_id)
row = district_row(summary, region_id)
rank_row = district_row(ranking, region_id)
district_name = word(row.get("district_name"), word(rank_row.get("district_name"), "선택한 동네"))

render_hero(district_name, ranking=ranking)

st.html("""<style>
.st-key-ownership_content [class*="st-key-ownership_metric_"] {
  min-height: 190px; border-radius: 16px; border-color: #DCE1ED;
}
.st-key-ownership_content [class*="st-key-ownership_metric_"] [data-testid="stMetricLabel"] {
  min-height: 48px; color: #1B2340;
}
.st-key-ownership_content [class*="st-key-ownership_metric_"] [data-testid="stMetricValue"] {
  color: #27336B; font-variant-numeric: tabular-nums;
}
.st-key-ownership_content [class*="st-key-ownership_metric_"] [data-testid="stCaptionContainer"] {
  margin-top: auto;
}
.st-key-ownership_vehicle_panel, .st-key-ownership_fuel_panel {
  min-height: 540px; border-radius: 16px; border-color: #DCE1ED;
}
.st-key-ownership_vehicle_header, .st-key-ownership_fuel_header { min-height: 132px; }
.st-key-ownership_content [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Up"]) { color: #C81E1E; background-color: #FEE2E2; }
.st-key-ownership_content [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Down"]) { color: #1D4ED8; background-color: #DBEAFE; }
</style>""")

with st.container(gap="small", key="ownership_content"):
    st.subheader(f":orange[**{district_name}**]의 차량 보유 현황", anchor=False)
    level = word(row.get("ownership_level"))
    st.markdown(f"**차량 보유 {level}** · {rank_text(row, 'ownership')}")
    st.caption(f"등록 기준 {date_text(row.get('stat_month'), month=True)} · 같은 달의 등록 차량과 세대수로 비교해요.")
    readable.cards(rank_row, ranking, ("own", "ev"), title="서울 평균과 견주면")
    with st.grid(4, min_column_width=225, gap="small"):
        _metric(row, "vehicle_count", "등록 차량", 0, "대")
        _metric(row, "vehicle_per_household", "세대당 차량", 2, "대")
        _metric(row, "electric_count", "전기차", 0, "대")
        _metric(row, "electric_share_pct", "전기차 비중", 2, "%")
    st.caption("서울 평균은 자료가 있는 구별 값의 산술평균이에요. 비율도 구별 비율의 평균이며, 서울 전체 합계로 계산한 비율과 달라요. 전기차 비중 차이는 %p로 표시해요.")

    st.subheader("어떤 차가 등록되어 있을까요?", anchor=False)
    breakdown = load_frame(q.get_registration_breakdown, region_id)
    vehicle_column, fuel_column = st.columns(2, gap="medium")
    with vehicle_column.container(border=True, height="stretch", gap="small", key="ownership_vehicle_panel"):
        with st.container(gap="small", key="ownership_vehicle_header"):
            st.markdown("**차종 구성**")
            scope = st.segmented_control(
                "차종 구성 범위", ["all", "electric"], default="all", key="ownership_scope",
                format_func=lambda value: "전체 차량" if value == "all" else "전기차",
            ) or "all"
        _vehicle_composition(breakdown, scope, district_name)
    with fuel_column.container(border=True, height="stretch", gap="small", key="ownership_fuel_panel"):
        with st.container(gap="small", key="ownership_fuel_header"):
            st.markdown("**연료 구성**")
            st.caption("전기차는 전체 등록 차량에 포함돼요. 휘발유·경유 등 세부 연료별 자료는 없어요.")
        _fuel_composition(row, district_name)

    st.subheader("서울 25구, 세대당 차량은 얼마나 될까요?", anchor=False)
    st.caption("차량 보유는 한 세대당 등록된 차량 수로 비교해요. 값이 큰 순서이며, 동률은 같은 순위예요. 숫자는 소수 둘째 자리까지 보여 드리고 순위는 반올림 전 값으로 정해서, 보이는 숫자가 같아도 순위가 다를 수 있어요. 1위부터 8위는 많은 편, 9위부터 17위는 보통, 18위부터 25위는 적은 편이에요.")
    if ranking.empty:
        st.info("서울 25구 순위는 자료 없음이에요.")
    else:
        key = f"ownership_ranking_{st.session_state.get('rank_epoch', 0)}"
        shown = top_three(ranking, "ownership_value", "ownership_ranking")
        st.altair_chart(ranking_chart(shown, "ownership", region_id), key=key,
                        on_select=partial(select_rank_region, key), selection_mode="rank",
                        width="stretch", height=max(120, len(shown) * 30),
                        alt="서울 25구의 세대당 차량 보유 순위. 행을 누르면 해당 구를 선택해요.")
