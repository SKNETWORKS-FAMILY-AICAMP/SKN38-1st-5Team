from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import Mock, patch

from etl.load import LoadReportError, main


class LoadReportTest(unittest.TestCase):
    def test_committed_data_is_not_reported_as_rolled_back(self):
        output = StringIO()
        engine = Mock()
        with patch("sys.argv", ["etl.load"]), patch("etl.load.get_engine", return_value=engine), patch("etl.load.load_data", side_effect=LoadReportError), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertIn("커밋되었습니다", output.getvalue())
        self.assertIn("보고서 저장에 실패", output.getvalue())
        self.assertNotIn("롤백", output.getvalue())
        engine.dispose.assert_called_once()

    def test_unknown_failure_does_not_claim_commit_or_rollback(self):
        output = StringIO()
        with patch("sys.argv", ["etl.load"]), patch("etl.load.get_engine", side_effect=ValueError), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertNotIn("커밋되었습니다", output.getvalue())
        self.assertNotIn("롤백", output.getvalue())
