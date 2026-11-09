"""기본은 로컬 개발 DB에, --allow-remote 지정 시 설정된 DB에 DDL을 적용한다."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from sqlalchemy import inspect, text

from db.connection import get_connection_config, get_engine, is_local_config

ROOT = Path(__file__).resolve().parents[1]


CORE_TABLE = {"source_snapshot", "region", "vehicle_type", "fuel_scope", "company", "registration",
              "province_registration", "region_context", "parking_site", "charging_station", "charger", "faq"}
EXT_TABLE = {"traffic_coverage", "traffic_snapshot", "transit_coverage", "transit_ridership_snapshot", "weather_snapshot"}
BOUNDARY_TABLE = {"region_boundary"}


def split_statement(source: str) -> list[str]:
    result, buffer, quote, comment = [], [], None, None
    index, depth = 0, 0
    while index < len(source):
        char = source[index]
        pair = source[index:index + 2]
        if comment == "line":
            if char == "\n":
                comment = None
                buffer.append("\n")
        elif comment == "block":
            if pair == "*/":
                comment = None
                index += 1
        elif quote:
            buffer.append(char)
            if char == "\\" and index + 1 < len(source):
                index += 1
                buffer.append(source[index])
            elif char == quote:
                if index + 1 < len(source) and source[index + 1] == quote:
                    index += 1
                    buffer.append(source[index])
                else:
                    quote = None
        elif pair == "/*":
            if source[index:index + 3] == "/*!":
                raise ValueError("실행형 MySQL 주석은 초기화 입력으로 지원하지 않습니다.")
            comment = "block"
            index += 1
            buffer.append(" ")
        elif char == "#" or (pair == "--" and (index + 2 == len(source) or source[index + 2].isspace())):
            comment = "line"
            if pair == "--":
                index += 1
            buffer.append(" ")
        elif char in ("'", '"', '`'):
            quote = char
            buffer.append(char)
        elif char == ";":
            if depth:
                raise ValueError("DDL 괄호가 닫히기 전에 구문이 끝났습니다.")
            if "".join(buffer).strip():
                result.append("".join(buffer).strip())
            buffer = []
        else:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    raise ValueError("DDL 괄호의 순서가 올바르지 않습니다.")
            buffer.append(char)
        index += 1
    if quote or comment == "block" or depth:
        raise ValueError("DDL 문자열·주석·괄호가 끝나지 않았습니다.")
    if "".join(buffer).strip():
        result.append("".join(buffer).strip())
    return result


def validate_schema(statement_by_path):
    for path, statements in statement_by_path.items():
        expected = {"schema_core.sql": CORE_TABLE, "schema_active_ext.sql": EXT_TABLE,
                    "schema_boundary.sql": BOUNDARY_TABLE}[path.name]
        names = []
        for statement in statements:
            match = re.match(r"CREATE\s+TABLE\s+`?([a-z_]+)`?\s*\(", statement, re.IGNORECASE)
            if match:
                names.append(match.group(1).lower())
        if set(names) != expected or len(names) != len(expected):
            raise ValueError(f"{path.name}의 {len(expected)}표 정의가 비어 있거나 누락·중복되었습니다.")


def apply_schema(engine, reset: bool = False, with_ext: bool = False,
                 allow_remote: bool = False, report_dir: Path | None = None) -> dict:
    if allow_remote:
        config = get_connection_config(require_database=True)
        if engine.url.database != config["database"] or engine.url.host != config["host"]:
            raise ValueError("스키마 대상 host·database가 secrets/env의 접속 설정과 다릅니다.")
    elif engine.url.database != "chachacha" or not is_local_config(engine.url):
        raise ValueError("로컬 chachacha 개발 DB에서만 스키마 적용을 허용합니다.")
    sources = [ROOT / "db/sql/schema_core.sql"]
    if with_ext:
        sources.extend([ROOT / "db/sql/schema_active_ext.sql", ROOT / "db/sql/schema_boundary.sql"])
    # 입력 파일 오류로 기존 DB만 삭제되는 일을 막기 위해 먼저 읽고 검사한다.
    content = {path: path.read_bytes() for path in sources}
    statement_by_path = {path: split_statement(value.decode("utf-8")) for path, value in content.items()}
    validate_schema(statement_by_path)
    output_dir = Path(report_dir) if report_dir is not None else Path(os.getenv("DB_REPORT_DIR", ROOT / "docs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"스키마 적용 대상: host={engine.url.host!r}, database={engine.url.database!r}", flush=True)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        current = inspect(conn)
        table = current.get_table_names()
        view = current.get_view_names()
        if (table or view) and not reset:
            raise ValueError("기존 테이블이 있습니다. DB 초기화는 --reset을 지정하세요.")
        quote = conn.dialect.identifier_preparer.quote
        # 접속한 DB를 유지하기 위해 SQL 파일의 DB 선택 지시문은 건너뛴다.
        conn.exec_driver_sql("ALTER DATABASE " + quote(engine.url.database) + " CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        try:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for name in view:
                conn.exec_driver_sql("DROP VIEW " + quote(name))
            for name in reversed(table):
                conn.exec_driver_sql("DROP TABLE " + quote(name))
        finally:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.execute(text("SET default_storage_engine = 'InnoDB'"))
        count = 0
        for path in sources:
            for statement in statement_by_path[path]:
                if re.match(r"(?:CREATE\s+DATABASE|ALTER\s+DATABASE|USE)\s", statement, re.IGNORECASE):
                    continue
                conn.exec_driver_sql(statement)
                count += 1
            if path.name == "schema_core.sql" and len(inspect(conn).get_table_names()) != len(CORE_TABLE):
                raise ValueError(f"3차 핵심 정본의 {len(CORE_TABLE)}테이블과 적용 결과가 다릅니다.")
        result = {"statement_count": count, "table_count": len(inspect(conn).get_table_names()),
                  "view_count": len(inspect(conn).get_view_names()),
                  "server_version": conn.execute(text("SELECT VERSION()")).scalar_one(),
                  "schema_version": "ERD 3차", "core_table_count": len(CORE_TABLE),
                  "extension_table_count": len(EXT_TABLE) if with_ext else 0,
                  "boundary_table_count": len(BOUNDARY_TABLE) if with_ext else 0,
                  "source_sha256": {p.name: hashlib.sha256(content[p]).hexdigest() for p in sources}}
    (output_dir / "schema_apply.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--with-ext", action="store_true", help=f"시간 {len(EXT_TABLE)}표·구 경계 {len(BOUNDARY_TABLE)}표와 충전 상세 열 적용")
    parser.add_argument("--allow-remote", action="store_true", help="secrets/env에 명시한 host·database와 같은 대상에만 적용 허용")
    parser.add_argument("--report-dir", type=Path, help="검사 결과 위치. 기본 DB_REPORT_DIR 또는 docs")
    args = parser.parse_args()
    engine = None
    try:
        engine = get_engine()
        result = apply_schema(engine, args.reset, args.with_ext, args.allow_remote, args.report_dir)
        print("DDL 적용 완료:", result["table_count"], "테이블,", result["view_count"], "뷰")
        return 0
    except Exception as exc:
        print("DDL 적용 실패:", type(exc).__name__, "접속 설정과 DDL 정의를 확인하세요.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
