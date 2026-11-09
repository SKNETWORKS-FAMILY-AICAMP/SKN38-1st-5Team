from datetime import date, datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import text

from db.connection import get_engine
from db import queries as q
from tests.query_support import query_overlay
from etl.load import source_record, load_data
from etl.prepare_api import read_csv, read_source, validate_weather, station_key, read_api_package, PROCESSED
from scoring import compute_score


class ApiPackageTest(unittest.TestCase):
    def test_operator_is_part_of_parent_key(self):
        self.assertNotEqual(station_key("01", "기관A"), station_key("01", "기관B"))
        self.assertNotEqual(station_key("a|b", "c"), station_key("a", "b|c"))
        self.assertEqual(station_key("01", "기관A"), station_key("01", "기관A"))

    def test_partial_csv_hash_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "snapshot"
            folder.mkdir()
            (folder / "validation.json").write_text(json.dumps({"passed": True, "published": True, "output_sha256": {"traffic_coverage.csv": "missing"}}))
            with self.assertRaises(ValueError):
                source_record(folder)

    def test_string_false_is_not_validation_success(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "validation.json").write_text(json.dumps({"passed": "false", "published": True}))
            with self.assertRaises(ValueError):
                source_record(folder)

    def test_weather_missing_hour_or_filled_null_is_rejected(self):
        weather = read_csv(PROCESSED / "weather_snapshot.csv")
        self.assertEqual(validate_weather(weather)["rain_mm"], 46)
        with self.assertRaises(ValueError):
            validate_weather(weather.iloc[:-1])
        changed = weather.copy()
        changed.loc[changed.rain_mm.eq(""), "rain_mm"] = "0"
        with self.assertRaises(ValueError):
            validate_weather(changed)

    def test_lightweight_join_and_unassigned_id(self):
        source, station, charger, weather = read_api_package()
        self.assertEqual((len(station), len(charger), len(weather)), (13098, 75607, 48))
        self.assertTrue(charger.station_row_no.isin(station.station_row_no).all())
        self.assertTrue(charger.source_charger_id.str.len().eq(2).all())
        self.assertEqual(charger.speed_code.value_counts().to_dict(), {"slow": 69634, "fast": 5041, "unknown": 932})
        self.assertIsNone(source[0]["reference_start"])
        self.assertEqual(source[1]["collected_on"], "2026-11-06")

    def test_weather_numeric_range_and_precision(self):
        original = read_csv(PROCESSED / "weather_snapshot.csv")
        for column, value in (("rain_mm", "-1"), ("rain_mm", "0.001"), ("temperature_c", "NaN"), ("temperature_c", "1000")):
            changed = original.copy()
            changed.loc[changed[column].ne(""), column] = value
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                validate_weather(changed)

    def test_weather_source_metadata_is_checked_before_loading(self):
        original = json.loads((PROCESSED / "weather_snapshot.meta.json").read_text())
        for column, value in (("station_id", "159"), ("timezone", "UTC"), ("missing_hour_count", 1)):
            changed = {**original, column: value}
            with self.subTest(column=column), tempfile.TemporaryDirectory() as directory:
                metadata = Path(directory) / "weather.meta.json"
                metadata.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    read_source(PROCESSED / "weather_snapshot.csv", metadata, "kma_asos_hourly")


class ApiQueryIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        cls.snapshot = q.get_filter_options()['snapshots'].drop_duplicates("source_code").set_index("source_code").snapshot_id.to_dict()
        if "keco_ev_charger" not in cls.snapshot:
            cls.engine.dispose()
            raise unittest.SkipTest("4차 적재 DB가 필요합니다.")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_sources_are_not_combined(self):
        for code, expected in (("seoul_charger", 429), ("keco_ev_charger", 75607)):
            with query_overlay(source=code):
                result = q.get_charger_summary()
                self.assertEqual(int(result.listed_count.sum()), expected)
                self.assertTrue((result.fast_count + result.slow_count + result.unknown_count).eq(result.listed_count).all())
        result = q.get_district_ranking(date(2026, 9, 1))
        self.assertEqual(int(result.listed_count.sum()), 75607)

    def test_missing_default_source_does_not_fall_back(self):
        with query_overlay(excluded_sources=("keco_ev_charger",)):
            score = q.get_district_ranking(date(2026, 9, 1))
            self.assertTrue(score.score.isna().all())
            self.assertTrue(score.judgment.eq("자료 부족").all())

    def test_weather_null_and_source_filter(self):
        import pandas as pd
        values = [q.get_weather(datetime(2026, 10, day, hour)).iloc[0] for day in (30, 31) for hour in range(24)]
        self.assertEqual(sum(pd.isna(row.rain_mm) for row in values), 46)
        self.assertEqual(sum(pd.isna(row.snow_cm) for row in values), 48)
        self.assertTrue(all(pd.isna(row.temperature_qc_flag) for row in values))
        with query_overlay(excluded_sources=("kma_asos_hourly",)):
            self.assertTrue(q.get_weather(datetime(2026, 10, 30, 8)).empty)
        self.assertTrue(q.get_weather(datetime(2026, 11, 1, 0)).empty)

    def test_operator_and_extension_preserved(self):
        with self.engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM (SELECT source_station_id FROM charging_station WHERE source_snapshot_id=:id GROUP BY source_station_id HAVING COUNT(DISTINCT operator_name)>1) t"), {"id": self.snapshot["keco_ev_charger"]}).scalar_one()
            self.assertGreater(count, 0)
            row = conn.execute(text("SELECT COUNT(c.status_code),COUNT(c.floor_number),COUNT(c.capacity_kw) FROM charger c JOIN charging_station s ON s.station_id=c.station_id WHERE s.source_snapshot_id=:id"), {"id": self.snapshot["keco_ev_charger"]}).one()
            self.assertEqual(row[0], 75607)
            self.assertGreater(row[1], 0)
            self.assertGreater(row[2], 0)

    def test_time_csv_without_validation_stops_before_write(self):
        original_exists = Path.exists

        def exists(path):
            if path == PROCESSED / "snapshot/validation.json":
                return False
            return original_exists(path)

        def read_source(folder):
            if folder.name == "snapshot":
                raise FileNotFoundError("누락 검산 기록 재현")
            return source_record(folder)

        with patch("pathlib.Path.exists", exists), patch("etl.load.source_record", side_effect=read_source), patch.object(self.engine, "begin") as begin:
            with self.assertRaises(FileNotFoundError):
                load_data(self.engine)
            begin.assert_not_called()

    def test_registration_ratio_keeps_small_difference(self):
        region = int(q.get_filter_options()["regions"].iloc[0].region_id)
        changes = {
            "registration": {"columns": {"vehicle_count": "CASE WHEN region_id=:fixture_region AND fuel_scope_code='all' THEN CASE WHEN vehicle_type_code='passenger' THEN 1 ELSE 0 END ELSE vehicle_count END"}},
            "region_context": {"columns": {"household_count": "CASE WHEN region_id=:fixture_region THEN 20001 ELSE household_count END"}},
        }
        with query_overlay(changes, params={"fixture_region": region}):
            actual = float(q.get_summary_metrics(region, date(2026, 9, 1)).iloc[0].vehicle_per_household)
            self.assertAlmostEqual(actual, 1 / 20001, places=12)
            self.assertGreater(actual, 0)
