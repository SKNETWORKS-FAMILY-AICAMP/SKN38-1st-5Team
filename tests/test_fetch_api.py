# API 응답 fixture는 명세를 바탕으로 만든 가짜 데이터다.

from __future__ import annotations

import contextlib
import copy
import csv
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import quote

import requests

from etl import fetch_asos, fetch_ev_chargers
from etl.fetch_api_common import (ApiClient, FetchError, RequestBudget, collect_page,
                                  parse_page, run_cli, save_snapshot, validate_budget)

FIXTURE = Path(__file__).parent / "fixtures"
PROJECT = Path(__file__).resolve().parents[1]
NETWORK_GUARD = patch("requests.sessions.Session.request", side_effect=AssertionError("테스트 네트워크 금지"))


def setUpModule():
    NETWORK_GUARD.start()


def tearDownModule():
    NETWORK_GUARD.stop()


def fixture(name):
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


def response(payload=None, status=200, xml=None):
    result = Mock(status_code=status, content=xml)
    result.json.return_value = payload
    if xml is not None:
        result.json.side_effect = ValueError("가짜 JSON 오류")
    return result


class ParsingTest(unittest.TestCase):
    def test_weather_blank_quality_alias_does_not_hide_bad_quality(self):
        item = parse_page(fixture("asos_hourly.json")).item[:1]
        item[0].update(ta="999", taQcflag="", taQcflg="9")
        row = fetch_asos.parse_weather(item)[0]
        self.assertIsNone(row["temperature_c"])
        self.assertEqual(row["temperature_qc_flag"], "9")

    def test_weather_conflicting_quality_alias_is_rejected(self):
        item = parse_page(fixture("asos_hourly.json")).item[:1]
        item[0].update(taQcflag="0", taQcflg="9")
        with self.assertRaises(FetchError):
            fetch_asos.parse_weather(item)

    def test_error_code_precedes_empty_body_validation(self):
        for body in (None, "", []):
            with self.subTest(body=body):
                with self.assertRaises(FetchError) as error:
                    parse_page({"response": {"header": {"resultCode": "01"}, "body": body}})
                self.assertTrue(error.exception.retryable)
                page = parse_page({"response": {"header": {"resultCode": "03"}, "body": body}})
                self.assertEqual(page.total_count, 0)

    def test_weather_missing_zero_negative_temperature_and_quality(self):
        page = parse_page(fixture("asos_hourly.json"))
        rows = fetch_asos.parse_weather(page.item, 17)
        self.assertEqual(page.total_count, 3)
        self.assertEqual(set(rows[0]), set(fetch_asos.COLUMN))
        self.assertEqual(rows[0]["source_snapshot_id"], 17)
        self.assertIsNone(rows[0]["rain_mm"])
        self.assertIsNone(rows[0]["snow_cm"])
        self.assertEqual(rows[1]["rain_mm"], "0.0")
        self.assertEqual(rows[1]["temperature_c"], "-1.7")
        self.assertIsNone(rows[2]["temperature_c"])
        self.assertIsNone(rows[2]["rain_mm"])
        self.assertEqual(rows[2]["rain_qc_flag"], "9")

    def test_weather_rejects_wrong_station_duplicate_and_nonhour(self):
        original = parse_page(fixture("asos_hourly.json")).item
        for field, value in (("stnId", "119"), ("tm", "2026-10-30 00:30"),
                             ("ta", "NaN"), ("rn", "-1")):
            rows = copy.deepcopy(original)
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(FetchError):
                fetch_asos.parse_weather(rows)
        with self.assertRaises(FetchError):
            fetch_asos.parse_weather([original[0], original[0]])

    def test_charger_preserves_id_detail_unknown_and_deletion(self):
        page = parse_page(fixture("ev_charger.json"))
        rows = fetch_ev_chargers.parse_charger(page.item)
        self.assertEqual(set(rows[0]), set(fetch_ev_chargers.COLUMN))
        self.assertEqual(rows[0]["source_charger_id"], "01")
        self.assertEqual(rows[0]["station_key"], rows[1]["station_key"])
        self.assertNotEqual(rows[0]["station_key"], rows[2]["station_key"])
        self.assertEqual(len(rows[0]["station_key"]), 64)
        self.assertEqual([row["source_row_no"] for row in rows], [1, 2, 3])
        self.assertEqual(rows[0]["district_name"], "종로구")
        self.assertEqual(rows[1]["district_name"], "종로구")
        self.assertEqual(rows[0]["speed_code"], "fast")
        self.assertEqual(rows[1]["speed_code"], "slow")
        self.assertEqual(rows[2]["speed_code"], "unknown")
        self.assertEqual(rows[2]["capacity_text"], "50/100")
        self.assertIsNone(rows[2]["capacity_kw"])
        self.assertIsNone(rows[2]["district_name"])
        self.assertIsNone(rows[2]["latitude"])
        self.assertEqual(rows[2]["deleted_code"], "Y")
        self.assertEqual(rows[0]["status_updated_at"], "2026-11-06 09:00:00")
        self.assertNotIn("busiCall", rows[0])

    def test_charger_rejects_duplicate_empty_identifier_and_wrong_province(self):
        item = parse_page(fixture("ev_charger.json")).item
        for field, value in (("statId", ""), ("chgerId", ""), ("zcode", "28"),
                             ("statUpdDt", "잘못된시각")):
            rows = copy.deepcopy(item)
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(FetchError):
                fetch_ev_chargers.parse_charger(rows)
        with self.assertRaises(FetchError):
            fetch_ev_chargers.parse_charger([item[0], item[0]])

    def test_singleton_empty_and_nested_header_count(self):
        payload = fixture("ev_charger.json")
        payload["items"]["item"] = payload["items"]["item"][0]
        payload["totalCount"] = 1
        self.assertEqual(len(parse_page(payload).item), 1)
        nested = {"response": {"header": {key: value for key, value in payload.items() if key != "items"},
                               "body": {"items": payload["items"]}}}
        self.assertEqual(parse_page(nested).total_count, 1)
        payload["totalCount"], payload["items"] = 0, ""
        self.assertEqual(parse_page(payload).item, [])
        self.assertEqual(parse_page({"response": {"header": {"resultCode": "03"}}}).total_count, 0)

    def test_api_error_and_malformed_payload(self):
        with self.assertRaisesRegex(FetchError, "코드 30"):
            parse_page(fixture("api_error.json"))
        for payload in ([], {"response": None}, {"resultCode": "00"},
                        {"resultCode": "00", "totalCount": -1}):
            with self.subTest(payload=payload), self.assertRaises(FetchError):
                parse_page(payload)


