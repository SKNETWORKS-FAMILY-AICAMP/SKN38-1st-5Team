import unittest
import re
from unittest.mock import patch

import pandas as pd

import home_extras


class SeoulOverviewTest(unittest.TestCase):
    def setUp(self):
        self.ranking = pd.DataFrame({
            "vehicle_count": [1000] * 25, "household_count": [500] * 25,
            "electric_count": [100] * 25, "population": [2000] * 25,
            "listed_count": [20] * 25, "listed_station_count": [5] * 25,
            "fast_count": [4] * 25, "parking_value": [0.4] * 25,
            "need_value": [2.0] * 25,
        })

    def rendered(self, ranking=None):
        with patch.object(home_extras.st, "subheader"), patch.object(home_extras.st, "html") as html:
            home_extras.seoul_overview(self.ranking if ranking is None else ranking)
        return dict(re.findall(r"<div><dt>(.*?)</dt><dd>(.*?)</dd></div>", html.call_args.args[0]))

    def test_complete_totals_and_ratios_keep_existing_labels(self):
        cells = self.rendered()
        self.assertIn('25,000<small>대</small>', cells["등록 차량"])
        self.assertIn('2.00<small>대</small>', cells["세대당 차량"])
        self.assertIn('등록 차량의 10.0%', cells["전기차"])
        self.assertIn('약 1<small>만 면</small>', cells["수록 주차면"])
        self.assertIn('차 100대당 40.0면', cells["수록 주차면"])
        self.assertIn('약 10<small>만 명</small>', cells["하루 대중교통 승객"])
        self.assertIn('주민 1명당 2.00명', cells["하루 대중교통 승객"])

    def test_each_raw_sum_rejects_a_missing_district_without_hiding_other_cells(self):
        for column, label in (("vehicle_count", "등록 차량"), ("household_count", "세대당 차량"),
                              ("electric_count", "전기차"), ("listed_count", "수록 충전기")):
            with self.subTest(column=column):
                ranking = self.ranking.copy()
                ranking.loc[0, column] = float("nan")
                cells = self.rendered(ranking)
                self.assertTrue(cells[label].startswith('자료 없음<small>'))
                self.assertEqual(len(cells), 6)
                self.assertIn('약 10<small>만 명</small>', cells["하루 대중교통 승객"])
        for column, text in (("listed_station_count", "충전소 자료 없음곳"),
                             ("fast_count", "급속 자료 없음기")):
            ranking = self.ranking.copy()
            ranking.loc[0, column] = float("nan")
            self.assertIn(text, self.rendered(ranking)["수록 충전기"])

    def test_missing_weighted_inputs_do_not_become_zero_totals_or_ratios(self):
        for column, label, ratio in (("parking_value", "수록 주차면", "차 100대당 자료 없음면"),
                                     ("need_value", "하루 대중교통 승객", "주민 1명당 자료 없음명"),
                                     ("population", "하루 대중교통 승객", "주민 1명당 자료 없음명")):
            for missing_rows in ([0], list(range(25))):
                with self.subTest(column=column, missing_rows=len(missing_rows)):
                    ranking = self.ranking.copy()
                    ranking.loc[missing_rows, column] = float("nan")
                    cell = self.rendered(ranking)[label]
                    self.assertTrue(cell.startswith('자료 없음<small>'))
                    self.assertIn(ratio, cell)

    def test_genuine_zero_totals_and_zero_numerators_remain_zero(self):
        self.ranking[["electric_count", "listed_count", "listed_station_count", "fast_count",
                      "parking_value", "need_value"]] = 0
        cells = self.rendered()
        self.assertTrue(cells["전기차"].startswith('0<small>'))
        self.assertIn('등록 차량의 0.0%', cells["전기차"])
        self.assertIn('충전소 0곳 · 급속 0기', cells["수록 충전기"])
        self.assertTrue(cells["수록 주차면"].startswith('약 0<small>'))
        self.assertIn('차 100대당 0.0면', cells["수록 주차면"])
        self.assertTrue(cells["하루 대중교통 승객"].startswith('약 0<small>'))
        self.assertIn('주민 1명당 0.00명', cells["하루 대중교통 승객"])

    def test_zero_denominators_are_missing_ratios_not_exceptions(self):
        self.ranking[["vehicle_count", "household_count", "population"]] = 0
        cells = self.rendered()
        self.assertTrue(cells["등록 차량"].startswith('0<small>'))
        self.assertTrue(cells["세대당 차량"].startswith('자료 없음<small>'))
        self.assertIn('등록 차량의 자료 없음%', cells["전기차"])
        self.assertIn('주민 1명당 자료 없음명', cells["하루 대중교통 승객"])

    def test_partial_or_empty_dataset_does_not_claim_seoul_totals(self):
        for count in (0, 2, 24):
            with self.subTest(count=count):
                cells = self.rendered(self.ranking.head(count))
                self.assertEqual(len(cells), 6)
                self.assertTrue(all(cell.startswith('자료 없음<small>') for cell in cells.values()))


class TopRanksTest(unittest.TestCase):
    def rendered(self, last_value: float) -> str:
        ranking = pd.DataFrame({"district_name": ["강남구", "성동구"], "parking_value": [0.026, last_value]})
        with patch.object(home_extras.st, "subheader"), patch.object(home_extras.st, "caption"), \
                patch.object(home_extras.st, "html") as html:
            home_extras.top_ranks(ranking)
        return html.call_args.args[0]

    def test_small_positive_last_place_is_not_shown_as_zero(self):
        self.assertIn("성동구 0.03<", self.rendered(0.000294))

    def test_real_zero_stays_zero(self):
        self.assertIn("성동구 0.0<", self.rendered(0))


if __name__ == "__main__":
    unittest.main()
