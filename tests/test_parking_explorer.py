import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests
from streamlit.testing.v1 import AppTest

from tests import app_env
from parking_explorer import (charger_records, distance_m, fee, hours, map_html,
                              parking_records, seoul_parking, station_search)


class ParkingExplorerTest(unittest.TestCase):
    def test_prices_do_not_turn_missing_amounts_or_zero_caps_into_free(self):
        self.assertEqual(fee({"pay_yn": "N"}), "무료")
        self.assertIn("금액 정보 미제공", fee({"pay_yn": "Y", "rates": "", "day_maximum": "0"}))
        label = fee({"pay_yn": "Y", "rates": "0", "time_rate": "30", "add_rates": "1000", "add_time_rate": "10"})
        self.assertIn("유료", label)
        self.assertIn("기본 30분 0원", label)
        self.assertIn("추가 10분 1,000원", label)
        self.assertIn("유·무료 정보 미제공", fee({}))

    def test_hours_missing_closed_and_overnight(self):
        self.assertEqual(hours("0000", "2400"), "24시간")
        self.assertEqual(hours("0000", "0000"), "운영 여부 확인 필요")
        self.assertEqual(hours(None, "1800"), "정보 미제공")
        self.assertIn("다음 날", hours("2200", "0600"))
        self.assertEqual(hours("9999", "1800"), "정보 미제공")

    def test_invalid_coordinates_are_not_mapped(self):
        rows = [{"parking_code": "1", "parking_type": "NS", "parking_name": "실제 주차장",
                 "position_list": [{"lat": "0", "lng": "0"}, {"lat": "37.55", "lng": "126.93"}]}]
        records = parking_records(rows)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["name"], "실제 주차장")
        self.assertEqual(records[0]["operation"], "공영")
        self.assertEqual(parking_records([{"position_list": [{"lat": 0, "lng": 0}]}]), [])

    def test_station_search_excludes_shops_and_exits(self):
        station_search.clear()
        rows = [{"title": title, "latitude": "37.4852", "longitude": "127.0162"}
                for title in ["남부터미널역 3호선", "카페 남부터미널역점", "남부터미널역 3호선 1번출구"]]
        with patch("parking_explorer.requests.post") as post:
            post.return_value.json.return_value = rows
            self.assertEqual([r["name"] for r in station_search("남부터미널역")], ["남부터미널역 3호선"])
        station_search.clear()

    def test_network_failure_is_distinct_from_no_parking_results(self):
        seoul_parking.clear()
        with patch("parking_explorer.requests.post", side_effect=requests.Timeout):
            self.assertIsNone(seoul_parking("마포구"))
        seoul_parking.clear()

    def test_distance_boundary_and_html_escaping(self):
        station = {"name": "홍대입구역", "latitude": 37.55, "longitude": 126.93}
        self.assertEqual(distance_m(station, station), 0)
        self.assertGreater(distance_m(station, {"latitude": 37.56, "longitude": 126.93}), 1000)
        html = map_html([{"name": "</script><img onerror=alert(1)>"}], station, 500, False)
        self.assertNotIn("</script><img onerror", html)
        self.assertIn("\\u003c/script>", html)
        self.assertIn('"animate": false', html)

    def test_charger_parking_fee_is_not_charging_fee(self):
        points = pd.DataFrame([{"place_id": 1, "place_name": "충전소", "address": "주소",
                                "latitude": 37.55, "longitude": 126.93, "charger_count": 2,
                                "operator_name": "운영사"}])
        devices = pd.DataFrame([{"station_id": 1, "parking_free": "Y", "operating_time_text": "24시간",
                                  "restriction_note": None}])
        record = charger_records(points, devices)[0]
        self.assertIn("주차 무료", record["price"])
        self.assertIn("충전요금: 금액 정보 미제공", record["price"])
        self.assertEqual(record["hours"], "24시간")

    def test_public_map_search_and_station_highlight(self):
        station = {"name": "홍대입구역 2호선", "latitude": 37.55687, "longitude": 126.92378}
        place = {"id": "public-1", "name": "홍대 테스트 주차장", "address": "서울 마포구 양화로",
                 "latitude": 37.557, "longitude": 126.924, "operation": "공영", "kind": "주차장",
                 "price": "유료 · 기본 10분 500원", "hours": "24시간", "note": "현장 확인",
                 "capacity": "10면", "operator": "서울시", "updated": "2026-11-09"}
        with patch("parking_explorer.seoul_parking", return_value=[place]), \
                patch("parking_explorer.station_search", return_value=[station]):
            app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=40).run()
            app.switch_page("app_pages/parking.py").run()
            app.selectbox(key="parking_station_마포구_").set_value(1).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertTrue(any("500m 안 주차장 1곳" in x.value for x in app.caption))
            app.text_input(key="parking_keyword").set_value("홍대 테스트").run()
            html = app.get("iframe")[0].proto.srcdoc
            payload = json.loads(re.search(r"const data=(.*?);\nconst esc", html, re.S).group(1))
            self.assertEqual(payload["places"][0]["name"], "홍대 테스트 주차장")
            self.assertEqual(payload["station"]["name"], station["name"])
            app.checkbox(key="parking_pin_animation").uncheck().run()
            self.assertIn('"animate": false', app.get("iframe")[0].proto.srcdoc)
            app.text_input(key="parking_keyword").set_value("일치하지않는장소").run()
            self.assertTrue(any("반경에 표시할 시설이 없어요" in x.value for x in app.info))


if __name__ == "__main__":
    unittest.main()
