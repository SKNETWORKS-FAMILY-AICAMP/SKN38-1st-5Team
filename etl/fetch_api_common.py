from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import unquote_to_bytes
from xml.etree import ElementTree

PROJECT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
LEDGER = PROJECT / "data/.api_request_budget.sqlite3"


class FetchError(Exception):
    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def text_value(value):
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise FetchError("응답 필드의 자료형이 올바르지 않습니다.")
    return str(value).strip()


def decimal_value(value, *, nonnegative=False):
    value = text_value(value)
    if not value:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise FetchError("응답의 숫자 형식이 올바르지 않습니다.") from None
    if not number.is_finite() or (nonnegative and number < 0):
        raise FetchError("응답의 숫자 범위가 올바르지 않습니다.")
    return format(number, "f")


def integer_value(value, *, minimum=0):
    value = text_value(value)
    if not re.fullmatch(r"[0-9]+", value) or int(value) < minimum:
        raise FetchError("응답의 건수 또는 페이지 번호가 올바르지 않습니다.")
    return int(value)


def check_result(code):
    code = text_value(code)
    if code in {"00", "0", "03"}:
        return code
    safe_code = code if re.fullmatch(r"[0-9]{1,3}", code) else "미확인"
    raise FetchError(
        f"API 응답 오류(코드 {safe_code}).", retryable=code in {"01", "02", "99"}
    )


@dataclass
class Page:
    item: list
    total_count: int
    page_no: int
    page_size: int
    result_code: str


def parse_page(payload):
    if not isinstance(payload, dict):
        raise FetchError("응답 JSON 구조가 올바르지 않습니다.")
    root = payload.get("response", payload)
    if not isinstance(root, dict):
        raise FetchError("응답 JSON 구조가 올바르지 않습니다.")
    header = root.get("header", root)
    if not isinstance(header, dict):
        raise FetchError("응답 헤더가 올바르지 않습니다.")
    code = check_result(header.get("resultCode"))
    if code == "03":
        return Page([], 0, 1, 1, code)
    body = root.get("body", root)
    if not isinstance(body, dict):
        raise FetchError("응답 본문이 올바르지 않습니다.")
    total = integer_value(body.get("totalCount", header.get("totalCount")))
    page_no = integer_value(body.get("pageNo", header.get("pageNo")), minimum=1)
    page_size = integer_value(body.get("numOfRows", header.get("numOfRows")), minimum=1)
    item = body.get("items")
    if isinstance(item, dict):
        item = item.get("item")
    if item is None or item == "":
        item = []
    elif isinstance(item, dict):
        item = [item]
    if not isinstance(item, list) or any(not isinstance(row, dict) for row in item):
        raise FetchError("응답 목록 구조가 올바르지 않습니다.")
    if len(item) > total or len(item) > page_size:
        raise FetchError("응답 목록 건수와 전체 건수가 다릅니다.")
    return Page(item, total, page_no, page_size, code)


