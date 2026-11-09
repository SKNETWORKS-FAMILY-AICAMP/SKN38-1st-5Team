import pandas as pd
import pydeck as pdk
import streamlit as st

from db import queries as q
from scene_parking import parking_hero
from ui import date_text, display_table, district_row, load_frame, load_options, number, topic_value, word


def _contains(frame: pd.DataFrame, keyword: str, columns: tuple[str, ...]) -> pd.Series:
    matched = pd.Series(not keyword, index=frame.index, dtype=bool)
    for column in columns:
        if column in frame and keyword:
            matched |= frame[column].astype("string").str.contains(
                keyword, case=False, regex=False, na=False,
            )
    return matched


def _parking_filter(frame: pd.DataFrame, keyword: str, operation: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    mask = frame["kind"].eq("parking_site") & _contains(frame, keyword, ("address",))
    if operation != "전체":
        mask &= frame["parking_operation"].eq(operation)
    return frame.loc[mask].copy()


def _parking_rows(region_id: int, keyword: str, points: pd.DataFrame) -> pd.DataFrame:
    # 빈 검색어는 충전소로 한도를 채우므로 주차장 제목으로 별도 조회한다.
    catalog = load_frame(q.search_places, "주차장 [", region_id=region_id, limit=100)
    frames = [catalog, points]
    if keyword:
        frames.append(load_frame(q.search_places, keyword, region_id=region_id, limit=100))
    columns = ["kind", "place_id", "address", "parking_operation", "parking_type",
               "space_count", "map_eligible", "coordinate_valid", "identifier_status"]
    parking = [frame.loc[frame["kind"].eq("parking_site")].reindex(columns=columns).astype(object)
               for frame in frames if not frame.empty and "kind" in frame]
    parking = [frame for frame in parking if not frame.empty]
    if not parking:
        return pd.DataFrame()
    for frame in parking:
        frame.attrs = {}
    # 검색 한도로 빠진 주차장을 보완하려고 지도 자료도 합친다.
    return pd.concat(parking, ignore_index=True).drop_duplicates(["kind", "place_id"])


def _map_note(row: pd.Series) -> str:
    eligible = row.get("map_eligible")
    if eligible is None or pd.isna(eligible):
        return "자료 없음"
    if eligible == 1:
        return "지도 표시"
    valid = row.get("coordinate_valid")
    if valid is not None and pd.notna(valid) and valid == 0:
        return "좌표 없음·범위 밖"
    if word(row.get("identifier_status")) == "conflict":
        return "관리번호 겹침"
    return "지도 제외"


def _coverage(points: pd.DataFrame, kind: str, district: str) -> dict:
    records = points.attrs.get("coverage", [])
    record = next((item for item in records if item.get("kind") == kind), {})
    label = "주차장" if kind == "parking_site" else "충전소"
    st.caption(
        f"{district} 전체 수록 {label} {number(record.get('total_count'), suffix='건')} · "
        f"지도 표시 가능 {number(record.get('point_count'), suffix='건')} · "
        f"지도 제외 {number(record.get('excluded_count'), suffix='건')} "
        f"(좌표 없음·범위 밖 {number(record.get('invalid_coordinate_count'), suffix='건')}, "
        f"관리번호 겹침 {number(record.get('identifier_conflict_count'), suffix='건')})"
    )
    return record


def _place_map(points: pd.DataFrame, kind: str) -> None:
    if points.empty:
        st.info("원본 자료에 이 동네 주차장의 위치(좌표) 정보가 없어 지도에 표시할 수 없어요. 아래 목록에서 주소로 확인해 주세요.")
        return
    # 주소로 위치를 추정하지 않고 get_place_points의 유효 좌표만 쓴다.
    data = points[["latitude", "longitude", "address"]].copy()
    data["address_label"] = data.pop("address").map(word)
    if kind == "parking_site":
        data["detail_label"] = [
            f"{word(row.parking_operation)} · {word(row.parking_type)} · {number(row.space_count, suffix='면')}"
            for _, row in points.iterrows()
        ]
        colors = {"공영": [39, 51, 107], "민영": [255, 122, 102]}
        data["color"] = [colors.get(value, [142, 152, 207])
                         for value in points.parking_operation.astype(object).fillna("")]
        st.caption("공영은 남색, 민영은 코랄, 구분 자료 없음은 연보라예요. 점에 마우스를 올리면 주소와 면수가 나와요.")
    else:
        data["detail_label"] = [
            f"{word(row.place_name)} · 충전기 {number(row.charger_count, suffix='기')}"
            for _, row in points.iterrows()
        ]
        data["color"] = [[39, 51, 107] for _ in range(len(data))]
        st.caption("지도 점 하나는 같은 운영자가 관리하는 충전소예요. 점에 마우스를 올리면 주소가 나와요.")
    coordinates = data[["longitude", "latitude"]].drop_duplicates()
    if len(coordinates) == 1:
        point = coordinates.iloc[0]
        view = pdk.ViewState(latitude=float(point.latitude), longitude=float(point.longitude), zoom=15)
    else:
        view = pdk.data_utils.compute_view(coordinates.to_numpy().tolist())
        view.zoom = min(view.zoom, 15)
    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=view,
            layers=[pdk.Layer(
                "ScatterplotLayer", id="parking-page-places", data=data,
                get_position="[longitude, latitude]", get_fill_color="color",
                get_radius=35, radius_min_pixels=5, radius_max_pixels=12,
                pickable=True, stroked=True, get_line_color=[255, 255, 255],
                line_width_min_pixels=1,
            )],
            tooltip={"text": "{address_label}\n{detail_label}"},
        ),
        key="parking_places_map", height=380, width="stretch",
        alt="검색 조건에 맞고 위치를 확인할 수 있는 주차장 또는 충전소 지도",
    )


