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

    def test_home_details_preview_and_full(self):
        app = AppTest.from_file(ROOT / 'app.py', default_timeout=30).run()
        app.session_state['b_details'] = True
        app.run()
        self.assertFalse(app.exception)
        rows, _ = self.chart_rows(app, '서울 25구')
        self.assertEqual(len(rows), 3)
        app.toggle(key='ranking_ownership_show_all').set_value(True).run()
        rows, _ = self.chart_rows(app, '서울 25구')
        self.assertEqual(len(rows), 25)
        for topic in ['차량 구성', '주차·충전 시설', '시간대별 승객']:
            app.segmented_control(key='detail_topic').set_value(topic).run()
            self.assertFalse(app.exception, topic)
            if topic == '주차·충전 시설':
                app.segmented_control(key='detail_facility').set_value('충전기').run()
                self.assertFalse(app.exception)
                rows, _ = self.chart_rows(app, '충전소별')
                self.assertLessEqual(len(rows), 3)
                app.toggle(key='detail_charging_stations_show_all').set_value(True).run()
                self.assertFalse(app.exception)
            if topic == '시간대별 승객':
                rows, _ = self.chart_rows(app, '시간대별 수록')
                self.assertEqual(len(rows), 3)
                app.toggle(key='detail_passengers_show_all').set_value(True).run()
                rows, _ = self.chart_rows(app, '시간대별 수록')
                self.assertEqual(len(rows), 24)
