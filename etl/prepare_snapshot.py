"""기존 교통·승객 파일을 구별 시간 스냅샷으로 정제한다. 외부 호출 없음."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import pandas as pd

from etl.prepare import DISTRICT, PROJECT, RAW, count_value, district_from_address, write_json

OUT = PROJECT / "data/processed/snapshot"
SOURCE = {
    "seoul_traffic": ("api_research/seoul_traffic/traffic_202609.xlsx", "https://topis.seoul.go.kr/refRoom/openRefRoom_1.do?tab=volumeDaily", "2026-09-01", "2026-09-30"),
    "seoul_passenger": ("api_research/seoul_passenger/tpss.csv", "https://t-data.seoul.go.kr/dataprovide/download.do?id=10239", "2026-10-30", "2026-10-31"),
}


def prepare_traffic(path: Path) -> dict[str, pd.DataFrame]:
    point = pd.read_excel(path, sheet_name="수집지점 주소 및 좌표", dtype=str)
    point["지점번호"] = point["지점번호"].ffill()
    point = point.loc[point["방향"].isin(["유입", "유출"])].copy()
    point["district_name"] = point["주소"].map(district_from_address)
    point["district_name"] = point["district_name"].fillna(point["도로명 주소"].map(district_from_address))
    if point.duplicated(["지점번호", "방향"]).any():
        raise ValueError("교통 지점·방향이 중복되었습니다.")
    point = point.loc[point.district_name.isin(DISTRICT)]
    frame = pd.read_excel(path, sheet_name="2026년 09월", dtype=str)
    expected_date = set(pd.date_range("2026-09-01", "2026-09-30").strftime("%Y%m%d"))
    if set(frame["일자"]) != expected_date:
        raise ValueError("교통 관측일이 고정 수집 기간과 다릅니다.")
    frame = frame.merge(point[["지점번호", "방향", "district_name"]], on=["지점번호", "방향"], validate="many_to_one")
    if frame.duplicated(["일자", "지점번호", "방향"]).any():
        raise ValueError("교통 날짜·지점·방향이 중복되었습니다.")
    long = frame.melt(id_vars=["district_name", "일자", "지점번호", "방향"], value_vars=[str(hour) + "시" for hour in range(24)], var_name="hour", value_name="count")
    long["observed_at"] = pd.to_datetime(long["일자"], format="%Y%m%d") + pd.to_timedelta(long["hour"].str.removesuffix("시").astype(int), unit="h")
    long["count"] = long["count"].map(lambda value: None if pd.isna(value) or str(value).strip() == "" else count_value(value)).astype("Int64")
    group = long.groupby(["district_name", "observed_at"])["count"]
    snapshot = pd.concat([group.count().rename("valid_point_direction_count"), group.sum(min_count=1).rename("known_vehicle_sum")], axis=1).reset_index()
    coverage = point.groupby("district_name").size().reindex(DISTRICT, fill_value=0).rename("expected_point_direction_count").reset_index().rename(columns={"index": "district_name"})
    expected = snapshot.merge(coverage, on="district_name", validate="many_to_one")
    if not (expected.valid_point_direction_count <= expected.expected_point_direction_count).all():
        raise ValueError("교통 유효 지점 수가 관측 범위를 넘었습니다.")
    if len(point) != 260 or len(snapshot) != 17280 or int(snapshot.valid_point_direction_count.sum()) != 180755:
        raise ValueError("교통 수집본의 기존 검산과 다릅니다.")
    return {"traffic_coverage": coverage, "traffic_snapshot": snapshot}


def prepare_transit(path: Path) -> dict[str, pd.DataFrame]:
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    if frame.duplicated(["기준일", "행정동ID", "분석유형"]).any():
        raise ValueError("승객 날짜·행정동·유형이 중복되었습니다.")
    if (set(frame["기준일"]) != {"20261030", "20261031"}
            or set(frame["분석유형"]) != {"4"}
            or not frame.groupby("기준일")["행정동ID"].nunique().eq(426).all()):
        raise ValueError("승객 관측일·분석유형·행정동 수가 고정 수집본과 다릅니다.")
    if set(frame["자치구명"]) != set(DISTRICT):
        raise ValueError("승객 자료의 서울 25구 연결을 확인하세요.")
    frame = frame.rename(columns={"자치구명": "district_name", "분석유형": "analysis_type"})
    frame["stat_date"] = pd.to_datetime(frame["기준일"], format="%Y%m%d").dt.date
    key = ["district_name", "stat_date", "analysis_type"]
    coverage = frame.groupby(key)["행정동ID"].nunique().rename("expected_dong_count").reset_index()
    outputs = []
    for mode, label in {"total": "합계", "bus": "버스", "subway": "지하철"}.items():
        long = frame.melt(id_vars=key, value_vars=[label + str(hour).zfill(2) + "H" for hour in range(24)], var_name="hour", value_name="count")
        long["hour_of_day"] = long.hour.str.extract(r"([0-9]{2})H$")[0].astype(int)
        long["count"] = long["count"].map(lambda value: None if pd.isna(value) or str(value).strip() == "" else count_value(value)).astype("Int64")
        group = long.groupby(key + ["hour_of_day"])["count"]
        summary = pd.concat([group.count().rename("valid_dong_count"), group.sum(min_count=1).rename("known_passenger_sum")], axis=1).reset_index()
        summary["mode_code"] = mode
        outputs.append(summary)
    snapshot = pd.concat(outputs, ignore_index=True)
    check = snapshot.merge(coverage, on=key, validate="many_to_one")
    if len(coverage) != 50 or len(snapshot) != 3600 or int((check.valid_dong_count < check.expected_dong_count).sum()) != 1296:
        raise ValueError("승객 수집본의 기존 검산과 다릅니다.")
    if not (check.valid_dong_count <= check.expected_dong_count).all():
        raise ValueError("승객 유효 행정동 수가 기대 수를 넘었습니다.")
    return {"transit_coverage": coverage, "transit_ridership_snapshot": snapshot}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=RAW)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "validation.json", {"passed": False, "published": False})
    manifest, count, digest = [], {}, {}
    try:
        with tempfile.TemporaryDirectory(dir=OUT.parent, prefix=".snapshot-") as directory:
            stage = Path(directory)
            for code, (relative, url, start, end) in SOURCE.items():
                source, target = args.source_dir / relative, RAW / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.resolve() != target.resolve():
                    shutil.copyfile(source, target)
                frames = prepare_traffic(target) if code == "seoul_traffic" else prepare_transit(target)
                for name, frame in frames.items():
                    frame.to_csv(stage / (name + ".csv"), index=False, encoding="utf-8-sig")
                    count[name] = len(frame)
                    digest[name + ".csv"] = hashlib.sha256((stage / (name + ".csv")).read_bytes()).hexdigest()
                manifest.append({"source_code": code, "source_url": url, "artifact_path": "data/raw/" + relative,
                                 "content_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                                 "reference_start": start, "reference_end": end, "collected_on": "2026-11-06",
                                 "collection_method": "file", "coverage_note": "교통은 2026년 9월 24구 관측, 승객은 10월 30~31일 25구 표본. 결측은 0이 아님."})
            write_json(stage / "source_manifest.json", {"source": manifest})
            for path in stage.iterdir():
                path.replace(OUT / path.name)
        write_json(OUT / "validation.json", {"passed": True, "published": True, "row_count": count, "output_sha256": digest})
        print("스냅샷 정제 완료:", json.dumps(count, ensure_ascii=False))
        return 0
    except Exception as exc:
        write_json(OUT / "validation.json", {"passed": False, "published": False, "error_type": type(exc).__name__})
        print("스냅샷 정제 실패:", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
