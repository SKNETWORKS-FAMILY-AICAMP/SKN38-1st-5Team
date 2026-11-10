import itertools
import unittest
from unittest.mock import patch

import pandas as pd

import scene_seoul
from ui import mobility_mood, neighborhood_sentence


OWNERSHIP = ('많은 편', '보통', '적은 편')
PARKING = ('좋음', '보통', '빠듯함')
TRANSIT = ('차가 필요한 편', '있으면 편함', '대중교통으로 충분')


def district(ownership='보통', parking='보통', need='대중교통으로 충분'):
    return pd.Series(dict(region_id=1, district_name='테스트구', ownership_level=ownership,
                          parking_level=parking, need_level=need,
                          ownership_value=0.8, parking_value=0.6, need_value=2.4,
                          ownership_rank=12, parking_rank=13, need_rank=4))


class NeighborhoodContextTest(unittest.TestCase):
    def test_all_27_contexts_keep_each_observation_and_give_parking_advice(self):
        sentences = set()
        for ownership, parking, need in itertools.product(OWNERSHIP, PARKING, TRANSIT):
            with self.subTest(ownership=ownership, parking=parking, need=need):
                row = district(ownership, parking, need)
                original = row.copy(deep=True)
                sentence = neighborhood_sentence(row)
                sentences.add(sentence)
                self.assertIn({'많은 편': '차량 보유가 많은 편', '보통': '차량 보유는 보통',
                               '적은 편': '차량 보유가 적은 편'}[ownership], sentence)
                self.assertIn({'좋음': '여유 있는 편', '보통': '차량 대비 보통',
                               '빠듯함': '차량 대비 빠듯'}[parking], sentence)
                self.assertIn({'차가 필요한 편': '이용 지표는 낮은 편', '있으면 편함': '이용 지표는 보통',
                               '대중교통으로 충분': '이용 지표는 높은 편'}[need], sentence)
                self.assertIn('주차', sentence)
                self.assertIn('확인', sentence)
                self.assertNotIn('차가 필요한 편이에요', sentence)
                self.assertNotIn('차가 있으면 편해요', sentence)
                self.assertNotIn('대중교통으로 충분해요', sentence)
                self.assertNotIn('구매', sentence)
                self.assertEqual(sentence.count('.'), 3)
                pd.testing.assert_series_equal(row, original)
        self.assertEqual(len(sentences), 27)

    def test_songpa_many_cars_tight_parking_does_not_recommend_purchase(self):
        row = district('많은 편', '빠듯함', '차가 필요한 편')
        row['district_name'] = '송파구'
        sentence = neighborhood_sentence(row)
        self.assertNotIn('구매', sentence)
        self.assertIn('주차 공간부터 확인', sentence)
        self.assertIn('실제 대중교통 경로도 비교', sentence)

    def test_red_threshold_and_low_ownership_expressions(self):
        cases = (
            ('많은 편', '빠듯함', '대중교통으로 충분', 'crying'),
            ('보통', '빠듯함', '차가 필요한 편', 'crying'),
            ('많은 편', '좋음', '차가 필요한 편', 'crying'),
            ('적은 편', '빠듯함', '있으면 편함', 'smile'),
            ('적은 편', '보통', '있으면 편함', 'happy'),
            ('보통', '보통', '있으면 편함', 'smile'),
            ('적은 편', '좋음', '대중교통으로 충분', 'happy'),
        )
        for ownership, parking, transit, mood in cases:
            with self.subTest(ownership=ownership, parking=parking, transit=transit):
                self.assertEqual(mobility_mood(district(ownership, parking, transit)), mood)
        for ownership, parking, transit in itertools.product(OWNERSHIP, PARKING, TRANSIT):
            red_count = sum((ownership == '많은 편', parking == '빠듯함', transit == '차가 필요한 편'))
            self.assertEqual(mobility_mood(district(ownership, parking, transit)) == 'crying', red_count >= 2)

    def test_mapo_normal_ownership_parking_high_transit_is_happy(self):
        row = district()
        row['district_name'] = '마포구'
        self.assertEqual(mobility_mood(row), 'happy')
        self.assertIn('대중교통을 먼저 살펴보고', neighborhood_sentence(row))

    def test_missing_or_unknown_indicators_do_not_invent_bad_conditions(self):
        for field in ('ownership_level', 'parking_level', 'need_level'):
            for missing in (None, pd.NA, float('nan'), '', 'unknown'):
                with self.subTest(field=field, missing=missing):
                    row = district()
                    row[field] = missing
                    self.assertEqual(mobility_mood(row), 'smile')
                    self.assertIn('자료는 없', neighborhood_sentence(row))
        self.assertEqual(mobility_mood(pd.Series(dtype=object)), 'smile')

    def test_hero_payload_preserves_metrics_and_uses_context_for_every_combination(self):
        for levels in itertools.product(OWNERSHIP, PARKING, TRANSIT):
            with self.subTest(levels=levels):
                row = district(*levels)
                ranking = pd.DataFrame([row])
                def fetch(query):
                    return ranking if query is scene_seoul.q.get_district_ranking else pd.DataFrame()
                with patch.object(scene_seoul, 'load_frame', side_effect=fetch), \
                        patch.object(scene_seoul.st, 'session_state', {'district_id': 1, 'topic': 'need'}), \
                        patch.object(scene_seoul, '_HERO') as hero:
                    scene_seoul.render_hero('테스트구')
                data = hero.call_args.kwargs['data']
                self.assertEqual(data['selected']['sentence'], neighborhood_sentence(row))
                self.assertEqual(data['selected']['mobility_mood'], mobility_mood(row))
                verdicts = data['selected']['verdicts']
                self.assertEqual([v['level'] for v in verdicts], list(levels))
                self.assertIn('2.40명', verdicts[2]['value'])
                self.assertIn('4위', verdicts[2]['rank'])
                self.assertEqual(verdicts[2]['label'], '대중교통 이용 지표')
                self.assertEqual([v['level'] for v in data['legend']],
                                 ['이용 적은 편', '이용 보통', '이용 많은 편'])
                self.assertEqual(verdicts[2]['display_level'], data['legend'][TRANSIT.index(levels[2])]['level'])

    def test_accessible_copy_explains_proxy_and_announces_context(self):
        self.assertIn('role="status" aria-live="polite" aria-atomic="true"', scene_seoul.HTML)
        self.assertIn('개인의 차량 구매 필요를 뜻하지 않아요', scene_seoul.HTML)
        self.assertIn('${s.data.selected.sentence}', scene_seoul.JS)
        self.assertIn('${item.display_level}', scene_seoul.JS)
        self.assertNotIn("v.topic === 'need' ? -1", scene_seoul.JS)


if __name__ == '__main__':
    unittest.main()
