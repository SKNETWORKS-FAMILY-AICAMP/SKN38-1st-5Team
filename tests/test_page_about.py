from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from sqlalchemy import inspect
from streamlit.testing.v1 import AppTest

from tests import app_env
from db import queries as q
from db.connection import get_engine
from ui import date_text


ROOT = Path(__file__).resolve().parents[1]
HARNESS = f"""
import streamlit as st
st.navigation([
    st.Page({str(ROOT / 'app_pages/faq.py')!r}, title="FAQ", default=True),
    st.Page({str(ROOT / 'app_pages/about.py')!r}, title="자료 안내", url_path="about"),
], position="hidden").run()
"""


class AboutFaqTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = q.get_filter_options()
        cls.company_faq = q.search_faq()
        cls.table_names = inspect(get_engine()).get_table_names()

    def setUp(self):
        options = patch.object(q, "get_filter_options", return_value=self.options)
        self.options_query = options.start()
        self.addCleanup(options.stop)
        self.app = AppTest.from_string(HARNESS, default_timeout=30).run()
        self.assert_ready()

    def assert_ready(self):
        self.assertFalse(self.app.exception, [item.message for item in self.app.exception])

    def page_text(self):
        return "\n".join(str(item.value)
                         for group in (self.app.markdown, self.app.caption, self.app.info,
                                       self.app.text, self.app.subheader)
                         for item in group)

    def open_company(self):
        self.app.segmented_control(key="faq_kind").set_value("기업 FAQ").run()
        self.assert_ready()

    def open_about(self, section="출처·기준일"):
        self.app.switch_page(str(ROOT / "app_pages/about.py")).run()
        if section != "출처·기준일":
            self.app.segmented_control(key="about_section").set_value(section).run()
        self.assert_ready()

    def test_service_faq_is_default_and_needs_no_database(self):
        self.assertEqual(self.app.segmented_control(key="faq_kind").value, "차차차 FAQ")
        self.options_query.assert_not_called()
        self.assertGreaterEqual(len(self.app.expander), 10)
        self.assertLessEqual(len(self.app.expander), 13)
        self.assertEqual(len({item.key for item in self.app.expander}), len(self.app.expander))
        self.assertFalse(self.app.selectbox)
        with patch.object(q, "search_faq") as query:
            self.app.run()
            query.assert_not_called()
        for phrase in ("차량 보유 현황", "주차하기 좋은 동네", "차가 꼭 필요한 동네",
                       "1위부터 8위", "9위부터 17위", "18위부터 25위", "절대 기준을 정할 근거 자료",
                       "2026.09", "2026.10.30~31", "2013년", "아파트", "관리번호",
                       "좌표", "실시간", "서울 25구", "로그인이나 회원가입 없이",
                       "Claude API", "개인정보나 비밀정보는 질문에 적지", "기업 FAQ"):
            self.assertIn(phrase, self.page_text())

    def test_company_faq_keeps_answers_sources_and_dates(self):
        self.open_company()
        self.assertCountEqual([item.label for item in self.app.expander],
                              self.company_faq.question.tolist())
        for _, row in self.company_faq.iterrows():
            expander = self.app.expander(key=f"faq_{row.company_id}_{row.faq_key}")
            self.assertIn(str(row.answer_text), [item.value for item in expander.markdown])
            self.assertIn(date_text(row.fetched_on), "\n".join(item.value for item in expander.caption))
            self.assertEqual(expander.link_button[0].url, row.source_url)

    def test_company_filters_empty_results_and_reset(self):
        self.open_company()
        company = int(self.options["faq_companies"].iloc[0].company_id)
        category = self.options["faq_categories"][0]
        with patch.object(q, "search_faq", wraps=q.search_faq) as query:
            self.app.text_input(key="faq_keyword").set_value("  충전  ")
            self.app.selectbox(key="faq_company").select(company)
            self.app.selectbox(key="faq_category").select(category).run()
            query.assert_called_with("충전", company_id=company, category=category, limit=50)
        expected = q.search_faq("충전", company_id=company, category=category)
        self.assertCountEqual([item.label for item in self.app.expander], expected.question.tolist())
        self.app.text_input(key="faq_keyword").set_value("없는질문xyz987").run()
        self.assert_ready()
        self.assertFalse(self.app.expander)
        self.assertIn("조건에 맞는 질문", self.page_text())
        self.app.button(key="faq_reset").click().run()
        self.assert_ready()
        self.assertEqual(self.app.text_input(key="faq_keyword").value, "")
        self.assertIsNone(self.app.selectbox(key="faq_company").value)
        self.assertIsNone(self.app.selectbox(key="faq_category").value)
        self.assertEqual(len(self.app.expander), len(self.company_faq))

    def test_company_filters_survive_switching_faq_kind(self):
        self.open_company()
        company = int(self.options["faq_companies"].iloc[0].company_id)
        category = self.options["faq_categories"][0]
        self.app.text_input(key="faq_keyword").set_value("충전")
        self.app.selectbox(key="faq_company").select(company)
        self.app.selectbox(key="faq_category").select(category).run()
        self.app.segmented_control(key="faq_kind").set_value("차차차 FAQ").run()
        self.assert_ready()
        self.assertFalse(self.app.text_input)
        self.open_company()
        self.assertEqual(self.app.text_input(key="faq_keyword").value, "충전")
        self.assertEqual(self.app.selectbox(key="faq_company").value, company)
        self.assertEqual(self.app.selectbox(key="faq_category").value, category)

    def test_company_missing_fields_and_invalid_links_stay_explicit(self):
        frame = self.company_faq.iloc[:1].copy()
        frame["answer_text"] = None
        frame["fetched_on"] = pd.NaT
        for url in (None, "https:///missing-host", "javascript:alert(1)"):
            with self.subTest(url=url):
                frame["source_url"] = url
                with patch.object(q, "search_faq", return_value=frame):
                    self.open_company()
                self.assertFalse(self.app.link_button)
                self.assertIn("원문 링크: 자료 없음", self.page_text())
                self.assertNotIn("NaT", self.page_text())

    def test_sources_show_all_actual_snapshots_and_completeness_limits(self):
        self.open_about()
        expected = self.options["snapshots"]
        table = self.app.dataframe[0].value
        self.assertEqual(len(table), len(expected))
        self.assertEqual(len(table), 11)
        self.assertTrue(all("·" in name or "주차장" in name for name in table["자료"]))
        self.assertEqual(table["수집일"].tolist(), expected.collected_on.map(date_text).tolist())
        self.assertEqual(table["수록 범위·누락"].nunique(), len(expected))
        self.assertTrue(table["수록 범위·누락"].str.endswith("요.").all())
        self.assertFalse(table["수록 범위·누락"].str.contains("NULL|ASOS|API|고정 수집본").any())
        original_notes = [item.value.removeprefix("수집 기록 원문: ").replace(r"\~", "~")
                          for item in self.app.caption if item.value.startswith("수집 기록 원문: ")]
        self.assertEqual(original_notes, expected.coverage_note.tolist())
        self.assertTrue((table["완전성"] == "검수 완료").all())
        for index, row in enumerate(expected.itertuples()):
            if pd.isna(row.reference_start) and pd.isna(row.reference_end):
                self.assertEqual(table.iloc[index]["기준 기간"], "자료 없음")
            else:
                self.assertEqual(table.iloc[index]["기준 기간"],
                                 f"{date_text(row.reference_start)} ~ {date_text(row.reference_end)}")
        self.assertIn("모든 지역·시설·관측값이 빠짐없이 있다는 뜻은 아니에요", self.page_text())

    def test_unknown_source_missing_dates_and_repeated_snapshots_are_preserved(self):
        snapshots = self.options["snapshots"].iloc[[0, 0]].copy().reset_index(drop=True)
        snapshots["source_code"] = "future_source"
        snapshots["reference_start"] = None
        snapshots["reference_end"] = None
        snapshots["collected_on"] = None
        snapshots["coverage_note"] = None
        self.options_query.return_value = {"snapshots": snapshots}
        self.open_about()
        table = self.app.dataframe[0].value
        self.assertEqual(len(table), 2)
        self.assertEqual(table["자료"].tolist(), ["future_source", "future_source"])
        for column in ("기준 기간", "수집일", "수록 범위·누락"):
            self.assertEqual(table[column].tolist(), ["자료 없음", "자료 없음"])

    def test_collection_summary_counts_each_source_once_and_details_keep_methods(self):
        snapshots = self.options["snapshots"].iloc[[0] * 5].copy().reset_index(drop=True)
        snapshots["source_code"] = ["first", "first", "second", "third", "fourth"]
        snapshots["collection_method"] = ["api", "crawl", "api", "crawl", "file"]
        self.options_query.return_value = {"snapshots": snapshots}
        self.open_about()
        self.assertIn("API 조회 2종 · 웹 수집 1종 · 파일 수집 1종", self.page_text())
        self.assertEqual(len(self.app.dataframe[0].value), 5)
        methods = [item.value for item in self.app.expander(key="about_coverage").caption
                   if item.value.startswith("수집 방법:")]
        self.assertEqual(methods, ["수집 방법: API 조회", "수집 방법: 웹 수집", "수집 방법: API 조회",
                                   "수집 방법: 웹 수집", "수집 방법: 파일 수집"])

    def test_missing_sources_do_not_hide_criteria(self):
        for snapshots in (None, pd.DataFrame()):
            with self.subTest(snapshots=type(snapshots).__name__):
                self.options_query.return_value = {"snapshots": snapshots}
                self.open_about()
                self.app.segmented_control(key="about_section").set_value("출처·기준일").run()
                self.assertFalse(self.app.dataframe)
                self.assertIn("자료 없음", self.page_text())
                self.assertNotIn("API 조회", self.page_text())
                self.app.segmented_control(key="about_section").set_value("판정 기준").run()
                self.assert_ready()
                self.assertEqual(len(self.app.table[0].value), 3)

    def test_source_failure_is_sanitized_and_other_sections_remain_available(self):
        self.options_query.side_effect = RuntimeError("private-database-connection-detail")
        self.open_about()
        self.assertTrue(self.app.error)
        self.assertNotIn("private-database", self.page_text())
        self.assertNotIn("private-database", "\n".join(item.value for item in self.app.error))
        self.app.segmented_control(key="about_section").set_value("DB 구성").run()
        self.assert_ready()
        self.assertFalse(self.app.error)
        self.assertEqual(len(self.app.dataframe[0].value), 18)

    def test_criteria_keep_rank_direction_and_relative_interpretation(self):
        self.open_about("판정 기준")
        table = self.app.table[0].value.set_index("질문")
        for question, labels in (
            ("차량 보유 현황", ["많은 편", "보통", "적은 편"]),
            ("주차하기 좋은 동네", ["좋음", "보통", "빠듯함"]),
            ("차가 꼭 필요한 동네", ["대중교통으로 충분", "있으면 편함", "차가 필요한 편"]),
        ):
            self.assertEqual(table.loc[question, ["1~8위", "9~17위", "18~25위"]].tolist(), labels)
        for phrase in ("동률", "다음 순위는 건너뛰", "절대 기준을 정할 근거 자료",
                       "차 100대당", "2026.10.30", "강서구", "고유 주민 수"):
            self.assertIn(phrase, self.page_text())

    def test_database_summary_matches_all_18_physical_tables_and_has_erd(self):
        self.open_about("DB 구성")
        table = self.app.dataframe[0].value
        self.assertEqual(len(table), 18)
        self.assertCountEqual(table["표 이름"].tolist(), self.table_names)
        image = self.app.get("image")[0].proto.imgs[0]
        self.assertTrue(image.url.endswith(".png"))
        self.assertIn("18표 관계도", image.alt)
        self.assertTrue((ROOT / "docs/erd_core.png").is_file())

    def test_limitations_explain_observation_gaps_and_time_periods(self):
        self.open_about("자료의 한계")
        for phrase in ("2026.09", r"2026.10.30\~31", "전월 대비", "아파트", "실시간 빈자리",
                       "환경공단", "합산하지", "강서구", "강북구", "관측 지점·방향",
                       "48시간", "구별 실측", "2013년", "16개 시도", "전남광주", "자료 없음"):
            self.assertIn(phrase, self.page_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
