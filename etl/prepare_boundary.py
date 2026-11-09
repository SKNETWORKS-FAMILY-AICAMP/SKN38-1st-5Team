"""2013년 서울 25구 경계를 검산해 게시한다. 지도 전용이며 점수에는 쓰지 않는다."""

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import pandas as pd

from etl.prepare import write_json

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
RAW = ROOT / "data/raw/boundary/seoul-districts.geojson"
SOURCE_CODE = "kostat_seoul_boundary"
SOURCE_URL = "https://github.com/southkorea/seoul-maps"
COVERAGE_NOTE = "2013년 경계, 지도 표시 전용, 점수 계산에 쓰지 않음"
CSV_NAME = "region_boundary.csv"
MANIFEST_NAME = "boundary_manifest.json"
VALIDATION_NAME = "boundary_validation.json"
METRIC_COLUMN = ("centroid_latitude", "centroid_longitude", "min_latitude", "max_latitude", "min_longitude", "max_longitude", "ring_count")
COLUMN = ("region_id", "district_name", "boundary_year", "geometry_json", *METRIC_COLUMN)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry_metrics(geometry: dict) -> dict:
    # 경위도를 평면 좌표로 다루므로 중심과 면적은 근사값이다.
    if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("경계 도형은 Polygon 또는 MultiPolygon이어야 합니다.")
    polygons = [geometry.get("coordinates")] if geometry["type"] == "Polygon" else geometry.get("coordinates")
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("경계 좌표가 비어 있습니다.")
    points, ring_count, area, weighted_x, weighted_y = [], 0, 0.0, 0.0, 0.0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("경계 고리가 비어 있습니다.")
        polygon_area = 0.0
        for index, ring in enumerate(polygon):
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("경계 고리는 최소 네 좌표이며 처음과 끝이 같아야 합니다.")
            for point in ring:
                if (not isinstance(point, list) or len(point) != 2
                        or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point)
                        or not (126.75 <= point[0] <= 127.2 and 37.4 <= point[1] <= 37.75)):
                    raise ValueError("경계 좌표가 서울 범위의 유한한 경도·위도가 아닙니다.")
            origin_x, origin_y = ring[0]
            cross_sum = moment_x = moment_y = 0.0
            for left, right in zip(ring, ring[1:]):
                x1, y1 = left[0] - origin_x, left[1] - origin_y
                x2, y2 = right[0] - origin_x, right[1] - origin_y
                cross = x1 * y2 - x2 * y1
                cross_sum += cross
                moment_x += (x1 + x2) * cross
                moment_y += (y1 + y2) * cross
            if abs(cross_sum) < 1e-14:
                raise ValueError("면적이 없는 경계 고리입니다.")
            weight = abs(cross_sum) / 2 * (1 if index == 0 else -1)
            polygon_area += weight
            weighted_x += (origin_x + moment_x / (3 * cross_sum)) * weight
            weighted_y += (origin_y + moment_y / (3 * cross_sum)) * weight
            points.extend(ring)
            ring_count += 1
        if polygon_area <= 0:
            raise ValueError("경계의 내부 고리가 외곽 면적보다 큽니다.")
        area += polygon_area
    result = dict(centroid_latitude=weighted_y / area, centroid_longitude=weighted_x / area,
                  min_latitude=min(p[1] for p in points), max_latitude=max(p[1] for p in points),
                  min_longitude=min(p[0] for p in points), max_longitude=max(p[0] for p in points))
    if not (result["min_latitude"] <= result["centroid_latitude"] <= result["max_latitude"]
            and result["min_longitude"] <= result["centroid_longitude"] <= result["max_longitude"]):
        raise ValueError("경계 중심이 경계 상자 밖에 있습니다.")
    rounded = {}
    for name, value in result.items():
        if name.startswith("min_"):
            rounded[name] = math.floor(value * 10**7) / 10**7
        elif name.startswith("max_"):
            rounded[name] = math.ceil(value * 10**7) / 10**7
        else:
            rounded[name] = round(value, 7)
    return {**rounded, "ring_count": ring_count}


def build_frame(document: dict, regions: pd.DataFrame) -> pd.DataFrame:
    if (len(regions) != 25 or regions.region_id.duplicated().any() or regions.district_name.duplicated().any()
            or document.get("type") != "FeatureCollection" or len(document.get("features", [])) != 25):
        raise ValueError("구 목록과 경계 원본은 중복 없는 서울 25구여야 합니다.")
    region_id = regions.set_index("district_name").region_id.to_dict()
    rows, names = [], set()
    for feature in document["features"]:
        properties = feature.get("properties", {})
        name = properties.get("name")
        if feature.get("type") != "Feature" or str(properties.get("base_year")) != "2013":
            raise ValueError("2013년 경계 feature가 아닙니다.")
        if name not in region_id or name in names:
            raise ValueError("경계 이름이 구 목록과 연결되지 않거나 중복됩니다.")
        names.add(name)
        geometry = feature.get("geometry")
        metrics = geometry_metrics(geometry)
        rows.append(dict(region_id=int(region_id[name]), district_name=name, boundary_year=2013,
                         geometry_json=json.dumps(geometry, ensure_ascii=False, separators=(",", ":"), allow_nan=False), **metrics))
    return pd.DataFrame(rows, columns=pd.Index(COLUMN)).sort_values("region_id").reset_index(drop=True)


