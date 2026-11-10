from html import escape
from math import isclose

import altair as alt
import pandas as pd
import streamlit as st

from db import queries as q
from ui import (
    TOPICS, date_text, district_row, incomplete_transit, load_frame,
    load_options, number, rank_text, topic_value, word,
)


def select_first_district() -> None:
    selected = int(st.session_state.compare_first_id)
    st.session_state.district_id = selected
    st.session_state.selected_region_id = selected


def difference(row: pd.Series, other: pd.Series, topic: str) -> tuple[str, bool]:
    raw, reference = row.get(f"{topic}_value"), other.get(f"{topic}_value")
    if raw is None or reference is None or pd.isna(raw) or pd.isna(reference):
        return "비교 자료 없음", False
    if topic == "need" and (incomplete_transit(row) or incomplete_transit(other)):
        return "부분 관측으로 비교에 주의", False
    raw, reference = float(raw), float(reference)
    if isclose(raw, reference, rel_tol=1e-9, abs_tol=1e-12):
        return "근거값이 같아요", False
    spec = TOPICS[topic]
    gap = abs(raw - reference) * spec.multiplier
    unit = {"ownership": "대", "parking": "면", "need": "명"}[topic]
    # 표시 단위보다 작은 차이는 방향을 강조하지 않는다.
    step = 10 ** -spec.digits
    if gap < step and not isclose(gap, step, rel_tol=1e-9, abs_tol=1e-12):
        threshold = f"{step:.{spec.digits}f}"
        return f"거의 같아요 · {threshold}{unit} 미만 차이", False
    amount = number(gap, spec.digits)
    more = raw > reference
    if topic == "ownership":
        return f"세대당 {amount}대 {'더 많아요' if more else '더 적어요'}", more
    if topic == "parking":
        return f"차 100대당 {amount}면 {'더 많아요' if more else '더 적어요'}", more
    return f"주민 1명당 하루 승객이 {amount}명 {'더 많아요' if more else '더 적어요'}", not more


