import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import os
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from click.testing import CliRunner
from starlette.applications import Starlette
from starlette.routing import Route
import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.web.cli import main as streamlit_cli

from tests import app_env
from asgi_app import SECURITY_HEADERS, SecurityMiddleware, robots_txt
from scripts.check_before_push import content_findings, main, scan, tracked_files, worktree_files
import security


ROOT = Path(__file__).resolve().parents[1]
BROWSER = "Mozilla/5.0 Chrome/130.0.0.0 Safari/537.36"


class BotPolicyTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"CHACHACHA_ALLOW_BOTS": "0"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_missing_and_known_user_agents_are_blocked_case_insensitively(self):
        for value in (None, "", " ", *security.BOT_MARKERS):
            with self.subTest(value=value):
                self.assertTrue(security.is_blocked_user_agent(value))
                if value and value.strip():
                    self.assertTrue(security.is_blocked_user_agent(f"Mozilla/5.0 {value.upper()}/1.0"))
        self.assertFalse(security.is_blocked_user_agent(BROWSER))

    def test_only_exact_environment_override_allows_bots(self):
        for value in ("0", "true", "yes", ""):
            with patch.dict(os.environ, {"CHACHACHA_ALLOW_BOTS": value}):
                self.assertTrue(security.is_blocked_user_agent("curl/8"))
        with patch.dict(os.environ, {"CHACHACHA_ALLOW_BOTS": "1"}):
            self.assertFalse(security.is_blocked_user_agent(None))

    def test_ip_source_priority_validation_and_forwarded_fallback(self):
        headers = {"X-Forwarded-For": "192.0.2.1, 192.0.2.2"}
        self.assertEqual(security.client_ip(headers, "2001:0db8::1"), "2001:db8::1")
        self.assertEqual(security.client_ip(headers, None), "192.0.2.1")
        self.assertIsNone(security.client_ip({"x-forwarded-for": "invalid"}, None))

    def test_guard_stops_before_any_page_content_and_keeps_valid_requests(self):
        source = "from security import guard_request\nimport streamlit as st\nguard_request()\nst.success('페이지 실행')"
        for agent, allowed in ((None, False), ("curl/8", False), (BROWSER, True)):
            with self.subTest(agent=agent), patch.object(st, "context", SimpleNamespace(
                    headers={} if agent is None else {"User-Agent": agent}, ip_address="192.0.2.30")):
                with patch("security.request_limiter", return_value=security.RequestLimiter()):
                    app = AppTest.from_string(source).run()
                self.assertFalse(app.exception)
                self.assertEqual(bool(app.success), allowed)
                self.assertEqual(bool(app.info), not allowed)

    def test_override_keeps_rate_limits_and_dev_mode_only_disables_deterrent(self):
        limiter = security.RequestLimiter()
        for _ in range(120):
            limiter.check("limited-session", None)
        with patch.dict(os.environ, {"CHACHACHA_ALLOW_BOTS": "1", "CHACHACHA_DEV": "1"}), \
                patch("security.request_limiter", return_value=limiter):
            app = AppTest.from_string("from security import guard_request\nguard_request()")
            app.session_state["_security_session_id"] = "limited-session"
            app.run()
            self.assertTrue(any("초 뒤" in item.value for item in app.info))
            with patch("security.st.html") as html:
                security.add_view_deterrent()
                self.assertIn("abort()", html.call_args.args[0])
                self.assertNotIn("addEventListener", html.call_args.args[0])


