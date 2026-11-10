import json
import os
import re
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import pyarrow as pa
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from tests import app_env
from db import queries as q
from db.connection import get_engine
from tests.query_support import clear_query_cache, query_overlay


ROOT = Path(__file__).resolve().parents[1]


class ChargingQueryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.regions = q.get_filter_options()["regions"]
        cls.ids = dict(zip(cls.regions.district_name.astype(str), cls.regions.region_id.astype(int)))

    def tearDown(self):
        clear_query_cache()

    def test_traffic_matches_raw_hourly_means_and_unfiltered_city_average(self):
        with get_engine().connect() as conn:
            raw = pd.DataFrame(conn.execute(text("""
                SELECT t.region_id, t.observed_at, t.known_vehicle_sum, t.valid_point_direction_count,
                       v.expected_point_direction_count
                FROM traffic_snapshot t JOIN traffic_coverage v
                  ON v.region_id=t.region_id AND v.source_snapshot_id=t.source_snapshot_id
                WHERE t.source_snapshot_id=(SELECT snapshot_id FROM source_snapshot
                  WHERE source_code='seoul_traffic' AND is_complete=1
                  ORDER BY collected_on DESC, snapshot_id DESC LIMIT 1)
            """)).mappings().all())
        raw = raw.loc[raw.known_vehicle_sum.notna() & raw.valid_point_direction_count.gt(0)].copy()
        observed = pd.to_datetime(raw.observed_at)
        raw["hour_of_day"] = observed.dt.hour
        raw["day_type"] = np.where(observed.dt.dayofweek.lt(5), "평일", "주말")
        raw["complete"] = raw.valid_point_direction_count.eq(raw.expected_point_direction_count)
        means = raw.groupby(["region_id", "day_type", "hour_of_day"]).known_vehicle_sum.mean()
        city = means.groupby(["day_type", "hour_of_day"]).mean()
        for district in ("강남구", "마포구"):
            region_id = self.ids[district]
            result = q.get_traffic_profile(region_id)
            self.assertEqual(len(result), 48)
            self.assertEqual(result.day_type.tolist(), ["평일"] * 24 + ["주말"] * 24)
            self.assertEqual(result.hour_of_day.tolist(), list(range(24)) * 2)
            for _, row in result.iterrows():
                self.assertAlmostEqual(row["avg_vehicles"], means.loc[region_id, row["day_type"], row["hour_of_day"]])
                self.assertAlmostEqual(row["seoul_avg_vehicles"], city.loc[row["day_type"], row["hour_of_day"]])
                sample = raw.loc[raw.region_id.eq(region_id) & raw.day_type.eq(row["day_type"])
                                 & raw.hour_of_day.eq(row["hour_of_day"])]
                self.assertEqual(row["observed_hour_count"], len(sample))
                self.assertEqual(row["complete_hour_count"], int(sample.complete.sum()))
                self.assertEqual(row["seoul_region_count"], 24)
                self.assertEqual(row["reference_start"], sample.observed_at.min().date())
                self.assertEqual(row["reference_end"], sample.observed_at.max().date())
        self.assertTrue(q.get_traffic_profile(self.ids["강북구"]).empty)

    def test_traffic_missing_values_are_excluded_instead_of_zero_filled(self):
        region_id = self.ids["강남구"]
        with query_overlay({"traffic_snapshot": {"columns": {
            "known_vehicle_sum": "CASE WHEN region_id=:target AND HOUR(observed_at)=0 THEN NULL ELSE known_vehicle_sum END",
            "valid_point_direction_count": "CASE WHEN region_id=:target AND HOUR(observed_at)=0 THEN 0 ELSE valid_point_direction_count END",
        }}}, params={"target": region_id}):
            selected = q.get_traffic_profile(region_id)
            self.assertEqual(len(selected), 46)
            self.assertFalse(selected.hour_of_day.eq(0).any())
            other = q.get_traffic_profile(self.ids["마포구"])
            self.assertTrue(other.loc[other.hour_of_day.eq(0), "seoul_region_count"].eq(23).all())
            self.assertTrue(other.loc[other.hour_of_day.ne(0), "seoul_region_count"].eq(24).all())

    def test_breakdowns_reconcile_to_summary_and_device_flags_for_all_districts(self):
        summaries = q.get_charger_summary().set_index("region_id")
        for region_id in self.ids.values():
            with self.subTest(region_id=region_id):
                rows = q.get_charger_breakdown(region_id)
                totals = rows.groupby("breakdown_type", observed=True).charger_count.sum()
                self.assertEqual(set(totals.index), {"speed", "operator", "connector", "restriction", "parking"})
                self.assertTrue(totals.eq(int(summaries.loc[region_id, "listed_count"])).all())
                operators = rows.loc[rows.breakdown_type.eq("operator")]
                self.assertLessEqual(len(operators), 11)
                top = operators.loc[operators.category_code.ne("__other__")]
                self.assertEqual(top.category_rank.tolist(), list(range(1, len(top) + 1)))
                self.assertTrue(top.charger_count.is_monotonic_decreasing)
        devices = q.get_charger_detail(self.ids["강남구"], limit=None)
        breakdown = q.get_charger_breakdown(self.ids["강남구"])
        for kind, field in (("parking", "parking_free"), ("restriction", "restriction_code"), ("speed", "speed_code")):
            for row in breakdown.loc[breakdown.breakdown_type.eq(kind)].itertuples():
                count = devices[field].isna().sum() if row.category_code == "unknown" and kind != "speed" else devices[field].eq(row.category_code).sum()
                self.assertEqual(row.charger_count, int(count))
        unknown_name = breakdown.loc[breakdown.breakdown_type.eq("connector") & breakdown.category_code.eq("11")].iloc[0]
        self.assertEqual(unknown_name.category_label, "이름 자료 없음 (11)")
        self.assertIn("02", breakdown.category_code.tolist())

    def test_latest_complete_charger_snapshot_without_combining_sources(self):
        changes = {"source_code": "CASE WHEN source_code='seoul_charger' THEN 'keco_ev_charger' ELSE source_code END",
                   "collected_on": "CASE WHEN source_code='seoul_charger' THEN '2026-11-07' ELSE collected_on END"}
        region_id = self.ids["강남구"]
        with query_overlay({"source_snapshot": {"columns": changes}}):
            result = q.get_charger_breakdown(region_id)
            devices = q.get_charger_detail(region_id, limit=None)
            self.assertEqual(int(result.loc[result.breakdown_type.eq("speed")].charger_count.sum()), len(devices))
            self.assertLess(len(devices), 500)
        changes["is_complete"] = "CASE WHEN source_code='seoul_charger' THEN 0 ELSE is_complete END"
        with query_overlay({"source_snapshot": {"columns": changes}}):
            result = q.get_charger_breakdown(region_id)
            self.assertGreater(int(result.loc[result.breakdown_type.eq("speed")].charger_count.sum()), 500)

    def test_missing_flags_remain_unknown_not_free_or_unrestricted(self):
        with query_overlay({"charger": {"columns": {"restriction_code": "NULL", "parking_free": "NULL"}}}):
            result = q.get_charger_breakdown(self.ids["마포구"])
            for kind in ("restriction", "parking"):
                rows = result.loc[result.breakdown_type.eq(kind)]
                self.assertEqual(rows.category_code.tolist(), ["unknown"])
                self.assertEqual(rows.category_label.tolist(), ["자료 없음"])

    def test_no_valid_source_or_unknown_district_returns_empty(self):
        with query_overlay(excluded_sources=("seoul_traffic", "keco_ev_charger")):
            self.assertTrue(q.get_traffic_profile(self.ids["강남구"]).empty)
            self.assertTrue(q.get_charger_breakdown(self.ids["강남구"]).empty)
        self.assertTrue(q.get_traffic_profile(999999).empty)
        self.assertTrue(q.get_charger_breakdown(999999).empty)

    def test_region_validation_binding_and_cached_frame_isolation(self):
        for function, metric in ((q.get_traffic_profile, "avg_vehicles"), (q.get_charger_breakdown, "charger_count")):
            function.clear()
            with patch.object(q, "_read_query", wraps=q._read_query) as read:
                first = function(self.ids["마포구"])
                original = first.loc[first.index[0], metric]
                first.loc[first.index[0], metric] = 0
                second = function(self.ids["마포구"])
                self.assertEqual(read.call_count, 1)
                sql, params = read.call_args.args
                self.assertIn(":region_ids", sql)
                self.assertEqual(params["region_ids"], [self.ids["마포구"]])
                self.assertIsNot(first, second)
                self.assertEqual(second.loc[second.index[0], metric], original)
            for value in (None, True, 0, -1, 1.5, "1 OR 1=1"):
                with self.subTest(metric=metric, value=value), self.assertRaises(ValueError):
                    function(value)


