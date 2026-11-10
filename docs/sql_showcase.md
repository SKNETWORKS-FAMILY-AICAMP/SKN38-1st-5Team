# MySQL·DBeaver 대표 SQL 7개

차차차 · 2026-11-09 · 현재 `db/queries.py` 기준

서울 25구 자료를 보관하는 MySQL은 18표·총 111,676행이다. 이 문서는 조회 함수의 SQL을 DBeaver에서 실행하는 예시다. 세 판정·서울 지도·25구 순위·두 동네 비교와 전국 등록·FAQ의 조회를 다룬다. 앱 사용 방법은 [화면·실행 안내](../README.md)에 정리했다.

예시는 데이터가 적재된 `chachacha` DB를 사용한다. DB 덤프·정제 CSV·원본과 기업 FAQ 원문은 공개 레포에 포함하지 않는다. 데이터 준비에는 [출처 기록](../data/SOURCES.md)을 참고한다.

DBeaver에서 `chachacha` DB를 선택하고 각 SQL 블록을 처음부터 세미콜론까지 한 문장으로 실행한다. 1번은 긴 SQL 전문을 접어 두었다. 7개 모두 `WITH` 또는 `SELECT` 조회문이다.

## 원본 SQL과 예시 값

- 원본: [db/queries.py](../db/queries.py). 바인드 변수 자리에 예시 값을 넣고 함수의 CTE·반환 열·집계·필터·정렬을 사용한다.
- 기준월은 `date(2026, 9, 1)`이며 SQL에는 `'2026-09-01'`로 표시한다. 등록 자료는 **2026-09 한 달뿐**이므로 전월 대비 증감과 월별 추이는 계산하지 않는다.
- 2–4번의 `region_id=13`은 프로젝트 DB의 **마포구** 번호다. 다른 DB에서는 `SELECT region_id, district_name FROM region WHERE district_name='마포구';`로 먼저 확인한다. 이 한 줄은 번호 확인용 보조 조회이며 대표 SQL 7개에는 포함하지 않는다.
- 시설·경계·승객 자료는 `is_complete=1`인 수집본 중 출처별 수집일·번호가 가장 최신인 한 개를 선택한다. 충전은 `keco_ev_charger`만 사용하고 서울 공공 출처를 더하거나 대신 쓰지 않는다.
- 애플리케이션은 사용자 값을 SQLAlchemy 바인드 변수로 전달한다. 아래 고정값 SQL을 사용자 입력 문자열 연결의 예시로 사용하지 않는다.

| 번호 | 현재 함수 | 예시 조건 | 연결할 화면·근거 |
| --- | --- | --- | --- |
| 1 | `get_district_ranking` | 2026-09, 25구 전체 | [우리 동네](screens/01_home.png)의 지도 색, [25구 순위](../app_pages/ranking.py)의 세 판정 카드·클릭하는 25구 막대 순위. 비교와 요약 함수도 같은 지표 CTE 사용 |
| 2 | `get_registration_breakdown` | 마포구, 2026-09 | 차량 보유의 차종별 구성, 두 동네 비교의 차종·전기차 상세 |
| 3 | `get_charger_summary` | 마포구, `speed='all'` | 전기차 충전의 충전기 요약과 대조할 집계 예시. 화면은 `get_summary_metrics`·`get_charger_breakdown` 사용 |
| 4 | `get_parking_summary` | 마포구 | 주차·충전 찾기의 수록 주차면 요약. 25구 순위의 주차 판정도 같은 주차 집계 CTE 사용 |
| 5 | `get_national_registrations` | 2026-09, 시도·차종·용도 전체 | [전국 등록 조회](screens/03_national.png)의 등록 지표·시도별 용도/차종 누적 막대·등록표 |
| 6 | `search_faq` | 검색어 `충전`, 기업·분류 전체, 최대 50건 | [기업 FAQ](screens/04_faq.png)의 질문·답변 검색 |
| 7 | `get_region_boundaries` | 최신 유효 경계 수집본 | 홈 지도의 구 모양·구 선택, 차량 보유와 주차·충전 지도의 구 경계, 실시간 교통 지도의 선택 구 중심 |

홈 지도·25구 순위·차량 보유·두 동네 비교·전국 등록 조회는 기준월을 생략해 최신 유효 등록월을 조회하며 현재는 2026-09다. 아래 예시는 같은 월을 명시해 재현한다. SQL 4의 함수는 주차·충전 찾기의 면수 요약에 쓰이며, 주차 지도와 목록은 `get_place_points`와 `search_places`를 사용한다. 전국 화면은 SQL 5의 필터 결과를 Python에서 조건별·시도별로 합산하며, SQL 5 자체는 시도·차종·용도별 행을 반환한다.

25구 순위의 `판정 기준과 출처`와 자료 안내에 표시하는 자료 출처·기준 기간·수집일은 `get_filter_options()`가 반환한 `snapshots`를 사용한다.

## 1. 25구 지표·순위·세 판정

대응 함수는 `get_district_ranking(date(2026, 9, 1))`다. 등록·주차·충전·승객을 각각 구 단위로 집계한 뒤 연결하여 시설 상세끼리의 JOIN으로 숫자가 불어나는 문제를 피한다. `metric_windows`에서 서울 평균과 순위를, `ranked_metrics`에서 세 판정을 계산한다. **집계·순위·세 판정과 보조 종합점수는 MySQL에서 계산한다.** `scoring.py`에는 보조점수의 기준 구현이 있다.

각 지표는 큰 값부터 `RANK()`로 순위를 매긴다. 1–8위, 9–17위, 18–25위에 다음 라벨을 붙인다. 동률은 같은 순위이며 다음 순위를 건너뛰므로 각 묶음의 구 수가 항상 8·9·8인 것은 아니다. 결측은 순위도 결측이고 라벨은 `자료 없음`이다. 결측이 생겨도 경계 8·17을 유효 구 수에 맞춰 다시 나누지는 않는다.

| 판정 | 비교하는 값 | 순위별 라벨: 1–8 / 9–17 / 18–25 |
| --- | --- | --- |
| 차량 보유 현황 | 같은 달 등록 차량 ÷ 세대수 | 많은 편 / 보통 / 적은 편 |
| 주차하기 좋은 동네 | 관리번호 충돌을 뺀 수록 주차면 ÷ 등록 차량 | 좋음 / 보통 / 빠듯함 |
| 차가 꼭 필요한 동네 | 2026-10-30 하루 수록 승객 합 ÷ 선택 등록월의 주민 수 | 대중교통으로 충분 / 있으면 편함 / 차가 필요한 편 |