class RateLimitTests(unittest.TestCase):
    def test_session_boundary_and_sliding_expiration(self):
        limiter = security.RequestLimiter()
        self.assertTrue(all(limiter.check("a", "192.0.2.1", now=10) == 0 for _ in range(120)))
        self.assertEqual(limiter.check("a", "192.0.2.1", now=10), 60)
        self.assertEqual(limiter.check("a", "192.0.2.1", now=69.5), 1)
        self.assertEqual(limiter.check("a", "192.0.2.1", now=70), 0)

    def test_ip_limit_survives_new_sessions_without_affecting_other_ips(self):
        limiter = security.RequestLimiter()
        for index in range(300):
            self.assertEqual(limiter.check(str(index), "192.0.2.1", now=10), 0)
        self.assertEqual(limiter.check("another", "192.0.2.1", now=10), 60)
        self.assertEqual(limiter.check("another", "192.0.2.2", now=10), 0)

    def test_stale_sessions_and_ips_are_removed_without_unbounded_rejected_entries(self):
        limiter = security.RequestLimiter()
        for index in range(300):
            limiter.check(str(index), "192.0.2.1", now=10)
        for index in range(300, 1000):
            limiter.check(str(index), "192.0.2.1", now=11)
        self.assertEqual(len(limiter.sessions), 300)
        limiter.check("fresh", "192.0.2.2", now=71)
        self.assertEqual(set(limiter.sessions), {"fresh"})
        self.assertEqual(set(limiter.ips), {"192.0.2.2"})

    def test_parallel_requests_cannot_exceed_ip_budget(self):
        limiter = security.RequestLimiter()
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda i: limiter.check(str(i), "192.0.2.1", now=1), range(450)))
        self.assertEqual(results.count(0), 300)

    def test_missing_ip_does_not_merge_unrelated_sessions(self):
        limiter = security.RequestLimiter()
        for _ in range(120):
            limiter.check("one", None, now=1)
        self.assertEqual(limiter.check("one", None, now=1), 60)
        self.assertEqual(limiter.check("two", None, now=1), 0)
        self.assertFalse(limiter.ips)


async def exchange(app, scope, incoming):
    events = iter(incoming)
    messages = []

    async def receive():
        return next(events)

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    return messages


def http_scope(agent=BROWSER, path="/"):
    return {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
            "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
            "root_path": "", "headers": [(b"user-agent", agent.encode())],
            "client": ("192.0.2.1", 23456), "server": ("localhost", 80)}


class ASGITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"CHACHACHA_ALLOW_BOTS": "0"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    async def test_robots_route_headers_and_bot_403(self):
        app = SecurityMiddleware(Starlette(routes=[Route("/robots.txt", robots_txt), Route("/", robots_txt)]))
        for agent in (BROWSER, "GPTBot/1", "curl/8", "HeadlessChrome", ""):
            messages = await exchange(app, http_scope(agent, "/robots.txt"), [{"type": "http.request"}])
            self.assertEqual(messages[0]["status"], 200)
            headers = dict(messages[0]["headers"])
            for name, value in SECURITY_HEADERS.items():
                self.assertEqual(headers[name], value)
            self.assertEqual(messages[1]["body"], b"User-agent: *\nDisallow: /\n")
        for agent in ("GPTBot/1", "curl/8", "HeadlessChrome", ""):
            for path in ("/", "/roads", "/robots.txt/", "/robots.txt/private"):
                messages = await exchange(app, http_scope(agent, path), [{"type": "http.request"}])
                self.assertEqual(messages[0]["status"], 403)
                headers = dict(messages[0]["headers"])
                for name, value in SECURITY_HEADERS.items():
                    self.assertEqual(headers[name], value)
        head_scope = {**http_scope("GPTBot/1", "/robots.txt"), "method": "HEAD"}
        messages = await exchange(app, head_scope, [{"type": "http.request"}])
        self.assertEqual(messages[0]["status"], 200)
        with patch.dict(os.environ, {"CHACHACHA_ALLOW_BOTS": "1"}):
            messages = await exchange(app, http_scope("curl", "/"), [{"type": "http.request"}])
            self.assertEqual(messages[0]["status"], 200)

    async def test_websocket_payload_subprotocol_and_lifespan_pass_through(self):
        async def downstream(scope, receive, send):
            if scope["type"] == "lifespan":
                self.assertEqual((await receive())["type"], "lifespan.startup")
                await send({"type": "lifespan.startup.complete"})
            else:
                self.assertEqual(scope["path"], "/_stcore/stream")
                self.assertEqual((await receive())["type"], "websocket.connect")
                await send({"type": "websocket.accept", "subprotocol": "streamlit"})
                payload = await receive()
                await send({"type": "websocket.send", "bytes": payload["bytes"]})

        app = SecurityMiddleware(downstream)
        scope = {**http_scope(path="/_stcore/stream"), "type": "websocket"}
        events = await exchange(app, scope, [{"type": "websocket.connect"},
                                            {"type": "websocket.receive", "bytes": b"streamlit-message"}])
        self.assertEqual(events, [{"type": "websocket.accept", "subprotocol": "streamlit"},
                                  {"type": "websocket.send", "bytes": b"streamlit-message"}])
        scope["headers"] = [(b"user-agent", b"HeadlessChrome")]
        self.assertEqual(await exchange(app, scope, []), [{"type": "websocket.close", "code": 1008}])
        scope["path"] = "/robots.txt"
        self.assertEqual(await exchange(app, scope, []), [{"type": "websocket.close", "code": 1008}])
        self.assertEqual(await exchange(app, {"type": "lifespan"}, [{"type": "lifespan.startup"}]),
                         [{"type": "lifespan.startup.complete"}])

    async def test_security_headers_replace_unsafe_values_without_dropping_cookies(self):
        async def downstream(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": [
                (b"X-Frame-Options", b"SAMEORIGIN"), (b"set-cookie", b"a=1"), (b"set-cookie", b"b=2")]})
        events = await exchange(SecurityMiddleware(downstream), http_scope(), [])
        headers = events[0]["headers"]
        self.assertEqual([value for name, value in headers if name == b"set-cookie"], [b"a=1", b"b=2"])
        self.assertEqual([value for name, value in headers if name.lower() == b"x-frame-options"], [b"DENY"])

    def test_streamlit_run_detects_wrapper_without_starting_a_server(self):
        with patch("streamlit.web.bootstrap.run_asgi_app") as launch:
            result = CliRunner().invoke(streamlit_cli, ["run", str(ROOT / "asgi_app.py"), "--server.headless=true"])
        self.assertEqual(result.exit_code, 0, result.output)
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[1], "asgi_app:app")


class PrePushTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, body):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def index(self, paths, version=2):
        entries, previous = b"", b""
        for path in paths:
            name = path.encode()
            fixed = b"\0" * 60 + struct.pack("!H", len(name))
            if version == 4:
                shared = 0
                while shared < min(len(previous), len(name)) and previous[shared] == name[shared]:
                    shared += 1
                record = fixed + bytes([len(previous) - shared]) + name[shared:] + b"\0"
            else:
                record = fixed + name + b"\0"
                record += b"\0" * (-len(record) % 8)
            entries += record
            previous = name
        payload = struct.pack("!4sII", b"DIRC", version, len(paths)) + entries
        (self.root / ".git").mkdir(exist_ok=True)
        (self.root / ".git/index").write_bytes(payload + hashlib.sha1(payload).digest())

    def test_nested_ignore_negation_glob_and_excluded_parent(self):
        self.write(".gitignore", "work/\n*.csv\n!keep.csv\ndata/raw/**\n!data/raw/.gitkeep\ncache/\n!cache/keep.txt\n")
        for name in ("work/file.py", "deep/a.csv", "keep.csv", "data/raw/.gitkeep",
                     "data/raw/private.json", "cache/keep.txt", "app.py", "deep/note.txt"):
            self.write(name, "safe")
        self.write("deep/.gitignore", "note.txt\n")
        files = worktree_files(self.root)
        self.assertIn("keep.csv", files)
        self.assertIn("data/raw/.gitkeep", files)
        for name in ("work/file.py", "deep/a.csv", "cache/keep.txt", "deep/note.txt", "data/raw/private.json"):
            self.assertNotIn(name, files)

    def test_tracked_ignored_files_are_checked_in_all_supported_indexes(self):
        paths = [".env", "work/private.txt", "data/processed/registrations.csv"]
        self.write(".gitignore", ".env\nwork/\ndata/processed/**/*.csv\n")
        for path in paths:
            self.write(path, "fixture")
        for version in (2, 3, 4):
            self.index(paths, version)
            self.assertEqual(tracked_files(self.root), set(paths))
            self.assertEqual({finding.path for finding in scan(self.root)}, set(paths))

    def test_forbidden_paths_and_symlinks_fail_without_reading_target(self):
        for name in (".env", "a/secrets.toml", "data/raw/a.json", "data/processed/deep/a.csv",
                     "dump.sql.gz", "work/note.txt", "prototypes/app.py", ".venv/config"):
            self.write(name, "fixture")
        (self.root / "linked.txt").symlink_to(ROOT / ".streamlit/secrets.toml")
        self.assertEqual(len(scan(self.root)), 9)

    def test_detects_keys_literals_and_copied_private_values_without_printing_values(self):
        api_value = "sk-" + "ant-" + "aB3_" * 15
        data_value = "9a7b6c5d" * 8
        password_value = "fixture-" + "secret-" + "12345"
        self.write(".gitignore", ".streamlit/secrets.toml\n")
        self.write(".streamlit/secrets.toml", f'[mysql]\npassword = "{password_value}"\n')
        self.write("leaked.txt", f'{api_value}\n{data_value}\npassword="{password_value}"\n')
        self.write("copied.md", f"A copy: {password_value}\n")
        output = StringIO()
        with redirect_stdout(output):
            status = main(["--root", str(self.root)])
        self.assertEqual(status, 1)
        self.assertIn("leaked.txt:1", output.getvalue())
        self.assertIn("leaked.txt:2", output.getvalue())
        self.assertIn("leaked.txt:3", output.getvalue())
        self.assertIn("copied.md:1", output.getvalue())
        for value in (api_value, data_value, password_value):
            self.assertNotIn(value, output.getvalue())

    def test_safe_examples_environment_references_checksums_and_numeric_substrings(self):
        source = 'password = ""\napi_key = os.environ["API_KEY"]\npassword = "YOUR_PASSWORD"\n'
        self.assertEqual(content_findings("sample.py", source, set()), [])
        checksum = hashlib.sha256(b"fixture").hexdigest()
        self.assertEqual(content_findings("manifest.json", '{"sha256":{"a.csv":"' + checksum + '"}}', set()), [])
        self.assertEqual(content_findings("coordinates.py", "value = 37.123456789", {"4567"}), [])
        self.assertEqual(content_findings("code.py", "secret = {}", set()), [])
        self.assertEqual(content_findings("code.py", "engine.url.password == token", set()), [])
        self.write("app.py", source)
        self.assertEqual(scan(self.root), [])

    def test_example_markers_and_short_values_pass_but_long_literals_are_reviewed(self):
        examples = [f"prefix-{marker.upper()}-credential-value" for marker in
                    ("fake", "fixture", "dummy", "omit", "example", "test", "changeme")]
        examples += ["omit", "fake-credential", "fixture-credential", "Q7m" * 5]
        self.write("examples.py", "\n".join(f'api_key = "{value}"' for value in examples))
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--root", str(self.root)]), 0)
        self.assertIn("통과", output.getvalue())
        long_value = "Q7m" * 5 + "p"
        findings = content_findings("candidate.txt", f'password="{long_value}"', set())
        self.assertEqual([(item.line, item.reason) for item in findings], [(1, "비밀값 직접 지정")])

    def test_key_shapes_are_detected_even_when_they_contain_example_markers(self):
        shaped_value = "sk-" + "ant-" + "fixture-" + "Ab9_" * 12
        data_value = "a7B4" * 22
        self.write("candidates.txt", f'api_key="{shaped_value}"\n{data_value}\n')
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--root", str(self.root)]), 1)
        self.assertIn("candidates.txt:1 [API 키 패턴]", output.getvalue())
        self.assertIn("candidates.txt:2 [긴 API 키 후보]", output.getvalue())
        for value in (shaped_value, data_value):
            self.assertNotIn(value, output.getvalue())

    def test_ignored_local_files_pass_but_copied_short_local_secret_fails(self):
        short_value = "k9P" + "2s7X"
        self.write(".gitignore", ".env\n.streamlit/secrets.toml\ndata/raw/\nwork/\nprototypes/\n")
        self.write(".streamlit/secrets.toml", f'[mysql]\npassword="{short_value}"\n')
        for path in (".env", "data/raw/input.json", "work/note.txt", "prototypes/app.py"):
            self.write(path, short_value)
        self.write("app.py", "print('차차차')\n")
        self.assertEqual(scan(self.root), [])
        self.write("copied.txt", short_value)
        findings = scan(self.root)
        self.assertEqual([(item.path, item.line, item.reason) for item in findings],
                         [("copied.txt", 1, "로컬 비밀값과 일치")])

    def test_pass_reports_ignored_forbidden_files_without_values(self):
        value = "k9P" + "2s7X-local"
        self.write(".gitignore", ".env\nwork/\n")
        self.write(".env", value)
        self.write("work/note.txt", value)
        self.write("app.py", "print('차차차')\n")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--root", str(self.root)]), 0)
        self.assertIn("2개 (.env, work)", output.getvalue())
        self.assertIn("git으로만", output.getvalue())
        self.assertNotIn(value, output.getvalue())

    def test_deterrent_uses_physical_keys_for_macos_option_shortcuts(self):
        for token in ("event.code", "event.altKey", "'KeyI'"):
            self.assertIn(token, security.DETERRENT_SCRIPT)

    def test_broken_index_fails_closed(self):
        self.index(["app.py"])
        (self.root / ".git/index").write_bytes(b"broken")
        self.assertTrue(scan(self.root))


