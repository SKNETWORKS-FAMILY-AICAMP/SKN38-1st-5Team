from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

from etl.fetch_asos import COLUMN as WEATHER_COLUMN
from etl.fetch_ev_chargers import COLUMN as CHARGER_COLUMN, DISTRICT

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"
OUT = ROOT / "work"


def csv_path(name):
    path = DATA / name
    if name == "charger_national_snapshot.csv" and not path.exists():
        return ROOT / "data/raw/api" / name
    return path


def read_csv(name):
    with csv_path(name).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        return reader.fieldnames, list(reader)


def normalize_text(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).casefold())


def normalize_address(value, approximate=False):
    value = unicodedata.normalize("NFKC", value)
    if approximate:
        value = re.sub(r"\([^)]*\)", "", value).split(",", 1)[0]
    return normalize_text(re.sub(r"^서울(?:특별시|시)?", "서울", value.strip()))


def verify_snapshot(name, expected_column):
    column, rows = read_csv(name + ".csv")
    path = csv_path(name + ".csv")
    meta = json.loads((DATA / (name + ".meta.json")).read_text())
    if column != list(expected_column):
        raise ValueError("수집 CSV 열이 계약과 다릅니다.")
    if len(rows) != meta["row_count"] or len(rows) != meta["total_count"]:
        raise ValueError("CSV 행 수와 메타데이터 건수가 다릅니다.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != meta["content_sha256"]:
        raise ValueError("CSV와 메타데이터 해시가 다릅니다.")
    return rows, meta


def verify_weather(weather, weather_meta):
    if (weather_meta.get("source_code") != "kma_asos_hourly"
            or weather_meta.get("station_id") != "108"
            or weather_meta.get("timezone") != "Asia/Seoul"):
        raise ValueError("기상 출처·관측소·시간대가 수집 계약과 다릅니다.")
    start = datetime.combine(date.fromisoformat(weather_meta["reference_start"]), datetime.min.time())
    end = datetime.combine(date.fromisoformat(weather_meta["reference_end"]), datetime.min.time()) + timedelta(days=1)
    if start >= end:
        raise ValueError("기상 기준 기간이 올바르지 않습니다.")
    expected = {(start + timedelta(hours=hour)).strftime("%Y-%m-%d %H:%M:%S")
                for hour in range(int((end - start).total_seconds() // 3600))}
    actual = {row["observed_at"] for row in weather}
    if len(actual) != len(weather) or actual - expected:
        raise ValueError("기상 시간에 중복 또는 기간 밖 값이 있습니다.")
    if (weather_meta.get("expected_hour_count") != len(expected)
            or weather_meta.get("missing_hour_count") != len(expected - actual)
            or weather_meta.get("is_complete") is not (actual == expected)):
        raise ValueError("기상 시간 완결 여부와 메타데이터가 다릅니다.")
    for row in weather:
        for value, flag in (("temperature_c", "temperature_qc_flag"),
                            ("rain_mm", "rain_qc_flag"), ("wind_speed_ms", "wind_qc_flag")):
            code = row[flag]
            if code and not re.fullmatch(r"[0-9]", code):
                raise ValueError("기상 품질 플래그 형식이 올바르지 않습니다.")
            if code not in {"", "0"} and row[value]:
                raise ValueError("비정상 품질의 기상 숫자는 NULL이어야 합니다.")
    for column in ("temperature_c", "rain_mm", "snow_cm", "wind_speed_ms"):
        for row in weather:
            if row[column]:
                value = Decimal(row[column])
                bound = Decimal("999.99" if column == "temperature_c" else "999999.99")
                if (not value.is_finite() or abs(value) > bound
                        or value != value.quantize(Decimal(".01"))
                        or (column != "temperature_c" and value < 0)):
                    raise ValueError("기상 수치가 MySQL 자료형 범위를 벗어납니다.")
    return expected, actual


def main():
    weather, weather_meta = verify_snapshot("weather_snapshot", WEATHER_COLUMN)
    charger, charger_meta = verify_snapshot("charger_national_snapshot", CHARGER_COLUMN)
    _, old_station = read_csv("charging_station.csv")
    _, old_charger = read_csv("charger.csv")
    expected, actual = verify_weather(weather, weather_meta)
    if len({(r["source_station_id"], r["source_charger_id"]) for r in charger}) != len(charger):
        raise ValueError("충전기 자연키가 중복되었습니다.")
    if any(r["province_code"] != "11" for r in charger):
        raise ValueError("서울 밖 지역코드가 있습니다.")
    if sorted(int(r["source_row_no"]) for r in charger) != list(range(1, len(charger) + 1)):
        raise ValueError("원본 충전기 행 번호가 연속되지 않습니다.")

    station_attribute = defaultdict(lambda: defaultdict(set))
    for row in charger:
        for column in ("station_name", "operator_name", "address", "district_name"):
            station_attribute[row["source_station_id"]][column].add(row[column])
    conflict_id = {station for station, attribute in station_attribute.items()
                   if any(len(value) > 1 for value in attribute.values())}
    active = [r for r in charger if r["deleted_code"] == "N"]
    active_id = {r["source_station_id"] for r in active}
    exact_index, address_index = defaultdict(set), defaultdict(set)
    for row in active:
        name = normalize_text(row["station_name"])
        exact_index[(name, normalize_address(row["address"]))].add(row["source_station_id"])
        address_index[normalize_address(row["address"], True)].add((name, row["source_station_id"]))

    exact_old, candidate_old, address_old = set(), set(), set()
    exact_new, candidate_new = set(), set()
    for row in old_station:
        name = normalize_text(row["station_name"])
        exact = exact_index.get((name, normalize_address(row["address"])), set())
        candidate = set(exact)
        address = address_index.get(normalize_address(row["address"], True), set())
        for new_name, station in address:
            if SequenceMatcher(None, name, new_name).ratio() >= 0.6:
                candidate.add(station)
        if exact:
            exact_old.add(row["station_key"])
            exact_new.update(exact)
        if candidate:
            candidate_old.add(row["station_key"])
            candidate_new.update(candidate)
        if address:
            address_old.add(row["station_key"])

    district = Counter(r["district_name"] or "미연결" for r in charger)
    old_district = Counter(r["district_name"] for r in old_charger)
    mobile_pattern = re.compile(r"(?<!\d)01[016789][\s-]?\d{3,4}[\s-]?\d{4}(?!\d)")
    text_column = ("station_name", "operator_name", "address", "operating_time_text",
                   "restriction_note", "deleted_note", "floor_number")
    result = {
        "structural_check_passed": True,
        "weather": {
            "artifact_path": csv_path("weather_snapshot.csv").relative_to(ROOT).as_posix(),
            "row_count": len(weather), "expected_hour_count": len(expected),
            "missing_hour": sorted(expected - actual), "duplicate_hour_count": 0,
            "quality_value_check_passed": True,
            "time_completeness_matches_metadata": True,
            "numeric_sql_range_check": True, "sha256_matches": True,
            "null_count": {c: sum(not r[c] for r in weather) for c in WEATHER_COLUMN},
            "quality_count": {c: dict(Counter(r[c] or "NULL" for r in weather))
                              for c in WEATHER_COLUMN if c.endswith("_qc_flag")},
            "collected_at": weather_meta["collected_at"],
        },
        "charger": {
            "artifact_path": csv_path("charger_national_snapshot.csv").relative_to(ROOT).as_posix(),
            "row_count": len(charger), "station_count": len(station_attribute),
            "operator_station_group_count": len({(r["source_station_id"], r["operator_name"]) for r in charger}),
            "active_row_count": len(active), "active_station_count": len(active_id),
            "active_mapped_row_count": sum(bool(r["district_name"]) for r in active),
            "active_unmatched_district_count": sum(not r["district_name"] for r in active),
            "load_candidate_operator_station_group_count": len({(r["source_station_id"], r["operator_name"])
                                                                  for r in active if r["district_name"]}),
            "deleted_count": sum(r["deleted_code"] == "Y" for r in charger),
            "duplicate_count": 0, "sha256_matches": True,
            "speed_count": dict(Counter(r["speed_code"] for r in charger)),
            "active_speed_count": dict(Counter(r["speed_code"] for r in active)),
            "unmatched_district_count": district.get("미연결", 0),
            "conflicting_station_count": len(conflict_id),
            "conflicting_station_row_count": sum(r["source_station_id"] in conflict_id for r in charger),
            "conflicting_attribute_count": {
                c: sum(len(a[c]) > 1 for a in station_attribute.values())
                for c in ("station_name", "operator_name", "address", "district_name")},
            "required_null_count": {c: sum(not r[c] for r in charger)
                                    for c in ("source_station_id", "source_charger_id", "station_key",
                                              "station_name", "operator_name", "address", "district_name")},
            "oversize_field_count": {c: sum(len(r[c]) > limit for r in charger) for c, limit in (
                ("station_name", 200), ("operator_name", 100), ("address", 500),
                ("connector_text", 120), ("capacity_text", 120),
                ("operating_time_text", 200), ("restriction_note", 500))},
            "mobile_contact_in_text_count": sum(bool(mobile_pattern.search(r[c])) for r in charger for c in text_column),
            "source_snapshot_id_blank_count": sum(not r["source_snapshot_id"] for r in charger),
            "district_count": dict(sorted(district.items())),
            "collected_at": charger_meta["collected_at"],
            "full_request_count": charger_meta["request_count"],
        },
        "overlap_estimate": {
            "old_station_count": len(old_station), "old_charger_count": len(old_charger),
            "new_scope": "deleted_code=N만 비교. 시설 후보이며 같은 기기 확인 아님",
            "name_similarity_threshold": 0.6,
            "exact_old_station_count": len(exact_old),
            "exact_old_charger_row_count": sum(r["station_key"] in exact_old for r in old_charger),
            "exact_new_station_count": len(exact_new),
            "candidate_old_station_count_including_exact": len(candidate_old),
            "candidate_old_charger_row_count": sum(r["station_key"] in candidate_old for r in old_charger),
            "candidate_new_station_count": len(candidate_new),
            "address_only_old_station_count": len(address_old),
        },
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "fetch_run_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    with (OUT / "fetch_run_district.csv").open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["district_name", "keco_charger_count", "seoul_public_charger_count"])
        writer.writerows((name, district.get(name, 0), old_district.get(name, 0))
                         for name in sorted(DISTRICT) + ["미연결"])
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
