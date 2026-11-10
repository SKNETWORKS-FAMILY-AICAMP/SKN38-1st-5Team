import unittest

from streamlit.testing.v1 import AppTest

import transit_savings


class EstimateTest(unittest.TestCase):
    def test_each_discount_is_taken_from_the_full_fare(self):
        result = transit_savings.estimate(90)
        self.assertEqual(result["cost"], 135_000)
        self.assertEqual(result["with_early"], 121_500)
        self.assertEqual(result["with_kpass"], 108_000)

    def test_kpass_needs_fifteen_rides(self):
        self.assertIsNone(transit_savings.estimate(14)["with_kpass"])
        self.assertEqual(transit_savings.estimate(15)["with_kpass"], 15 * 1500 * 0.8)


class DialogTest(unittest.TestCase):
    def test_more_button_opens_tips_and_calculator(self):
        app = AppTest.from_string("import transit_savings\ntransit_savings.teaser()\n").run()
        self.assertFalse(app.exception)
        app.button(key="transit_save_open").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.slider(key="transit_save_rides").value, 44)
        # AppTest는 창 안 조작도 전체를 다시 실행하므로, 창 상태 대신 저장된 값을 확인한다.
        app.segmented_control(key="transit_save_preset").set_value("매일 여러 번 (60번)").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["transit_save_rides"], 60)


if __name__ == "__main__":
    unittest.main()
