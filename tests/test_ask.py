from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import anthropic
import httpx2 as httpx
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from tests import app_env
import ask_service as ask


def response(reason="end_turn", text="조회한 자료를 알려드려요.", tools=()):
    blocks = ([SimpleNamespace(type="text", text=text)] if text else []) + list(tools)
    return SimpleNamespace(stop_reason=reason, content=blocks)


def tool(name="get_district_judgment", values=None, tool_id="tool_1"):
    return SimpleNamespace(type="tool_use", name=name,
                           input={"district": "마포"} if values is None else values, id=tool_id)


class FakeStream:
    def __init__(self, message, chunks=None, error_at=None):
        self.message = message
        self.chunks = chunks if chunks is not None else [
            block.text for block in message.content if block.type == "text"]
        self.error_at = error_at
        self.closed = False

    def __enter__(self):
        if self.error_at == "enter":
            raise ValueError("private error detail")
        return self

    def __exit__(self, *_):
        self.closed = True
        if self.error_at == "exit":
            raise ValueError("private error detail")

    @property
    def text_stream(self):
        yield from self.chunks
        if self.error_at == "iterate":
            raise ValueError("private error detail")

    def get_final_message(self):
        if self.error_at == "final":
            raise ValueError("private error detail")
        return self.message


class FakeClient:
    def __init__(self, *steps):
        self.steps = iter(steps)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self.stream))

    def stream(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        step = next(self.steps)
        if isinstance(step, Exception):
            raise step
        return step if isinstance(step, FakeStream) else FakeStream(step)


def fake_queries():
    queries = Mock()
    queries.get_filter_options.return_value = {"regions": pd.DataFrame({
        "district_name": pd.Series(ask.DISTRICTS, dtype="category"), "region_id": range(1, 26)})}
    frame = pd.DataFrame({
        "district_name": pd.Series(["강남구", "강서구", "마포구", "중구"], dtype="category"),
        "stat_month": [date(2026, 9, 1)] * 4,
        "ownership_value": [Decimal("1.25"), Decimal("0.9"), Decimal("0.8"), None],
        "ownership_rank": pd.Series([1, 2, 3, None], dtype="Int16"),
        "ownership_level": ["많은 편", "많은 편", "많은 편", "자료 없음"],
        "parking_value": [Decimal("0.2"), Decimal("0.1"), Decimal("0.1"), None],
        "parking_rank": pd.Series([1, 2, 2, None], dtype="Int16"),
        "parking_level": ["좋음", "좋음", "좋음", "자료 없음"],
        "need_value": [Decimal("4.2"), Decimal("1.1"), Decimal("2.3"), None],
        "need_rank": pd.Series([1, 3, 2, None], dtype="Int16"),
        "need_level": ["대중교통으로 충분"] * 3 + ["자료 없음"],
        "electric_count": pd.Series([65000, 800, None, 0], dtype="UInt16"),
        "vehicle_count": pd.Series([2**63 + 7, 1200, 1100, None], dtype="UInt64"),
        "electric_share_pct": [Decimal("3.25"), Decimal("2.5"), None, None],
        "need_stat_date": [date(2026, 10, 30)] * 4,
        "transit_observed_hour_count": [24, 24, 24, None],
        "transit_complete_hour_count": [24, 0, 24, None],
        "source_snapshot_id": [999] * 4,
    })
    queries.get_district_ranking.return_value = frame
    queries.get_summary_metrics.return_value = frame.iloc[:1]
    queries.get_compare_metrics.return_value = frame.iloc[[0, 2]]
    queries.get_registration_breakdown.return_value = pd.DataFrame({
        "district_name": ["마포구"] * 2, "stat_month": [date(2026, 9, 1)] * 2,
        "vehicle_type_name": ["승용차"] * 2, "fuel_scope_name": ["전체", "전기차"],
        "vehicle_count": pd.Series([65000, 800], dtype="UInt16"),
    })
    queries.search_faq.return_value = pd.DataFrame({
        "company_id": [1], "faq_key": ["example_1"],
        "company_name": ["예시 기업"], "category": ["충전"], "question": ["충전은 어떻게 해요?"],
        "answer_text": ["수집된 기업 안내예요."], "source_url": ["https://example.com/faq"],
        "fetched_on": [date(2026, 11, 1)],
    })
    return queries


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        # 실수로 실제 SDK 클라이언트를 쓰더라도 HTTP 요청은 나가지 않는다.
        self.addCleanup(patch.stopall)
        patch("httpx2.Client.send", side_effect=AssertionError("HTTP is disabled in ask tests")).start()


class ToolTest(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.queries = fake_queries()

    def test_all_district_names_and_short_names_are_validated(self):
        for district in ask.DISTRICTS:
            self.assertEqual(ask.normalize_district(district), district)
            self.assertEqual(ask.normalize_district(district[:-1]), district)
        for invalid in (None, 1, "서울", "부산", "서울 마포구", "마포구; DROP TABLE region", "강남구구"):
            with self.subTest(invalid=invalid), self.assertRaises(ask.InputError):
                ask.normalize_district(invalid)

    def test_invalid_or_extra_tool_inputs_never_query(self):
        invalid = [
            ("delete", {}), ("get_district_judgment", '{"district":"마포"}'),
            ("get_district_judgment", {}), ("get_district_judgment", {"district": "부산"}),
            ("get_district_judgment", {"district": "마포", "sql": "anything"}),
            ("compare_districts", {"district_a": "마포", "district_b": 1}),
            ("search_faq", {"keyword": None}), ("search_faq", {"keyword": "가" * 501}),
        ]
        for value in (True, 0, 26, 1.5, "3", None):
            invalid.append(("rank_districts", {"topic": "need", "order": "high", "limit": value}))
        for topic, order in (("score", "high"), ("need", "ascending"), ([], "high")):
            invalid.append(("rank_districts", {"topic": topic, "order": order, "limit": 3}))
        for name, values in invalid:
            with self.subTest(name=name, values=values):
                self.assertTrue(ask.execute_tool(name, values, self.queries).is_error)
        self.assertFalse(self.queries.mock_calls)

    def test_summary_json_preserves_null_big_integer_decimal_category_and_dates(self):
        result = ask.execute_tool("get_district_judgment", {"district": "강남"}, self.queries)
        self.assertFalse(result.is_error)
        row = json.loads(result.content)["rows"][0]
        self.assertEqual(row["electric_count"], 65000)
        self.assertEqual(row["vehicle_count"], 2**63 + 7)
        self.assertEqual(row["electric_share_pct"], 3.25)
        self.assertEqual(row["ownership_value"], 1.25)
        self.assertEqual(row["stat_month"], "2026-09-01")
        self.assertEqual(row["need_stat_date"], "2026-10-30")
        self.assertIsNone(row["population"])
        self.assertNotIn("source_snapshot_id", row)
        self.queries.get_summary_metrics.assert_called_once_with(1)

    def test_ranking_uses_existing_global_ranks_preserves_ties_and_omits_missing(self):
        high = ask.execute_tool("rank_districts", {"topic": "parking", "order": "high", "limit": 25}, self.queries)
        low = ask.execute_tool("rank_districts", {"topic": "parking", "order": "low", "limit": 2}, self.queries)
        assert high.evidence is not None and low.evidence is not None
        self.assertEqual([r["parking_rank"] for r in high.evidence["rows"]], [1, 2, 2])
        self.assertEqual([r["parking_rank"] for r in low.evidence["rows"]], [2, 2])
        need = ask.execute_tool("rank_districts", {"topic": "need", "order": "high", "limit": 3}, self.queries)
        assert need.evidence is not None
        self.assertEqual([r["district_name"] for r in need.evidence["rows"]], ["강남구", "마포구", "강서구"])
        self.assertTrue(any("강서구" in note and "일부 행정동" in note for note in need.evidence["notes"]))

    def test_compare_breakdown_and_faq_only_use_allowed_queries(self):
        compare = ask.execute_tool("compare_districts", {"district_a": "강남", "district_b": "마포구"}, self.queries)
        assert compare.evidence is not None
        self.assertEqual(len(compare.evidence["rows"]), 2)
        self.queries.get_compare_metrics.assert_called_once_with(1, 13)
        breakdown = ask.execute_tool("get_registration_breakdown", {"district": "마포"}, self.queries)
        assert breakdown.evidence is not None
        self.assertEqual([r["vehicle_count"] for r in breakdown.evidence["rows"]], [65000, 800])
        self.assertIn("더하지", breakdown.evidence["notes"][0])
        faq = ask.execute_tool("search_faq", {"keyword": "%_!"}, self.queries)
        assert faq.evidence is not None
        self.queries.search_faq.assert_called_once_with("%_!", limit=5)
        self.assertEqual(faq.evidence["rows"][0]["source_url"], "https://example.com/faq")

    def test_rows_are_bounded_and_database_errors_are_redacted(self):
        self.queries.get_summary_metrics.return_value = pd.concat([self.queries.get_district_ranking()] * 20)
        result = ask.execute_tool("get_district_judgment", {"district": "마포"}, self.queries)
        assert result.evidence is not None
        self.assertLessEqual(len(result.evidence["rows"]), 25)
        self.queries.search_faq.side_effect = RuntimeError("private database error detail")
        result = ask.execute_tool("search_faq", {"keyword": ""}, self.queries)
        self.assertTrue(result.is_error)
        self.assertNotIn("private", result.content)

    def test_no_rows_or_missing_rank_columns_are_explicit(self):
        self.queries.get_district_ranking.return_value = pd.DataFrame()
        result = ask.execute_tool("rank_districts", {"topic": "need", "order": "low", "limit": 1}, self.queries)
        assert result.evidence is not None
        self.assertFalse(result.is_error)
        self.assertEqual(result.evidence["rows"], [])
        self.assertIn("자료 없음", result.evidence["notes"])


class ConversationTest(OfflineTestCase):
    def test_request_contract_tool_batch_and_unchanged_thinking(self):
        thinking = SimpleNamespace(type="thinking", thinking="opaque", signature="unchanged")
        first = response("tool_use", text="자료를 살펴볼게요.", tools=[
            tool(), tool("search_faq", {"keyword": 123}, "tool_2")])
        first.content.insert(0, thinking)
        final = response(text="마포구 자료를 확인했어요.")
        client = FakeClient(first, final)
        conversation = ask.Conversation(client, "마포 알려줘", queries=fake_queries())
        chunks = list(conversation.stream())
        self.assertEqual(chunks, ["자료를 살펴볼게요.", "마포구 자료를 확인했어요."])
        self.assertEqual(conversation.answer.text, "마포구 자료를 확인했어요.")
        self.assertIs(conversation.messages[1]["content"], first.content)
        self.assertIs(conversation.messages[1]["content"][0], thinking)
        batch = client.calls[1]["messages"][2]
        self.assertEqual(batch["role"], "user")
        self.assertEqual([r["is_error"] for r in batch["content"]], [False, True])
        self.assertEqual([r["tool_use_id"] for r in batch["content"]], ["tool_1", "tool_2"])
        self.assertEqual(len(conversation.answer.evidence), 1)
        request = client.calls[0]
        self.assertEqual(set(request), {"model", "max_tokens", "betas", "fallbacks", "output_config", "system", "tools", "messages"})
        self.assertEqual(request["model"], "claude-opus-5-5")
        self.assertEqual(request["max_tokens"], 2000)
        self.assertEqual(request["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(request["fallbacks"], "default")
        self.assertEqual(request["output_config"], {"effort": "low"})
        self.assertEqual(request["system"], [{"type": "text", "text": ask.SYSTEM, "cache_control": {"type": "ephemeral"}}])
        self.assertTrue(all(t["eager_input_streaming"] for t in request["tools"]))

    def test_truncated_tool_calls_all_return_errors_without_queries(self):
        queries = Mock()
        first = response("max_tokens", text="", tools=[tool(), tool(tool_id="tool_2")])
        client = FakeClient(first, response())
        conversation = ask.Conversation(client, "마포 알려줘", queries=queries)
        list(conversation.stream())
        self.assertFalse(queries.mock_calls)
        results = client.calls[1]["messages"][2]["content"]
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["is_error"] for r in results))

    def test_pause_continues_and_limits_every_stop_reason_to_five_requests(self):
        client = FakeClient(response("pause_turn", "앞부분이에요. "), response(text="뒷부분이에요."))
        conversation = ask.Conversation(client, "마포 알려줘")
        list(conversation.stream())
        self.assertEqual(conversation.answer.text, "앞부분이에요. 뒷부분이에요.")
        for reason in ("pause_turn", "tool_use", "max_tokens"):
            client = FakeClient(*[response(reason, "", tools=[tool()]) for _ in range(6)])
            conversation = ask.Conversation(client, "마포 알려줘", queries=fake_queries())
            list(conversation.stream())
            self.assertEqual(len(client.calls), 5)
            self.assertTrue(conversation.answer.failed)

    def test_refusal_does_not_read_content_or_execute_tools(self):
        class Refused:
            stop_reason = "refusal"

            @property
            def content(self):
                raise AssertionError("refusal content must not be read")

        queries = Mock()
        client = FakeClient(FakeStream(Refused(), chunks=[]))
        conversation = ask.Conversation(client, "질문", queries=queries)
        list(conversation.stream())
        self.assertEqual(conversation.answer.text, ask.REFUSAL)
        self.assertFalse(conversation.answer.failed)
        self.assertFalse(queries.mock_calls)

    def test_previous_history_is_last_six_text_pairs_only(self):
        history = [{"question": f"질문 {i}", "answer": f"답 {i}", "evidence": [{"secret": "omit"}],
                    "thinking": "omit", "content": [tool()]} for i in range(9)]
        messages = ask.build_messages("현재 질문", history)
        self.assertEqual(len(messages), 13)
        self.assertEqual(messages[0], {"role": "user", "content": "질문 3"})
        self.assertTrue(all(isinstance(m["content"], str) for m in messages))
        self.assertNotIn("omit", json.dumps(messages))

    def test_api_error_classes_get_distinct_safe_messages(self):
        request = httpx.Request("POST", "https://example.com")
        errors: list[Exception] = [
            cls("private error detail", response=httpx.Response(code, request=request), body={})
            for cls, code in [(anthropic.BadRequestError, 400), (anthropic.AuthenticationError, 401),
                              (anthropic.RateLimitError, 429), (anthropic.APIStatusError, 500)]
        ]
        errors.append(anthropic.APIConnectionError(message="private error detail", request=request))
        messages = []
        for error in errors:
            conversation = ask.Conversation(FakeClient(error), "질문")
            list(conversation.stream())
            self.assertTrue(conversation.answer.failed)
            self.assertNotIn("private", conversation.answer.text)
            messages.append(conversation.answer.text)
        self.assertEqual(len(set(messages)), 5)

    def test_json_value_errors_are_caught_around_entire_context(self):
        for stage in ("enter", "iterate", "final", "exit"):
            with self.subTest(stage=stage):
                stream = FakeStream(response(), error_at=stage)
                conversation = ask.Conversation(FakeClient(stream), "질문")
                list(conversation.stream())
                self.assertTrue(conversation.answer.failed)
                self.assertNotIn("private", conversation.answer.text)
                if stage != "enter":
                    self.assertTrue(stream.closed)

    def test_empty_or_truncated_text_does_not_become_successful_answer(self):
        for message in (response(text=""), response("max_tokens", "잘린 답"), response("tool_use", "", tools=[])):
            conversation = ask.Conversation(FakeClient(message), "질문")
            list(conversation.stream())
            self.assertTrue(conversation.answer.failed)
            self.assertEqual(conversation.answer.text, ask.INCOMPLETE)


class LimitsAndExamplesTest(OfflineTestCase):
    def test_credentials_priority_no_key_and_client_options(self):
        self.assertEqual(ask.resolve_api_key({"anthropic": {"api_key": "test-only"}},
                                            {"ANTHROPIC_API_KEY": "environment-only"}), "test-only")
        self.assertEqual(ask.resolve_api_key({"anthropic": {"api_key": " "}},
                                            {"ANTHROPIC_API_KEY": "environment-only"}), "environment-only")
        self.assertIsNone(ask.resolve_api_key({}, {}))
        with patch("ask_service.anthropic.Anthropic") as constructor:
            ask.create_client("test-only")
        constructor.assert_called_once_with(api_key="test-only", timeout=30.0, max_retries=1)

    def test_invalid_question_and_session_limit_do_not_consume_daily_quota(self):
        quota = ask.DailyQuota()
        for question in (None, "", " ", "가" * 201):
            with self.assertRaises(ask.InputError):
                quota.reserve(question, 0)
        with self.assertRaises(ask.InputError):
            quota.reserve("질문", 10)
        self.assertEqual(quota.remaining(), 200)
        self.assertEqual(quota.reserve("가" * 200, 9), "가" * 200)
        self.assertEqual(quota.remaining(), 199)

    def test_process_limit_is_atomic_and_resets_on_seoul_calendar_day(self):
        today = [date(2026, 11, 9)]
        quota = ask.DailyQuota(today=lambda: today[0])

        def reserve(_):
            try:
                quota.reserve("질문", 0)
                return 1
            except ask.InputError:
                return 0

        with ThreadPoolExecutor(max_workers=12) as pool:
            self.assertEqual(sum(pool.map(reserve, range(250))), 200)
        self.assertEqual(quota.remaining(), 0)
        today[0] = date(2026, 11, 10)
        self.assertEqual(quota.remaining(), 200)

    def test_saved_examples_require_exact_question_and_valid_file(self):
        question = ask.EXAMPLE_QUESTIONS[0]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "examples.json"
            self.assertIsNone(ask.load_saved_example(question, path))
            path.write_text("invalid json", encoding="utf-8")
            self.assertIsNone(ask.load_saved_example(question, path))
            evidence = ask.execute_tool("compare_districts", {"district_a": "강남", "district_b": "마포"}, fake_queries()).evidence
            payload = {"schema_version": 1, "examples": [
                {"question": question, "answer": "저장한 답이에요.", "evidence": [evidence]}]}
            path.write_text(json.dumps(payload), encoding="utf-8")
            answer = ask.load_saved_example(question, path)
            assert answer is not None
            self.assertTrue(answer.saved)
            self.assertEqual(answer.evidence, [evidence])
            self.assertIsNone(ask.load_saved_example("비슷하지만 다른 질문", path))
            payload["examples"][0]["evidence"] = [{"rows": "broken"}]
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(ask.load_saved_example(question, path))


class AskPageTest(OfflineTestCase):
    def setUp(self):
        super().setUp()
        st.cache_resource.clear()
        self.addCleanup(st.cache_resource.clear)
        patch("ui.load_options", return_value={}).start()
        self.queries = fake_queries()
        for name in ("get_filter_options", "get_summary_metrics", "get_district_ranking", "get_compare_metrics",
                     "get_registration_breakdown", "search_faq"):
            patch.object(ask.q, name, getattr(self.queries, name)).start()
        self.key = patch("ask_service.resolve_api_key", return_value=None).start()
        self.factory = patch("ask_service.create_client").start()
        self.saved = patch("ask_service.load_saved_example", return_value=None).start()

    def page(self):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
        self.assertFalse(app.exception)
        app.switch_page("app_pages/ask.py").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def test_no_key_keeps_navigation_and_page_working_without_client(self):
        app = self.page()
        self.assertTrue(any("아직 연결되지" in item.value for item in app.info))
        self.assertTrue(app.chat_input(key="ask_prompt").disabled)
        self.assertEqual(len([b for b in app.button if b.key.startswith("ask_example_")]), 3)
        self.assertTrue(all(app.button(key=f"ask_example_{i}").disabled for i in range(3)))
        self.assertEqual(sum(link.value == "물어보기" for link in app.page_link), 3)
        app.switch_page("app_pages/faq.py").run()
        self.assertFalse(app.exception)
        self.factory.assert_not_called()

    def test_example_stream_evidence_history_and_cached_client(self):
        self.key.return_value = "test-only"
        client = FakeClient(response("tool_use", "", tools=[tool()]), response(text="근거를 확인했어요."))
        self.factory.return_value = client
        app = self.page()
        app.button(key="ask_example_0").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.session_state["ask_count"], 1)
        self.assertEqual(len(app.session_state["ask_history"]), 1)
        self.assertEqual(app.session_state["ask_history"][0]["answer"], "근거를 확인했어요.")
        self.assertEqual(len(app.expander), 1)
        self.assertEqual(app.dataframe[0].value["전기차(대)"].iloc[0], "65000")
        self.assertEqual(app.dataframe[0].value["주민(명)"].iloc[0], "자료 없음")
        self.assertFalse(any(b.key.startswith("ask_example_") for b in app.button))
        app.run()
        self.assertEqual(len(client.calls), 2)
        self.factory.assert_called_once()

    def test_chat_input_and_tenth_question_disable_future_submissions(self):
        self.key.return_value = "test-only"
        self.factory.return_value = FakeClient(response())
        app = self.page()
        app.session_state["ask_count"] = 9
        app.run()
        app.chat_input(key="ask_prompt").set_value("마포 알려줘").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.session_state["ask_count"], 10)
        self.assertTrue(app.chat_input(key="ask_prompt").disabled)
        self.assertTrue(any("10회를 모두" in item.value for item in app.info))

    def test_api_failure_shows_saved_example_label_and_original_evidence(self):
        self.key.return_value = "test-only"
        self.factory.return_value = FakeClient(ValueError("private error detail"))
        evidence = ask.execute_tool("search_faq", {"keyword": "충전"}, self.queries).evidence
        assert evidence is not None
        self.saved.return_value = ask.Answer(text="저장한 답이에요.", evidence=[evidence], saved=True)
        app = self.page()
        app.button(key="ask_example_0").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("미리 저장한 답변" in item.value for item in app.caption))
        self.assertEqual(app.session_state["ask_history"][0]["answer"], "저장한 답이에요.")
        self.assertEqual(len(app.dataframe), 1)
        self.assertFalse(any("private" in item.value for item in app.markdown))


if __name__ == "__main__":
    unittest.main()
