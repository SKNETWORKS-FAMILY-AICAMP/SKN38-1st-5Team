from datetime import date, datetime
from decimal import Decimal
from numbers import Integral, Real
from typing import Sequence

import numpy as np
import pandas as pd
import streamlit as st
from sqlalchemy import bindparam, text

from db.connection import get_engine
from scoring import MODEL_VERSION, SCORE_THRESHOLD, SCORE_WEIGHT

VEHICLE = {"passenger", "bus", "truck", "special"}
SPEED = {"all", "fast", "slow", "unknown"}
DEFAULT_CHARGER_SOURCE = "keco_ev_charger"
PLACE_KIND = ("charging_station", "parking_site")
_CATEGORY_COLUMNS = {
    "district_name", "province_name", "vehicle_type_code", "vehicle_type_name",
    "fuel_scope_code", "fuel_scope_name", "usage_code", "speed_code", "kind",
    "kind_label", "parking_operation", "parking_type", "identifier_status",
    "source_code", "collection_method", "company_name", "category", "mode_code",
    "analysis_type", "need_analysis_type", "series_type", "judgment", "model_version",
    "ownership_level", "parking_level", "need_level", "day_type", "breakdown_type",
}
_FLOAT_COLUMNS = {
    "temperature_c", "rain_mm", "snow_cm", "wind_speed_ms", "capacity_kw",
    "vehicle_per_household", "electric_share_pct", "parking_per_vehicle",
    "charger_per_electric_vehicle", "vehicle_per_valid_direction", "score", "score_raw",
    "parking_space_per_vehicle", "transit_passenger_per_resident",
    "ownership_value", "parking_value", "need_value", "avg_vehicles", "seoul_avg_vehicles",
    "avg_valid_point_direction_count",
}
_INTEGER_COLUMNS = {"region_id", "company_id", "place_id", "station_id", "snapshot_id",
                    "source_snapshot_id", "parking_snapshot_id", "charger_snapshot_id",
                    "boundary_year", "hour_of_day", "coordinate_valid", "map_eligible"}


def _optimize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    for column in frame.columns:
        values = frame[column]
        if column in {"stat_month", "stat_date", "need_stat_date", "reference_start", "reference_end", "collected_on", "page_updated_on", "fetched_on"}:
            frame[column] = pd.to_datetime(values).dt.date
            continue
        coordinate = "latitude" in column or "longitude" in column
        floating = (coordinate or column in _FLOAT_COLUMNS
                    or column.endswith(("_seoul_avg", "_vs_seoul", "_percentile")))
        integer = (column in _INTEGER_COLUMNS or column.endswith(("_count", "_sum", "_rank")))
        present = values.dropna()
        numeric = not present.empty and all(isinstance(value, (Real, Decimal)) for value in present)
        if floating or numeric or integer:
            if not floating and all(Decimal(str(value)) == int(value) for value in present):
                # 큰 정수와 NULL이 섞여도 float 변환으로 정밀도를 잃지 않게 한다.
                integers = [None if pd.isna(value) else int(value) for value in values]
                low, high = (min(present), max(present)) if not present.empty else (0, 0)
                signed = low < 0 or high <= np.iinfo(np.int64).max
                prefix = "Int" if signed else "UInt"
                for bits in (8, 16, 32, 64):
                    bounds = np.iinfo(("int" if signed else "uint") + str(bits))
                    if low >= bounds.min and high <= bounds.max:
                        dtype = prefix + str(bits) if values.isna().any() or present.empty else prefix.lower() + str(bits)
                        frame[column] = pd.Series(integers, index=frame.index, dtype=dtype)
                        break
                else:
                    # BIGINT 여러 행 합계가 UInt64 범위를 넘어도 Python int로 보존한다.
                    frame[column] = pd.Series(integers, index=frame.index, dtype=object)
            else:
                floats = pd.Series([np.nan if pd.isna(value) else float(value) for value in values],
                                   index=frame.index, dtype="float64")
                smaller = floats.astype("float32")
                exact = (floats.eq(smaller.astype("float64")) | floats.isna()).all()
                frame[column] = smaller if exact and not coordinate else floats
        elif column in _CATEGORY_COLUMNS:
            frame[column] = values.astype("category")
    return frame


def _read_query(sql: str, params: dict | None = None, *, _connection=None) -> pd.DataFrame:
    statement = text(sql)
    if params is not None and "region_ids" in params:
        statement = statement.bindparams(bindparam("region_ids", expanding=True))

    def read(conn):
        result = conn.execute(statement, params or {})
        return _optimize_frame(pd.DataFrame(result.fetchall(), columns=result.keys(), dtype=object))

    if _connection is not None:
        return read(_connection)
    with get_engine().connect() as conn:
        return read(conn)


def _region_param(region_ids: Sequence[int] | None) -> dict:
    if isinstance(region_ids, (str, bytes)):
        raise ValueError("구 번호는 양의 정수 목록이어야 합니다.")
    try:
        values = [] if region_ids is None else list(region_ids)
    except TypeError:
        raise ValueError("구 번호는 양의 정수 목록이어야 합니다.") from None
    if any(isinstance(value, bool) or not isinstance(value, Integral) or value <= 0 for value in values):
        raise ValueError("구 번호는 양의 정수 목록이어야 합니다.")
    return {"all_region": int(region_ids is None), "region_ids": [int(value) for value in values]}


def _one_region(region_id, *, optional=False) -> dict:
    if region_id is None and optional:
        return _region_param(None)
    return _region_param([region_id])


def _month_value(value):
    if value is not None and (not isinstance(value, date) or isinstance(value, datetime) or value.day != 1):
        raise ValueError("기준월은 월 첫날인 date 또는 None이어야 합니다.")
    return value


def _speed_value(value):
    if not isinstance(value, str) or value not in SPEED:
        raise ValueError("충전 속도 구분이 올바르지 않습니다.")
    return value


