# 차차차 데이터베이스 설계 문서

SKN 5팀 · 2026-11-09 · 공식 과제: **전국 자동차 등록 현황 및 기업 FAQ 조회시스템**

차차차는 서울 25개 구의 **차량 보유 현황, 주차하기 좋은 동네, 차가 꼭 필요한 동네**를 각각 비교한다. 전국 자동차 등록과 기업 FAQ도 별도로 조회한다. 서비스 이름은 차차차이며 현재 DB 이름은 `chachacha`다.

실행 DB는 **18표·136열·111,676행**, 제약은 **PK 18개·FK 25개·UNIQUE 8개·CHECK 47개**이고 뷰는 없다. UNIQUE 수는 PK를 제외한 값이다. 정의와 구현은 [DDL](../db/sql/schema.sql), [조회 코드](../db/queries.py)를 따른다. 앱의 메뉴와 사용 방법은 [화면·실행 안내](../README.md)에 정리했다.

DB 덤프·정제 CSV·수집 원본은 팀 내부에서 관리하고 **공개 레포에 올리지 않는다**. 공개 산출물은 코드·스키마·출처 기록으로 한정한다. 파일의 공개 가능 여부를 `.gitignore` 등록 여부만으로 판단하지 않는다. 출처와 수록 범위는 [데이터 출처](../data/SOURCES.md)를 따른다.

## 1. 개념적 설계

| 질문 | 설계의 답 |
| --- | --- |
| 어떤 대상이 있는가? | 지역, 차량 등록, 주차장 관측행, 충전소·충전기, 기업·FAQ, 교통·승객·날씨, 출처 수집본이다. |
| 왜 함께 모으는가? | 서로 다른 기관의 자료를 같은 구 번호로 연결하고, 기준일과 빠진 자료를 보존한 채 비교하기 위해서다. |
| 대상마다 무엇을 기록하는가? | 등록에는 월·차종·범위·대수, 시설에는 위치·면수 또는 속도·용량·이용시간, FAQ에는 질문·답변·출처, 시간자료에는 관측 시점·관측 범위가 있다. |
| 대상은 어떻게 연결되는가? | 구는 등록·주차·충전·시간자료와 연결되고, 충전소는 기기와, 기업은 FAQ와 연결된다. 수집 데이터는 직접 또는 부모 표를 통해 출처 수집본을 참조한다. |
| 1:n과 n:m 관계는 무엇인가? | 한 구에 여러 주차 관측행, 한 충전소에 여러 기기, 한 기업에 여러 FAQ가 있다. 구와 차종의 n:m은 월·연료범위를 가진 `registration`으로 풀어 두 개의 1:n 관계로 표현한다. |

전국 시도와 서울 구는 단위가 달라 각각 `province_registration`과 `region`·`registration`으로 나눈다. `region`에는 서울 25개 구만 들어간다. 개인의 실제 주소·차량 소유 정보를 저장하는 표는 없다.

### 정식 앱과 조회의 연결

시작점은 [app.py](../app.py)이며 `app_pages/`의 네 화면을 연결한다. [site_shell.py](../site_shell.py)는 공통 navbar의 메뉴·동네 선택, 홈 hero와 나머지 페이지 머리말, footer의 출처 안내를 맡고 `assets/`의 로고·자동차 세 대 그림을 사용한다. [ui.py](../ui.py)는 세 칸 판정·지도·한눈에 읽는 우리 동네·클릭하는 25구 막대 순위·표시 단위를 맡는다. [details.py](../details.py)는 홈에서 자세한 자료를 펼쳤을 때만 해당 자료를 조회한다.