def comparison_table(left: pd.Series, right: pd.Series, left_name: str, right_name: str) -> str:
    groups = (
        ("차와 주차", (
            ("세대당 차량", "ownership_value", 2, "대", "ownership"),
            ("차 100대당 주차면", "parking_value", 1, "면", "parking"),
            ("주차 여유", "parking_level", -1, "", None),
        )),
        ("대중교통", (
            ("주민 1명당 하루 승객", "need_value", 2, "명", "need"),
            ("차 필요도", "need_level", -1, "", None),
        )),
        ("전기차", (
            ("전기차 1대당 충전기", "charger_per_electric_vehicle", 2, "기", None),
            ("전기차 비율", "electric_share_pct", 2, "%", None),
            ("충전소", "listed_station_count", 0, "묶음", None),
            ("급속 충전기", "fast_count", 0, "기", None),
        )),
        ("동네 규모", (
            ("인구", "population", 0, "명", None),
            ("세대", "household_count", 0, "세대", None),
            ("등록 차량", "vehicle_count", 0, "대", None),
        )),
    )
    parts = ['<table class="compare-table" role="table"><caption>두 동네 항목별 비교</caption>',
             '<thead role="rowgroup"><tr role="row"><th scope="col">항목</th>']
    for index, (name, row) in enumerate(((left_name, left), (right_name, right))):
        parts.append(f'<th id="compare-district-{index}" scope="col" role="columnheader">'
                     f'<span class="compare-note">{"기준 동네" if index == 0 else "함께 보는 동네"}</span>'
                     f'<span class="compare-name">{escape(name)}</span>')
        for topic, label in (("ownership", "차량 보유"), ("parking", "주차 여유"), ("need", "차 필요도")):
            parts.append(f'<span class="compare-judgment">{label} · '
                         f'{escape(word(row.get(f"{topic}_level")))}</span>')
        parts.append(f'<span class="compare-note">등록·주민 '
                     f'{date_text(row.get("stat_month"), month=True)}</span></th>')
    parts.append('</tr></thead>')
    for title, fields in groups:
        parts.append(f'<tbody role="rowgroup"><tr class="compare-group" role="row">'
                     f'<th colspan="3" scope="colgroup">{title}</th></tr>')
        for label, field, digits, unit, topic in fields:
            parts.append(f'<tr role="row"><th id="compare-{field}" scope="row" role="rowheader">{label}</th>')
            for index, (row, other) in enumerate(((left, right), (right, left))):
                raw, reference = row.get(field), other.get(field)
                value = (topic_value(row, topic, brief=True) if topic else
                         word(raw) if digits < 0 else number(raw, digits, unit))
                value_html = escape(value)
                if digits >= 0 and raw is not None and pd.notna(raw):
                    value_html = (f'<span class="compare-number">{escape(value.removesuffix(unit))}</span>'
                                  f'<span class="compare-unit">{unit}</span>')
                parts.append(f'<td role="cell" headers="compare-{field} compare-district-{index}">'
                             f'<strong class="compare-value">{value_html}</strong>')
                if (digits >= 0 and raw is not None and reference is not None
                        and pd.notna(raw) and pd.notna(reference)):
                    multiplier = TOPICS[topic].multiplier if topic else 1
                    step = 10 ** -digits
                    gap = (float(raw) - float(reference)) * multiplier
                    more = (not isclose(float(raw), float(reference), rel_tol=1e-9, abs_tol=1e-12)
                            and (gap > step or isclose(gap, step, rel_tol=1e-9, abs_tol=1e-12)))
                    if topic == "need" and (incomplete_transit(row) or incomplete_transit(other)):
                        more = False
                    if more:
                        parts.append('<span class="compare-more">더 많음</span>')
                rank = row.get(f'{topic}_rank' if topic else f'{field}_rank') if digits >= 0 else None
                if raw is not None and pd.notna(raw) and rank is not None and pd.notna(rank):
                    text = rank_text(row, topic) if topic else f'서울 25구 중 {int(rank)}위'
                    parts.append(f'<span class="compare-note compare-rank">{escape(text)}</span>')
                if topic:
                    text, _ = difference(row, other, topic)
                    parts.append(f'<span class="compare-note compare-difference">{escape(text)}</span>')
                parts.append('</td>')
            parts.append('</tr>')
        parts.append('</tbody>')
    parts.append('</table>')
    return ''.join(parts)


COMPARE_STYLE = """
<style>
.compare-table { width: 100%; table-layout: fixed; border-collapse: collapse; color: #1B2340; font: inherit; }
.compare-table caption { text-align: left; margin-bottom: 16px; font-weight: 600; }
.compare-table th, .compare-table td { padding: 16px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
.compare-table th { font-weight: 600; }
.compare-table thead th:first-child { width: 26%; }
.compare-table thead th { background: #EEF0FA; }
.compare-table tbody tr:not(.compare-group) { border-bottom: 1px solid #C8CDE3; }
.compare-table .compare-group th { border-top: 2px solid #27336B; padding-top: 24px; font-size: 22px; }
.compare-table .compare-name { display: block; font-family: Jua, sans-serif; font-size: 30px; font-weight: 400; margin: 4px 0 12px; }
.compare-table .compare-judgment { display: block; font-size: 18px; font-weight: 400; margin-bottom: 8px; }
.compare-table .compare-value { display: flex; flex-wrap: wrap; align-items: baseline; gap: 3px; font-size: 2rem; font-weight: 800; color: #27336B; font-variant-numeric: tabular-nums; line-height: 1.4; }
.compare-table .compare-number { white-space: nowrap; }
.compare-table .compare-unit { font-size: 18px; font-weight: 400; }
.compare-table .compare-note { display: block; margin-top: 6px; color: #4A5270; font-size: 16px; font-weight: 400; line-height: 1.6; }
.compare-table .compare-difference { font-size: 18px; }
.compare-table .compare-more { display: inline-block; margin-top: 6px; padding: 2px 10px; border-radius: 16px; background: #EEF0FA; color: #27336B; font-size: 16px; font-weight: 600; }
@media (max-width: 640px) {
  .compare-table, .compare-table thead, .compare-table tbody { display: block; }
  .compare-table tr { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .compare-table th, .compare-table td { min-width: 0; padding: 12px 8px; }
  .compare-table thead th:first-child { display: none; }
  .compare-table tbody th { grid-column: 1 / -1; padding-bottom: 0; }
  .compare-table .compare-group th { padding-bottom: 12px; }
}
</style>
"""


