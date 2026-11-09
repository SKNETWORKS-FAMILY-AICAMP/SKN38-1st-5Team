from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

from etl.prepare import RAW
from etl.prepare_snapshot import prepare_traffic, prepare_transit


class SnapshotTest(unittest.TestCase):
    def test_traffic_rejects_shifted_period(self):
        path = RAW / "api_research/seoul_traffic/traffic_202609.xlsx"
        original = pd.read_excel
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs.get("sheet_name") == "2026년 09월":
                result["일자"] = result["일자"].str.replace("202609", "202608", regex=False)
            return result
        with patch("etl.prepare_snapshot.pd.read_excel", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "관측일"):
                prepare_traffic(path)

    def test_transit_rejects_wrong_date_or_analysis_type(self):
        frame = pd.read_csv(RAW / "api_research/seoul_passenger/tpss.csv", dtype=str)
        for column, original, value in [("기준일", "20261030", "20261029"), ("분석유형", "4", "5")]:
            changed = frame.copy()
            # 날짜별 426행과 집계 행 수를 유지해 날짜·유형 오류가 건수로는 드러나지 않게 한다.
            changed.loc[changed[column].eq(original), column] = value
            with self.subTest(column=column), patch("etl.prepare_snapshot.pd.read_csv", return_value=changed):
                with self.assertRaisesRegex(ValueError, "고정 수집본"):
                    prepare_transit(Path("unused.csv"))
