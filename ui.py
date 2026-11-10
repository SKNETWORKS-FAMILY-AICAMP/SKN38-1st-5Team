from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from content_faq import RANKING_NOTE
from db import queries as q


@dataclass(frozen=True)
class Topic:
    title: str
    unit: str
    order_label: str
    levels: tuple[str, str, str]
    multiplier: float = 1
    digits: int = 2


TOPICS = {
    "ownership": Topic("차량 보유 현황", "세대당 차량", "세대당 차량 많은 순",
                       ("많은 편", "보통", "적은 편")),
    "parking": Topic("주차하기 좋은 동네", "차 100대당 주차면", "차량 대비 수록 주차면 많은 순",
                     ("좋음", "보통", "빠듯함"), multiplier=100, digits=1),
    "need": Topic("차가 꼭 필요한 동네", "주민 1명당 하루 승객", "대중교통 이용 많은 순",
                  ("차가 필요한 편", "있으면 편함", "대중교통으로 충분")),
}
# 충전은 세 판정에 들지 않아 지도 기준이 아닌 순위 항목으로만 쓴다.
RANKED_TOPICS = {**TOPICS, "charging": Topic("충전 여건", "전기차 1대당 충전기", "전기차 대비 수록 충전기 많은 순",
                                             ("많은 편", "보통", "적은 편"))}
COLORS = ["#27336B", "#8E98CF", "#EEF0FA", "#E4E7E6"]
MISSING = "자료 없음"
MAP_PANEL_HEIGHT = 672
RANK_HEIGHT = 550
RANK_BAR_LEFT = 96


def load_options() -> dict:
    try:
        return q.get_filter_options()
    except Exception:
        # 연결 예외 원문에는 접속 정보가 포함될 수 있으므로 화면에 내보내지 않는다.
        st.error("조회 조건을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.")
        return {}


def load_frame(fetch: Callable[..., pd.DataFrame], *args: Any, **kwargs: Any) -> pd.DataFrame:
    try:
        frame = fetch(*args, **kwargs)
        # 표시 계산의 오버플로를 막도록 작은 정수형만 확장한다.
        small_integers = frame.select_dtypes(
            include=["int8", "int16", "int32", "uint8", "uint16", "uint32"]
        ).columns
        casts = {column: "Int64" if frame[column].isna().any() else "int64"
                 for column in small_integers}
        return frame.astype(casts) if casts else frame
    except Exception:
        st.error("자료를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.")
        return pd.DataFrame()


def word(value: Any, fallback: str = MISSING) -> str:
    return fallback if value is None or pd.isna(value) else str(value)