보유는 **한 세대당 차의 수**, 주차는 **차량에 비해 수록 주차면이 얼마나 있는지**, 필요성은 **주민 수에 비해 하루 대중교통 이용이 얼마나 많은지**를 읽는 값이다. 화면의 주차 값은 `parking_value * 100`을 표시한 **차 100대당 주차면**이며 순위·판정은 SQL 결과 그대로다. 필요성 순위는 **대중교통 이용 많은 순**이므로 1위가 차량을 가장 필요로 한다는 뜻은 아니다.

차 필요 판정은 하루 자료로 만든 상대적 **추정**이다. 승객 수에는 거주자 외 방문·통근 이용이 포함되며 실제 구매 필요를 확정하지 않는다. **중구·종로구는 출퇴근 유입으로 주민당 승객 값이 커질 수 있다.** 등록·주민은 2026-09, 승객은 2026-10-30으로 기준 시점도 다르다.

승객은 `mode_code='total'`의 24시간만 더한다. `bus`·`subway`를 다시 합치지 않는다. 분석유형이 정확히 하나이고 24시간 행·승객 값이 모두 있으며 주민 수가 0보다 커야 필요 지표를 계산한다. 강서구는 24시간 모두 자료가 있지만 행정동 일부가 빠진 부분합이다. `transit_complete_hour_count=0`, `transit_observed_hour_count=24`를 함께 제공하며, 이 값만으로 강서구 전체의 이용량을 단정하지 않는다.

`get_summary_metrics`와 `get_compare_metrics`도 같은 CTE를 사용한다. **25구의 순위를 먼저 계산한 다음 마지막 SELECT에서 한두 구를 고른다.** 비교 함수는 입력한 구 순서로 반환하고, 같은 구 번호를 두 번 넣으면 1행이다. 두 구만 대상으로 순위를 다시 매기지 않는다.

<details>
<summary>실행 가능한 SQL 1 전문 펼치기</summary>

