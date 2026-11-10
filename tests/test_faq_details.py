from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from tests import app_env
from db import queries as q
from ui import date_text


APP = Path(__file__).resolve().parents[1] / "app.py"


class FaqDetailsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = q.get_filter_options()

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

    def test_home_runs_no_page_detail_queries(self):
        query_names = (
            "get_summary_metrics", "get_registration_breakdown", "get_place_points",
            "search_places", "get_charger_summary", "get_charger_detail", "get_trend_data", "get_weather",
        )
        with ExitStack() as stack:
            calls = [stack.enter_context(patch.object(q, name, wraps=getattr(q, name))) for name in query_names]
            self.app.run()
            self.assert_ready()
            for query in calls:
                query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