| 화면 | 입력 → 결과 | 주요 조회·테이블 |
| --- | --- | --- |
| [우리 동네](screens/01_home.png), [모바일](screens/05_home_mobile.png) | Navbar·지도·막대 행에서 구 선택 → 둥근 세 칸의 판정·근거값·동네 요약. 주제 선택 → 지도 색과 서울 25구 막대 순위 | `get_district_ranking`, `get_region_boundaries`; 등록·인구·주차·승객 집계와 `region_boundary` |
| [두 동네 비교](screens/02_compare.png) | 두 구 선택 → 나란한 둥근 카드의 세 판정·근거값 차이·서울 전체 순위 | `get_compare_metrics`, `get_registration_breakdown`; 같은 지표 CTE와 `registration` |
| [전국 등록 조회](screens/03_national.png) | 시도·차종·용도 선택 → 조건별 등록 합계·서울 등록·시도별 막대·등록표. 전체 조건은 16개 시도 이름을 표시하고 서울 막대는 코랄 강조 | `get_national_registrations`; `province_registration`, `vehicle_type` |
| [기업 FAQ](screens/04_faq.png) | 검색어·기업·분류 선택 → 둥근 질문 상자, 펼친 원문 답변·원문 링크·수집일 | `search_faq`; `company`, `faq`, `source_snapshot` |
| 공통 navbar·footer | 네 메뉴 이동·현재 메뉴·동네 선택, 하단의 자료 출처·기준 기간·수집일과 추정 안내 | `get_filter_options`; `region`, 유효한 `source_snapshot`의 `snapshots` |

홈의 `자세한 자료`는 차량 구성, 주차·충전 시설, 시간대별 승객으로 나뉜다. 등록은 `get_summary_metrics`·`get_registration_breakdown`, 시설은 `get_place_points`·`search_places`·`get_charger_summary`·`get_charger_detail`, 승객과 날씨는 `get_trend_data`·`get_weather`로 읽는다. 충전 속도는 요약·지도·목록에 동일하게 적용한다. 주차 목록은 최대 100건, 충전기 목록은 최대 200기이며 지도에서 빠진 좌표 없는 시설도 목록에 남긴다.

세 판정과 서울 전체 순위는 SQL에서 계산한다. 전국 화면의 선택 합계·시도별 막대용 합계는 SQL로 필터링한 결과를 Python에서 더하며 결측이 있으면 확정하지 않는다. 도로 교통량도 DB에 보존하지만 현재 홈의 시간 그래프는 승객만 표시한다. 최신 서울 공통 날씨는 별도로 표시하고 승객과 같은 관측 시각으로 간주하지 않는다.

## 2. 원본 보존과 2NF 정규화

[raw DDL](../db/sql/schema_raw.sql)은 초기 선정 원본의 모양을 보존하는 13표 설계다. raw 표 수, 현재 출처 수집본 11개, 실행 DB 18표는 서로 다른 수다. raw 13표는 현재 조회 DB의 18표에 더하지 않는다. 파일 식별자·원본 행 번호를 보존하고 엑셀처럼 여러 시트가 있으면 시트도 구분한다. 검증되지 않은 원문 구명을 정식 지역 코드로 다루지 않으며, 합계·소계를 상세 행과 다시 더하지 않는다.

2NF는 복합키의 일부에만 의존하는 설명을 별도 표로 옮기는 것이다. 아래는 개념을 설명하는 **가상 예시**이며 실제 수집값이 아니다.

| 분리 전 복합키: 충전소 번호+기기번호 | 충전소 주소 | 기기 용량(kW) |
| --- | --- | --- |
| 101 + 01 | 가 주소 | 100 |
| 101 + 02 | 가 주소 | 7 |
| 102 + 01 | 나 주소 | 50 |

충전소 주소는 기기번호 없이 충전소 번호만으로 정해진다. 이를 그대로 두면 주소를 여러 행에서 고쳐야 하고, 마지막 기기를 삭제할 때 충전소 설명까지 잃을 수 있다.

| 분리 후 `charging_station`의 station_id | 주소 |
| --- | --- |
| 101 | 가 주소 |
| 102 | 나 주소 |

