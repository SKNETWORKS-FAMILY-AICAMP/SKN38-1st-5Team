import json
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pyarrow as pa
from streamlit.testing.v1 import AppTest

from tests import app_env
from db import queries as q


APP = Path(__file__).resolve().parents[1] / "app.py"


class CompareNationalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = q.get_filter_options()
        cls.ids = dict(zip(options["regions"].district_name.astype(str),
                           options["regions"].region_id.astype("int64")))
        cls.national = q.get_national_registrations()

    def ready(self, app):
        self.assertFalse(app.exception, [item.message for item in app.exception])
        self.assertFalse(app.error, [item.value for item in app.error])

    def page(self, name):
        app = AppTest.from_file(APP, default_timeout=30).run()
        self.ready(app)
        app.switch_page(f"app_pages/{name}.py").run()
        self.ready(app)
        return app

    @staticmethod
    def metric_values(app):
        return {metric.label: metric.value for metric in app.metric}

    @staticmethod
    def chart_frame(app):
        proto = app.get("vega_lite_chart")[0].proto
        payload = proto.datasets[0].data.data if proto.datasets else proto.data.data
        return pa.ipc.open_stream(payload).read_all().to_pandas()

    @staticmethod
    def chart_spec(app):
        return json.loads(app.get("vega_lite_chart")[0].proto.spec)

    def assert_national_result(self, app, expected):
        self.ready(app)
        metrics = self.metric_values(app)
        total = int(expected.vehicle_count.astype("int64").sum())
        self.assertEqual(metrics["선택 조건 합계"], f"{total:,}대")
        self.assertEqual(len(app.dataframe[0].value), len(expected))
        self.assertEqual(int(app.dataframe[0].value["등록 대수"].astype("int64").sum()), total)
        chart = self.chart_frame(app)
        wanted = expected.assign(vehicle_count=expected.vehicle_count.astype("int64"))
        wanted = wanted.groupby("province_name", observed=True).vehicle_count.sum().to_dict()
        self.assertEqual(dict(zip(chart.province_name, chart.vehicle_count)), wanted)
        self.assertEqual(set(chart.loc[chart.is_seoul, "province_name"]),
                         {"서울"} if "서울" in wanted else set())
        axis = self.chart_spec(app)["encoding"]["y"]["axis"]
        self.assertCountEqual(axis["values"], wanted)
        self.assertFalse(axis["labelOverlap"])

    def test_national_totals_chart_and_raw_rows_agree(self):
        app = self.page("national")
        self.assert_national_result(app, self.national)
        values = self.metric_values(app)
        self.assertEqual(values["선택 조건 합계"], "26,706,123대")
        self.assertEqual(values["서울 등록"], "3,150,351대")
        self.assertEqual(values["자료에 있는 지역"], "16개")
        color = self.chart_spec(app)["encoding"]["color"]
        self.assertEqual(color["condition"]["test"], "datum.is_seoul")
        self.assertEqual(color["condition"]["value"], "#FF7A66")
        self.assertEqual(color["value"], "#27336B")

    def test_national_combined_filters_and_selection_survive_navigation(self):
        app = self.page("national")
        app.selectbox(key="district_id").select(self.ids["강서구"])
        app.selectbox(key="national_province").select("서울")
        app.selectbox(key="national_type").select("passenger")
        app.selectbox(key="national_usage").select("private").run()
        expected = q.get_national_registrations(
            province_name="서울", vehicle_type_code="passenger", usage_code="private")
        self.assert_national_result(app, expected)
        self.assertEqual(self.metric_values(app)["서울 등록"],
                         self.metric_values(app)["선택 조건 합계"])
        app.switch_page("app_pages/compare.py").run()
        self.ready(app)
        self.assertEqual(app.selectbox(key="district_id").value, self.ids["강서구"])
        app.switch_page("app_pages/national.py").run()
        self.assertEqual(app.selectbox(key="national_province").value, "서울")
        self.assertEqual(app.selectbox(key="national_type").value, "passenger")
        self.assertEqual(app.selectbox(key="national_usage").value, "private")
        self.assert_national_result(app, expected)

    def test_national_non_seoul_filter_does_not_fabricate_zero_seoul(self):
        app = self.page("national")
        province = next(name for name in self.national.province_name.unique() if name != "서울")
        app.selectbox(key="national_province").select(province).run()
        self.assert_national_result(app, q.get_national_registrations(province_name=province))
        self.assertEqual(self.metric_values(app)["서울 등록"], "선택에서 제외")

    def test_national_missing_counts_do_not_become_a_complete_total(self):
        incomplete = self.national.copy()
        incomplete["vehicle_count"] = incomplete.vehicle_count.astype("Int64")
        missing_index = incomplete.index[incomplete.province_name.eq("서울")][0]
        incomplete.loc[missing_index, "vehicle_count"] = pd.NA
        app = self.page("national")
        with patch("db.queries.get_national_registrations", return_value=incomplete):
            app.run()
        self.ready(app)
        values = self.metric_values(app)
        self.assertEqual(values["선택 조건 합계"], "자료 없음")
        self.assertEqual(values["서울 등록"], "자료 없음")
        self.assertIn("자료 없음", app.dataframe[0].value["등록 대수"].tolist())
        chart = self.chart_frame(app)
        seoul = chart.loc[chart.province_name.eq("서울"), "vehicle_count"]
        self.assertTrue(seoul.empty or seoul.isna().all())

    def test_national_empty_result_keeps_filters_and_navigation(self):
        app = self.page("national")
        with patch("db.queries.get_national_registrations", return_value=self.national.iloc[:0]):
            app.run()
        self.ready(app)
        self.assertTrue(app.info)
        self.assertTrue(app.selectbox(key="national_province"))
        self.assertFalse(app.get("vega_lite_chart"))
        app.switch_page("app_pages/compare.py").run()
        self.ready(app)

    def test_compare_uses_two_districts_and_sql_judgments(self):
        app = self.page("compare")
        app.selectbox(key="district_id").select(self.ids["강서구"]).run()
        app.selectbox(key="compare_id").select(self.ids["강남구"]).run()
        self.ready(app)
        expected = q.get_compare_metrics(self.ids["강서구"], self.ids["강남구"])
        self.assertEqual(len(app.metric), 6)
        self.assertCountEqual([metric.value for metric in app.metric],
                              [str(row[f"{topic}_level"]) for _, row in expected.iterrows()
                               for topic in ("ownership", "parking", "need")])
        captions = "\n".join(item.value for item in app.caption)
        for _, row in expected.iterrows():
            self.assertIn(f"{float(row.parking_value) * 100:.1f}면", captions)
            for topic in ("ownership", "parking", "need"):
                self.assertIn(f"서울 25구 중 {int(row[f'{topic}_rank'])}위", captions)
        self.assertIn("일부 행정동", captions)
        self.assertIn("아파트", captions)
        self.assertIn("부분 관측", app.metric[2].delta)
        self.assertIn("부분 관측", app.metric[5].delta)

    def test_compare_direction_and_first_picker_stay_in_sync(self):
        app = self.page("compare")
        app.selectbox(key="compare_first_id").select(self.ids["마포구"]).run()
        app.selectbox(key="compare_id").select(self.ids["강남구"]).run()
        self.ready(app)
        self.assertIn("더 많아요", app.metric[3].delta)
        self.assertIn("더 적어요", app.metric[2].delta)
        self.assertIn("더 많아요", app.metric[5].delta)
        self.assertTrue(any("승객 수가 적은 쪽을 차 필요성이 더 높은" in item.value for item in app.caption))
        self.assertNotIn("미만면", app.metric[1].delta)
        app.selectbox(key="compare_first_id").select(self.ids["강서구"]).run()
        self.ready(app)
        self.assertEqual(app.selectbox(key="district_id").value, self.ids["강서구"])
        app.switch_page("app_pages/faq.py").run()
        self.ready(app)
        app.switch_page("app_pages/compare.py").run()
        self.ready(app)
        self.assertEqual(app.selectbox(key="compare_first_id").value, self.ids["강서구"])
        self.assertEqual(app.selectbox(key="compare_id").value, self.ids["강남구"])

    def test_compare_registration_details_do_not_double_count_electric(self):
        app = self.page("compare")
        app.selectbox(key="compare_first_id").select(self.ids["마포구"]).run()
        app.selectbox(key="compare_id").select(self.ids["강남구"]).run()
        app.session_state["compare_details"] = True
        app.run()
        for label, scope in (("전체 차량", "all"), ("전기차", "electric")):
            app.pills(key="compare_fuel_scope").set_value(label).run()
            self.ready(app)
            self.assertEqual(len(app.dataframe), 2)
            self.assertEqual(len(app.get("vega_lite_chart")), 1)
            self.assertEqual(len(app.dataframe[0].value), 2)
            chart = self.chart_frame(app)
            table = app.dataframe[1].value.set_index("차종")
            self.assertEqual(len(chart), 8)
            encoding = self.chart_spec(app)["encoding"]
            # 정렬 오류가 드러나도록 가나다순과 다른 순서로 동네를 선택한다.
            expected_order = ["마포구", "강남구"]
            self.assertEqual(encoding["yOffset"]["sort"], expected_order)
            self.assertEqual(encoding["color"]["sort"], expected_order)
            self.assertEqual(encoding["color"]["scale"]["domain"], expected_order)
            self.assertEqual(list(table.columns), expected_order)
            for name in ("마포구", "강남구"):
                expected = q.get_registration_breakdown(self.ids[name])
                expected = expected.loc[expected.fuel_scope_code.eq(scope)]
                expected_counts = dict(zip(expected.vehicle_type_name.astype(str), expected.vehicle_count.astype("int64")))
                plotted = chart.loc[chart.district_name.eq(name)]
                self.assertEqual(dict(zip(plotted.vehicle_type_name, plotted.vehicle_count)), expected_counts)
                for vehicle, count in expected_counts.items():
                    self.assertEqual(table.loc[vehicle, name], f"{count:,}대")

        app.selectbox(key="compare_first_id").select(self.ids["강남구"]).run()
        app.selectbox(key="compare_id").select(self.ids["마포구"]).run()
        self.ready(app)
        encoding = self.chart_spec(app)["encoding"]
        for order in (encoding["yOffset"]["sort"], encoding["color"]["sort"],
                      encoding["color"]["scale"]["domain"]):
            self.assertEqual(order, ["강남구", "마포구"])

    def test_compare_same_district_is_allowed_and_explained(self):
        app = self.page("compare")
        selected = app.selectbox(key="district_id").value
        app.selectbox(key="compare_id").select(selected).run()
        self.ready(app)
        self.assertTrue(any("같은 동네" in item.value or "같은 구" in item.value for item in app.info))
        self.assertEqual(app.selectbox(key="compare_id").value, selected)
        self.assertTrue(all(metric.delta == "근거값이 같아요" for metric in app.metric))
        app.session_state["compare_details"] = True
        app.run()
        self.ready(app)
        self.assertEqual(len(app.dataframe[0].value), 1)
        self.assertEqual(len(self.chart_frame(app)), 4)
        encoding = self.chart_spec(app)["encoding"]
        name = next(name for name, region_id in self.ids.items() if region_id == selected)
        self.assertEqual(encoding["yOffset"]["sort"], [name])
        self.assertEqual(encoding["color"]["scale"]["domain"], [name])

    def test_compare_small_differences_and_rounding_boundaries(self):
        app = self.page("compare")
        first = app.selectbox(key="compare_first_id").value
        second = app.selectbox(key="compare_id").value
        comparison = q.get_compare_metrics(first, second).copy()
        comparison["transit_observed_hour_count"] = 24
        comparison["transit_complete_hour_count"] = 24
        cases = (
            ((1.00001, 0.02603, 1.00001),
             ["거의 같아요 · 0.01대 미만 차이", "거의 같아요 · 0.1면 미만 차이",
              "거의 같아요 · 0.01명 미만 차이"]),
            ((1.01, 0.027, 1.01),
             ["세대당 0.01대 더 많아요", "차 100대당 0.1면 더 많아요", "주민 1명당 하루 승객이 0.01명 더 많아요"]),
        )
        for values, expected in cases:
            with self.subTest(values=values):
                for topic, value, reference in zip(("ownership", "parking", "need"), values, (1.0, 0.026, 1.0)):
                    comparison[f"{topic}_value"] = comparison.region_id.map({first: value, second: reference})
                with patch("db.queries.get_compare_metrics", return_value=comparison):
                    app.run()
                self.ready(app)
                self.assertEqual([metric.delta for metric in app.metric[:3]], expected)
                reverse = [text.replace("더 많아요", "더 적어요") for text in expected]
                self.assertEqual([metric.delta for metric in app.metric[3:]], reverse)

    def test_compare_missing_judgment_is_not_an_invented_comparison(self):
        app = self.page("compare")
        first = app.selectbox(key="district_id").value
        second = app.selectbox(key="compare_id").value
        incomplete = q.get_compare_metrics(first, second).copy()
        for column in ("parking_value", "parking_rank", "parking_level"):
            incomplete[column] = pd.NA
        with patch("db.queries.get_compare_metrics", return_value=incomplete):
            app.run()
        self.ready(app)
        self.assertEqual(sum(metric.value == "자료 없음" for metric in app.metric), 2)


if __name__ == "__main__":
    unittest.main()
