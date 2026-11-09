"""실제 DB의 조회 계약·검산·점수를 확인한다. 비밀값과 예외 원문은 출력하지 않는다."""

from datetime import date, datetime
import argparse
import json
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from db.connection import LOCAL_HOSTS, get_engine
from db import queries as q

from scoring import MODEL_VERSION, compute_score

ROOT = Path(__file__).resolve().parents[1]
MONTH = date(2026, 9, 1)


def _check_region_filter(query, **filters) -> int:
    whole = query(**filters)
    for region_id in whole.region_id:
        expected = whole.loc[whole.region_id.eq(region_id)].reset_index(drop=True)
        actual = query(region_ids=[int(region_id)], **filters)
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, check_categorical=False)
    return len(whole)


def run_check(engine, report_dir: Path | None = None) -> dict:
    options = q.get_filter_options()
    snapshot = options['snapshots'].drop_duplicates('source_code').set_index('source_code').snapshot_id.to_dict()
    assert len(options['regions']) == 25, '구 25개 조회 실패'
    registration = q.get_registration_breakdown(None, MONTH)
    assert int(registration.loc[registration.fuel_scope_code.eq('all')].vehicle_count.sum()) == 3150351, '서울 등록 조회 실패'
    ranking = q.get_district_ranking(MONTH)
    assert int(ranking.electric_count.sum()) == 127750, '전기 등록 요약 실패'
    assert int(q.get_parking_summary().unique_space_count.sum()) == 73068, '주차 요약 실패'
    assert int(q.get_national_registrations(MONTH).vehicle_count.sum()) == 26706123, '전국 등록 조회 실패'
    assert len(q.search_faq()) == 10, 'FAQ 조회 실패'
    assert len(ranking) == 25 and int(ranking.listed_count.sum()) == 75607, '환경공단 기본 점수 입력 실패'
    assert ranking.charger_snapshot_id.eq(snapshot[q.DEFAULT_CHARGER_SOURCE]).all(), '기본 충전 출처 실패'
    for speed, expected in (("all", 75607), ("fast", 5041), ("slow", 69634), ("unknown", 932)):
        assert int(q.get_charger_summary(speed=speed).listed_count.sum()) == expected, '환경공단 속도 검산 실패'
    with engine.connect() as conn:
        # 비기본 출처 직접 선택은 공개 API에 없어 검산에서만 조회한다.
        seoul = conn.execute(text("""SELECT COUNT(*), SUM(c.speed_code='fast') FROM charger c
            JOIN charging_station t ON t.station_id=c.station_id JOIN source_snapshot s ON s.snapshot_id=t.source_snapshot_id
            WHERE s.source_code='seoul_charger' AND s.is_complete=1 AND s.snapshot_id=:id"""), {'id': int(snapshot['seoul_charger'])}).one()
        assert tuple(map(int, seoul)) == (429, 356), '서울 공공 충전 검산 실패'
        version = conn.execute(text('SELECT VERSION()')).scalar_one()
    region_filter_comparison = {
        q.DEFAULT_CHARGER_SOURCE: sum(_check_region_filter(q.get_charger_summary, speed=speed) for speed in ('all','fast','slow','unknown')),
        'parking_standard': _check_region_filter(q.get_parking_summary),
    }
    for day in (30, 31):
        assert len(q.get_weather(datetime(2026,10,day,8))) == 1, '날씨 시간대 연결 실패'
        transit = q.get_trend_data(None, date(2026,10,day))
        assert len(transit.loc[transit.hour_of_day.eq(8)]) == 75, '승객 주중 주말 연결 실패'
    traffic = q.get_trend_data(None, date(2026,9,30))
    assert len(traffic.loc[traffic.hour_of_day.eq(8)]) == 25, '교통 조회 실패'
    assert q.get_parking_summary([]).empty and q.get_charger_summary([]).empty, '빈 구 목록 처리 실패'
    assert q.get_national_registrations(MONTH, province_name="' OR 1=1 --").empty, '바인딩 검사 실패'
    assert q.search_faq("' OR 1=1 --").empty, 'FAQ 바인딩 검사 실패'
    expected = compute_score(ranking)
    pd.testing.assert_series_equal(ranking.score, expected.score, check_dtype=False)
    assert ranking.score.notna().all() and ranking.score.between(0,100).all(), '점수 범위 검사 실패'
    for prefix in ('ownership','parking','need'):
        assert sorted(ranking[prefix+'_level'].value_counts().tolist()) == [8,8,9], '세 판정 분포 실패'
    points = q.get_place_points(None)
    coverage = pd.DataFrame(points.attrs['coverage'])
    assert len(points)>0 and points.latitude.between(37.4,37.75).all() and points.longitude.between(126.75,127.2).all(), '지도 좌표 검사 실패'
    assert coverage.total_count.eq(coverage.point_count+coverage.excluded_count).all(), '지도 포함·제외 합계 실패'
    assert coverage.excluded_count.eq(coverage.invalid_coordinate_count+coverage.identifier_conflict_count).all(), '지도 제외 사유 합계 실패'
    assert int(coverage.point_count.sum()) == len(points), '지도 핀 합계 실패'
    assert coverage.set_index('kind').total_count.to_dict() == {'charging_station':13098,'parking_site':857}, '지도 출처 범위 실패'
    places = q.search_places('강남',limit=50)
    assert 0<len(places)<=50 and {'충전소','주차장'}.issuperset(set(places.kind_label)), '시설 검색 검사 실패'
    boundaries = q.get_region_boundaries()
    assert len(boundaries)==boundaries.region_id.nunique()==25, '서울 25구 경계 연결 실패'
    assert boundaries.boundary_year.eq(2013).all(), '경계 기준 연도 실패'
    assert boundaries.min_latitude.ge(37.4).all() and boundaries.max_latitude.le(37.75).all(), '경계 위도 실패'
    assert boundaries.min_longitude.ge(126.75).all() and boundaries.max_longitude.le(127.2).all(), '경계 경도 실패'
    assert all(json.loads(value)['type'] in ('Polygon','MultiPolygon') for value in boundaries.geometry_json), '경계 JSON 실패'
    frames = {'get_district_ranking':ranking,'get_registration_breakdown':registration,
              'get_place_points':points,'search_places':places,'get_region_boundaries':boundaries}
    result = {name:{'row_count':len(frame),'column':list(frame.columns)} for name,frame in frames.items()}
    result['get_place_points']['coverage'] = coverage.to_dict('records')
    record = {'passed':True,'server_version':version,'local_version_accepted':engine.url.host in LOCAL_HOSTS,
              'sql_target':'MySQL 8.0.16 이상 문법','query':result,
              'default_charger_source':q.DEFAULT_CHARGER_SOURCE,'default_charger_count':75607,
              'region_filter_comparison':region_filter_comparison,
              'weather_hour_count':48,'score_model':MODEL_VERSION,'score_row_count':len(ranking)}
    output_dir = Path(report_dir) if report_dir is not None else Path(os.getenv('DB_REPORT_DIR', ROOT/'docs'))
    output_dir.mkdir(parents=True,exist_ok=True)
    ranking.to_csv(output_dir/'score_result.csv',index=False,encoding='utf-8-sig')
    (output_dir/'query_check.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', type=Path, help='검사 결과 위치. 기본 DB_REPORT_DIR 또는 docs')
    args = parser.parse_args()
    engine = None
    try:
        engine = get_engine()
        result = run_check(engine, args.report_dir)
        print('연결·조회·점수 검사 완료: MySQL', result['server_version'], ', 필수 조회·지도·검색·날씨, 서울 25구')
        return 0
    except Exception as exc:
        print('DB 검사 실패:', type(exc).__name__, '설정·적재 상태·검산 조건을 확인하세요.')
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