def prepare_boundary(regions: pd.DataFrame, output_dir: Path = PROCESSED, source_path: Path = RAW) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_path = output_dir / VALIDATION_NAME
    write_json(validation_path, {"passed": False, "published": False, "status": "running"})
    try:
        frame = build_frame(json.loads(source_path.read_text()), regions)
        source = dict(source_code=SOURCE_CODE, source_url=SOURCE_URL,
                      artifact_path=source_path.resolve().relative_to(ROOT).as_posix(), content_sha256=digest(source_path),
                      reference_start="2013-01-01", reference_end="2013-12-31", page_updated_on=None,
                      collected_on=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(), collected_at=None,
                      collection_method="file", is_complete=0, coverage_note=COVERAGE_NOTE)
        with tempfile.TemporaryDirectory(prefix=".boundary-", dir=output_dir.parent) as directory:
            stage = Path(directory)
            frame.to_csv(stage / CSV_NAME, index=False, encoding="utf-8-sig", lineterminator="\n", float_format="%.7f")
            write_json(stage / MANIFEST_NAME, {"source": [source], "license": "Apache-2.0", "coordinate_order": "longitude,latitude",
                                             "centroid_method": "경위도 평면 면적 중심, 내부 고리 제외. 지도 표시용 근사값."})
            record = {"passed": True, "published": True, "status": "complete", "row_count": len(frame),
                      "district_match_count": len(frame), "ring_count": int(frame.ring_count.sum()),
                      "output_sha256": {CSV_NAME: digest(stage / CSV_NAME)}, "manifest_sha256": digest(stage / MANIFEST_NAME),
                      "raw_sha256": digest(source_path)}
            for name in (CSV_NAME, MANIFEST_NAME):
                (stage / name).replace(output_dir / name)
            write_json(validation_path, record)
        return record
    except Exception as exc:
        write_json(validation_path, {"passed": False, "published": False, "status": "failed", "error_type": type(exc).__name__})
        raise


def read_boundary_package(folder: Path = PROCESSED) -> tuple[dict, pd.DataFrame]:
    record = json.loads((folder / VALIDATION_NAME).read_text())
    if record.get("passed") is not True or record.get("published") is not True or set(record.get("output_sha256", {})) != {CSV_NAME}:
        raise ValueError("경계 정제 검산과 게시가 완료되지 않았습니다.")
    if digest(folder / CSV_NAME) != record["output_sha256"][CSV_NAME] or digest(folder / MANIFEST_NAME) != record.get("manifest_sha256"):
        raise ValueError("경계 CSV 또는 manifest가 검산 이후 변경되었습니다.")
    manifest = json.loads((folder / MANIFEST_NAME).read_text())
    if len(manifest.get("source", [])) != 1:
        raise ValueError("경계 출처는 한 수집본이어야 합니다.")
    source = manifest["source"][0]
    raw = (ROOT / source["artifact_path"]).resolve()
    if not raw.is_relative_to(ROOT / "data/raw/boundary") or digest(raw) != source["content_sha256"] or digest(raw) != record["raw_sha256"]:
        raise ValueError("경계 원본 경로 또는 해시가 다릅니다.")
    if (source["source_code"] != SOURCE_CODE or source["reference_start"] != "2013-01-01"
            or source["reference_end"] != "2013-12-31" or source["coverage_note"] != COVERAGE_NOTE):
        raise ValueError("경계 출처와 기준 연도가 다릅니다.")
    frame = pd.read_csv(folder / CSV_NAME, encoding="utf-8-sig")
    if tuple(frame.columns) != COLUMN:
        raise ValueError("경계 CSV의 컬럼이 다릅니다.")
    expected = build_frame(json.loads(raw.read_text()), frame[["region_id", "district_name"]])
    pd.testing.assert_frame_equal(frame, expected, check_dtype=False, rtol=0, atol=1e-10)
    source["is_complete"] = 0
    return source, frame


def main() -> int:
    from db.connection import get_engine, is_local_config
    from db.queries import get_filter_options

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROCESSED)
    args = parser.parse_args()
    engine = get_engine()
    try:
        if not is_local_config(engine.url):
            raise ValueError("경계 정제의 구 연결 검증은 로컬 DB에서 실행하세요.")
        result = prepare_boundary(get_filter_options()["regions"], args.output_dir)
        print("서울 구 경계 정제 완료:", result["row_count"], "행")
        return 0
    except Exception as exc:
        print("경계 정제 실패:", type(exc).__name__, "원본과 구 이름 연결을 확인하세요.")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
