from contextlib import redirect_stdout
from io import StringIO
import os
import ssl
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

import streamlit
from sqlalchemy import URL
from sqlalchemy.dialects.mysql import dialect

from db.connection import _clear_engine_cache, _require_tls, get_engine
from db.init_schema import CORE_TABLE, apply_schema


class RemoteConnectionTest(unittest.TestCase):
    def setUp(self):
        _clear_engine_cache()

    def tearDown(self):
        _clear_engine_cache()

    def connection_args(self, secret, environment=None):
        _clear_engine_cache()
        with patch.dict(os.environ, environment or {}, clear=True), patch.object(streamlit, 'secrets', {'mysql': secret}), patch('db.connection.create_engine') as create, patch('db.connection.event.listen') as listen:
            get_engine()
            return create.call_args.kwargs['connect_args'], listen.call_count

    def test_remote_always_enables_tls_without_ca(self):
        args, listeners = self.connection_args({'host': 'database.example.invalid'})
        self.assertTrue(args['ssl'].check_hostname)
        self.assertEqual(args['ssl'].verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(listeners, 1)

    def test_local_default_and_explicit_ssl(self):
        for host in ('localhost', '127.0.0.1', '::1'):
            with self.subTest(host=host):
                args, listeners = self.connection_args({'host': host})
                self.assertNotIn('ssl', args)
                self.assertEqual(listeners, 0)
                args, listeners = self.connection_args({'host': host, 'ssl_ca': ''})
                self.assertTrue(args['ssl'])
                self.assertEqual(listeners, 1)

    def test_ca_file_environment_fallback_and_secret_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / 'ca.pem'
            from datetime import datetime, timedelta, timezone
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'Test CA')])
            now = datetime.now(timezone.utc)
            cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
                    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                    .sign(key, hashes.SHA256()))
            ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            original_context = ssl.create_default_context
            with patch('db.connection.ssl.create_default_context', wraps=original_context) as create_context:
                args, _ = self.connection_args({}, {'MYSQL_SSL_CA': str(ca)})
                create_context.assert_called_once_with(cafile=str(ca))
                self.assertTrue(args['ssl'].check_hostname)
                self.assertEqual(args['ssl'].verify_mode, ssl.CERT_REQUIRED)
                create_context.reset_mock()
                args, _ = self.connection_args({'ssl_ca': ''}, {'MYSQL_SSL_CA': str(ca)})
                create_context.assert_called_once_with(cafile=None)
                self.assertTrue(args['ssl'].check_hostname)
                create_context.reset_mock()
                self.connection_args({'ssl_ca': str(ca)}, {'MYSQL_SSL_CA': '/missing/env.pem'})
                create_context.assert_called_once_with(cafile=str(ca))

    def test_absent_ca_file_fails_before_opening_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'CA 인증서 파일을 찾을 수 없습니다'):
                self.connection_args({'ssl_ca': str(Path(directory) / 'missing.pem')})

    def test_invalid_ca_contents_fail_without_leaking_path(self):
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / 'private-path.pem'
            ca.write_text('not a certificate')
            with self.assertRaisesRegex(ValueError, '인증서 형식') as caught:
                self.connection_args({'ssl_ca': str(ca)})
            self.assertNotIn(str(ca), str(caught.exception))

    def test_invalid_ca_type_fails_without_value_in_error(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(streamlit, 'secrets', {'mysql': {'ssl_ca': ['invalid']}}):
            with self.assertRaisesRegex(ValueError, '자료형과 포트 범위'):
                get_engine()

    def test_tls_downgrade_is_rejected(self):
        for cipher in ('', 'TLS_AES_256_GCM_SHA384'):
            connection = MagicMock()
            connection.cursor.return_value.__enter__.return_value.fetchone.return_value = ('Ssl_cipher', cipher)
            if cipher:
                _require_tls(connection, None)
                connection.close.assert_not_called()
            else:
                with self.assertRaisesRegex(RuntimeError, 'TLS 연결'):
                    _require_tls(connection, None)
                connection.close.assert_called_once()


class RemoteSchemaTest(unittest.TestCase):
    def engine(self, host='database.example.invalid', database='configured_db'):
        engine = MagicMock()
        engine.url = URL.create('mysql+pymysql', host=host, database=database)
        return engine

    def test_default_guard_rejects_remote_and_other_local_database(self):
        for engine in (self.engine(), self.engine('localhost', 'other_db'),
                       self.engine('localhost', 'legacy_db')):
            with self.assertRaisesRegex(ValueError, '로컬 chachacha'):
                apply_schema(engine, reset=True)
            engine.connect.assert_not_called()

    def test_remote_guard_requires_explicit_database(self):
        engine = self.engine(database='chachacha')
        with patch.dict(os.environ, {}, clear=True), patch.object(streamlit, 'secrets', {'mysql': {'host': engine.url.host}}):
            with self.assertRaisesRegex(ValueError, '명시적인 DB 이름'):
                apply_schema(engine, reset=True, allow_remote=True)
        engine.connect.assert_not_called()

    def test_remote_guard_rejects_config_mismatch(self):
        for secret in ({'host': 'database.example.invalid', 'database': 'other_db'},
                       {'host': 'other.example.invalid', 'database': 'configured_db'}):
            engine = self.engine()
            with patch.dict(os.environ, {}, clear=True), patch.object(streamlit, 'secrets', {'mysql': secret}):
                with self.assertRaisesRegex(ValueError, '접속 설정과 다릅니다'):
                    apply_schema(engine, reset=True, allow_remote=True)
            engine.connect.assert_not_called()

    def test_remote_executes_only_configured_database_and_prints_before_drop(self):
        engine = self.engine(database='configured-db')
        connection = engine.connect.return_value.execution_options.return_value.__enter__.return_value
        connection.dialect = dialect()
        connection.execute.return_value.scalar_one.return_value = '8.0.mock'
        inspector = Mock()
        inspector.get_table_names.side_effect = [['old_table'], sorted(CORE_TABLE), sorted(CORE_TABLE)]
        inspector.get_view_names.return_value = []
        output = StringIO()

        def check_before_drop(statement):
            if statement.startswith('DROP'):
                self.assertIn("host='database.example.invalid', database='configured-db'", output.getvalue())

        connection.exec_driver_sql.side_effect = check_before_drop
        secret = {'host': engine.url.host, 'database': engine.url.database}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), patch.object(streamlit, 'secrets', {'mysql': secret}), patch('db.init_schema.inspect', return_value=inspector), redirect_stdout(output):
            result = apply_schema(engine, reset=True, allow_remote=True, report_dir=Path(directory))
            self.assertTrue((Path(directory) / 'schema_apply.json').is_file())
        statements = [call.args[0] for call in connection.exec_driver_sql.call_args_list]
        self.assertTrue(any(s.startswith('ALTER DATABASE `configured-db` ') for s in statements))
        self.assertFalse(any(s.startswith(('CREATE DATABASE', 'USE ', 'ALTER DATABASE chachacha')) for s in statements))
        self.assertEqual(result['table_count'], 12)

    def test_remote_still_requires_reset_for_existing_table(self):
        engine = self.engine()
        inspector = Mock()
        inspector.get_table_names.return_value = ['existing_table']
        inspector.get_view_names.return_value = []
        secret = {'host': engine.url.host, 'database': engine.url.database}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), patch.object(streamlit, 'secrets', {'mysql': secret}), patch('db.init_schema.inspect', return_value=inspector), redirect_stdout(StringIO()):
            with self.assertRaisesRegex(ValueError, '--reset'):
                apply_schema(engine, allow_remote=True, report_dir=Path(directory))
        connection = engine.connect.return_value.execution_options.return_value.__enter__.return_value
        connection.exec_driver_sql.assert_not_called()
