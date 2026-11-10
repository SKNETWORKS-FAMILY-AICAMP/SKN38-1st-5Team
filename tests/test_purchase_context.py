import unittest
import pandas as pd
from ui import purchase_context


class PurchaseContextTest(unittest.TestCase):
    def setUp(self):
        self.ranking = pd.DataFrame({'population': [100, 300, 500, 700, 900]})
        self.traffic = pd.DataFrame({'avg_vehicles_per_point': [70] * 24,
                                    'seoul_avg_vehicles_per_point': [100] * 24,
                                    'observed_hour_count': [1] * 24,
                                    'complete_hour_count': [1] * 24})

    def mood(self, population=100, parking='좋음'):
        return purchase_context(pd.Series({'population': population, 'parking_level': parking}),
                                self.ranking, self.traffic)[0]

    def test_low_traffic_low_population_good_parking_is_happy(self):
        self.assertEqual(self.mood(), 'happy')
        self.assertEqual(self.mood(population=500), 'smile')
        self.assertEqual(self.mood(parking='보통'), 'smile')

    def test_two_adverse_conditions_are_crying(self):
        self.traffic['avg_vehicles_per_point'] = 140
        self.assertEqual(self.mood(population=900), 'crying')
        self.assertEqual(self.mood(parking='빠듯함'), 'crying')
        self.assertEqual(self.mood(), 'smile')

    def test_missing_or_incomplete_observations_stay_neutral(self):
        self.traffic.loc[0, 'complete_hour_count'] = 0
        self.assertEqual(self.mood(), 'smile')
        self.traffic = pd.DataFrame()
        self.assertEqual(self.mood(), 'smile')

    def test_traffic_threshold_boundaries(self):
        self.traffic['avg_vehicles_per_point'] = 85
        self.assertEqual(self.mood(), 'happy')
        self.traffic['avg_vehicles_per_point'] = 86
        self.assertEqual(self.mood(), 'smile')

    def test_low_transit_usage_and_crowded_population_are_caution(self):
        row = pd.Series({'population': 900, 'parking_level': '보통', 'need_level': '차가 필요한 편'})
        self.assertEqual(purchase_context(row, self.ranking, self.traffic)[0], 'crying')
