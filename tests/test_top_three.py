import json
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
from tests import app_env

ROOT = Path(__file__).resolve().parents[1]

class TopThreeTest(unittest.TestCase):
    def chart_rows(self, app, phrase):
        chart = next(c.proto for c in app.get('vega_lite_chart') if phrase in c.proto.alt)
        return convert_arrow_bytes_to_pandas_df(chart.datasets[0].data.data), json.loads(chart.spec)

    def test_ownership_top_three_and_full_ranking(self):
        app = AppTest.from_file(ROOT / 'app.py', default_timeout=30).run()
        app.switch_page('app_pages/ownership.py').run()
        self.assertFalse(app.exception)
        rows, spec = self.chart_rows(app, '세대당 차량 보유 순위')
        self.assertEqual(len(rows), 3)
        self.assertEqual(int(rows.highest.sum()), 1)
        app.toggle(key='ownership_ranking_show_all').set_value(True).run()
        self.assertFalse(app.exception)
        rows, _ = self.chart_rows(app, '세대당 차량 보유 순위')
        self.assertEqual(len(rows), 25)
        rows, _ = self.chart_rows(app, '차종별 등록 대수')
        self.assertEqual(len(rows), 3)
        app.toggle(key='ownership_vehicle_show_all').set_value(True).run()
        rows, _ = self.chart_rows(app, '차종별 등록 대수')
        self.assertEqual(len(rows), 4)

    def test_ranking_lists_show_top_five_lowest_and_full(self):
        from db import queries as q
        ranking = q.get_district_ranking()
        app = AppTest.from_file(ROOT / 'app.py', default_timeout=30).run()
        app.switch_page('app_pages/ranking.py').run()
        self.assertFalse(app.exception)
        for topic, phrase, rank in (('ownership', '세대당 차량 많은 순', 'ownership_rank'),
                                    ('parking', '수록 주차면 많은 순', 'parking_rank'),
                                    ('charging', '수록 충전기 많은 순', 'charger_per_electric_vehicle_rank'),
                                    ('need', '대중교통 이용 많은 순', 'need_rank')):
            with self.subTest(topic=topic):
                rows, _ = self.chart_rows(app, phrase)
                expected = sorted(int(value) for value in ranking[rank] if int(value) <= 5 or int(value) == int(ranking[rank].max()))
                self.assertEqual([int(value) for value in rows.rank_label], expected)
                self.assertEqual(int(rows.highest.sum()), 1)
                app.toggle(key=f'ranking_{topic}_show_all').set_value(True).run()
                self.assertFalse(app.exception)
                rows, _ = self.chart_rows(app, phrase)
                self.assertEqual(len(rows), 25)

    def test_ranking_preview_handles_missing_and_tied_ranks(self):
        from unittest.mock import patch
        import pandas as pd
        from db import queries as q
        ranking = q.get_district_ranking()
        all_missing = ranking.assign(ownership_rank=pd.Series(pd.NA, index=ranking.index, dtype='Int64'))
        tied = ranking.assign(ownership_rank=[1, 1, 1, 4, 4, 4, *range(7, 26)])
        for frame, phrase, count in ((ranking.drop(columns=['ownership_rank']), '세대당 차량 많은 순', 25),
                                     (all_missing, '세대당 차량 많은 순', 25),
                                     (tied, '세대당 차량 많은 순', 7),
                                     (ranking.drop(columns=['charger_per_electric_vehicle_rank', 'charger_per_electric_vehicle']),
                                      '수록 충전기 많은 순', 25)):
            with self.subTest(count=count, phrase=phrase), patch('db.queries.get_district_ranking', return_value=frame):
                app = AppTest.from_file(ROOT / 'app.py', default_timeout=30).run()
                app.switch_page('app_pages/ranking.py').run()
                self.assertFalse(app.exception, [item.message for item in app.exception])
                self.assertEqual(len(self.chart_rows(app, phrase)[0]), count)