class NavigationSecurityTests(unittest.TestCase):
    def test_all_pages_in_nav_and_footer_and_new_headers_without_database(self):
        expected = {"", "ownership", "parking", "charging", "transit", "roads", "compare",
                    "national", "faq", "ask", "about"}
        with patch.dict(os.environ, {"CHACHACHA_ALLOW_BOTS": "1"}), \
                patch("ui.load_options", return_value={}), \
                patch("db.queries.get_filter_options", return_value={}):
            app = AppTest.from_file(ROOT / "app.py").run()
            self.assertFalse(app.exception)
            menu = [link.proto.page for link in app.get_by_key("site_menu").page_link]
            more = [link.proto.page for link in app.get_by_key("site_more_links").page_link]
            footer = [link.proto.page for link in app.get_by_key("footer_menu").page_link]
            self.assertEqual(set(menu), expected)
            self.assertEqual([path for path in menu if path not in more],
                             ["", "ownership", "parking", "transit"])
            self.assertEqual(more, ["charging", "roads", "compare", "national", "faq", "ask", "about"])
            self.assertEqual(len(more), 7)
            self.assertEqual(len(footer), 11)
            self.assertEqual(set(footer), expected)
            self.assertTrue(any("noindex" in element.proto.body for element in app.get("html")))
            for path in ("charging", "roads", "about"):
                app.switch_page(f"app_pages/{path}.py").run()
                self.assertFalse(app.exception)
                self.assertEqual(len(app.get_by_key("site_page_header").title), 1)

    def test_footer_has_no_sources(self):
        app = AppTest.from_string("from site_shell import footer\nfooter([])\n").run()
        self.assertFalse(app.exception, [item.message for item in app.exception])
        app.get_by_key("site_footer")
        with self.assertRaises(KeyError):
            app.get_by_key("footer_sources")


if __name__ == "__main__":
    unittest.main()