| 분리 후 `charger`의 station_id | source_charger_id | capacity_kw |
| --- | --- | --- |
| 101 | 01 | 100 |
| 101 | 02 | 7 |
| 102 | 01 | 50 |

기기 3행을 보존하면서 주소는 충전소별 한 행에서 관리한다. 기기가 없어도 충전소를 먼저 등록할 수 있으며, 두 표를 `station_id`로 연결하면 원래 정보를 복원한다. 원본 기기번호의 선행 0은 문자열로 보존한다.

실제 기본 환경공단 자료도 **충전소 운영묶음 13,098행과 기기 75,607행**으로 나뉜다. 같은 원본 충전소 ID라도 운영기관이 다르면 다른 운영묶음이다. 등록표의 구명·차종명은 `region`·`vehicle_type`, 구·월로 정해지는 인구·세대는 `region_context`로 분리했다. 가로 열을 세로 행으로 바꾸는 정제, 구별 합산, 자동번호 추가 자체를 정규화라고 설명하지 않는다. 과제의 2NF 목표와 실제 관리 범위를 기준으로 표를 나눴으며 모든 범주를 별도 표로 확장하지는 않았다.

## 3. 실행 18표와 주요 키

PK는 행을 식별하는 기본키, FK는 다른 표를 참조하는 외래키다. 여러 컬럼으로 구성한 키는 복합키다. 컬럼·자료형·NULL·제약은 [실행 DDL](../db/sql/schema.sql)을 따른다.

| 표 | 한 행의 뜻 | 기본키 | 현재 행 수 |
| --- | --- | --- | ---: |
| `source_snapshot` | 출처 수집본의 기간·수집일·해시·유효 여부 | `snapshot_id` | 11 |
| `region` | 서울 구 하나 | `region_id` | 25 |
| `vehicle_type` | 차종 하나 | `vehicle_type_code` | 4 |
| `fuel_scope` | 전체 또는 전기 범위 하나 | `fuel_scope_code` | 2 |
| `registration` | 서울 구·월·차종·연료범위 등록 | `region_id, stat_month, vehicle_type_code, fuel_scope_code` | 200 |
| `province_registration` | 원본 시도·월·차종·용도 등록 | `province_name, stat_month, vehicle_type_code, usage_code` | 192 |
| `region_context` | 구·월별 인구·세대와 출처 | `region_id, stat_month` | 25 |
| `parking_site` | 원본 주차장 관측행 | `parking_row_id` | 857 |
| `charging_station` | 수집본 안의 충전소 운영묶음 | `station_id` | 13,285 |
| `charger` | 충전소 안의 기기 한 대 | `station_id, source_charger_id` | 76,036 |
| `company` | FAQ 제공 기업 | `company_id` | 1 |
| `faq` | 기업의 질문·답변 | `company_id, faq_key` | 10 |
| `traffic_coverage` | 출처·구의 기대 관측 방향 수 | `source_snapshot_id, region_id` | 25 |
| `traffic_snapshot` | 구·시간별 확인된 교통량 부분합 | `source_snapshot_id, region_id, observed_at` | 17,280 |
| `transit_coverage` | 구·날짜·분석유형의 기대 행정동 수 | `source_snapshot_id, region_id, stat_date, analysis_type` | 50 |
| `transit_ridership_snapshot` | 구·날짜·시간·수단별 승객 부분합 | `source_snapshot_id, region_id, stat_date, analysis_type, hour_of_day, mode_code` | 3,600 |
| `weather_snapshot` | 서울 108번 관측소의 시간별 기상 | `source_snapshot_id, observed_at` | 48 |
| `region_boundary` | 구 하나의 지도 경계와 출처 | `region_id` | 25 |

총 **111,676행**이다. 핵심 12표, 시간자료 5표, 지도 경계 1표로 구성된다. `charger`에 보관한 76,036행은 환경공단 75,607행과 서울 공공 429행을 함께 보관한 수이며 실제 고유 기기 수를 뜻하지 않는다. 조회에서는 두 출처를 합산하지 않는다.