```sql
WITH ranked_snapshot AS (
    SELECT snapshot_id, source_code,
           ROW_NUMBER() OVER (PARTITION BY source_code ORDER BY collected_on DESC, snapshot_id DESC) AS source_rank
    FROM source_snapshot WHERE is_complete=1
), latest_snapshot AS (
    SELECT snapshot_id, source_code FROM ranked_snapshot WHERE source_rank=1
)

, chosen_month AS (
    SELECT COALESCE('2026-09-01', MAX(r.stat_month)) AS stat_month
    FROM registration r JOIN source_snapshot s ON s.snapshot_id=r.source_snapshot_id AND s.is_complete=1
)

, parking AS (
    SELECT p.region_id, COUNT(*) AS listed_row_count,
           SUM(p.identifier_status='conflict') AS identifier_conflict_count,
           SUM(CASE WHEN p.identifier_status='unique' THEN p.space_count END) AS unique_space_count,
           SUM(p.space_count IS NULL) AS missing_space_count,
           SUM(p.identifier_status='unique' AND p.space_count IS NULL) AS unique_missing_space_count,
           SUM(p.parking_operation='공영') AS public_row_count,
           SUM(p.parking_operation='민영') AS private_row_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='공영' THEN p.space_count ELSE 0 END) AS public_known_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='민영' THEN p.space_count ELSE 0 END) AS private_known_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND COALESCE(p.parking_operation,'') NOT IN ('공영','민영') THEN p.space_count ELSE 0 END) AS other_known_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='공영' AND p.space_count IS NULL THEN 1 ELSE 0 END) AS public_missing_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='민영' AND p.space_count IS NULL THEN 1 ELSE 0 END) AS private_missing_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND COALESCE(p.parking_operation,'') NOT IN ('공영','민영') AND p.space_count IS NULL THEN 1 ELSE 0 END) AS other_missing_space_count
    FROM parking_site p JOIN latest_snapshot s ON s.snapshot_id=p.source_snapshot_id
    WHERE s.source_code='parking_standard' GROUP BY p.region_id
)

, charging AS (
    SELECT t.region_id, COUNT(*) AS listed_count, COUNT(DISTINCT t.station_id) AS listed_station_count,
           SUM(c.restriction_note IS NOT NULL) AS restriction_noted_count,
           SUM(c.restriction_note IS NULL) AS restriction_unknown_count,
           SUM(c.speed_code='fast') AS fast_count, SUM(c.speed_code='slow') AS slow_count,
           SUM(c.speed_code='unknown') AS unknown_count
    FROM charging_station t JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
    JOIN charger c ON c.station_id=t.station_id
    WHERE s.source_code='keco_ev_charger' AND ('all'='all' OR c.speed_code='all')
    GROUP BY t.region_id
)

, car AS (
    SELECT r.region_id,
           CASE WHEN SUM(r.fuel_scope_code='all')=4 THEN SUM(CASE WHEN r.fuel_scope_code='all' THEN r.vehicle_count END) END AS vehicle_count,
           CASE WHEN SUM(r.fuel_scope_code='electric')=4 THEN SUM(CASE WHEN r.fuel_scope_code='electric' THEN r.vehicle_count END) END AS electric_count
    FROM registration r JOIN source_snapshot s ON s.snapshot_id=r.source_snapshot_id AND s.is_complete=1
    JOIN chosen_month m ON m.stat_month=r.stat_month GROUP BY r.region_id
), resident AS (
    SELECT c.region_id, c.population, c.household_count FROM region_context c
    JOIN source_snapshot s ON s.snapshot_id=c.resident_snapshot_id AND s.is_complete=1
    JOIN chosen_month m ON m.stat_month=c.stat_month
), weekday_analysis AS (
    SELECT MIN(t.analysis_type) AS analysis_type FROM transit_ridership_snapshot t
    JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id AND s.source_code='seoul_passenger'
    WHERE t.stat_date='2026-10-30' AND t.mode_code='total'
    HAVING COUNT(DISTINCT t.analysis_type)=1
), weekday_transit AS (
    SELECT t.region_id, t.analysis_type, SUM(t.known_passenger_sum) AS transit_passenger_count,
           COUNT(*) AS transit_observed_hour_count,
           COUNT(t.known_passenger_sum) AS transit_known_hour_count,
           SUM(t.valid_dong_count=v.expected_dong_count) AS transit_complete_hour_count,
           MIN(t.valid_dong_count) AS transit_min_valid_dong_count,
           MAX(v.expected_dong_count) AS transit_expected_dong_count
    FROM transit_ridership_snapshot t JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
    JOIN transit_coverage v ON v.source_snapshot_id=t.source_snapshot_id AND v.region_id=t.region_id
         AND v.stat_date=t.stat_date AND v.analysis_type=t.analysis_type
    JOIN weekday_analysis a ON a.analysis_type=t.analysis_type
    WHERE s.source_code='seoul_passenger' AND t.stat_date='2026-10-30' AND t.mode_code='total'
    GROUP BY t.region_id, t.analysis_type
), metrics AS (
    SELECT g.region_id, g.district_name, m.stat_month, c.vehicle_count, c.electric_count,
           x.population, x.household_count,
           CAST(c.vehicle_count AS DECIMAL(24,10))/NULLIF(x.household_count,0) AS vehicle_per_household,
           CASE WHEN c.electric_count<=c.vehicle_count THEN 100.0*c.electric_count/NULLIF(c.vehicle_count,0) END AS electric_share_pct,
           p.listed_row_count, p.identifier_conflict_count, p.unique_space_count,
           p.missing_space_count, p.unique_missing_space_count, p.public_row_count, p.private_row_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.listed_count,0) END AS listed_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.listed_station_count,0) END AS listed_station_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.restriction_noted_count,0) END AS restriction_noted_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.restriction_unknown_count,0) END AS restriction_unknown_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.fast_count,0) END AS fast_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.slow_count,0) END AS slow_count,
           CASE WHEN cs.snapshot_id IS NOT NULL THEN COALESCE(h.unknown_count,0) END AS unknown_count,
           CASE WHEN p.unique_missing_space_count=0 THEN 1e0*p.unique_space_count/NULLIF(c.vehicle_count,0) END AS parking_per_vehicle,
           CASE WHEN c.electric_count<=c.vehicle_count AND cs.snapshot_id IS NOT NULL
                THEN 1e0*COALESCE(h.listed_count,0)/NULLIF(c.electric_count,0) END AS charger_per_electric_vehicle,
           ps.snapshot_id AS parking_snapshot_id, cs.snapshot_id AS charger_snapshot_id,
           '2026-10-30' AS need_stat_date, t.analysis_type AS need_analysis_type,
           t.transit_passenger_count, t.transit_observed_hour_count, t.transit_complete_hour_count,
           t.transit_min_valid_dong_count, t.transit_expected_dong_count,
           CASE WHEN t.transit_observed_hour_count=24 AND t.transit_known_hour_count=24
                THEN CAST(t.transit_passenger_count AS DECIMAL(30,14))/NULLIF(x.population,0) END AS transit_passenger_per_resident
    FROM region g CROSS JOIN chosen_month m LEFT JOIN car c ON c.region_id=g.region_id
    LEFT JOIN resident x ON x.region_id=g.region_id LEFT JOIN parking p ON p.region_id=g.region_id
    LEFT JOIN charging h ON h.region_id=g.region_id
    LEFT JOIN latest_snapshot ps ON ps.source_code='parking_standard'
    LEFT JOIN latest_snapshot cs ON cs.source_code='keco_ev_charger'
    LEFT JOIN weekday_transit t ON t.region_id=g.region_id
)
, metric_windows AS (
    SELECT m.region_id,
           m.district_name,
           m.stat_month,
           m.vehicle_count,
           m.electric_count,
           m.population,
           m.household_count,
           m.vehicle_per_household,
           m.electric_share_pct,
           m.listed_row_count,
           m.identifier_conflict_count,
           m.unique_space_count,
           m.missing_space_count,
           m.unique_missing_space_count,
           m.public_row_count,
           m.private_row_count,
           m.listed_count,
           m.listed_station_count,
           m.restriction_noted_count,
           m.restriction_unknown_count,
           m.fast_count,
           m.slow_count,
           m.unknown_count,
           m.parking_per_vehicle,
           m.charger_per_electric_vehicle,
           m.parking_snapshot_id,
           m.charger_snapshot_id,
           m.need_stat_date,
           m.need_analysis_type,
           m.transit_passenger_count,
           m.transit_observed_hour_count,
           m.transit_complete_hour_count,
           m.transit_min_valid_dong_count,
           m.transit_expected_dong_count,
           m.transit_passenger_per_resident,
           AVG(m.vehicle_count) OVER () AS vehicle_count_seoul_avg,
           m.vehicle_count - AVG(m.vehicle_count) OVER () AS vehicle_count_vs_seoul,
           CASE WHEN m.vehicle_count IS NOT NULL THEN RANK() OVER (ORDER BY m.vehicle_count DESC) END AS vehicle_count_rank,
           COUNT(m.vehicle_count) OVER () AS vehicle_count_seoul_count,
           AVG(m.vehicle_per_household) OVER () AS vehicle_per_household_seoul_avg,
           m.vehicle_per_household - AVG(m.vehicle_per_household) OVER () AS vehicle_per_household_vs_seoul,
           CASE WHEN m.vehicle_per_household IS NOT NULL THEN RANK() OVER (ORDER BY m.vehicle_per_household DESC) END AS vehicle_per_household_rank,
           COUNT(m.vehicle_per_household) OVER () AS vehicle_per_household_seoul_count,
           AVG(m.electric_count) OVER () AS electric_count_seoul_avg,
           m.electric_count - AVG(m.electric_count) OVER () AS electric_count_vs_seoul,
           CASE WHEN m.electric_count IS NOT NULL THEN RANK() OVER (ORDER BY m.electric_count DESC) END AS electric_count_rank,
           COUNT(m.electric_count) OVER () AS electric_count_seoul_count,
           AVG(m.electric_share_pct) OVER () AS electric_share_pct_seoul_avg,
           m.electric_share_pct - AVG(m.electric_share_pct) OVER () AS electric_share_pct_vs_seoul,
           CASE WHEN m.electric_share_pct IS NOT NULL THEN RANK() OVER (ORDER BY m.electric_share_pct DESC) END AS electric_share_pct_rank,
           COUNT(m.electric_share_pct) OVER () AS electric_share_pct_seoul_count,
           AVG(m.listed_row_count) OVER () AS listed_row_count_seoul_avg,
           m.listed_row_count - AVG(m.listed_row_count) OVER () AS listed_row_count_vs_seoul,
           CASE WHEN m.listed_row_count IS NOT NULL THEN RANK() OVER (ORDER BY m.listed_row_count DESC) END AS listed_row_count_rank,
           COUNT(m.listed_row_count) OVER () AS listed_row_count_seoul_count,
           AVG(m.unique_space_count) OVER () AS unique_space_count_seoul_avg,
           m.unique_space_count - AVG(m.unique_space_count) OVER () AS unique_space_count_vs_seoul,
           CASE WHEN m.unique_space_count IS NOT NULL THEN RANK() OVER (ORDER BY m.unique_space_count DESC) END AS unique_space_count_rank,
           COUNT(m.unique_space_count) OVER () AS unique_space_count_seoul_count,
           AVG(m.listed_count) OVER () AS listed_count_seoul_avg,
           m.listed_count - AVG(m.listed_count) OVER () AS listed_count_vs_seoul,
           CASE WHEN m.listed_count IS NOT NULL THEN RANK() OVER (ORDER BY m.listed_count DESC) END AS listed_count_rank,
           COUNT(m.listed_count) OVER () AS listed_count_seoul_count,
           AVG(m.listed_station_count) OVER () AS listed_station_count_seoul_avg,
           m.listed_station_count - AVG(m.listed_station_count) OVER () AS listed_station_count_vs_seoul,
           CASE WHEN m.listed_station_count IS NOT NULL THEN RANK() OVER (ORDER BY m.listed_station_count DESC) END AS listed_station_count_rank,
           COUNT(m.listed_station_count) OVER () AS listed_station_count_seoul_count,
           AVG(m.fast_count) OVER () AS fast_count_seoul_avg,
           m.fast_count - AVG(m.fast_count) OVER () AS fast_count_vs_seoul,
           CASE WHEN m.fast_count IS NOT NULL THEN RANK() OVER (ORDER BY m.fast_count DESC) END AS fast_count_rank,
           COUNT(m.fast_count) OVER () AS fast_count_seoul_count,
           AVG(m.slow_count) OVER () AS slow_count_seoul_avg,
           m.slow_count - AVG(m.slow_count) OVER () AS slow_count_vs_seoul,
           CASE WHEN m.slow_count IS NOT NULL THEN RANK() OVER (ORDER BY m.slow_count DESC) END AS slow_count_rank,
           COUNT(m.slow_count) OVER () AS slow_count_seoul_count,
           AVG(m.parking_per_vehicle) OVER () AS parking_per_vehicle_seoul_avg,
           m.parking_per_vehicle - AVG(m.parking_per_vehicle) OVER () AS parking_per_vehicle_vs_seoul,
           CASE WHEN m.parking_per_vehicle IS NOT NULL THEN RANK() OVER (ORDER BY m.parking_per_vehicle DESC) END AS parking_per_vehicle_rank,
           COUNT(m.parking_per_vehicle) OVER () AS parking_per_vehicle_seoul_count,
           AVG(m.charger_per_electric_vehicle) OVER () AS charger_per_electric_vehicle_seoul_avg,
           m.charger_per_electric_vehicle - AVG(m.charger_per_electric_vehicle) OVER () AS charger_per_electric_vehicle_vs_seoul,
           CASE WHEN m.charger_per_electric_vehicle IS NOT NULL THEN RANK() OVER (ORDER BY m.charger_per_electric_vehicle DESC) END AS charger_per_electric_vehicle_rank,
           COUNT(m.charger_per_electric_vehicle) OVER () AS charger_per_electric_vehicle_seoul_count,
           AVG(m.transit_passenger_per_resident) OVER () AS transit_passenger_per_resident_seoul_avg,
           m.transit_passenger_per_resident - AVG(m.transit_passenger_per_resident) OVER () AS transit_passenger_per_resident_vs_seoul,
           CASE WHEN m.transit_passenger_per_resident IS NOT NULL THEN RANK() OVER (ORDER BY m.transit_passenger_per_resident DESC) END AS transit_passenger_per_resident_rank,
           COUNT(m.transit_passenger_per_resident) OVER () AS transit_passenger_per_resident_seoul_count,
           CASE WHEN COUNT(*) OVER ()=25 AND SUM(CASE WHEN m.parking_per_vehicle IS NULL OR m.charger_per_electric_vehicle IS NULL OR m.vehicle_per_household IS NULL OR m.parking_per_vehicle<0 OR m.charger_per_electric_vehicle<0 OR m.vehicle_per_household<0 THEN 1 ELSE 0 END) OVER ()=0 THEN 1 ELSE 0 END AS score_ready,
           100e0 * (RANK() OVER (ORDER BY m.parking_per_vehicle) + (COUNT(*) OVER (PARTITION BY m.parking_per_vehicle) - 1) / 2e0 - 1) / 24e0 AS parking_percentile_candidate,
           100e0 * (RANK() OVER (ORDER BY m.charger_per_electric_vehicle) + (COUNT(*) OVER (PARTITION BY m.charger_per_electric_vehicle) - 1) / 2e0 - 1) / 24e0 AS charging_percentile_candidate,
           100e0 - (100e0 * (RANK() OVER (ORDER BY m.vehicle_per_household) + (COUNT(*) OVER (PARTITION BY m.vehicle_per_household) - 1) / 2e0 - 1) / 24e0) AS registration_percentile_candidate
    FROM metrics m
)
, scored AS (
    SELECT w.region_id,
           w.district_name,
           w.stat_month,
           w.vehicle_count,
           w.electric_count,
           w.population,
           w.household_count,
           w.vehicle_per_household,
           w.electric_share_pct,
           w.listed_row_count,
           w.identifier_conflict_count,
           w.unique_space_count,
           w.missing_space_count,
           w.unique_missing_space_count,
           w.public_row_count,
           w.private_row_count,
           w.listed_count,
           w.listed_station_count,
           w.restriction_noted_count,
           w.restriction_unknown_count,
           w.fast_count,
           w.slow_count,
           w.unknown_count,
           w.parking_per_vehicle,
           w.charger_per_electric_vehicle,
           w.parking_snapshot_id,
           w.charger_snapshot_id,
           w.need_stat_date,
           w.need_analysis_type,
           w.transit_passenger_count,
           w.transit_observed_hour_count,
           w.transit_complete_hour_count,
           w.transit_min_valid_dong_count,
           w.transit_expected_dong_count,
           w.transit_passenger_per_resident,
           w.vehicle_count_seoul_avg,
           w.vehicle_count_vs_seoul,
           w.vehicle_count_rank,
           w.vehicle_count_seoul_count,
           w.vehicle_per_household_seoul_avg,
           w.vehicle_per_household_vs_seoul,
           w.vehicle_per_household_rank,
           w.vehicle_per_household_seoul_count,
           w.electric_count_seoul_avg,
           w.electric_count_vs_seoul,
           w.electric_count_rank,
           w.electric_count_seoul_count,
           w.electric_share_pct_seoul_avg,
           w.electric_share_pct_vs_seoul,
           w.electric_share_pct_rank,
           w.electric_share_pct_seoul_count,
           w.listed_row_count_seoul_avg,
           w.listed_row_count_vs_seoul,
           w.listed_row_count_rank,
           w.listed_row_count_seoul_count,
           w.unique_space_count_seoul_avg,
           w.unique_space_count_vs_seoul,
           w.unique_space_count_rank,
           w.unique_space_count_seoul_count,
           w.listed_count_seoul_avg,
           w.listed_count_vs_seoul,
           w.listed_count_rank,
           w.listed_count_seoul_count,
           w.listed_station_count_seoul_avg,
           w.listed_station_count_vs_seoul,
           w.listed_station_count_rank,
           w.listed_station_count_seoul_count,
           w.fast_count_seoul_avg,
           w.fast_count_vs_seoul,
           w.fast_count_rank,
           w.fast_count_seoul_count,
           w.slow_count_seoul_avg,
           w.slow_count_vs_seoul,
           w.slow_count_rank,
           w.slow_count_seoul_count,
           w.parking_per_vehicle_seoul_avg,
           w.parking_per_vehicle_vs_seoul,
           w.parking_per_vehicle_rank,
           w.parking_per_vehicle_seoul_count,
           w.charger_per_electric_vehicle_seoul_avg,
           w.charger_per_electric_vehicle_vs_seoul,
           w.charger_per_electric_vehicle_rank,
           w.charger_per_electric_vehicle_seoul_count,
           w.transit_passenger_per_resident_seoul_avg,
           w.transit_passenger_per_resident_vs_seoul,
           w.transit_passenger_per_resident_rank,
           w.transit_passenger_per_resident_seoul_count,
           CASE WHEN w.score_ready=1 THEN w.parking_percentile_candidate END AS parking_percentile,
           CASE WHEN w.score_ready=1 THEN w.charging_percentile_candidate END AS charging_percentile,
           CASE WHEN w.score_ready=1 THEN w.registration_percentile_candidate END AS registration_percentile,
           CASE WHEN w.score_ready=1 THEN w.parking_percentile_candidate * 0.3333333333333333 + w.charging_percentile_candidate * 0.3333333333333333 + w.registration_percentile_candidate * 0.3333333333333333 END AS score_raw
    FROM metric_windows w
)
, ranked_metrics AS (
    SELECT s.region_id,
           s.district_name,
           s.stat_month,
           s.vehicle_count,
           s.electric_count,
           s.population,
           s.household_count,
           s.vehicle_per_household,
           s.electric_share_pct,
           s.listed_row_count,
           s.identifier_conflict_count,
           s.unique_space_count,
           s.missing_space_count,
           s.unique_missing_space_count,
           s.public_row_count,
           s.private_row_count,
           s.listed_count,
           s.listed_station_count,
           s.restriction_noted_count,
           s.restriction_unknown_count,
           s.fast_count,
           s.slow_count,
           s.unknown_count,
           s.parking_per_vehicle,
           s.charger_per_electric_vehicle,
           s.parking_snapshot_id,
           s.charger_snapshot_id,
           s.need_stat_date,
           s.need_analysis_type,
           s.transit_passenger_count,
           s.transit_observed_hour_count,
           s.transit_complete_hour_count,
           s.transit_min_valid_dong_count,
           s.transit_expected_dong_count,
           s.transit_passenger_per_resident,
           s.vehicle_count_seoul_avg,
           s.vehicle_count_vs_seoul,
           s.vehicle_count_rank,
           s.vehicle_count_seoul_count,
           s.vehicle_per_household_seoul_avg,
           s.vehicle_per_household_vs_seoul,
           s.vehicle_per_household_rank,
           s.vehicle_per_household_seoul_count,
           s.electric_count_seoul_avg,
           s.electric_count_vs_seoul,
           s.electric_count_rank,
           s.electric_count_seoul_count,
           s.electric_share_pct_seoul_avg,
           s.electric_share_pct_vs_seoul,
           s.electric_share_pct_rank,
           s.electric_share_pct_seoul_count,
           s.listed_row_count_seoul_avg,
           s.listed_row_count_vs_seoul,
           s.listed_row_count_rank,
           s.listed_row_count_seoul_count,
           s.unique_space_count_seoul_avg,
           s.unique_space_count_vs_seoul,
           s.unique_space_count_rank,
           s.unique_space_count_seoul_count,
           s.listed_count_seoul_avg,
           s.listed_count_vs_seoul,
           s.listed_count_rank,
           s.listed_count_seoul_count,
           s.listed_station_count_seoul_avg,
           s.listed_station_count_vs_seoul,
           s.listed_station_count_rank,
           s.listed_station_count_seoul_count,
           s.fast_count_seoul_avg,
           s.fast_count_vs_seoul,
           s.fast_count_rank,
           s.fast_count_seoul_count,
           s.slow_count_seoul_avg,
           s.slow_count_vs_seoul,
           s.slow_count_rank,
           s.slow_count_seoul_count,
           s.parking_per_vehicle_seoul_avg,
           s.parking_per_vehicle_vs_seoul,
           s.parking_per_vehicle_rank,
           s.parking_per_vehicle_seoul_count,
           s.charger_per_electric_vehicle_seoul_avg,
           s.charger_per_electric_vehicle_vs_seoul,
           s.charger_per_electric_vehicle_rank,
           s.charger_per_electric_vehicle_seoul_count,
           s.transit_passenger_per_resident_seoul_avg,
           s.transit_passenger_per_resident_vs_seoul,
           s.transit_passenger_per_resident_rank,
           s.transit_passenger_per_resident_seoul_count,
           s.parking_percentile,
           s.charging_percentile,
           s.registration_percentile,
           s.score_raw,
           ROUND(s.score_raw,1) AS score,
           CASE WHEN s.score_raw IS NOT NULL THEN RANK() OVER (ORDER BY s.score_raw DESC) END AS score_rank,
           CASE WHEN s.score_raw IS NULL THEN '자료 부족' WHEN s.score_raw>=70 THEN '권장' WHEN s.score_raw>=40 THEN '조건 확인' ELSE '보류' END AS judgment,
           CASE WHEN s.score_raw IS NULL THEN '25구 공통 지표에 결측·잘못된 분모가 있어 백분위를 계산하지 않음' ELSE '수록자료에 따른 추정 참고판정. 실제 주차·충전 난도 또는 구매 필요를 확정하지 않음' END AS score_reason,
           'listed_equal_v3' AS model_version,
           s.parking_per_vehicle AS parking_space_per_vehicle,
           s.vehicle_per_household AS ownership_value,
           s.vehicle_per_household_rank AS ownership_rank,
           CASE WHEN s.vehicle_per_household IS NULL THEN '자료 없음' WHEN s.vehicle_per_household_rank<=8 THEN '많은 편' WHEN s.vehicle_per_household_rank<=17 THEN '보통' ELSE '적은 편' END AS ownership_level,
           s.parking_per_vehicle AS parking_value,
           s.parking_per_vehicle_rank AS parking_rank,
           CASE WHEN s.parking_per_vehicle IS NULL THEN '자료 없음' WHEN s.parking_per_vehicle_rank<=8 THEN '좋음' WHEN s.parking_per_vehicle_rank<=17 THEN '보통' ELSE '빠듯함' END AS parking_level,
           s.transit_passenger_per_resident AS need_value,
           s.transit_passenger_per_resident_rank AS need_rank,
           CASE WHEN s.transit_passenger_per_resident IS NULL THEN '자료 없음' WHEN s.transit_passenger_per_resident_rank<=8 THEN '대중교통으로 충분' WHEN s.transit_passenger_per_resident_rank<=17 THEN '있으면 편함' ELSE '차가 필요한 편' END AS need_level
    FROM scored s
)

SELECT region_id, district_name, stat_month, vehicle_count,
       electric_count, population, household_count, vehicle_per_household,
       electric_share_pct, listed_row_count, identifier_conflict_count, unique_space_count,
       missing_space_count, unique_missing_space_count, public_row_count, private_row_count,
       listed_count, listed_station_count, restriction_noted_count, restriction_unknown_count,
       fast_count, slow_count, unknown_count, parking_per_vehicle,
       charger_per_electric_vehicle, parking_snapshot_id, charger_snapshot_id, need_stat_date,
       need_analysis_type, transit_passenger_count, transit_observed_hour_count, transit_complete_hour_count,
       transit_min_valid_dong_count, transit_expected_dong_count, transit_passenger_per_resident, vehicle_count_seoul_avg,
       vehicle_count_vs_seoul, vehicle_count_rank, vehicle_count_seoul_count, vehicle_per_household_seoul_avg,
       vehicle_per_household_vs_seoul, vehicle_per_household_rank, vehicle_per_household_seoul_count, electric_count_seoul_avg,
       electric_count_vs_seoul, electric_count_rank, electric_count_seoul_count, electric_share_pct_seoul_avg,
       electric_share_pct_vs_seoul, electric_share_pct_rank, electric_share_pct_seoul_count, listed_row_count_seoul_avg,
       listed_row_count_vs_seoul, listed_row_count_rank, listed_row_count_seoul_count, unique_space_count_seoul_avg,
       unique_space_count_vs_seoul, unique_space_count_rank, unique_space_count_seoul_count, listed_count_seoul_avg,
       listed_count_vs_seoul, listed_count_rank, listed_count_seoul_count, listed_station_count_seoul_avg,
       listed_station_count_vs_seoul, listed_station_count_rank, listed_station_count_seoul_count, fast_count_seoul_avg,
       fast_count_vs_seoul, fast_count_rank, fast_count_seoul_count, slow_count_seoul_avg,
       slow_count_vs_seoul, slow_count_rank, slow_count_seoul_count, parking_per_vehicle_seoul_avg,
       parking_per_vehicle_vs_seoul, parking_per_vehicle_rank, parking_per_vehicle_seoul_count, charger_per_electric_vehicle_seoul_avg,
       charger_per_electric_vehicle_vs_seoul, charger_per_electric_vehicle_rank, charger_per_electric_vehicle_seoul_count, transit_passenger_per_resident_seoul_avg,
       transit_passenger_per_resident_vs_seoul, transit_passenger_per_resident_rank, transit_passenger_per_resident_seoul_count, parking_percentile,
       charging_percentile, registration_percentile, score_raw, score,
       score_rank, judgment, score_reason, model_version,
       parking_space_per_vehicle, ownership_value, ownership_rank, ownership_level,
       parking_value, parking_rank, parking_level, need_value,
       need_rank, need_level
FROM ranked_metrics
 ORDER BY district_name;
```