def _source_caption(options: dict, source_code: str, label: str) -> None:
    snapshots = options.get("snapshots", pd.DataFrame())
    if snapshots.empty:
        st.caption(f"{label} · 자료 기준과 수집일 자료 없음")
        return
    rows = snapshots.loc[snapshots.source_code.eq(source_code)]
    if rows.empty:
        st.caption(f"{label} · 자료 기준과 수집일 자료 없음")
        return
    latest = rows.iloc[0]
    first, last = date_text(latest.reference_start), date_text(latest.reference_end)
    reference = "기준 기간은 알 수 없음" if "자료 없음" in (first, last) else f"자료 기준 {first} ~ {last}"
    st.caption(f"{label} · {reference} · 수집 {date_text(latest.collected_on)}")


selected = st.session_state.get("district_id")
if selected is None:
    st.info("위 메뉴에서 동네를 선택해 주세요.")
    st.stop()
region_id = int(selected)
options = load_options()
row = district_row(load_frame(q.get_district_ranking), region_id)
region = district_row(options.get("regions", pd.DataFrame()), region_id)
district = word(region.get("district_name", row.get("district_name")))
parking_value = topic_value(row, "parking")
if pd.notna(row.get("parking_rank")):
    parking_value += f" · 서울 25구 중 {int(row['parking_rank'])}위"

st.html("<style>.st-key-parking_page_hero { padding-bottom: 28px; }</style>")
with st.container(key="parking_page_hero"):
    parking_hero(
        district_id=region_id, district_name=district,
        parking_level=word(row.get("parking_level")), parking_value=parking_value,
        levels={topic: word(row.get(f"{topic}_level")) for topic in ("ownership", "parking", "need")},
        active_topic="parking",
    )

capacity = district_row(load_frame(q.get_parking_summary, [region_id]), region_id)
with st.grid(2, min_column_width=160, gap="small"):
    st.metric("공영 주차면", number(capacity.get("public_space_count"), suffix="면"), border=True)
    st.metric("민영 주차면", number(capacity.get("private_space_count"), suffix="면"), border=True)
st.caption(
    "수록된 주차장의 면수이며 아파트 주차장은 빠져 있어요. 실제 빈자리가 아니에요. "
    "관리번호가 겹치는 항목은 면수 합계와 지도에서 제외하며, 면수 자료가 빠지면 자료 없음으로 표시해요."
)

