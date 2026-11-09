from contextlib import ExitStack
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
import pyarrow as pa
from streamlit.testing.v1 import AppTest

from tests import app_env
from db import queries as q
from ui import date_text, number


APP = Path(__file__).resolve().parents[1] / "app.py"


class FaqDetailsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = q.get_filter_options()
        regions = cls.options["regions"]
        cls.region_id = int(regions.loc[regions.district_name == "마포구", "region_id"].iloc[0])
        cls.gangseo_id = int(regions.loc[regions.district_name == "강서구", "region_id"].iloc[0])

    def setUp(self):
        self.app = AppTest.from_file(APP, default_timeout=30).run()
        self.assert_ready()

    def assert_ready(self):
        self.assertFalse(self.app.exception, [item.message for item in self.app.exception])
        self.assertFalse(self.app.error, [item.value for item in self.app.error])

    def page_text(self):
        return "\n".join(
            str(item.value)
            for group in (self.app.markdown, self.app.caption, self.app.info, self.app.warning)
            for item in group
        )

    def open_detail(self, topic="차량 구성"):
        self.app.session_state["b_details"] = True
        self.app.run()
        self.assert_ready()
        if self.app.segmented_control(key="detail_topic").value != topic:
            self.app.segmented_control(key="detail_topic").set_value(topic).run()
            self.assert_ready()

    def passenger_chart_data(self):
        for chart in self.app.get("vega_lite_chart"):
            payloads = [chart.proto.data, *(dataset.data for dataset in chart.proto.datasets)]
            for payload in payloads:
                if not payload.data:
                    continue
                frame = pa.ipc.open_stream(payload.data).read_all().to_pandas()
                if {"hour_of_day", "known_passenger_sum"}.issubset(frame.columns):
                    return frame
        self.fail("시간별 승객 데이터가 차트에 전달되지 않았습니다.")

    def test_faq_shows_all_questions_with_answers_sources_and_dates(self):
        expected = q.search_faq()
        self.app.switch_page("app_pages/faq.py").run()
        self.app.segmented_control(key="faq_kind").set_value("기업 FAQ").run()
        self.assert_ready()
        self.assertEqual(len(expected), 10)
        self.assertCountEqual([item.label for item in self.app.expander], expected.question.tolist())
        for _, row in expected.iterrows():
            expander = self.app.expander(key=f"faq_{row.company_id}_{row.faq_key}")
            self.assertIn(str(row.answer_text), [item.value for item in expander.markdown])
            self.assertIn(date_text(row.fetched_on), "\n".join(item.value for item in expander.caption))
            self.assertEqual(expander.link_button[0].url, row.source_url)

    def test_faq_filters_empty_result_and_reset(self):
        self.app.switch_page("app_pages/faq.py").run()
        self.app.segmented_control(key="faq_kind").set_value("기업 FAQ").run()
        self.assert_ready()
        company_id = int(self.options["faq_companies"].iloc[0].company_id)
        category = self.options["faq_categories"][0]
        with patch.object(q, "search_faq", wraps=q.search_faq) as search:
            self.app.text_input(key="faq_keyword").set_value("충전")
            self.app.selectbox(key="faq_company").select(company_id)
            self.app.selectbox(key="faq_category").select(category).run()
            self.assert_ready()
            args, kwargs = search.call_args
            self.assertEqual(args[0], "충전")
            self.assertEqual(kwargs["company_id"], company_id)
            self.assertEqual(kwargs["category"], category)
        expected = q.search_faq("충전", company_id=company_id, category=category)
        self.assertCountEqual([item.label for item in self.app.expander], expected.question.tolist())
        self.app.text_input(key="faq_keyword").set_value("없는질문xyz987").run()
        self.assert_ready()
        self.assertEqual(len(self.app.expander), 0)
        self.assertIn("조건에 맞는 질문", self.page_text())
        self.app.button(key="faq_reset").click().run()
        self.assert_ready()
        self.assertEqual(self.app.text_input(key="faq_keyword").value, "")
        self.assertIsNone(self.app.selectbox(key="faq_company").value)
        self.assertIsNone(self.app.selectbox(key="faq_category").value)
        self.assertEqual(len(self.app.expander), 10)

    def test_faq_missing_answer_date_and_unusable_source_are_explicit(self):
        frame = q.search_faq().iloc[:1].copy()
        frame["answer_text"] = None
        frame["fetched_on"] = pd.NaT
        frame["source_url"] = "https:///missing-host"
        with patch.object(q, "search_faq", return_value=frame):
            self.app.switch_page("app_pages/faq.py").run()
            self.app.segmented_control(key="faq_kind").set_value("기업 FAQ").run()
        self.assert_ready()
        self.assertFalse(self.app.link_button)
        self.assertIn("자료 없음", self.page_text())
        self.assertNotIn("NaT", self.page_text())

    def test_closed_details_skip_queries_and_only_open_section_loads(self):
        query_names = (
            "get_summary_metrics", "get_registration_breakdown", "get_place_points",
            "search_places", "get_charger_summary", "get_charger_detail", "get_trend_data", "get_weather",
        )
        with ExitStack() as stack:
            calls = {name: stack.enter_context(patch.object(q, name, wraps=getattr(q, name)))
                     for name in query_names}
            self.app.run()
            self.assert_ready()
            for query in calls.values():
                query.assert_not_called()
            self.open_detail()
            calls["get_registration_breakdown"].assert_called()
            for name in ("get_place_points", "get_charger_detail", "get_trend_data", "get_weather"):
                calls[name].assert_not_called()
            before = {name: query.call_count for name, query in calls.items()}
            self.app.session_state["b_details"] = False
            self.app.run()
            self.assert_ready()
            self.assertEqual({name: query.call_count for name, query in calls.items()}, before)
            self.assertFalse(self.app.segmented_control)

    def test_registration_keeps_electric_subset_and_sql_share(self):
        self.open_detail()
        summary = q.get_summary_metrics(self.region_id).iloc[0]
        metrics = {item.label: item.value for item in self.app.metric}
        self.assertIn(number(summary.electric_share_pct, 1, "%"), metrics.values())
        rows = q.get_registration_breakdown(self.region_id)
        for scope in ("all", "electric"):
            with self.subTest(scope=scope):
                self.app.segmented_control(key="detail_fuel").set_value(scope).run()
                self.assert_ready()
                table = self.app.dataframe[-1].value
                expected = rows.loc[rows.fuel_scope_code == scope]
                self.assertEqual(table["차종"].tolist(), expected.vehicle_type_name.astype(str).tolist())
                self.assertEqual(pd.to_numeric(table["등록 대수"]).tolist(),
                                 expected.vehicle_count.astype("int64").tolist())

    def test_charger_map_and_details_follow_same_speed_filter(self):
        self.open_detail("주차·충전 시설")
        self.app.toggle(key="detail_parking_show_all").set_value(True).run()
        # 마포구는 수록 주차장의 좌표가 전부 없어도 목록은 보여야 한다.
        parking = q.search_places("주차장 [", region_id=self.region_id, limit=100)
        parking = parking.loc[parking.kind == "parking_site"]
        self.assertEqual(len(self.app.dataframe[-1].value), len(parking))
        self.assertGreater(len(parking), 0)
        self.app.segmented_control(key="detail_facility").set_value("충전기").run()
        self.assert_ready()
        with patch.object(q, "get_place_points", wraps=q.get_place_points) as points, \
                patch.object(q, "get_charger_detail", wraps=q.get_charger_detail) as chargers, \
                patch.object(q, "get_charger_summary", wraps=q.get_charger_summary) as summary:
            self.app.pills(key="detail_speed").set_value("fast").run()
            self.assert_ready()
            for query in (points, chargers, summary):
                self.assertEqual(query.call_args.kwargs["speed"], "fast")
            self.assertEqual(points.call_args.kwargs["kinds"], ("charger",))
        self.assertTrue(self.app.get("deck_gl_json_chart"))
        self.assertIn("실시간", self.page_text())

    def test_no_coordinates_preserves_exclusion_notice_and_skips_map(self):
        points = q.get_place_points(self.region_id, kinds=("parking",)).iloc[:0].copy()
        points.attrs["coverage"] = [{
            "kind": "parking_site", "total_count": 3, "point_count": 0,
            "excluded_count": 3, "invalid_coordinate_count": 2, "identifier_conflict_count": 1,
        }]
        points.attrs["returned_count"] = 0
        with patch.object(q, "get_place_points", return_value=points):
            self.open_detail("주차·충전 시설")
        self.assert_ready()
        self.assertFalse(self.app.get("deck_gl_json_chart"))
        self.assertIn("좌표", self.page_text())
        self.assertIn("번호", self.page_text())
        self.assertIn("3", self.page_text())

    def test_transit_uses_judgment_day_single_mode_and_partial_notice(self):
        with patch.object(q, "get_trend_data", wraps=q.get_trend_data) as trend:
            self.open_detail("시간대별 승객")
            self.assertEqual(trend.call_args.kwargs["stat_date"], date(2026, 10, 30))
        self.assertEqual(self.app.selectbox(key="detail_day").value, date(2026, 10, 30))
        self.app.toggle(key="detail_passengers_show_all").set_value(True).run()
        for mode in ("total", "bus"):
            with self.subTest(mode=mode):
                self.app.pills(key="detail_mode").set_value(mode).run()
                self.assert_ready()
                actual = self.passenger_chart_data()
                expected = q.get_trend_data(self.region_id, date(2026, 10, 30), analysis_type="4")
                expected = expected.loc[(expected.series_type == "passenger") & (expected.mode_code == mode)]
                expected = expected.sort_values("known_passenger_sum", ascending=False, kind="stable")
                self.assertEqual(actual.known_passenger_sum.tolist(), expected.known_passenger_sum.tolist())
                self.assertEqual(actual.hour_of_day.tolist(), expected.hour_of_day.tolist())
        self.app.selectbox(key="district_id").select(self.gangseo_id).run()
        self.assert_ready()
        self.assertIn("일부 행정동 자료가 빠져", self.page_text())

    def test_weather_missing_precipitation_is_not_zero_and_survives_empty_transit(self):
        weather = q.get_weather().copy()
        self.assertFalse(weather.empty)
        weather["rain_mm"] = pd.NA
        weather["snow_cm"] = pd.NA
        with patch.object(q, "get_weather", return_value=weather), \
                patch.object(q, "get_trend_data", return_value=pd.DataFrame()):
            self.open_detail("시간대별 승객")
        self.assert_ready()
        metrics = {item.label: item.value for item in self.app.metric}
        self.assertEqual(metrics["강수량"], "자료 없음")
        self.assertEqual(metrics["적설량"], "자료 없음")
        self.assertIn("서울", self.page_text())
        self.assertIn(date_text(weather.iloc[0].observed_at), self.page_text())


if __name__ == "__main__":
    unittest.main()
