from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any
import unittest
from unittest.mock import patch

import requests

from kakao_routes import get_walking_route


class WalkingRouteTests(unittest.TestCase):
    def setUp(self):
        key = patch("kakao_routes.rest_key", return_value="test-only")
        key.start()
        self.addCleanup(key.stop)
        request = patch("kakao_routes.requests.get")
        self.request = request.start()
        self.addCleanup(request.stop)
        self.response = self.request.return_value.__enter__.return_value
        self.response.status_code = 200
        self.response.json.return_value = {
            "status": "OK", "route": {"properties": {"totalDistance": 720, "totalTime": 645},
                                        "legs": [{"steps": []}]},
        }
        self.points = (37.55, 126.95, 37.56, 126.96)

    def test_request_uses_server_authorization_and_wgs84_coordinate_order(self):
        self.assertEqual(get_walking_route(*self.points), {"distance_m": 720, "duration_s": 645})
        self.request.assert_called_once_with(
            "https://dapi.kakao.com/v2/routing/walk",
            headers={"Authorization": "KakaoAK test-only"},
            params={"start_x": "126.95", "start_y": "37.55", "end_x": "126.96", "end_y": "37.56",
                    "input_coord": "WGS84"},
            timeout=(3, 5), allow_redirects=False,
        )
        self.request.return_value.__exit__.assert_called_once()

    def test_missing_key_does_not_make_a_request(self):
        with patch("kakao_routes.rest_key", return_value=""):
            self.assertIsNone(get_walking_route(*self.points))
        self.request.assert_not_called()

    def test_invalid_coordinates_do_not_make_a_request(self):
        for index, invalid in ((0, None), (0, True), (0, float("nan")), (1, float("inf")),
                               (0, 91), (1, -181), (2, -91), (3, 181), (3, "unknown")):
            with self.subTest(index=index, invalid=invalid):
                points: list[Any] = list(self.points)
                points[index] = invalid
                self.assertIsNone(get_walking_route(*points))
        self.request.assert_not_called()

    def test_http_errors_and_redirects_return_none_without_retries(self):
        for status in (301, 302, 400, 401, 403, 404, 429, 500, 503):
            with self.subTest(status=status):
                self.request.reset_mock()
                self.response.status_code = status
                self.assertIsNone(get_walking_route(*self.points))
                self.request.assert_called_once()
                self.response.json.assert_not_called()

    def test_transport_and_json_failures_do_not_print_details(self):
        output = StringIO()
        for error in (requests.Timeout("private-request-detail"), requests.ConnectionError("private-request-detail")):
            self.request.side_effect = error
            with redirect_stdout(output), redirect_stderr(output):
                self.assertIsNone(get_walking_route(*self.points))
        self.request.side_effect = None
        self.response.json.side_effect = ValueError("private-response-detail")
        with redirect_stdout(output), redirect_stderr(output):
            self.assertIsNone(get_walking_route(*self.points))
        self.assertEqual(output.getvalue(), "")

    def test_non_success_route_statuses_do_not_invent_a_route(self):
        for status in ("SAME_POINT", "START_LINK_NOT_FOUND", "END_LINK_NOT_FOUND", "TOO_MANY_SEARCH_LINK",
                       "TOO_FAR_AWAY", "ROUTE_RESULT_NOT_FOUND", None):
            with self.subTest(status=status):
                self.response.json.return_value["status"] = status
                self.assertIsNone(get_walking_route(*self.points))

    def test_malformed_responses_return_none(self):
        for payload in (None, [], {}, {"status": "OK"}, {"status": "OK", "route": None},
                        {"status": "OK", "route": {"properties": {"totalDistance": 720}}}):
            with self.subTest(payload=payload):
                self.response.json.return_value = payload
                self.assertIsNone(get_walking_route(*self.points))

    def test_missing_negative_boolean_or_non_integer_summary_is_rejected(self):
        properties = self.response.json.return_value["route"]["properties"]
        for field in ("totalDistance", "totalTime"):
            original = properties[field]
            for invalid in (None, -1, True, "720", 1.5, float("nan"), float("inf")):
                with self.subTest(field=field, invalid=invalid):
                    properties[field] = invalid
                    self.assertIsNone(get_walking_route(*self.points))
            properties[field] = original

    def test_observed_zero_is_preserved(self):
        self.response.json.return_value["route"]["properties"] = {"totalDistance": 0, "totalTime": 0}
        self.assertEqual(get_walking_route(*self.points), {"distance_m": 0, "duration_s": 0})

    def test_each_call_fetches_again_without_caching(self):
        self.assertEqual(get_walking_route(*self.points), {"distance_m": 720, "duration_s": 645})
        self.response.json.return_value["route"]["properties"]["totalTime"] = 660
        self.assertEqual(get_walking_route(*self.points), {"distance_m": 720, "duration_s": 660})
        self.assertEqual(self.request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