</details>

**조회 예시:** 25행·106열, 구 이름순. 마포구 등록 120,231대, 세대당 약 0.666159대, 수록 주차면 3,080면이다. 마포구는 보유 16위 `보통`, 주차 12위 `보통`, 주민당 승객 6위 `대중교통으로 충분`이다. 강남구는 보유 2위 `많은 편`, 주차 11위 `보통`, 주민당 승객 3위 `대중교통으로 충분`이다.

보조 종합점수는 주차·충전·등록 3축의 평균순위 백분위를 각 1/3로 합친 값이다. 조회 결과에는 남아 있지만 현재 25구 순위·두 동네 비교 화면에는 표시하지 않는다. 세 판정의 3등분과 계산 규칙이 다르며 세 판정을 대신하지 않는다. 주차·충전은 클수록, 등록은 작을수록 보조 점수가 높다. 25구 공통 3축이 모두 유효할 때만 계산한다. 반올림 전 70·40 경계로 `권장/조건 확인/보류`를 나누고 결측은 `자료 부족`이다.

## 2. 한 구의 차종별 전체 등록·전기차

대응 함수는 `get_registration_breakdown(13, date(2026, 9, 1))`이다. 차량 보유의 기초값을 차종·연료 범위별로 확인한다. SQL 1의 등록 합계는 각 연료 범위에서 필수 4차종이 모두 있어야 제공한다.

