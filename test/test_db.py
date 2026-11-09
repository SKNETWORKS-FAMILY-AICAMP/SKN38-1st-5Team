import builtins
from concurrent.futures import ThreadPoolExecutor
import os
import time
import unittest
from unittest.mock import patch

import streamlit
from streamlit.errors import StreamlitSecretNotFoundError

from db.connection import _clear_engine_cache, get_engine


class ConnectionTest(unittest.TestCase):
    def setUp(self):
        _clear_engine_cache()

    def tearDown(self):
        _clear_engine_cache()

    def test_concurrent_first_calls_share_one_engine(self):
        sentinel = object()

        def create(*args, **kwargs):
            time.sleep(0.02)
            return sentinel

        with patch.object(streamlit, "secrets", {"mysql": {"host": "localhost"}}), patch(
            "db.connection.create_engine", side_effect=create
        ) as factory, ThreadPoolExecutor(max_workers=8) as executor:
            engines = list(executor.map(lambda _: get_engine(), range(8)))
        self.assertEqual(factory.call_count, 1)
        self.assertTrue(all(engine is sentinel for engine in engines))

    def test_secret_priority(self):
        token = os.urandom(16).hex() + "@:/?#%"
        with patch.dict(os.environ, {"MYSQL_HOST": "env-host", "MYSQL_DATABASE": "env_db"}), patch.object(
            streamlit, "secrets", {"mysql": {"host": "secret-host", "password": token}}
        ):
            engine = get_engine()
        try:
            self.assertEqual(engine.url.host, "secret-host")
            self.assertEqual(engine.url.database, "env_db")
            self.assertTrue(engine.url.password == token, "특수문자를 포함한 값의 전달 실패")
            self.assertTrue(engine.hide_parameters)
            self.assertFalse(engine.echo)
        finally:
            engine.dispose()

    def test_environment_without_streamlit(self):
        original_import = builtins.__import__

        def import_without_streamlit(name, *args, **kwargs):
            if name == "streamlit":
                raise ModuleNotFoundError("optional dependency", name="streamlit")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_without_streamlit), patch.dict(
            os.environ, {"MYSQL_HOST": "127.0.0.1", "MYSQL_PORT": "3307", "MYSQL_DATABASE": "sample"}
        ):
            engine = get_engine()
        try:
            self.assertEqual(engine.url.host, "127.0.0.1")
            self.assertEqual(engine.url.port, 3307)
            self.assertEqual(engine.url.database, "sample")
        finally:
            engine.dispose()

    def test_invalid_port_has_safe_error(self):
        with patch.object(streamlit, "secrets", {}), patch.dict(os.environ, {"MYSQL_PORT": "invalid"}):
            with self.assertRaisesRegex(ValueError, "자료형과 포트 범위"):
                get_engine()

    def test_malformed_secret_does_not_fall_back(self):
        class InvalidSecret:
            def __getitem__(self, key):
                raise StreamlitSecretNotFoundError("Error parsing secrets file: invalid syntax")

        with patch.object(streamlit, "secrets", InvalidSecret()):
            with self.assertRaisesRegex(RuntimeError, "비밀 설정 파일의 형식"):
                get_engine()

    def test_missing_secret_uses_environment(self):
        class MissingSecret:
            def __getitem__(self, key):
                raise StreamlitSecretNotFoundError("No secrets found. Valid paths are unavailable")

        with patch.object(streamlit, "secrets", MissingSecret()), patch.dict(os.environ, {"MYSQL_DATABASE": "fallback_db"}):
            engine = get_engine()
        try:
            self.assertEqual(engine.url.database, "fallback_db")
        finally:
            engine.dispose()

    def test_port_does_not_accept_fraction_or_boolean(self):
        for value in (3306.5, True):
            with patch.object(streamlit, "secrets", {"mysql": {"port": value}}):
                with self.assertRaises(ValueError):
                    get_engine()