class TransportTest(unittest.TestCase):
    def make_client(self, result, retries=3):
        budget = Mock()
        session = Mock()
        session.get.side_effect = result
        client = ApiClient("fixture-credential-not-real", budget, retries=retries, session=session)
        return client, session, budget

    def test_network_retries_three_times_and_hides_exception(self):
        client, session, budget = self.make_client([
            requests.ConnectionError("URL contains fixture-credential-not-real") for _ in range(4)
        ])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run_cli(lambda: client.get_page(fetch_asos.ENDPOINT, {}))
        self.assertEqual(code, 1)
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual(budget.claim.call_count, 4)
        self.assertNotIn("fixture-credential-not-real", output.getvalue())

    def test_retry_http_and_api_transient_error_then_success(self):
        client, session, _ = self.make_client([
            response(status=503), response({"resultCode": "01"}), response(fixture("ev_charger.json"))
        ])
        self.assertEqual(client.get_page(fetch_ev_chargers.ENDPOINT, {"zcode": "11"}).total_count, 3)
        self.assertEqual(client.request_count, 3)
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
        self.assertEqual(session.get.call_args.kwargs["params"]["serviceKey"], "fixture-credential-not-real")

    def test_xml_auth_error_and_redirect_never_retry(self):
        xml = b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
        for result in (response(xml=xml), response(status=302), response(fixture("api_error.json"))):
            client, session, _ = self.make_client([result])
            with self.subTest(result=result), self.assertRaises(FetchError):
                client.get_page(fetch_ev_chargers.ENDPOINT, {})
            self.assertEqual(session.get.call_count, 1)

    def test_smoke_one_request_and_no_retry(self):
        client, session, _ = self.make_client([response(fixture("ev_charger.json"))], retries=0)
        rows, total, pages = collect_page(client, fetch_ev_chargers.ENDPOINT, {}, smoke=True)
        self.assertEqual((len(rows), total, pages, session.get.call_count), (3, 3, 1, 1))
        client, session, _ = self.make_client([response(status=503)], retries=0)
        with self.assertRaises(FetchError):
            collect_page(client, fetch_ev_chargers.ENDPOINT, {}, smoke=True)
        self.assertEqual(session.get.call_count, 1)

    def test_pagination_uses_server_size_and_reserves_retry_budget(self):
        one = fixture("ev_charger.json")
        two = copy.deepcopy(one)
        one["numOfRows"], one["items"]["item"] = 2, one["items"]["item"][:2]
        two["numOfRows"], two["pageNo"], two["items"]["item"] = 2, 2, two["items"]["item"][2:]
        client, session, budget = self.make_client([response(one), response(two)])
        item, total, pages = collect_page(client, fetch_ev_chargers.ENDPOINT, {"numOfRows": 9999})
        self.assertEqual((len(item), total, pages), (3, 3, 2))
        budget.require.assert_called_once_with(4)
        self.assertEqual(session.get.call_args.kwargs["params"]["numOfRows"], 2)
        self.assertEqual(session.get.call_args.kwargs["params"]["pageNo"], 2)

    def test_last_page_may_report_actual_remaining_count(self):
        one = fixture("ev_charger.json")
        two = copy.deepcopy(one)
        one["numOfRows"], one["items"]["item"] = 2, one["items"]["item"][:2]
        two["numOfRows"], two["pageNo"], two["items"]["item"] = 1, 2, two["items"]["item"][2:]
        client, session, _ = self.make_client([response(one), response(two)])
        item, total, pages = collect_page(client, fetch_ev_chargers.ENDPOINT, {"numOfRows": 2})
        self.assertEqual((len(item), total, pages), (3, 3, 2))
        self.assertEqual(session.get.call_args.kwargs["params"]["numOfRows"], 2)

    def test_drift_truncated_page_and_no_data_fail(self):
        first = fixture("ev_charger.json")
        first["numOfRows"], first["items"]["item"] = 2, first["items"]["item"][:2]
        second = copy.deepcopy(first)
        second.update(pageNo=2, totalCount=4)
        client, _, _ = self.make_client([response(first), response(second)])
        with self.assertRaises(FetchError):
            collect_page(client, fetch_ev_chargers.ENDPOINT, {})
        first["items"]["item"] = first["items"]["item"][:1]
        for payload in (first, {"resultCode": "03"}):
            client, _, _ = self.make_client([response(payload)])
            with self.assertRaises(FetchError):
                collect_page(client, fetch_ev_chargers.ENDPOINT, {})

    def test_not_enough_budget_stops_after_first_request(self):
        first = fixture("ev_charger.json")
        first["numOfRows"], first["items"]["item"] = 2, first["items"]["item"][:2]
        client, session, budget = self.make_client([response(first)])
        budget.require.side_effect = FetchError("한도 부족")
        with self.assertRaises(FetchError):
            collect_page(client, fetch_ev_chargers.ENDPOINT, {})
        self.assertEqual(session.get.call_count, 1)


