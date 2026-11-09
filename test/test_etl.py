from pathlib import Path
import tempfile
import unittest

import pandas as pd

from etl.crawl_faq import extract_faq
from etl.prepare import count_value, district_from_address

ROOT = Path(__file__).resolve().parents[1]


class EtlTest(unittest.TestCase):
    def test_address_without_space_and_outside_seoul(self):
        self.assertEqual(district_from_address("서울특별시 강남구영동대로106길 33 주변"), "강남구")
        self.assertEqual(district_from_address("서울시 중구 세종대로"), "중구")
        self.assertEqual(district_from_address("서울시, 노원구 공릉동"), "노원구")
        self.assertIsNone(district_from_address("경기도 안양시 서울길"))
        self.assertIsNone(district_from_address("부산광역시 중구 중앙대로"))

    def test_count_missing_is_not_zero(self):
        self.assertEqual(count_value("6,789"), 6789)
        self.assertEqual(count_value(0), 0)
        for value in (None, "", -1, 1.5, float("nan"), "1,,000", "3,21"):
            with self.assertRaises(ValueError):
                count_value(value)

    def test_faq_ignores_navigation_and_keeps_paragraph(self):
        html = '<nav><li><h3>메뉴</h3><p>메뉴</p></li></nav><section class="faq" aria-labelledby="ev-care-faq-title"><li><h3>질문</h3><p>첫 문단</p><p>둘째 문단</p></li></section>'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "faq.html"
            path.write_text(html, encoding="utf-8")
            frame = extract_faq(path)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["answer_text"], "첫 문단\n둘째 문단")

    def test_processed_scope_and_registration(self):
        region = pd.read_csv(ROOT / "data/processed/region.csv", dtype={"resident_code": str})
        registration = pd.read_csv(ROOT / "data/processed/registration.csv", dtype={"resident_code": str})
        self.assertEqual(len(region), 25)
        self.assertEqual(len(registration), 200)
        self.assertEqual(set(registration.resident_code), set(region.resident_code))
        self.assertFalse(registration.duplicated(["resident_code", "stat_month", "vehicle_type_code", "fuel_scope_code"]).any())
        pivot = registration.pivot(index=["resident_code", "vehicle_type_code"], columns="fuel_scope_code", values="vehicle_count")
        self.assertTrue((pivot.electric <= pivot["all"]).all())
        self.assertEqual(int(pivot["all"].sum()), 3150351)
        self.assertEqual(int(pivot.electric.sum()), 127750)

    def test_parking_conflict_and_charger_key(self):
        parking = pd.read_csv(ROOT / "data/processed/parking_site.csv")
        charger = pd.read_csv(ROOT / "data/processed/charger.csv", dtype={"source_charger_id": str})
        station = pd.read_csv(ROOT / "data/processed/charging_station.csv")
        self.assertEqual(len(parking), 857)
        self.assertEqual(int(parking.identifier_status.eq("conflict").sum()), 22)
        self.assertTrue(parking.loc[parking.identifier_status.eq("conflict"), "map_eligible"].eq(0).all())
        self.assertEqual(len(charger), 429)
        self.assertFalse(charger.duplicated(["station_key", "source_charger_id"]).any())
        self.assertEqual(len(charger.merge(station[["station_key"]], validate="many_to_one")), 429)
