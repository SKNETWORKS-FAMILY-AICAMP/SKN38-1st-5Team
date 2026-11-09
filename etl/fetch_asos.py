"""서울 108번 ASOS 시간자료를 일회성 CSV로 수집한다."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime

if __package__:
    from .fetch_api_common import (ApiClient, FetchError, KST, RequestBudget,
        add_common_argument, collect_page, decimal_value, run_cli, save_snapshot,
        text_value, validate_budget)
else:
    from fetch_api_common import (ApiClient, FetchError, KST, RequestBudget,
        add_common_argument, collect_page, decimal_value, run_cli, save_snapshot,
        text_value, validate_budget)

ENDPOINT = "https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"
SOURCE_URL = "https://www.data.go.kr/data/15057210/openapi.do"
COLUMN = ("source_snapshot_id", "observed_at", "temperature_c", "rain_mm", "snow_cm",
          "wind_speed_ms", "temperature_qc_flag", "rain_qc_flag", "wind_qc_flag")


def parse_weather(item, source_snapshot_id=None):
    result, seen = [], set()
    for source in item:
        if text_value(source.get("stnId")) != "108":
            raise FetchError("서울 108번이 아닌 관측소가 응답에 있습니다.")
        raw_time = text_value(source.get("tm"))
        observed = None
        for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H"):
            try:
                observed = datetime.strptime(raw_time, pattern)
                break
            except ValueError:
                pass
        if observed is None or observed.minute != 0:
            raise FetchError("기상 관측시각이 시간자료 형식과 다릅니다.")
        timestamp = observed.strftime("%Y-%m-%d %H:%M:%S")
        if timestamp in seen:
            raise FetchError("기상 관측시간이 중복되었습니다.")
        seen.add(timestamp)
        row = {"source_snapshot_id": source_snapshot_id, "observed_at": timestamp,
               "snow_cm": decimal_value(source.get("dsnw"), nonnegative=True)}
        for api_name, column, flag_column in (
            ("ta", "temperature_c", "temperature_qc_flag"),
            ("rn", "rain_mm", "rain_qc_flag"),
            ("ws", "wind_speed_ms", "wind_qc_flag"),
        ):
            # 공식 표는 Qcflag, 일부 응답 예시는 Qcflg 표기를 사용한다.
            flag_set = {text_value(source.get(api_name + suffix)) for suffix in ("Qcflag", "Qcflg")}
            flag_set.discard("")
            if len(flag_set) > 1:
                raise FetchError("기상 품질 플래그의 두 표기가 서로 다릅니다.")
            flag = next(iter(flag_set), "")
            if flag and not re.fullmatch(r"[0-9]", flag):
                raise FetchError("기상 품질 플래그 형식이 올바르지 않습니다.")
            row[flag_column] = flag or None
            # 빈 품질 표시는 정상 여부를 알 수 없으므로 그대로 남긴다.
            row[column] = (None if flag and flag != "0" else
                           decimal_value(source.get(api_name), nonnegative=api_name != "ta"))
        result.append(row)
    return sorted(result, key=lambda row: row["observed_at"])


def parse_date(value):
    for pattern in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError("날짜는 YYYY-MM-DD 또는 YYYYMMDD 형식입니다.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=parse_date, default=parse_date("2026-10-30"))
    parser.add_argument("--end", type=parse_date, default=parse_date("2026-10-31"))
    parser.add_argument("--page-size", type=int, default=999,
                        help="한 페이지 건수 1~999. 서버 반환 크기로 다음 페이지 계산")
    add_common_argument(parser, output="weather_snapshot.csv", daily_limit=10000)
    args = parser.parse_args()
    key = os.environ.get("DATA_GO_KR_API_KEY", "").strip()
    if not key:
        print("DATA_GO_KR_API_KEY 없음")
        return 2
    validate_budget(args, 10000)
    if args.start > args.end or args.end >= datetime.now(KST).date():
        raise FetchError("시작일과 종료일을 확인하세요. 전일 자료까지만 조회합니다.")
    if not 1 <= args.page_size <= 999:
        raise FetchError("기상 페이지 크기는 1~999입니다.")
    params = {"dataType": "JSON", "dataCd": "ASOS", "dateCd": "HR", "stnIds": "108",
              "startDt": args.start.strftime("%Y%m%d"), "startHh": "00",
              "endDt": args.end.strftime("%Y%m%d"), "endHh": "23",
              "numOfRows": 1 if args.smoke else args.page_size}
    client = ApiClient(key, RequestBudget("asos", args.daily_limit, used_today=args.used_today),
                       retries=0 if args.smoke else 3)
    item, total, pages = collect_page(client, ENDPOINT, params, smoke=args.smoke)
    rows = parse_weather(item, args.source_snapshot_id)
    if any(not args.start <= datetime.fromisoformat(row["observed_at"]).date() <= args.end
           for row in rows):
        raise FetchError("요청 기간 밖의 기상 관측값이 있습니다.")
    summary = {"service": "asos", "http_status": client.http_status,
               "api_result_code": client.result_code, "row_count": len(rows),
               "total_count": total, "planned_page_count": pages,
               "request_count": client.request_count, "smoke": args.smoke}
    if not args.smoke:
        expected = ((args.end - args.start).days + 1) * 24
        metadata = {**summary, "source_code": "kma_asos_hourly", "source_url": SOURCE_URL,
                    "collection_method": "api", "station_id": "108", "station_name": "서울",
                    "timezone": "Asia/Seoul", "reference_start": args.start.isoformat(),
                    "reference_end": args.end.isoformat(), "expected_hour_count": expected,
                    "missing_hour_count": expected - len(rows),
                    "is_complete": len(rows) == expected,
                    "collected_at": datetime.now(KST).isoformat(timespec="seconds")}
        save_snapshot(args.output, rows, COLUMN, metadata, api_key=key)
        summary["missing_hour_count"] = expected - len(rows)
        summary["csv_saved"] = True
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
