from contextlib import chdir, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from etl import crawl_faq, prepare


class PrepareTest(unittest.TestCase):
    def test_exception_keeps_previous_csv_and_continues_faq(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            previous = b"previous validated dataset\n"
            (output / "registration.csv").write_bytes(previous)
            (output / "validation.json").write_text('{"passed": true, "published": true}')
            with patch.object(prepare, "prepare_fuel", side_effect=ValueError("invalid input")):
                result = prepare.prepare_bundle(prepare.RAW, output)
            self.assertFalse(result["passed"])
            self.assertFalse(result["published"])
            self.assertEqual(result["faq"]["row_count"], 10)
            self.assertEqual((output / "registration.csv").read_bytes(), previous)
            self.assertFalse((output / "region.csv").exists())
            self.assertFalse(json.loads((output / "validation.json").read_text())["passed"])
            self.assertEqual(result["error"][0]["stage"], "fuel")

    def test_failed_check_does_not_publish(self):
        original = prepare.prepare_fuel

        def mismatched_fuel(region, registration, checks, output_dir):
            result = original(region, registration, checks, output_dir)
            prepare.record_check(checks, "의도한 검산 실패", False, True)
            return result

        with tempfile.TemporaryDirectory() as directory, patch.object(prepare, "prepare_fuel", side_effect=mismatched_fuel):
            output = Path(directory)
            result = prepare.prepare_bundle(prepare.RAW, output)
            self.assertFalse(result["passed"])
            self.assertFalse(result["published"])
            self.assertEqual(result["faq"]["row_count"], 10)
            self.assertEqual(list(output.glob("*.csv")), [])

    def test_repeat_is_identical_and_ignores_unowned_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "unrelated.csv").write_text("unrelated\nvalue\n")
            first = prepare.prepare_bundle(prepare.RAW, output)
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
            second = prepare.prepare_bundle(prepare.RAW, output)
            after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
            self.assertTrue(first["passed"] and second["passed"])
            self.assertTrue(first["published"] and second["published"])
            self.assertEqual(before, after)
            self.assertEqual(len(second["output_row_count"]), 14)
            self.assertNotIn("unrelated.csv", second["output_row_count"])

    def test_missing_source_invalidates_old_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            output.mkdir()
            (output / "validation.json").write_text('{"passed": true}')
            result = prepare.prepare_bundle(Path(directory) / "missing", output)
            self.assertFalse(result["passed"])
            self.assertFalse(json.loads((output / "validation.json").read_text())["passed"])

    def test_faq_default_input_is_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as directory, chdir(directory), redirect_stdout(io.StringIO()):
            target = Path(directory) / "preview.csv"
            crawl_faq.main(["--output", str(target)])
            self.assertTrue(target.exists())