regions = load_options().get("regions")
if regions is None or regions.empty:
    st.info("비교할 동네 자료가 없어요.")
    st.stop()

names = dict(zip(regions.region_id.astype("int64"), regions.district_name.astype(str)))
ids = list(names)
selected_id = st.session_state.get("district_id", ids[0])
if selected_id not in names:
    selected_id = ids[0]
st.session_state.compare_first_id = selected_id
if st.session_state.get("compare_id") not in names:
    st.session_state.compare_id = next((value for value in ids if value != selected_id), selected_id)

with st.container(border=True, gap="small", key="compare_pickers"):
    st.markdown("**비교할 두 동네를 선택해 주세요**")
    left_picker, right_picker = st.columns(2, gap="medium")
    with left_picker:
        left_id = st.selectbox(
            "기준 동네", ids, format_func=lambda value: names[value],
            key="compare_first_id", on_change=select_first_district,
            persist_state="session", width="stretch",
        )
    with right_picker:
        right_id = st.selectbox(
            "함께 비교할 동네", ids, format_func=lambda value: names[value],
            key="compare_id", persist_state="session", width="stretch",
        )
if left_id == right_id:
    st.info("같은 동네를 골랐어요. 다른 동네를 선택하면 차이를 비교할 수 있어요.")

comparison = load_frame(q.get_compare_metrics, left_id, right_id)
if comparison.empty:
    st.info("선택한 두 동네의 비교 자료가 없어요.")
    st.stop()

left_row, right_row = district_row(comparison, left_id), district_row(comparison, right_id)
st.caption("‘더 많음’은 표시 단위 이상 차이가 나는 수치에 붙어요. 좋고 나쁨을 뜻하지 않아요. 순위는 값이 많은 순서예요.")
st.html(COMPARE_STYLE + comparison_table(left_row, right_row, names[left_id], names[right_id]))
st.caption("주민당 승객 수가 적은 쪽을 차 필요성이 더 높은 동네로 추정해요.")
for region_id in dict.fromkeys((left_id, right_id)):
    row = district_row(comparison, region_id)
    if incomplete_transit(row):
        st.caption(f"{names[region_id]}는 일부 행정동의 승객 자료가 빠져 있어요. 실제 이용 규모보다 적게 집계될 수 있어요.")
    listed = row.get("listed_row_count")
    if listed is not None and pd.notna(listed) and listed == 1:
        st.caption(f"{names[region_id]}는 수록 주차장이 {number(listed, suffix='곳')}뿐이어서 지역 전체의 주차 여건으로 해석하기 어려워요.")
st.caption("서울 25구 비교에 따른 추정이에요. 주차는 수록 주차장 기준이며 아파트 주차장은 빠져 있어요.")
st.caption("충전소는 장소 수가 아니라 운영 묶음 수예요. 같은 장소에 여러 운영 묶음이 있을 수 있어요.")
with st.popover("비교 기준", icon=":material/info:"):
    st.write("보유는 세대당 차량 수, 주차는 차 100대당 수록 주차면을 비교해요. 실제 빈자리 수는 아니에요.")
    st.write("차 필요성은 주민 1명당 하루 대중교통 승객 수가 적을수록 높다고 추정해요. 순위는 승객이 많은 순서이며 개인의 차량 구매 필요를 확정하지 않아요.")
    for region_id, row in ((left_id, left_row), (right_id, right_row)):
        st.caption(f"{names[region_id]} · 승객 기준 {date_text(row.get('need_stat_date'))}")

