import math

import altair as alt
import pandas as pd
import streamlit as st

import kakao_map
from db import queries as q
from ui import date_text, district_row, load_frame, load_options, number, word


DAY_TYPES = ("평일", "주말")
WEATHER_HOURS = pd.date_range("2026-10-30", periods=48, freq="h", name="observed_at")
TRAFFIC_VALUES = ("avg_vehicles", "seoul_avg_vehicles")


TRAFFIC_JS = r"""
const instances = new WeakMap();
export default function ({parentElement, data}) {
  const canvas = parentElement.querySelector('.roads-traffic-canvas');
  const status = parentElement.querySelector('.roads-traffic-status');
  if (!canvas || !status) return;
  canvas.setAttribute('aria-label', data.district_name + ' 실시간 교통 상황, 카카오 제공');
  let state = instances.get(parentElement);
  if (state && state.failed) { state.cleanup(); state = null; }
  if (!state) {
    state = {data, map: null, disposed: false, failed: false};
    instances.set(parentElement, state);
    canvas.hidden = false;
    status.hidden = false;
    status.textContent = '지금 교통 지도를 불러오고 있어요.';
    const fail = () => {
      if (state.disposed || state.failed) return;
      state.failed = true;
      clearTimeout(state.timer);
      canvas.hidden = true;
      status.hidden = false;
      status.textContent = '지금 교통 지도를 불러오지 못했어요. 아래 수록 교통량과 날씨 자료를 확인해 주세요.';
    };
    state.cleanup = () => {
      state.disposed = true;
      clearTimeout(state.timer);
      if (state.observer) state.observer.disconnect();
      if (state.map && state.loaded) state.maps.event.removeListener(state.map, 'tilesloaded', state.loaded);
      canvas.replaceChildren();
      instances.delete(parentElement);
    };
    state.timer = setTimeout(fail, 8000);
    window.chachachaKakao(data.javascript_api_key, '').then(kakao => {
      if (state.disposed || state.failed) return;
      const maps = state.maps = kakao.maps;
      state.map = new maps.Map(canvas, {
        center: new maps.LatLng(state.data.latitude, state.data.longitude),
        level: 7, scrollwheel: false, keyboardShortcuts: true,
      });
      state.regionId = state.data.region_id;
      state.loaded = () => {
        if (state.disposed || state.failed) return;
        clearTimeout(state.timer);
        status.hidden = true;
      };
      maps.event.addListener(state.map, 'tilesloaded', state.loaded);
      state.map.addOverlayMapTypeId(maps.MapTypeId.TRAFFIC);
      state.map.addControl(new maps.ZoomControl(), maps.ControlPosition.RIGHT);
      state.observer = new ResizeObserver(() => {
        if (state.disposed || state.failed) return;
        const center = state.map.getCenter();
        state.map.relayout();
        state.map.setCenter(center);
      });
      state.observer.observe(canvas);
    }).catch(fail);
  } else {
    state.data = data;
    if (state.map && state.regionId !== data.region_id) {
      state.map.setCenter(new state.maps.LatLng(data.latitude, data.longitude));
      state.regionId = data.region_id;
    }
  }
  return state.cleanup;
}
"""

_TRAFFIC_MAP = st.components.v2.component(
    "chachacha_traffic_map",
    html='<p class="roads-traffic-status" role="status" aria-live="polite"></p>'
         '<div class="roads-traffic-canvas" role="region" tabindex="0"></div>',
    css="""
    .roads-traffic-canvas {width:100%; height:360px;}
    .roads-traffic-canvas[hidden] {display:none;}
    .roads-traffic-status {font:inherit; line-height:1.6; margin:0 0 .75rem;}
    """,
    js=kakao_map.SDK_LOADER_JS + TRAFFIC_JS, isolate_styles=False,
)


def _live_traffic(region_id: int, district_name: str) -> None:
    with st.container(border=True, gap="small", key="roads_live_traffic"):
        st.subheader(f":orange[**{district_name}**], 지금 교통 상황", anchor=False)
        st.caption("실시간 · 카카오 제공 · 아래 수록 교통량과 기준 시점이 달라요.")
        key = kakao_map.javascript_key()
        if not key:
            st.info("지금 교통 지도를 준비하지 못했어요. 아래 수록 교통량과 날씨 자료를 확인해 주세요.")
            return
        boundary = district_row(load_frame(q.get_region_boundaries), region_id)
        try:
            latitude = float(boundary.get("centroid_latitude"))
            longitude = float(boundary.get("centroid_longitude"))
            valid = (math.isfinite(latitude) and math.isfinite(longitude)
                     and -90 <= latitude <= 90 and -180 <= longitude <= 180)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            st.info("선택한 구의 지도 중심 자료가 없어요. 아래 수록 교통량과 날씨 자료를 확인해 주세요.")
            return
        _TRAFFIC_MAP(
            key="roads_traffic_map", width="stretch", height="content",
            data={"javascript_api_key": key, "region_id": region_id, "district_name": district_name,
                  "latitude": latitude, "longitude": longitude},
        )


