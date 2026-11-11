# 수집 데이터 출처와 이용조건

이용조건 확인일: **2026-11-06**. 데이터는 기본 14개·시간 4개·API 경량·검토용 5개·날씨 1개로 총 24개 CSV다. 원본·정제 CSV·DB 덤프는 공개 레포에 포함하지 않습니다.

DB 적재에는 CSV와 원본 해시의 일치가 필요하다. 공개 포털의 최신 파일은 아래 수집본과 바이트·행 수가 다를 수 있습니다.

## 1. 출처 URL·기준일·수집일

수집일은 manifest의 날짜다. 기본 8개 DB 출처의 정확한 시각은 미확인이고 `collected_at=NULL`이다. API 2개는 5절의 한국 시각을 보존합니다. ‘기준일 미상’인 시설·FAQ는 수집일이 실제 현황 기준일을 뜻하지 않습니다.

| 자료 | 출처 URL | 기준·수집일 |
| --- | --- | --- |
| molit_registration<br>국토교통부 자동차등록현황보고 | [원문](https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=58) | 2026-09-01 ~ 2026-09-30<br>수집 2026-11-05 |
| seoul_fuel<br>서울특별시 자동차 연료별 등록 | [원문](https://data.seoul.go.kr/dataList/OA-15640/S/1/datasetView.do) | 2026-09-01 ~ 2026-09-30<br>수집 2026-11-05 |
| seoul_charger<br>서울특별시 공공 전기차 충전소 | [원문](https://data.seoul.go.kr/dataList/OA-23033/S/1/datasetView.do) | 자료 기준일 미상; 제공 페이지 갱신일 2026-09-30<br>수집 2026-11-05 |
| national_parking<br>전국주차장정보표준데이터 | [원문](https://www.data.go.kr/data/15012896/standard.do) | 2026-04-08 ~ 2026-10-30<br>수집 2026-11-05 |
| resident_join<br>등록·인구 연결 보조 CSV | [원문](https://jumin.mois.go.kr/statMonth.do) | 2026-09-01 ~ 2026-09-30; 공식 다운로드가 아닌 연결 보조물<br>수집 2026-11-05 |
| resident_population<br>행정안전부 주민등록 인구·세대 | [원문](https://jumin.mois.go.kr/statMonth.do) | 2026-09-01 ~ 2026-09-30<br>수집 2026-11-05 |
| hyundai_ev_faq<br>현대자동차 EV 에브리케어 FAQ | [원문](https://www.hyundai.com/kr/ko/service-membership/ev/ev-everycare/ev) | 자료 기준일 미상<br>수집 2026-11-05 |
| seoul_traffic<br>서울특별시 TOPIS 지점별 일자별 교통량 | [원문](https://topis.seoul.go.kr/refRoom/openRefRoom_1.do?tab=volumeDaily) | 2026-09-01 ~ 2026-09-30<br>수집 2026-11-06 |
| seoul_passenger<br>서울특별시 행정동별 대중교통 승객수 | [원문](https://t-data.seoul.go.kr/dataprovide/download.do?id=10239) | 2026-10-30 ~ 2026-10-31<br>수집 2026-11-06 |

전국주차 기준 범위 2026-04-08~10-30은 원본 전체 범위다. 실제 채택한 서울 857행의 행별 기준일은 2026-04-14~10-24입니다. 서울 충전 목록은 433행 수신 중 주소로 서울 429행을 채택했다. source_x/y의 좌표계는 확인되지 않아 위경도로 사용하지 않는다.

## 2. API 출처

API 자료의 수집일은 2026-11-06이다. 수신 완료와 DB 적재 완료를 구분하며, 외래키·출처별 건수·결측 검사에 문제가 없는 트랜잭션 끝에서만 `is_complete=1`로 바꾼다.

| 출처·공식 URL | 기간·수집 한국 시각 | 파일 경로·수록량 |
| --- | --- | --- |
| kma_asos_hourly [ASOS](https://www.data.go.kr/data/15057210/openapi.do) | 서울108, 2026-10-30~31 / 2026-11-06 09:23:45 | processed/weather_snapshot.csv, 48시간·9열. 강수 NULL46·적설 NULL48 |
| keco_ev_charger [환경공단](https://www.data.go.kr/data/15076352/openapi.do) | 과거 관측 기간 미제공 / 2026-11-06 09:26:28 | raw/api/charger_national_snapshot.csv, 수신76,341행. 삭제709·보류25 제외 후75,607행 |

## 3. 서울 25구 경계 (수집일: 2026-11-08)

[southkorea/seoul-maps](https://github.com/southkorea/seoul-maps)의 KOSTAT 2013 센서스 행정구역 경계다. 저장소 README는 Apache v2.0과 기여자 Lucy Park를 표시한다. `seoul-districts.geojson`의 경계 좌표를 단순화하지 않고 사용한다. **2013년 경계, 지도 표시 전용, 점수 계산에 쓰지 않음.** 현재 행정구역의 법적 경계 자료로 취급하지 않는다.

| 원본 상대 경로 | SHA-256 | 크기(byte) |
| --- | --- | --- |
| data/raw/boundary/seoul-districts.geojson | 2bb208614451c9f2a096cd62204063d6b27e57dcb7650a35ac19c06f1a84eb03 | 57732 |

25 feature·25 Polygon·25개 고리·1,374개 좌표(닫는 끝점 포함)로 구성되며 `region.district_name`과 25개 구가 모두 연결된다. 좌표 순서는 **경도, 위도**다. 중심은 경위도 평면의 면적 중심으로 계산한 지도용 근사값이며 소수 7자리로 저장한다. bbox는 모든 원본 점을 포함하도록 최솟값을 내림·최댓값을 올림하여 소수 7자리로 저장한다. 도형의 원본 좌표 정밀도는 유지한다.

DB의 `source_snapshot`은 경계 출처를 포함해 11행이며 `region_boundary`는 25행이다.

## 주차 지도 상세 안내와 역 검색 (2026-11-09 추가)

- 출처: [서울시 주차정보안내시스템](https://parking.seoul.go.kr/). 공개 화면에서 사용하는 주차장 목록 조회(`/search/parking/list.do`)와 목적지 검색(`/search/parking/destination.do`)를 이용한다.
- 지도에 표시하는 이름·주소·좌표·평일/토요일/공휴일 운영시간·유무료 구분·기본/추가 요금·일 최대/월 정기권은 해당 조회 응답 기준이다. 응답의 `sync_time`을 상세 안내에 표시한다. 현재 빈자리 수는 사용하지 않는다.
- 성공한 주차장 조회는 동네별 1시간, 역 검색은 검색어별 24시간 캐시한다. 조회 실패는 캐시하지 않고 다음 조회에서 재시도한다. 조회 실패 시 기존 DB의 유효 좌표로 돌아가며, 없는 이름·운영시간·요금을 추정해 채우지 않는다.
- 이 지도 안내는 기존 `parking_standard` 통계·주소 목록과 별도의 제공 범위다. 주차장 관리번호를 서로 같은 식별자로 간주하거나 DB 통계를 덮어쓰지 않는다.
- 역 검색은 실제 역 이름과 노선명이 있는 결과만 사용하고, 역 이름이 포함된 상점·출구는 제외한다. 주변 시설은 현재 동네·시설·검색·운영 필터 안에서 계산하며 역 좌표와의 직선거리다. 여러 위치로 구성된 주차구간은 유효 좌표를 모두 보존하고 가장 가까운 위치로 반경을 판정한다. 경로·도보거리나 인근 시설의 전수 목록을 뜻하지 않는다.
- 충전소 상세는 기존 환경공단 자료의 운영시간·이용제한·운영사·`parking_free`를 사용한다. 주차 무료와 충전 무료는 구분한다. 이용제한 코드는 설명과 함께 집계하며, 제한 코드가 있으면 설명이 없어도 제한 있음을 표시한다. 충전 단가가 없으면 금액 정보 미제공으로 안내한다.
- 배경지도와 지도 기능은 [Kakao 지도 Web API](https://apis.map.kakao.com/web/)로 제공한다. 지도 안의 카카오 로고·저작권 표시를 유지한다. 키가 없는 환경의 주차·충전 지도는 Leaflet 1.9.4(BSD-2-Clause, `assets/vendor/leaflet-LICENSE.txt`)와 OpenStreetMap을 사용하며 해당 저작권 표시도 유지한다.

## 지도 제공자와 실시간 정보

- 카카오는 배경지도·실시간 교통정보와 도보 경로의 제공자다. 지도 위의 등록 대수·주차장·충전소·구 경계는 각각 국토교통부, 서울시·전국주차장정보표준데이터, 환경공단, 통계청 경계 원자료를 사용하며 기존 출처·기준일을 유지한다. 홈 지도는 통계청 경계를 사용한 자체 표시다.
- 도로와 날씨의 ‘지금 교통 상황’은 [카카오 교통정보 오버레이](https://apis.map.kakao.com/web/sample/addTrafficOverlay/)로 제공하는 실시간 정보다. DB에 수록된 2026년 9월 TOPIS 교통량과 10월 30~31일 ASOS 날씨 표본은 별도 자료이며 현재 상황을 나타내지 않는다.
- 도보 거리와 예상 소요 시간은 [카카오맵 REST API의 도보 경로 조회](https://developers.kakao.com/docs/ko/kakaomap/rest-api) 규격을 따른다. 거리 단위는 미터, 시간 단위는 초이며 기존 역 주변 시설의 직선거리와 구분한다. REST API 키는 서버에서만 사용한다.
- 카카오 응답(좌표·장소·경로·소요 시간)은 MySQL·파일·로그·`st.cache_data`에 저장하지 않고, 같은 세션의 화면 표시에 필요한 동안만 사용한다. SDK·타일도 파일로 저장하지 않는다.