```sql
WITH ranked_snapshot AS (
    SELECT snapshot_id, source_code,
           ROW_NUMBER() OVER (PARTITION BY source_code ORDER BY collected_on DESC, snapshot_id DESC) AS source_rank
    FROM source_snapshot WHERE is_complete=1
), latest_snapshot AS (
    SELECT snapshot_id, source_code FROM ranked_snapshot WHERE source_rank=1
)

, chosen_month AS (
    SELECT COALESCE('2026-09-01', MAX(r.stat_month)) AS stat_month
    FROM registration r JOIN source_snapshot s ON s.snapshot_id=r.source_snapshot_id AND s.is_complete=1
)

        SELECT r.region_id, g.district_name, r.stat_month, r.vehicle_type_code, v.vehicle_type_name,
               r.fuel_scope_code, f.fuel_scope_name, r.vehicle_count
        FROM registration r JOIN region g ON g.region_id=r.region_id
        JOIN source_snapshot s ON s.snapshot_id=r.source_snapshot_id AND s.is_complete=1
        JOIN vehicle_type v ON v.vehicle_type_code=r.vehicle_type_code
        JOIN fuel_scope f ON f.fuel_scope_code=r.fuel_scope_code
        JOIN chosen_month m ON m.stat_month=r.stat_month
        WHERE (0=1 OR r.region_id IN (13))
        ORDER BY g.district_name, r.fuel_scope_code, r.vehicle_type_code;
```