def _polish(chart):
    return chart.configure_view(stroke=None).configure_axis(
        labelFont="Noto Sans KR", titleFont="Noto Sans KR", labelFontSize=15, titleFontSize=15,
        labelColor="#4A5270",
        titleColor="#4A5270", gridColor="#EEF0FA", domain=False,
    ).configure_legend(labelFont="Noto Sans KR", labelFontSize=15, titleFontSize=15, labelColor="#1B2340")


def _day_profile(frame: pd.DataFrame, day_type: str) -> pd.DataFrame:
    columns = ["hour_of_day", "day_type", *TRAFFIC_VALUES]
    if frame.empty or not set(columns).issubset(frame.columns):
        selected = pd.DataFrame(columns=pd.Index(columns))
    else:
        selected = frame.loc[frame.day_type == day_type].copy()
    selected = selected.set_index("hour_of_day").reindex(range(24)).reset_index()
    for field in TRAFFIC_VALUES:
        values = pd.to_numeric(selected[field], errors="coerce")
        selected[field] = values.where(values.ge(0) & values.lt(float("inf")))
    selected["day_type"] = day_type
    return selected


def _traffic_chart(frame: pd.DataFrame, district_name: str, ceiling: float) -> alt.Chart:
    series = []
    labels = [district_name, "서울 구 평균"]
    legend = alt.Legend(orient="top", symbolType="stroke", symbolStrokeWidth=3, symbolSize=400)
    for field, label in zip(TRAFFIC_VALUES, labels):
        rows = frame[["hour_of_day", "day_type", field]].rename(columns={field: "vehicles"}).copy()
        rows["series_label"] = label
        # Altair가 null을 걸러도 결측 양옆의 관측값이 이어지지 않게 한다.
        rows["segment"] = rows.vehicles.isna().cumsum()
        series.append(rows)
    chart = alt.Chart(pd.concat(series, ignore_index=True)).mark_line(
        strokeWidth=3, point=alt.OverlayMarkDef(size=25, filled=True), invalid="filter",
    ).encode(
        x=alt.X("hour_of_day:Q", title="시간", scale=alt.Scale(domain=[0, 23]),
                axis=alt.Axis(values=[0, 6, 12, 18, 23], labelExpr="datum.value + '시'")),
        y=alt.Y("vehicles:Q", title="시간당 평균 수록 차량 (대)",
                scale=alt.Scale(domain=[0, ceiling], zero=True),
                axis=alt.Axis(format=",.0f", tickCount=4)),
        color=alt.Color("series_label:N", title=None, sort=labels,
                        scale=alt.Scale(domain=labels, range=["#27336B", "#8E98CF"]),
                        legend=legend),
        strokeDash=alt.StrokeDash("series_label:N", title=None, sort=labels,
                                  scale=alt.Scale(domain=labels, range=[[1, 0], [5, 3]]),
                                  legend=legend),
        detail=alt.Detail("segment:O"),
        tooltip=[alt.Tooltip("series_label:N", title="구분"),
                 alt.Tooltip("day_type:N", title="요일"),
                 alt.Tooltip("hour_of_day:Q", title="시작 시각", format="d"),
                 alt.Tooltip("vehicles:Q", title="시간당 평균 (대)", format=",.1f")],
    ).properties(height=250)
    return _polish(chart)


def _time_text(frame: pd.DataFrame, *, busiest: bool) -> str:
    known = frame.dropna(subset=["avg_vehicles"])
    if known.empty:
        return "자료 없음"
    values = known.avg_vehicles
    value = values.max() if busiest else values.min()
    if values.nunique() == 1:
        scope = "모든 시간" if len(known) == 24 else "수록된 시간"
        return f"{scope} 동일 · 시간당 평균 {number(value, 1, '대')}"
    hours = known.loc[values == value, "hour_of_day"]
    groups = []
    for hour in hours.astype(int):
        if groups and groups[-1][1] == hour:
            groups[-1][1] = hour + 1
        else:
            groups.append([hour, hour + 1])
    times = ", ".join(rf"{start:02d}\~{end:02d}시" for start, end in groups)
    scope = "수록된 시간 중 " if len(known) < 24 else ""
    tied = " (공동)" if len(hours) > 1 else ""
    return f"{scope}**{times}**{tied} · 시간당 평균 {number(value, 1, '대')}"


