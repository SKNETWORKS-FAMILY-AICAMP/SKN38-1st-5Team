import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from etl import validate_fetch_run as review


class SnapshotReviewTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.data = self.root / "data/processed"
        self.data.mkdir(parents=True)
        self.archive = self.root / "data/raw/api/charger_national_snapshot.csv"
        self.archive.parent.mkdir(parents=True)
        self.archive.write_bytes(b"column\nFAKE\n")
        metadata = {"row_count": 1, "total_count": 1,
                    "content_sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest()}
        (self.data / "charger_national_snapshot.meta.json").write_text(json.dumps(metadata))
        self.enterContext(patch.object(review, "ROOT", self.root))
        self.enterContext(patch.object(review, "DATA", self.data))

    def test_archived_original_is_verified_and_tampering_rejected(self):
        rows, _ = review.verify_snapshot("charger_national_snapshot", ("column",))
        self.assertEqual(rows, [{"column": "FAKE"}])
        self.archive.write_bytes(b"column\nCHANGED\n")
        with self.assertRaisesRegex(ValueError, "해시"):
            review.verify_snapshot("charger_national_snapshot", ("column",))

    def test_invalid_processed_copy_is_not_hidden_by_valid_archive(self):
        (self.data / self.archive.name).write_bytes(b"column\nCHANGED\n")
        with self.assertRaisesRegex(ValueError, "해시"):
            review.verify_snapshot("charger_national_snapshot", ("column",))

    def test_missing_original_is_not_replaced_by_slim_file(self):
        self.archive.unlink()
        (self.data / "charger_national_seoul.csv").write_bytes(b"column\nFAKE\n")
        with self.assertRaises(FileNotFoundError):
            review.verify_snapshot("charger_national_snapshot", ("column",))


class WeatherReviewTest(unittest.TestCase):
    def setUp(self):
        fixture = Path(__file__).parent / "fixtures/asos_hourly.json"
        from etl.fetch_asos import COLUMN, parse_weather
        from etl.fetch_api_common import parse_page
        parsed = parse_weather(parse_page(json.loads(fixture.read_text())).item)
        self.rows = [{c: "" if row[c] is None else str(row[c]) for c in COLUMN} for row in parsed]
        self.meta = dict(source_code="kma_asos_hourly", station_id="108", timezone="Asia/Seoul",
                         reference_start="2026-10-30", reference_end="2026-10-30",
                         expected_hour_count=24, missing_hour_count=21, is_complete=False)

    def test_partial_hours_zero_and_unknown_quality_are_preserved(self):
        expected, actual = review.verify_weather(self.rows, self.meta)
        self.assertEqual(len(expected - actual), 21)
        self.assertEqual(self.rows[1]["rain_mm"], "0.0")
        self.assertEqual(self.rows[2]["rain_mm"], "")
        self.rows[0]["temperature_qc_flag"] = ""
        review.verify_weather(self.rows, self.meta)

    def test_bad_quality_cannot_have_numeric_value(self):
        for value, flag in (("temperature_c", "temperature_qc_flag"),
                            ("rain_mm", "rain_qc_flag"), ("wind_speed_ms", "wind_qc_flag")):
            for code in ("9", "0.0", "unknown"):
                with self.subTest(value=value, code=code):
                    rows = [dict(row) for row in self.rows]
                    rows[0].update({value: "0", flag: code})
                    with self.assertRaises(ValueError):
                        review.verify_weather(rows, self.meta)

    def test_incorrect_metadata_cannot_approve_partial_observation(self):
        for field, value in (("is_complete", True), ("is_complete", "false"),
                             ("missing_hour_count", 0), ("expected_hour_count", 3),
                             ("source_code", "other"), ("station_id", "119"), ("timezone", "UTC")):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                review.verify_weather(self.rows, {**self.meta, field: value})

    def test_duplicate_time_and_invalid_sql_number_are_rejected(self):
        with self.assertRaises(ValueError):
            review.verify_weather([self.rows[0]] * 3, self.meta)
        for value in ("1000", "NaN", "1.234"):
            rows = [dict(row) for row in self.rows]
            rows[0].update(temperature_c=value, temperature_qc_flag="0")
            with self.subTest(value=value), self.assertRaises(ValueError):
                review.verify_weather(rows, self.meta)


if __name__ == "__main__":
    unittest.main()
