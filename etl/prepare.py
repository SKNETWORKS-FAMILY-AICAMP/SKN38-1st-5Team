"""1차 정제: 확보한 원본을 복사하고 검산한다. DB 적재·네트워크 호출 없음."""

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

import pandas as pd

from etl.crawl_faq import extract_faq

PROJECT = Path(__file__).resolve().parents[1]
RAW = PROJECT / "data/raw"
OUT = PROJECT / "data/processed"
MONTH = "2026-09-01"
FETCHED_ON = "2026-11-05"
DISTRICT = (
    "종로구 중구 용산구 성동구 광진구 동대문구 중랑구 성북구 강북구 도봉구 "
    "노원구 은평구 서대문구 마포구 양천구 강서구 구로구 금천구 영등포구 "
    "동작구 관악구 서초구 강남구 송파구 강동구"
).split()
ADDRESS = re.compile(r"^서울(?:특별시|시)?\s*,?\s*(" + "|".join(sorted(DISTRICT, key=len, reverse=True)) + r")")
VEHICLE = ("passenger", "bus", "truck", "special")
USAGE = ("official", "private", "commercial")
SOURCE = {
    "data_A/molit_202609.xlsx": ("molit_registration", "https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=58", "2026-09-01", "2026-09-30"),
    "b_verified/seoul_fuel_202609.xlsx": ("seoul_fuel", "https://data.seoul.go.kr/dataList/OA-15640/S/1/datasetView.do", "2026-09-01", "2026-09-30"),
    "ab_verified/seoul_charger_api.json": ("seoul_charger", "https://data.seoul.go.kr/dataList/OA-23033/S/1/datasetView.do", None, None),
    "data_A/parking_page0.json": ("national_parking", "https://www.data.go.kr/data/15012896/standard.do", "2026-04-08", "2026-10-30"),
    "data_A/parking_page1.json": ("national_parking", "https://www.data.go.kr/data/15012896/standard.do", "2026-04-08", "2026-10-30"),
    "data_A/parking_page2.json": ("national_parking", "https://www.data.go.kr/data/15012896/standard.do", "2026-04-08", "2026-10-30"),
    "data_A/seoul_registration_population_202609.csv": ("resident_join", "https://jumin.mois.go.kr/statMonth.do", "2026-09-01", "2026-09-30"),
    "data_A/jumin_sgg_202609.csv": ("resident_population", "https://jumin.mois.go.kr/statMonth.do", "2026-09-01", "2026-09-30"),
    "ab_verified/hyundai_ev_current.html": ("hyundai_ev_faq", "https://www.hyundai.com/kr/ko/service-membership/ev/ev-everycare/ev", None, None),
}


def clean_text(value: object) -> str:
    return "" if pd.isna(value) else " ".join(str(value).split())


def count_value(value: object) -> int:
    text = clean_text(value)
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.0+)?", text):
        raise ValueError("대수 또는 인구에 정수가 아닌 값이 있습니다.")
    return int(text.replace(",", "").split(".")[0])


def district_from_address(value: object) -> str | None:
    match = ADDRESS.match(clean_text(value))
    return match[1] if match else None


def save_frame(name: str, frame: pd.DataFrame, output_dir: Path = OUT) -> None:
    frame.to_csv(output_dir / name, index=False, encoding="utf-8-sig", lineterminator="\n")


def record_check(checks: list, name: str, actual: object, expected: object) -> None:
    if hasattr(actual, "item"):
        actual = actual.item()
    checks.append({"check": name, "actual": actual, "expected": expected, "passed": actual == expected})


def copy_source(source_dir: Path, error: list) -> list:
    manifest = []
    for relative, (code, url, start, end) in SOURCE.items():
        source = source_dir / relative
        target = RAW / relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            content = source.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                partial = None
                try:
                    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
                        partial = Path(temporary.name)
                        temporary.write(content)
                    partial.replace(target)
                finally:
                    if partial is not None:
                        partial.unlink(missing_ok=True)
        except OSError as exc:
            error.append({"stage": "source", "source_file": relative, "error_type": type(exc).__name__})
            continue
        manifest.append({
            "source_code": code, "artifact_path": f"data/raw/{relative}", "source_url": url,
            "content_sha256": digest, "byte_count": target.stat().st_size,
            "reference_start": start, "reference_end": end, "fetched_on": FETCHED_ON,
            "date_note": "기존 수집본의 수집일. 현재 정제 실행일과 구분한다.",
        })
    return manifest


