import ast
from pathlib import Path
import unittest
from unittest.mock import patch


class IdleNudgeTests(unittest.TestCase):
    def test_messages_cover_all_app_pages(self):
        from idle_nudge import MESSAGES

        source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        paths = []
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "st" and node.func.attr == "Page"):
                continue
            keywords = {item.arg: item.value for item in node.keywords}
            is_default = "default" in keywords and ast.literal_eval(keywords["default"])
            paths.append("" if is_default else ast.literal_eval(keywords["url_path"]))

        self.assertEqual(len(paths), 11)
        self.assertEqual(set(MESSAGES), set(paths))
        for path in paths:
            with self.subTest(page=path):
                self.assertIsInstance(MESSAGES[path], tuple)
                self.assertEqual(len(MESSAGES[path]), 2)
                self.assertTrue(all(isinstance(message, str) and message.strip()
                                    for message in MESSAGES[path]))

    def test_script_allows_clicks_to_pass_through(self):
        from idle_nudge import add_idle_nudge

        with patch("idle_nudge.st.html") as html:
            add_idle_nudge("")
        html.assert_called_once()
        self.assertRegex(html.call_args.args[0], r"pointer-events\s*:\s*none")
        self.assertTrue(html.call_args.kwargs["unsafe_allow_javascript"])


if __name__ == "__main__":
    unittest.main()