**조회 예시:** 마포구 8행, 4차종 × 2연료 범위. `all` 합계 120,231대, `electric` 합계 5,075대다. 전기차는 전체 등록 안에 포함되므로 `all`과 `electric`을 더하지 않는다. `bus`의 등록 차종명은 승합차다.

## 3. 충전소·충전기 속도별 집계

대응 함수는 `get_charger_summary([13], speed='all')`이다. 충전기마다 한 행인 `charger`에서 기기 수를 세고 `COUNT(DISTINCT station_id)`로 충전소 운영묶음 수를 센다. 운영기관이 다른 충전소 묶음은 같은 장소라도 별개일 수 있다. 같은 속도 조건을 기기·충전소·제한 안내·속도별 집계에 모두 적용한다.

```sql
WITH ranked_snapshot AS (
    SELECT snapshot_id, source_code,
           ROW_NUMBER() OVER (PARTITION BY source_code ORDER BY collected_on DESC, snapshot_id DESC) AS source_rank
    FROM source_snapshot WHERE is_complete=1
), latest_snapshot AS (
    SELECT snapshot_id, source_code FROM ranked_snapshot WHERE source_rank=1
)

, charging AS (
    SELECT t.region_id, COUNT(*) AS listed_count, COUNT(DISTINCT t.station_id) AS listed_station_count,
           SUM(c.restriction_note IS NOT NULL) AS restriction_noted_count,
           SUM(c.restriction_note IS NULL) AS restriction_unknown_count,
           SUM(c.speed_code='fast') AS fast_count, SUM(c.speed_code='slow') AS slow_count,
           SUM(c.speed_code='unknown') AS unknown_count
    FROM charging_station t JOIN latest_snapshot s ON s.snapshot_id=t.source_snapshot_id
    JOIN charger c ON c.station_id=t.station_id
    WHERE s.source_code='keco_ev_charger' AND ('all'='all' OR c.speed_code='all')
    GROUP BY t.region_id
)

        SELECT g.region_id, g.district_name, 'all' AS speed_code, s.snapshot_id AS source_snapshot_id,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.listed_count,0) END AS listed_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.listed_station_count,0) END AS listed_station_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.restriction_noted_count,0) END AS restriction_noted_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.restriction_unknown_count,0) END AS restriction_unknown_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.fast_count,0) END AS fast_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.slow_count,0) END AS slow_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(c.unknown_count,0) END AS unknown_count
        FROM region g LEFT JOIN charging c ON c.region_id=g.region_id
        LEFT JOIN latest_snapshot s ON s.source_code='keco_ev_charger'
        WHERE (0=1 OR g.region_id IN (13)) ORDER BY g.district_name;
```