def prepare_population(checks: list, output_dir: Path = OUT) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    path = RAW / "data_A/seoul_registration_population_202609.csv"
    encoding = "utf-8-sig" if path.read_bytes().startswith(b"\xef\xbb\xbf") else "cp949"
    joined = pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False)
    joined["district_name"] = joined["region_name"].str.replace("서울특별시 ", "", regex=False)
    record_check(checks, "인구 연결 CSV 서울 25구", set(joined["district_name"]) == set(DISTRICT) and len(joined) == 25, True)
    raw = pd.read_csv(RAW / "data_A/jumin_sgg_202609.csv", encoding="cp949", dtype=str, keep_default_na=False)
    name = raw["행정구역"].str.extract(r"^\s*(서울특별시\s+[^()]+?)\s*\((11\d{8})\)\s*$")
    raw["district_name"] = name[0].str.replace("서울특별시 ", "", regex=False).str.strip()
    raw["resident_code"] = name[1]
    raw = raw.loc[raw["district_name"].isin(DISTRICT)].copy()
    raw["population"] = raw["2026년09월_총인구수"].map(count_value)
    raw["household_count"] = raw["2026년09월_세대수"].map(count_value)
    record_check(checks, "CP949 인구 원본 서울 행", len(raw), 25)
    joined["population"] = joined["population"].map(count_value)
    joined["household_count"] = joined["households"].map(count_value)
    matched = joined.merge(raw[["district_name", "resident_code", "population", "household_count"]], on="district_name", suffixes=("_joined", "_raw"), validate="one_to_one")
    record_check(checks, "인구 원본과 연결 CSV 일치", bool(
        (matched["population_joined"] == matched["population_raw"]).all()
        and (matched["household_count_joined"] == matched["household_count_raw"]).all()
        and (matched["region_code"] == matched["resident_code"]).all()
    ), True)
    region = raw[["resident_code", "district_name"]].sort_values("district_name").reset_index(drop=True)
    region.insert(1, "province_name", "서울특별시")
    record_check(checks, "주민등록 코드 중복", int(region["resident_code"].duplicated().sum()), 0)
    record_check(checks, "서울 구 주민등록 코드 형식", bool(region["resident_code"].str.fullmatch(r"11[0-9]{3}00000").all()), True)
    context = raw[["resident_code", "district_name", "population", "household_count"]].sort_values("district_name").reset_index(drop=True)
    context.insert(2, "stat_month", MONTH)
    record_check(checks, "서울 인구 합계", context["population"].sum(), 9279861)
    record_check(checks, "서울 세대 합계", context["household_count"].sum(), 4524905)
    save_frame("region.csv", region, output_dir)
    save_frame("region_context.csv", context, output_dir)
    return region, joined, {"joined_encoding": encoding, "raw_encoding": "cp949", "row_count": len(context), "population": int(context["population"].sum()), "household_count": int(context["household_count"].sum())}


