"""환경공단 서울 충전기 목록 수집. 기존 서울 충전 CSV와 별도로 보관한다."""

from __future__ import annotations

import argparse
import hashlib
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

ENDPOINT = "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo"
SOURCE_URL = "https://www.data.go.kr/data/15076352/openapi.do"
SOURCE_CODE = "keco_ev_charger"
DISTRICT = ("종로구 중구 용산구 성동구 광진구 동대문구 중랑구 성북구 강북구 도봉구 "
            "노원구 은평구 서대문구 마포구 양천구 강서구 구로구 금천구 영등포구 "
            "동작구 관악구 서초구 강남구 송파구 강동구").split()
ADDRESS = re.compile(r"^서울(?:특별시|시)?\s*(" + "|".join(sorted(DISTRICT, key=len, reverse=True)) + r")")
CONNECTOR = {"01": "DC차데모", "02": "AC완속", "03": "DC차데모+AC3상", "04": "DC콤보",
             "05": "DC차데모+DC콤보", "06": "DC차데모+AC3상+DC콤보", "07": "AC3상",
             "08": "DC콤보(완속)", "09": "NACS", "10": "DC콤보+NACS"}
COLUMN = ("source_snapshot_id", "source_station_id", "station_key", "source_charger_id",
          "source_row_no", "district_name",
          "station_name", "operator_name", "address", "latitude", "longitude",
          "connector_code", "connector_text", "speed_code", "capacity_kw", "capacity_text",
          "charging_method", "operating_time_text", "restriction_code", "restriction_note",
          "parking_free", "deleted_code", "deleted_note", "floor_type", "floor_number",
          "province_code", "district_code", "status_code", "status_updated_at")


def parse_charger(item, source_snapshot_id=None):
    result, seen = [], set()
    for source_row_no, source in enumerate(item, 1):
        station = text_value(source.get("statId"))
        charger = text_value(source.get("chgerId"))
        if not station or not charger or (station, charger) in seen:
            raise FetchError("충전기 식별자가 없거나 중복되었습니다.")
        seen.add((station, charger))
        if text_value(source.get("zcode")) != "11":
            raise FetchError("서울 지역코드 11이 아닌 충전기가 있습니다.")
        address = " ".join(text_value(source.get("addr")).split())
        district = ADDRESS.match(address)
        connector = text_value(source.get("chgerType"))
        speed = ("slow" if connector in {"02", "08"} else "fast"
                 if connector in {"01", "03", "04", "05", "06", "07"} else "unknown")
        capacity = text_value(source.get("output"))
        capacity_kw = decimal_value(capacity) if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", capacity) else None
        updated = text_value(source.get("statUpdDt"))
        if updated:
            try:
                updated = datetime.strptime(updated, "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise FetchError("충전기 상태 갱신시각이 올바르지 않습니다.") from None
        station_key = hashlib.sha256(json.dumps(
            [SOURCE_CODE, station], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        row = {"source_snapshot_id": source_snapshot_id, "source_station_id": station,
               "station_key": station_key, "source_row_no": source_row_no,
               "source_charger_id": charger, "district_name": district[1] if district else None,
               "address": address or None, "connector_code": connector or None,
               "connector_text": CONNECTOR.get(connector), "speed_code": speed,
               "capacity_kw": capacity_kw, "capacity_text": capacity or None,
               "status_updated_at": updated or None}
        for api_name, column in (
            ("statNm", "station_name"), ("busiNm", "operator_name"), ("method", "charging_method"),
            ("useTime", "operating_time_text"), ("limitYn", "restriction_code"),
            ("limitDetail", "restriction_note"), ("parkingFree", "parking_free"),
            ("delYn", "deleted_code"), ("delDetail", "deleted_note"),
            ("floorType", "floor_type"), ("floorNum", "floor_number"),
            ("zcode", "province_code"), ("zscode", "district_code"), ("stat", "status_code"),
        ):
            row[column] = text_value(source.get(api_name)) or None
        for api_name, column, bound in (("lat", "latitude", 90), ("lng", "longitude", 180)):
            coordinate = decimal_value(source.get(api_name))
            row[column] = (coordinate if coordinate is not None
                           and 0 < abs(float(coordinate)) <= bound else None)
        result.append(row)
    return sorted(result, key=lambda row: (row["source_station_id"], row["source_charger_id"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-size", type=int, default=9999, help="한 페이지 건수 10~9999")
    add_common_argument(parser, output="charger_national_snapshot.csv", daily_limit=1000)
    args = parser.parse_args()
    key = os.environ.get("DATA_GO_KR_API_KEY", "").strip()
    if not key:
        print("DATA_GO_KR_API_KEY 없음")
        return 2
    validate_budget(args, 1000)
    if not 10 <= args.page_size <= 9999:
        raise FetchError("충전기 페이지 크기는 10~9999입니다.")
    params = {"dataType": "JSON", "zcode": "11", "numOfRows": 10 if args.smoke else args.page_size}
    client = ApiClient(key, RequestBudget("ev_charger", args.daily_limit, used_today=args.used_today),
                       retries=0 if args.smoke else 3)
    item, total, pages = collect_page(client, ENDPOINT, params, smoke=args.smoke)
    rows = parse_charger(item, args.source_snapshot_id)
    summary = {"service": "ev_charger", "http_status": client.http_status,
               "api_result_code": client.result_code, "row_count": len(rows),
               "total_count": total, "planned_page_count": pages,
               "request_count": client.request_count, "smoke": args.smoke}
    if not args.smoke:
        metadata = {**summary, "source_code": SOURCE_CODE, "source_url": SOURCE_URL,
                    "collection_method": "api", "province_code": "11", "timezone": "Asia/Seoul",
                    "collected_at": datetime.now(KST).isoformat(timespec="seconds"),
                    "is_complete": True,
                    "unmatched_district_count": sum(row["district_name"] is None for row in rows),
                    "deleted_count": sum(row["deleted_code"] == "Y" for row in rows),
                    "unknown_speed_count": sum(row["speed_code"] == "unknown" for row in rows),
                    "coverage_note": "API 수록 서울 목록의 수신 완료. 서울 전체 공급량을 보장하지 않음"}
        save_snapshot(args.output, rows, COLUMN, metadata, api_key=key)
        summary["csv_saved"] = True
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