def _partial_coverage(frame: pd.DataFrame) -> bool:
    fields = {"complete_hour_count", "observed_hour_count"}
    if not fields.issubset(frame.columns):
        return False
    return bool((frame.complete_hour_count < frame.observed_hour_count).any())


def _traffic_period(frame: pd.DataFrame, options: dict) -> str:
    if {"reference_start", "reference_end"}.issubset(frame.columns) and not frame.empty:
        start, end = frame.reference_start.min(), frame.reference_end.max()
    else:
        dates = options.get("traffic_dates", [])
        if not dates:
            return "교통량 기준 기간 자료 없음"
        start, end = min(dates), max(dates)
    return rf"{date_text(start)} \~ {date_text(end)} 수록 자료"


def _weather_sample(observed_at) -> pd.DataFrame:
    times = WEATHER_HOURS.intersection(pd.DatetimeIndex(observed_at))
    frames = [q.get_weather(at.to_pydatetime()) for at in times]
    frames = [frame for frame in frames if not frame.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _weather_series(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["observed_at", "temperature_c", "rain_mm"]
    if frame.empty or not set(columns).issubset(frame.columns):
        frame = pd.DataFrame(columns=pd.Index(columns))
    else:
        frame = frame.copy()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"])
    frame = frame.set_index("observed_at").reindex(WEATHER_HOURS).reset_index()
    for field in ("temperature_c", "rain_mm"):
        values = pd.to_numeric(frame[field], errors="coerce")
        frame[field] = values.where(values.abs().lt(float("inf")))
    frame["rain_mm"] = frame.rain_mm.where(frame.rain_mm.ge(0))
    frame["segment"] = frame.temperature_c.isna().cumsum()
    return frame


def _weather_chart(frame: pd.DataFrame, field: str):
    is_temperature = field == "temperature_c"
    label = "기온 (℃)" if is_temperature else "강수 (mm)"
    # 강수가 모두 0이어도 축이 사라지지 않도록 최솟값을 둔다.
    scale = (alt.Scale(zero=False) if is_temperature else
             alt.Scale(domain=[0, max(1.0, float(frame[field].max()))], zero=True))
    base = alt.Chart(frame).encode(
        x=alt.X("observed_at:T", title="관측 시각 (한국 시각)",
                scale=alt.Scale(domain=[WEATHER_HOURS[0].isoformat(), WEATHER_HOURS[-1].isoformat()]),
                axis=alt.Axis(format="%m.%d %H시", tickCount=4, labelAngle=0)),
        y=alt.Y(f"{field}:Q", title=label, scale=scale,
                axis=alt.Axis(format=".1f", tickCount=3)),
        tooltip=[alt.Tooltip("observed_at:T", title="관측 시각", format="%m.%d %H:%M"),
                 alt.Tooltip(f"{field}:Q", title=label, format=".1f")],
    )
    if is_temperature:
        chart = base.mark_line(
            color="#27336B", strokeWidth=2, point=alt.OverlayMarkDef(size=18, filled=True),
            invalid="filter",
        ).encode(detail=alt.Detail("segment:O"))
    else:
        # 높이가 없는 0mm 관측도 보이도록 점을 겹친다.
        chart = base.mark_bar(color="#8E98CF", size=6) + base.mark_point(
            color="#27336B", filled=True, size=32,
        )
    return _polish(chart.properties(height=150))


region_id = st.session_state.get("district_id")
if region_id is None:
    st.info("위에서 동네를 선택해 주세요.")
    st.stop()
region_id = int(region_id)
options = load_options()
district_name = word(district_row(options.get("regions", pd.DataFrame()), region_id).get("district_name"),
                     "선택한 동네")

_live_traffic(region_id, district_name)

st.subheader(f":orange[**{district_name}**], 언제 차량이 많을까요?", anchor=False)
st.html("""<style>
[class*="st-key-roads_busy_"] {padding:14px 18px;background:#FFF1F2;border:1px solid #FECDD3;border-radius:12px;min-height:126px;}
[class*="st-key-roads_quiet_"] {padding:14px 18px;background:#ECFDF5;border:1px solid #A7F3D0;border-radius:12px;min-height:126px;}
[class*="st-key-roads_busy_"] strong {font-size:26px;font-weight:800;color:#B91C1C;}
[class*="st-key-roads_quiet_"] strong {font-size:26px;font-weight:800;color:#166534;}
</style>""")
profile_query = getattr(q, "get_traffic_profile", None)
profile = load_frame(profile_query, region_id) if callable(profile_query) else pd.DataFrame()
st.caption(f"{_traffic_period(profile, options)} · 평일은 월요일부터 금요일, 주말은 토·일이에요. 공휴일은 따로 나누지 않았어요.")
st.caption("교통량은 수록 지점·방향의 차량 수를 더한 값이에요. 구마다 관측 지점 수가 달라 구끼리 절대 규모를 단순 비교하기 어려워요.")

daily = {day: _day_profile(profile, day) for day in DAY_TYPES}
has_traffic = any(frame.avg_vehicles.notna().any() for frame in daily.values())
if not has_traffic:
    st.info(f"{district_name} 교통량은 자료 없음이에요. 관측 자료가 없는 구는 붐비는 시간이나 출발 시간을 안내하기 어려워요.")
else:
    maximum = pd.concat(daily.values(), ignore_index=True)[list(TRAFFIC_VALUES)].max().max()
    ceiling = float(maximum) * 1.08 if maximum > 0 else 1.0
    with st.grid(2, min_column_width=340, gap="medium"):
        for day, frame in daily.items():
            with st.container(border=True, height="stretch", gap="small", key=f"roads_{day}"):
                st.markdown(f"### {day}")
                if frame.avg_vehicles.notna().any():
                    st.altair_chart(_traffic_chart(frame, district_name, ceiling), width="stretch",
                                    key=f"roads_traffic_{day}",
                                    alt=f"{district_name} {day} 시간대별 평균 수록 차량과 서울 구 평균")
                    if frame.avg_vehicles.isna().any() or frame.seoul_avg_vehicles.isna().any():
                        st.caption("자료가 없는 시간은 선을 잇지 않았어요. 시간 안내는 수록된 시간 안에서만 비교해요.")
                    if not frame.seoul_avg_vehicles.notna().any():
                        st.caption("서울 구 평균은 자료 없음이에요.")
                else:
                    st.info(f"{day} 교통량은 자료 없음이에요.")
                with st.container(key=f"roads_busy_{day}"):
                    st.markdown("가장 붐비는 시간 · 수록량 기준")
                    st.markdown(_time_text(frame, busiest=True))
                with st.container(key=f"roads_quiet_{day}"):
                    st.markdown("차량이 가장 적은 시간 · 수록량 기준")
                    st.markdown(_time_text(frame, busiest=False))
                if _partial_coverage(frame):
                    st.caption("일부 관측 지점이 빠진 때가 있어요. 같은 구에서도 관측 범위가 달라 시간대 차이가 왜곡될 수 있어요.")
    count_text = ""
    if "seoul_region_count" in profile:
        counts = profile.seoul_region_count.dropna()
        if not counts.empty:
            count_text = (f" ({int(counts.iloc[0])}개 구)" if counts.nunique() == 1
                          else rf" (시간대별 {int(counts.min())}\~{int(counts.max())}개 구)")
    st.caption(f"서울 구 평균은 같은 요일 구분·시간대에 자료가 있는 구별 평균의 산술평균이에요{count_text}.")
    with st.container(border=True, gap="small", key="roads_departure"):
        st.markdown("**차를 끌고 나간다면**")
        st.write("차량이 적게 수록된 시간을 출발 시간 선택에 참고해 보세요. 실제 정체·소요 시간이나 운전하기 좋은 조건을 뜻하지는 않아요.")
        if _partial_coverage(profile):
            st.caption("관측 범위가 일정하지 않아 이 자료만으로 출발 시간을 추천하기는 어려워요.")

st.subheader("서울 날씨 표본 (10월 30~31일)", anchor=False)
st.caption(r"9월 교통량과는 기준 기간이 달라요. 2026.10.30\~31의 48시간 표본이에요. 서울 108 관측소의 공통 자료로, 구별 날씨나 현재 날씨·예보가 아니에요.")
weather = _weather_series(load_frame(_weather_sample, options.get("weather_observed_at", [])))
with st.grid(2, min_column_width=340, gap="medium"):
    for field, label in (("temperature_c", "기온"), ("rain_mm", "강수")):
        with st.container(border=True, gap="small", height="stretch", key=f"roads_weather_{field}"):
            st.markdown(f"**{label}**")
            known_count = int(weather[field].notna().sum())
            if known_count:
                st.altair_chart(_weather_chart(weather, field), width="stretch", key=f"roads_{field}",
                                alt=f"서울 공통 2026년 10월 30일부터 31일까지 시간별 {label} 표본")
                st.caption(f"값이 있는 시간 {known_count}/48시간")
            else:
                st.info(f"{label} 표본은 자료 없음이에요.")
            if known_count < 48:
                st.caption("값이 없는 시간은 비워 뒀어요. 강수 결측은 비가 오지 않았다는 뜻이 아니에요."
                           if field == "rain_mm" else "값이 없는 시간은 비워 두고 선을 잇지 않았어요.")