def prepare_registration(region: pd.DataFrame, joined: pd.DataFrame, checks: list, output_dir: Path = OUT) -> tuple[pd.DataFrame, dict]:
    sheet = pd.read_excel(RAW / "data_A/molit_202609.xlsx", sheet_name="02.통계표_시군구", header=None)
    record_check(checks, "통계누리 기준월", clean_text(sheet.iat[1, 1]), "2026.09")
    data = sheet.iloc[4:].copy()
    data[0] = data[0].ffill()
    detail, total = [], []
    valid_row_count = 0
    leaf_count = 0
    for index, row in data.iterrows():
        values = [count_value(row[col]) for col in range(2, 22)]
        row_valid = all(sum(values[j:j + 3]) == values[j + 3] for j in (0, 4, 8, 12, 16))
        row_valid = row_valid and all(sum(values[j + k] for j in (0, 4, 8, 12)) == values[16 + k] for k in range(4))
        valid_row_count += int(row_valid)
        district = clean_text(row[1])
        if district in ("계", "총계"):
            total.append({"province_name_source": clean_text(row[0]), "row_kind": district, "vehicle_count": values[19], "source_row_no": index + 1})
            continue
        leaf_count += 1
        for kind, vehicle in enumerate(VEHICLE):
            for use, usage in enumerate(USAGE):
                detail.append({"province_name_source": clean_text(row[0]), "district_name": district, "stat_month": MONTH, "vehicle_type_code": vehicle, "usage_type_code": usage, "vehicle_count": values[kind * 4 + use], "source_row_no": index + 1})
    national = pd.DataFrame(detail)
    subtotal = pd.DataFrame(total)
    record_check(checks, "통계누리 모든 행의 용도·차종 합계", valid_row_count, len(data))
    record_check(checks, "통계누리 전국 지역 행", leaf_count, 263)
    record_check(checks, "통계누리 전국 세로형 행", len(national), 3156)
    record_check(checks, "전국 등록 합계", national["vehicle_count"].sum(), 26706123)
    record_check(checks, "전국 원본 총계", int(subtotal.loc[subtotal["row_kind"] == "총계", "vehicle_count"].sum()), 26706123)
    record_check(checks, "전국 등록 자연키 중복", int(national.duplicated(["province_name_source", "district_name", "stat_month", "vehicle_type_code", "usage_type_code"]).sum()), 0)
    seoul = national.loc[national["province_name_source"] == "서울"].drop(columns="province_name_source").merge(region[["resident_code", "district_name"]], on="district_name", validate="many_to_one")
    record_check(checks, "서울 등록 세로형 행", len(seoul), 300)
    record_check(checks, "서울 등록 합계", seoul["vehicle_count"].sum(), 3150351)
    for column, subset in [("vehicles", seoul), ("private_passenger", seoul.loc[(seoul["vehicle_type_code"] == "passenger") & (seoul["usage_type_code"] == "private")])]:
        actual = subset.groupby("district_name")["vehicle_count"].sum().sort_index()
        expected = joined.set_index("district_name")[column].map(count_value).sort_index()
        record_check(checks, f"인구 연결 CSV의 {column} 구별 대조", actual.equals(expected), True)
    all_registration = seoul.groupby(["resident_code", "district_name", "stat_month", "vehicle_type_code"], as_index=False)["vehicle_count"].sum()
    all_registration["fuel_scope_code"] = "all"
    all_registration["source_code"] = "molit_registration"
    save_frame("registration_national_audit.csv", national, output_dir)
    grouped = national.groupby(
        ["province_name_source", "stat_month", "vehicle_type_code", "usage_type_code"],
        as_index=False,
    )["vehicle_count"].sum().rename(columns={"province_name_source": "province_name", "usage_type_code": "usage_code"})
    province_sheet = pd.read_excel(RAW / "data_A/molit_202609.xlsx", sheet_name="01.통계표", header=None)
    record_check(checks, "시도 통계표 기준월", clean_text(province_sheet.iat[1, 1]), "2026.09")
    province = pd.DataFrame([
        {"province_name": clean_text(row[0]), "stat_month": MONTH,
         "vehicle_type_code": vehicle, "usage_code": usage,
         "vehicle_count": count_value(row[2 + kind * 4 + use])}
        for _, row in province_sheet.iloc[5:21].iterrows()
        for kind, vehicle in enumerate(VEHICLE)
        for use, usage in enumerate(USAGE)
    ])
    key = ["province_name", "stat_month", "vehicle_type_code", "usage_code"]
    record_check(checks, "시도 원표와 시군구 합산 192개 값 대조",
                 province.set_index(key).sort_index().equals(grouped.set_index(key).sort_index()), True)
    record_check(checks, "시도 등록 자연키 중복", int(province.duplicated(key).sum()), 0)
    save_frame("province_registration.csv", province, output_dir)
    record_check(checks, "시도 집계 전국 등록 합계", province["vehicle_count"].sum(), 26706123)
    save_frame("registration_total_audit.csv", subtotal, output_dir)
    save_frame("registration_usage.csv", seoul, output_dir)
    return all_registration, {"national_region_count": leaf_count, "national_row_count": len(national), "national_total": int(national["vehicle_count"].sum()), "seoul_row_count": len(seoul), "seoul_total": int(seoul["vehicle_count"].sum())}