**조회 예시:** 1행. 마포구 충전소 운영묶음 622곳·기기 3,518기이며 급속 226기·완속 3,260기·미상 32기다. 이용제한 안내 있음 2,600기, 안내 미상 918기다. 안내 없음은 자유 이용 가능을 뜻하지 않는다.

| `speed` 값 | 기기 수 | 충전소 운영묶음 수 |
| --- | --- | --- |
| `all` | 3,518기 | 622곳 |
| `fast` | 226기 | 93곳 |
| `slow` | 3,260기 | 554곳 |
| `unknown` | 32기 | 4곳 |

표의 나머지 행은 같은 함수에 해당 `speed`를 넣은 결과다. SQL로 바꿀 때는 반환 `speed_code`, 속도 조건의 왼쪽 선택값, `c.speed_code`와 비교할 선택값을 함께 바꾸고 전체 허용 조건의 오른쪽 상수 `'all'`은 유지한다.

급속·완속은 커넥터 기준 추정이며 빈자리 수가 아니다. 서로 다른 속도의 기기가 한 운영묶음에 함께 있을 수 있으므로 속도별 충전소 수를 더하지 않는다. 환경공단 75,607기와 별도 출처인 서울 공공 429기도 합치지 않는다. 유효 수집본이 없으면 집계는 NULL, 수집본은 있지만 선택 속도 기기가 없으면 0이다.

## 4. 주차 기록과 공영·민영 주차면 집계

대응 함수는 `get_parking_summary([13])`이다. 관리번호 충돌행을 기록 수에는 남기고 면수 계산에서 제외한다. `public_row_count`·`private_row_count`는 공영·민영 **관측행 수**이며 면수가 아니다. 공영·민영·기타 면수는 `public_space_count`·`private_space_count`·`other_space_count`로 따로 반환한다.

```sql
WITH ranked_snapshot AS (
    SELECT snapshot_id, source_code,
           ROW_NUMBER() OVER (PARTITION BY source_code ORDER BY collected_on DESC, snapshot_id DESC) AS source_rank
    FROM source_snapshot WHERE is_complete=1
), latest_snapshot AS (
    SELECT snapshot_id, source_code FROM ranked_snapshot WHERE source_rank=1
)

, parking AS (
    SELECT p.region_id, COUNT(*) AS listed_row_count,
           SUM(p.identifier_status='conflict') AS identifier_conflict_count,
           SUM(CASE WHEN p.identifier_status='unique' THEN p.space_count END) AS unique_space_count,
           SUM(p.space_count IS NULL) AS missing_space_count,
           SUM(p.identifier_status='unique' AND p.space_count IS NULL) AS unique_missing_space_count,
           SUM(p.parking_operation='공영') AS public_row_count,
           SUM(p.parking_operation='민영') AS private_row_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='공영' THEN p.space_count ELSE 0 END) AS public_known_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='민영' THEN p.space_count ELSE 0 END) AS private_known_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND COALESCE(p.parking_operation,'') NOT IN ('공영','민영') THEN p.space_count ELSE 0 END) AS other_known_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='공영' AND p.space_count IS NULL THEN 1 ELSE 0 END) AS public_missing_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND p.parking_operation='민영' AND p.space_count IS NULL THEN 1 ELSE 0 END) AS private_missing_space_count,
           SUM(CASE WHEN p.identifier_status='unique' AND COALESCE(p.parking_operation,'') NOT IN ('공영','민영') AND p.space_count IS NULL THEN 1 ELSE 0 END) AS other_missing_space_count
    FROM parking_site p JOIN latest_snapshot s ON s.snapshot_id=p.source_snapshot_id
    WHERE s.source_code='parking_standard' GROUP BY p.region_id
)

        SELECT g.region_id, g.district_name, s.snapshot_id AS source_snapshot_id,
               p.listed_row_count, p.identifier_conflict_count, p.unique_space_count,
               p.missing_space_count, p.unique_missing_space_count, p.public_row_count, p.private_row_count,
               CASE WHEN s.snapshot_id IS NOT NULL AND COALESCE(p.public_missing_space_count,0)=0 THEN COALESCE(p.public_known_space_count,0) END AS public_space_count,
               CASE WHEN s.snapshot_id IS NOT NULL AND COALESCE(p.private_missing_space_count,0)=0 THEN COALESCE(p.private_known_space_count,0) END AS private_space_count,
               CASE WHEN s.snapshot_id IS NOT NULL AND COALESCE(p.other_missing_space_count,0)=0 THEN COALESCE(p.other_known_space_count,0) END AS other_space_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(p.public_missing_space_count,0) END AS public_missing_space_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(p.private_missing_space_count,0) END AS private_missing_space_count,
               CASE WHEN s.snapshot_id IS NOT NULL THEN COALESCE(p.other_missing_space_count,0) END AS other_missing_space_count
        FROM region g LEFT JOIN parking p ON p.region_id=g.region_id
        LEFT JOIN latest_snapshot s ON s.source_code='parking_standard'
        WHERE (0=1 OR g.region_id IN (13)) ORDER BY g.district_name;
```