class ChargingSummaryTest(unittest.TestCase):
    def test_shared_gauge_keeps_rank_and_missing_rules(self):
        from scene_charging import _level
        for rank, expected in ((1, 3), (8, 3), (9, 2), (17, 2), (18, 1), (25, 1)):
            self.assertEqual(_level(pd.Series({'charger_per_electric_vehicle': .5,
                                             'charger_per_electric_vehicle_rank': rank}))[1], expected)
        self.assertEqual(_level(pd.Series(dtype=object)), ('자료 없음', 0))

    def test_charging_menu_removed_and_search_reaches_parking(self):
        from site_shell import NAV_GROUPS, SEARCH_WORDS
        self.assertNotIn('charging', [path for _, _, paths in NAV_GROUPS for path in paths])
        self.assertEqual(dict(SEARCH_WORDS)['충전'], 'parking')
        self.assertFalse((ROOT / 'app_pages/charging.py').exists())

    def test_parking_still_shows_charging_summary_without_deleted_link(self):
        app = AppTest.from_file(ROOT / 'app.py', default_timeout=30).run()
        app.switch_page('app_pages/parking.py').run()
        self.assertFalse(app.exception)
        gauges = [x.proto for x in app.get('bidi_component')
                  if x.proto.component_name == 'chachacha_charging_gauge']
        self.assertEqual(len(gauges), 1)
        self.assertFalse(any(x.proto.page == 'charging' for x in app.get('page_link')))


if __name__ == '__main__':
    unittest.main()
