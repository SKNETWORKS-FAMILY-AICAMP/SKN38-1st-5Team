"""Parking map details from Seoul's public parking service and local charger records."""
import json
import math
import re
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).parent
SOURCE = "https://parking.seoul.go.kr"


def text(value, fallback="정보 미제공"):
    return fallback if value is None or pd.isna(value) or not str(value).strip() else str(value).strip()


def hours(start, end):
    start, end = text(start, ""), text(end, "")
    if not all(re.fullmatch(r"(?:[01]\d|2[0-3])[0-5]\d|2400", s) for s in (start, end)):
        return "정보 미제공"
    if (start, end) in (("0000", "2400"), ("0000", "2359")):
        return "24시간"
    if start == end:
        return "운영 여부 확인 필요"
    return f"{start[:2]}:{start[2:]}~{end[:2]}:{end[2:]}" + (" (다음 날)" if end < start else "")


def fee(row):
    if row.get("pay_yn") == "N":
        return "무료"
    parts = ["유료" if row.get("pay_yn") == "Y" else "유·무료 정보 미제공"]
    for label, amount, minutes in (("기본", "rates", "time_rate"), ("추가", "add_rates", "add_time_rate")):
        try:
            price, duration = float(row[amount]), float(row[minutes])
            if price >= 0 and duration > 0:
                parts.append(f"{label} {duration:g}분 {price:,.0f}원")
        except (KeyError, TypeError, ValueError):
            pass
    for label, key in (("일 최대", "day_maximum"), ("월 정기권", "fulltime_monthly")):
        try:
            amount = float(row[key])
            # The source uses zero for an unregistered cap, not free parking.
            if amount > 0:
                parts.append(f"{label} {amount:,.0f}원")
        except (KeyError, TypeError, ValueError):
            pass
    if len(parts) == 1:
        parts.append("금액 정보 미제공")
    return " · ".join(parts)


def parking_records(rows):
    result = []
    for row in rows:
        position = next((p for p in row.get("position_list", []) if valid_position(p.get("lat"), p.get("lng"))), None)
        if position is None:
            continue
        kind = row.get("parking_type")
        operation = {"NS": "공영", "NW": "공영", "NP": "민영", "BP": "공영"}.get(kind, "부설·기타")
        holiday = " · ".join(f"{day} { {'Y': '유료', 'N': '무료'}.get(row.get(key), '정보 미제공')}"
                             for day, key in (("토요일", "saturday_pay_yn"), ("공휴일", "holiday_pay_yn")))
        result.append({
            "id": f"seoul-{row.get('parking_code')}-{row.get('infra_type')}",
            "name": text(row.get("parking_name"), "주차장"),
            "address": text(row.get("new_juso") or row.get("address")),
            "latitude": float(position["lat"]), "longitude": float(position["lng"]),
            "operation": operation, "kind": "주차장", "price": fee(row),
            "hours": " / ".join(f"{day} {hours(row.get(a), row.get(b))}" for day, a, b in (
                ("평일", "weekday_begin_time", "weekday_end_time"),
                ("토요일", "weekend_begin_time", "weekend_end_time"),
                ("공휴일", "holiday_begin_time", "holiday_end_time"))),
            "note": holiday + " · " + text(row.get("sh_etc"), "현장 이용 조건 확인"),
            "capacity": text(row.get("capacity")) + "면", "operator": "서울시 주차정보안내시스템",
            "updated": text(row.get("sync_time")),
        })
    return list({r["id"]: r for r in result}.values())


def valid_position(lat, lon):
    try:
        return 37.4 <= float(lat) <= 37.75 and 126.75 <= float(lon) <= 127.2
    except (TypeError, ValueError):
        return False


@st.cache_data(ttl=3600, show_spinner=False)
def seoul_parking(district):
    try:
        response = requests.post(SOURCE + "/search/parking/list.do", data={
            "Gu": district, "Dong": "", "Keyword": "", "index": 1, "Type": 63, "Rule": 0,
        }, timeout=(3, 8))
        response.raise_for_status()
        payload = response.json()
        if payload.get("result_state") != "0000":
            raise ValueError("Parking source unavailable")
        return parking_records(payload["res_value"]["parking_list"])
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def station_search(keyword):
    try:
        response = requests.post(SOURCE + "/search/parking/destination.do",
                                 data={"Keyword": keyword, "index": 1}, timeout=(3, 8))
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            return []
        result = []
        for row in rows:
            name = text(row.get("title"), "")
            # Exclude businesses, exits and bus stops that merely contain a station name.
            if not re.fullmatch(r".+역\s+(?:\d+호선|[가-힣A-Za-z·]+선|공항철도|서해선|신림선)", name):
                continue
            if valid_position(row.get("latitude"), row.get("longitude")):
                result.append({"name": name, "latitude": float(row["latitude"]), "longitude": float(row["longitude"])})
        return result
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return []