def _limit_value(value, *, maximum=None, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0 or (maximum is not None and value > maximum):
        raise ValueError("결과 수는 허용 범위의 양의 정수여야 합니다.")
    return int(value)


def _like_pattern(keyword: str, limit: int) -> str:
    _limit_value(limit, maximum=100)
    if not isinstance(keyword, str) or len(keyword) > 500:
        raise ValueError("검색어는 500자 이내 문자열이어야 합니다.")
    return "%" + keyword.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


_SNAPSHOT_CTE = """
WITH ranked_snapshot AS (
    SELECT snapshot_id, source_code,
           ROW_NUMBER() OVER (PARTITION BY source_code ORDER BY collected_on DESC, snapshot_id DESC) AS source_rank
    FROM source_snapshot WHERE is_complete=1
), latest_snapshot AS (
    SELECT snapshot_id, source_code FROM ranked_snapshot WHERE source_rank=1
)
"""
_MONTH_CTE = """
, chosen_month AS (
    SELECT COALESCE(:stat_month, MAX(r.stat_month)) AS stat_month
    FROM registration r JOIN source_snapshot s ON s.snapshot_id=r.source_snapshot_id AND s.is_complete=1
)
"""
_PARKING_CTE = """
, parking AS (
    SELECT p.region_id, COUNT(*) AS listed_row_count,
           SUM(p.identifier_status='conflict') AS identifier_conflict_count,
           SUM(CASE WHEN p.identifier_status='unique' THEN p.space_count END) AS unique_space_count,
           SUM(p.space_count IS NULL) AS missing_space_count,
           SUM(p.identifier_status='unique' AND p.space_count IS NULL) AS unique_missing_space_count,
           SUM(p.parking_operation='공영') AS public_row_count,
           SUM(p.parking_operation='민영') AS private_row_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='공영' THEN p.space_count ELSE 0 END) AS public_known_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='민영' THEN p.space_count ELSE 0 END) AS private_known_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND COALESCE(p.parking_operation,'') NOT IN ('공영','민영') THEN p.space_count ELSE 0 END) AS other_known_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='공영' AND p.space_count IS NULL THEN 1 ELSE 0 END) AS public_missing_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='민영' AND p.space_count IS NULL THEN 1 ELSE 0 END) AS private_missing_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND COALESCE(p.parking_operation,'') NOT IN ('공영','민영') AND p.space_count IS NULL THEN 1 ELSE 0 END) AS other_missing_space_count
    FROM parking_site p JOIN latest_snapshot s ON s.snapshot_id=p.source_snapshot_id
    WHERE s.source_code='parking_standard' GROUP BY p.region_id
)
"""
_CHARGING_CTE = """
, charging AS (
    SELECT t.region_id, COUNT(*) AS listed_count, COUNT(DISTINCT t.station_id) AS listed_station_count,
           SUM(c.restriction_note IS NOT NULL) AS restriction_noted_count,
           SUM(c.restriction_note IS NULL) AS restriction_unknown_count,
           SUM(c.speed_code='fast') AS fast_count, SUM(c.speed_code='slow') AS slow_count,
           SUM(c.speed_code='unknown') AS unknown_count
    FROM charging_station t JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
    JOIN charger c ON c.station_id=t.station_id
    WHERE s.source_code=:charger_source AND (:speed_code='all' OR c.speed_code=:speed_code)
    GROUP BY t.region_id
)
"""


@st.cache_data(ttl=600, show_spinner=False)
def get_filter_options() -> dict:
    with get_engine().connect() as conn:
        def read(sql):
            return _read_query(sql, _connection=conn)

        regions = read("SELECT region_id, province_name, district_name, resident_code FROM region ORDER BY district_name")
        vehicles = read("SELECT vehicle_type_code, vehicle_type_name FROM vehicle_type ORDER BY vehicle_type_code")
        fuels = read("SELECT fuel_scope_code, fuel_scope_name FROM fuel_scope ORDER BY fuel_scope_code")
        provinces = read("""SELECT DISTINCT p.province_name FROM province_registration p
            JOIN source_snapshot s ON s.snapshot_id=p.source_snapshot_id AND s.is_complete=1 ORDER BY p.province_name""")
        usages = read("""SELECT DISTINCT p.usage_code FROM province_registration p
            JOIN source_snapshot s ON s.snapshot_id=p.source_snapshot_id AND s.is_complete=1 ORDER BY p.usage_code""")
        companies = read("""SELECT DISTINCT c.company_id, c.company_name FROM company c JOIN faq f ON f.company_id=c.company_id
            JOIN source_snapshot s ON s.snapshot_id=f.source_snapshot_id AND s.is_complete=1 ORDER BY c.company_id""")
        categories = read("""SELECT DISTINCT f.category FROM faq f JOIN source_snapshot s ON s.snapshot_id=f.source_snapshot_id
            WHERE s.is_complete=1 ORDER BY f.category""")
        months = read("""SELECT r.stat_month FROM registration r JOIN source_snapshot s ON s.snapshot_id=r.source_snapshot_id AND s.is_complete=1
            UNION SELECT p.stat_month FROM province_registration p JOIN source_snapshot s ON s.snapshot_id=p.source_snapshot_id AND s.is_complete=1
            ORDER BY stat_month DESC""")
        transit = read(_SNAPSHOT_CTE + """SELECT DISTINCT t.stat_date FROM transit_ridership_snapshot t
            JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id WHERE s.source_code='seoul_passenger' ORDER BY t.stat_date DESC""")
        analyses = read(_SNAPSHOT_CTE + """SELECT DISTINCT t.analysis_type FROM transit_ridership_snapshot t
            JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id WHERE s.source_code='seoul_passenger' ORDER BY t.analysis_type""")
        traffic = read(_SNAPSHOT_CTE + """SELECT DISTINCT DATE(t.observed_at) AS stat_date FROM traffic_snapshot t
            JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id WHERE s.source_code='seoul_traffic' ORDER BY stat_date DESC""")
        weather = read(_SNAPSHOT_CTE + """SELECT w.observed_at FROM weather_snapshot w JOIN latest_snapshot s ON s.snapshot_id=w.source_snapshot_id
            WHERE s.source_code='kma_asos_hourly' ORDER BY w.observed_at DESC""")
        snapshots = read("""SELECT snapshot_id, source_code, reference_start, reference_end, page_updated_on,
            collected_on, collection_method, coverage_note FROM source_snapshot WHERE is_complete=1 ORDER BY collected_on DESC, snapshot_id DESC""")
    return {"regions": regions, "vehicle_types": vehicles, "fuel_scopes": fuels,
            "provinces": provinces.province_name.tolist(), "usage_codes": usages.usage_code.tolist(),
            "faq_companies": companies, "faq_categories": categories.category.tolist(),
            "stat_months": months.stat_month.tolist(), "transit_dates": transit.stat_date.tolist(),
            "analysis_types": analyses.analysis_type.tolist(), "traffic_dates": traffic.stat_date.tolist(),
            "weather_observed_at": weather.observed_at.tolist(), "snapshots": snapshots}


@st.cache_data(ttl=600, show_spinner=False)
def get_parking_summary(region_ids=None) -> pd.DataFrame:
    """주차면 수 집계에서 식별번호가 충돌하는 행은 제외한다."""
    return _read_query(_SNAPSHOT_CTE + _PARKING_CTE + """
        SELECT g.region_id, g.district_name, s.snapshot_id AS source_snapshot_id,
               p.listed_row_count, p.identifier_conflict_count, p.unique_space_count,
               p.missing_space_count, p.unique_missing_space_count, p.public_row_count, p.private_row_count,
               CASE WHEN s.snapshot_id IS NOT NULL AND COALESCE(p.public_missing_space_count,0)=0 THEN COALESCE(p.public_known_space_count,0) END AS public_space_count,
               CASE WHEN s.snapshot_id IS NOT NULL AND COALESCE(p.private_missing_space_count,0)=0 THEN COALESCE(p.private_known_space_count,0) END AS private_space_count,
               CASE WHEN s.snapshot_id IS NOT NULL AND COALESCE(p.other_missing_space_count,0)=0 THEN COALESCE(p.other_known_space_count,0) END AS other_space_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(p.public_missing_space_count,0) END AS public_missing_space_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(p.private_missing_space_count,0) END AS private_missing_space_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(p.other_missing_space_count,0) END AS other_missing_space_count
        FROM region g LEFT JOIN parking p ON p.region_id=g.region_id
        LEFT JOIN latest_snapshot s ON s.source_code='parking_standard'
        WHERE (:all_region=1 OR g.region_id IN :region_ids) ORDER BY g.district_name
    """, _region_param(region_ids))


@st.cache_data(ttl=600, show_spinner=False)
def get_charger_summary(region_ids=None, speed="all") -> pd.DataFrame:
    """환경공단 자료만 집계하며 다른 출처와 합산하지 않는다."""
    return _read_query(_SNAPSHOT_CTE + _CHARGING_CTE + """
        SELECT g.region_id, g.district_name, :speed_code AS speed_code, s.snapshot_id AS source_snapshot_id,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.listed_count,0) END AS listed_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.listed_station_count,0) END AS listed_station_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.restriction_noted_count,0) END AS restriction_noted_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.restriction_unknown_count,0) END AS restriction_unknown_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.fast_count,0) END AS fast_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.slow_count,0) END AS slow_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.unknown_count,0) END AS unknown_count
        FROM region g LEFT JOIN charging c ON c.region_id=g.region_id
        LEFT JOIN latest_snapshot s ON s.source_code=:charger_source
        WHERE (:all_region=1 OR g.region_id IN :region_ids) ORDER BY g.district_name
    """, {**_region_param(region_ids), "speed_code": _speed_value(speed), "charger_source": DEFAULT_CHARGER_SOURCE})


@st.cache_data(ttl=600, show_spinner=False)
def get_region_boundaries() -> pd.DataFrame:
    """2013년 서울 25구 경계. 지도 표시 전용."""
    return _read_query(_SNAPSHOT_CTE + """
        SELECT b.region_id, g.district_name, b.geometry_json, b.centroid_latitude, b.centroid_longitude,
               b.min_latitude, b.max_latitude, b.min_longitude, b.max_longitude,
               b.boundary_year, b.ring_count, b.source_snapshot_id
        FROM region_boundary b JOIN region g ON g.region_id=b.region_id
        JOIN latest_snapshot s ON s.snapshot_id=b.source_snapshot_id
        WHERE s.source_code='kostat_seoul_boundary' ORDER BY g.district_name
    """)


@st.cache_data(ttl=600, show_spinner=False)
def get_registration_breakdown(region_id, stat_month=None) -> pd.DataFrame:
    """전기차는 전체 등록 대수에 포함되므로 두 범위를 더하지 않는다."""
    return _read_query(_SNAPSHOT_CTE + _MONTH_CTE + """
        SELECT r.region_id, g.district_name, r.stat_month, r.vehicle_type_code, v.vehicle_type_name,
               r.fuel_scope_code, f.fuel_scope_name, r.vehicle_count
        FROM registration r JOIN region g ON g.region_id=r.region_id
        JOIN source_snapshot s ON s.snapshot_id=r.source_snapshot_id AND s.is_complete=1
        JOIN vehicle_type v ON v.vehicle_type_code=r.vehicle_type_code
        JOIN fuel_scope f ON f.fuel_scope_code=r.fuel_scope_code
        JOIN chosen_month m ON m.stat_month=r.stat_month
        WHERE (:all_region=1 OR r.region_id IN :region_ids)
        ORDER BY g.district_name, r.fuel_scope_code, r.vehicle_type_code
    """, {**_one_region(region_id, optional=True), "stat_month": _month_value(stat_month)})


@st.cache_data(ttl=600, show_spinner=False)
def get_national_registrations(stat_month=None, province_name=None, vehicle_type_code=None, usage_code=None) -> pd.DataFrame:
    if vehicle_type_code is not None and vehicle_type_code not in VEHICLE:
        raise ValueError("차종이 올바르지 않습니다.")
    if usage_code is not None and usage_code not in ("official", "private", "commercial"):
        raise ValueError("용도가 올바르지 않습니다.")
    if province_name is not None and not isinstance(province_name, str):
        raise ValueError("시도명은 문자열 또는 None이어야 합니다.")
    return _read_query("""
        WITH chosen_month AS (
            SELECT COALESCE(:stat_month, MAX(p.stat_month)) AS stat_month FROM province_registration p
            JOIN source_snapshot s ON s.snapshot_id=p.source_snapshot_id AND s.is_complete=1
        )
        SELECT p.province_name, p.stat_month, p.vehicle_type_code, v.vehicle_type_name, p.usage_code, p.vehicle_count
        FROM province_registration p JOIN vehicle_type v ON v.vehicle_type_code=p.vehicle_type_code
        JOIN source_snapshot s ON s.snapshot_id=p.source_snapshot_id AND s.is_complete=1
        JOIN chosen_month m ON m.stat_month=p.stat_month
        WHERE (:province_name IS NULL OR p.province_name=:province_name)
          AND (:vehicle_type IS NULL OR p.vehicle_type_code=:vehicle_type) AND (:usage_code IS NULL OR p.usage_code=:usage_code)
        ORDER BY p.province_name, p.vehicle_type_code, p.usage_code
    """, {"stat_month": _month_value(stat_month), "province_name": province_name,
          "vehicle_type": vehicle_type_code, "usage_code": usage_code})


@st.cache_data(ttl=600, show_spinner=False)
def search_faq(keyword="", company_id=None, category=None, limit=50) -> pd.DataFrame:
    pattern = _like_pattern(keyword, limit)
    if company_id is not None:
        _one_region(company_id)
    if category is not None and not isinstance(category, str):
        raise ValueError("FAQ 분류는 문자열 또는 None이어야 합니다.")
    return _read_query("""
        SELECT c.company_id, c.company_name, f.faq_key, f.category, f.question, f.answer_text, f.source_url,
               s.collected_on AS fetched_on
        FROM faq f JOIN company c ON c.company_id=f.company_id
        JOIN source_snapshot s ON s.snapshot_id=f.source_snapshot_id AND s.is_complete=1
        WHERE (:company_id IS NULL OR c.company_id=:company_id) AND (:category IS NULL OR f.category=:category)
          AND (f.question LIKE :pattern ESCAPE '!' OR f.answer_text LIKE :pattern ESCAPE '!')
        ORDER BY c.company_id, f.faq_key LIMIT :limit
    """, {"company_id": company_id, "category": category, "pattern": pattern, "limit": int(limit)})


_METRICS_CTE = """
, car AS (
    SELECT r.region_id,
           CASE WHEN SUM(r.fuel_scope_code='all')=4 THEN SUM(CASE WHEN r.fuel_scope_code='all' THEN r.vehicle_count END) END AS vehicle_count,
           CASE WHEN SUM(r.fuel_scope_code='electric')=4 THEN SUM(CASE WHEN r.fuel_scope_code='electric' THEN r.vehicle_count END) END AS electric_count
    FROM registration r JOIN source_snapshot s ON s.snapshot_id=r.source_snapshot_id AND s.is_complete=1
    JOIN chosen_month m ON m.stat_month=r.stat_month GROUP BY r.region_id
), resident AS (
    SELECT c.region_id, c.population, c.household_count FROM region_context c
    JOIN source_snapshot s ON s.snapshot_id=c.resident_snapshot_id AND s.is_complete=1
    JOIN chosen_month m ON m.stat_month=c.stat_month
), weekday_analysis AS (
    SELECT MIN(t.analysis_type) AS analysis_type FROM transit_ridership_snapshot t
    JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id AND s.source_code='seoul_passenger'
    WHERE t.stat_date=:need_stat_date AND t.mode_code='total'
    HAVING COUNT(DISTINCT t.analysis_type)=1
), weekday_transit AS (
    SELECT t.region_id, t.analysis_type, SUM(t.known_passenger_sum) AS transit_passenger_count,
           COUNT(*) AS transit_observed_hour_count,
           COUNT(t.known_passenger_sum) AS transit_known_hour_count,
           SUM(t.valid_dong_count=v.expected_dong_count) AS transit_complete_hour_count,
           MIN(t.valid_dong_count) AS transit_min_valid_dong_count,
           MAX(v.expected_dong_count) AS transit_expected_dong_count
    FROM transit_ridership_snapshot t JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
    JOIN transit_coverage v ON v.source_snapshot_id=t.source_snapshot_id AND v.region_id=t.region_id
         AND v.stat_date=t.stat_date AND v.analysis_type=t.analysis_type
    JOIN weekday_analysis a ON a.analysis_type=t.analysis_type
    WHERE s.source_code='seoul_passenger' AND t.stat_date=:need_stat_date AND t.mode_code='total'
    GROUP BY t.region_id, t.analysis_type
), metrics AS (
    SELECT g.region_id, g.district_name, m.stat_month, c.vehicle_count, c.electric_count,
           x.population, x.household_count,
           CAST(c.vehicle_count AS DECIMAL(24,10))/NULLIF(x.household_count,0) AS vehicle_per_household,
           CASE WHEN c.electric_count<=c.vehicle_count THEN 100.0*c.electric_count/NULLIF(c.vehicle_count,0) END AS electric_share_pct,
           p.listed_row_count, p.identifier_conflict_count, p.unique_space_count,
           p.missing_space_count, p.unique_missing_space_count, p.public_row_count, p.private_row_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.listed_count,0) END AS listed_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.listed_station_count,0) END AS listed_station_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.restriction_noted_count,0) END AS restriction_noted_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.restriction_unknown_count,0) END AS restriction_unknown_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.fast_count,0) END AS fast_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.slow_count,0) END AS slow_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.unknown_count,0) END AS unknown_count,
           CASE WHEN p.unique_missing_space_count=0 THEN 1e0*p.unique_space_count/NULLIF(c.vehicle_count,0) END AS parking_per_vehicle,
           CASE WHEN c.electric_count<=c.vehicle_count AND cs.snapshot_id IS NOT NULL
                THEN 1e0*COALESCE(h.listed_count,0)/NULLIF(c.electric_count,0) END AS charger_per_electric_vehicle,
           ps.snapshot_id AS parking_snapshot_id, cs.snapshot_id AS charger_snapshot_id,
           :need_stat_date AS need_stat_date, t.analysis_type AS need_analysis_type,
           t.transit_passenger_count, t.transit_observed_hour_count, t.transit_complete_hour_count,
           t.transit_min_valid_dong_count, t.transit_expected_dong_count,
           CASE WHEN t.transit_observed_hour_count=24 AND t.transit_known_hour_count=24
                THEN CAST(t.transit_passenger_count AS DECIMAL(30,14))/NULLIF(x.population,0) END AS transit_passenger_per_resident
    FROM region g CROSS JOIN chosen_month m LEFT JOIN car c ON c.region_id=g.region_id
    LEFT JOIN resident x ON x.region_id=g.region_id LEFT JOIN parking p ON p.region_id=g.region_id
    LEFT JOIN charging h ON h.region_id=g.region_id
    LEFT JOIN latest_snapshot ps ON ps.source_code='parking_standard'
    LEFT JOIN latest_snapshot cs ON cs.source_code=:charger_source
    LEFT JOIN weekday_transit t ON t.region_id=g.region_id
)
, metric_windows AS (
    SELECT m.region_id,
           m.district_name,
           m.stat_month,
           m.vehicle_count,
           m.electric_count,
           m.population,
           m.household_count,
           m.vehicle_per_household,
           m.electric_share_pct,
           m.listed_row_count,
           m.identifier_conflict_count,
           m.unique_space_count,
           m.missing_space_count,
           m.unique_missing_space_count,
           m.public_row_count,
           m.private_row_count,
           m.listed_count,
           m.listed_station_count,
           m.restriction_noted_count,
           m.restriction_unknown_count,
           m.fast_count,
           m.slow_count,
           m.unknown_count,
           m.parking_per_vehicle,
           m.charger_per_electric_vehicle,
           m.parking_snapshot_id,
           m.charger_snapshot_id,
           m.need_stat_date,
           m.need_analysis_type,
           m.transit_passenger_count,
           m.transit_observed_hour_count,
           m.transit_complete_hour_count,
           m.transit_min_valid_dong_count,
           m.transit_expected_dong_count,
           m.transit_passenger_per_resident,
           AVG(m.vehicle_count) OVER () AS vehicle_count_seoul_avg,
           m.vehicle_count - AVG(m.vehicle_count) OVER () AS vehicle_count_vs_seoul,
           CASE WHEN m.vehicle_count IS NOT NULL THEN RANK() OVER (ORDER BY m.vehicle_count DESC) END AS vehicle_count_rank,
           COUNT(m.vehicle_count) OVER () AS vehicle_count_seoul_count,
           AVG(m.vehicle_per_household) OVER () AS vehicle_per_household_seoul_avg,
           m.vehicle_per_household - AVG(m.vehicle_per_household) OVER () AS vehicle_per_household_vs_seoul,
           CASE WHEN m.vehicle_per_household IS NOT NULL THEN RANK() OVER (ORDER BY m.vehicle_per_household DESC) END AS vehicle_per_household_rank,
           COUNT(m.vehicle_per_household) OVER () AS vehicle_per_household_seoul_count,
           AVG(m.electric_count) OVER () AS electric_count_seoul_avg,
           m.electric_count - AVG(m.electric_count) OVER () AS electric_count_vs_seoul,
           CASE WHEN m.electric_count IS NOT NULL THEN RANK() OVER (ORDER BY m.electric_count DESC) END AS electric_count_rank,
           COUNT(m.electric_count) OVER () AS electric_count_seoul_count,
           AVG(m.electric_share_pct) OVER () AS electric_share_pct_seoul_avg,
           m.electric_share_pct - AVG(m.electric_share_pct) OVER () AS electric_share_pct_vs_seoul,
           CASE WHEN m.electric_share_pct IS NOT NULL THEN RANK() OVER (ORDER BY m.electric_share_pct DESC) END AS electric_share_pct_rank,
           COUNT(m.electric_share_pct) OVER () AS electric_share_pct_seoul_count,
           AVG(m.listed_row_count) OVER () AS listed_row_count_seoul_avg,
           m.listed_row_count - AVG(m.listed_row_count) OVER () AS listed_row_count_vs_seoul,
           CASE WHEN m.listed_row_count IS NOT NULL THEN RANK() OVER (ORDER BY m.listed_row_count DESC) END AS listed_row_count_rank,
           COUNT(m.listed_row_count) OVER () AS listed_row_count_seoul_count,
           AVG(m.unique_space_count) OVER () AS unique_space_count_seoul_avg,
           m.unique_space_count - AVG(m.unique_space_count) OVER () AS unique_space_count_vs_seoul,
           CASE WHEN m.unique_space_count IS NOT NULL THEN RANK() OVER (ORDER BY m.unique_space_count DESC) END AS unique_space_count_rank,
           COUNT(m.unique_space_count) OVER () AS unique_space_count_seoul_count,
           AVG(m.listed_count) OVER () AS listed_count_seoul_avg,
           m.listed_count - AVG(m.listed_count) OVER () AS listed_count_vs_seoul,
           CASE WHEN m.listed_count IS NOT NULL THEN RANK() OVER (ORDER BY m.listed_count DESC) END AS listed_count_rank,
           COUNT(m.listed_count) OVER () AS listed_count_seoul_count,
           AVG(m.listed_station_count) OVER () AS listed_station_count_seoul_avg,
           m.listed_station_count - AVG(m.listed_station_count) OVER () AS listed_station_count_vs_seoul,
           CASE WHEN m.listed_station_count IS NOT NULL THEN RANK() OVER (ORDER BY m.listed_station_count DESC) END AS listed_station_count_rank,
           COUNT(m.listed_station_count) OVER () AS listed_station_count_seoul_count,
           AVG(m.fast_count) OVER () AS fast_count_seoul_avg,
           m.fast_count - AVG(m.fast_count) OVER () AS fast_count_vs_seoul,
           CASE WHEN m.fast_count IS NOT NULL THEN RANK() OVER (ORDER BY m.fast_count DESC) END AS fast_count_rank,
           COUNT(m.fast_count) OVER () AS fast_count_seoul_count,
           AVG(m.slow_count) OVER () AS slow_count_seoul_avg,
           m.slow_count - AVG(m.slow_count) OVER () AS slow_count_vs_seoul,
           CASE WHEN m.slow_count IS NOT NULL THEN RANK() OVER (ORDER BY m.slow_count DESC) END AS slow_count_rank,
           COUNT(m.slow_count) OVER () AS slow_count_seoul_count,
           AVG(m.parking_per_vehicle) OVER () AS parking_per_vehicle_seoul_avg,
           m.parking_per_vehicle - AVG(m.parking_per_vehicle) OVER () AS parking_per_vehicle_vs_seoul,
           CASE WHEN m.parking_per_vehicle IS NOT NULL THEN RANK() OVER (ORDER BY m.parking_per_vehicle DESC) END AS parking_per_vehicle_rank,
           COUNT(m.parking_per_vehicle) OVER () AS parking_per_vehicle_seoul_count,
           AVG(m.charger_per_electric_vehicle) OVER () AS charger_per_electric_vehicle_seoul_avg,
           m.charger_per_electric_vehicle - AVG(m.charger_per_electric_vehicle) OVER () AS charger_per_electric_vehicle_vs_seoul,
           CASE WHEN m.charger_per_electric_vehicle IS NOT NULL THEN RANK() OVER (ORDER BY m.charger_per_electric_vehicle DESC) END AS charger_per_electric_vehicle_rank,
           COUNT(m.charger_per_electric_vehicle) OVER () AS charger_per_electric_vehicle_seoul_count,
           AVG(m.transit_passenger_per_resident) OVER () AS transit_passenger_per_resident_seoul_avg,
           m.transit_passenger_per_resident - AVG(m.transit_passenger_per_resident) OVER () AS transit_passenger_per_resident_vs_seoul,
           CASE WHEN m.transit_passenger_per_resident IS NOT NULL THEN RANK() OVER (ORDER BY m.transit_passenger_per_resident DESC) END AS transit_passenger_per_resident_rank,
           COUNT(m.transit_passenger_per_resident) OVER () AS transit_passenger_per_resident_seoul_count,
           CASE WHEN COUNT(*) OVER ()=25 AND SUM(CASE WHEN m.parking_per_vehicle IS NULL OR m.charger_per_electric_vehicle IS NULL OR m.vehicle_per_household IS NULL OR m.parking_per_vehicle<0 OR m.charger_per_electric_vehicle<0 OR m.vehicle_per_household<0 THEN 1 ELSE 0 END) OVER ()=0 THEN 1 ELSE 0 END AS score_ready,
           100e0 * (RANK() OVER (ORDER BY m.parking_per_vehicle) + (COUNT(*) OVER (PARTITION BY m.parking_per_vehicle) - 1) / 2e0 - 1) / 24e0 AS parking_percentile_candidate,
           100e0 * (RANK() OVER (ORDER BY m.charger_per_electric_vehicle) + (COUNT(*) OVER (PARTITION BY m.charger_per_electric_vehicle) - 1) / 2e0 - 1) / 24e0 AS charging_percentile_candidate,
           100e0 - (100e0 * (RANK() OVER (ORDER BY m.vehicle_per_household) + (COUNT(*) OVER (PARTITION BY m.vehicle_per_household) - 1) / 2e0 - 1) / 24e0) AS registration_percentile_candidate
    FROM metrics m
)
, scored AS (
    SELECT w.region_id,
           w.district_name,
           w.stat_month,
           w.vehicle_count,
           w.electric_count,
           w.population,
           w.household_count,
           w.vehicle_per_household,
           w.electric_share_pct,
           w.listed_row_count,
           w.identifier_conflict_count,
           w.unique_space_count,
           w.missing_space_count,
           w.unique_missing_space_count,
           w.public_row_count,
           w.private_row_count,
           w.listed_count,
           w.listed_station_count,
           w.restriction_noted_count,
           w.restriction_unknown_count,
           w.fast_count,
           w.slow_count,
           w.unknown_count,
           w.parking_per_vehicle,
           w.charger_per_electric_vehicle,
           w.parking_snapshot_id,
           w.charger_snapshot_id,
           w.need_stat_date,
           w.need_analysis_type,
           w.transit_passenger_count,
           w.transit_observed_hour_count,
           w.transit_complete_hour_count,
           w.transit_min_valid_dong_count,
           w.transit_expected_dong_count,
           w.transit_passenger_per_resident,
           w.vehicle_count_seoul_avg,
           w.vehicle_count_vs_seoul,
           w.vehicle_count_rank,
           w.vehicle_count_seoul_count,
           w.vehicle_per_household_seoul_avg,
           w.vehicle_per_household_vs_seoul,
           w.vehicle_per_household_rank,
           w.vehicle_per_household_seoul_count,
           w.electric_count_seoul_avg,
           w.electric_count_vs_seoul,
           w.electric_count_rank,
           w.electric_count_seoul_count,
           w.electric_share_pct_seoul_avg,
           w.electric_share_pct_vs_seoul,
           w.electric_share_pct_rank,
           w.electric_share_pct_seoul_count,
           w.listed_row_count_seoul_avg,
           w.listed_row_count_vs_seoul,
           w.listed_row_count_rank,
           w.listed_row_count_seoul_count,
           w.unique_space_count_seoul_avg,
           w.unique_space_count_vs_seoul,
           w.unique_space_count_rank,
           w.unique_space_count_seoul_count,
           w.listed_count_seoul_avg,
           w.listed_count_vs_seoul,
           w.listed_count_rank,
           w.listed_count_seoul_count,
           w.listed_station_count_seoul_avg,
           w.listed_station_count_vs_seoul,
           w.listed_station_count_rank,
           w.listed_station_count_seoul_count,
           w.fast_count_seoul_avg,
           w.fast_count_vs_seoul,
           w.fast_count_rank,
           w.fast_count_seoul_count,
           w.slow_count_seoul_avg,
           w.slow_count_vs_seoul,
           w.slow_count_rank,
           w.slow_count_seoul_count,
           w.parking_per_vehicle_seoul_avg,
           w.parking_per_vehicle_vs_seoul,
           w.parking_per_vehicle_rank,
           w.parking_per_vehicle_seoul_count,
           w.charger_per_electric_vehicle_seoul_avg,
           w.charger_per_electric_vehicle_vs_seoul,
           w.charger_per_electric_vehicle_rank,
           w.charger_per_electric_vehicle_seoul_count,
           w.transit_passenger_per_resident_seoul_avg,
           w.transit_passenger_per_resident_vs_seoul,
           w.transit_passenger_per_resident_rank,
           w.transit_passenger_per_resident_seoul_count,
           CASE WHEN w.score_ready=1 THEN w.parking_percentile_candidate END AS parking_percentile,
           CASE WHEN w.score_ready=1 THEN w.charging_percentile_candidate END AS charging_percentile,
           CASE WHEN w.score_ready=1 THEN w.registration_percentile_candidate END AS registration_percentile,
           CASE WHEN w.score_ready=1 THEN w.parking_percentile_candidate * :parking_weight + w.charging_percentile_candidate * :charging_weight + w.registration_percentile_candidate * :registration_weight END AS score_raw
    FROM metric_windows w
)
, ranked_metrics AS (
    SELECT s.region_id,
           s.district_name,
           s.stat_month,
           s.vehicle_count,
           s.electric_count,
           s.population,
           s.household_count,
           s.vehicle_per_household,
           s.electric_share_pct,
           s.listed_row_count,
           s.identifier_conflict_count,
           s.unique_space_count,
           s.missing_space_count,
           s.unique_missing_space_count,
           s.public_row_count,
           s.private_row_count,
           s.listed_count,
           s.listed_station_count,
           s.restriction_noted_count,
           s.restriction_unknown_count,
           s.fast_count,
           s.slow_count,
           s.unknown_count,
           s.parking_per_vehicle,
           s.charger_per_electric_vehicle,
           s.parking_snapshot_id,
           s.charger_snapshot_id,
           s.need_stat_date,
           s.need_analysis_type,
           s.transit_passenger_count,
           s.transit_observed_hour_count,
           s.transit_complete_hour_count,
           s.transit_min_valid_dong_count,
           s.transit_expected_dong_count,
           s.transit_passenger_per_resident,
           s.vehicle_count_seoul_avg,
           s.vehicle_count_vs_seoul,
           s.vehicle_count_rank,
           s.vehicle_count_seoul_count,
           s.vehicle_per_household_seoul_avg,
           s.vehicle_per_household_vs_seoul,
           s.vehicle_per_household_rank,
           s.vehicle_per_household_seoul_count,
           s.electric_count_seoul_avg,
           s.electric_count_vs_seoul,
           s.electric_count_rank,
           s.electric_count_seoul_count,
           s.electric_share_pct_seoul_avg,
           s.electric_share_pct_vs_seoul,
           s.electric_share_pct_rank,
           s.electric_share_pct_seoul_count,
           s.listed_row_count_seoul_avg,
           s.listed_row_count_vs_seoul,
           s.listed_row_count_rank,
           s.listed_row_count_seoul_count,
           s.unique_space_count_seoul_avg,
           s.unique_space_count_vs_seoul,
           s.unique_space_count_rank,
           s.unique_space_count_seoul_count,
           s.listed_count_seoul_avg,
           s.listed_count_vs_seoul,
           s.listed_count_rank,
           s.listed_count_seoul_count,
           s.listed_station_count_seoul_avg,
           s.listed_station_count_vs_seoul,
           s.listed_station_count_rank,
           s.listed_station_count_seoul_count,
           s.fast_count_seoul_avg,
           s.fast_count_vs_seoul,
           s.fast_count_rank,
           s.fast_count_seoul_count,
           s.slow_count_seoul_avg,
           s.slow_count_vs_seoul,
           s.slow_count_rank,
           s.slow_count_seoul_count,
           s.parking_per_vehicle_seoul_avg,
           s.parking_per_vehicle_vs_seoul,
           s.parking_per_vehicle_rank,
           s.parking_per_vehicle_seoul_count,
           s.charger_per_electric_vehicle_seoul_avg,
           s.charger_per_electric_vehicle_vs_seoul,
           s.charger_per_electric_vehicle_rank,
           s.charger_per_electric_vehicle_seoul_count,
           s.transit_passenger_per_resident_seoul_avg,
           s.transit_passenger_per_resident_vs_seoul,
           s.transit_passenger_per_resident_rank,
           s.transit_passenger_per_resident_seoul_count,
           s.parking_percentile,
           s.charging_percentile,
           s.registration_percentile,
           s.score_raw,
           ROUND(s.score_raw,1) AS score,
           CASE WHEN s.score_raw IS NOT NULL THEN RANK() OVER (ORDER BY s.score_raw DESC) END AS score_rank,
           CASE WHEN s.score_raw IS NULL THEN '자료 부족' WHEN s.score_raw>=:recommend_threshold THEN '권장' WHEN s.score_raw>=:check_threshold THEN '조건 확인' ELSE '보류' END AS judgment,
           CASE WHEN s.score_raw IS NULL THEN '25구 공통 지표에 결측·잘못된 분모가 있어 백분위를 계산하지 않음' ELSE '수록자료에 따른 추정 참고판정. 실제 주차·충전 난도 또는 구매 필요를 확정하지 않음' END AS score_reason,
           :model_version AS model_version,
           s.parking_per_vehicle AS parking_space_per_vehicle,
           s.vehicle_per_household AS ownership_value,
           s.vehicle_per_household_rank AS ownership_rank,
           CASE WHEN s.vehicle_per_household IS NULL THEN '자료 없음' WHEN s.vehicle_per_household_rank<=8 THEN '많은 편' WHEN s.vehicle_per_household_rank<=17 THEN '보통' ELSE '적은 편' END AS ownership_level,
           s.parking_per_vehicle AS parking_value,
           s.parking_per_vehicle_rank AS parking_rank,
           CASE WHEN s.parking_per_vehicle IS NULL THEN '자료 없음' WHEN s.parking_per_vehicle_rank<=8 THEN '좋음' WHEN s.parking_per_vehicle_rank<=17 THEN '보통' ELSE '빠듯함' END AS parking_level,
           s.transit_passenger_per_resident AS need_value,
           s.transit_passenger_per_resident_rank AS need_rank,
           CASE WHEN s.transit_passenger_per_resident IS NULL THEN '자료 없음' WHEN s.transit_passenger_per_resident_rank<=8 THEN '대중교통으로 충분' WHEN s.transit_passenger_per_resident_rank<=17 THEN '있으면 편함' ELSE '차가 필요한 편' END AS need_level
    FROM scored s
)
"""

_METRICS_SELECT = """
SELECT region_id, district_name, stat_month, vehicle_count, electric_count, population, household_count, vehicle_per_household, electric_share_pct, listed_row_count, identifier_conflict_count, unique_space_count, missing_space_count, unique_missing_space_count, public_row_count, private_row_count, listed_count, listed_station_count, restriction_noted_count, restriction_unknown_count, fast_count, slow_count, unknown_count, parking_per_vehicle, charger_per_electric_vehicle, parking_snapshot_id, charger_snapshot_id, need_stat_date, need_analysis_type, transit_passenger_count, transit_observed_hour_count, transit_complete_hour_count, transit_min_valid_dong_count, transit_expected_dong_count, transit_passenger_per_resident, vehicle_count_seoul_avg, vehicle_count_vs_seoul, vehicle_count_rank, vehicle_count_seoul_count, vehicle_per_household_seoul_avg, vehicle_per_household_vs_seoul, vehicle_per_household_rank, vehicle_per_household_seoul_count, electric_count_seoul_avg, electric_count_vs_seoul, electric_count_rank, electric_count_seoul_count, electric_share_pct_seoul_avg, electric_share_pct_vs_seoul, electric_share_pct_rank, electric_share_pct_seoul_count, listed_row_count_seoul_avg, listed_row_count_vs_seoul, listed_row_count_rank, listed_row_count_seoul_count, unique_space_count_seoul_avg, unique_space_count_vs_seoul, unique_space_count_rank, unique_space_count_seoul_count, listed_count_seoul_avg, listed_count_vs_seoul, listed_count_rank, listed_count_seoul_count, listed_station_count_seoul_avg, listed_station_count_vs_seoul, listed_station_count_rank, listed_station_count_seoul_count, fast_count_seoul_avg, fast_count_vs_seoul, fast_count_rank, fast_count_seoul_count, slow_count_seoul_avg, slow_count_vs_seoul, slow_count_rank, slow_count_seoul_count, parking_per_vehicle_seoul_avg, parking_per_vehicle_vs_seoul, parking_per_vehicle_rank, parking_per_vehicle_seoul_count, charger_per_electric_vehicle_seoul_avg, charger_per_electric_vehicle_vs_seoul, charger_per_electric_vehicle_rank, charger_per_electric_vehicle_seoul_count, transit_passenger_per_resident_seoul_avg, transit_passenger_per_resident_vs_seoul, transit_passenger_per_resident_rank, transit_passenger_per_resident_seoul_count, parking_percentile, charging_percentile, registration_percentile, score_raw, score, score_rank, judgment, score_reason, model_version, parking_space_per_vehicle, ownership_value, ownership_rank, ownership_level, parking_value, parking_rank, parking_level, need_value, need_rank, need_level FROM ranked_metrics
"""


def _metrics_params(stat_month, region_ids):
    if (set(SCORE_WEIGHT) != {"parking", "charging", "registration"}
            or any(weight < 0 for weight in SCORE_WEIGHT.values())
            or not np.isclose(sum(SCORE_WEIGHT.values()), 1)):
        raise ValueError("축별 가중치는 0 이상이며 합이 1이어야 합니다.")
    return {**_region_param(region_ids), "stat_month": _month_value(stat_month),
            "speed_code": "all", "charger_source": DEFAULT_CHARGER_SOURCE,
            "need_stat_date": date(2026, 10, 30),
            "parking_weight": SCORE_WEIGHT["parking"], "charging_weight": SCORE_WEIGHT["charging"],
            "registration_weight": SCORE_WEIGHT["registration"],
            "recommend_threshold": SCORE_THRESHOLD["recommend"], "check_threshold": SCORE_THRESHOLD["check"],
            "model_version": MODEL_VERSION}


def _metrics_sql():
    return _SNAPSHOT_CTE + _MONTH_CTE + _PARKING_CTE + _CHARGING_CTE + _METRICS_CTE + _METRICS_SELECT


@st.cache_data(ttl=600, show_spinner=False)
def get_summary_metrics(region_id, stat_month=None) -> pd.DataFrame:
    _one_region(region_id)
    return _read_query(_metrics_sql() + " WHERE region_id IN :region_ids ORDER BY district_name",
                       _metrics_params(stat_month, [region_id]))


@st.cache_data(ttl=600, show_spinner=False)
def get_district_ranking(stat_month=None) -> pd.DataFrame:
    """순위는 서울 25개 구 전체를 기준으로 계산한다."""
    params = _metrics_params(stat_month, None)
    # SQL에 없는 목록 매개변수는 expanding 바인딩에서도 제외한다.
    params.pop("region_ids")
    return _read_query(_metrics_sql() + " ORDER BY district_name", params)


@st.cache_data(ttl=600, show_spinner=False)
def get_compare_metrics(region_id_a, region_id_b, stat_month=None) -> pd.DataFrame:
    """같은 구 번호를 두 번 지정하면 한 행만 반환한다."""
    _one_region(region_id_a)
    _one_region(region_id_b)
    return _read_query(_metrics_sql() + " WHERE region_id IN :region_ids ORDER BY CASE WHEN region_id=:first_region THEN 0 ELSE 1 END, district_name",
                       {**_metrics_params(stat_month, [region_id_a, region_id_b]), "first_region": int(region_id_a)})


_PLACE_CTE = """
, station AS (
          SELECT t.station_id, t.station_name, t.region_id, t.address, t.source_snapshot_id, t.operator_name FROM charging_station t JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
          WHERE s.source_code=:charger_source AND :include_charging=1
            AND (:all_region=1 OR t.region_id IN :region_ids)
        ), charging AS (
          SELECT c.station_id, COUNT(*) AS charger_count,
            SUM(c.speed_code='fast') AS fast_count, SUM(c.speed_code='slow') AS slow_count,
            SUM(c.speed_code='unknown') AS unknown_count,
            MIN(CASE WHEN c.latitude BETWEEN 37.4 AND 37.75 AND c.longitude BETWEEN 126.75 AND 127.2
                      AND NOT (c.latitude=37.5 AND c.longitude=126.8)  -- 원본의 자리표시 좌표
                     THEN c.source_charger_id END) AS coordinate_charger_id
          FROM charger c JOIN station t ON t.station_id=c.station_id
          WHERE (:speed_code='all' OR c.speed_code=:speed_code) GROUP BY c.station_id
        ), parking AS (
          SELECT p.parking_row_id, p.source_parking_no, p.region_id, p.address, p.source_snapshot_id, p.latitude, p.longitude, p.identifier_status, p.parking_operation, p.parking_type, p.space_count, CASE WHEN p.coordinate_valid=1 AND p.latitude BETWEEN 37.4 AND 37.75
                               AND p.longitude BETWEEN 126.75 AND 127.2 THEN 1 ELSE 0 END AS valid_point
          FROM parking_site p JOIN latest_snapshot s ON s.snapshot_id=p.source_snapshot_id
          WHERE s.source_code='parking_standard' AND :include_parking=1
            AND (:all_region=1 OR p.region_id IN :region_ids)
        ), place AS (
          SELECT 'charging_station' AS kind, '충전소' AS kind_label, t.station_id AS place_id,
            t.station_name AS place_name, t.station_name AS display_name,
            t.region_id, g.district_name, t.address, t.source_snapshot_id,
            c.latitude, c.longitude,
            CASE WHEN c.source_charger_id IS NOT NULL THEN 1 ELSE 0 END AS coordinate_valid,
            CASE WHEN c.source_charger_id IS NOT NULL THEN 1 ELSE 0 END AS map_eligible,
            t.operator_name, NULL AS parking_operation, NULL AS parking_type, NULL AS space_count,
            COALESCE(a.charger_count,0) AS charger_count, COALESCE(a.fast_count,0) AS fast_count,
            COALESCE(a.slow_count,0) AS slow_count, COALESCE(a.unknown_count,0) AS unknown_count,
            NULL AS identifier_status, NULL AS source_parking_no
          FROM station t JOIN region g ON g.region_id=t.region_id
          LEFT JOIN charging a ON a.station_id=t.station_id
          LEFT JOIN charger c ON c.station_id=t.station_id AND c.source_charger_id=a.coordinate_charger_id
          WHERE (:speed_code='all' OR a.charger_count>0)
          UNION ALL
          SELECT 'parking_site', '주차장', p.parking_row_id, NULL,
            CONCAT(COALESCE(p.parking_operation, '구분 미상'), ' 주차장 [', p.source_parking_no, ']'),
            p.region_id, g.district_name, p.address, p.source_snapshot_id,
            CASE WHEN p.valid_point=1 THEN p.latitude END,
            CASE WHEN p.valid_point=1 THEN p.longitude END,
            p.valid_point, CASE WHEN p.valid_point=1 AND p.identifier_status='unique' THEN 1 ELSE 0 END,
            NULL, p.parking_operation, p.parking_type, p.space_count, NULL, NULL, NULL, NULL,
            p.identifier_status, p.source_parking_no
          FROM parking p JOIN region g ON g.region_id=p.region_id
        ) """

_PLACE_SELECT = """
SELECT kind, kind_label, place_id, place_name, display_name, region_id, district_name, address, source_snapshot_id, latitude, longitude, coordinate_valid, map_eligible, operator_name, parking_operation, parking_type, space_count, charger_count, fast_count, slow_count, unknown_count, identifier_status, source_parking_no FROM place
"""


def _place_params(region_id, kinds, speed):
    if isinstance(kinds, str):
        raise ValueError("시설 종류는 목록이어야 합니다.")
    try:
        kinds = tuple(kinds)
    except TypeError:
        raise ValueError("시설 종류는 목록이어야 합니다.") from None
    if any(kind not in ("parking", "charger") for kind in kinds):
        raise ValueError("시설 종류가 올바르지 않습니다.")
    return {**_one_region(region_id, optional=True), "charger_source": DEFAULT_CHARGER_SOURCE,
            "speed_code": _speed_value(speed), "include_charging": int("charger" in kinds),
            "include_parking": int("parking" in kinds)}


@st.cache_data(ttl=600, show_spinner=False)
def get_place_points(region_id, kinds=("parking", "charger"), speed="all", limit=None) -> pd.DataFrame:
    """지도에서 제외한 시설 수는 DataFrame.attrs['coverage']에서 확인한다."""
    params = _place_params(region_id, kinds, speed)
    limit = _limit_value(limit, optional=True)
    sql = _SNAPSHOT_CTE + _PLACE_CTE + _PLACE_SELECT + " WHERE map_eligible=1 ORDER BY district_name, kind, display_name, place_id"
    if limit is not None:
        sql += " LIMIT :limit"
        params["limit"] = limit
    with get_engine().connect() as conn:
        points = _read_query(sql, params, _connection=conn)
        coverage = _read_query(_SNAPSHOT_CTE + _PLACE_CTE + """
            , requested_kind AS (
                SELECT 'charging_station' AS kind WHERE :include_charging=1
                UNION ALL SELECT 'parking_site' AS kind WHERE :include_parking=1
            )
            SELECT k.kind, COUNT(p.place_id) AS total_count,
                   COALESCE(SUM(p.map_eligible=1),0) AS point_count,
                   COALESCE(SUM(p.map_eligible=0),0) AS excluded_count,
                   COALESCE(SUM(p.coordinate_valid=0),0) AS invalid_coordinate_count,
                   COALESCE(SUM(p.coordinate_valid=1 AND p.identifier_status='conflict'),0) AS identifier_conflict_count
            FROM requested_kind k LEFT JOIN place p ON p.kind=k.kind GROUP BY k.kind ORDER BY k.kind
        """, params, _connection=conn)
    points.attrs["coverage"] = coverage.to_dict("records")
    points.attrs["returned_count"] = len(points)
    return points


@st.cache_data(ttl=600, show_spinner=False)
def search_places(keyword, region_id=None, limit=50) -> pd.DataFrame:
    """좌표가 없는 시설도 검색한다. %, _, !는 문자 그대로 찾는다."""
    params = {**_place_params(region_id, ("parking", "charger"), "all"),
              "pattern": _like_pattern(keyword, limit), "limit": int(limit)}
    return _read_query(_SNAPSHOT_CTE + _PLACE_CTE + _PLACE_SELECT + """
        WHERE (place_name LIKE :pattern ESCAPE '!' OR display_name LIKE :pattern ESCAPE '!' OR address LIKE :pattern ESCAPE '!')
        ORDER BY district_name, kind, display_name, place_id LIMIT :limit
    """, params)


@st.cache_data(ttl=600, show_spinner=False)
def get_charger_breakdown(region_id) -> pd.DataFrame:
    return _read_query(_SNAPSHOT_CTE + """
        , devices AS (
            SELECT t.station_id, t.operator_name, c.speed_code, c.connector_code,
                   c.connector_text, c.restriction_code, c.parking_free
            FROM charging_station t
            JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
            JOIN charger c ON c.station_id=t.station_id
            JOIN region g ON g.region_id=t.region_id
            WHERE s.source_code=:charger_source AND g.region_id IN :region_ids
        ), categories AS (
            SELECT 'speed' AS breakdown_type, speed_code AS category_code,
                   CASE speed_code WHEN 'fast' THEN '급속' WHEN 'slow' THEN '완속'
                        ELSE '속도 자료 없음' END AS category_label, station_id
            FROM devices
            UNION ALL
            SELECT 'operator', operator_name, operator_name, station_id FROM devices
            UNION ALL
            SELECT 'connector', COALESCE(connector_code,'unknown'),
                   COALESCE(NULLIF(TRIM(connector_text),''),
                            CONCAT('이름 자료 없음 (',connector_code,')'), '자료 없음'), station_id
            FROM devices
            UNION ALL
            SELECT 'restriction', CASE WHEN restriction_code IN ('Y','N') THEN restriction_code ELSE 'unknown' END,
                   CASE restriction_code WHEN 'Y' THEN '이용 제한 있음' WHEN 'N' THEN '제한 없음으로 수록'
                        ELSE '자료 없음' END, station_id
            FROM devices
            UNION ALL
            SELECT 'parking', CASE WHEN parking_free IN ('Y','N') THEN parking_free ELSE 'unknown' END,
                   CASE parking_free WHEN 'Y' THEN '무료로 수록' WHEN 'N' THEN '유료로 수록'
                        ELSE '자료 없음' END, station_id
            FROM devices
        ), grouped AS (
            SELECT breakdown_type, category_code, MAX(category_label) AS category_label,
                   COUNT(*) AS charger_count, COUNT(DISTINCT station_id) AS station_count
            FROM categories GROUP BY breakdown_type, category_code
        ), ordered AS (
            SELECT g.*, ROW_NUMBER() OVER (
                PARTITION BY breakdown_type ORDER BY charger_count DESC, category_code
            ) AS category_rank FROM grouped g
        ), breakdown AS (
            SELECT breakdown_type, category_code, category_label, charger_count, station_count, category_rank
            FROM ordered WHERE breakdown_type<>'operator' OR category_rank<=10
            UNION ALL
            SELECT 'operator', '__other__', '그 외 운영기관', SUM(charger_count), SUM(station_count), 11
            FROM ordered WHERE breakdown_type='operator' AND category_rank>10
            HAVING COUNT(*)>0
        )
        SELECT breakdown_type, category_code, category_label, charger_count, station_count, category_rank
        FROM breakdown
        ORDER BY CASE breakdown_type WHEN 'speed' THEN 0 WHEN 'operator' THEN 1
                 WHEN 'connector' THEN 2 WHEN 'restriction' THEN 3 ELSE 4 END, category_rank
    """, {**_one_region(region_id), "charger_source": DEFAULT_CHARGER_SOURCE})


@st.cache_data(ttl=600, show_spinner=False)
def get_charger_detail(region_id, speed="all", limit=200) -> pd.DataFrame:
    """충전기 상태는 수집 당시 값이며 실시간 빈자리가 아니다."""
    params = {**_one_region(region_id, optional=True), "charger_source": DEFAULT_CHARGER_SOURCE,
              "speed_code": _speed_value(speed)}
    limit = _limit_value(limit, optional=True)
    sql = _SNAPSHOT_CTE + """
        SELECT g.region_id, g.district_name, t.station_id, t.station_name, t.operator_name, t.address,
               t.source_snapshot_id, t.source_station_id, c.source_charger_id, c.speed_code,
               c.capacity_text, c.connector_text, c.operating_time_text, c.restriction_note,
               c.connector_code, c.capacity_kw, c.charging_method, c.restriction_code,
               c.parking_free, c.floor_type, c.floor_number, c.status_code, c.status_updated_at,
               c.latitude, c.longitude
        FROM charging_station t JOIN charger c ON c.station_id=t.station_id
        JOIN region g ON g.region_id=t.region_id JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
        WHERE s.source_code=:charger_source AND (:speed_code='all' OR c.speed_code=:speed_code)
          AND (:all_region=1 OR g.region_id IN :region_ids)
        ORDER BY g.district_name, t.station_name, c.source_charger_id, t.station_id
    """
    if limit is not None:
        sql += " LIMIT :limit"
        params["limit"] = limit
    return _read_query(sql, params)


@st.cache_data(ttl=600, show_spinner=False)
def get_traffic_profile(region_id) -> pd.DataFrame:
    """교통량 관측 지점 수는 구마다 다르다."""
    return _read_query(_SNAPSHOT_CTE + """
        , district_hour AS (
            SELECT t.region_id, HOUR(t.observed_at) AS hour_of_day,
                   CASE WHEN WEEKDAY(t.observed_at)<5 THEN '평일' ELSE '주말' END AS day_type,
                   AVG(1e0*t.known_vehicle_sum) AS avg_vehicles,
                   COUNT(*) AS observed_hour_count,
                   SUM(t.valid_point_direction_count=v.expected_point_direction_count) AS complete_hour_count,
                   MAX(v.expected_point_direction_count) AS expected_point_direction_count,
                   AVG(1e0*t.valid_point_direction_count) AS avg_valid_point_direction_count,
                   MIN(t.valid_point_direction_count) AS min_valid_point_direction_count,
                   MIN(DATE(t.observed_at)) AS reference_start,
                   MAX(DATE(t.observed_at)) AS reference_end,
                   t.source_snapshot_id
            FROM traffic_snapshot t
            JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
            JOIN traffic_coverage v ON v.source_snapshot_id=t.source_snapshot_id AND v.region_id=t.region_id
            JOIN region g ON g.region_id=t.region_id
            WHERE s.source_code='seoul_traffic'
              AND t.valid_point_direction_count>0 AND t.known_vehicle_sum IS NOT NULL
            GROUP BY t.region_id, HOUR(t.observed_at),
                     CASE WHEN WEEKDAY(t.observed_at)<5 THEN '평일' ELSE '주말' END,
                     t.source_snapshot_id
        ), city_hour AS (
            SELECT d.*,
                   AVG(d.avg_vehicles) OVER (PARTITION BY d.day_type, d.hour_of_day) AS seoul_avg_vehicles,
                   COUNT(*) OVER (PARTITION BY d.day_type, d.hour_of_day) AS seoul_region_count
            FROM district_hour d
        )
        SELECT hour_of_day, day_type, avg_vehicles, seoul_avg_vehicles,
               observed_hour_count, complete_hour_count, expected_point_direction_count,
               avg_valid_point_direction_count, min_valid_point_direction_count, seoul_region_count,
               reference_start, reference_end, source_snapshot_id
        FROM city_hour WHERE region_id IN :region_ids
        ORDER BY CASE WHEN day_type='평일' THEN 0 ELSE 1 END, hour_of_day
    """, _one_region(region_id))


@st.cache_data(ttl=600, show_spinner=False)
def get_weather(observed_at=None) -> pd.DataFrame:
    if observed_at is not None and (not isinstance(observed_at, datetime) or observed_at.tzinfo is not None
                                   or observed_at.minute or observed_at.second or observed_at.microsecond):
        raise ValueError("관측시간은 한국 시각 정시의 naive datetime 또는 None이어야 합니다.")
    return _read_query(_SNAPSHOT_CTE + """
        , chosen_time AS (
            SELECT COALESCE(:observed_at, MAX(w.observed_at)) AS observed_at
            FROM weather_snapshot w JOIN latest_snapshot s ON s.snapshot_id=w.source_snapshot_id
            WHERE s.source_code='kma_asos_hourly'
        )
        SELECT w.observed_at, w.temperature_c, w.rain_mm, w.snow_cm, w.wind_speed_ms,
               w.temperature_qc_flag, w.rain_qc_flag, w.wind_qc_flag, w.source_snapshot_id
        FROM weather_snapshot w JOIN latest_snapshot s ON s.snapshot_id=w.source_snapshot_id
        JOIN chosen_time t ON t.observed_at=w.observed_at WHERE s.source_code='kma_asos_hourly'
        ORDER BY w.observed_at
    """, {"observed_at": observed_at})


@st.cache_data(ttl=600, show_spinner=False)
def get_trend_data(region_id, stat_date=None, analysis_type=None) -> pd.DataFrame:
    """날짜를 생략하면 출처별 최신 날짜가 서로 다를 수 있다."""
    if stat_date is not None and (not isinstance(stat_date, date) or isinstance(stat_date, datetime)):
        raise ValueError("기준일은 date 또는 None이어야 합니다.")
    if analysis_type is not None and (not isinstance(analysis_type, str) or len(analysis_type)>10):
        raise ValueError("분석유형은 10자 이내 문자열 또는 None이어야 합니다.")
    return _read_query(_SNAPSHOT_CTE + """
        , transit_day AS (
            SELECT COALESCE(:stat_date, MAX(t.stat_date)) AS stat_date
            FROM transit_ridership_snapshot t JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
            WHERE s.source_code='seoul_passenger'
        ), traffic_day AS (
            SELECT COALESCE(:stat_date, DATE(MAX(t.observed_at))) AS stat_date
            FROM traffic_snapshot t JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
            WHERE s.source_code='seoul_traffic'
        ), traffic_times AS (
            SELECT DISTINCT t.observed_at, t.source_snapshot_id
            FROM traffic_snapshot t JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
            JOIN traffic_day d ON t.observed_at>=d.stat_date AND t.observed_at<DATE_ADD(d.stat_date, INTERVAL 1 DAY)
            WHERE s.source_code='seoul_traffic'
        ), trend AS (
            SELECT g.region_id, g.district_name, 'passenger' AS series_type,
                   t.stat_date, t.hour_of_day, t.mode_code, t.analysis_type, NULL AS observed_at,
                   v.expected_dong_count, t.valid_dong_count, t.known_passenger_sum,
                   CASE WHEN t.valid_dong_count=v.expected_dong_count THEN t.known_passenger_sum END AS complete_passenger_count,
                   NULL AS expected_point_direction_count, NULL AS valid_point_direction_count,
                   NULL AS known_vehicle_sum, NULL AS vehicle_per_valid_direction, t.source_snapshot_id
            FROM transit_ridership_snapshot t JOIN region g ON g.region_id=t.region_id
            JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
            JOIN transit_day d ON d.stat_date=t.stat_date
            JOIN transit_coverage v ON v.source_snapshot_id=t.source_snapshot_id AND v.region_id=t.region_id
                 AND v.stat_date=t.stat_date AND v.analysis_type=t.analysis_type
            WHERE s.source_code='seoul_passenger' AND (:all_region=1 OR g.region_id IN :region_ids)
              AND (:analysis_type IS NULL OR t.analysis_type=:analysis_type)
            UNION ALL
            SELECT g.region_id, g.district_name, 'traffic', DATE(h.observed_at), HOUR(h.observed_at),
                   'road', NULL, t.observed_at, NULL, NULL, NULL, NULL,
                   v.expected_point_direction_count, t.valid_point_direction_count,
                   t.known_vehicle_sum, t.known_vehicle_sum/NULLIF(t.valid_point_direction_count,0), h.source_snapshot_id
            FROM region g CROSS JOIN traffic_times h
            LEFT JOIN traffic_coverage v ON v.region_id=g.region_id AND v.source_snapshot_id=h.source_snapshot_id
            LEFT JOIN traffic_snapshot t ON t.region_id=g.region_id AND t.source_snapshot_id=h.source_snapshot_id AND t.observed_at=h.observed_at
            WHERE (:all_region=1 OR g.region_id IN :region_ids)
        )
        SELECT region_id, district_name, series_type, stat_date, hour_of_day, mode_code, analysis_type, observed_at,
               expected_dong_count, valid_dong_count, known_passenger_sum, complete_passenger_count,
               expected_point_direction_count, valid_point_direction_count, known_vehicle_sum,
               vehicle_per_valid_direction, source_snapshot_id
        FROM trend ORDER BY district_name, stat_date, hour_of_day, series_type, analysis_type, mode_code
    """, {**_one_region(region_id, optional=True), "stat_date": stat_date, "analysis_type": analysis_type})