st.subheader(f"{district} 주차장 찾기", anchor=False)
with st.container(horizontal=True, vertical_alignment="bottom", gap="medium"):
    facility = st.segmented_control(
        "찾을 시설", ["주차장", "충전소"], default="주차장", required=True,
        key="parking_facility", persist_state="session",
    )
    keyword = st.text_input(
        "주소 검색", placeholder="도로명이나 동 이름을 입력해 주세요", max_chars=500,
        key="parking_keyword", width="stretch", persist_state="session",
        help="주차장은 주소로, 충전소는 이름이나 주소로 찾아요. 검색 기호도 글자 그대로 찾아요.",
    ).strip()
    if facility == "주차장":
        operation = st.segmented_control(
            "주차장 운영", ["전체", "공영", "민영"], default="전체", required=True,
            key="parking_operation", persist_state="session",
        ) or "전체"

if facility == "주차장":
    points = load_frame(q.get_place_points, region_id, kinds=("parking",), limit=None)
    catalog = _parking_rows(region_id, keyword, points)
    coverage = _coverage(points, "parking_site", district)
    if pd.notna(coverage.get("total_count")) and len(catalog) < coverage["total_count"]:
        st.warning("주차 목록 일부만 조회됐어요. 주소 검색은 최대 100건이므로 도로명이나 번지로 범위를 좁혀 주세요.")
    parking = _parking_filter(catalog, keyword, operation)
    visible_points = _parking_filter(points, keyword, operation)
    st.caption(f"현재 조건의 목록 {len(parking):,}건 · 지도 {len(visible_points):,}건")
    with st.container(border=True, gap="small", key="parking_map_panel"):
        _place_map(visible_points, "parking_site")
    st.markdown("**주소로 보는 주차장 목록**")
    st.caption("주차장 이름 자료가 없어 주소로 보여 드려요. 좌표가 없거나 관리번호가 겹쳐 지도에서 빠진 항목도 남겨 두었어요.")
    if not parking.empty:
        parking["space_label"] = parking.space_count.map(lambda value: number(value, suffix="면"))
        parking["map_note"] = parking.apply(_map_note, axis=1)
    display_table(
        parking,
        {"address": "주소", "parking_operation": "운영", "parking_type": "유형",
         "space_label": "주차면", "map_note": "지도 안내"},
        "선택한 동네와 주소, 공영·민영 조건에 맞는 주차장 목록. 지도에서 제외된 항목도 포함해요.",
    )
    _source_caption(options, "parking_standard", "수록 주차장")
else:
    points = load_frame(q.get_place_points, region_id, kinds=("charger",), limit=None)
    chargers = load_frame(q.get_charger_detail, region_id, limit=None)
    _coverage(points, "charging_station", district)
    visible_points = points.loc[_contains(points, keyword, ("address", "place_name"))].copy()
    chargers = chargers.loc[_contains(chargers, keyword, ("address", "station_name"))].copy()
    st.caption(f"현재 조건의 충전기 목록 {len(chargers):,}기 · 지도에 표시한 충전소 {len(visible_points):,}곳")
    with st.container(border=True, gap="small", key="parking_map_panel"):
        _place_map(visible_points, "charging_station")
    st.markdown("**충전기별 이용 안내**")
    st.caption(
        "환경공단 자료만 사용해요. 좌표 없는 충전소의 기기도 목록에 남겨 두었어요. "
        "운영시간과 이용제한은 수집 당시 안내예요. 실시간 사용 가능 여부가 아니며, 안내가 없어도 자유 이용을 뜻하지 않아요."
    )
    if not chargers.empty:
        chargers["speed_label"] = chargers.speed_code.astype(object).map(
            {"fast": "급속", "slow": "완속", "unknown": "속도 미상"},
        )
        eligible = set(points["place_id"]) if "place_id" in points else set()
        chargers["map_note"] = chargers.station_id.map(
            lambda value: "지도 표시" if value in eligible else "충전소 위치 자료 없음",
        )
    display_table(
        chargers,
        {"station_name": "충전소", "address": "주소", "source_charger_id": "기기번호",
         "speed_label": "속도", "capacity_text": "출력", "connector_text": "충전 방식",
         "operating_time_text": "운영시간", "restriction_note": "이용제한", "map_note": "지도 안내"},
        "주소나 이름에 맞는 충전기 목록과 운영시간, 이용제한 안내. 좌표 없는 기기도 포함해요.",
    )
    _source_caption(options, "keco_ev_charger", "환경공단 충전기")