### 주요 FK와 무결성

- `registration`은 지역·차종·연료범위·출처를 참조한다. 전국 등록은 차종·출처를 참조한다.
- `charging_station`은 지역·출처를 참조하고 `charger`는 충전소를 참조한다. `(source_snapshot_id, station_key)`는 같은 수집본의 운영묶음 중복을 막는다.
- `faq`는 기업·출처를 참조한다. `company`는 FAQ 기업이며 충전 운영기관 표가 아니다.
- `traffic_snapshot`은 출처+구의 `traffic_coverage`를, `transit_ridership_snapshot`은 출처+구+날짜+분석유형의 `transit_coverage`를 참조한다. 복합 FK 한 개를 연결 컬럼 수만큼 세지 않는다.
- `region_boundary.region_id`는 PK이자 지역 FK다. 한 구에 경계는 최대 한 행이며 현재 25구 모두 연결돼 있다. 경계 25행은 별도의 출처 수집본 한 행을 참조한다.
- CHECK는 월 첫날, 정시 관측, 코드 범위, 양수·결측 규칙, 좌표 범위 등을 검사한다. 대수·면수처럼 음수가 허용되지 않는 값은 UNSIGNED 또는 CHECK로 제한한다.

행정동·교통 관측 지점의 기대 수와 실제 유효 수를 나누어 보관하므로, 값이 작다는 이유만으로 관측 누락을 0으로 해석하지 않는다. `source_snapshot`은 메타정보이고 시설·시간자료는 관측 사실값이다. 점수 저장표와 집계 전용 뷰는 두지 않고 조회 SQL에서 계산한다.

### 지도 경계

[경계 DDL](../db/sql/schema_boundary.sql)은 `region_id, source_snapshot_id, boundary_year, geometry_json, centroid_latitude, centroid_longitude, min_latitude, max_latitude, min_longitude, max_longitude, ring_count`를 정의한다. 모든 열은 NOT NULL이다. 중심·경계 상자의 위경도는 DECIMAL(10,7), 도형은 JSON이다.

`get_region_boundaries()`는 최신 유효 경계 수집본의 25구를 구 이름순으로 반환한다. `geometry_json`은 Polygon 또는 MultiPolygon geometry이며 GeoJSON 좌표 순서는 [**경도, 위도**]다. **2013년 경계, 지도 표시 전용**으로 통계 면적이나 판정 계산에는 사용하지 않는다.

## 4. 세 개의 판정 기준

`get_district_ranking()`, `get_summary_metrics(region_id)`, `get_compare_metrics(region_id_a, region_id_b)`가 같은 기준의 값·순위·라벨을 반환한다. 서울 25구 전체의 순위를 SQL `RANK()`로 계산한 뒤 선택한 구를 고른다. 따라서 두 구만 비교해도 전체 순위가 바뀌지 않는다.

| 질문 | 원지표와 단위 | 반환 컬럼 | 큰 값부터 1–8위 / 9–17위 / 18–25위 |
| --- | --- | --- | --- |
| 차량 보유 현황 | 같은 기준월 등록 대수 ÷ 세대수, 대/세대 | `ownership_value, ownership_rank, ownership_level` | 많은 편 / 보통 / 적은 편 |
| 주차하기 좋은 동네 | 비충돌 수록 주차면 ÷ 전체 등록 대수, 면/대 | `parking_value, parking_rank, parking_level` | 좋음 / 보통 / 빠듯함 |
| 차가 꼭 필요한 동네 | 2026-10-30 하루 수록 대중교통 승객 합 ÷ 선택 등록월 주민 수, 승객/주민 | `need_value, need_rank, need_level` | 대중교통으로 충분 / 있으면 편함 / 차가 필요한 편 |

