import json
import math
import re
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.components.v2.bidi_component.main import _make_trigger_id
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
from streamlit.testing.v1 import AppTest

from tests import app_env
from tests.test_compare_table import cells_for, table_from_app


TOPIC_LEVELS = {
    "ownership": ("많은 편", "보통", "적은 편"),
    "parking": ("좋음", "보통", "빠듯함"),
    "need": ("차가 필요한 편", "있으면 편함", "대중교통으로 충분"),
}
TOPIC_UNITS = ("세대당 차량", "차 100대당 주차면", "주민 1명당 하루 승객")
TOPIC_ORDERS = {
    "ownership": "세대당 차량 많은 순",
    "parking": "차량 대비 수록 주차면 많은 순",
    "charging": "전기차 대비 수록 충전기 많은 순",
    "need": "대중교통 이용 많은 순",
}
LEVEL_COLORS = ("#27336B", "#8E98CF", "#EEF0FA")


def expected_values(row):
    # 화면 도우미의 계산 오류를 함께 놓치지 않도록 기대값은 별도로 계산한다.
    values = []
    for topic, multiplier, digits, unit in (
        ("ownership", 1, 2, "대"), ("parking", 100, 1, "면"), ("need", 1, 2, "명")
    ):
        raw = row.get(f"{topic}_value")
        if raw is None or pd.isna(raw):
            values.append("자료 없음")
            continue
        scaled = float(raw) * multiplier
        if topic == "parking" and 0 < scaled < 0.1:
            digits = 2
        values.append(f"{scaled:,.{digits}f}{unit}")
    return values


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30)
        for topic in TOPIC_ORDERS:
            self.app.session_state[f"ranking_{topic}_show_all"] = True
        self.app.run()
        from db import queries as q
        self.ranking = q.get_district_ranking()
        self.ids = dict(zip(self.ranking.district_name.astype(str), self.ranking.region_id.astype(int)))
        self.assert_ready()

    def assert_ready(self):
        self.assertFalse(self.app.exception, [e.message for e in self.app.exception])
        self.assertFalse(self.app.error, [e.value for e in self.app.error])

    def map_proto(self):
        return next(element.proto for element in self.app.get("bidi_component")
                    if element.proto.component_name.endswith("h3_seoul_drawing"))

    def map_data(self):
        return json.loads(self.map_proto().json)

    def ranking_table(self, topic):
        element = next(element for element in self.app.get("vega_lite_chart")
                       if TOPIC_ORDERS[topic] in element.proto.alt)
        frame = convert_arrow_bytes_to_pandas_df(element.proto.datasets[0].data.data).rename(
            columns={"rank_label": "순위", "name": "동네", "label": "값"})
        return SimpleNamespace(proto=element.proto, value=frame)

    def send_selection(self, widget_id, selection):
        # AppTest에는 차트·데이터프레임 클릭 API가 없어 브라우저 위젯 이벤트를 직접 넣는다.
        states = self.app._tree.get_widget_states()
        event = states.widgets.add()
        event.id = widget_id
        event.string_value = json.dumps({"selection": selection})
        self.app._run(widget_state=states)
        self.assert_ready()

    def send_map_event(self, name, value):
        # CCv2 트리거는 별도 집계기를 사용하므로 브라우저와 같은 이벤트 묶음을 넣는다.
        states = self.app._tree.get_widget_states()
        event = states.widgets.add()
        event.id = _make_trigger_id(self.map_proto().id, "events")
        event.json_trigger_value = json.dumps([{"event": name, "value": value}])
        self.app._run(widget_state=states)
        self.assert_ready()

    def assert_selected(self, name):
        region_id = self.ids[name]
        self.assertEqual(self.app.selectbox(key="district_id").value, region_id)
        self.assertEqual(self.app.session_state["selected_region_id"], region_id)

    def assert_cards(self, name):
        row = self.ranking.loc[self.ranking.region_id == self.ids[name]].iloc[0]
        self.assertEqual([m.value for m in self.app.metric[:3]], expected_values(row))
        self.assertEqual([m.label for m in self.app.metric[:3]], list(TOPIC_UNITS))

    def assert_district(self, name):
        self.assert_selected(name)
        region_id = self.ids[name]
        row = self.ranking.loc[self.ranking.region_id == region_id].iloc[0]
        selected = self.map_data()["selected"]
        self.assertEqual((selected["id"], selected["name"]), (region_id, name))
        self.assertEqual([v["level"] for v in selected["verdicts"]],
                         [str(row[f"{topic}_level"]) for topic in TOPIC_LEVELS])
        self.assertEqual([v["value"] for v in selected["verdicts"]],
                         [f"{label} {value}" for label, value in zip(TOPIC_UNITS, expected_values(row))])

    def assert_compare_table(self, left, right):
        table = table_from_app(self.app)
        self.assertEqual([item.get_text(strip=True) for item in table.select(".compare-name")], [left, right])
        rows = [self.ranking.loc[self.ranking.region_id == self.ids[name]].iloc[0] for name in (left, right)]
        for index, row in enumerate(rows):
            header = table.find(id=f"compare-district-{index}")
            self.assertEqual([item.get_text(strip=True) for item in header.select(".compare-judgment")],
                             [f"{label} · {row[f'{topic}_level']}" for topic, label in
                              zip(TOPIC_LEVELS, ("차량 보유", "주차 여유", "차 필요도"))])
        for position, (topic, scale, digits) in enumerate((("ownership", 1, 2), ("parking", 100, 1), ("need", 1, 2))):
            cells = cells_for(table, f"{topic}_value")
            self.assertEqual([cell.select_one(".compare-value").get_text() for cell in cells],
                             [expected_values(row)[position] for row in rows])
            self.assertEqual([cell.select_one(".compare-rank").get_text() for cell in cells],
                             [f"{TOPIC_ORDERS[topic]} · 서울 25구 중 {int(row[f'{topic}_rank'])}위" for row in rows])
            gap = (float(rows[0][f"{topic}_value"]) - float(rows[1][f"{topic}_value"])) * scale
            step = 10 ** -digits
            self.assertEqual([cell.select_one(".compare-more") is not None for cell in cells],
                             [gap >= step, -gap >= step])
        for field in ("parking_level", "need_level"):
            self.assertEqual([cell.select_one(".compare-value").get_text() for cell in cells_for(table, field)],
                             [str(row[field]) for row in rows])

    def test_navigation_selection_and_contract_values(self):
        at = self.app
        row = self.ranking.loc[self.ranking.region_id == self.ids["마포구"]].iloc[0]
        self.assert_district("마포구")
        at.switch_page("app_pages/ranking.py").run()
        self.assert_ready()
        self.assert_cards("마포구")
        self.assertEqual(at.metric[1].value, f"{float(row.parking_value) * 100:.1f}면")
        for criterion in ("세대당 차량 많은 순", "차량 대비 수록 주차면 많은 순", "대중교통 이용 많은 순"):
            self.assertTrue(any(criterion in c.value and "서울 25구 중" in c.value for c in at.caption))
        before = at.metric[0].value
        at.selectbox(key="district_id").select(self.ids["강남구"]).run()
        self.assert_ready()
        self.assertNotEqual(before, at.metric[0].value)
        for topic in ("parking", "need", "ownership"):
            at.button(key=f"tab_{topic}").click().run()
            self.assert_ready()
            self.assertEqual(at.session_state["topic"], topic)
        at.button(key="tab_need").click().run()

        at.switch_page("app_pages/compare.py").run()
        self.assert_ready()
        self.assertEqual(at.selectbox(key="district_id").value, self.ids["강남구"])
        at.selectbox(key="compare_id").select(self.ids["마포구"]).run()
        self.assert_ready()
        self.assert_compare_table("강남구", "마포구")

        at.switch_page("app_pages/national.py").run()
        self.assert_ready()
        self.assertGreater(len(at.dataframe[0].value), 0)
        at.selectbox(key="national_province").select("서울").run()
        self.assert_ready()
        self.assertTrue((at.dataframe[0].value["시도"] == "서울").all())

        at.switch_page("app_pages/faq.py").run()
        self.assert_ready()
        self.assertEqual(at.segmented_control(key="faq_kind").value, "기업 FAQ")
        self.assertGreater(len(at.expander), 0)
        at.text_input(key="faq_keyword").set_value("일치하지않는검색어xyz987").run()
        self.assert_ready()
        self.assertTrue(at.info)
        at.switch_page("app_pages/home.py").run()
        self.assert_ready()
        self.assertEqual(at.selectbox(key="district_id").value, self.ids["강남구"])
        self.assertEqual(at.session_state["topic"], "need")
        at.switch_page("app_pages/compare.py").run()
        self.assertEqual(at.selectbox(key="compare_id").value, self.ids["마포구"])

    def test_thirteen_pages_and_metric_page_links(self):
        at = self.app
        expected = ["", "finder", "ownership", "parking", "charging", "transit", "roads",
                    "ranking", "compare", "national", "faq", "ask", "about"]
        expected_menu = expected
        menu = at.get_by_key("site_menu").page_link
        groups = [[link.proto.page for link in at.get_by_key(f"site_group_{number}").page_link]
                  for number in range(3)]
        self.assertEqual(len(menu), 13)
        self.assertEqual(groups, [["ownership", "parking", "charging", "transit", "roads"],
                                  ["ranking", "compare", "national"], ["faq", "ask", "about"]])
        self.assertEqual([link.proto.page for link in menu], expected_menu)
        labels = {link.proto.page: link.value for link in menu}
        for path, label in (("ranking", "25구 순위"), ("parking", "주차·충전 찾기"), ("faq", "기업 FAQ"),
                            ("charging", "전기차 충전"), ("roads", "도로와 날씨"), ("about", "자료 안내")):
            self.assertEqual(labels[path], label)
        at.switch_page("app_pages/ranking.py").run()
        self.assert_ready()
        for topic, target in (("ownership", "ownership"), ("parking", "parking"), ("need", "transit")):
            links = at.get_by_key(f"judgment_{topic}").page_link
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0].proto.page, target)
        for page in ("ranking", "finder", "ownership", "parking", "charging", "transit", "roads", "compare",
                     "national", "faq", "ask", "about", "home"):
            with self.subTest(page=page):
                at.switch_page(f"app_pages/{page}.py").run()
                self.assert_ready()
                self.assertEqual([link.proto.page for link in at.get_by_key("site_menu").page_link], expected_menu)
                self.assertEqual([link.proto.page for link in at.get_by_key("footer_menu").page_link], expected)
                self.assertEqual(at.selectbox(key="district_id").value, self.ids["마포구"])

    def test_site_search_reaches_ranking_and_renamed_pages(self):
        at = self.app
        for query, group, member in (("25구 순위", 1, 0), ("순위", 1, 0), ("주차·충전 찾기", 0, 1),
                                     ("주차 찾기", 0, 1), ("기업 FAQ", 2, 0)):
            with self.subTest(query=query):
                at.switch_page("app_pages/home.py").run()
                tools = at.get_by_key("site_tools")
                tools.text_input[0].set_value(query)
                tools.button[0].click().run()
                self.assert_ready()
                at.get_by_key(f"more_current_{group}_{member}")

    def test_site_search_sends_questions_to_ask(self):
        at = self.app
        tools = at.get_by_key("site_tools")
        tools.text_input[0].set_value("차 없어도 살 만한 동네")
        with patch("ask_service.resolve_api_key", return_value=None):
            tools.button[0].click().run()
        self.assert_ready()
        at.get_by_key("more_current_2_1")

    def test_sitemap_lists_every_group_with_ranking(self):
        at = self.app
        at.button(key="site_sitemap_open").click().run()
        self.assert_ready()
        self.assertEqual([[link.proto.page for link in at.get_by_key(f"sitemap_row_{number}").page_link]
                          for number in range(4)],
                         [["", "finder"], ["ownership", "parking", "charging", "transit", "roads"],
                          ["ranking", "compare", "national"], ["faq", "ask", "about"]])
        self.assertIn("25구 순위", at.get_by_key("sitemap_row_2").caption[0].value)

    def test_home_has_map_extras_and_footer_without_judgment_sections(self):
        at = self.app
        content = at.get_by_key("site_content")
        self.assertEqual(len(at.get("bidi_component")), 1)
        self.assertEqual([item.value for item in content.subheader],
                         ["마포구라면 이렇게 알아보세요", "자주 찾는 메뉴", "서울 자동차 현황", "25구 순위"])
        at.get_by_key("site_footer")
        for element in ("metric", "expander", "dataframe", "vega_lite_chart"):
            with self.subTest(element=element):
                self.assertFalse(at.get(element))
        self.assertNotIn("popover", {getattr(node, "type", "") for node in content})
        self.assertNotIn("두 동네 비교하기", [link.value for link in content.page_link])
        with self.assertRaises(KeyError):
            at.get_by_key("judgment_deck")

    def test_home_without_judgment_data_keeps_notice_and_footer(self):
        with patch("db.queries.get_district_ranking", return_value=pd.DataFrame()):
            self.app.run()
        self.assert_ready()
        self.assertTrue(any("동네 판정 자료가 없어요" in item.value for item in self.app.info))
        self.app.get_by_key("site_footer")
        with self.assertRaises(KeyError):
            self.app.get_by_key("home_extras")

    def test_partial_observation_notice_follows_the_selected_district(self):
        at = self.app
        at.switch_page("app_pages/ranking.py").run()
        self.assert_ready()
        notice = "이 구의 승객 수에는 일부 행정동 자료가 빠져"
        self.assertFalse(any(notice in c.value for c in at.caption))
        at.selectbox(key="district_id").select(self.ids["강서구"]).run()
        self.assert_ready()
        self.assertTrue(any(notice in c.value for c in at.caption))

    def test_missing_contract_columns_do_not_fabricate_values(self):
        missing = self.ranking.drop(columns=["parking_value", "parking_rank", "parking_level"])
        with patch("db.queries.get_district_ranking", return_value=missing):
            self.send_map_event("topic", "parking")
            data = self.map_data()
            self.app.switch_page("app_pages/ranking.py").run()
        self.assert_ready()
        self.assertEqual(self.app.metric[1].value, "자료 없음")
        self.assertEqual(self.app.metric[1].label, "차 100대당 주차면")
        self.assertTrue((self.ranking_table("parking").value["값"] == "자료 없음").all())
        self.assertIn("주차 여건 자료는 없어요", data["selected"]["sentence"])
        for district in data["district_data"]:
            verdict = next(v for v in district["verdicts"] if v["topic"] == "parking")
            self.assertEqual(verdict["level"], "자료 없음")
            self.assertEqual(verdict["value"], "자료 없음")
            self.assertEqual(verdict["rank"], "순위 자료 없음")
            self.assertIsNone(verdict["signal_index"])
            self.assertEqual(verdict["color"], "#E4E7E6")

    def test_small_positive_parking_value_is_not_displayed_as_zero(self):
        self.app.selectbox(key="district_id").select(self.ids["성동구"]).run()
        self.assert_ready()
        district = next(d for d in self.map_data()["district_data"] if d["name"] == "성동구")
        verdict = next(v for v in district["verdicts"] if v["topic"] == "parking")
        self.assertEqual(verdict["value"], "차 100대당 주차면 0.03면")
        self.app.switch_page("app_pages/ranking.py").run()
        self.assert_ready()
        self.assertEqual(self.app.metric[1].label, "차 100대당 주차면")
        self.assertEqual(self.app.metric[1].value, "0.03면")
        table = self.ranking_table("parking").value
        selected = table.loc[table["동네"].str.startswith("성동구")].iloc[0]
        self.assertEqual(selected["값"], "0.03면")

    def test_home_keeps_one_large_hero_and_no_duplicate_summary(self):
        self.assertEqual(len(self.app.get("bidi_component")), 1)
        with self.assertRaises(KeyError):
            self.app.get_by_key("neighborhood_summary")
        # AppTest는 브라우저 레이아웃을 계산하지 못하므로 CSS에 선언된 높이를 확인한다.
        css = self.map_proto().css_content
        hero = re.search(r"\.hero\s*\{[^}]*?\bheight:\s*(\d+)px", css)
        map_svg = re.search(r"\.seoul\s*\{[^}]*?\bheight:\s*(\d+)px", css)
        if hero is None or map_svg is None:
            self.fail("The desktop hero and map must declare their height")
        self.assertGreaterEqual(int(hero.group(1)), 640)
        self.assertLessEqual(int(hero.group(1)), 720)
        self.assertGreaterEqual(int(map_svg.group(1)), 560)

    def test_map_geometry_survives_streamlit_transport(self):
        from db import queries as q
        boundaries = q.get_region_boundaries()
        first_shapes = self.map_data()["boundaries"]
        component_id = self.map_proto().id
        for topic in ("ownership", "parking", "need"):
            with self.subTest(topic=topic):
                self.send_map_event("topic", topic)
                proto = self.map_proto()
                self.assertEqual(proto.id, component_id)
                self.assertEqual(proto.WhichOneof("data"), "json")
                data = self.map_data()
                self.assertEqual(data["topic"], topic)
                self.assertEqual(data["boundaries"], first_shapes)
                self.assertEqual(len(data["boundaries"]), 25)
                self.assertEqual({d["id"] for d in data["boundaries"]}, set(self.ids.values()))
                self.assertEqual({d["name"] for d in data["boundaries"]}, set(self.ids))
                view_box = re.search(r'<svg[^>]*class="seoul"[^>]*viewBox="0 0 ([\d.]+) ([\d.]+)"', proto.html_content)
                if view_box is None:
                    self.fail("The Seoul map must declare its coordinate system")
                width, height = map(float, view_box.groups())
                for district in data["boundaries"]:
                    boundary = boundaries.loc[boundaries.region_id == district["id"]].iloc[0]
                    geometry = json.loads(boundary.geometry_json)
                    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
                    ring_count = sum(len(polygon) for polygon in polygons)
                    self.assertEqual(district["path"].count("M"), ring_count)
                    self.assertEqual(district["path"].count("Z"), ring_count)
                    coordinates = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", district["path"])]
                    self.assertGreater(len(coordinates), 6)
                    self.assertEqual(len(coordinates) % 2, 0)
                    self.assertTrue(all(math.isfinite(v) for v in coordinates))
                    self.assertTrue(all(0 <= x <= width for x in coordinates[::2]))
                    self.assertTrue(all(0 <= y <= height for y in coordinates[1::2]))
                    self.assertTrue(0 <= district["x"] <= width and 0 <= district["y"] <= height)
                self.assertEqual(len(data["district_data"]), 25)
                self.assertEqual({d["id"] for d in data["district_data"]}, set(self.ids.values()))
                legend = {item["level"]: item["color"] for item in data["legend"]}
                for level, color in zip(TOPIC_LEVELS[topic], LEVEL_COLORS):
                    display_level = {"차가 필요한 편": "이용 적은 편", "있으면 편함": "이용 보통", "대중교통으로 충분": "이용 많은 편"}.get(level, level) if topic == "need" else level
                    self.assertEqual(legend[display_level], color)
                for district in data["district_data"]:
                    expected = self.ranking.loc[self.ranking.region_id == district["id"]].iloc[0]
                    self.assertEqual(district["name"], str(expected.district_name))
                    self.assertEqual(len(district["verdicts"]), 3)
                    for index, verdict in enumerate(district["verdicts"]):
                        criterion = tuple(TOPIC_LEVELS)[index]
                        level = str(expected[f"{criterion}_level"])
                        signal_index = TOPIC_LEVELS[criterion].index(level)
                        self.assertEqual(verdict["topic"], criterion)
                        self.assertEqual(verdict["level"], level)
                        self.assertEqual(verdict["signal_index"], signal_index)
                        self.assertEqual(verdict["color"], LEVEL_COLORS[signal_index])
                        self.assertEqual(verdict["value"], f"{TOPIC_UNITS[index]} {expected_values(expected)[index]}")
                        self.assertEqual(verdict["rank"],
                                         f"{TOPIC_ORDERS[criterion]} · 서울 25구 중 {int(expected[f'{criterion}_rank'])}위")
                self.assertFalse(any(
                    param.get("name") == "district"
                    for chart in self.app.get("vega_lite_chart")
                    for param in json.loads(chart.proto.spec).get("params", [])
                ))

    def test_map_selection_updates_district_and_all_judgments(self):
        self.send_map_event("district", self.ids["강남구"])
        self.assert_district("강남구")
        self.app.switch_page("app_pages/compare.py").run()
        self.assert_ready()
        self.assertEqual(self.app.selectbox(key="district_id").value, self.ids["강남구"])

    def test_map_can_reselect_same_district_after_external_selection(self):
        at = self.app
        map_id = self.map_proto().id
        self.send_map_event("district", self.ids["강남구"])
        self.assert_district("강남구")
        epoch = at.session_state["map_epoch"]
        self.assertEqual(self.map_proto().id, map_id)

        at.selectbox(key="district_id").select(self.ids["마포구"]).run()
        self.assert_ready()
        self.assert_district("마포구")
        self.assertGreater(at.session_state["map_epoch"], epoch)
        self.assertEqual(self.map_proto().id, map_id, "The hero must survive dropdown reruns without replaying")
        self.send_map_event("district", self.ids["강남구"])
        self.assert_district("강남구")

    def test_ranking_row_can_reselect_same_district_after_external_selection(self):
        at = self.app
        at.switch_page("app_pages/ranking.py").run()
        self.assert_ready()
        table = self.ranking_table("ownership")
        self.send_selection(table.proto.id, {"rank": [{"region_id": self.ids["서초구"]}]})
        self.assert_selected("서초구")
        self.assert_cards("서초구")
        at.selectbox(key="district_id").select(self.ids["강남구"]).run()
        self.assert_ready()
        self.assert_selected("강남구")
        self.assertNotEqual(self.ranking_table("ownership").proto.id, table.proto.id)
        self.send_selection(self.ranking_table("ownership").proto.id, {"rank": [{"region_id": self.ids["서초구"]}]})
        self.assert_selected("서초구")
        self.assert_cards("서초구")

    def test_ranking_lists_keep_all_sql_ranks_and_values(self):
        self.app.switch_page("app_pages/ranking.py").run()
        self.assert_ready()
        for topic, rank, value, scale, digits, unit in (
            ("ownership", "ownership_rank", "ownership_value", 1, 2, "대"),
            ("parking", "parking_rank", "parking_value", 100, 1, "면"),
            ("charging", "charger_per_electric_vehicle_rank", "charger_per_electric_vehicle", 1, 2, "기"),
            ("need", "need_rank", "need_value", 1, 2, "명"),
        ):
            with self.subTest(topic=topic):
                table = self.ranking_table(topic).value
                expected = self.ranking.sort_values([rank, "district_name"])
                self.assertEqual(table["동네"].tolist(), expected.district_name.astype(str).tolist())
                self.assertEqual(table["순위"].tolist(), [str(int(v)) for v in expected[rank]])
                labels = [f"{float(v) * scale:,.2f}{unit}" if topic == "parking" and float(v) * scale < 0.1
                          else f"{float(v) * scale:,.{digits}f}{unit}" for v in expected[value]]
                self.assertEqual(table["값"].tolist(), labels)

    def test_ranking_page_totals_notes_and_links_come_from_database(self):
        at = self.app
        at.switch_page("app_pages/ranking.py").run()
        self.assert_ready()
        total = lambda name: sum(int(value) for value in self.ranking[name])
        metrics = {item.label: item.value for item in at.metric}
        self.assertEqual(metrics["등록 차량"], f"{total('vehicle_count'):,}대")
        self.assertEqual(metrics["세대당 차량"], f"{total('vehicle_count') / total('household_count'):.2f}대")
        self.assertEqual(metrics["전기차"], f"{total('electric_count'):,}대")
        self.assertEqual(metrics["수록 충전기"], f"{total('listed_count'):,}기")
        self.assertEqual(metrics["수록 주차면"], f"{total('unique_space_count'):,}면")
        self.assertEqual(metrics["하루 대중교통 승객"], f"{total('transit_passenger_count'):,}명")
        captions = "\n".join(item.value for item in at.caption)
        for phrase in ("환경공단 자료", "강서구는 일부 행정동", "성동구는 수록 주차장이 1곳뿐",
                       "중구·종로구는", "아파트 주차장 제외", "2026.10.30 하루",
                       f"주민 1명당 {total('transit_passenger_count') / total('population'):.2f}명"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, captions)
        self.assertNotIn("공공 충전기", captions)
        self.assertFalse(any(value.startswith("약") for value in metrics.values()))
        self.assertTrue(any("세 판정의 기준" in item.value for item in at.markdown))
        links = {link.value: link.proto.page for link in at.get_by_key("site_content").page_link}
        self.assertEqual((links["두 동네 비교하기"], links["주차·충전 찾기"]), ("compare", "parking"))

    def test_ranking_page_missing_counts_are_not_understated(self):
        def changed(column, value, dtype):
            frame = self.ranking.copy()
            frame[column] = frame[column].astype(dtype)
            frame.loc[frame.index[0], column] = value
            return frame

        for frame, labels in (
            (changed("vehicle_count", pd.NA, "Int64"), ("등록 차량", "세대당 차량")),
            (changed("unique_missing_space_count", 2, "Int64"), ("수록 주차면",)),
            (changed("transit_passenger_count", pd.NA, "Int64"), ("하루 대중교통 승객",)),
            (changed("transit_passenger_per_resident", float("nan"), "float64"), ("하루 대중교통 승객",)),
        ):
            with self.subTest(labels=labels), patch("db.queries.get_district_ranking", return_value=frame):
                self.app.switch_page("app_pages/ranking.py").run()
                self.assert_ready()
                metrics = {item.label: item.value for item in self.app.metric}
                for label in labels:
                    self.assertEqual(metrics[label], "자료 없음")

    def test_missing_boundaries_keep_district_data_and_selection(self):
        with patch("db.queries.get_region_boundaries", return_value=pd.DataFrame()):
            self.app.run()
            self.assert_ready()
            self.assertEqual(self.map_data()["boundaries"], [])
            self.assertEqual(len(self.map_data()["district_data"]), 25)
            self.app.selectbox(key="district_id").select(self.ids["강남구"]).run()
            self.assert_ready()
            self.assert_district("강남구")

    def test_hero_topics_update_map_without_changing_identity(self):
        map_id = self.map_proto().id
        for topic in ("parking", "need", "ownership", "parking"):
            with self.subTest(topic=topic):
                self.send_map_event("topic", topic)
                self.assertEqual(self.app.session_state["topic"], topic)
                self.assertEqual(self.map_data()["topic"], topic)
                self.assertEqual(self.map_proto().id, map_id)
                self.assert_district("마포구")

    def test_invalid_hero_events_do_not_change_valid_selection(self):
        map_id = self.map_proto().id
        for value in (-1, "강남구", True):
            self.send_map_event("district", value)
            self.assert_district("마포구")
        self.send_map_event("topic", "unavailable")
        self.assertEqual(self.app.session_state["topic"], "ownership")
        self.assertEqual(self.map_proto().id, map_id)


