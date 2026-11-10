import pandas as pd
import streamlit as st

import readable

from db import queries as q


# 각 지표는 값이 클수록 사용자에게 유리한 방향이다.
METRICS = {
    "parking": ("parking_value", "주차", "차 100대당 주차면", 100, "면", 1),
    "transit": ("need_value", "대중교통", "주민 1명당 하루 승객", 1, "명", 2),
    "charging": ("charger_per_electric_vehicle", "충전", "전기차 1대당 충전기", 1, "기", 2),
}
CAR_OPTIONS = ("있어요", "살 예정이에요", "없어요")
EV_OPTIONS = ("아니요", "예")
FOCUS_OPTIONS = ("균형 있게", "주차", "대중교통")


def weights(car: str, ev: str, focus: str) -> dict[str, int]:
    has_car = car != "없어요"
    result = {"parking": 3 if has_car else 0, "transit": 1 if has_car else 4,
              "charging": 3 if has_car and ev == "예" else 0}
    if focus == "주차" and has_car:
        result["parking"] += 2
    elif focus == "대중교통":
        result["transit"] += 2
    return result


def score_table(ranking: pd.DataFrame, weight: dict[str, int]) -> pd.DataFrame:
    table = ranking[["region_id", "district_name", "vehicle_per_household"]].copy()
    total = pd.Series(0.0, index=ranking.index)
    used = pd.Series(0.0, index=ranking.index)
    for key, (column, *_rest) in METRICS.items():
        values = pd.to_numeric(ranking[column], errors="coerce")
        table[key] = values
        table[f"{key}_rank"] = values.rank(ascending=False, method="min")
        if weight[key]:
            percentile = values.rank(pct=True, method="average") * 100
            total += percentile.fillna(0) * weight[key]
            used += values.notna() * weight[key]
    table["score"] = (total / used.where(used > 0)).round(0)
    return table.sort_values(["score", "district_name"], ascending=[False, True]).reset_index(drop=True)


def reason_lines(row: pd.Series, weight: dict[str, int]) -> list[str]:
    lines = []
    for key in sorted(weight, key=weight.get, reverse=True):
        if not weight[key]:
            continue
        _column, _short, label, scale, unit, digits = METRICS[key]
        value = row[key]
        if pd.isna(value):
            lines.append(f"{label}: 자료 없음")
            continue
        phrase, _tone = readable.compare_phrase(value * scale, AVERAGES.get(key, 0) * scale,
                                                readable.METRICS[READABLE_KEYS[key]])
        lines.append(f"{label} {value * scale:.{digits}f}{unit} · {phrase} (서울 {int(row[f'{key}_rank'])}위)")
    return lines


def caution(row: pd.Series, weight: dict[str, int]) -> str | None:
    if weight["transit"] and row.district_name in ("중구", "종로구"):
        return "출퇴근 유입이 많아 주민 대비 승객 값이 크게 나오는 구예요."
    if weight["transit"] and row.district_name == "강서구":
        return "일부 행정동의 승객 자료가 빠져 실제보다 낮게 계산됐을 수 있어요."
    return None


def open_district(region_id: int, page: str) -> None:
    st.session_state.selected_region_id = int(region_id)
    st.switch_page(page)


ranking = q.get_district_ranking()
if ranking is None or ranking.empty:
    st.info("비교할 동네 자료가 없어요. 잠시 후 다시 시도해 주세요.")
    st.stop()

st.html("""<style>
.st-key-finder_form [data-testid="stWidgetLabel"] p {
  font-size:22px;font-weight:800;color:#27336B;line-height:1.5;
}
.st-key-finder_cards [data-testid="stColumn"] {display:flex;align-items:stretch;}
.st-key-finder_cards [data-testid="stColumn"] > div {width:100%;height:100%;}
.st-key-finder_cards [class*="st-key-finder_pick_"] {
  height:100%;min-height:460px;box-sizing:border-box;padding:22px;
  display:flex;flex-direction:column;background:#FFFFFF;
}
.st-key-finder_cards .st-key-finder_pick_0 {background:#DCFCE7;border-color:#86EFAC;}
.st-key-finder_cards .st-key-finder_pick_0 h3 {color:#166534;}
.st-key-finder_cards [class*="st-key-finder_reasons_"] {min-height:142px;}
.st-key-finder_cards [class*="st-key-finder_note_"] {min-height:62px;}
.st-key-finder_cards [data-testid="stButton"] {margin-top:auto;}
@media(max-width:700px) {
  .st-key-finder_cards [class*="st-key-finder_pick_"] {min-height:0;}
}
</style>""")