def distance_m(a, b):
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    delta_lat = lat2 - lat1
    delta_lon = math.radians(b["longitude"] - a["longitude"])
    h = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, h)))


def charger_records(points, details):
    result = []
    for _, point in points.iterrows():
        devices = details.loc[details.station_id.eq(point.place_id)] if not details.empty else pd.DataFrame()
        def values(column):
            if column not in devices:
                return "정보 미제공"
            return " / ".join(dict.fromkeys(text(v) for v in devices[column]))
        parking = values("parking_free")
        parking = {"Y": "주차 무료", "N": "주차 유료 · 금액 정보 미제공"}.get(parking, "주차 유·무료 확인 필요")
        result.append({
            "id": f"charger-{point.place_id}", "name": text(point.place_name, "충전소"),
            "address": text(point.address), "latitude": float(point.latitude), "longitude": float(point.longitude),
            "kind": "충전소", "operation": "충전소", "price": parking + " / 충전요금: 금액 정보 미제공 (운영사·회원·출력별 확인)",
            "hours": values("operating_time_text"), "note": "이용제한: " + values("restriction_note"),
            "capacity": f"충전기 {int(point.charger_count)}기", "operator": text(point.operator_name),
            "updated": "환경공단 수집 자료 · 실시간 상태 아님",
        })
    return result


def fallback_parking(points):
    return [{"id": f"db-{r.place_id}", "name": text(r.place_name, text(r.display_name)),
             "address": text(r.address), "latitude": float(r.latitude), "longitude": float(r.longitude),
             "kind": "주차장", "operation": text(r.parking_operation), "price": "요금 정보 미제공",
             "hours": "운영시간 정보 미제공", "note": "방문 전 운영기관에 확인해 주세요.",
             "capacity": text(r.space_count) + "면", "operator": "수록 주차장 자료", "updated": "수집 자료"}
            for _, r in points.iterrows()]


def map_html(records, station=None, radius=500, animate=True):
    payload = {"places": records, "station": station, "radius": radius, "animate": animate}
    # Escaping '<' prevents source data from terminating the script element.
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    template = (ROOT / "assets" / "parking_explorer.html").read_text()
    return (template.replace("__LEAFLET_CSS__", (ROOT / "assets/vendor/leaflet.css").read_text())
            .replace("__LEAFLET_JS__", (ROOT / "assets/vendor/leaflet.js").read_text())
            .replace("__DATA__", data))


def explorer(records, district, facility):
    with st.container(horizontal=True, vertical_alignment="bottom"):
        query = st.text_input("역 이름 검색", placeholder="예: 남부터미널역, 홍대입구역",
                              key="parking_station_query", help="역 이름을 입력하고 Enter를 누르면 검색해요.")
        stations = station_search(query.strip() if query.strip() else f"{district} 지하철역")
        station_index = st.selectbox("가까운 시설을 찾을 역", range(len(stations) + 1),
                                     format_func=lambda i: "역 선택 안 함" if i == 0 else stations[i - 1]["name"],
                                     key=f"parking_station_{district}_{query.strip()}")
        radius = st.select_slider("강조 반경", options=[300, 500, 1000, 2000], value=500,
                                  format_func=lambda r: f"{r:,}m", key="parking_station_radius")
    animate = st.checkbox("가까운 핀 깜빡임", value=True, key="parking_pin_animation")
    station = stations[station_index - 1] if station_index else None
    if not stations:
        st.caption("역 검색 결과가 없어요. 정확한 역 이름을 입력해 주세요.")
    nearby = []
    if station:
        nearby = sorted([(distance_m(station, p), p) for p in records if distance_m(station, p) <= radius], key=lambda x: (x[0], x[1]["id"]))
        st.caption(f"{station['name']} 기준 직선거리 {radius:,}m 안 {facility} {len(nearby)}곳 · 현재 동네·검색·운영 조건에 맞는 시설만 강조해요.")
        if not nearby:
            st.info("선택한 반경에 표시할 시설이 없어요. 반경을 늘리거나 동네·검색 조건을 바꿔 주세요.")
    st.caption("핀에 마우스를 올리면 요약, 클릭하면 상세 안내를 볼 수 있어요. P는 주차장, ⚡는 충전소예요.")
    if records or station:
        st.iframe(map_html(records, station, radius, animate), height=570,
                  alt="주차장·충전소 지도. 핀을 누르면 이용시간과 요금 상세 안내를 볼 수 있어요.")
    else:
        st.info("이 조건에서 지도에 표시할 위치 자료가 없어요. 좌표가 없는 곳도 아래 목록에서 확인할 수 있어요.")
    if nearby:
        with st.expander(f"역에서 가까운 {facility} 목록 · {len(nearby)}곳"):
            st.dataframe(pd.DataFrame([{"장소": p["name"], "역에서 직선거리": f"{d:,.0f}m", "요금": p["price"],
                                        "이용시간": p["hours"], "주소": p["address"]} for d, p in nearby]),
                         hide_index=True, width="stretch")
