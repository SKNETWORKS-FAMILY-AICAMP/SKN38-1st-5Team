# 예외 데이터는 원본 DB를 바꾸지 않도록 SELECT CTE로 주입한다.

from contextlib import contextmanager
import re
from unittest.mock import patch

import pandas as pd
from sqlalchemy import text

from db import queries
from db.connection import get_engine


def clear_query_cache():
    for name in dir(queries):
        value = getattr(queries, name)
        if name.startswith(("get_", "search_")) and hasattr(value, "clear"):
            value.clear()


def points_and_coverage(region_id=None, **kwargs):
    points = queries.get_place_points(region_id, **kwargs)
    return points, pd.DataFrame(points.attrs["coverage"], columns=pd.Index([
        "kind", "total_count", "point_count", "excluded_count", "invalid_coordinate_count", "identifier_conflict_count"]))


@contextmanager
def query_overlay(changes=None, *, excluded_sources=(), source=None, params=None):
    changes = dict(changes or {})
    bound = dict(params or {})
    if excluded_sources:
        if "source_snapshot" in changes:
            raise ValueError("수집본 변경과 제외 목록을 동시에 지정할 수 없습니다.")
        excluded = []
        for index, code in enumerate(excluded_sources):
            key = "fixture_source_" + str(index)
            excluded.append(":" + key)
            bound[key] = code
        changes["source_snapshot"] = {"columns": {
            "is_complete": "CASE WHEN source_code IN (" + ",".join(excluded) + ") THEN 0 ELSE is_complete END"}}
    ctes = []
    engine = get_engine()
    if engine.url.database != "chachacha":
        raise ValueError("로컬 chachacha 조회용 검사입니다.")
    with engine.connect() as conn:
        for table, change in changes.items():
            if not re.fullmatch(r"[a-z_]+", table):
                raise ValueError("검사 테이블 이름 오류")
            columns = conn.execute(text("SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:table ORDER BY ORDINAL_POSITION"), {"table": table}).scalars().all()
            if not columns or not set(change.get("columns", {})).issubset(columns):
                raise ValueError("검사 컬럼 이름 오류")
            expressions = [change.get("columns", {}).get(column, "`" + column + "`") + " AS `" + column + "`" for column in columns]
            ctes.append("`" + table + "` AS (SELECT " + ", ".join(expressions) + " FROM chachacha.`" + table + "` WHERE " + change.get("where", "1=1") + ")")
    original = queries._read_query

    def read(sql, params=None, **kwargs):
        if ctes:
            sql = sql.lstrip()
            sql = "WITH " + ", ".join(ctes) + (", " + sql[5:] if sql.upper().startswith("WITH ") else " " + sql)
        return original(sql, {**(params or {}), **bound}, **kwargs)

    clear_query_cache()
    try:
        with patch.object(queries, "_read_query", side_effect=read), patch.object(queries, "DEFAULT_CHARGER_SOURCE", source or queries.DEFAULT_CHARGER_SOURCE):
            yield
    finally:
        clear_query_cache()
