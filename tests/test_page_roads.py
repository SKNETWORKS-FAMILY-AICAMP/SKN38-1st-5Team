from datetime import datetime
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
from streamlit.testing.v1 import AppTest

from tests import app_env
from db import queries as q


ROOT = Path(__file__).resolve().parents[1]


class RoadsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = q.get_filter_options()
        regions = cls.options["regions"]
        cls.ids = dict(zip(regions.district_name.astype(str), regions.region_id.astype(int)))
        cls.region_id = cls.ids["마포구"]
        cls.profile = q.get_traffic_profile(cls.region_id)
        cls.weather = pd.concat([q.get_weather(at) for at in cls.options["weather_observed_at"]],
                                ignore_index=True).sort_values("observed_at").reset_index(drop=True)

    def setUp(self):
        self.app = AppTest.from_file(ROOT / "app_pages/roads.py", default_timeout=30)
        self.app.session_state["district_id"] = self.region_id
        self.options_patch = patch.object(q, "get_filter_options", return_value=self.options)
        self.options_patch.start()
        self.addCleanup(self.options_patch.stop)

    def run_page(self):
        self.app.run()
        self.assertFalse(self.app.exception, [e.message for e in self.app.exception])
        self.assertFalse(self.app.error, [e.value for e in self.app.error])

    def page_text(self):
        return "\n".join(e.value for kind in (self.app.subheader, self.app.markdown,
                                             self.app.caption, self.app.info, self.app.error)
                         for e in kind)

    def chart(self, phrase):
        return next(element.proto for element in self.app.get("vega_lite_chart")
                    if phrase in element.proto.alt)

    def chart_data(self, phrase):
        chart = self.chart(phrase)
        self.assertEqual(len(chart.datasets), 1)
        return convert_arrow_bytes_to_pandas_df(chart.datasets[0].data.data)

    def traffic_charts(self):
        return [e for e in self.app.get("vega_lite_chart") if "평균 수록 차량" in e.proto.alt]

    def test_real_hourly_profiles_and_seoul_averages_are_not_recomputed(self):
        with patch.object(q, "get_traffic_profile", wraps=q.get_traffic_profile) as query:
            self.run_page()
        query.assert_called_once_with(self.region_id)
        self.assertEqual(len(self.traffic_charts()), 2)
        domains = []
        for day in ("평일", "주말"):
            data = self.chart_data(f"{day} 시간대별")
            expected = self.profile.loc[self.profile.day_type == day].sort_values("hour_of_day")
            self.assertEqual(len(data), 48)
            for label, field in (("마포구", "avg_vehicles"), ("서울 구 평균", "seoul_avg_vehicles")):
                actual = data.loc[data.series_label == label]
                self.assertEqual(actual.hour_of_day.tolist(), list(range(24)))
                self.assertEqual(actual.vehicles.tolist(), expected[field].tolist())
            spec = json.loads(self.chart(f"{day} 시간대별").spec)
            domains.append(spec["encoding"]["y"]["scale"]["domain"])
        self.assertEqual(domains[0], domains[1])
        for phrase in (r"2026.09.01 \~ 2026.09.30", "24개 구", "관측 지점 수가 달라",
                       "공휴일은 따로", "실제 정체·소요 시간", "산술평균"):
            self.assertIn(phrase, self.page_text())

    def test_peak_and_low_times_match_actual_district_values(self):
        self.run_page()
        text = self.page_text()
        for day in ("평일", "주말"):
            frame = self.profile.loc[self.profile.day_type == day]
            for index in (frame.avg_vehicles.idxmax(), frame.avg_vehicles.idxmin()):
                row = frame.loc[index]
                hour = int(row.hour_of_day)
                self.assertIn(rf"**{hour:02d}\~{hour+1:02d}시** · 시간당 평균 {row.avg_vehicles:,.1f}대", text)
        self.assertIn("차를 끌고 나간다면", text)

    def test_district_change_and_unobserved_district_keep_weather(self):
        self.app.session_state["topic"] = "parking"
        for district in ("강남구", "강북구", "마포구"):
            with self.subTest(district=district):
                self.app.session_state["district_id"] = self.ids[district]
                with patch.object(q, "get_traffic_profile", wraps=q.get_traffic_profile) as query:
                    self.run_page()
                query.assert_called_once_with(self.ids[district])
                self.assertEqual(self.app.session_state["topic"], "parking")
                self.assertIn(district, self.app.subheader[0].value)
                if district == "강북구":
                    self.assertEqual(len(self.traffic_charts()), 0)
                    self.assertIn("강북구 교통량은 자료 없음", self.page_text())
                    self.assertNotIn("차량이 가장 적은 시간", self.page_text())
                else:
                    self.assertEqual(len(self.traffic_charts()), 2)
                self.assertEqual(len(self.chart_data("시간별 기온 표본")), 48)

    def test_absent_query_and_empty_query_do_not_hide_weather(self):
        for absent in (True, False):
            with self.subTest(absent=absent):
                replacement = (patch.object(q, "get_traffic_profile", None) if absent
                               else patch.object(q, "get_traffic_profile", return_value=pd.DataFrame()))
                with replacement:
                    self.run_page()
                self.assertEqual(len(self.traffic_charts()), 0)
                self.assertIn("교통량은 자료 없음", self.page_text())
                self.assertEqual(len(self.chart_data("시간별 기온 표본")), 48)

    def test_missing_day_preserves_the_other_day(self):
        frame = self.profile.loc[self.profile.day_type == "평일"]
        with patch.object(q, "get_traffic_profile", return_value=frame):
            self.run_page()
        self.assertEqual(len(self.traffic_charts()), 1)
        self.assertIn("주말 교통량은 자료 없음", self.page_text())
        self.assertIn("평일 시간대별", self.traffic_charts()[0].proto.alt)

    def test_missing_hours_break_each_series_independently(self):
        frame = self.profile.copy()
        frame.loc[(frame.day_type == "평일") & (frame.hour_of_day == 8), "avg_vehicles"] = float("nan")
        frame.loc[(frame.day_type == "평일") & (frame.hour_of_day == 10), "seoul_avg_vehicles"] = float("nan")
        with patch.object(q, "get_traffic_profile", return_value=frame):
            self.run_page()
        data = self.chart_data("평일 시간대별")
        for label, hour in (("마포구", 8), ("서울 구 평균", 10)):
            series = data.loc[data.series_label == label].set_index("hour_of_day")
            self.assertTrue(pd.isna(series.loc[hour, "vehicles"]))
            self.assertNotEqual(series.loc[hour-1, "segment"], series.loc[hour+1, "segment"])
        spec = json.loads(self.chart("평일 시간대별").spec)
        self.assertEqual(spec["encoding"]["detail"]["field"], "segment")
        self.assertIn("수록된 시간 중", self.page_text())

    def test_missing_seoul_average_does_not_become_zero(self):
        frame = self.profile.copy()
        frame["seoul_avg_vehicles"] = float("nan")
        with patch.object(q, "get_traffic_profile", return_value=frame):
            self.run_page()
        data = self.chart_data("평일 시간대별")
        self.assertTrue(data.loc[data.series_label == "서울 구 평균", "vehicles"].isna().all())
        self.assertEqual(len(self.traffic_charts()), 2)
        self.assertIn("서울 구 평균은 자료 없음", self.page_text())

    def test_tied_hours_are_all_shown_and_zero_has_no_arbitrary_peak(self):
        frame = self.profile.copy()
        frame["avg_vehicles"] = 100.0
        frame.loc[frame.hour_of_day.isin([8, 9, 18]), "avg_vehicles"] = 999.0
        frame.loc[frame.hour_of_day.isin([3, 4]), "avg_vehicles"] = 1.0
        with patch.object(q, "get_traffic_profile", return_value=frame):
            self.run_page()
        self.assertIn(r"**08\~10시, 18\~19시** (공동)", self.page_text())
        self.assertIn(r"**03\~05시** (공동)", self.page_text())
        frame["avg_vehicles"] = 0.0
        with patch.object(q, "get_traffic_profile", return_value=frame):
            self.run_page()
        self.assertIn("모든 시간 동일 · 시간당 평균 0.0대", self.page_text())
        self.assertNotIn(r"**00\~01시**", self.page_text())

    def test_partial_observations_warn_against_a_departure_recommendation(self):
        frame = self.profile.copy()
        frame["complete_hour_count"] = 0
        with patch.object(q, "get_traffic_profile", return_value=frame):
            self.run_page()
        self.assertIn("일부 관측 지점이 빠진", self.page_text())
        self.assertIn("시간대 차이가 왜곡", self.page_text())
        self.assertIn("출발 시간을 추천하기는 어려워요", self.page_text())
        frame["complete_hour_count"] = frame.observed_hour_count
        with patch.object(q, "get_traffic_profile", return_value=frame):
            self.run_page()
        self.assertNotIn("일부 관측 지점이 빠진", self.page_text())

    def test_weather_uses_only_explicit_sample_hours_and_preserves_null_rain(self):
        options = dict(self.options)
        options["weather_observed_at"] = [*options["weather_observed_at"], datetime(2027, 1, 1)]
        with patch.object(q, "get_filter_options", return_value=options), \
                patch.object(q, "get_weather", wraps=q.get_weather) as query:
            self.run_page()
        self.assertEqual(query.call_count, 48)
        self.assertEqual({call.args[0] for call in query.call_args_list}, set(self.options["weather_observed_at"]))
        data = self.chart_data("시간별 기온 표본")
        for field in ("temperature_c", "rain_mm"):
            pd.testing.assert_series_equal(data[field].reset_index(drop=True), self.weather[field],
                                           check_dtype=False, check_names=False)
        rain = self.chart_data("시간별 강수 표본")
        self.assertEqual(rain.rain_mm.isna().sum(), self.weather.rain_mm.isna().sum())
        for phrase in (r"2026.10.30\~31", "48시간 표본", "서울 108", "현재 날씨·예보가 아니에요",
                       "9월 교통량과는 기준 기간이 달라요", "강수 결측은 비가 오지 않았다는 뜻이 아니에요"):
            self.assertIn(phrase, self.page_text())

    def test_missing_weather_hour_breaks_the_temperature_line(self):
        missing = datetime(2026, 10, 30, 8)
        original = q.get_weather
        with patch.object(q, "get_weather", side_effect=lambda at:
                          pd.DataFrame() if at == missing else original(at)):
            self.run_page()
        frame = self.chart_data("시간별 기온 표본").set_index("observed_at")
        self.assertTrue(pd.isna(frame.loc[missing, "temperature_c"]))
        self.assertNotEqual(frame.loc[datetime(2026, 10, 30, 7), "segment"],
                            frame.loc[datetime(2026, 10, 30, 9), "segment"])
        self.assertIn("값이 있는 시간 47/48시간", self.page_text())

    def test_empty_weather_keeps_traffic_and_does_not_claim_no_rain(self):
        with patch.object(q, "get_weather", return_value=pd.DataFrame()):
            self.run_page()
        self.assertEqual(len(self.traffic_charts()), 2)
        self.assertEqual(len(self.app.get("vega_lite_chart")), 2)
        self.assertIn("기온 표본은 자료 없음", self.page_text())
        self.assertIn("강수 표본은 자료 없음", self.page_text())
        self.assertNotIn("0mm", self.page_text())

    def test_query_failure_is_redacted_and_weather_still_renders(self):
        with patch.object(q, "get_traffic_profile", side_effect=RuntimeError("private-connection-detail")):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.error), 1)
        self.assertNotIn("private-connection-detail", self.page_text())
        self.assertIn("자료를 불러오지 못했어요", self.page_text())
        self.assertEqual(len(self.chart_data("시간별 기온 표본")), 48)

    def test_missing_region_requests_a_selection_without_querying(self):
        del self.app.session_state["district_id"]
        with patch.object(q, "get_traffic_profile") as query:
            self.run_page()
        query.assert_not_called()
        self.assertIn("동네를 선택해 주세요", self.page_text())


if __name__ == "__main__":
    unittest.main()
