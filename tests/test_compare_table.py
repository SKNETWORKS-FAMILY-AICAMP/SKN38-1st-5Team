import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
import pandas as pd
from streamlit.testing.v1 import AppTest

from tests import app_env
from db import queries as q


APP = Path(__file__).resolve().parents[1] / "app.py"


def table_from_app(app):
    for element in app.get("html"):
        table = BeautifulSoup(element.proto.body, "html.parser").select_one(".compare-table")
        if table is not None:
            return table
    raise AssertionError("비교표가 표시되지 않았어요.")


def cells_for(table, field):
    return table.find("th", id=f"compare-{field}").find_parent("tr").find_all("td")


class CompareTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        regions = q.get_filter_options()["regions"]
        cls.ids = dict(zip(regions.district_name.astype(str), regions.region_id.astype("int64")))

    def setUp(self):
        self.app = AppTest.from_file(APP, default_timeout=30).run()
        self.app.switch_page("app_pages/compare.py").run()
        self.app.selectbox(key="compare_first_id").select(self.ids["마포구"]).run()
        self.app.selectbox(key="compare_id").select(self.ids["성동구"]).run()
        self.comparison = q.get_compare_metrics(self.ids["마포구"], self.ids["성동구"]).copy()
        self.ready()

    def ready(self):
        self.assertFalse(self.app.exception, [item.message for item in self.app.exception])
        self.assertFalse(self.app.error, [item.value for item in self.app.error])

    def render(self, frame):
        with patch("db.queries.get_compare_metrics", return_value=frame):
            self.app.run()
        self.ready()
        return table_from_app(self.app)

    def test_twelve_rows_keep_districts_values_and_sql_ranks_aligned(self):
        table = table_from_app(self.app)
        self.assertEqual([item.get_text(strip=True) for item in table.select(".compare-group")],
                         ["차와 주차", "대중교통", "전기차", "동네 규모"])
        self.assertEqual(len(table.select("tbody tr:not(.compare-group)")), 12)
        self.assertEqual([item.get_text(strip=True) for item in table.select(".compare-name")],
                         ["마포구", "성동구"])
        fields = (
            ("ownership_value", 2, "대", 1, "ownership_rank"),
            ("parking_value", 1, "면", 100, "parking_rank"),
            ("need_value", 2, "명", 1, "need_rank"),
            ("charger_per_electric_vehicle", 2, "기", 1, "charger_per_electric_vehicle_rank"),
            ("electric_share_pct", 2, "%", 1, "electric_share_pct_rank"),
            ("listed_station_count", 0, "묶음", 1, "listed_station_count_rank"),
            ("fast_count", 0, "기", 1, "fast_count_rank"),
            ("population", 0, "명", 1, None),
            ("household_count", 0, "세대", 1, None),
            ("vehicle_count", 0, "대", 1, "vehicle_count_rank"),
        )
        for field, digits, unit, scale, rank_field in fields:
            cells = cells_for(table, field)
            self.assertEqual(len(cells), 2)
            for index, (_, row) in enumerate(self.comparison.iterrows()):
                with self.subTest(field=field, district=row.district_name):
                    value = float(row[field]) * scale
                    precision = 2 if field == "parking_value" and 0 < value < 0.1 else digits
                    self.assertEqual(cells[index].select_one(".compare-value").get_text(),
                                     f"{value:,.{precision}f}{unit}")
                    rank = cells[index].select_one(".compare-rank")
                    if rank_field:
                        self.assertIn(f"서울 25구 중 {int(row[rank_field])}위", rank.get_text())
                    else:
                        self.assertIsNone(rank)
        for field in ("parking_level", "need_level"):
            self.assertEqual([cell.select_one(".compare-value").get_text() for cell in cells_for(table, field)],
                             self.comparison[field].astype(str).tolist())
        self.assertEqual(len(table.select(".compare-judgment")), 6)
        for index, (_, row) in enumerate(self.comparison.iterrows()):
            header = table.find(id=f"compare-district-{index}").get_text()
            for topic in ("ownership", "parking", "need"):
                self.assertIn(str(row[f"{topic}_level"]), header)

    def test_small_positive_parking_and_coverage_notes_are_preserved(self):
        table = table_from_app(self.app)
        seongdong = cells_for(table, "parking_value")[1]
        self.assertEqual(seongdong.select_one(".compare-value").get_text(), "0.03면")
        captions = "\n".join(item.value for item in self.app.caption)
        self.assertIn("성동구는 수록 주차장이 1곳뿐", captions)
        self.assertIn("아파트 주차장은 빠져", captions)
        self.assertIn("장소 수가 아니라 운영 묶음 수", captions)
        self.assertIn("좋고 나쁨을 뜻하지", captions)

    def test_missing_values_never_become_zero_or_receive_rank_or_more(self):
        fields = ("ownership_value", "parking_value", "need_value", "charger_per_electric_vehicle",
                  "electric_share_pct", "listed_station_count", "fast_count", "population",
                  "household_count", "vehicle_count", "parking_level", "need_level")
        for missing in (None, pd.NA, float("nan")):
            with self.subTest(missing=repr(missing)):
                frame = self.comparison.astype(object)
                frame.loc[frame.index[0], list(fields)] = missing
                table = self.render(frame)
                for field in fields:
                    cells = cells_for(table, field)
                    self.assertEqual(cells[0].select_one(".compare-value").get_text(), "자료 없음")
                    self.assertIsNone(cells[0].select_one(".compare-rank"))
                    self.assertFalse(any(cell.select_one(".compare-more") for cell in cells))
                for field in ("ownership_value", "parking_value", "need_value"):
                    self.assertEqual([cell.select_one(".compare-difference").get_text()
                                      for cell in cells_for(table, field)], ["비교 자료 없음"] * 2)

    def test_missing_district_row_does_not_reuse_the_other_district(self):
        table = self.render(self.comparison.iloc[:1])
        self.assertEqual(table.find(id="compare-district-1").select_one(".compare-name").get_text(), "성동구")
        for row in table.select("tbody tr:not(.compare-group)"):
            cells = row.find_all("td")
            self.assertEqual(cells[1].select_one(".compare-value").get_text(), "자료 없음")
            self.assertFalse(row.select(".compare-more"))

    def test_ranks_are_sql_values_and_missing_ranks_are_omitted(self):
        frame = self.comparison.copy()
        frame["charger_per_electric_vehicle"] = [0.5, 0.5]
        frame["charger_per_electric_vehicle_rank"] = [19, 19]
        frame["vehicle_count_rank"] = [23, 4]
        frame["fast_count_rank"] = pd.NA
        frame = frame.drop(columns="electric_share_pct_rank")
        table = self.render(frame)
        for field, ranks in (("charger_per_electric_vehicle", (19, 19)), ("vehicle_count", (23, 4))):
            for cell, rank in zip(cells_for(table, field), ranks):
                self.assertEqual(cell.select_one(".compare-rank").get_text(), f"서울 25구 중 {rank}위")
        for field in ("fast_count", "electric_share_pct", "population", "household_count"):
            self.assertFalse(any(cell.select_one(".compare-rank") for cell in cells_for(table, field)))
        self.assertFalse(any(cell.select_one(".compare-more")
                             for cell in cells_for(table, "charger_per_electric_vehicle")))

    def test_more_uses_display_precision_in_both_directions(self):
        frame = self.comparison.copy()
        cases = ((0.5, 0.5, None), (0.500001, 0.5, None), (0.51, 0.5, 0), (0.5, 0.51, 1))
        for first, second, marked in cases:
            with self.subTest(first=first, second=second):
                for field in ("charger_per_electric_vehicle", "electric_share_pct"):
                    frame[field] = [first, second]
                table = self.render(frame)
                for field in ("charger_per_electric_vehicle", "electric_share_pct"):
                    for index, cell in enumerate(cells_for(table, field)):
                        badge = cell.select_one(".compare-more")
                        self.assertEqual(badge.get_text() if badge else None, "더 많음" if index == marked else None)
        frame["fast_count"] = [0, 1]
        table = self.render(frame)
        cells = cells_for(table, "fast_count")
        self.assertEqual(cells[0].select_one(".compare-value").get_text(), "0기")
        self.assertIsNone(cells[0].select_one(".compare-more"))
        self.assertEqual(cells[1].select_one(".compare-more").get_text(), "더 많음")

    def test_partial_transit_never_marks_either_value_as_more(self):
        frame = self.comparison.copy()
        frame["need_value"] = [9.0, 1.0]
        frame["transit_observed_hour_count"] = [24, 24]
        frame["transit_complete_hour_count"] = [23, 24]
        table = self.render(frame)
        cells = cells_for(table, "need_value")
        self.assertFalse(any(cell.select_one(".compare-more") for cell in cells))
        self.assertTrue(all("부분 관측" in cell.select_one(".compare-difference").get_text() for cell in cells))
        self.assertTrue(any("마포구는 일부 행정동" in item.value for item in self.app.caption))

    def test_judgment_text_is_escaped_in_table(self):
        frame = self.comparison.copy()
        text = '<img src=x onerror="alert(1)"> & 자료'
        frame["parking_level"] = text
        table = self.render(frame)
        self.assertFalse(table.select("img, script"))
        self.assertEqual(cells_for(table, "parking_level")[0].select_one(".compare-value").get_text(), text)

    def test_empty_comparison_keeps_pickers_and_shows_message(self):
        with patch("db.queries.get_compare_metrics", return_value=self.comparison.iloc[:0]):
            self.app.run()
        self.ready()
        self.assertTrue(any("비교 자료가 없어요" in item.value for item in self.app.info))
        self.assertEqual(self.app.selectbox(key="compare_first_id").value, self.ids["마포구"])
        self.assertEqual(self.app.selectbox(key="compare_id").value, self.ids["성동구"])
        self.assertFalse(any("compare-table" in element.proto.body for element in self.app.get("html")))


if __name__ == "__main__":
    unittest.main()