원지표 이름은 차례로 `vehicle_per_household`, `parking_space_per_vehicle`(같은 값의 `parking_per_vehicle`도 제공), `transit_passenger_per_resident`다. 동률은 같은 순위와 같은 묶음에 들어가며 다음 순위는 건너뛴다. 현재 데이터에서는 세 판정 모두 **8·9·8구**지만, 동률이 생기면 묶음 크기는 달라질 수 있다. 지표가 NULL이면 순위도 NULL, 라벨은 **자료 없음**이다. 차량 보유가 많다는 라벨은 좋고 나쁨의 점수가 아니다.

쉬운 말로 보유는 **한 세대당 차의 수**, 주차는 **등록 차량에 비해 확보된 수록 주차면**, 필요성은 **주민 수에 비해 하루 대중교통 이용이 많은 정도**다. 화면의 주차 단위는 SQL 값에 100을 곱한 **차 100대당 주차면**이며 순위는 그대로다. 차 필요성의 순위는 대중교통 이용 많은 순서다. 승객 값이 낮을수록 차가 필요한 편으로 추정하므로 1위가 필요성이 가장 높다는 뜻은 아니다.

차 필요도는 `mode_code='total'` 행만 합산한다. bus·subway를 다시 더하지 않는다. 최신 유효 승객 수집본의 2026-10-30 분석유형이 하나일 때만 사용하며 현재 코드는 `'4'`다. 24시간 행이나 시간별 합계가 빠졌거나 주민 수가 0이면 필요도는 결측이다. 분석유형이 여러 개면 임의로 합산하지 않는다.

**해석 한계:** 차 필요도는 평일 하루 관측에 따른 팀의 추정 규칙이며 실제 차량 구매 필요를 확정하지 않는다. 중구·종로구는 출퇴근 유입 등 비거주자의 이용이 승객 합에 포함될 수 있어 주민 수로 나눈 값이 커질 수 있다. 주민 한 사람이 실제로 대중교통을 이용한 횟수나 이용자 비율로 읽으면 안 된다. 현재 값은 중구 약 7.0783(1위), 종로구 약 4.6628(2위)다. 이 자료만으로 출퇴근 유입의 효과를 따로 측정하지는 않았다.

또한 **등록·인구·세대의 기준월은 2026-09, 필요도 승객 기준일은 2026-10-30**이다. 강서구는 24시간 합계가 있으나 일부 행정동이 빠진 부분합이다. `transit_complete_hour_count=0`, `transit_observed_hour_count=24`이므로 실제 이용 규모보다 작게 집계될 수 있다는 안내를 함께 사용한다. 관측 동 수는 `transit_min_valid_dong_count`, 기대 동 수는 `transit_expected_dong_count`로 확인한다.

### 보조 종합점수

주차 면/등록 차량, 충전기/전기차, 등록 차량/세대의 세 축을 25구 백분위로 바꿔 각 1/3씩 평균한다. 주차·충전 값은 클수록, 등록 부담은 작을수록 점수가 높다. 동률은 평균 순위를 사용하고 모두 같으면 해당 축은 50점이다. 25구 공통 세 지표가 하나라도 유효하지 않으면 점수는 결측, 보조 판정은 `자료 부족`이다.

반환 점수 `score`는 소수 1자리, `score_raw`는 반올림 전 값이다. 70 이상 권장, 40 이상 70 미만 조건 확인, 40 미만 보류이며 판정은 반올림 전 값으로 정한다. 이 규칙은 [scoring.py](../scoring.py)의 가중치·기준과 일치하도록 **현재 조회 SQL에서 계산**한다. 현재 홈·비교 화면에는 이 종합점수를 표시하지 않고 세 판정을 보여 준다. 세 판정의 RANK 구간과 이 종합점수의 평균순위 백분위를 혼동하지 않는다. 통근·날씨·정류장 값은 보조 종합점수에 들어가지 않는다.

## 5. 수집본·필터·결측 규칙