class RequestBudget:
    def __init__(self, service, limit, *, used_today=0, path=LEDGER):
        self.service, self.limit, self.used_today = service, limit, used_today
        self.baseline_day = datetime.now(KST).date().isoformat()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS request_budget ("
                       "service TEXT, day TEXT, used INTEGER NOT NULL, "
                       "last_started REAL NOT NULL, PRIMARY KEY(service, day))")
            # 한도 때문에 첫 요청이 거부되더라도 외부 사용량은 다음 실행에 남긴다.
            db.execute("INSERT INTO request_budget VALUES (?, ?, ?, 0) "
                       "ON CONFLICT(service, day) DO UPDATE SET "
                       "used=MAX(request_budget.used, excluded.used)",
                       (self.service, self.baseline_day, self.used_today))

    def _current(self, db):
        day = datetime.now(KST).date().isoformat()
        row = db.execute("SELECT used FROM request_budget WHERE service=? AND day=?",
                         (self.service, day)).fetchone()
        baseline = self.used_today if day == self.baseline_day else 0
        return day, max(row[0] if row else 0, baseline)

    def require(self, count):
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            _, used = self._current(db)
        if used + count > self.limit:
            raise FetchError("남은 일일 호출 한도로 전체 수집과 재시도를 마칠 수 없습니다.")

    def claim(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            _, used = self._current(db)
            if used >= self.limit:
                raise FetchError("일일 호출 한도에 도달했습니다.")
            last = db.execute("SELECT MAX(last_started) FROM request_budget WHERE service=?",
                              (self.service,)).fetchone()[0]
            delay = max(0.0, (last or 0) + 1.0 - time.time())
            if delay:
                time.sleep(delay)
            day, used = self._current(db)
            if used >= self.limit:
                raise FetchError("일일 호출 한도에 도달했습니다.")
            db.execute("INSERT INTO request_budget VALUES (?, ?, ?, ?) "
                       "ON CONFLICT(service, day) DO UPDATE SET "
                       "used=excluded.used, last_started=excluded.last_started",
                       (self.service, day, used + 1, time.time()))


class ApiClient:
    def __init__(self, api_key, budget, *, retries=3, session=None):
        # API를 호출하지 않는 실행에서는 requests가 필요하지 않다.
        import requests

        self.requests = requests
        self.session = session if session is not None else requests.Session()
        self.api_key, self.budget, self.retries = api_key, budget, retries
        self.request_count, self.http_status, self.result_code = 0, None, None

    def get_page(self, endpoint, params):
        for attempt in range(self.retries + 1):
            self.budget.claim()
            self.request_count += 1
            try:
                response = self.session.get(
                    endpoint, params={**params, "serviceKey": self.api_key},
                    timeout=(10, 60), allow_redirects=False,
                )
                self.http_status = response.status_code
                if response.status_code != 200:
                    raise FetchError(
                        f"HTTP 요청 실패(상태 {response.status_code}).",
                        retryable=response.status_code == 429 or response.status_code >= 500,
                    )
                try:
                    payload = response.json()
                except ValueError:
                    # 포털 게이트웨이는 JSON 요청에도 XML 인증 오류를 반환할 수 있다.
                    try:
                        root = ElementTree.fromstring(response.content)
                        code = root.findtext(".//returnReasonCode") or root.findtext(".//resultCode")
                    except ElementTree.ParseError:
                        code = None
                    if code:
                        check_result(code)
                    raise FetchError("JSON 응답을 읽을 수 없습니다.") from None
                page = parse_page(payload)
                self.result_code = page.result_code
                return page
            except self.requests.RequestException:
                error = FetchError("네트워크 요청에 실패했습니다.", retryable=True)
            except FetchError as exc:
                error = exc
            finally:
                if "response" in locals():
                    response.close()
                    del response
            if not error.retryable or attempt == self.retries:
                raise error from None
        raise FetchError("수집을 마치지 못했습니다.")


def collect_page(client, endpoint, params, *, smoke=False):
    first = client.get_page(endpoint, {**params, "pageNo": 1})
    if first.total_count == 0:
        raise FetchError("조회 결과가 없습니다. 기존 CSV는 유지합니다.")
    if first.page_no != 1 or len(first.item) != min(first.page_size, first.total_count):
        raise FetchError("첫 페이지의 번호 또는 건수가 일치하지 않습니다.")
    page_count = math.ceil(first.total_count / first.page_size)
    if page_count > 9999:
        raise FetchError("페이지가 너무 많습니다. 조회 기간을 나누어 실행하세요.")
    if smoke:
        return first.item, first.total_count, page_count
    client.budget.require((page_count - 1) * (client.retries + 1))
    result = list(first.item)
    for number in range(2, page_count + 1):
        page = client.get_page(endpoint, {**params, "numOfRows": first.page_size, "pageNo": number})
        expected = min(first.page_size, first.total_count - len(result))
        # 환경공단은 마지막 페이지 numOfRows에 요청 크기 대신 실제 잔여 건수를 반환한다.
        if (page.total_count != first.total_count or page.page_no != number
                or page.page_size not in {first.page_size, expected} or len(page.item) != expected):
            raise FetchError("수집 중 페이지 건수 또는 totalCount가 바뀌었습니다. 다시 수집하세요.")
        result.extend(page.item)
    return result, first.total_count, page_count


def positive_int(value):
    try:
        number = int(value)
        if number < 1:
            raise ValueError
        return number
    except ValueError:
        raise argparse.ArgumentTypeError("1 이상의 정수를 입력하세요.") from None


def add_common_argument(parser, *, output, daily_limit):
    parser.add_argument("--output", type=Path, default=PROJECT / "data/processed" / output)
    parser.add_argument("--source-snapshot-id", type=positive_int,
                        help="적재 담당자가 발급한 출처 ID. 생략하면 CSV에서 빈 값")
    parser.add_argument("--daily-limit", type=positive_int, default=daily_limit,
                        help="서비스의 하루 한도 이하로 설정")
    parser.add_argument("--used-today", type=int, default=0,
                        help="포털에서 확인한 오늘 총 사용량. 로컬 누적보다 클 때 반영")
    parser.add_argument("--smoke", action="store_true", help="재시도 없이 1회 조회, CSV 저장 안 함")


def validate_budget(args, maximum):
    # 포털 사용량이 설정 한도를 넘어도 누적 기록에 반영한 뒤 요청을 차단한다.
    if args.used_today < 0 or not 1 <= args.daily_limit <= maximum:
        raise FetchError("호출 한도 또는 오늘 사용량 범위를 확인하세요.")
    if args.source_snapshot_id is not None and args.source_snapshot_id > 4294967295:
        raise FetchError("출처 ID가 MySQL INT UNSIGNED 범위를 넘었습니다.")


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
            name = target.name
            target.write(content)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def save_snapshot(path, rows, columns, metadata, *, api_key):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    content = buffer.getvalue().encode("utf-8-sig")
    metadata = {**metadata, "row_count": len(rows),
                "content_sha256": hashlib.sha256(content).hexdigest()}
    manifest = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    # 응답에 인증키가 반사될 수 있어 원문과 URL 디코딩 결과를 함께 검사한다.
    secret = api_key.encode()
    if any(secret in candidate for candidate in (
            content, manifest, unquote_to_bytes(content), unquote_to_bytes(manifest))):
        raise FetchError("출력에 인증정보가 포함되어 저장을 중단했습니다.")
    atomic_write(path, content)
    atomic_write(Path(path).with_suffix(".meta.json"), manifest)


def run_cli(main):
    try:
        return main()
    except FetchError as exc:
        print(f"수집 실패: {exc}")
        return 1
    except KeyboardInterrupt:
        print("수집을 중단했습니다.")
        return 130
    except Exception:
        # requests 예외와 traceback에는 인증키가 붙은 URL이 들어갈 수 있다.
        print("수집 실패: 실행 환경 또는 파일 처리를 확인하세요. 오류 원문은 출력하지 않습니다.")
        return 1
