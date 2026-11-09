import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scoring import compute_score, condition_judgment


class ScoringTest(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({"region_id": range(1, 26), "parking_per_vehicle": range(25),
                             "charger_per_electric_vehicle": range(25), "vehicle_per_household": range(24, -1, -1)})

    def test_direction_and_equal_weight(self):
        score = compute_score(self.frame())
        self.assertEqual(score.score.iloc[0], 0)
        self.assertEqual(score.score.iloc[-1], 100)
        self.assertEqual(score.judgment.iloc[0], "보류")
        self.assertEqual(score.judgment.iloc[12], "조건 확인")
        self.assertEqual(score.judgment.iloc[-1], "권장")

    def test_tie_is_average_rank(self):
        frame = self.frame()
        frame.loc[:, ["parking_per_vehicle", "charger_per_electric_vehicle", "vehicle_per_household"]] = 1
        self.assertTrue(compute_score(frame).score.eq(50).all())

    def test_missing_does_not_reweight_or_reduce_population(self):
        frame = self.frame()
        frame["parking_per_vehicle"] = frame.parking_per_vehicle.astype(float)
        frame.loc[0, "parking_per_vehicle"] = np.nan
        self.assertTrue(compute_score(frame).score.isna().all())
        self.assertTrue(compute_score(frame).judgment.eq("자료 부족").all())
        with self.assertRaises(ValueError):
            compute_score(frame.iloc[:2])

    def test_invalid_weight_is_rejected(self):
        with patch("scoring.SCORE_WEIGHT", {"parking": 0.4, "charging": 0.4, "registration": 0.4}):
            with self.assertRaises(ValueError):
                compute_score(self.frame())

    def test_judgment_uses_unrounded_score(self):
        frame = self.frame()
        frame["charger_per_electric_vehicle"] = range(24, -1, -1)
        frame["vehicle_per_household"] = 1
        for parking, charging, raw, expected in [(0.1002, 0.4998, 69.98, "조건 확인"),
                                                 (0.4002, 0.1998, 39.98, "보류"),
                                                 (0.1, 0.5, 70.0, "권장"),
                                                 (0.4, 0.2, 40.0, "조건 확인")]:
            with self.subTest(raw=raw), patch("scoring.SCORE_WEIGHT", {"parking": parking, "charging": charging, "registration": 0.4}):
                result = compute_score(frame).iloc[0]
                self.assertAlmostEqual(result.score_raw, raw)
                self.assertEqual(result.judgment, expected)

    def test_personal_condition_cannot_upgrade_or_fill_missing(self):
        for base, parking, charging, expected in [
            ("보류", "미확인", "미확인", "보류"),
            ("보류", "가능", "가능", "보류"),
            ("권장", "미확인", "가능", "조건 확인"),
            ("권장", "어려움", "가능", "보류"),
            ("조건 확인", "가능", "가능", "조건 확인"),
            ("자료 부족", "가능", "가능", "자료 부족"),
        ]:
            with self.subTest(base=base, parking=parking, charging=charging):
                self.assertEqual(condition_judgment(base, parking, charging), expected)

    def test_pm_missing_axis_is_insufficient_in_both_tabs(self):
        frame = self.frame().astype({"parking_per_vehicle": float})
        frame.loc[0, "parking_per_vehicle"] = np.nan
        result = compute_score(frame)
        self.assertTrue(result.score.isna().all())
        self.assertTrue(result.score_raw.isna().all())
        self.assertTrue(result.judgment.eq("자료 부족").all())
        self.assertEqual(condition_judgment(result.judgment.iloc[0], "가능", "가능"), "자료 부족")

    def test_pm_changed_weight_does_not_round_across_threshold(self):
        frame = self.frame()
        frame["charger_per_electric_vehicle"] = range(24, -1, -1)
        frame["vehicle_per_household"] = range(25)
        # 마지막 구는 주차 백분위만 100이므로 주차 가중치로 판정 경계를 만든다.
        for weight, expected in [(0.6996, "조건 확인"), (0.3996, "보류")]:
            other = (1 - weight) / 2
            with self.subTest(weight=weight), patch("scoring.SCORE_WEIGHT", {"parking": weight, "charging": other, "registration": other}):
                result = compute_score(frame).iloc[-1]
                self.assertAlmostEqual(result.score_raw, weight * 100)
                self.assertEqual(result.score, round(weight * 100, 1))
                self.assertEqual(result.judgment, expected)
