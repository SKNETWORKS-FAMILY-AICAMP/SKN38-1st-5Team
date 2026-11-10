import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
import pyarrow as pa
from streamlit.testing.v1 import AppTest


PAGE = Path(__file__).resolve().parents[1] / "app_pages/national.py"


class NationalKpiTest(unittest.TestCase):
    def setUp(self):
        rows = []
        counts = {
            "서울": ((80, 10, 10), (30, 5, 5)),
            "경기": ((400, 100, 0), (100, 20, 0)),
            "인천": ((40, 10, 0), (20, 0, 0)),
            "전남광주": ((90, 10, 0), (900, 180, 0)),
        }
        types = [("passenger", "승용"), ("truck", "화물")]
        usages = ["private", "commercial", "official"]
        for province, parts in counts.items():
            for (code, name), values in zip(types, parts):
                for usage, count in zip(usages, values):
                    rows.append((province, pd.Timestamp("2026-01-01"), code, name, usage, count))
        self.frame = pd.DataFrame(rows, columns=pd.Index([
            "province_name", "stat_month", "vehicle_type_code", "vehicle_type_name", "usage_code", "vehicle_count",
        ]))
        self.frame["vehicle_count"] = self.frame.vehicle_count.astype("int32")
        options = {"provinces": list(counts), "usage_codes": usages,
                   "vehicle_types": pd.DataFrame(types, columns=pd.Index(["vehicle_type_code", "vehicle_type_name"]))}
        for mocked in (patch("db.queries.get_filter_options", return_value=options),
                       patch("db.queries.get_national_registrations", side_effect=self.filtered)):
            mocked.start()
            self.addCleanup(mocked.stop)

    def filtered(self, province_name=None, vehicle_type_code=None, usage_code=None):
        frame = self.frame
        for column, selected in (("province_name", province_name), ("vehicle_type_code", vehicle_type_code),
                                 ("usage_code", usage_code)):
            if selected is not None:
                frame = frame.loc[frame[column].eq(selected)]
        return frame

    def page(self):
        app = AppTest.from_string(
            f"import streamlit as st\nst.navigation([st.Page({str(PAGE)!r}, title='전국 등록 조회')]).run()",
            default_timeout=15,
        ).run()
        self.ready(app)
        return app

    def ready(self, app):
        self.assertFalse(app.exception, [item.message for item in app.exception])
        self.assertFalse(app.error, [item.value for item in app.error])

    @staticmethod
    def metrics(app):
        return {metric.label: metric.value for metric in app.metric}

    @staticmethod
    def captions(app):
        return "\n".join(item.value for item in app.caption)

    @staticmethod
    def chart(app):
        proto = app.get("vega_lite_chart")[0].proto
        payload = proto.datasets[0].data.data if proto.datasets else proto.data.data
        return pa.ipc.open_stream(payload).read_all().to_pandas(), json.loads(proto.spec)

    def test_kpis_use_ratios_of_sums_and_show_scope(self):
        original = self.frame.copy(deep=True)
        app = self.page()
        self.assertEqual(self.metrics(app), {"전국 합계": "2,010대", "수도권 비중": "41.3%",
                                            "영업용 비중": "16.7%", "승용 비중": "37.3%"})
        captions = self.captions(app)
        for text in ("서울·경기·인천 · 830대", "전체 시도 · 전체 차종 · 전체 용도",
                     "분모는 현재 조건 합계 2,010대", "4개 지역", "전남광주", "이륜차"):
            self.assertIn(text, captions)
        pd.testing.assert_frame_equal(self.frame, original)

    def test_type_and_usage_filters_update_all_four_kpis(self):
        app = self.page()
        app.selectbox(key="national_type").select("passenger")
        app.selectbox(key="national_usage").select("commercial").run()
        self.ready(app)
        self.assertEqual(self.metrics(app), {"전국 합계": "130대", "수도권 비중": "92.3%",
                                            "영업용 비중": "100.0%", "승용 비중": "100.0%"})
        self.assertIn("전체 시도 · 승용 · 영업용", self.captions(app))
        self.assertEqual(len(app.dataframe[0].value), 4)

    def test_province_filter_hides_capital_and_excluded_categories_are_zero(self):
        app = self.page()
        app.selectbox(key="national_province").select("서울")
        app.selectbox(key="national_type").select("truck")
        app.selectbox(key="national_usage").select("private").run()
        self.ready(app)
        self.assertEqual(self.metrics(app), {"선택 조건 합계": "30대", "영업용 비중": "0.0%", "승용 비중": "0.0%"})
        self.assertIn("분모는 현재 조건 합계 30대", self.captions(app))
        app.selectbox(key="national_province").select(None).run()
        self.ready(app)
        self.assertIn("수도권 비중", self.metrics(app))

    def test_both_stack_modes_preserve_totals_and_order_from_query_values(self):
        app = self.page()
        for mode, column in (("용도별", "usage_code"), ("차종별", "vehicle_type_code")):
            with self.subTest(mode=mode):
                app.segmented_control(key="national_split").set_value(mode).run()
                self.ready(app)
                chart, spec = self.chart(app)
                expected = self.frame.groupby(["province_name", column]).vehicle_count.sum().to_dict()
                self.assertEqual(chart.set_index(["province_name", column]).vehicle_count.to_dict(), expected)
                self.assertEqual(int(chart.vehicle_count.sum()), 2010)
                self.assertEqual(spec["encoding"]["x"]["stack"], "zero")
                self.assertEqual(spec["encoding"]["y"]["sort"], ["전남광주", "경기", "서울", "인천"])
                self.assertEqual(spec["encoding"]["y"]["axis"]["values"], ["전남광주", "경기", "서울", "인천"])
                self.assertIn("segment_name", [item["field"] for item in spec["encoding"]["tooltip"]])
        self.frame.loc[self.frame.province_name.eq("인천"), "vehicle_count"] = 1000
        app.run()
        self.ready(app)
        self.assertEqual(self.chart(app)[1]["encoding"]["y"]["sort"][0], "인천")

    def test_missing_counts_are_not_partial_totals_or_partial_stacks(self):
        self.frame["vehicle_count"] = self.frame.vehicle_count.astype("Int64")
        self.frame.loc[0, "vehicle_count"] = pd.NA
        original = self.frame.copy(deep=True)
        app = self.page()
        self.assertEqual(set(self.metrics(app).values()), {"자료 없음"})
        self.assertIn("자료 없음", app.dataframe[0].value["등록 대수"].tolist())
        self.assertIn("합계 자료 없음: 서울", self.captions(app))
        for mode in ("용도별", "차종별"):
            app.segmented_control(key="national_split").set_value(mode).run()
            self.ready(app)
            self.assertNotIn("서울", self.chart(app)[0].province_name.tolist())
        pd.testing.assert_frame_equal(self.frame, original)

    def test_zero_denominator_does_not_produce_a_percentage(self):
        self.frame["vehicle_count"] = 0
        app = self.page()
        self.assertEqual(self.metrics(app), {"전국 합계": "0대", "수도권 비중": "자료 없음",
                                            "영업용 비중": "자료 없음", "승용 비중": "자료 없음"})

    def test_absent_unfiltered_category_is_missing_instead_of_zero(self):
        self.frame = self.frame.loc[self.frame.usage_code.ne("commercial")
                                    & self.frame.vehicle_type_code.ne("passenger")]
        app = self.page()
        self.assertEqual(self.metrics(app)["영업용 비중"], "자료 없음")
        self.assertEqual(self.metrics(app)["승용 비중"], "자료 없음")

    def test_large_integer_counts_do_not_overflow(self):
        self.frame["vehicle_count"] = pd.Series(2_000_000_000, index=self.frame.index, dtype="int32")
        app = self.page()
        self.assertEqual(self.metrics(app)["전국 합계"], "48,000,000,000대")
        self.assertEqual(self.metrics(app)["수도권 비중"], "75.0%")
        self.assertEqual(int(self.chart(app)[0].vehicle_count.sum()), 48_000_000_000)

    def test_empty_result_keeps_all_filters(self):
        self.frame = self.frame.iloc[:0]
        app = self.page()
        self.assertTrue(app.info)
        self.assertFalse(app.metric)
        self.assertFalse(app.get("vega_lite_chart"))
        self.assertFalse(app.dataframe)
        self.assertEqual({item.key for item in app.selectbox},
                         {"national_province", "national_type", "national_usage"})


if __name__ == "__main__":
    unittest.main()
