from datetime import date
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
DAYS = {date(2026, 10, 30): "10.30(금)", date(2026, 10, 31): "10.31(토)"}


class TransitPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ranking = q.get_district_ranking()
        cls.ids = dict(zip(cls.ranking.district_name.astype(str), cls.ranking.region_id.astype(int)))
        cls.region_id = cls.ids["마포구"]
        cls.trends = {day: q.get_trend_data(cls.region_id, stat_date=day, analysis_type="4") for day in DAYS}

    def setUp(self):
        self.app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        self.app.switch_page("app_pages/transit.py").run()
        self.assert_ready()

    def assert_ready(self):
        self.assertFalse(self.app.exception, [e.message for e in self.app.exception])
        self.assertFalse(self.app.error, [e.value for e in self.app.error])

    def page_text(self):
        return "\n".join(e.value for kind in (self.app.markdown, self.app.caption, self.app.info)
                         for e in kind)

    def hero(self):
        return next(e for e in self.app.get("bidi_component")
                    if e.proto.id.endswith("-transit_drive_hero"))

    def chart_data(self, mode):
        for chart in self.app.get("vega_lite_chart"):
            data = convert_arrow_bytes_to_pandas_df(chart.proto.datasets[0].data.data)
            if "mode_code" in data and set(data.mode_code) == {mode}:
                return chart, data
        self.fail(f"{mode} 승객 그래프 없음")

    def patch_trends(self, frames):
        return patch.object(q, "get_trend_data", side_effect=lambda region_id, stat_date, analysis_type:
                            frames[stat_date].copy())

    def test_real_judgment_dates_and_rank(self):
        row = self.ranking.loc[self.ranking.region_id == self.region_id].iloc[0]
        self.assertEqual([m.value for m in self.app.metric],
                         [str(row.need_level), f"{row.need_value:.2f}명", f"{int(row.need_rank)}위"])
        self.assertEqual(row.need_stat_date, date(2026, 10, 30))
        text = self.page_text()
        for expected in ("2026.10.30", "2026.10.31", "2026.09", "25구 안의 상대적 추정", "고유 주민 수"):
            self.assertIn(expected, text)
        props = json.loads(self.hero().proto.json)
        self.assertEqual(props["need_level"], str(row.need_level))
        self.assertEqual(props["district_id"], self.region_id)

    def test_queries_use_both_explicit_dates_and_single_analysis(self):
        with patch.object(q, "get_trend_data", wraps=q.get_trend_data) as query:
            self.app.run()
        self.assert_ready()
        self.assertEqual(query.call_count, 2)
        self.assertEqual({call.kwargs["stat_date"] for call in query.call_args_list}, set(DAYS))
        for call in query.call_args_list:
            self.assertEqual(call.args, (self.region_id,))
            self.assertEqual(call.kwargs["analysis_type"], "4")

    def test_all_96_chart_values_match_the_database(self):
        self.assertEqual(len(self.app.get("vega_lite_chart")), 2)
        for mode in ("bus", "subway"):
            chart, actual = self.chart_data(mode)
            self.assertEqual(len(actual), 48)
            spec = json.loads(chart.proto.spec)
            self.assertEqual(spec["encoding"]["y"]["field"], "known_passenger_sum")
            for day, label in DAYS.items():
                expected = self.trends[day].loc[
                    (self.trends[day].series_type == "passenger") & (self.trends[day].mode_code == mode)
                ].sort_values("hour_of_day")
                observed = actual.loc[actual.day_label == label].sort_values("hour_of_day")
                self.assertEqual(observed.hour_of_day.tolist(), list(range(24)))
                self.assertEqual(observed.known_passenger_sum.tolist(), expected.known_passenger_sum.tolist())

    def test_peak_times_use_each_mode_and_day(self):
        text = self.page_text()
        for day, frame in self.trends.items():
            for mode in ("bus", "subway"):
                series = frame.loc[(frame.series_type == "passenger") & (frame.mode_code == mode)]
                peak = series.loc[series.known_passenger_sum.idxmax()]
                hour = int(peak.hour_of_day)
                self.assertIn(DAYS[day], text)
                self.assertIn(f"**{hour:02d}~{hour+1:02d}시** · {int(peak.known_passenger_sum):,}명", text)
                quiet = series.loc[series.known_passenger_sum.idxmin()]
                hour = int(quiet.hour_of_day)
                self.assertIn(f"· {int(quiet.known_passenger_sum):,}명", text)
                if series.known_passenger_sum.eq(quiet.known_passenger_sum).sum() == 1:
                    self.assertIn(f"**{hour:02d}~{hour+1:02d}시**", text)
        self.assertEqual(text.count("가장 한산한 시간"), 4)
        self.assertIn("차량 안 혼잡도나 평소 이용량을 뜻하지 않아요", text)

    def test_district_selection_preserves_component_key_and_shared_state(self):
        component_id = self.hero().proto.id
        self.app.session_state["topic"] = "parking"
        for district in ("강서구", "중구", "종로구", "마포구"):
            with self.subTest(district=district):
                region_id = self.ids[district]
                self.app.selectbox(key="district_id").select(region_id).run()
                self.assert_ready()
                row = self.ranking.loc[self.ranking.region_id == region_id].iloc[0]
                self.assertEqual(self.app.metric[0].value, str(row.need_level))
                self.assertEqual(self.app.session_state["selected_region_id"], region_id)
                self.assertEqual(self.app.session_state["topic"], "parking")
                self.assertEqual(self.hero().proto.id, component_id)
                self.assertEqual(json.loads(self.hero().proto.json)["district_name"], district)
                self.assertIn("중구·종로구는 출퇴근 유입", self.page_text())
                if district == "강서구":
                    self.assertIn("일부 행정동 자료가 빠져", self.page_text())
        self.app.switch_page("app_pages/national.py").run()
        self.app.switch_page("app_pages/transit.py").run()
        self.assert_ready()
        self.assertEqual(self.app.selectbox(key="district_id").value, self.region_id)

    def test_missing_need_value_cannot_leave_a_stale_verdict_or_rank(self):
        frame = self.ranking.copy()
        frame["need_value"] = pd.NA
        with patch.object(q, "get_district_ranking", return_value=frame):
            self.app.run()
        self.assert_ready()
        self.assertEqual([m.value for m in self.app.metric], ["자료 없음"] * 3)
        self.assertEqual(json.loads(self.hero().proto.json)["need_level"], "자료 없음")
        self.assertEqual(len(self.app.get("vega_lite_chart")), 2)

    def test_empty_ranking_still_shows_selected_name_and_passengers(self):
        with patch.object(q, "get_district_ranking", return_value=pd.DataFrame()):
            self.app.run()
        self.assert_ready()
        self.assertEqual(json.loads(self.hero().proto.json)["district_name"], "마포구")
        self.assertEqual([m.value for m in self.app.metric], ["자료 없음"] * 3)
        self.assertEqual(len(self.app.get("vega_lite_chart")), 2)

    def test_empty_trends_preserve_missing_values_and_benefits(self):
        with patch.object(q, "get_trend_data", return_value=pd.DataFrame()):
            self.app.run()
        self.assert_ready()
        self.assertEqual(len(self.app.get("vega_lite_chart")), 0)
        self.assertIn("버스 시간대별 승객은 자료 없음", self.page_text())
        self.assertIn("지하철 시간대별 승객은 자료 없음", self.page_text())
        self.assertNotIn("0명", self.page_text())
        for title in ("주차 걱정 없음", "차 유지 부담 없음", "이동 시간 활용"):
            self.assertIn(title, self.page_text())

    def test_one_missing_day_does_not_hide_the_other(self):
        frames = dict(self.trends)
        frames[date(2026, 10, 31)] = pd.DataFrame()
        with self.patch_trends(frames):
            self.app.run()
        self.assert_ready()
        for mode in ("bus", "subway"):
            _, data = self.chart_data(mode)
            self.assertTrue(data.loc[data.day_label == DAYS[date(2026, 10, 31)], "known_passenger_sum"].isna().all())
            self.assertEqual(data.known_passenger_sum.notna().sum(), 24)
        self.assertIn("10.31(토)", self.page_text())
        self.assertEqual(self.page_text().count("**자료 없음**"), 4)

    def test_missing_hour_is_not_zero_and_breaks_the_line(self):
        frames = {day: frame.copy() for day, frame in self.trends.items()}
        day = date(2026, 10, 30)
        frame = frames[day]
        frames[day] = frame.loc[~((frame.mode_code == "bus") & (frame.hour_of_day == 8))]
        with self.patch_trends(frames):
            self.app.run()
        self.assert_ready()
        chart, data = self.chart_data("bus")
        weekday = data.loc[data.day_label == DAYS[day]].set_index("hour_of_day")
        self.assertTrue(pd.isna(weekday.loc[8, "known_passenger_sum"]))
        self.assertNotEqual(weekday.loc[7, "segment"], weekday.loc[9, "segment"])
        self.assertEqual(json.loads(chart.proto.spec)["encoding"]["detail"]["field"], "segment")
        self.assertIn("수록된 시간 중", self.page_text())

    def test_total_and_other_analysis_values_are_never_added(self):
        frames = {}
        for day, source in self.trends.items():
            frame = source.copy()
            frame.loc[frame.mode_code == "total", "known_passenger_sum"] = 99_999_999
            other = source.copy()
            other["analysis_type"] = "other"
            other["known_passenger_sum"] = 88_888_888
            frames[day] = pd.concat([frame, other], ignore_index=True)
        with self.patch_trends(frames):
            self.app.run()
        self.assert_ready()
        self.test_all_96_chart_values_match_the_database()

    def test_saturday_partial_coverage_has_a_notice(self):
        frames = {day: frame.copy() for day, frame in self.trends.items()}
        frames[date(2026, 10, 31)]["valid_dong_count"] = 1
        with self.patch_trends(frames):
            self.app.run()
        self.assert_ready()
        self.assertIn("일부 행정동 자료가 빠져", self.page_text())
        self.test_all_96_chart_values_match_the_database()

    def test_tied_peaks_are_all_reported_without_summing(self):
        frames = {day: frame.copy() for day, frame in self.trends.items()}
        weekday = frames[date(2026, 10, 30)]
        weekday.loc[weekday.mode_code == "bus", "known_passenger_sum"] = 0
        weekday.loc[(weekday.mode_code == "bus") & weekday.hour_of_day.isin([8, 18]), "known_passenger_sum"] = 12_345
        with self.patch_trends(frames):
            self.app.run()
        self.assert_ready()
        self.assertIn("**08~09시, 18~19시 (공동)** · 12,345명", self.page_text())
        self.assertIn("**00~08시, 09~18시, 19~24시 (공동)** · 0명", self.page_text())

    def test_observed_zero_is_different_from_missing(self):
        frames = {day: frame.copy() for day, frame in self.trends.items()}
        for frame in frames.values():
            frame["known_passenger_sum"] = 0
        with self.patch_trends(frames):
            self.app.run()
        self.assert_ready()
        self.assertEqual(len(self.app.get("vega_lite_chart")), 2)
        self.assertEqual(self.page_text().count("수록 승객 모두 0명 · 붐비는 시간 없음"), 4)
        self.assertEqual(self.page_text().count("**모든 시간 동일** · 0명"), 4)

    def test_quiet_hours_ignore_missing_and_report_all_ties(self):
        frames = {day: frame.copy() for day, frame in self.trends.items()}
        weekday = frames[date(2026, 10, 30)]
        bus = weekday.mode_code.eq("bus")
        weekday.loc[bus, "known_passenger_sum"] = 5
        weekday.loc[bus & weekday.hour_of_day.isin([2, 3]), "known_passenger_sum"] = float("nan")
        weekday.loc[bus & weekday.hour_of_day.isin([8, 9]), "known_passenger_sum"] = 1
        with self.patch_trends(frames):
            self.app.run()
        self.assert_ready()
        self.assertIn("수록된 시간 중 **08~10시 (공동)** · 1명", self.page_text())
        self.assertNotIn("**02~04시 (공동)** · 0명", "\n".join(
            element.value for element in self.app.markdown[:8]))

    def test_query_failure_does_not_expose_connection_details(self):
        with patch.object(q, "get_trend_data", side_effect=RuntimeError("private-connection-detail")):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.error), 2)
        self.assertTrue(all("자료를 불러오지 못했어요" in e.value for e in self.app.error))
        self.assertNotIn("private-connection-detail", self.page_text())
        self.assertIn("이동 시간 활용", self.page_text())

    def test_benefit_cards_have_no_unsubstantiated_numbers(self):
        from scene_drive import hero_props
        for raw in (None, float("nan"), float("inf")):
            frame = pd.DataFrame([{"region_id": 1, "need_value": raw, "need_level": "대중교통으로 충분"}])
            self.assertEqual(hero_props(frame, 1, "테스트구")["need_level"], "자료 없음")
        for title in ("주차 걱정 없음", "차 유지 부담 없음", "이동 시간 활용"):
            elements = list(self.app.markdown)
            index = next(i for i, element in enumerate(elements) if title in element.value)
            contents = elements[index].value + elements[index + 1].value
            self.assertNotRegex(contents, r"\d")


if __name__ == "__main__":
    unittest.main()
