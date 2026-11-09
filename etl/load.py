"""검산 완료 CSV를 한 트랜잭션으로 적재한다. 동일 키는 갱신한다."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import Date, DateTime, MetaData, delete, func, select, text, update
from sqlalchemy.dialects.mysql import insert

from db.connection import get_engine
from etl.prepare_api import read_api_package, WEATHER_COLUMN, PROFILE_COLUMN
from etl.prepare_boundary import read_boundary_package, SOURCE_CODE as BOUNDARY_SOURCE

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
BATCH_SIZE = 1000

TABLE_NAME = {name: name for name in (
    "source_snapshot", "region", "vehicle_type", "fuel_scope", "company",
    "province_registration", "registration", "region_context", "parking_site",
    "charging_station", "charger", "faq", "traffic_coverage", "traffic_snapshot",
    "transit_coverage", "transit_ridership_snapshot", "weather_snapshot",
    "region_boundary",
)}
COLUMN_MAP = {
    "region": {column: column for column in ("resident_code", "province_name", "district_name")},
    "province_registration": {column: column for column in ("province_name", "stat_month", "vehicle_type_code", "usage_code", "vehicle_count")},
    "registration": {column: column for column in ("stat_month", "vehicle_type_code", "fuel_scope_code", "vehicle_count")},
    "region_context": {column: column for column in ("stat_month", "population", "household_count")},
    "parking_site": {column: column for column in ("source_row_no", "institution_code", "source_parking_no", "parking_operation", "parking_type", "address", "space_count", "latitude", "longitude", "reference_date", "identifier_status", "coordinate_valid")},
    "charging_station": {column: column for column in ("station_key", "operator_name", "station_name", "address")},
    "charger": {column: column for column in ("source_charger_id", "source_row_no", "speed_code", "connector_text", "capacity_text", "operating_time_text", "restriction_note", "source_x", "source_y")},
    "faq": {column: column for column in ("faq_key", "category", "question", "answer_text", "source_url")},
    "traffic_coverage": {"expected_point_direction_count": "expected_point_direction_count"},
    "traffic_snapshot": {column: column for column in ("observed_at", "valid_point_direction_count", "known_vehicle_sum")},
    "transit_coverage": {column: column for column in ("stat_date", "analysis_type", "expected_dong_count")},
    "transit_ridership_snapshot": {column: column for column in ("stat_date", "analysis_type", "hour_of_day", "mode_code", "valid_dong_count", "known_passenger_sum")},
}
COLUMN_MAP["weather_snapshot"] = {name: name for name in WEATHER_COLUMN if name != "source_snapshot_id"}
API_COLUMN_MAP = {
    "charging_station": {name: name for name in ("station_key", "source_station_id", "station_name", "operator_name", "address")},
    "charger": {name: name for name in (*PROFILE_COLUMN, "source_row_no", "source_charger_id", "status_code", "status_updated_at")},
}
BASE_CSV = {name + ".csv" for name in (
    "region", "province_registration", "registration", "registration_fuel", "registration_usage",
    "registration_national_audit", "registration_total_audit", "region_context", "parking_site",
    "parking_exclusion", "charging_station", "charger", "charger_exclusion", "faq")}
SOURCE_FOR_TABLE = {
    "province_registration": "molit_registration", "region_context": "resident_population",
    "parking_site": "parking_standard", "charging_station": "seoul_charger", "faq": "hyundai_ev_faq",
    "traffic_coverage": "seoul_traffic", "traffic_snapshot": "seoul_traffic",
    "transit_coverage": "seoul_passenger", "transit_ridership_snapshot": "seoul_passenger",
}
TIME_TABLE = {"traffic_coverage", "traffic_snapshot", "transit_coverage", "transit_ridership_snapshot"}


class LoadReportError(RuntimeError):
    """DB 커밋 뒤 검산 보고서 저장만 실패한 상태."""


def read_frame(path: Path) -> pd.DataFrame:
    # 식별번호의 선행 0을 보존하기 위해 문자열로 읽는다.
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    return frame.replace("", None)


def verify_file(item: dict) -> None:
    path = (ROOT / item["artifact_path"]).resolve()
    if not path.is_relative_to(ROOT / "data/raw"):
        raise ValueError("원본 경로는 프로젝트 data/raw 안이어야 합니다.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != item["content_sha256"]:
        raise ValueError("원본 해시가 정제 수집본과 다릅니다.")


def source_record(folder: Path) -> list[dict]:
    validation = json.loads((folder / "validation.json").read_text())
    if validation.get("passed") is not True or validation.get("published") is not True:
        raise ValueError("정제 검산과 게시가 완료되지 않았습니다.")
    expected_file = {name + ".csv" for name in TIME_TABLE} if folder.name == "snapshot" else BASE_CSV
    if set(validation.get("output_sha256", {})) != expected_file:
        raise ValueError("CSV 해시 기록이 없습니다. 정제를 다시 실행하세요.")
    for name, digest in validation["output_sha256"].items():
        path = (folder / name).resolve()
        if path.parent != folder.resolve() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("정제 CSV가 검산 후 변경되었습니다.")
    manifest = json.loads((folder / "source_manifest.json").read_text())["source"]
    records, parking = [], []
    for item in manifest:
        verify_file(item)
        code = item["source_code"]
        if code == "resident_join" or item["artifact_path"].endswith("parking_page0.json"):
            continue
        if code == "national_parking":
            parking.append(item)
            continue
        record = {key: item.get(key) for key in ("source_code", "source_url", "artifact_path", "content_sha256", "reference_start", "reference_end")}
        record.update(collected_on=item.get("collected_on", item.get("fetched_on")), collected_at=None,
                      page_updated_on="2026-09-30" if code == "seoul_charger" else None,
                      collection_method=item.get("collection_method", "api" if code == "seoul_charger" else "crawl" if code == "hyundai_ev_faq" else "file"),
                      is_complete=0, coverage_note=item.get("coverage_note", "검산된 고정 수집본. 등록·인구는 2026년 9월, 충전 목록의 행별 기준일과 제한 여부는 미상일 수 있음."))
        records.append(record)
    if parking:
        pair = sorted((item["artifact_path"], item["content_sha256"]) for item in parking)
        records.append({"source_code": "parking_standard", "source_url": parking[0]["source_url"],
                        "artifact_path": (folder / "source_manifest.json").relative_to(ROOT).as_posix(), "content_sha256": hashlib.sha256(json.dumps(pair, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
                        "reference_start": "2026-04-08", "reference_end": "2026-10-30", "page_updated_on": None,
                        "collected_on": parking[0]["fetched_on"], "collected_at": None, "collection_method": "file", "is_complete": 0,
                        "coverage_note": "전국 표준주차 page1·2 묶음 중 서울 857관측행. 식별번호 충돌 22행 보존, 비충돌 수록 면수만 합산. 전체 공급 아님."})
    return records


def upsert_frame(conn, table, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    if not set(frame.columns).issubset(table.c.keys()):
        raise ValueError("CSV 매핑과 실제 DDL 컬럼이 다릅니다.")
    frame = frame.copy()
    for column in frame:
        if isinstance(table.c[column].type, DateTime):
            frame[column] = pd.to_datetime(frame[column]).map(lambda value: value.to_pydatetime() if pd.notna(value) else None)
        elif isinstance(table.c[column].type, Date):
            frame[column] = pd.to_datetime(frame[column]).dt.date
    rows = frame.astype(object).where(pd.notna(frame), None).to_dict("records")
    statement = insert(table)
    update_column = {name: statement.inserted[name] for name in frame if not table.c[name].primary_key}
    if not update_column:
        name = next(iter(frame.columns))
        update_column = {name: statement.inserted[name]}
    statement = statement.on_duplicate_key_update(**update_column)
    for offset in range(0, len(rows), BATCH_SIZE):
        conn.execute(statement, rows[offset:offset + BATCH_SIZE])


def verify_total(conn, snapshot_id: dict) -> dict:
    # 출처가 다른 충전 목록에는 같은 시설이 겹칠 수 있어 따로 집계한다.
    row = conn.execute(text("""
        SELECT (SELECT SUM(vehicle_count) FROM province_registration) AS national_vehicle_count,
          (SELECT SUM(vehicle_count) FROM registration WHERE fuel_scope_code='all') AS seoul_vehicle_count,
          (SELECT SUM(vehicle_count) FROM registration WHERE fuel_scope_code='electric') AS electric_count,
          (SELECT COUNT(*) FROM region) AS region_count,
          (SELECT COUNT(*) FROM parking_site) AS parking_count,
          (SELECT COUNT(*) FROM faq) AS faq_count
    """)).mappings().one()
    actual = {key: int(value or 0) for key, value in row.items()}
    expected = dict(national_vehicle_count=26706123, seoul_vehicle_count=3150351, electric_count=127750,
                    region_count=25, parking_count=857, faq_count=10)
    if actual != expected:
        raise ValueError("DB 기본 자료 검산 결과가 고정 수집본 기대값과 다릅니다.")
    source_expected = {"seoul_charger": (187, 429, 356, 73, 0), "keco_ev_charger": (13098, 75607, 5041, 69634, 932)}
    by_source = {}
    for code, expected_value in source_expected.items():
        if code not in snapshot_id:
            continue
        row = conn.execute(text("""
            SELECT COUNT(DISTINCT t.station_id) AS station_count, COUNT(*) AS charger_count,
              SUM(c.speed_code='fast') AS fast_count, SUM(c.speed_code='slow') AS slow_count,
              SUM(c.speed_code='unknown') AS unknown_count
            FROM charging_station t JOIN charger c ON c.station_id=t.station_id
            WHERE t.source_snapshot_id=:snapshot_id
        """), {"snapshot_id": snapshot_id[code]}).mappings().one()
        values = {name: int(value or 0) for name, value in row.items()}
        if tuple(values.values()) != expected_value:
            raise ValueError("충전 목록의 출처별 검산이 다릅니다.")
        by_source[code] = values
    actual["charger_by_source"] = by_source
    if "kma_asos_hourly" in snapshot_id:
        row = conn.execute(text("""
            SELECT COUNT(*) AS row_count, COUNT(DISTINCT observed_at) AS hour_count,
              MIN(observed_at) AS start_at, MAX(observed_at) AS end_at,
              SUM(temperature_c IS NULL) AS temperature_null, SUM(rain_mm IS NULL) AS rain_null,
              SUM(snow_cm IS NULL) AS snow_null, SUM(wind_speed_ms IS NULL) AS wind_null,
              SUM(temperature_qc_flag IS NULL) AS temperature_qc_null,
              SUM(rain_qc_flag IS NULL) AS rain_qc_null, SUM(rain_qc_flag='9') AS rain_qc_9,
              SUM(wind_qc_flag IS NULL) AS wind_qc_null
            FROM weather_snapshot WHERE source_snapshot_id=:snapshot_id
        """), {"snapshot_id": snapshot_id["kma_asos_hourly"]}).mappings().one()
        counts = {name: int(value or 0) for name, value in row.items() if name not in ("start_at", "end_at")}
        if (tuple(counts.values()) != (48, 48, 0, 46, 48, 0, 48, 31, 17, 48)
                or str(row["start_at"]) != "2026-10-30 00:00:00" or str(row["end_at"]) != "2026-10-31 23:00:00"):
            raise ValueError("날씨 시간·결측·품질 검산이 다릅니다.")
        actual["weather"] = counts
    if BOUNDARY_SOURCE in snapshot_id:
        row = conn.execute(text("""
            SELECT COUNT(*) AS row_count, SUM(JSON_TYPE(geometry_json)='OBJECT') AS geometry_count,
                   MIN(boundary_year) AS min_year, MAX(boundary_year) AS max_year
            FROM region_boundary WHERE source_snapshot_id=:snapshot_id
        """), {"snapshot_id": snapshot_id[BOUNDARY_SOURCE]}).one()
        if tuple(row) != (25, 25, 2013, 2013):
            raise ValueError("서울 25구 경계의 행 수·도형·연도 검산이 다릅니다.")
        actual["region_boundary_count"] = int(row.row_count)
    return actual


def load_api_frame(conn, tables, snapshot_id, district_id, package):
    _, station, charger, weather = package
    frame = pd.DataFrame({target: station[source] for target, source in API_COLUMN_MAP["charging_station"].items()})
    frame["region_id"] = station.district_name.map(district_id)
    frame["source_snapshot_id"] = snapshot_id["keco_ev_charger"]
    if frame.region_id.isna().any():
        raise ValueError("환경공단 부모의 구 연결이 누락되었습니다.")
    upsert_frame(conn, tables["charging_station"], frame)
    table = tables["charging_station"]
    parent = pd.read_sql(select(table.c.station_id, table.c.station_key).where(
        table.c.source_snapshot_id == snapshot_id["keco_ev_charger"]), conn)
    station["station_id"] = station.station_key.map(parent.set_index("station_key").station_id)
    frame = pd.DataFrame({target: charger[source] for target, source in API_COLUMN_MAP["charger"].items()})
    frame["station_id"] = charger.station_row_no.map(station.set_index("station_row_no").station_id)
    if frame.station_id.isna().any():
        raise ValueError("환경공단 부모·자식 연결이 누락되었습니다.")
    upsert_frame(conn, tables["charger"], frame)
    frame = pd.DataFrame({target: weather[source] for target, source in COLUMN_MAP["weather_snapshot"].items()})
    frame["source_snapshot_id"] = snapshot_id["kma_asos_hourly"]
    upsert_frame(conn, tables["weather_snapshot"], frame)


def load_boundary_frame(conn, tables, snapshot_id: int, raw: pd.DataFrame) -> None:
    region = pd.read_sql(select(tables["region"].c.region_id, tables["region"].c.district_name), conn)
    district_id = region.set_index("district_name").region_id.to_dict()
    if set(raw.district_name) != set(district_id) or len(district_id) != 25:
        raise ValueError("경계와 실제 DB의 서울 25구가 일치하지 않습니다.")
    frame = raw.drop(columns="district_name").copy()
    frame["region_id"] = raw.district_name.map(district_id)
    frame["geometry_json"] = frame.geometry_json.map(json.loads)
    frame["source_snapshot_id"] = snapshot_id
    upsert_frame(conn, tables["region_boundary"], frame)


def load_boundary_data(engine, report_dir: Path | None = None) -> dict:
    source, frame = read_boundary_package(PROCESSED)
    metadata = MetaData()
    metadata.reflect(bind=engine, only=["source_snapshot", "region", "region_boundary"])
    tables = metadata.tables
    with engine.begin() as conn:
        table = tables["source_snapshot"]
        upsert_frame(conn, table, pd.DataFrame([source]))
        snapshot_id = conn.execute(select(table.c.snapshot_id).where(
            table.c.source_code == BOUNDARY_SOURCE, table.c.content_sha256 == source["content_sha256"]
        )).scalar_one()
        load_boundary_frame(conn, tables, snapshot_id, frame)
        totals = verify_total(conn, {BOUNDARY_SOURCE: snapshot_id})
        conn.execute(update(table).where(table.c.snapshot_id == snapshot_id).values(is_complete=1))
    result = {"passed": True, "boundary_only": True, "snapshot_id": {BOUNDARY_SOURCE: snapshot_id}, "total": totals}
    save_load_report(result, report_dir)
    return result


def load_data(engine, truncate: bool = False, report_dir: Path | None = None) -> dict:
    metadata = MetaData()
    metadata.reflect(bind=engine)
    tables = {name: metadata.tables[physical] for name, physical in TABLE_NAME.items() if physical in metadata.tables}
    if not (set(TABLE_NAME) - TIME_TABLE - {"weather_snapshot", "region_boundary"}).issubset(tables):
        raise ValueError("ERD 3차 핵심 테이블을 먼저 적용하세요.")
    sources = source_record(PROCESSED)
    snapshot_folder = PROCESSED / "snapshot"
    snapshot_present = any((snapshot_folder / (name + ".csv")).exists() for name in TIME_TABLE) or (snapshot_folder / "validation.json").exists()
    if snapshot_present and not TIME_TABLE.issubset(tables):
        raise ValueError("시간 수집본을 적재할 확장 테이블이 없습니다.")
    use_snapshot = snapshot_present
    if use_snapshot:
        sources += source_record(snapshot_folder)
    api_present = (PROCESSED / "weather_snapshot.csv").exists() or (PROCESSED / "api_validation.json").exists()
    package = None
    if api_present:
        if "weather_snapshot" not in tables or not set(API_COLUMN_MAP["charger"]).issubset(tables["charger"].c.keys()):
            raise ValueError("날씨·환경공단 확장 DDL을 먼저 적용하세요.")
        package = read_api_package()
        sources += package[0]
    boundary_present = (PROCESSED / "region_boundary.csv").exists() or (PROCESSED / "boundary_validation.json").exists()
    boundary = None
    if boundary_present:
        if "region_boundary" not in tables:
            raise ValueError("구 경계 DDL을 먼저 적용하세요.")
        boundary_source, boundary = read_boundary_package(PROCESSED)
        sources.append(boundary_source)
    with engine.begin() as conn:
        if truncate:
            # 전체 삭제도 롤백할 수 있도록 DELETE를 쓴다.
            for table in reversed(metadata.sorted_tables):
                conn.execute(delete(table))
        upsert_frame(conn, tables["source_snapshot"], pd.DataFrame(sources))
        snapshot_id = {}
        for source in sources:
            table = tables["source_snapshot"]
            snapshot_id[source["source_code"]] = conn.execute(select(table.c.snapshot_id).where(
                table.c.source_code == source["source_code"], table.c.content_sha256 == source["content_sha256"]
            )).scalar_one()
        upsert_frame(conn, tables["region"], read_frame(PROCESSED / "region.csv"))
        upsert_frame(conn, tables["vehicle_type"], pd.DataFrame({"vehicle_type_code": ["passenger", "bus", "truck", "special"], "vehicle_type_name": ["승용", "승합", "화물", "특수"]}))
        upsert_frame(conn, tables["fuel_scope"], pd.DataFrame({"fuel_scope_code": ["all", "electric"], "fuel_scope_name": ["전체", "전기"]}))
        upsert_frame(conn, tables["company"], pd.DataFrame([{"company_name": "현대자동차", "website_url": "https://www.hyundai.com/kr/ko"}]))
        region = pd.read_sql(select(tables["region"]), conn)
        region_id = region.set_index("resident_code").region_id.to_dict()
        district_id = region.set_index("district_name").region_id.to_dict()
        company_id = conn.execute(select(tables["company"].c.company_id).where(tables["company"].c.company_name == "현대자동차")).scalar_one()
        order = ["province_registration", "registration", "region_context", "parking_site", "charging_station", "charger", "faq"]
        if use_snapshot:
            order += ["traffic_coverage", "traffic_snapshot", "transit_coverage", "transit_ridership_snapshot"]
        station_id = {}
        for name in order:
            folder = snapshot_folder if name.startswith(("traffic_", "transit_")) else PROCESSED
            raw = read_frame(folder / (name + ".csv"))
            frame = pd.DataFrame({target: raw[source] for target, source in COLUMN_MAP[name].items()})
            if "resident_code" in raw:
                frame["region_id"] = raw.resident_code.map(region_id)
            elif "district_name" in raw:
                frame["region_id"] = raw.district_name.map(district_id)
            if "region_id" in frame and frame.region_id.isna().any():
                raise ValueError("서울 구 연결에 실패한 적재 행이 있습니다.")
            if name == "registration":
                frame["source_snapshot_id"] = raw.source_code.map(snapshot_id)
            elif name == "region_context":
                frame["resident_snapshot_id"] = snapshot_id["resident_population"]
            elif name in SOURCE_FOR_TABLE:
                frame["source_snapshot_id"] = snapshot_id[SOURCE_FOR_TABLE[name]]
            if name == "charger":
                frame = frame.drop(columns="region_id")
                frame["station_id"] = raw.station_key.map(station_id)
                if frame.station_id.isna().any():
                    raise ValueError("충전소와 기기 연결에 실패했습니다.")
            if name == "faq":
                frame["company_id"] = company_id
            upsert_frame(conn, tables[name], frame)
            if name == "charging_station":
                table = tables[name]
                station = pd.read_sql(select(table.c.station_id, table.c.station_key).where(table.c.source_snapshot_id == snapshot_id["seoul_charger"]), conn)
                station_id = station.set_index("station_key").station_id.to_dict()
        if package is not None:
            load_api_frame(conn, tables, snapshot_id, district_id, package)
        if boundary is not None:
            load_boundary_frame(conn, tables, snapshot_id[BOUNDARY_SOURCE], boundary)
        totals = verify_total(conn, snapshot_id)
        table = tables["source_snapshot"]
        conn.execute(update(table).where(table.c.snapshot_id.in_(list(snapshot_id.values()))).values(is_complete=1))
        counts = {table.name: conn.execute(select(func.count()).select_from(table)).scalar_one() for table in metadata.sorted_tables}
    result = {"passed": True, "table_row_count": counts, "total": totals, "snapshot_id": snapshot_id,
              "time_snapshot_loaded": use_snapshot, "api_snapshot_loaded": api_present,
              "boundary_snapshot_loaded": boundary_present, "truncate": truncate}
    save_load_report(result, report_dir)
    return result


def save_load_report(result: dict, report_dir: Path | None = None) -> None:
    try:
        output_dir = Path(report_dir) if report_dir is not None else Path(os.getenv("DB_REPORT_DIR", ROOT / "docs"))
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "load_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except OSError:
        raise LoadReportError("DB 커밋은 완료됐지만 검산 보고서를 저장하지 못했습니다.") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truncate", action="store_true")
    parser.add_argument("--boundary-only", action="store_true", help="기존 자료를 유지하고 구 경계만 추가·갱신")
    parser.add_argument("--report-dir", type=Path, help="검사 결과 위치. 기본 DB_REPORT_DIR 또는 docs")
    args = parser.parse_args()
    if args.boundary_only and args.truncate:
        parser.error("--boundary-only와 --truncate는 함께 사용할 수 없습니다.")
    engine = None
    try:
        engine = get_engine()
        result = load_boundary_data(engine, args.report_dir) if args.boundary_only else load_data(engine, args.truncate, args.report_dir)
        print("적재 완료:", json.dumps(result["total"], ensure_ascii=False))
        return 0
    except LoadReportError:
        print("DB 적재·검산은 커밋되었습니다. 검산 보고서 저장에 실패했습니다. 결과 저장 경로와 쓰기 권한을 확인하세요.")
        return 1
    except Exception as exc:
        print("적재 처리 실패:", type(exc).__name__, "CSV·DDL 매핑과 DB 상태를 확인하세요.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