class QueryFrameSafetyTest(unittest.TestCase):
    def test_widened_counts_do_not_overflow_when_multiplied(self):
        from db import queries as q
        from ui import load_frame

        counts = q.get_district_ranking()[["electric_count"]].dropna()
        counts = counts.loc[counts.electric_count.between(656, 65535)].astype("uint16")
        self.assertFalse(counts.empty, "Need a real small-int count that overflows when multiplied by 100")
        counts.attrs["source"] = "contract query"
        widened = load_frame(lambda: counts)
        self.assertEqual(str(widened.electric_count.dtype), "int64")
        self.assertEqual((widened.electric_count * 100).tolist(),
                         [int(value) * 100 for value in counts.electric_count])
        self.assertEqual(widened.attrs, counts.attrs)

    def test_widening_keeps_missing_values_and_large_unsigned_integers(self):
        from ui import load_frame

        frame = pd.DataFrame({"count": pd.Series([65000, None], dtype="UInt16"),
                              "large_count": pd.Series([2**63 + 7, None], dtype="UInt64")})
        widened = load_frame(lambda: frame)
        self.assertEqual(str(widened["count"].dtype), "Int64")
        self.assertEqual((widened["count"] * 100).iloc[0], 6500000)
        self.assertTrue(pd.isna(widened["count"].iloc[1]))
        self.assertEqual(int(widened.large_count.iloc[0]), 2**63 + 7)
        self.assertTrue(pd.isna(widened.large_count.iloc[1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
