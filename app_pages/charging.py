import json

import altair as alt
import pandas as pd
import streamlit as st

import readable

from db import queries as q
from ui import date_text, display_table, district_row, load_frame, load_options, number, word


SPEED_LABELS = {"all": "전체", "fast": "급속", "slow": "완속", "unknown": "속도 자료 없음"}
_GAUGE = st.components.v2.component(
    "chachacha_charging_gauge",
    isolate_styles=True,
    html="""
    <section class="scene">
      <div class="copy"><p class="eyebrow">우리 동네 충전 여건</p>
        <h3 class="title"><span class="district-name"></span><span class="title-copy"></span></h3><p class="detail"></p></div>
      <div class="battery" role="img"><div class="fill"></div>
        <div class="divider first"></div><div class="divider second"></div>
        <svg class="bolt" viewBox="0 0 24 32" aria-hidden="true">
          <path d="M14 1 2 18h9l-1 13 12-19h-9Z" fill="#FF7A66"/>
        </svg>
      </div>
    </section>
    """,
    css="""
    .scene { box-sizing: border-box; display: flex; align-items: center;
      justify-content: space-between; gap: 24px; padding: 24px 30px;
      border: 1px solid #C8CDE3; border-radius: var(--st-base-radius, 16px);
      background: #EEF0FA; color: #1B2340; font-family: var(--st-font, sans-serif); }
    .copy { min-width: 0; }
    .eyebrow { color: #4A5270; font-size: 16px; margin: 0 0 8px; }
    .title { font-family: var(--st-heading-font, inherit); font-size: 27px;
      font-weight: 400; line-height: 1.3; margin: 0 0 8px; overflow-wrap: anywhere; }
    .district-name { display:block; font-size:clamp(36px,5vw,52px); font-weight:800;
      color:#B45309; margin-bottom:6px; }
    .detail { color: #4A5270; margin: 0; font-size: 16px; line-height: 1.6; }
    .battery { width: 152px; height: 66px; flex: 0 0 auto; position: relative;
      border: 4px solid var(--status-color, #64748B); border-radius: 13px; background: #E5E7EB; }
    .battery::after { content: ''; position: absolute; right: -13px; top: 20px;
      height: 25px; width: 8px; border-radius: 0 4px 4px 0; background: var(--status-color, #64748B); }
    .fill { position: absolute; inset: 5px; border-radius: 5px; background: var(--status-color, #64748B);
      transform: scaleX(0); transform-origin: left center; }
    .divider { position: absolute; top: 4px; bottom: 4px; width: 4px; background: white; }
    .first { left: 33.33%; } .second { left: 66.66%; }
    .bolt { position: absolute; width: 24px; height: 32px; left: 64px; top: 17px; }
    @media (max-width: 480px) {
      .scene { padding: 20px; gap: 22px; flex-direction: column; align-items: flex-start; }
      .title { font-size: 24px; } .battery { margin-bottom: 4px; }
    }
    """,
    js="""
    export default function ({ data, parentElement }) {
      const scene = parentElement.querySelector('.scene');
      const fill = parentElement.querySelector('.fill');
      const battery = parentElement.querySelector('.battery');
      parentElement.querySelector('.district-name').textContent = data.district_name;
      parentElement.querySelector('.title-copy').textContent = data.title_copy;
      parentElement.querySelector('.detail').textContent = data.detail;
      battery.setAttribute('aria-label', data.accessibleLabel);
      const level = Math.max(0, Math.min(3, Number(data.level) || 0));
      const target = level / 3;
      battery.style.setProperty('--status-color', data.color);
      battery.dataset.level = String(level);
      fill.getAnimations().forEach(animation => animation.cancel());
      fill.style.transform = `scaleX(${target})`;
      if (data.animate && !scene.dataset.opened &&
          !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        fill.animate([{ transform: 'scaleX(0)' }, { transform: `scaleX(${target})` }],
          { duration: 1100, easing: 'cubic-bezier(.2,.7,.2,1)' });
      }
      scene.dataset.opened = 'true';
      return () => fill.getAnimations().forEach(animation => animation.cancel());
    }
    """,
)


