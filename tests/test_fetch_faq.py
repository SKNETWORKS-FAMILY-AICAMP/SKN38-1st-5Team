from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd
from selenium.common.exceptions import TimeoutException

from etl import crawl_faq, fetch_faq


HTML = ('<nav><li><h3>Menu</h3><p>Ignore</p></li></nav>'
        '<section class="faq" aria-labelledby="ev-care-faq-title">'
        '<li><h3>Question</h3><p>First</p><p>Second</p></li></section>')


class FaqCollectionTest(unittest.TestCase):
    def test_offline_default_and_explicit_collection_date(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.html"
            source.write_text(HTML, encoding="utf-8")
            self.assertEqual(crawl_faq.extract_faq(source).fetched_on.tolist(), ["2026-11-05"])
            result = crawl_faq.extract_faq(source, "2026-11-10")
            self.assertEqual(result.fetched_on.tolist(), ["2026-11-10"])
            self.assertEqual(result.answer_text.tolist(), ["First\nSecond"])
            with self.assertRaises(ValueError):
                crawl_faq.extract_faq(source, "not-a-date")

    def test_offline_cli_accepts_actual_capture_date(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.html", Path(directory) / "faq.csv"
            source.write_text(HTML, encoding="utf-8")
            crawl_faq.main(["--input", str(source), "--output", str(output),
                            "--fetched-on", "2026-11-10"])
            self.assertEqual(pd.read_csv(output).fetched_on.tolist(), ["2026-11-10"])

    def test_live_fixed_url_wait_timestamp_and_cleanup(self):
        driver = Mock(page_source=HTML)
        captured = datetime(2026, 11, 10, 9, 12, 34, tzinfo=ZoneInfo("Asia/Seoul"))
        with patch("selenium.webdriver.Chrome", return_value=driver), \
                patch("selenium.webdriver.support.ui.WebDriverWait") as wait, \
                patch.object(fetch_faq, "datetime") as clock:
            clock.now.return_value = captured
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "faq.csv"
                self.assertEqual(fetch_faq.fetch_faq(output, 7), 1)
                frame = pd.read_csv(output)
        driver.get.assert_called_once_with(crawl_faq.SOURCE_URL)
        driver.set_page_load_timeout.assert_called_once_with(7)
        wait.assert_called_once_with(driver, 7)
        wait.return_value.until.assert_called_once()
        driver.quit.assert_called_once()
        self.assertEqual(frame.fetched_on.tolist(), ["2026-11-10"])
        self.assertEqual(frame.collected_at.tolist(), ["2026-11-10T09:12:34+09:00"])
        self.assertEqual(frame.source_url.tolist(), [crawl_faq.SOURCE_URL])

    def test_failure_preserves_output_and_quits(self):
        for failure in ("navigation", "wait", "selector", "duplicate"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "faq.csv"
                output.write_bytes(b"previous verified CSV")
                driver = Mock(page_source=HTML)
                if failure == "navigation":
                    driver.get.side_effect = TimeoutException()
                elif failure == "selector":
                    driver.page_source = "<html>Not the expected FAQ page</html>"
                elif failure == "duplicate":
                    driver.page_source = HTML + HTML
                with patch("selenium.webdriver.Chrome", return_value=driver), \
                        patch("selenium.webdriver.support.ui.WebDriverWait") as wait:
                    if failure == "wait":
                        wait.return_value.until.side_effect = TimeoutException()
                    with self.assertRaises((TimeoutException, ValueError)):
                        fetch_faq.fetch_faq(output)
                driver.quit.assert_called_once()
                self.assertEqual(output.read_bytes(), b"previous verified CSV")

    def test_invalid_timeout_never_starts_browser(self):
        with patch("selenium.webdriver.Chrome") as chrome:
            for timeout in (0, -1, float("inf"), float("nan")):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    fetch_faq.collect_faq(timeout)
            chrome.assert_not_called()

    def test_write_failure_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "faq.csv"
            output.write_bytes(b"previous verified CSV")
            frame = crawl_faq.extract_faq_html(HTML)
            with patch.object(fetch_faq, "collect_faq", return_value=frame), \
                    patch.object(pd.DataFrame, "to_csv", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    fetch_faq.fetch_faq(output)
            self.assertEqual(output.read_bytes(), b"previous verified CSV")


if __name__ == "__main__":
    unittest.main()