| 항목 | 조회가 지키는 규칙 |
| --- | --- |
| 유효 수집본 | `is_complete=1`만 사용한다. 시설·시간자료·경계는 출처별 수집일·번호 역순의 최신 수집본을 선택한다. 등록·인구는 선택 기준월과 연결된 유효 자료를 사용한다. |
| 기본 충전 출처 | `keco_ev_charger`가 기본이다. 기본 출처가 없으면 서울 공공 목록으로 바꾸거나 두 출처를 합하지 않는다. 공개 조회 API에는 출처·수집본 ID를 직접 지정하는 인자가 없다. |
| 등록 | 전체와 전기는 서로 더하지 않는다. 범위별 네 차종이 모두 있어야 합계를 확정한다. 전기차가 전체보다 많거나 분모가 0이면 해당 비율은 NULL이다. |
| 주차 | 번호 충돌 22행은 원본에 보존한다. 면수는 `identifier_status='unique'`만 합한다. 공영·민영·기타 면수는 해당 유형이 없으면 0, 면수 결측이 있거나 유효 수집본이 없으면 NULL이다. |
| 주차 판정 | `unique_space_count`의 알려진 부분합은 표시할 수 있지만 비충돌 행의 면수 결측이 있으면 `parking_per_vehicle`를 확정하지 않는다. |
| 지도·검색 | 주차는 저장된 좌표 유효성 조건과 서울 범위를 만족하고 번호가 비충돌이어야 지도에 넣는다. 충전소 대표 좌표는 같은 속도 조건의 기기 한 대에서 한 쌍으로 고른다. 검색은 지도 제외 행도 보존한다. |
| 구 미연결 | 추정 구 번호로 메우지 않는다. 구별 집계·지도에는 연결된 구만 포함한다. |
| 시간자료 | 교통은 9월, 승객·날씨는 10월 30–31일이다. 같은 날 관측처럼 합치지 않는다. `total`과 하위 수단을 중복 합산하지 않으며 NULL 강수·적설을 0으로 바꾸지 않는다. |
| 서울 평균 | SQL `AVG(...) OVER ()`로 결측을 뺀 구별 값의 산술평균을 낸다. 비율의 서울 평균은 서울 총합끼리 나눈 비율과 다르다. 평균 참여 구 수도 함께 반환한다. |
| 입력 안전 | SQLAlchemy `text()`·바인딩을 쓰고 구 목록은 expanding bind로 전달한다. 검색의 `%`, `_`, `!`는 문자 그대로 찾는다. 값으로 SQL 문자열을 조립하지 않는다. |

조회는 [db/queries.py](../db/queries.py)의 공개 함수 15개로 분리했다. 호출자는 연결 객체를 넘기지 않는다. [db/connection.py](../db/connection.py)는 최초 동시 호출에도 Engine 한 개를 만들고, 조회는 context manager로 Connection을 반환한다. 접속 정보는 `st.secrets` 우선·환경변수 폴백이며 값을 로그에 출력하지 않는다. 공개 조회는 600초 캐시를 사용한다.

결과는 DataFrame이고 필터 옵션만 dict다. 표시 값을 보존하면서 category·정수 다운캐스팅을 적용하며 위경도는 float64를 유지한다. 결측은 `pd.isna`로 확인하고 category를 묶을 때는 `groupby(..., observed=True)`를 사용한다. **다운캐스트된 정수 컬럼은 곱하기 전에 `astype("int64")`로 확장한다.** 곱한 뒤 형을 바꾸면 넘친 값이 복구되지 않는다. 결측 정수는 `Int64`, 이미 큰 UInt64·Python int는 계산 결과까지 범위를 확인한다. 전기차 비중은 SQL의 `electric_share_pct`를 그대로 표시한다.

## 6. 현재 수록값과 자료의 한계

