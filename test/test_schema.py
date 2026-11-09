from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import URL

from db.init_schema import apply_schema, split_statement, CORE_TABLE, EXT_TABLE, BOUNDARY_TABLE, ROOT


class SchemaTest(unittest.TestCase):
    def test_missing_ddl_does_not_connect_or_drop(self):
        engine = Mock()
        engine.url = URL.create("mysql+pymysql", host="localhost", database="chachacha")
        with tempfile.TemporaryDirectory() as directory, patch("db.init_schema.ROOT", Path(directory)):
            with self.assertRaises(FileNotFoundError):
                apply_schema(engine, reset=True, with_ext=True)
        engine.connect.assert_not_called()

    def test_empty_or_incomplete_ddl_stops_before_connect(self):
        core = (ROOT / "db/sql/schema_core.sql").read_text()
        extension = (ROOT / "db/sql/schema_active_ext.sql").read_text()
        for candidate_core, candidate_ext in (("", extension), (core, ""), (core.replace("CREATE TABLE faq", "CREATE TABLE missing_faq"), extension)):
            with self.subTest(), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory) / "db/sql"
                folder.mkdir(parents=True)
                (folder / "schema_core.sql").write_text(candidate_core)
                (folder / "schema_active_ext.sql").write_text(candidate_ext)
                (folder / "schema_boundary.sql").write_text((ROOT / "db/sql/schema_boundary.sql").read_text())
                engine = Mock()
                engine.url = URL.create("mysql+pymysql", host="localhost", database="chachacha")
                with patch("db.init_schema.ROOT", Path(directory)), self.assertRaises(ValueError):
                    apply_schema(engine, reset=True, with_ext=True)
                engine.connect.assert_not_called()

    def test_block_comment_cannot_restore_deferred_table(self):
        import re
        source = (ROOT / "db/sql/schema.sql").read_text()
        name = [match.group(1) for statement in split_statement(source)
                if (match := re.match(r"CREATE TABLE ([a-z_]+)", statement))]
        self.assertEqual(set(name), CORE_TABLE | EXT_TABLE | BOUNDARY_TABLE)
        self.assertEqual(len(name), len(CORE_TABLE | EXT_TABLE | BOUNDARY_TABLE))
        self.assertNotIn("parking_profile", name)

    def test_comment_and_literal_semicolon(self):
        source = "SELECT/* 주석; */'a;--b', 'c'';d'; # 설명;\nSELECT 2--1; -- 설명;\nSELECT '/*;*/';"
        self.assertEqual(split_statement(source), ["SELECT 'a;--b', 'c'';d'", "SELECT 2--1", "SELECT '/*;*/'"])

    def test_unclosed_input_is_rejected(self):
        for source in ("SELECT 'unfinished", "/* unfinished", "CREATE TABLE t (id INT", "SELECT /*! 1 */ 2"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                split_statement(source)
