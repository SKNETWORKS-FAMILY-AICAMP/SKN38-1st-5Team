# 수집 데이터 출처와 이용조건

이용조건 확인일: **2026-11-06**. 데이터는 기본 14개·시간 4개·API 경량·검토용 5개·날씨 1개로 총 24개 CSV다. 원본·정제 CSV·DB 덤프는 공개 레포에 포함하지 않는다.

DB 적재에는 CSV와 원본 해시의 일치가 필요하다. 공개 포털의 최신 파일은 아래 수집본과 바이트·행 수가 다를 수 있다.

## 1. 출처 URL·기준일·수집일

수집일은 manifest의 날짜다. 기본 8개 DB 출처의 정확한 시각은 미확인이고 `collected_at=NULL`이다. API 2개는 5절의 한국 시각을 보존한다. ‘기준일 미상’인 시설·FAQ는 수집일이 실제 현황 기준일을 뜻하지 않는다.

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

전국주차 기준 범위 2026-04-08~10-30은 원본 전체 범위다. 실제 채택한 서울 857행의 행별 기준일은 **2026-04-14~10-24**다. 서울 충전 목록은 433행 수신 중 주소로 서울 429행을 채택했다. source_x/y의 좌표계는 확인되지 않아 위경도로 사용하지 않는다.

주민등록 연결 CSV의 원출처에는 주민등록뿐 아니라 통계누리도 포함된다. 이 보조 CSV 자체를 공공기관이 배포한 독립 데이터셋으로 소개하지 않는다. 교통 9월과 승객 10월 이틀을 같은 기간 자료로 합쳐 부르지 않는다.

## 2. 공공누리·이용허락 확인

아래는 공개된 원문 표시를 기록한 것이다. 유형명이 확인되지 않은 자료를 일괄 제1유형으로 간주하지 않는다. ‘제한 없음’은 포털의 표시이며 공공누리 유형 번호와 구분한다. 원자료 조건을 정제 CSV 전체에 대한 새 허락으로 확대하지 않는다.