def prepare_fuel(region: pd.DataFrame, all_registration: pd.DataFrame, checks: list, output_dir: Path = OUT) -> dict:
    sheet = pd.read_excel(RAW / "b_verified/seoul_fuel_202609.xlsx", header=None)
    record_check(checks, "서울 연료 기준월", clean_text(sheet.iat[5, 2]), "2026.09")
    record_check(checks, "서울 연료 원본 총계", count_value(sheet.iat[7, 15]), 3150351)
    data = sheet.iloc[8:].copy()
    data[0] = data[0].ffill()
    data = data.loc[data[0].isin(DISTRICT) & data[6].isin(("사업용", "비사업용"))]
    detail = []
    valid_row_count = 0
    for index, row in data.iterrows():
        counts = [count_value(row[col]) for col in (7, 8, 9, 12)]
        valid_row_count += int(sum(counts) == count_value(row[15]))
        for vehicle, count in zip(VEHICLE, counts):
            detail.append({"district_name": clean_text(row[0]), "stat_month": MONTH, "fuel_name": clean_text(row[3]), "usage_name": clean_text(row[6]), "vehicle_type_code": vehicle, "vehicle_count": count, "source_row_no": index + 1})
    fuel = pd.DataFrame(detail).merge(region[["resident_code", "district_name"]], on="district_name", validate="many_to_one")
    keys = ["resident_code", "district_name", "stat_month", "vehicle_type_code"]
    fuel_total = fuel.groupby(keys)["vehicle_count"].sum().sort_index()
    all_total = all_registration.set_index(keys)["vehicle_count"].sort_index()
    record_check(checks, "연료 원본 행의 차종 합계", valid_row_count, len(data))
    record_check(checks, "통계누리·연료 구×차종 100개 일치", fuel_total.equals(all_total), True)
    record_check(checks, "연료 상세 자연키 중복", int(fuel.duplicated(keys + ["fuel_name", "usage_name"]).sum()), 0)
    electric = fuel.loc[fuel["fuel_name"] == "전기"].groupby(keys, as_index=False)["vehicle_count"].sum()
    electric["fuel_scope_code"] = "electric"
    electric["source_code"] = "seoul_fuel"
    record_check(checks, "전기 등록 구×차종 행", len(electric), 100)
    record_check(checks, "서울 전기 등록 합계", electric["vehicle_count"].sum(), 127750)
    registration = pd.concat([all_registration, electric], ignore_index=True).sort_values(keys + ["fuel_scope_code"])
    save_frame("registration_fuel.csv", fuel, output_dir)
    save_frame("registration.csv", registration, output_dir)
    return {"source_detail_row_count": len(data), "detail_row_count": len(fuel), "registration_row_count": len(registration), "all_total": int(fuel_total.sum()), "electric_total": int(electric["vehicle_count"].sum())}