| 항목 | 수록값 | 해석 |
| --- | --- | --- |
| 전국 등록 | 26,706,123대 | 원본 16시도 표기×4차종×3용도. `전남광주`를 임의 분할하지 않는다. |
| 서울 전체·전기 등록 | 3,150,351대·127,750대 | 2026-09 한 달. 전월 대비 증감이나 월별 추이를 만들 수 없다. |
| 서울 인구·세대 | 9,279,861명·4,524,905세대 | 등록과 같은 2026-09 기준월이다. |
| 수록 주차 | 857행: 공영 812·민영 45 | 번호 충돌 22행을 제외한 835행의 알려진 면수는 73,068면이다. |
| 공영·민영·기타 비충돌 면수 | 71,919면·1,149면·0면 | 수집 목록의 면수이며 서울 전체 공급량이나 실시간 빈자리가 아니다. |
| 환경공단 충전 | 75,607기: 급속 5,041·완속 69,634·미상 932 | 속도는 커넥터 코드 기반 구분이다. 상태는 수집 당시 값이다. |
| 서울 공공 충전 | 429기: 급속 356·완속 73 | 별도 보관한 출처이며 기본 조회에 합하지 않는다. |
| 교통 | 17,280행 | 9월 24구×30일×24시간. 강북구는 기대 관측 방향 수가 0이다. |
| 승객 | 3,600행 중 일부 동 누락 1,296행 | 25구×2일×24시간×3수단. 부분합·기대 동 수를 함께 읽는다. |
| 날씨 | 48시간, 강수 NULL 46·적설 NULL 48 | 서울 108번 공통 관측이다. 구별 관측값으로 소개하지 않는다. |
| FAQ | 현대 EV 10문항 | 현대자동차 EV 에브리케어 원문을 사용한다. |

자료에 없는 충전 가격, 실제 빈자리, 주차 요금·감면 정보를 만들어 내지 않는다. 정류장 참고 컬럼은 현재 NULL이며 세 판정과 보조 종합점수에 사용하지 않는다.

## 7. DDL 구성과 확인 방법

| 파일 | 역할 |
| --- | --- |
| [schema.sql](../db/sql/schema.sql) | 경계를 포함한 현재 실행 18표의 전체 정의 |
| [schema_core.sql](../db/sql/schema_core.sql) | 초기 핵심 12표 |
| [schema_active_ext.sql](../db/sql/schema_active_ext.sql) | 시간자료 5표와 충전소·기기 표의 추가 12열 |
| [schema_ext.sql](../db/sql/schema_ext.sql) | 같은 확장 범위의 파일. 중복 적용하지 않는다. |
| [schema_boundary.sql](../db/sql/schema_boundary.sql) | 지도 경계 1표 |
| [schema_raw.sql](../db/sql/schema_raw.sql) | 앱 DB와 별도인 초기 원본 보존 13표 설계 |

`parking_profile`, `public_parking_site`, `parking_guidance`는 주석 처리된 정의이며 물리 DB에 없다. SQL은 MySQL 8.0 문법 범위이며 CHECK 강제는 8.0.16 이상을 전제로 한다. 개발 환경의 MySQL 버전 문자열은 26.10.0이다.

데이터가 적재된 DB와 접속 설정이 준비되면 프로젝트 루트의 가상환경으로 조회 검사를 실행한다.

```bash
.venv/bin/python -m db.self_check --report-dir /private/tmp/chachacha-db-check
.venv/bin/python -m unittest discover tests
.venv/bin/python -m unittest discover test
```

앱 실행 및 폴더 설명은 [실행 안내](../README.md), 대표 조회는 [SQL 예제](sql_showcase.md)를 따른다. 보고서 경로를 `/private/tmp`로 지정한 첫 명령은 조회 검산 기록만 임시 폴더에 저장한다. DB 초기화 명령은 일반 조회 실행 절차에 포함하지 않는다.

## 8. ERD

[원본 보존 ERD](erd_raw.png)와 [핵심 테이블 ERD](erd_core.png)를 제공한다. 시간자료·지도 경계를 포함한 전체 테이블 정의는 [schema.sql](../db/sql/schema.sql)을 따른다.
