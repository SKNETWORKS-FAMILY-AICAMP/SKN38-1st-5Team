import unittest
from unittest.mock import patch

import pandas as pd

import home_extras


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
