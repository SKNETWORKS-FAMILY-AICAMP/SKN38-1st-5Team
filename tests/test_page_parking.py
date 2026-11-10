import json
import re
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import pandas as pd
from streamlit.testing.v1 import AppTest

from tests import app_env
from db import queries as q


APP = Path(__file__).resolve().parents[1] / "app.py"
PAGE = "app_pages/parking.py"


class ParkingPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ranking = q.get_district_ranking()
        cls.ids = dict(zip(cls.ranking.district_name.astype(str), cls.ranking.region_id.astype(int)))

    def setUp(self):
        key_patch = patch("parking_explorer.javascript_key", return_value="")
        key_patch.start()
        self.addCleanup(key_patch.stop)
        # Keep DB coverage regressions deterministic and test the offline fallback.
        # Streamlit runs pages outside their module name; patch the imported provider instead.
        self.source_patch = patch("parking_explorer.seoul_parking", return_value=None)
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)
        station_patch = patch("parking_explorer.station_search", return_value=[])
        station_patch.start()
        self.addCleanup(station_patch.stop)
        self.app = AppTest.from_file(APP, default_timeout=30).run()
        self.app.switch_page(PAGE).run()
        self.assert_ready()

    def assert_ready(self):
        self.assertFalse(self.app.exception, [item.message for item in self.app.exception])
        self.assertFalse(self.app.error, [item.value for item in self.app.error])

    def text(self):
        return "\n".join(str(item.value) for group in (
            self.app.caption, self.app.markdown, self.app.info, self.app.warning, self.app.error,
        ) for item in group)

    def select_district(self, name):
        self.app.selectbox(key="district_id").select(self.ids[name]).run()
        self.assert_ready()

    def table(self):
        self.assertEqual(len(self.app.dataframe), 1)
        return self.app.dataframe[0].value

    def hero(self):
        components = [item.proto for item in self.app.get("bidi_component")
                      if item.proto.component_name == "chachacha_h4_parking_hero"]
        self.assertEqual(len(components), 1)
        return components[0]

    def assert_map_matches(self, expected):
        maps = [item for item in self.app.get("bidi_component")
                if item.proto.component_name == "chachacha_parking_frame"]
        if expected.empty:
            self.assertEqual(len(maps), 0)
            return
        self.assertEqual(len(maps), 1)
        html = json.loads(maps[0].proto.json)["html"]
        payload = json.loads(re.search(r"const data=(.*?);\nconst esc", html, re.S).group(1))
        points = payload["places"]
        self.assertCountEqual(
            [(item["latitude"], item["longitude"]) for item in points],
            [(float(item.latitude), float(item.longitude)) for _, item in expected.iterrows()],
        )
        self.assertTrue(all(37.4 <= item["latitude"] <= 37.75 for item in points))
        self.assertTrue(all(126.75 <= item["longitude"] <= 127.2 for item in points))
        self.assertIn("marker.bindPopup", html)
        self.assertIn("marker.bindTooltip", html)

    def test_mapo_keeps_all_31_without_coordinates_and_real_capacity(self):
        self.assertEqual(self.app.segmented_control(key="parking_facility").value, "주차장")
        self.assertEqual(self.app.selectbox(key="district_id").value, self.ids["마포구"])
        self.assertEqual([(item.label, item.value) for item in self.app.metric],
                         [("공영 주차면", "3,080면"), ("민영 주차면", "0면")])
        table = self.table()
        self.assertEqual(len(table), 31)
        self.assertEqual(table.columns.tolist(), ["주소", "운영", "유형", "주차면", "지도 안내", "카카오맵에서 주소 찾기"])
        self.assertEqual([unquote(url.removeprefix("https://map.kakao.com/link/search/"))
                          for url in table["카카오맵에서 주소 찾기"]], table["주소"].tolist())
        self.assertTrue(table["지도 안내"].eq("좌표 없음·범위 밖").all())
        self.assertFalse(table["주소"].str.contains("주차장 ", regex=False).any())
        self.assertIn("지도 제외 31건", self.text())
        self.assertIn("좌표 없음·범위 밖 31건", self.text())
        self.assertIn("실제 빈자리가 아니에요", self.text())
        self.assert_map_matches(pd.DataFrame())

    def test_every_district_retains_full_parking_inventory_and_verified_points(self):
        self.assertEqual(len(self.ids), 25)
        for name, region_id in self.ids.items():
            with self.subTest(district=name):
                self.select_district(name)
                expected = q.search_places("주차장 [", region_id=region_id, limit=100)
                expected = expected.loc[expected.kind.eq("parking_site")]
                points = q.get_place_points(region_id, kinds=("parking",))
                coverage = points.attrs["coverage"][0]
                self.assertEqual(len(self.table()), int(coverage["total_count"]))
                self.assertCountEqual(self.table()["주소"], expected.address.tolist())
                self.assertCountEqual(self.table()["주차면"],
                                      [f"{int(value):,}면" for value in expected.space_count])
                self.assert_map_matches(points)
                hero = json.loads(self.hero().json)
                row = self.ranking.loc[self.ranking.region_id.eq(region_id)].iloc[0]
                self.assertEqual(hero["parkingLevel"], str(row.parking_level))
                self.assertEqual(hero["districtId"], region_id)
                self.assertEqual(hero["districtName"], name)

    def test_public_private_filters_apply_to_list_and_map(self):
        self.select_district("구로구")
        region_id = self.ids["구로구"]
        catalog = q.search_places("주차장 [", region_id=region_id, limit=100)
        points = q.get_place_points(region_id, kinds=("parking",))
        for operation in ("민영", "공영", "전체"):
            with self.subTest(operation=operation):
                self.app.segmented_control(key="parking_operation").set_value(operation).run()
                self.assert_ready()
                expected = catalog if operation == "전체" else catalog.loc[catalog.parking_operation.eq(operation)]
                expected_points = points if operation == "전체" else points.loc[points.parking_operation.eq(operation)]
                self.assertGreater(len(expected), 0)
                self.assertCountEqual(self.table()["주소"], expected.address.tolist())
                self.assert_map_matches(expected_points)

    def test_address_search_calls_public_api_and_filters_both_views(self):
        self.select_district("강남구")
        region_id = self.ids["강남구"]
        with patch.object(q, "search_places", wraps=q.search_places) as search:
            self.app.text_input(key="parking_keyword").set_value("논현로").run()
            search.assert_any_call("논현로", region_id=region_id, limit=100)
        self.assert_ready()
        table = self.table()
        self.assertGreater(len(table), 0)
        self.assertTrue(table["주소"].str.contains("논현로", regex=False).all())
        points = q.get_place_points(region_id, kinds=("parking",))
        self.assert_map_matches(points.loc[points.address.str.contains("논현로", regex=False, na=False)])

    def test_broad_search_does_not_lose_parking_to_first_100_chargers(self):
        first_results = q.search_places("서울", region_id=self.ids["마포구"], limit=100)
        self.assertEqual(len(first_results), 100)
        self.assertTrue(first_results.kind.eq("charging_station").all())
        self.app.text_input(key="parking_keyword").set_value("서울").run()
        self.assert_ready()
        self.assertEqual(len(self.table()), 31)
        self.assert_map_matches(pd.DataFrame())

    def test_search_metacharacters_are_literal_and_no_match_is_not_fabricated(self):
        for keyword in ("%", "_", "!", "[", "없는주소xyz987"):
            with self.subTest(keyword=keyword):
                self.app.text_input(key="parking_keyword").set_value(keyword).run()
                self.assert_ready()
                self.assertEqual(len(self.app.dataframe), 0)
                self.assertEqual(len(self.app.get("deck_gl_json_chart")), 0)
                self.assertIn("조건에 맞는 자료가 없어요", self.text())
        self.app.text_input(key="parking_keyword").set_value("").run()
        self.assertEqual(len(self.table()), 31)

    def test_conflicting_parking_rows_remain_in_list_but_not_map(self):
        self.select_district("강남구")
        self.assertEqual(len(self.table()), 68)
        self.assertEqual(int(self.table()["지도 안내"].eq("관리번호 겹침").sum()), 4)
        points = q.get_place_points(self.ids["강남구"], kinds=("parking",))
        self.assertEqual(len(points), 64)
        self.assert_map_matches(points)
        self.assertIn("관리번호 겹침 4건", self.text())

    def test_missing_metrics_judgment_address_and_capacity_are_explicit(self):
        region_id = self.ids["마포구"]
        summary = q.get_parking_summary([region_id]).copy()
        summary["public_space_count"] = pd.NA
        ranking = self.ranking.drop(columns=["parking_value", "parking_rank", "parking_level"])
        catalog = q.search_places("주차장 [", region_id=region_id, limit=100).copy()
        catalog["space_count"] = catalog.space_count.astype("Int64")
        catalog.loc[catalog.index[0], "space_count"] = pd.NA
        catalog.loc[catalog.index[0], "address"] = None
        with patch.object(q, "get_parking_summary", return_value=summary), \
                patch.object(q, "get_district_ranking", return_value=ranking), \
                patch.object(q, "search_places", return_value=catalog):
            self.app.run()
        self.assert_ready()
        self.assertEqual(self.app.metric[0].value, "자료 없음")
        self.assertEqual(self.app.metric[1].value, "0면")
        self.assertEqual(self.table().iloc[0]["주소"], "자료 없음")
        self.assertEqual(self.table().iloc[0]["주차면"], "자료 없음")
        self.assertEqual(self.table().iloc[0]["카카오맵에서 주소 찾기"], "")
        hero = json.loads(self.hero().json)
        self.assertEqual(hero["parkingLevel"], "자료 없음")
        self.assertEqual(hero["parkingValue"], "자료 없음")

    def test_small_positive_parking_ratio_is_not_rounded_to_zero(self):
        self.select_district("성동구")
        self.assertTrue(json.loads(self.hero().json)["parkingValue"].startswith("차 100대당 주차면 0.03면"))

    def test_partial_catalog_limit_is_disclosed(self):
        catalog = q.search_places("주차장 [", region_id=self.ids["마포구"], limit=100).head(1)
        with patch.object(q, "search_places", return_value=catalog):
            self.app.run()
        self.assert_ready()
        self.assertEqual(len(self.table()), 1)
        self.assertIn("주차 목록 일부만 조회됐어요", self.text())
        self.assertIn("최대 100건", self.text())

    def test_chargers_include_unmapped_stations_and_keep_device_ids(self):
        region_id = self.ids["마포구"]
        details = q.get_charger_detail(region_id, limit=None)
        points = q.get_place_points(region_id, kinds=("charger",))
        missing = details.loc[~details.station_id.isin(points.place_id)]
        self.assertGreater(len(missing), 0)
        self.app.segmented_control(key="parking_facility").set_value("충전소").run()
        self.assert_ready()
        self.assertEqual(len(self.table()), len(details))
        self.assertCountEqual(self.table()["기기번호"], details.source_charger_id.tolist())
        self.assertEqual(int(self.table()["지도 안내"].eq("충전소 위치 자료 없음").sum()), len(missing))
        self.assert_map_matches(points)
        self.assertIn("환경공단 자료만", self.text())
        self.assertIn("실시간 사용 가능 여부가 아니며", self.text())
        name = str(missing.iloc[0].station_name)
        self.app.text_input(key="parking_keyword").set_value(name).run()
        self.assert_ready()
        self.assertGreater(len(self.table()), 0)
        self.assertTrue(self.table()["지도 안내"].eq("충전소 위치 자료 없음").any())

    def test_hero_identity_and_district_survive_search_and_page_navigation(self):
        original_id = self.hero().id
        self.select_district("구로구")
        self.assertEqual(self.hero().id, original_id)
        self.app.segmented_control(key="parking_operation").set_value("민영").run()
        self.app.text_input(key="parking_keyword").set_value("서울").run()
        self.assertEqual(self.hero().id, original_id)
        self.assertEqual(json.loads(self.hero().json)["activeTopic"], "parking")
        self.app.switch_page("app_pages/compare.py").run()
        self.assert_ready()
        self.app.switch_page(PAGE).run()
        self.assert_ready()
        self.assertEqual(self.app.selectbox(key="district_id").value, self.ids["구로구"])
        self.assertEqual(self.app.session_state["selected_region_id"], self.ids["구로구"])
        self.assertEqual(self.app.segmented_control(key="parking_operation").value, "민영")
        self.assertEqual(self.app.text_input(key="parking_keyword").value, "서울")
        self.assertEqual(self.hero().id, original_id)

    def test_unavailable_map_query_keeps_address_list_and_hides_internal_error(self):
        with patch.object(q, "get_place_points", side_effect=RuntimeError("internal-connection-details")):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertTrue(self.app.error)
        self.assertNotIn("internal-connection-details", self.text())
        self.assertEqual(len(self.table()), 31)
        self.assertIn("지도 제외 자료 없음", self.text())

    def test_kakao_map_survives_district_filters_and_facility_changes(self):
        def component():
            return next(item.proto for item in self.app.get("bidi_component")
                        if item.proto.component_name == "chachacha_kakao_places")
        with patch("parking_explorer.javascript_key", return_value="test-only"):
            self.app.run()
            self.assert_ready()
            identity = component().id
            self.assertEqual(json.loads(component().json)["places"], [])
            self.assertEqual(len(self.table()), 31)
            self.assertTrue(json.loads(component().json)["boundary"]["polygons"])
            self.select_district("강남구")
            self.app.segmented_control(key="parking_operation").set_value("민영").run()
            self.assert_ready()
            expected = q.get_place_points(self.ids["강남구"], kinds=("parking",), limit=None)
            expected = expected.loc[expected.parking_operation.eq("민영")]
            self.assertCountEqual([place["id"] for place in json.loads(component().json)["places"]],
                                  [f"db-{value}" for value in expected.place_id])
            self.assertEqual(component().id, identity)
            self.app.segmented_control(key="parking_facility").set_value("충전소").run()
            self.assert_ready()
            expected = q.get_place_points(self.ids["강남구"], kinds=("charger",), limit=None)
            self.assertCountEqual([place["id"] for place in json.loads(component().json)["places"]],
                                  [f"charger-{value}" for value in expected.place_id])
            self.assertEqual(component().id, identity)
            self.assertFalse(self.app.get("iframe"))
            self.app.text_input(key="parking_keyword").set_value("없는시설xyz987").run()
            self.assert_ready()
            self.assertEqual(json.loads(component().json)["places"], [])
            self.assertEqual(component().id, identity)


if __name__ == "__main__":
    unittest.main()