def _level(row: pd.Series) -> tuple[str, int]:
    ratio, rank = row.get("charger_per_electric_vehicle"), row.get("charger_per_electric_vehicle_rank")
    if any(value is None or pd.isna(value) for value in (ratio, rank)):
        return "자료 없음", 0
    if float(ratio) < 0 or not 1 <= int(rank) <= 25:
        return "자료 없음", 0
    if rank <= 8:
        return "많은 편", 3
    if rank <= 17:
        return "보통", 2
    return "적은 편", 1


def _category(frame: pd.DataFrame, kind: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    return frame.loc[frame.breakdown_type.eq(kind)].copy()


def _category_count(frame: pd.DataFrame, kind: str, code: str):
    rows = _category(frame, kind)
    if rows.empty:
        return None
    chosen = rows.loc[rows.category_code.eq(code)]
    # 분류 자료가 있을 때만 빠진 범주를 0으로 본다.
    return int(chosen.iloc[0].charger_count) if not chosen.empty else 0


def _bar_chart_height(item_count: int) -> int:
    # fit 높이에는 축과 제목도 포함되므로 여백을 더한다.
    return max(170, 32 * item_count + 100)


def _bars(frame: pd.DataFrame, key: str, label: str, *, height: int | None = None) -> None:
    if frame.empty:
        st.info("구성을 보여 줄 자료가 없어요.")
        return
    frame = frame.copy()
    maximum = frame.charger_count.max()
    frame["is_highest"] = frame.charger_count.eq(maximum) & frame.charger_count.gt(0)
    leaders = frame.loc[frame.is_highest, "category_label"].astype(str).tolist()
    is_leader = f"indexof({json.dumps(leaders, ensure_ascii=False)}, datum.value) >= 0"
    chart = alt.Chart(frame).mark_bar(cornerRadiusEnd=4, size=19).encode(
        y=alt.Y("category_label:N", title=None, sort=None,
                axis=alt.Axis(labelLimit=180, labelOverlap=False,
                              labelFontWeight=alt.ExprRef(expr=f"{is_leader} ? 800 : 400"),
                              labelColor=alt.ExprRef(expr=f"{is_leader} ? '#B45309' : '#4A5270'"),
                              labelExpr=f"{is_leader} ? datum.label + ' ★' : datum.label")),
        color=alt.condition(alt.datum.is_highest, alt.value("#FF7A66"), alt.value("#8E98CF")),
        x=alt.X("charger_count:Q", title="수록 충전기 (기)",
                axis=alt.Axis(format=",d", tickCount=4), scale=alt.Scale(zero=True)),
        tooltip=[alt.Tooltip("category_label:N", title=label),
                 alt.Tooltip("charger_count:Q", title="충전기 수", format=",d")],
    ).properties(height=height or _bar_chart_height(len(frame))).configure_view(stroke=None).configure_axis(
        labelFont="Noto Sans KR", titleFont="Noto Sans KR", labelFontSize=15, titleFontSize=15,
        labelColor="#1B2340", titleColor="#4A5270", gridColor="#EEF0FA",
    )
    st.altair_chart(chart, key=key, width="stretch", alt=f"선택한 구의 {label}별 수록 충전기 수")


def _source_caption(options: dict) -> None:
    snapshots = options.get("snapshots", pd.DataFrame())
    source = snapshots.loc[snapshots.source_code.eq(q.DEFAULT_CHARGER_SOURCE)] if not snapshots.empty else snapshots
    if source.empty:
        st.caption("환경공단 충전기 · 자료 기준과 수집일 자료 없음")
        return
    latest = source.iloc[0]
    first, last = date_text(latest.reference_start), date_text(latest.reference_end)
    if "자료 없음" in (first, last):
        reference = "기준일 미제공"
    else:
        reference = f"자료 기준일 {first}" if first == last else f"자료 기준 {first} ~ {last}"
    st.caption(
        f"환경공단 충전기 · {reference} · 수집 {date_text(latest.collected_on)}"
    )


selected = st.session_state.get("district_id")
if selected is None:
    st.info("위 메뉴에서 동네를 선택해 주세요.")
    st.stop()
region_id = int(selected)
row = district_row(load_frame(q.get_summary_metrics, region_id), region_id)
options = load_options()
region = district_row(options.get("regions", pd.DataFrame()), region_id)
district = word(region.get("district_name", row.get("district_name")), "선택한 동네")
level, gauge_level = _level(row)
rank = row.get("charger_per_electric_vehicle_rank")
rank_label = f"서울 25구 중 {int(rank)}위" if gauge_level else "순위 자료 없음"
ratio = row.get("charger_per_electric_vehicle")
ratio_label = f"전기차 한 대당 {number(ratio, 2, '기')}" if pd.notna(ratio) else "전기차 대비 충전기 자료 없음"
animate = bool(gauge_level and not st.session_state.get("charging_gauge_opened", False))
_GAUGE(
    data={"title": f"{district}, 충전기는 {level}" if gauge_level else f"{district}, 충전 여건 자료 없음",
          "district_name": district,
          "title_copy": f"충전기는 {level}" if gauge_level else "충전 여건 자료 없음",
          "color": ("#64748B", "#DC2626", "#EAB308", "#15803D")[gauge_level],
          "detail": f"{ratio_label} · {rank_label}", "level": gauge_level, "animate": animate,
          "accessibleLabel": f"수록 충전기 여건 {level}. {gauge_level}칸. {rank_label}. 실제 배터리 충전량이나 주차 여건이 아닌 충전기 비율의 상대적 판정이에요."},
    key="charging_gauge", width="stretch", height="content",
)
if gauge_level:
    st.session_state.charging_gauge_opened = True
st.caption("게이지는 전기차 대비 충전기 비율의 서울 25구 순위예요. 1–8위는 초록 3칸(많은 편), 9–17위는 노랑 2칸(보통), 18–25위는 빨강 1칸(적은 편), 자료 없음은 회색 0칸이에요. 실제 배터리 충전량이나 주차 여건을 뜻하지 않아요.")
with st.container(key="charging_warning"):
    st.warning("실시간 빈자리 정보가 아니에요. 수집 당시 등록된 충전기이며, 이용 제한과 운영시간을 방문 전에 확인해 주세요.", icon=":material/info:")
st.html("""<style>
.st-key-site_root .st-key-charging_warning [data-testid="stAlertContainer"],
.st-key-charging_warning [data-testid="stAlert"] {background:#FEE2E2;color:#991B1B;border:1px solid #FCA5A5;}
.st-key-charging_warning [data-testid="stAlert"] p {color:#991B1B;}
.st-key-charging_metrics [data-testid="stMetric"], .st-key-charging_speed_metrics [data-testid="stMetric"] {min-height:130px;box-sizing:border-box;}
.st-key-charging_reference {min-height:130px;}
.st-key-charging_breakdown [data-testid="stHeading"] {min-height:72px;}
</style>""")

_ranking = load_frame(q.get_district_ranking)
readable.cards(district_row(_ranking, region_id), _ranking, ("charger", "ev"), title="서울 평균과 견주면")
with st.grid(3, min_column_width=185, gap="small", key="charging_metrics"):
    st.metric("전기차 한 대당 충전기", number(ratio, 2, "기"), border=True)
    st.metric("서울 순위 · 충전기 비율", f"{int(rank)}위 / 25구" if gauge_level else "자료 없음", border=True)
    st.metric("수록 충전소", number(row.get("listed_station_count"), suffix="곳"), border=True)
with st.container(key="charging_reference"):
    st.caption(
        f"전기차 {number(row.get('electric_count'), suffix='대')} · 수록 충전기 {number(row.get('listed_count'), suffix='기')} "
        f"· 차량 등록 기준 {date_text(row.get('stat_month'), month=True)} · "
        f"서울 구별 비율 평균 {number(row.get('charger_per_electric_vehicle_seoul_avg'), 2, '기/대')}"
    )
    st.caption("서울 평균은 자료가 있는 구별 비율의 산술평균이에요. 같은 장소도 운영기관이 다르면 별도 충전소로 세어요.")
    _source_caption(options)

st.subheader("급속과 완속, 얼마나 있을까요?", anchor=False)
with st.grid(3, min_column_width=160, gap="small", key="charging_speed_metrics"):
    for field, label in (("fast_count", "급속"), ("slow_count", "완속"), ("unknown_count", "속도 자료 없음")):
        st.metric(label, number(row.get(field), suffix="기"), border=True)

breakdown = load_frame(q.get_charger_breakdown, region_id)
operators = _category(breakdown, "operator")
top = operators.loc[operators.category_code.ne("__other__")] if not operators.empty else operators
connectors = _category(breakdown, "connector")
breakdown_height = _bar_chart_height(max(len(top), len(connectors)))
with st.grid(2, min_column_width=350, gap="medium", key="charging_breakdown"):
    with st.container(border=True, height="stretch", key="charging_operator_card"):
        st.subheader("충전기가 많은 운영기관", anchor=False)
        _bars(top, "charging_operators", "운영기관", height=breakdown_height)
        st.caption(f"충전기 수 상위 10곳이에요. 그 외 운영기관 {number(_category_count(breakdown, 'operator', '__other__'), suffix='기')}")
    with st.container(border=True, height="stretch", key="charging_connector_card"):
        st.subheader("내 차에 맞는 커넥터", anchor=False)
        _bars(connectors, "charging_connectors", "커넥터", height=breakdown_height)
        st.caption("여러 커넥터가 달린 기기도 한 대로 세어요. 이름이 없는 코드는 자료 없음으로 남겨 두었어요.")

st.subheader("무료 주차와 이용 조건", anchor=False)
with st.grid(2, min_column_width=290, gap="medium"):
    with st.container(border=True, height="stretch"):
        st.metric("무료 주차로 수록된 충전기", number(_category_count(breakdown, "parking", "Y"), suffix="기"))
        display_table(_category(breakdown, "parking"),
                      {"category_label": "주차 요금 구분", "charger_count": "충전기 수"},
                      "무료·유료·자료 없음으로 구분한 충전기 수",
                      column_config={"충전기 수": st.column_config.NumberColumn(format="%,d")})
    with st.container(border=True, height="stretch"):
        st.metric("이용 제한이 있는 충전기", number(_category_count(breakdown, "restriction", "Y"), suffix="기"))
        display_table(_category(breakdown, "restriction"),
                      {"category_label": "이용 제한 구분", "charger_count": "충전기 수"},
                      "이용 제한 여부별 충전기 수",
                      column_config={"충전기 수": st.column_config.NumberColumn(format="%,d")})
st.caption("무료 주차는 충전 요금 무료를 뜻하지 않아요. 무료 주차여도 입주민 전용 등 이용 제한이 있을 수 있어요. 자료 없음은 무료나 자유 이용을 뜻하지 않아요.")

st.subheader(f"{district} 충전소 이용 정보", anchor=False)
st.page_link("app_pages/parking.py", label="주차·충전 위치 지도에서 찾기", icon=":material/map:")
with st.container(horizontal=True, vertical_alignment="bottom"):
    speed = st.segmented_control("충전 속도", list(SPEED_LABELS), default="all", required=True,
                                 format_func=lambda value: SPEED_LABELS[value], key="charging_speed") or "all"
    keyword = st.text_input("충전소 이름·주소 검색", key="charging_keyword", max_chars=500,
                            placeholder="충전소 이름이나 도로명을 입력해 주세요").strip()
    free_only = st.toggle("무료 주차로 수록된 기기만", key="charging_free_only")

devices = load_frame(q.get_charger_detail, region_id, speed=speed, limit=None)
points = load_frame(q.get_place_points, region_id, kinds=("charger",), speed=speed, limit=None)
expected_devices = row.get("listed_count" if speed == "all" else f"{speed}_count")
if devices.empty and (pd.isna(expected_devices) or expected_devices > 0):
    st.info("충전소 목록과 지도는 자료 없음이에요. 충전기가 0기라는 뜻은 아니에요.")
    st.stop()
if not devices.empty:
    if keyword:
        mask = devices.station_name.astype("string").str.contains(keyword, case=False, regex=False, na=False)
        mask |= devices.address.astype("string").str.contains(keyword, case=False, regex=False, na=False)
        devices = devices.loc[mask].copy()
    if free_only:
        devices = devices.loc[devices.parking_free.eq("Y")].copy()
stations = devices.drop_duplicates("station_id").copy() if not devices.empty else pd.DataFrame()
station_ids = stations.station_id.tolist() if not stations.empty else []
visible_points = points.loc[points.place_id.isin(station_ids)].copy() if not points.empty else points
st.caption(f"현재 조건의 충전소 {len(stations):,}곳 · 충전기 {len(devices):,}기 · 위치 자료 {len(visible_points):,}곳")
if len(stations) > len(visible_points):
    st.caption(f"좌표가 없거나 표시 범위를 벗어난 충전소 {len(stations) - len(visible_points):,}곳은 목록에서 확인해 주세요.")
st.caption("같은 장소라도 운영기관이 다르면 별도 충전소예요. 위치 지도는 주차·충전 찾기에서 볼 수 있어요.")

if not stations.empty:
    mapped_ids = set(visible_points.place_id) if not visible_points.empty else set()
    stations["map_note"] = stations.station_id.map(lambda value: "지도 표시" if value in mapped_ids else "좌표 없음·범위 밖")
display_table(stations, {"station_name": "충전소", "operator_name": "운영기관", "address": "주소", "map_note": "지도 안내"},
              "선택한 조건의 충전소 목록. 위치 자료가 없는 충전소도 포함해요.")

if not stations.empty:
    labels = {int(item["station_id"]): f"{word(item['station_name'])} · {word(item['operator_name'])} · {word(item['address'])}"
              for _, item in stations.iterrows()}
    chosen = st.selectbox("충전소별 이용 조건", list(labels), format_func=lambda value: labels[value], key="charging_station")
    selected_devices = devices.loc[devices.station_id.eq(chosen)].copy()
    selected_devices["speed_label"] = selected_devices.speed_code.map(SPEED_LABELS).astype(object)
    selected_devices["parking_label"] = selected_devices.parking_free.map({"Y": "무료로 수록", "N": "유료로 수록"})
    selected_devices["restriction_label"] = selected_devices.restriction_code.map({"Y": "이용 제한 있음", "N": "제한 없음으로 수록"})
    selected_devices["connector_label"] = [
        word(item.connector_text, f"이름 자료 없음 ({item.connector_code})" if pd.notna(item.connector_code) else "자료 없음")
        for item in selected_devices.itertuples()
    ]
    display_table(selected_devices,
                  {"source_charger_id": "기기 번호", "speed_label": "충전 속도", "connector_label": "커넥터",
                   "capacity_text": "출력", "operating_time_text": "이용시간", "parking_label": "주차 요금",
                   "restriction_label": "이용 제한", "restriction_note": "제한 안내"},
                  "선택한 충전소의 기기별 커넥터, 출력, 운영시간과 이용 제한")