def number(value: Any, digits: int = 0, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return MISSING
    return f"{float(value):,.{digits}f}{suffix}"


def date_text(value: Any, month: bool = False) -> str:
    if value is None or pd.isna(value):
        return MISSING
    timestamp = pd.Timestamp(value)
    return timestamp.strftime("%Y.%m" if month else "%Y.%m.%d") if isinstance(timestamp, pd.Timestamp) else MISSING


def district_row(frame: pd.DataFrame, region_id: int) -> pd.Series:
    if frame.empty or "region_id" not in frame:
        return pd.Series(dtype=object)
    match = frame.loc[frame.region_id == region_id]
    return match.iloc[0] if not match.empty else pd.Series(dtype=object)


def topic_value(row: pd.Series, topic: str, brief: bool = False) -> str:
    spec = RANKED_TOPICS[topic]
    raw = row.get(f"{topic}_value")
    if raw is None or pd.isna(raw):
        return MISSING
    scaled = float(raw) * spec.multiplier
    digits = 2 if topic == "parking" and 0 < scaled < 0.1 else spec.digits
    value = number(scaled, digits)
    unit = {"ownership": "대", "parking": "면", "need": "명", "charging": "기"}[topic]
    return f"{value}{unit}" if brief else f"{spec.unit} {value}{unit}"


def rank_text(row: pd.Series, topic: str) -> str:
    rank = row.get(f"{topic}_rank")
    if rank is None or pd.isna(rank):
        return "순위 자료 없음"
    return f"{TOPICS[topic].order_label} · 서울 25구 중 {int(rank)}위"


def set_topic(topic: str) -> None:
    st.session_state.topic = topic


def remember_region() -> None:
    st.session_state.selected_region_id = int(st.session_state.district_id)
    # 다른 위젯에서 구를 바꾼 뒤에도 같은 지도 영역을 다시 누를 수 있게 선택을 초기화한다.
    st.session_state.map_epoch = st.session_state.get("map_epoch", 0) + 1
    clear_rank_selection()


def clear_rank_selection() -> None:
    # 다른 경로로 구를 바꾼 뒤에도 같은 순위 행을 다시 선택할 수 있게 한다.
    st.session_state.rank_epoch = st.session_state.get("rank_epoch", 0) + 1


def select_rank_region(key: str) -> None:
    event = st.session_state.get(key, {})
    chosen = event.get("selection", {}).get("rank", [])
    if chosen and chosen[0].get("region_id") is not None:
        st.session_state.district_id = int(chosen[0]["region_id"])
        remember_region()


def judgment_tabs(row: pd.Series) -> None:
    icons = {"ownership": ":material/directions_car:", "parking": ":material/local_parking:",
             "need": ":material/directions_bus:"}
    pages = {"ownership": ("ownership", "차량 보유 자세히"),
             "parking": ("parking", "주차장 찾기"),
             "need": ("transit", "대중교통 살펴보기")}
    with st.container(gap=0, key="judgment_deck"):
        for column, (topic, spec) in zip(st.columns(3, gap="medium"), TOPICS.items()):
            with column.container(border=False, height="stretch", gap=4, key=f"judgment_{topic}"):
                active = st.session_state.topic == topic
                with st.container(key=f"tab_{'active' if active else 'idle'}_{topic}"):
                    st.button(spec.title, key=f"tab_{topic}", width="stretch", icon=icons[topic],
                              type="primary" if active else "tertiary", on_click=set_topic, args=(topic,),
                              help="누르면 우리 동네 지도의 색이 이 기준으로 바뀌어요.")
                st.metric(label=spec.unit, value=topic_value(row, topic, brief=True), width="stretch")
                st.caption(rank_text(row, topic))
                page, label = pages[topic]
                st.page_link(f"app_pages/{page}.py", label=label, icon=":material/arrow_forward:")


def neighborhood_sentence(row: pd.Series) -> str:
    ownership = {
        "많은 편": "차량 보유가 많은 편이고", "보통": "차량 보유는 보통이고",
        "적은 편": "차량 보유가 적은 편이고",
    }.get(word(row.get("ownership_level")), "차량 보유 자료는 없고")
    parking = {
        "좋음": "수록 주차면은 차량 대비 여유 있는 편이에요.",
        "보통": "수록 주차면은 차량 대비 보통이에요.",
        "빠듯함": "수록 주차면은 차량 대비 빠듯해요.",
    }.get(word(row.get("parking_level")), "주차 여건 자료는 없어요.")
    need = word(row.get("need_level"))
    usage = {
        "대중교통으로 충분": "주민 대비 대중교통 이용 지표는 높은 편이에요.",
        "있으면 편함": "주민 대비 대중교통 이용 지표는 보통이에요.",
        "차가 필요한 편": "주민 대비 대중교통 이용 지표는 낮은 편이에요.",
    }.get(need, "대중교통 이용 지표 자료는 없어요.")
    # The DB's need labels describe passenger usage, not personal purchase need
    # or route availability. Parking advice therefore depends on both indicators.
    advice = {
        ("좋음", "대중교통으로 충분"): "대중교통을 먼저 살펴보고, 운전할 때는 목적지 주차 조건을 확인해 보세요.",
        ("보통", "대중교통으로 충분"): "대중교통을 먼저 살펴보고, 운전할 때는 목적지 주차 가능 여부를 확인해 보세요.",
        ("빠듯함", "대중교통으로 충분"): "주차가 빠듯하니 대중교통 경로를 먼저 살펴보고, 운전한다면 주차 공간을 미리 확인해 보세요.",
        ("좋음", "있으면 편함"): "이동 경로에 맞춰 교통수단을 비교하고, 운전할 때는 목적지 주차 조건을 확인해 보세요.",
        ("보통", "있으면 편함"): "대중교통 경로와 목적지 주차 가능 여부를 함께 확인해 보세요.",
        ("빠듯함", "있으면 편함"): "운전 전 주차 공간을 미리 확인하고 대중교통 경로도 함께 비교해 보세요.",
        ("좋음", "차가 필요한 편"): "실제 대중교통 경로와 목적지 주차 조건을 확인해 보세요.",
        ("보통", "차가 필요한 편"): "실제 이동 경로와 주차 가능 여부를 함께 확인해 보세요.",
        ("빠듯함", "차가 필요한 편"): "주차 공간부터 확인하고 실제 대중교통 경로도 비교해 보세요.",
    }.get((word(row.get("parking_level")), need),
          "실제 이동 경로와 목적지 주차 조건을 확인해 보세요.")
    return f"{ownership} {parking} {usage} {advice}"


def mobility_mood(row: pd.Series) -> str:
    """Illustrate mobility context; ownership prevalence is not a benefit/penalty.

    High transit usage is a positive proxy, never an inverted need score.
    Missing indicators stay neutral rather than implying a poor neighborhood.
    """
    if any(word(row.get(f"{topic}_level")) not in TOPICS[topic].levels for topic in TOPICS):
        return "smile"
    parking, need = word(row.get("parking_level")), word(row.get("need_level"))
    if need == "대중교통으로 충분":
        return "smile" if parking == "빠듯함" else "happy"
    if parking == "빠듯함":
        return "crying"
    return "happy" if parking == "좋음" and need == "있으면 편함" else "smile"


def neighborhood_summary(row: pd.Series) -> None:
    with st.container(border=True, gap=4, key="neighborhood_summary"):
        st.caption("한눈에 읽는 우리 동네")
        name = word(row.get("district_name"))
        st.header(f"{name}는요" if name != MISSING else name, anchor=False)
        st.markdown(neighborhood_sentence(row))
        short_names = {"ownership": "차량 보유", "parking": "주차 여건", "need": "차 필요성"}
        with st.container(horizontal=True, gap="xsmall", key="summary_signals"):
            for topic, spec in TOPICS.items():
                current = word(row.get(f"{topic}_level"))
                level_index = spec.levels.index(current) if current in spec.levels else 3
                with st.container(width="content", key=f"summary_level_{level_index}_{topic}"):
                    st.markdown(short_names[topic])


def incomplete_transit(row: pd.Series) -> bool:
    complete = row.get("transit_complete_hour_count")
    observed = row.get("transit_observed_hour_count")
    return (complete is not None and observed is not None
            and pd.notna(complete) and pd.notna(observed) and complete < observed)


def top_three(frame: pd.DataFrame, value: str, key: str) -> pd.DataFrame:
    """Show three largest observations, preserving the full result on demand."""
    full = st.toggle("상세보기 · 전체 자료", key=f"{key}_show_all")
    ordered = frame.reindex(columns=[*frame.columns, *([] if value in frame else [value])]).sort_values(value, ascending=False, kind="stable", na_position="last")
    if not full:
        st.caption("상위 3개 · 가장 큰 값은 주황색으로 표시해요.")
    return ordered if full else ordered.head(3)


def ranking_chart(ranking: pd.DataFrame, topic: str, selected: int) -> alt.LayerChart:
    ordered = ranking.copy()
    rank_col, value_col = f"{topic}_rank", f"{topic}_value"
    for column in (rank_col, value_col):
        if column not in ordered:
            ordered[column] = pd.NA
    ordered = ordered.sort_values([rank_col, "district_name"], na_position="last")
    def tier(row):
        rank = row[rank_col]
        if pd.isna(rank):
            return 'unknown'
        if rank == 1:
            return 'first'
        if rank <= 3:
            return 'podium'
        level = word(row.get(f"{topic}_level"))
        if level in {'많은 편', '빠듯함', '차가 필요한 편', '적은 편' if topic == 'charging' else ''} or rank == ordered[rank_col].max():
            return 'caution'
        return 'neutral'
    records = [{
        "region_id": int(row.region_id),
        "rank_label": number(row[rank_col]) if pd.notna(row[rank_col]) else "-",
        "name": str(row.district_name),
        "label": topic_value(row, topic, brief=True),
        "value": float(row[value_col]) if pd.notna(row[value_col]) else 0.0,
        "level": word(row.get(f"{topic}_level")),
        "selected": int(row.region_id) == selected,
        "tier": tier(row),
        "highest": pd.notna(row[value_col]) and row[value_col] == ordered[value_col].max(),
    } for _, row in ordered.iterrows()]
    top = max((record["value"] for record in records), default=0) or 1
    base = alt.Chart(alt.InlineData(values=records)).encode(y=alt.Y("name:N", sort=None, axis=None))
    x = alt.X("value:Q", axis=None,
              scale=alt.Scale(domain=[0, top], range=[RANK_BAR_LEFT, alt.expr("width - 62")]))
    tiers = ['first', 'podium', 'caution', 'neutral', 'unknown']
    inks = ['#166534', '#854D0E', '#B91C1C', '#1B2340', '#64748B']
    row_area = base.mark_rect(x=0, x2="width", cornerRadius=6, cursor="pointer").encode(
        color=alt.Color('tier:N', legend=None, scale=alt.Scale(domain=tiers,
            range=['#DCFCE7', '#FEF9C3', '#FEE2E2', '#F8FAFC', '#F1F5F9'])))
    highlight = base.transform_filter("datum.selected").mark_rect(
        x=0, x2="width", fillOpacity=0, stroke="#27336B", strokeWidth=1.5, cornerRadius=6)
    bars = base.mark_bar(height=11, cornerRadiusEnd=5, stroke="#C8CDE3", strokeWidth=0.6, cursor="pointer").encode(
        x=x, x2=alt.datum(0),
        color=alt.Color('tier:N', legend=None, scale=alt.Scale(domain=tiers, range=['#15803D', '#CA8A04', '#DC2626', '#8E98CF', '#94A3B8'])))
    weight = alt.expr("datum.selected || datum.highest ? 800 : 500")
    label_color = alt.Color("tier:N", legend=None, scale=alt.Scale(domain=tiers, range=inks))
    ranks = base.mark_text(align="right", x=20, fontSize=15, cursor="pointer").encode(
        text="rank_label:N",
        color=label_color)
    names = base.mark_text(align="left", x=26, fontSize=15, fontWeight=weight,
                           cursor="pointer").encode(text="name:N", color=label_color)
    values = base.mark_text(align="left", dx=4, fontSize=15, fontWeight=weight,
                            cursor="pointer").encode(x=x, text="label:N", color=label_color)
    selection = alt.selection_point(name="rank", fields=["region_id"], toggle=False, clear=False)
    return (alt.layer(row_area, highlight, bars, ranks, names, values).add_params(selection).resolve_scale(color="independent")
            .properties(height=max(120, len(records) * 30)).configure_view(stroke=None))


def ranking_list(ranking: pd.DataFrame, topic: str) -> None:
    spec = RANKED_TOPICS[topic]
    st.caption(spec.order_label)
    key = f"ranking_{topic}_{st.session_state.get('rank_epoch', 0)}"
    rank_col = f"{topic}_rank"
    shown = ranking
    if (not st.toggle("전체 25구 보기", key=f"ranking_{topic}_show_all")
            and rank_col in ranking and ranking[rank_col].notna().any()):
        rank = ranking[rank_col]
        shown = ranking.loc[rank.le(5) | rank.eq(rank.max())]
    st.altair_chart(ranking_chart(shown, topic, st.session_state.district_id), key=key,
                    on_select=partial(select_rank_region, key), selection_mode="rank",
                    width="stretch", height=max(120, len(shown) * 30),
                    alt=f"서울 25구 {spec.order_label} 막대 순위. 행을 누르면 해당 구를 선택해요.")


def display_table(frame: pd.DataFrame, columns: dict[str, str], alt_text: str,
                  *, column_config: dict[str, Any] | None = None) -> None:
    if frame.empty:
        st.info("조건에 맞는 자료가 없어요.")
        return
    data = frame.reindex(columns=list(columns)).rename(columns=columns).copy()
    for column in data.columns:
        data[column] = data[column].astype(object).where(pd.notna(data[column]), MISSING)
    st.dataframe(data, hide_index=True, column_config=column_config, alt=alt_text)


def source_notes(row: pd.Series) -> None:
    st.markdown("**세 판정의 기준**")
    st.write(RANKING_NOTE)
    st.write("차량 보유는 세대당 등록 대수, 주차는 차량 대비 수록 주차면이에요. 아파트 주차장은 빠져 있고 실제 빈자리를 뜻하지 않아요.")
    st.write(f"차 필요성은 {date_text(row.get('need_stat_date'))} 하루 수록 승객 수를 주민 수로 나눈 추정이에요. 실제 차량 구매 필요를 확정하지 않아요.")
    st.write("필요성 순위는 대중교통 이용 많은 순이에요. 1위가 차를 가장 필요로 한다는 뜻은 아니에요.")
    snapshots = load_options().get("snapshots", pd.DataFrame())
    if not snapshots.empty:
        recent = snapshots.drop_duplicates("source_code")
        source_names = {"molit_registration": "자동차 등록", "resident_population": "주민·세대",
                        "parking_standard": "수록 주차장", "keco_ev_charger": "환경공단 충전기",
                        "seoul_passenger": "대중교통 승객", "kostat_seoul_boundary": "서울 구 경계"}
        for _, snapshot in recent.iterrows():
            if snapshot.source_code in source_names:
                st.caption(f"{source_names[snapshot.source_code]} · 자료 기준 {date_text(snapshot.reference_start)} ~ {date_text(snapshot.reference_end)} · 수집 {date_text(snapshot.collected_on)}")