**조회 예시:** 1행. 마포구 관측행 31개, 번호 충돌 0행, 비충돌 수록 주차면 3,080면, 면수 결측 0행이다. 공영 3,080면·민영 0면·기타 0면이며 공영 관측행은 31개다.

`unique_space_count`는 알려진 비충돌 면수의 부분합이다. 공영·민영·기타 면수는 해당 유형에 결측이 하나라도 있으면 NULL이며, 유효 수집본에 해당 유형 자체가 없으면 0이다. 수집본이 없으면 자료 없음이다. 관측행 수와 부분합에는 이를 임의로 0으로 채우는 규칙을 적용하지 않는다.

SQL 1의 `parking_per_vehicle`는 비충돌 면수 결측이 없고 등록 차량 수가 0보다 클 때만 계산한다. 마포구는 약 0.025617면/대, 차량 100대당 약 2.56면이며 현재 카드에는 소수 한 자리인 **2.6면**으로 표시된다. 수록 면수는 구 전체 주차 공급이나 실제 빈자리가 아니다. Python에서 배수를 표시할 때 다운캐스트 정수 컬럼을 먼저 `astype("int64")`로 넓힌다.

## 5. 전국 등록 조회

대응 함수는 `get_national_registrations(date(2026, 9, 1))`이다. 시도·차종·용도 조건은 모두 `None`이다. 실제 함수는 이 조건을 **SQL WHERE에서 처리**하며, 조건이 비어 있을 때만 전체를 반환한다.

```sql
WITH chosen_month AS (
    SELECT COALESCE('2026-09-01', MAX(p.stat_month)) AS stat_month FROM province_registration p
    JOIN source_snapshot s ON s.snapshot_id=p.source_snapshot_id AND s.is_complete=1
)
SELECT p.province_name, p.stat_month, p.vehicle_type_code, v.vehicle_type_name, p.usage_code, p.vehicle_count
FROM province_registration p JOIN vehicle_type v ON v.vehicle_type_code=p.vehicle_type_code
JOIN source_snapshot s ON s.snapshot_id=p.source_snapshot_id AND s.is_complete=1
JOIN chosen_month m ON m.stat_month=p.stat_month
WHERE (NULL IS NULL OR p.province_name=NULL)
  AND (NULL IS NULL OR p.vehicle_type_code=NULL) AND (NULL IS NULL OR p.usage_code=NULL)
ORDER BY p.province_name, p.vehicle_type_code, p.usage_code;
```

**조회 예시:** 192행, 수록 등록 합계 26,706,123대. 원본의 16개 시도 표기 × 4차종 × 3용도다. 원본에 `전남광주`가 포함되어 있으므로 임의로 두 지역으로 나누거나 없는 시도 행을 만들지 않는다. 서울 25구 판정과는 별도 조회다.

## 6. 기업 FAQ 검색

대응 함수는 `search_faq('충전', company_id=None, category=None, limit=50)`이다. 질문·답변의 포함 검색에 기업·분류 조건과 결과 수 제한을 함께 적용한다.

```sql
SELECT c.company_id, c.company_name, f.faq_key, f.category, f.question, f.answer_text, f.source_url,
       s.collected_on AS fetched_on
FROM faq f JOIN company c ON c.company_id=f.company_id
JOIN source_snapshot s ON s.snapshot_id=f.source_snapshot_id AND s.is_complete=1
WHERE (NULL IS NULL OR c.company_id=NULL) AND (NULL IS NULL OR f.category=NULL)
  AND (f.question LIKE '%충전%' ESCAPE '!' OR f.answer_text LIKE '%충전%' ESCAPE '!')
ORDER BY c.company_id, f.faq_key LIMIT 50;
```

**조회 예시:** 5행, 모두 현대자동차 FAQ다. 검색어가 빈 문자열이면 수록 문항 10개가 반환된다. 기업명·원문 링크·수집일도 함께 조회하지만 원문 답변을 공개 레포에 복제하지 않는다.

`_like_pattern()`은 사용자 검색어의 `!`, `%`, `_`를 이스케이프하여 문자 그대로 찾고, SQL은 `ESCAPE '!'`를 사용한다. 검색어는 500자 이내이고 `limit`은 1–100이다. `None`인 기업·분류 조건은 전체를 의미한다.

## 7. 서울 구 경계 조회

대응 함수는 `get_region_boundaries()`다. 최신 유효 `kostat_seoul_boundary` 수집본을 골라 구 이름순으로 조회한다. `region_boundary.region_id`는 PK이자 `region`을 참조하는 FK이며 구마다 경계 한 행을 연결한다.

```sql
WITH ranked_snapshot AS (
    SELECT snapshot_id, source_code,
           ROW_NUMBER() OVER (PARTITION BY source_code ORDER BY collected_on DESC, snapshot_id DESC) AS source_rank
    FROM source_snapshot WHERE is_complete=1
), latest_snapshot AS (
    SELECT snapshot_id, source_code FROM ranked_snapshot WHERE source_rank=1
)

        SELECT b.region_id, g.district_name, b.geometry_json, b.centroid_latitude, b.centroid_longitude,
               b.min_latitude, b.max_latitude, b.min_longitude, b.max_longitude,
               b.boundary_year, b.ring_count, b.source_snapshot_id
        FROM region_boundary b JOIN region g ON g.region_id=b.region_id
        JOIN latest_snapshot s ON s.snapshot_id=b.source_snapshot_id
        WHERE s.source_code='kostat_seoul_boundary' ORDER BY g.district_name;
```

**조회 예시:** 25행·12열, `boundary_year`는 모두 2013이다. 현재 도형은 모두 Polygon이며 `ring_count`는 구별 1개다. `geometry_json`의 좌표 순서는 `[경도, 위도]`다. 2013년 경계는 지도 표시 전용이며 세 판정과 보조 점수 계산에 쓰지 않는다.

## 관련 자료

조회 결과의 수치는 이 문서의 수집본 기준이며 자료가 갱신되면 달라질 수 있다. 전체 구현은 [조회 코드](../db/queries.py), 테이블·행 수는 [DB 설계 문서](db_design.md), 보조점수의 기준 구현은 [scoring.py](../scoring.py)에서 확인한다.
