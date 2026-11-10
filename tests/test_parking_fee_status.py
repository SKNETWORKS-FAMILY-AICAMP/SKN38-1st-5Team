import unittest

import pandas as pd

from parking_explorer import charger_records, map_html, map_payload, parking_records


class ParkingFeeStatusTest(unittest.TestCase):
    def test_public_fee_flag_not_amount_controls_status(self):
        for flag, expected in [('N', 'free'), ('Y', 'paid'), (None, 'unknown')]:
            with self.subTest(flag=flag):
                rows = parking_records([{'parking_code': 'sample', 'pay_yn': flag,
                                         'position_list': [{'lat': 37.55, 'lng': 126.98}],
                                         'rates': 0, 'time_rate': 10}])
                self.assertEqual(rows[0]['fee_status'], expected)
                self.assertEqual(map_payload(rows)['places'][0]['fee_status'], expected)

    def test_charger_mixed_or_missing_parking_fee_is_not_free(self):
        points = pd.DataFrame([{'place_id': 1, 'place_name': '시험 충전소', 'address': '시험 주소',
                                'latitude': 37.55, 'longitude': 126.98, 'charger_count': 2,
                                'operator_name': '시험 운영사'}])
        for flags, expected in [(['Y', 'Y'], 'free'), (['N', 'N'], 'paid'),
                                (['Y', 'N'], 'unknown'), (['Y', None], 'unknown')]:
            with self.subTest(flags=flags):
                devices = pd.DataFrame({'station_id': [1, 1], 'parking_free': flags})
                record = charger_records(points, devices)[0]
                self.assertEqual(record['fee_status'], expected)
                self.assertIn('충전요금: 금액 정보 미제공', record['price'])

    def test_unknown_values_remain_neutral_and_source_text_is_escaped(self):
        base = {'id': 'sample', 'latitude': 37.55, 'longitude': 126.98,
                'name': '</script><script>alert(1)</script>', 'price': '무료라는 검색어'}
        for invalid in (None, 'FREE', '<script>', {'free': True}):
            payload = map_payload([{**base, 'fee_status': invalid}])
            self.assertEqual(payload['places'][0]['fee_status'], 'unknown')
        page = map_html([{**base, 'fee_status': 'free'}])
        self.assertNotIn(base['name'], page)
        self.assertIn('주차 무료', page)