details = st.expander("어떤 차가 많을까요? 차종과 전기차 비교", key="compare_details", on_change="rerun")
if details.open:
    with details:
        unique_ids = list(dict.fromkeys((left_id, right_id)))
        summary = pd.DataFrame([
            {
                "동네": names[region_id],
                "전체 등록 차량": number(district_row(comparison, region_id).get("vehicle_count"), suffix="대"),
                "전기차 등록": number(district_row(comparison, region_id).get("electric_count"), suffix="대"),
                "전기차 비중": number(district_row(comparison, region_id).get("electric_share_pct"), 2, "%"),
            }
            for region_id in unique_ids
        ])
        st.dataframe(summary, hide_index=True, width="stretch", alt="두 동네의 전체 등록 차량과 전기차 대수, 전기차 비중")
        scope = st.pills(
            "비교할 등록 범위", ["전체 차량", "전기차"], default="전체 차량",
            key="compare_fuel_scope", required=True, persist_state="session",
        )
        st.caption("전기차는 전체 차량에 포함돼요. 두 범위를 더하지 않아요.")
        frames = [load_frame(q.get_registration_breakdown, region_id) for region_id in unique_ids]
        populated = [frame for frame in frames if not frame.empty]
        if not populated:
            st.info("차종별 등록 자료가 없어요.")
        else:
            data = pd.concat(populated, ignore_index=True)
            fuel_code = "electric" if scope == "전기차" else "all"
            data = data.loc[data.fuel_scope_code.eq(fuel_code)].copy()
            if data.empty:
                st.info("선택한 등록 범위의 자료가 없어요.")
            else:
                data["district_name"] = data.district_name.astype(str)
                data["vehicle_type_name"] = data.vehicle_type_name.astype(str)
                chart_data = data.loc[data.vehicle_count.notna()].copy()
                if not chart_data.empty:
                    chart_data["vehicle_count"] = chart_data.vehicle_count.astype("int64")
                    district_order = [names[value] for value in unique_ids]
                    chart = alt.Chart(chart_data).mark_bar(cornerRadiusEnd=6).encode(
                        x=alt.X("vehicle_count:Q", title="등록 대수", axis=alt.Axis(format=",d")),
                        y=alt.Y("vehicle_type_name:N", title=None, sort=None),
                        yOffset=alt.YOffset("district_name:N", sort=district_order),
                        color=alt.Color(
                            "district_name:N", title=None, sort=district_order,
                            scale=alt.Scale(domain=district_order, range=["#27336B", "#8E98CF"]),
                            legend=alt.Legend(orient="bottom", direction="horizontal",
                                              symbolType="circle", labelFontSize=15),
                        ),
                        tooltip=[alt.Tooltip("district_name:N", title="동네"),
                                 alt.Tooltip("vehicle_type_name:N", title="차종"),
                                 alt.Tooltip("vehicle_count:Q", title="등록 대수", format=",d")],
                    ).properties(height=260).configure_view(stroke=None).configure_axis(
                        labelFontSize=15, titleFontSize=15, labelColor="#1B2340", titleColor="#4A5270",
                        labelFont="Noto Sans KR", titleFont="Noto Sans KR",
                        gridColor="#C8CDE3", domainColor="#C8CDE3", tickColor="#C8CDE3",
                    ).configure_legend(
                        labelFontSize=15, titleFontSize=15, labelColor="#1B2340", labelFont="Noto Sans KR",
                    )
                    st.altair_chart(chart, width="stretch", height=340,
                                    alt=f"두 동네의 {scope} 차종별 등록 대수 비교. 막대와 범례는 {' 다음 '.join(district_order)} 순서예요.")
                table = data.pivot(index="vehicle_type_name", columns="district_name", values="vehicle_count")
                table = table.reindex(columns=[names[value] for value in unique_ids])
                for name in table:
                    table[name] = table[name].map(lambda value: number(value, suffix="대"))
                table = table.rename_axis("차종").reset_index()
                st.dataframe(table, hide_index=True, width="stretch", alt=f"차종별 {scope} 등록 대수 비교표. 빠진 값은 자료 없음으로 표시해요.")
                st.caption(f"등록 기준 {date_text(data.iloc[0].get('stat_month'), month=True)} · 자료가 없는 값은 그래프에서 제외하고 표에 표시해요.")