| 자료 | 확인한 표시·상태 | 근거 |
| --- | --- | --- |
| resident_join | 자체 연결 산출물. 통계누리 및 주민등록 원자료의 조건을 각각 확인 | [공식 확인 페이지](https://jumin.mois.go.kr/statMonth.do) |
| molit_registration | 공공누리 번호는 별도 확인하지 않음. 공식 연결 카탈로그는 이용허락범위 제한 없음 | [공식 확인 페이지](https://www.data.go.kr/data/15024777/fileData.do) |
| seoul_fuel | 공공누리 제1유형, 출처표시 | [공식 확인 페이지](https://data.seoul.go.kr/dataList/OA-15640/S/1/datasetView.do) |
| hyundai_ev_faq | 기업 저작물, 공공누리 적용 자료로 확인되지 않음. 원문 재배포 허락은 별도 확인 | [공식 확인 페이지](https://www.hyundai.com/kr/ko/service-membership/ev/ev-everycare/ev) |
| seoul_charger | 공공누리 제1유형, 출처표시 | [공식 확인 페이지](https://data.seoul.go.kr/dataList/OA-23033/S/1/datasetView.do) |
| national_parking | 미확인. 공식 페이지의 공개 메타정보에 유형명이 없어 번호를 추정하지 않음 | [공식 확인 페이지](https://www.data.go.kr/data/15012896/standard.do) |
| seoul_passenger | 공공저작물 출처표시 제1유형 | [공식 확인 페이지](https://www.data.go.kr/data/15171264/fileData.do) |
| resident_population | 미확인. 해당 통계 화면에서 자료별 공공누리 유형을 확인하지 못함 | [공식 확인 페이지](https://jumin.mois.go.kr/statMonth.do) |
| seoul_traffic | 공식 연결 카탈로그는 이용허락범위 제한 없음. 공공누리 제1유형과 같은 표기로 바꾸지 않음 | [공식 확인 페이지](https://www.data.go.kr/data/15153325/fileData.do) |

통계누리의 [저작권보호정책](https://stat.molit.go.kr/portal/info/protect.do)은 통계 재사용·재배포와 상업적 활용, 구체적인 출처 표시를 안내하고, 개별 공공누리 표시 확인도 요구한다. 서울 연료·충전 자료의 상세 페이지와 승객 자료의 공공데이터포털에는 제1유형이 표시되어 있다.

주차 표준자료와 주민등록 자료는 공개 메타정보에 자료별 유형명을 확정할 근거가 부족해 미확인으로 남긴다. 공개 배포에는 제공처의 조건 확인이 필요하다.

FAQ 출처는 **현대자동차 EV 에브리케어** 한 곳이며 저장 HTML에서 질문·답변 10쌍을 추출했다. 제네시스 47쌍은 수록 범위에서 제외한다. `faq.csv`의 각 행에는 `source_url`, `fetched_on`, `company_name`이 있고 화면도 원문 링크·기업명·수집일을 표시한다. 기업 FAQ는 공공누리 데이터가 아니므로 기업 원문 출처를 별도로 유지한다.

## 3. 원본 파일 SHA-256

해시는 파일 바이트 전체 기준이다. 기본 manifest 9파일과 시간 manifest 2파일, **총 11파일**이다. `parking_page0.json`은 빈 응답 보관 파일이며 서울 자료를 포함하지 않는다. 원본은 공개 대상에서 제외한다.

| 원본 상대 경로 | SHA-256 | 크기(byte) |
| --- | --- | --- |
| data/raw/data_A/molit_202609.xlsx | 4d372e4fe3c98d2817c51be7ec294087b55f520225e9f60374a575afbbfc852c | 445410 |
| data/raw/b_verified/seoul_fuel_202609.xlsx | 28d5e10e39ef89d8fa2be35d9ae9e4072a70cab156b708a2fb3c3dce58702437 | 64128 |
| data/raw/ab_verified/seoul_charger_api.json | 900ce88980cbc0ed9006a6fa39dafa89c650d3c44607028bfe9f08decad4c0b3 | 193482 |
| data/raw/data_A/parking_page0.json | 4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945 | 2 |
| data/raw/data_A/parking_page1.json | e61f193522eeb35a478b10369c84639cb5d4f3341d1539cb5e8938b341f922f0 | 3232270 |
| data/raw/data_A/parking_page2.json | 08f50b209783c71d857f98f59b527284a984325c83a0f8af39e4069e0614c262 | 2858894 |
| data/raw/data_A/seoul_registration_population_202609.csv | 5f24aa2b4a15de3029abc4f47fc76dd851ecc14fe97712763dfa6ae540639007 | 1710 |
| data/raw/data_A/jumin_sgg_202609.csv | e2e1892a9af486162eceb364b4e8812f4ca2723e48882f370bdeafa6fc857186 | 31143 |
| data/raw/ab_verified/hyundai_ev_current.html | 3b77d03b05c3579f60d137c5a3c351838fb20f51bf969623111b2cb2a0949cee | 224998 |
| data/raw/api_research/seoul_traffic/traffic_202609.xlsx | fbeaeb0327ffdbc799d4ad72de2ea41f7b8203be7c24e8065823a5a5dc7d83a0 | 1576543 |
| data/raw/api_research/seoul_passenger/tpss.csv | c90aa6c5fe1e9723a9258e40293bb11ef3523a7520a435adaf942e0cdbbaf618 | 608352 |

DB 출처는 기본 8개와 API 2개를 합한 10개 출처, 서울 구 경계 1개 출처로 `source_snapshot` 총 11행이다. page1·2는 정렬한 `(경로, 파일 해시)` 목록의 JSON 바이트로 하나의 묶음 해시를 계산한다. 따라서 그 해시는 개별 JSON 파일이나 전체 manifest 파일의 SHA-256과 다르다. page0과 주민등록 연결 보조 CSV를 별도 DB 출처로 더하지 않는다.

## 4. 출처 표시 예시와 범위

출처: 국토교통부 통계누리 자동차등록현황보고(2026-09), 서울특별시 연료별 자동차 등록 및 공공 전기차 충전소, 행정안전부 주민등록 인구통계, 전국주차장정보표준데이터, 서울 TOPIS·서울교통빅데이터플랫폼, 현대자동차 EV 에브리케어. 수집 날짜와 각 URL은 위 표를 따른다. 정제·집계·점수는 차차차 프로젝트에서 계산한 값이며 기관의 공식 지표가 아니다.

API 자료에는 ASOS 관측값과 환경공단 충전 목록이 포함된다. 10/30~31 교통량은 미확보다. 공영주차 요금·운영·감면 자료는 24개 CSV와 DB 적재 범위에 포함하지 않는다. `tests/fixtures/`의 가상 자료는 실제 수집량에서 제외한다.

## 5. API 출처

API 자료의 수집일은 2026-11-06이다. 수신 완료와 DB 적재 완료를 구분하며, 외래키·출처별 건수·결측 검사에 문제가 없는 트랜잭션 끝에서만 `is_complete=1`로 바꾼다.

| 출처·공식 URL | 기간·수집 한국 시각 | 파일 경로·수록량 |
| --- | --- | --- |
| kma_asos_hourly [ASOS](https://www.data.go.kr/data/15057210/openapi.do) | 서울108, 2026-10-30~31 / 2026-11-06 09:23:45 | processed/weather_snapshot.csv, 48시간·9열. 강수 NULL46·적설 NULL48 |
| keco_ev_charger [환경공단](https://www.data.go.kr/data/15076352/openapi.do) | 과거 관측 기간 미제공 / 2026-11-06 09:26:28 | raw/api/charger_national_snapshot.csv, 수신76,341행. 삭제709·보류25 제외 후75,607행 |

원본 파일 SHA-256:

- `data/processed/weather_snapshot.csv`: `17cbf4b57562ded636952690b954129b30d3eabcc06324128085abd8f38bb2a4`
- `data/raw/api/charger_national_snapshot.csv`: `1582db882825f1592297032ffda29db9f8f126086f8923c9a181aaff45b155f8`

두 API의 공공누리 유형은 미확인이며 다른 자료의 이용허락 표시를 적용하지 않는다. 기본 충전 지표는 환경공단 출처 하나만 사용하며 서울 공공 목록은 비교표에만 쓴다.

## 6. 서울 25구 경계 (수집일: 2026-11-08)

[southkorea/seoul-maps](https://github.com/southkorea/seoul-maps)의 KOSTAT 2013 센서스 행정구역 경계다. 저장소 README는 Apache v2.0과 기여자 Lucy Park를 표시한다. `seoul-districts.geojson`의 경계 좌표를 단순화하지 않고 사용한다. **2013년 경계, 지도 표시 전용, 점수 계산에 쓰지 않음.** 현재 행정구역의 법적 경계 자료로 취급하지 않는다.

| 원본 상대 경로 | SHA-256 | 크기(byte) |
| --- | --- | --- |
| data/raw/boundary/seoul-districts.geojson | 2bb208614451c9f2a096cd62204063d6b27e57dcb7650a35ac19c06f1a84eb03 | 57732 |

25 feature·25 Polygon·25개 고리·1,374개 좌표(닫는 끝점 포함)로 구성되며 `region.district_name`과 25개 구가 모두 연결된다. 좌표 순서는 **경도, 위도**다. 중심은 경위도 평면의 면적 중심으로 계산한 지도용 근사값이며 소수 7자리로 저장한다. bbox는 모든 원본 점을 포함하도록 최솟값을 내림·최댓값을 올림하여 소수 7자리로 저장한다. 도형의 원본 좌표 정밀도는 유지한다.

DB의 `source_snapshot`은 경계 출처를 포함해 11행이며 `region_boundary`는 25행이다.
