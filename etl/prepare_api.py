from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from zoneinfo import ZoneInfo

import pandas as pd

from etl.fetch_ev_chargers import COLUMN as CHARGER_COLUMN
from etl.validate_fetch_run import verify_weather

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
RAW_CHARGER = ROOT / "data/raw/api/charger_national_snapshot.csv"
SOURCE_URL = {"keco_ev_charger": "https://www.data.go.kr/data/15076352/openapi.do",
              "kma_asos_hourly": "https://www.data.go.kr/data/15057210/openapi.do"}
WEATHER_COLUMN = ("source_snapshot_id", "observed_at", "temperature_c", "rain_mm", "snow_cm",
                  "wind_speed_ms", "temperature_qc_flag", "rain_qc_flag", "wind_qc_flag")
PROFILE_COLUMN = ("speed_code", "connector_text", "capacity_text", "operating_time_text", "restriction_note",
                  "connector_code", "capacity_kw", "charging_method", "restriction_code", "parking_free",
                  "floor_type", "floor_number", "latitude", "longitude")
PACKAGE_FILE = {"charging_station_seoul.csv", "charger_national_seoul.csv", "charger_profile_seoul.csv",
                "charger_seoul_hold.csv", "charger_seoul_exclusion.csv"}


def read_csv(path):
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def station_key(source_station_id, operator_name):
    # 원문에 구분자가 있어도 키가 겹치지 않도록 배열로 직렬화한다.
    return hashlib.sha256(json.dumps(["keco_ev_charger", source_station_id, operator_name],
                                    ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def read_source(path, meta_path, code):
    meta = json.loads(meta_path.read_text())
    if (meta.get("source_code") != code or meta.get("source_url") != SOURCE_URL[code]
            or meta.get("is_complete") is not True or meta.get("smoke") is not False
            or digest(path) != meta.get("content_sha256")):
        raise ValueError("API 수집본의 출처·완결·해시 검증에 실패했습니다.")
    frame = read_csv(path)
    if len(frame) != meta.get("row_count") or len(frame) != meta.get("total_count"):
        raise ValueError("API 메타데이터와 실제 행 수가 다릅니다.")
    if code == "kma_asos_hourly":
        validate_weather(frame, meta)
    elif meta.get("province_code") != "11" or meta.get("timezone") != "Asia/Seoul":
        raise ValueError("환경공단 수집 지역·시간대가 계약과 다릅니다.")
    collected = datetime.fromisoformat(meta["collected_at"])
    if collected.tzinfo is None:
        raise ValueError("API 수집시각의 시간대가 없습니다.")
    collected = collected.astimezone(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    source = dict(source_code=code, source_url=SOURCE_URL[code], artifact_path=path.relative_to(ROOT).as_posix(),
                  content_sha256=meta["content_sha256"], reference_start=meta.get("reference_start"),
                  reference_end=meta.get("reference_end"), page_updated_on=None,
                  collected_on=collected.date().isoformat(), collected_at=collected.isoformat(sep=" "),
                  collection_method="api", is_complete=0)
    return frame, source


def validate_weather(frame, metadata=None):
    if tuple(frame.columns) != WEATHER_COLUMN or not frame.source_snapshot_id.eq("").all():
        raise ValueError("날씨 CSV 열 또는 미발급 출처 번호가 다릅니다.")
    expected = pd.date_range("2026-10-30", "2026-10-31 23:00:00", freq="h")
    actual = pd.to_datetime(frame.observed_at)
    if len(actual) != 48 or actual.duplicated().any() or set(actual) != set(expected):
        raise ValueError("날씨 48시간의 누락·중복·기간을 확인하세요.")
    contract = {"source_code": "kma_asos_hourly", "station_id": "108", "timezone": "Asia/Seoul",
                "reference_start": "2026-10-30", "reference_end": "2026-10-31",
                "expected_hour_count": 48, "missing_hour_count": 0, "is_complete": True}
    try:
        verify_weather(frame.to_dict("records"), contract if metadata is None else metadata)
    except (ArithmeticError, ValueError):
        raise ValueError("날씨 수치·품질·관측소·시간대 검산에 실패했습니다.") from None
    expected_null = {"temperature_c": 0, "rain_mm": 46, "snow_cm": 48, "wind_speed_ms": 0,
                     "temperature_qc_flag": 48, "rain_qc_flag": 31, "wind_qc_flag": 48}
    if {name: int(frame[name].eq("").sum()) for name in expected_null} != expected_null:
        raise ValueError("고정 날씨 수집본의 결측 검산이 다릅니다.")
    for value, flag in (("temperature_c", "temperature_qc_flag"), ("rain_mm", "rain_qc_flag"), ("wind_speed_ms", "wind_qc_flag")):
        if ((~frame[flag].isin(["", "0"])) & frame[value].ne("")).any():
            raise ValueError("비정상 품질 값이 숫자로 보정되었습니다.")
    return expected_null


def split_charger(raw):
    if tuple(raw.columns) != CHARGER_COLUMN or len(raw) != 76341:
        raise ValueError("환경공단 고정 수집본의 열·행 수가 다릅니다.")
    if raw.duplicated(["source_station_id", "source_charger_id"]).any():
        raise ValueError("원본 기기 식별자가 중복되었습니다.")
    if not raw.deleted_code.isin(["N", "Y"]).all() or not raw.province_code.eq("11").all():
        raise ValueError("삭제 표시 또는 서울 지역 코드가 올바르지 않습니다.")
    if set(pd.to_numeric(raw.source_row_no)) != set(range(1, 76342)):
        raise ValueError("원본 연속 행 번호가 다릅니다.")
    excluded = raw.loc[raw.deleted_code.eq("Y"), ["source_row_no", "source_station_id", "source_charger_id"]].copy()
    excluded["exclusion_reason"] = "삭제 Y"
    hold = raw.loc[raw.deleted_code.eq("N") & raw.district_name.eq("")].copy()
    active = raw.loc[raw.deleted_code.eq("N") & raw.district_name.ne("")].copy()
    region = read_csv(PROCESSED / "region.csv")
    if not active.district_name.isin(region.district_name).all():
        raise ValueError("정식 서울 구 이름과 연결되지 않습니다.")
    active["station_key"] = [station_key(s, o) for s, o in zip(active.source_station_id, active.operator_name)]
    station_column = ["station_key", "source_station_id", "district_name", "station_name", "operator_name", "address"]
    station = active[station_column].drop_duplicates().reset_index(drop=True)
    if station.station_key.duplicated().any():
        raise ValueError("같은 운영기관 충전소 안에서 이름·주소·구가 다릅니다.")
    station.insert(0, "station_row_no", range(1, len(station) + 1))
    profile = active[list(PROFILE_COLUMN)].drop_duplicates().reset_index(drop=True)
    profile.insert(0, "profile_no", range(1, len(profile) + 1))
    charger = active.merge(station[["station_key", "station_row_no"]], on="station_key", validate="many_to_one")
    charger = charger.merge(profile, on=list(PROFILE_COLUMN), validate="many_to_one")
    charger = charger[["source_row_no", "station_row_no", "source_charger_id", "profile_no", "status_code", "status_updated_at"]]
    if (len(excluded), len(hold), len(active), len(station)) != (709, 25, 75607, 13098):
        raise ValueError("환경공단 제외·보류·적재 건수가 확정 수집본과 다릅니다.")
    if active.speed_code.value_counts().to_dict() != {"slow": 69634, "fast": 5041, "unknown": 932}:
        raise ValueError("환경공단 적재 대상의 속도 검산이 다릅니다.")
    return {"charging_station_seoul.csv": station, "charger_national_seoul.csv": charger,
            "charger_profile_seoul.csv": profile, "charger_seoul_hold.csv": hold, "charger_seoul_exclusion.csv": excluded}


def prepare_api():
    original = PROCESSED / "charger_national_snapshot.csv"
    source_path = original if original.exists() else RAW_CHARGER
    raw, _ = read_source(source_path, PROCESSED / "charger_national_snapshot.meta.json", "keco_ev_charger")
    weather, _ = read_source(PROCESSED / "weather_snapshot.csv", PROCESSED / "weather_snapshot.meta.json", "kma_asos_hourly")
    weather_null = validate_weather(weather)
    package = split_charger(raw)
    with tempfile.TemporaryDirectory(dir=PROCESSED, prefix=".api_stage_") as directory:
        stage = Path(directory)
        for name, frame in package.items():
            frame.to_csv(stage / name, index=False, encoding="utf-8-sig")
        if (stage / "charger_national_seoul.csv").stat().st_size > 5_000_000:
            raise ValueError("충전기 경량 CSV가 5MB를 초과합니다.")
        RAW_CHARGER.parent.mkdir(parents=True, exist_ok=True)
        if original.exists():
            if RAW_CHARGER.exists() and digest(RAW_CHARGER) != digest(original):
                raise ValueError("보관된 원본과 새 원본이 다릅니다. 새 수집본 경로를 분리하세요.")
            if not RAW_CHARGER.exists():
                shutil.copyfile(original, RAW_CHARGER)
        record = {"passed": True, "published": True, "raw_sha256": digest(RAW_CHARGER),
                  "weather_sha256": digest(PROCESSED / "weather_snapshot.csv"), "weather_null_count": weather_null,
                  "output_sha256": {name: digest(stage / name) for name in package},
                  "row_count": {name: len(frame) for name, frame in package.items()},
                  "byte_count": {name: (stage / name).stat().st_size for name in package}}
        for name in package:
            (stage / name).replace(PROCESSED / name)
        (stage / "api_validation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        (stage / "api_validation.json").replace(PROCESSED / "api_validation.json")
        if original.exists():
            original.unlink()
    return record


def read_api_package():
    record = json.loads((PROCESSED / "api_validation.json").read_text())
    if record.get("passed") is not True or record.get("published") is not True or set(record.get("output_sha256", {})) != PACKAGE_FILE:
        raise ValueError("API 경량본의 전체 검산 기록이 없습니다.")
    for name, checksum in record["output_sha256"].items():
        if digest(PROCESSED / name) != checksum:
            raise ValueError("API 경량본이 검산 이후 변경되었습니다.")
    raw, charger_source = read_source(RAW_CHARGER, PROCESSED / "charger_national_snapshot.meta.json", "keco_ev_charger")
    weather, weather_source = read_source(PROCESSED / "weather_snapshot.csv", PROCESSED / "weather_snapshot.meta.json", "kma_asos_hourly")
    if record["raw_sha256"] != digest(RAW_CHARGER) or record["weather_sha256"] != digest(PROCESSED / "weather_snapshot.csv"):
        raise ValueError("원본과 경량본의 검산 시점이 다릅니다.")
    validate_weather(weather)
    # 충전 목록에는 과거 관측 기간이 제공되지 않는다.
    if weather_source["reference_start"] != "2026-10-30" or weather_source["reference_end"] != "2026-10-31":
        raise ValueError("날씨 메타데이터의 기준 기간이 다릅니다.")
    if charger_source["reference_start"] is not None or charger_source["reference_end"] is not None:
        raise ValueError("충전 목록에는 과거 관측 기간이 제공되지 않았습니다.")
    charger_source["coverage_note"] = "서울 API 전수 수신 76341행. 삭제 Y 709 제외, 구 미연결 25 CSV 보류, 적재 75607기기·13098 운영기관 충전소. 속도는 커넥터 기반 추정, 미상 932. 같은 장소의 기존 서울 목록과 합산 금지. 상태는 수집 당시 코드이며 빈자리 아님."
    weather_source["coverage_note"] = "서울 ASOS108 공통 48시간, 누락시간 0. 강수 NULL46·적설 NULL48, 강수 품질9 17행·미상31행, 기온·풍속 품질 미상48행. 결측을 0으로 채우지 않음. 구별 실측이 아님."
    station = read_csv(PROCESSED / "charging_station_seoul.csv")
    charger = read_csv(PROCESSED / "charger_national_seoul.csv")
    profile = read_csv(PROCESSED / "charger_profile_seoul.csv")
    charger = charger.merge(profile, on="profile_no", validate="many_to_one")
    if len(charger) != 75607 or len(station) != 13098 or charger.duplicated(["station_row_no", "source_charger_id"]).any():
        raise ValueError("경량 충전 목록의 행 수·기기 식별자가 다릅니다.")
    return [charger_source, weather_source], station.replace("", None), charger.replace("", None), weather.replace("", None)


def main():
    try:
        record = prepare_api()
        print("API 경량 정제 완료:", json.dumps(record["row_count"], ensure_ascii=False))
        return 0
    except Exception as exc:
        print("API 경량 정제 실패:", type(exc).__name__, "출처·고정 수집본·검산 기록을 확인하세요.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