def prepare_charger(region: pd.DataFrame, checks: list, output_dir: Path = OUT) -> dict:
    payload = json.loads((RAW / "ab_verified/seoul_charger_api.json").read_text())["aiEvCharging"]
    rows = payload["row"]
    record_check(checks, "충전 원본 응답 코드", payload["RESULT"]["CODE"], "INFO-000")
    record_check(checks, "충전 원본 행", len(rows), 433)
    record_check(checks, "충전 응답 전체 수신", len(rows), payload["list_total_count"])
    detail, excluded = [], []
    for number, row in enumerate(rows, 1):
        district = district_from_address(row["ADDR"])
        if district is None or district != clean_text(row["SGG"]):
            excluded.append({"source_row_no": number, "reason": "outside_seoul" if district is None else "district_mismatch"})
            continue
        station_part = [clean_text(row[key]) for key in ("OPER_INST", "CHARG_STTN", "ADDR")]
        capacity = clean_text(row["CHARG_CPCT"])
        speed = "fast" if capacity.startswith("급속(") else "slow" if capacity.startswith("완속(") else "unknown"
        detail.append({
            "district_name": district, "snapshot_date": FETCHED_ON,
            "station_key": hashlib.sha256(json.dumps(station_part, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
            "operator_name": station_part[0], "station_name": station_part[1], "address": station_part[2],
            "source_charger_id": clean_text(row["CHARG_ID"]), "source_row_no": number,
            "speed_code": speed, "connector_text": clean_text(row["CHARG_TYPE"]), "capacity_text": capacity,
            "operating_time_text": clean_text(row["USE_PSBLTY_TM"]), "restriction_note": clean_text(row["USER_LMT"]) or None,
            "source_x": clean_text(row["X"]) or None, "source_y": clean_text(row["Y"]) or None,
        })
    charger = pd.DataFrame(detail).merge(region[["resident_code", "district_name"]], on="district_name", validate="many_to_one")
    record_check(checks, "서울 충전 행", len(charger), 429)
    record_check(checks, "서울 충전 25구", charger["district_name"].nunique(), 25)
    record_check(checks, "급속 항목", int(charger["speed_code"].eq("fast").sum()), 356)
    record_check(checks, "완속 항목", int(charger["speed_code"].eq("slow").sum()), 73)
    record_check(checks, "충전 자연키 중복", int(charger.duplicated(["station_key", "source_charger_id"]).sum()), 0)
    record_check(checks, "충전기 ID 빈 값", int(charger["source_charger_id"].eq("").sum()), 0)
    record_check(checks, "충전 제한 문구 존재", int(charger["restriction_note"].notna().sum()), 1)
    record_check(checks, "충전 제한 문구 미상", int(charger["restriction_note"].isna().sum()), 428)
    save_frame("charger.csv", charger, output_dir)
    station = charger[["station_key", "resident_code", "district_name", "snapshot_date", "operator_name", "station_name", "address"]].drop_duplicates()
    save_frame("charging_station.csv", station, output_dir)
    save_frame("charger_exclusion.csv", pd.DataFrame(excluded, columns=["source_row_no", "reason"]), output_dir)
    return {"raw_row_count": len(rows), "row_count": len(charger), "excluded_row_count": len(excluded), "station_row_count": len(station), "fast_count": int(charger["speed_code"].eq("fast").sum()), "slow_count": int(charger["speed_code"].eq("slow").sum()), "restriction_unknown_count": int(charger["restriction_note"].isna().sum())}


def prepare_parking(region: pd.DataFrame, checks: list, output_dir: Path = OUT) -> dict:
    frames = []
    page_counts = {}
    for page in range(3):
        name = f"data_A/parking_page{page}.json"
        rows = json.loads((RAW / name).read_text())
        page_counts[str(page)] = len(rows)
        if rows:
            frame = pd.DataFrame(rows)
            frame["source_file"] = name
            frame["source_file_row_no"] = range(1, len(frame) + 1)
            frames.append(frame)
    raw = pd.concat(frames, ignore_index=True)
    raw["source_row_no"] = range(1, len(raw) + 1)
    original_columns = [c for c in raw if not c.startswith("source_")]
    raw["exact_duplicate"] = raw.duplicated(original_columns, keep=False)
    raw["identifier_status"] = raw.duplicated(["INSTT_CODE", "PRKPLCE_NO"], keep=False).map({True: "conflict", False: "unique"})
    record_check(checks, "주차 원본 행", len(raw), 18994)
    record_check(checks, "주차 page0 빈 응답", page_counts["0"], 0)
    detail, excluded = [], []
    seoul_raw_count = 0
    for _, row in raw.iterrows():
        road, lot = clean_text(row["RDNMADR"]), clean_text(row["LNMADR"])
        if not (road.startswith("서울") or lot.startswith("서울")):
            continue
        seoul_raw_count += 1
        road_district, lot_district = district_from_address(road), district_from_address(lot)
        if road_district and lot_district and road_district != lot_district:
            excluded.append({"source_row_no": row["source_row_no"], "reason": "address_district_conflict"})
            continue
        district = road_district or lot_district
        if district is None:
            excluded.append({"source_row_no": row["source_row_no"], "reason": "district_not_found"})
            continue
        space = count_value(row["PRKCMPRT"]) if clean_text(row["PRKCMPRT"]) else None
        detail.append({
            "resident_code": None, "district_name": district, "snapshot_date": FETCHED_ON,
            "institution_code": clean_text(row["INSTT_CODE"]), "source_parking_no": clean_text(row["PRKPLCE_NO"]),
            "parking_operation": clean_text(row["PRKPLCE_SE"]), "parking_type": clean_text(row["PRKPLCE_TYPE"]),
            "address": road if road_district else lot, "space_count": space,
            "latitude": row["LATITUDE"], "longitude": row["LONGITUDE"],
            "reference_date": clean_text(row["REFERENCE_DATE"]), "identifier_status": row["identifier_status"],
            "exact_duplicate": int(row["exact_duplicate"]), "source_file": row["source_file"],
            "source_file_row_no": row["source_file_row_no"], "source_row_no": row["source_row_no"],
        })
    parking = pd.DataFrame(detail).drop(columns="resident_code").merge(region[["resident_code", "district_name"]], on="district_name", validate="many_to_one")
    parking["space_count"] = parking["space_count"].astype("Int64")
    for column, low, high in [("latitude", -90, 90), ("longitude", -180, 180)]:
        values = pd.to_numeric(parking[column], errors="coerce")
        parking[column] = values.where(values.between(low, high))
    parking["coordinate_valid"] = (parking["latitude"].between(37.4, 37.75) & parking["longitude"].between(126.75, 127.2)).astype(int)
    parking["map_eligible"] = (parking["coordinate_valid"].eq(1) & parking["identifier_status"].eq("unique")).astype(int)
    dates = pd.to_datetime(parking["reference_date"], errors="coerce")
    record_check(checks, "주차 기준일 파싱 실패", int(dates.isna().sum()), 0)
    record_check(checks, "서울 주차 원본 행", seoul_raw_count, 857)
    record_check(checks, "서울 주차 주소 연결", len(parking), 857)
    record_check(checks, "서울 주차 구 수", parking["district_name"].nunique(), 25)
    record_check(checks, "서울 주차 연결 실패", len(excluded), 0)
    record_check(checks, "주차 지도 후보: 좌표 범위와 식별번호 검사", int(parking["map_eligible"].sum()), 784)
    save_frame("parking_site.csv", parking, output_dir)
    save_frame("parking_exclusion.csv", pd.DataFrame(excluded, columns=["source_row_no", "reason"]), output_dir)
    return {"raw_row_count": len(raw), "page_row_count": page_counts, "row_count": len(parking), "excluded_row_count": len(excluded), "identifier_conflict_count": int(parking["identifier_status"].eq("conflict").sum()), "exact_duplicate_member_count": int(parking["exact_duplicate"].sum()), "coordinate_candidate_count": int(parking["coordinate_valid"].sum()), "map_eligible_count": int(parking["map_eligible"].sum()), "missing_space_count": int(parking["space_count"].isna().sum()), "unique_space_sum": int(parking.loc[parking["identifier_status"].eq("unique"), "space_count"].sum()), "raw_space_sum_audit_only": int(parking["space_count"].sum()), "reference_min": str(dates.min().date()), "reference_max": str(dates.max().date())}


def write_json(path: Path, value: dict) -> None:
    partial = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as temporary:
            partial = Path(temporary.name)
            json.dump(value, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        partial.replace(path)
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)


def prepare_bundle(source_dir: Path, output_dir: Path = OUT) -> dict:
    # 동시 실행은 지원하지 않으며, CSV는 validation.json의 passed·published가 모두 true일 때만 읽는다.
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_path = output_dir / "validation.json"
    write_json(validation_path, {"passed": False, "published": False, "status": "running"})
    checks, error, summary = [], [], {}
    manifest = copy_source(source_dir, error)
    available = {item["artifact_path"].removeprefix("data/raw/") for item in manifest}

    def execute_step(name: str, callback, required: list[str], dependency_ready: bool = True):
        missing = sorted(set(required) - available)
        if missing or not dependency_ready:
            error.append({"stage": name, "error_type": "MissingInput", "missing_source_file": missing})
            return None
        try:
            return callback()
        except Exception as exc:
            # 원본 셀이나 접속값이 포함될 수 있는 예외 원문은 기록하지 않는다.
            error.append({"stage": name, "error_type": type(exc).__name__})
            return None

    with tempfile.TemporaryDirectory(prefix=".etl-", dir=output_dir.parent) as directory:
        stage = Path(directory)
        population = execute_step(
            "population", lambda: prepare_population(checks, stage),
            ["data_A/seoul_registration_population_202609.csv", "data_A/jumin_sgg_202609.csv"],
        )
        region = joined = all_registration = None
        if population is not None:
            region, joined, summary["population"] = population
        registration = execute_step(
            "registration", lambda: prepare_registration(region, joined, checks, stage),
            ["data_A/molit_202609.xlsx"], population is not None,
        )
        if registration is not None:
            all_registration, summary["registration"] = registration
        fuel = execute_step(
            "fuel", lambda: prepare_fuel(region, all_registration, checks, stage),
            ["b_verified/seoul_fuel_202609.xlsx"], registration is not None,
        )
        if fuel is not None:
            summary["fuel"] = fuel
        charger = execute_step(
            "charger", lambda: prepare_charger(region, checks, stage),
            ["ab_verified/seoul_charger_api.json"], population is not None,
        )
        if charger is not None:
            summary["charger"] = charger
        parking = execute_step(
            "parking", lambda: prepare_parking(region, checks, stage),
            [f"data_A/parking_page{page}.json" for page in range(3)], population is not None,
        )
        if parking is not None:
            summary["parking"] = parking
        faq = execute_step(
            "faq", lambda: extract_faq(RAW / "ab_verified/hyundai_ev_current.html"),
            ["ab_verified/hyundai_ev_current.html"],
        )
        if faq is not None:
            save_frame("faq.csv", faq, stage)
            record_check(checks, "현대 EV FAQ 질문·답변 쌍", len(faq), 10)
            summary["faq"] = {"row_count": len(faq)}
        output_row_count = {
            path.name: len(pd.read_csv(path, encoding="utf-8-sig"))
            for path in sorted(stage.glob("*.csv"))
        }
        record_check(checks, "정제 CSV 파일 수", len(output_row_count), 14)
        passed = not error and all(check["passed"] for check in checks)
        summary.update(checks=checks, error=error, passed=passed, published=False,
                       status="validated" if passed else "failed", output_row_count=output_row_count)
        summary["output_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(stage.glob("*.csv"))}
        if passed:
            write_json(stage / "source_manifest.json", build_manifest(manifest))
            try:
                for path in sorted(stage.iterdir()):
                    path.replace(output_dir / path.name)
            except OSError as exc:
                summary.update(passed=False, status="publish_failed")
                error.append({"stage": "publish", "error_type": type(exc).__name__})
            else:
                summary.update(published=True, status="complete")
        # 파일 교체 도중 종료되면 앞서 기록한 running/false 상태가 유지된다.
        write_json(validation_path, summary)
    return summary


def build_manifest(manifest: list) -> dict:
    return {
        "source": manifest,
        "scope": "서울 점수는 25구. 전국 원본 상세는 검산용이며 province_registration.csv의 시도·차종·용도 집계만 전국 조회에 적재한다.",
        "charger_note": "433행 전체 수신 중 서울 주소 429행. 자료 행의 기준일과 EPSG는 미확인. source_x/y를 위경도로 사용하지 않는다.",
        "parking_note": "page0은 빈 응답. page1, page2를 순서대로 합친 source_row_no를 보존한다. 식별번호 충돌행을 삭제하지 않는다. 전국 수록 목록이며 전체 주차 공급의 완전성은 미확인.",
        "registration_note": "연료 all에 electric이 포함된다. registration_usage의 관용/자가용/영업용과 registration_fuel의 사업용/비사업용을 같은 용도로 연결하지 않는다.",
        "population_note": "지정 연결 CSV는 UTF-8 BOM이다. CP949 jumin_sgg 원본으로 구별 인구·세대·코드를 대조했다.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=RAW,
                        help="기본값은 프로젝트 data/raw. 최초 복사는 기존 다운로드 폴더를 지정한다.")
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args(argv)
    try:
        summary = prepare_bundle(args.source_dir, args.output_dir)
    except Exception:
        print("정제 실패: 원본과 출력 폴더 권한을 확인하세요. 미완료 검산 기록은 적재에 사용하지 마세요.")
        return 1
    for name in ("registration", "fuel", "charger", "parking", "population", "faq"):
        if name in summary:
            print(f"{name}: {json.dumps(summary[name], ensure_ascii=False)}")
    checks = summary["checks"]
    print(f"검산: {sum(c['passed'] for c in checks)}/{len(checks)} 통과")
    for check in checks:
        if not check["passed"]:
            print(f"검산 불일치: {check['check']}")
    for error in summary["error"]:
        print(f"처리 실패: {error['stage']} ({error['error_type']})")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
