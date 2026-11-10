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


class ChargingPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ranking = q.get_district_ranking()
        cls.ids = dict(zip(cls.ranking.district_name.astype(str), cls.ranking.region_id.astype(int)))

    def setUp(self):
        key_patch = patch("parking_explorer.javascript_key", return_value="")
        key_patch.start()
        self.addCleanup(key_patch.stop)
        environment = patch.dict(os.environ, {"CHACHACHA_ALLOW_BOTS": "1", "CHACHACHA_DEV": "1"})
        environment.start()
        self.addCleanup(environment.stop)
        self.app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        self.app.switch_page("app_pages/charging.py").run()
        self.assert_ready()

    def assert_ready(self):
        self.assertFalse(self.app.exception, [item.message for item in self.app.exception])
        self.assertFalse(self.app.error, [item.value for item in self.app.error])

    def text(self):
        return "\n".join(str(item.value) for group in (self.app.caption, self.app.markdown, self.app.info, self.app.warning) for item in group)

    def gauge(self):
        components = [item.proto for item in self.app.get("bidi_component")
                      if item.proto.component_name == "chachacha_charging_gauge"]
        self.assertEqual(len(components), 1)
        return json.loads(components[0].json)

    def table(self, column):
        return next(item.value for item in self.app.dataframe if column in item.value)

    def test_initial_metrics_sources_and_gauge_replay(self):
        row = q.get_summary_metrics(self.ids["마포구"]).iloc[0]
        metrics = {item.label: item.value for item in self.app.metric}
        self.assertEqual(metrics["전기차 한 대당 충전기"], f"{row.charger_per_electric_vehicle:,.2f}기")
        self.assertEqual(metrics["서울 순위 · 충전기 비율"], f"{row.charger_per_electric_vehicle_rank}위 / 25구")
        self.assertEqual(metrics["급속"], f"{row.fast_count:,}기")
        self.assertEqual(metrics["완속"], f"{row.slow_count:,}기")
        self.assertEqual(len(self.table("충전소")), row.listed_station_count)
        self.assertIn("실시간 빈자리 정보가 아니에요", self.text())
        self.assertIn("충전 요금 무료를 뜻하지 않아요", self.text())
        self.assertIn("실제 배터리 충전량이나 주차 여건을 뜻하지 않아요", self.text())
        self.assertEqual(self.gauge()["district_name"], "마포구")
        self.assertTrue(any("실시간 빈자리" in item.value for item in self.app.warning))
        self.assertIn("2026.09", self.text())
        self.assertIn("2026.11.06", self.text())
        self.assertTrue(self.gauge()["animate"])
        self.app.run()
        self.assert_ready()
        self.assertFalse(self.gauge()["animate"])

    def test_judgment_boundaries_and_missing_ratio(self):
        summary = q.get_summary_metrics(self.ids["마포구"]).copy()
        for rank, level in ((1, 3), (8, 3), (9, 2), (17, 2), (18, 1), (25, 1)):
            changed = summary.assign(charger_per_electric_vehicle_rank=rank)
            with patch.object(q, "get_summary_metrics", return_value=changed):
                self.app.run()
            self.assert_ready()
            self.assertEqual(self.gauge()["level"], level)
            self.assertEqual(self.gauge()["color"], {1: "#DC2626", 2: "#EAB308", 3: "#15803D"}[level])
            self.assertFalse(self.gauge()["animate"])
        changed = summary.assign(charger_per_electric_vehicle=pd.NA)
        with patch.object(q, "get_summary_metrics", return_value=changed):
            self.app.run()
        self.assert_ready()
        self.assertEqual(self.gauge()["level"], 0)
        self.assertEqual(self.gauge()["color"], "#64748B")
        self.assertIn("자료 없음", self.gauge()["title"])
        self.assertEqual(self.app.metric[0].value, "자료 없음")

    def test_connector_and_operator_charts_keep_labels_and_room_between_bars(self):
        item_counts = []
        heights = []
        for chart in self.app.get("vega_lite_chart"):
            spec = json.loads(chart.proto.spec)
            heights.append(spec["height"])
            payload = chart.proto.datasets[0].data.data if chart.proto.datasets else chart.proto.data.data
            data = pa.ipc.open_stream(payload).read_all().to_pandas()
            count = len(data)
            item_counts.append(count)
            with self.subTest(item_count=count):
                # Streamlit fit은 전체 높이에서 축·제목 공간을 먼저 뺀다.
                row_spacing = (spec["height"] - 80) / count
                self.assertGreaterEqual(row_spacing, 24)
                self.assertEqual(spec["mark"]["size"], 19)
                self.assertGreater(row_spacing, spec["mark"]["size"])
                self.assertIs(spec["encoding"]["y"]["axis"]["labelOverlap"], False)
                self.assertEqual(data.is_highest.tolist(), data.charger_count.eq(data.charger_count.max()).tolist())
                self.assertEqual(spec["encoding"]["color"]["condition"]["value"], "#FF7A66")
                self.assertEqual(spec["encoding"]["color"]["value"], "#8E98CF")
                self.assertIn("800", spec["encoding"]["y"]["axis"]["labelFontWeight"]["expr"])
        self.assertCountEqual(item_counts, [7, 10])
        self.assertEqual(len(set(heights)), 1)

    def test_zero_breakdown_has_no_invented_leader(self):
        breakdown = q.get_charger_breakdown(self.ids["마포구"]).copy()
        breakdown["charger_count"] = 0
        with patch.object(q, "get_charger_breakdown", return_value=breakdown):
            self.app.run()
        self.assert_ready()
        for chart in self.app.get("vega_lite_chart"):
            payload = chart.proto.datasets[0].data.data if chart.proto.datasets else chart.proto.data.data
            data = pa.ipc.open_stream(payload).read_all().to_pandas()
            self.assertFalse(data.is_highest.any())

    def test_district_changes_keep_city_rank_and_replace_station_inventory(self):
        for row in self.ranking.to_dict("records"):
            with self.subTest(district=row["district_name"]):
                self.app.selectbox(key="district_id").select(int(row["region_id"])).run()
                self.assert_ready()
                self.assertIn(row["district_name"], self.gauge()["title"])
                self.assertIn(f"{int(row['charger_per_electric_vehicle_rank'])}위", self.gauge()["detail"])
                self.assertEqual(len(self.table("충전소")), row["listed_station_count"])
                selected = self.app.selectbox(key="charging_station").value
                devices = q.get_charger_detail(int(row["region_id"]), limit=None)
                self.assertIn(selected, devices.station_id.tolist())
                self.assertFalse(self.gauge()["animate"])

    def test_fast_and_free_filters_match_device_inventory(self):
        self.app.segmented_control(key="charging_speed").set_value("fast").run()
        self.app.toggle(key="charging_free_only").set_value(True).run()
        self.assert_ready()
        expected = q.get_charger_detail(self.ids["마포구"], speed="fast", limit=None)
        expected = expected.loc[expected.parking_free.eq("Y")]
        self.assertEqual(len(self.table("충전소")), expected.station_id.nunique())
        self.assertTrue(self.table("기기 번호")["충전 속도"].eq("급속").all())
        self.assertTrue(self.table("기기 번호")["주차 요금"].eq("무료로 수록").all())
        selected = self.app.selectbox(key="charging_station").value
        self.assertEqual(self.table("기기 번호")["기기 번호"].tolist(),
                         expected.loc[expected.station_id.eq(selected)].source_charger_id.tolist())
        points = q.get_place_points(self.ids["마포구"], kinds=("charger",), speed="fast")
        points = points.loc[points.place_id.isin(expected.station_id)]
        html = self.app.get("iframe")[0].proto.srcdoc
        match = re.search(r"const data=(.*?);\nconst esc", html, re.S)
        if match is None:
            self.fail("지도 입력 자료가 없어요.")
        payload = json.loads(match.group(1))
        self.assertCountEqual([place["id"] for place in payload["places"]],
                              [f"charger-{value}" for value in points.place_id])
        self.assertTrue(all(place["kind"] == "충전소" for place in payload["places"]))
        self.assertIn("map.kakao.com/link/to/", html)
        self.assertNotIn("appkey", html)
        self.assertFalse(self.app.get("deck_gl_json_chart"))

    def test_search_is_literal_and_empty_search_has_no_stale_map(self):
        devices = q.get_charger_detail(self.ids["마포구"], limit=None).head(2).copy()
        devices["station_name"] = "충전소 [확인]%_!"
        with patch.object(q, "get_charger_detail", return_value=devices):
            self.app.text_input(key="charging_keyword").set_value("[확인]%_!").run()
        self.assert_ready()
        self.assertEqual(len(self.table("충전소")), devices.station_id.nunique())
        self.app.text_input(key="charging_keyword").set_value("없는충전소-충전검사-999999").run()
        self.assert_ready()
        self.assertFalse(self.app.get("deck_gl_json_chart"))
        self.assertIn("현재 조건의 충전소 0곳", self.text())
        self.assertFalse(self.app.get("iframe"))
        self.assertFalse(any("충전소" in item.value for item in self.app.dataframe))

    def test_stations_without_coordinates_stay_in_list(self):
        devices = q.get_charger_detail(self.ids["마포구"], limit=None)
        with patch.object(q, "get_place_points", return_value=pd.DataFrame()):
            self.app.run()
        self.assert_ready()
        self.assertEqual(len(self.table("충전소")), devices.station_id.nunique())
        self.assertTrue(self.table("충전소")["지도 안내"].eq("좌표 없음·범위 밖").all())
        self.assertFalse(self.app.get("deck_gl_json_chart"))
        self.assertFalse(self.app.get("iframe"))

    def test_missing_source_preserves_missing_metrics_and_no_fabricated_points(self):
        summary = q.get_summary_metrics(self.ids["마포구"]).copy()
        for column in ("charger_per_electric_vehicle", "charger_per_electric_vehicle_rank", "listed_station_count",
                       "listed_count", "fast_count", "slow_count", "unknown_count"):
            summary[column] = pd.NA
        with patch.object(q, "get_summary_metrics", return_value=summary), \
                patch.object(q, "get_charger_breakdown", return_value=pd.DataFrame()), \
                patch.object(q, "get_charger_detail", return_value=pd.DataFrame()), \
                patch.object(q, "get_place_points", return_value=pd.DataFrame()):
            self.app.run()
        self.assert_ready()
        self.assertTrue(all(item.value == "자료 없음" for item in self.app.metric))
        self.assertEqual(self.gauge()["level"], 0)
        self.assertFalse(self.app.get("deck_gl_json_chart"))
        self.assertIn("충전소 목록과 지도는 자료 없음이에요", self.text())
        self.assertNotIn("현재 조건의 충전소 0곳", self.text())

    def test_kakao_component_matches_filters_without_changing_identity(self):
        def component():
            return next(item.proto for item in self.app.get("bidi_component")
                        if item.proto.component_name == "chachacha_kakao_places")
        with patch("parking_explorer.javascript_key", return_value="test-only"):
            self.app.run()
            self.assert_ready()
            identity = component().id
            self.app.segmented_control(key="charging_speed").set_value("fast").run()
            self.app.toggle(key="charging_free_only").set_value(True).run()
            self.assert_ready()
            devices = q.get_charger_detail(self.ids["마포구"], speed="fast", limit=None)
            devices = devices.loc[devices.parking_free.eq("Y")]
            points = q.get_place_points(self.ids["마포구"], kinds=("charger",), speed="fast", limit=None)
            points = points.loc[points.place_id.isin(devices.station_id)]
            payload = json.loads(component().json)
            self.assertCountEqual([place["id"] for place in payload["places"]],
                                  [f"charger-{value}" for value in points.place_id])
            self.assertTrue(all("주차 무료" in place["price"] for place in payload["places"]))
            for place in payload["places"]:
                station_id = int(place["id"].removeprefix("charger-"))
                self.assertEqual(place["capacity"], f"충전기 {int(devices.station_id.eq(station_id).sum())}기")
            self.assertEqual(component().id, identity)
            self.assertFalse(self.app.get("iframe"))
            self.assertFalse(self.app.get("deck_gl_json_chart"))
            self.app.selectbox(key="district_id").select(self.ids["강남구"]).run()
            self.assert_ready()
            self.assertEqual(component().id, identity)
            self.assertEqual(json.loads(component().json)["district"], "강남구")
            self.app.text_input(key="charging_keyword").set_value("없는충전소xyz987").run()
            self.assert_ready()
            self.assertEqual(json.loads(component().json)["places"], [])
            self.assertEqual(component().id, identity)


if __name__ == "__main__":
    unittest.main()