with st.container(border=True, gap="small", key="finder_form"):
    st.markdown("**내 상황을 알려주세요**")
    first, second, third = st.columns(3)
    # 홈의 '내 상황으로 찾기'에서 고른 값이 있으면 그 값을 쓰고, 없을 때만 기본값을 준다.
    def preset(key: str, fallback: str) -> str | None:
        return None if key in st.session_state else fallback

    car = first.segmented_control("차가 있나요?", CAR_OPTIONS, default=preset("finder_car", "있어요"),
                                  key="finder_car", required=True, persist_state="session")
    ev = second.segmented_control("전기차인가요?", EV_OPTIONS, default=preset("finder_ev", "아니요"), key="finder_ev",
                                  required=True, persist_state="session", disabled=car == "없어요")
    focus = third.segmented_control("가장 중요하게 보는 것", FOCUS_OPTIONS, default=preset("finder_focus", "균형 있게"),
                                    key="finder_focus", required=True, persist_state="session")

weight = weights(car, ev, focus)
share = {key: round(100 * value / sum(weight.values())) for key, value in weight.items() if value}
st.caption("반영 비율 · " + " · ".join(f"{METRICS[key][1]} {value}%" for key, value in share.items())
           + " — 서울 25구 안에서의 상대 순위로 계산한 참고 점수예요.")

table = score_table(ranking, weight)
# 추천 이유를 숫자 대신 서울 평균과 견준 말로 보여 주기 위한 평균값
READABLE_KEYS = {"parking": "park", "transit": "need", "charging": "charger"}
AVERAGES = {key: float(pd.to_numeric(table[key], errors="coerce").mean()) for key in METRICS}

st.subheader("내 기준 추천 동네", anchor=False)
with st.container(key="finder_cards"):
    cards = st.columns(3)
    for index, column in enumerate(cards):
        row = table.iloc[index]
        with column.container(border=True, gap="small", height="stretch", key=f"finder_pick_{index}"):
            st.caption(f"{index + 1}위")
            st.markdown(f"### {row.district_name}")
            st.metric("내 기준 점수", f"{int(row.score)}점" if pd.notna(row.score) else "자료 없음")
            with st.container(key=f"finder_reasons_{index}"):
                for line in reason_lines(row, weight):
                    st.markdown(f"- {line}")
            with st.container(key=f"finder_note_{index}"):
                note = caution(row, weight)
                if note:
                    st.caption(f"참고: {note}")
                else:
                    st.html('<span aria-hidden="true">&nbsp;</span>')
            st.button("이 동네 자세히 보기", key=f"finder_open_{index}", width="stretch",
                      on_click=open_district, args=(int(row.region_id), "app_pages/home.py"))

if len(table) >= 2:
    top, runner = table.iloc[0], table.iloc[1]

    def compare_top_two() -> None:
        st.session_state.compare_id = int(runner.region_id)
        open_district(int(top.region_id), "app_pages/compare.py")

    st.button(f"{top.district_name}와 {runner.district_name} 나란히 비교하기", key="finder_compare",
              icon=":material/compare_arrows:", type="primary", on_click=compare_top_two)

st.subheader("서울 25구 전체 순위", anchor=False)
st.caption("열 이름을 누르면 원하는 기준으로 다시 정렬할 수 있어요.")
view = pd.DataFrame({
    "순위": range(1, len(table) + 1),
    "구": table.district_name,
    "내 기준 점수": table.score,
    "차 100대당 주차면": (table.parking * 100).round(1),
    "주민 1명당 하루 승객": table.transit.round(2),
    "전기차 1대당 충전기": table.charging.round(2),
    "세대당 차량": pd.to_numeric(table.vehicle_per_household, errors="coerce").round(2),
})
def highlight_top_three(row):
    rank = row["순위"]
    color = "#DCFCE7" if rank == 1 else "#FEF9C3"
    ink = "#166534" if rank == 1 else "#854D0E"
    style = f"background-color:{color};color:{ink};font-weight:bold" if rank <= 3 else ""
    return [style] * len(row)


st.dataframe(
    view.style.apply(highlight_top_three, axis=1), hide_index=True, width="stretch", height=560,
    column_config={
        "내 기준 점수": st.column_config.ProgressColumn("내 기준 점수", min_value=0, max_value=100, format="%d점"),
        "차 100대당 주차면": st.column_config.NumberColumn(format="%.1f면"),
        "주민 1명당 하루 승객": st.column_config.NumberColumn(format="%.2f명"),
        "전기차 1대당 충전기": st.column_config.NumberColumn(format="%.2f기"),
        "세대당 차량": st.column_config.NumberColumn(format="%.2f대"),
    },
)
st.download_button("이 표를 CSV로 받기", view.to_csv(index=False).encode("utf-8-sig"),
                   file_name="chachacha_district_ranking.csv", mime="text/csv",
                   icon=":material/download:", key="finder_download")
st.caption("등록·인구 2026-09, 승객 2026-10-30 하루 자료 기준이에요. 주차는 수록된 주차장만 집계하며 "
           "실시간 빈자리와 아파트 주차장은 포함하지 않아요. 중구·종로구는 출퇴근 유입으로 승객 값이 커질 수 있어요.")
