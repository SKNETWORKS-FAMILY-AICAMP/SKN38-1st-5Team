import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.components.v2.bidi_component.main import _make_trigger_id
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
from streamlit.proto.Metric_pb2 import Metric as MetricProto
from streamlit.testing.v1 import AppTest

from tests import app_env


ROOT = Path(__file__).resolve().parents[1]


class OwnershipPageTest(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        self.app.switch_page("app_pages/ownership.py").run()
        self.app.toggle(key="ownership_ranking_show_all").set_value(True).run()
        self.app.toggle(key="ownership_vehicle_show_all").set_value(True).run()
        self.assert_ready()
        from db import queries as q
        self.ranking = q.get_district_ranking()
        self.ids = dict(zip(self.ranking.district_name.astype(str), self.ranking.region_id.astype(int)))
        self.summary = q.get_summary_metrics(self.ids["마포구"])

    def assert_ready(self):
        self.assertFalse(self.app.exception, [e.message for e in self.app.exception])
        self.assertFalse(self.app.error, [e.value for e in self.app.error])

    def hero(self):
        return next(element.proto for element in self.app.get("bidi_component")
                    if element.proto.component_name == "chachacha_h2_seoul")

    def chart(self, phrase):
        return next(element.proto for element in self.app.get("vega_lite_chart") if phrase in element.proto.alt)

    def chart_data(self, phrase):
        chart = self.chart(phrase)
        self.assertEqual(len(chart.datasets), 1)
        return convert_arrow_bytes_to_pandas_df(chart.datasets[0].data.data)

    def select_hero(self, value):
        # AppTest에는 CCv2 클릭 API가 없어 브라우저와 같은 트리거 이벤트를 넣는다.
        states = self.app._tree.get_widget_states()
        event = states.widgets.add()
        event.id = _make_trigger_id(self.hero().id, "events")
        event.json_trigger_value = json.dumps([{"event": "district", "value": value}])
        self.app._run(widget_state=states)
        self.assert_ready()

    def select_rank(self, region_id):
        states = self.app._tree.get_widget_states()
        event = states.widgets.add()
        event.id = self.chart("세대당 차량 보유 순위").id
        event.string_value = json.dumps({"selection": {"rank": [{"region_id": region_id}]}})
        self.app._run(widget_state=states)
        self.assert_ready()

    def assert_district(self, name):
        region_id = self.ids[name]
        self.assertEqual(self.app.selectbox(key="district_id").value, region_id)
        self.assertEqual(self.app.session_state["selected_region_id"], region_id)
        payload = json.loads(self.hero().json)
        self.assertEqual(payload["selected_id"], region_id)
        expected = self.ranking.loc[self.ranking.region_id == region_id].iloc[0]
        self.assertEqual(self.app.metric[0].value, f"{int(expected.vehicle_count):,}대")
        ranks = self.chart_data("세대당 차량 보유 순위")
        self.assertEqual(ranks.loc[ranks.selected, "region_id"].tolist(), [region_id])

    def test_actual_summary_and_sql_average_comparisons(self):
        row = self.summary.iloc[0]
        fields = [
            ("등록 차량", "vehicle_count", 0, "대"),
            ("세대당 차량", "vehicle_per_household", 2, "대"),
            ("전기차", "electric_count", 0, "대"),
            ("전기차 비중", "electric_share_pct", 2, "%"),
        ]
        self.assertEqual(len(self.app.metric), 4)
        for metric, (label, field, digits, unit) in zip(self.app.metric, fields):
            self.assertEqual(metric.label, label)
            self.assertEqual(metric.value, f"{float(row[field]):,.{digits}f}{unit}")
            delta_unit = "%p" if field == "electric_share_pct" else unit
            self.assertEqual(metric.delta, f"{float(row[f'{field}_vs_seoul']):+,.{digits}f}{delta_unit}")
            average = f"서울 평균 {float(row[f'{field}_seoul_avg']):,.{digits}f}{unit}"
            self.assertTrue(any(average in caption.value for caption in self.app.caption))
        self.assertTrue(any("산술평균" in caption.value for caption in self.app.caption))
        self.assertTrue(any("등록 기준 2026.09" in caption.value for caption in self.app.caption))
        self.assert_district("마포구")

    def test_hero_contains_all_25_real_counts_boundaries_and_judgments(self):
        payload = json.loads(self.hero().json)
        self.assertEqual(len(payload["districts"]), 25)
        self.assertEqual(payload["month"], "2026.09")
        for district in payload["districts"]:
            row = self.ranking.loc[self.ranking.region_id == district["id"]].iloc[0]
            self.assertEqual(district["count"], int(row.vehicle_count))
            self.assertEqual(district["name"], str(row.district_name))
            self.assertTrue(district["polygons"])
            self.assertEqual(len(district["center"]), 2)
            for topic in ("ownership", "parking", "need"):
                self.assertEqual(district["levels"][topic], str(row[f"{topic}_level"]))

    def test_type_and_fuel_composition_never_double_count_electric(self):
        from db import queries as q
        source = q.get_registration_breakdown(self.ids["마포구"])
        for scope in ("all", "electric"):
            with self.subTest(scope=scope):
                self.app.segmented_control(key="ownership_scope").set_value(scope).run()
                self.assert_ready()
                rows = self.chart_data("차종별 등록 대수")
                expected = source.loc[source.fuel_scope_code == scope].sort_values("vehicle_count", ascending=False, kind="stable")
                self.assertEqual(len(rows), 4)
                self.assertEqual(rows.vehicle_type_code.tolist(), expected.vehicle_type_code.tolist())
                self.assertEqual(rows.vehicle_count.tolist(), expected.vehicle_count.tolist())
                color = json.loads(self.chart("차종별 등록 대수").spec)["layer"][0]["encoding"]["color"]
                self.assertIn(f"=== {int(expected.vehicle_count.max())}", color["condition"]["test"])
                fuel = self.chart_data("전기차와 전기차 외")
                total, electric = int(self.summary.iloc[0].vehicle_count), int(self.summary.iloc[0].electric_count)
                self.assertEqual(fuel.fuel.tolist(), ["전기차", "전기차 외"])
                self.assertEqual(fuel["count"].tolist(), [electric, total - electric])
                self.assertEqual(int(fuel["count"].sum()), total)
                self.assertAlmostEqual(float(fuel.share.sum()), 100)
        self.assertTrue(any("세부 연료별 자료는 없어요" in c.value for c in self.app.caption))

    def test_vehicle_table_keeps_each_scope_as_sql_counts(self):
        from db import queries as q
        source = q.get_registration_breakdown(self.ids["마포구"])
        for scope in ("all", "electric"):
            with self.subTest(scope=scope):
                self.app.segmented_control(key="ownership_scope").set_value(scope).run()
                self.assert_ready()
                table = self.app.dataframe[-1].value
                expected = source.loc[source.fuel_scope_code == scope]
                self.assertEqual(table["차종"].tolist(), expected.vehicle_type_name.astype(str).tolist())
                self.assertEqual([int(value) for value in table["등록 대수"]],
                                 [int(value) for value in expected.vehicle_count])

    def test_ranking_preserves_all_25_sql_ranks_and_values(self):
        rows = self.chart_data("세대당 차량 보유 순위")
        expected = self.ranking.sort_values(["ownership_rank", "district_name"])
        self.assertEqual(len(rows), 25)
        self.assertEqual(rows.region_id.tolist(), expected.region_id.tolist())
        self.assertEqual(rows.rank_label.tolist(), [str(int(value)) for value in expected.ownership_rank])
        for actual, value in zip(rows.value, expected.ownership_value):
            self.assertAlmostEqual(actual, float(value))

    def test_map_dropdown_and_ranking_reselect_same_district(self):
        hero_id = self.hero().id
        self.select_hero(self.ids["강남구"])
        self.assert_district("강남구")
        self.app.selectbox(key="district_id").select(self.ids["마포구"]).run()
        self.assert_ready()
        self.assert_district("마포구")
        self.select_hero(self.ids["강남구"])
        self.assert_district("강남구")
        old_rank_id = self.chart("세대당 차량 보유 순위").id
        self.select_rank(self.ids["서초구"])
        self.assert_district("서초구")
        self.assertNotEqual(self.chart("세대당 차량 보유 순위").id, old_rank_id)
        self.select_hero(self.ids["강남구"])
        self.assert_district("강남구")
        self.assertEqual(self.hero().id, hero_id, "Selection must not remount the opening scene")
        self.app.run()
        self.assert_ready()
        self.assert_district("강남구")
        self.app.switch_page("app_pages/compare.py").run()
        self.assert_ready()
        self.assertEqual(self.app.selectbox(key="district_id").value, self.ids["강남구"])
        self.app.switch_page("app_pages/ownership.py").run()
        self.assert_ready()
        self.assert_district("강남구")

    def test_invalid_map_events_do_not_change_selection(self):
        for value in (True, "1", -1, 999999, None):
            with self.subTest(value=value):
                self.select_hero(value)
                self.assert_district("마포구")

    def test_missing_metrics_and_geometry_stay_missing(self):
        missing = self.ranking.copy()
        fields = ["vehicle_count", "vehicle_per_household", "electric_count", "electric_share_pct",
                  "ownership_value", "ownership_rank", "ownership_level"]
        missing = missing.drop(columns=fields)
        summary = self.summary.drop(columns=fields)
        with (patch("db.queries.get_summary_metrics", return_value=summary),
              patch("db.queries.get_district_ranking", return_value=missing),
              patch("db.queries.get_region_boundaries", return_value=pd.DataFrame())):
            self.app.run()
        self.assert_ready()
        self.assertEqual([m.value for m in self.app.metric], ["자료 없음"] * 4)
        self.assertEqual([m.delta for m in self.app.metric], ["서울 평균 비교 자료 없음"] * 4)
        self.assertEqual({m.proto.direction for m in self.app.metric}, {MetricProto.MetricDirection.NONE})
        self.assertTrue(any("연료 구성은 자료 없음" in message.value for message in self.app.info))
        payload = json.loads(self.hero().json)
        self.assertEqual(len(payload["districts"]), 25)
        self.assertTrue(all(d["count"] is None and not d["polygons"] for d in payload["districts"]))
        rows = self.chart_data("세대당 차량 보유 순위")
        self.assertEqual(len(rows), 25)
        self.assertTrue(rows.label.eq("자료 없음").all())

    def test_empty_queries_show_missing_without_crashing(self):
        with (patch("db.queries.get_summary_metrics", return_value=pd.DataFrame()),
              patch("db.queries.get_district_ranking", return_value=pd.DataFrame()),
              patch("db.queries.get_registration_breakdown", return_value=pd.DataFrame())):
            self.app.run()
        self.assert_ready()
        self.assertEqual([m.value for m in self.app.metric], ["자료 없음"] * 4)
        self.assertFalse(self.app.get("vega_lite_chart"))
        self.assertTrue(any("서울 25구 순위는 자료 없음" in m.value for m in self.app.info))
        self.assertTrue(all(d["count"] is None for d in json.loads(self.hero().json)["districts"]))

    def test_zero_electric_count_is_valid_but_inconsistent_fuel_is_missing(self):
        # 작은 unsigned 정수의 산술 오류가 드러나도록 uint16을 유지한다.
        summary = self.summary.copy()
        summary["electric_count"] = pd.Series([0], dtype="uint16")
        summary["electric_share_pct"] = 0.0
        with patch("db.queries.get_summary_metrics", return_value=summary):
            self.app.run()
        self.assert_ready()
        self.assertEqual(self.app.metric[2].value, "0대")
        fuel = self.chart_data("전기차와 전기차 외")
        self.assertEqual(fuel["count"].tolist(), [0, int(summary.iloc[0].vehicle_count)])
        summary["electric_count"] = summary.vehicle_count.astype("int64") + 1
        with patch("db.queries.get_summary_metrics", return_value=summary):
            self.app.run()
        self.assert_ready()
        self.assertFalse(any("전기차와 전기차 외" in e.proto.alt for e in self.app.get("vega_lite_chart")))
        self.assertTrue(any("연료 구성은 자료 없음" in m.value for m in self.app.info))


if __name__ == "__main__":
    unittest.main(verbosity=2)