class BudgetAndOutputTest(unittest.TestCase):
    def test_rejected_external_usage_is_persisted_for_next_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.sqlite3"
            first = RequestBudget("ev_charger", 1000, used_today=1000, path=path)
            with self.assertRaises(FetchError):
                first.claim()
            second = RequestBudget("ev_charger", 1000, path=path)
            with self.assertRaises(FetchError):
                second.claim()
            with contextlib.closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT used FROM request_budget").fetchone()[0], 1000)

    def test_actual_usage_above_lower_limit_is_accepted_for_recording(self):
        args = Mock(used_today=600, daily_limit=500, source_snapshot_id=None)
        validate_budget(args, 1000)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.sqlite3"
            RequestBudget("ev_charger", args.daily_limit, used_today=args.used_today, path=path)
            with self.assertRaises(FetchError):
                RequestBudget("ev_charger", 500, path=path).claim()

    def test_url_encoded_credential_cannot_be_saved(self):
        credential = "fake-credential+/="
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing.csv"
            path.write_bytes(b"existing full data")
            encoded = quote(credential, safe="")
            for value in (encoded, encoded.replace("%2B", "%2b").replace("%2F", "%2f")):
                with self.assertRaises(FetchError):
                    save_snapshot(path, [{"note": value}], ("note",), {}, api_key=credential)
                self.assertEqual(path.read_bytes(), b"existing full data")

    def test_budget_persists_retries_spacing_and_external_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.sqlite3"
            first = RequestBudget("ev_charger", 4, used_today=1, path=path)
            with patch("etl.fetch_api_common.time.time", return_value=100.0):
                first.claim()
            second = RequestBudget("ev_charger", 4, path=path)
            with patch("etl.fetch_api_common.time.time", return_value=100.2), \
                    patch("etl.fetch_api_common.time.sleep") as sleep:
                second.claim()
                self.assertAlmostEqual(sleep.call_args.args[0], 0.8)
            with self.assertRaises(FetchError):
                second.require(2)
            second.require(1)
            with patch("etl.fetch_api_common.time.time", return_value=102.0):
                second.claim()
            with self.assertRaises(FetchError):
                first.claim()
            with contextlib.closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT used FROM request_budget").fetchone()[0], 4)
            RequestBudget("asos", 1, path=path).claim()

    def test_csv_bom_blank_null_manifest_hash_and_no_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weather.csv"
            rows = fetch_asos.parse_weather(parse_page(fixture("asos_hourly.json")).item)
            save_snapshot(path, rows, fetch_asos.COLUMN, {"station_id": "108"}, api_key="fake-credential")
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as source:
                saved = list(csv.DictReader(source))
            self.assertEqual(saved[0]["rain_mm"], "")
            self.assertEqual(saved[1]["rain_mm"], "0.0")
            manifest = json.loads(path.with_suffix(".meta.json").read_text())
            self.assertEqual(manifest["content_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertNotIn("fake-credential", path.read_text(encoding="utf-8-sig"))
            before = path.read_bytes()
            with self.assertRaises(FetchError):
                save_snapshot(path, [{"observed_at": "fake-credential"}], fetch_asos.COLUMN, {},
                              api_key="fake-credential")
            self.assertEqual(path.read_bytes(), before)

    def test_cli_missing_key_module_and_direct_script(self):
        env = {key: value for key, value in os.environ.items() if key != "DATA_GO_KR_API_KEY"}
        for name in ("fetch_asos", "fetch_ev_chargers"):
            for invocation in (["-m", f"etl.{name}"], [str(PROJECT / "etl" / f"{name}.py")]):
                with self.subTest(name=name, invocation=invocation):
                    run = subprocess.run([sys.executable, *invocation], cwd=PROJECT, env=env,
                                         text=True, capture_output=True, check=False)
                    self.assertEqual(run.returncode, 2)
                    self.assertEqual(run.stdout.strip(), "DATA_GO_KR_API_KEY 없음")
                    self.assertEqual(run.stderr, "")

    def test_weather_cli_saves_partial_coverage_with_real_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weather.csv"
            client = Mock()
            client.http_status, client.result_code, client.request_count, client.retries = 200, "00", 1, 3
            client.get_page.return_value = parse_page(fixture("asos_hourly.json"))
            with patch.dict(os.environ, {"DATA_GO_KR_API_KEY": "fixture-credential-not-real"}), \
                    patch.object(sys, "argv", ["fetch_asos", "--output", str(path)]), \
                    patch.object(fetch_asos, "ApiClient", return_value=client), \
                    patch.object(fetch_asos, "RequestBudget"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fetch_asos.main(), 0)
            metadata = json.loads(path.with_suffix(".meta.json").read_text())
            self.assertEqual(metadata["expected_hour_count"], 48)
            self.assertEqual(metadata["missing_hour_count"], 45)
            self.assertFalse(metadata["is_complete"])

    def test_ev_cli_keeps_details_and_marks_unmatched_and_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "charger.csv"
            client = Mock()
            client.http_status, client.result_code, client.request_count, client.retries = 200, "00", 1, 3
            client.get_page.return_value = parse_page(fixture("ev_charger.json"))
            with patch.dict(os.environ, {"DATA_GO_KR_API_KEY": "fixture-credential-not-real"}), \
                    patch.object(sys, "argv", ["fetch_ev_chargers", "--output", str(path)]), \
                    patch.object(fetch_ev_chargers, "ApiClient", return_value=client), \
                    patch.object(fetch_ev_chargers, "RequestBudget"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fetch_ev_chargers.main(), 0)
            metadata = json.loads(path.with_suffix(".meta.json").read_text())
            self.assertEqual(metadata["row_count"], 3)
            self.assertEqual(metadata["deleted_count"], 1)
            self.assertEqual(metadata["unmatched_district_count"], 1)
            self.assertEqual(metadata["unknown_speed_count"], 1)

    def test_smoke_never_creates_output_or_overwrites_full_csv(self):
        for module, sample in ((fetch_asos, "asos_hourly.json"), (fetch_ev_chargers, "ev_charger.json")):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "existing.csv"
                path.write_bytes(b"existing full data")
                client = Mock()
                client.http_status, client.result_code, client.request_count, client.retries = 200, "00", 1, 0
                client.get_page.return_value = parse_page(fixture(sample))
                with patch.dict(os.environ, {"DATA_GO_KR_API_KEY": "fixture-credential-not-real"}), \
                        patch.object(sys, "argv", ["fetch", "--smoke", "--output", str(path)]), \
                        patch.object(module, "ApiClient", return_value=client) as factory, \
                        patch.object(module, "RequestBudget"), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(module.main(), 0)
                self.assertEqual(factory.call_args.kwargs["retries"], 0)
                self.assertEqual(client.get_page.call_count, 1)
                self.assertEqual(path.read_bytes(), b"existing full data")
                self.assertFalse(path.with_suffix(".meta.json").exists())

    def test_failed_collection_preserves_existing_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing.csv"
            path.write_bytes(b"existing full data")
            client = Mock()
            client.get_page.side_effect = FetchError("가상 요청 실패")
            with patch.dict(os.environ, {"DATA_GO_KR_API_KEY": "fixture-credential-not-real"}), \
                    patch.object(sys, "argv", ["fetch_asos", "--output", str(path)]), \
                    patch.object(fetch_asos, "ApiClient", return_value=client), \
                    patch.object(fetch_asos, "RequestBudget"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_cli(fetch_asos.main), 1)
            self.assertEqual(path.read_bytes(), b"existing full data")


if __name__ == "__main__":
    unittest.main()
