# 차차차

![차차차: 차량 보유 현황·주차하기 좋은 동네·차가 꼭 필요한 동네](docs/screens/chachacha_banner.svg)

## 팀 소개

| 역할 | 이름 | GitHub | 맡은 일 |
|---|---|---|---|
| 팀장 · PM | 고재윤 | [@jjygo](https://github.com/jjygo) | 범위·일정·발표 준비 조율 |
| 프론트엔드 | 한기현 | [@airnsie-sudo](https://github.com/airnsie-sudo) | Streamlit 화면·지도·시연 |
| 백엔드 | 박채영 | [@chaezero03](https://github.com/chaezero03) | 데이터 수집·DB 구축·SQL 조회 |
| 백엔드 | 이현지 | [@ira1234847](https://github.com/ira1234847) | 데이터 수집·DB 구축·SQL 조회 |
| 서포터 | 권대원 | [@SorryToT](https://github.com/SorryToT) | 데이터 확인·문서·발표 자료 |

## 프로젝트 소개

공식 과제는 전국 자동차 등록 현황 및 기업 FAQ 조회시스템입니다.

차를 가지고 살 동네를 고를 때는 주차, 출퇴근길, 전기차 충전까지 같이 봐야 합니다. 역세권처럼 자동차 이용자 입장에서 동네를 볼 수 있으면 좋겠다는 생각으로 시작했고, 서울 25개 구의 차량 보유 현황, 주차 여건, 대중교통 이용 수준을 판정과 수치로 비교할 수 있게 만들었습니다.

## 주요 화면

<table>
  <thead>
    <tr><th>구분</th><th>메뉴</th><th>할 수 있는 것</th></tr>
  </thead>
  <tbody>
    <tr><td rowspan="2" align="center">시작</td><td><b>우리 동네</b></td><td>서울 지도에서 구를 고르면 세 판정을 볼 수 있고, 공공 사이트 연결과 바로가기, 서울 자동차 현황이 있습니다.</td></tr>
    <tr><td><b>동네 찾기</b></td><td>내 상황과 중요하게 보는 기준을 고르면 서울 25구를 순위로 추천합니다.</td></tr>
    <tr><td rowspan="4" align="center">동네 살펴보기</td><td><b>차량 보유</b></td><td>구별 차량 보유 현황을 지도로 보고 차종 구성을 서울 평균과 비교합니다.</td></tr>
    <tr><td><b>주차·충전 찾기</b></td><td>주차 여건을 확인하고 주차장과 충전소 위치를 지도에서 찾습니다.</td></tr>
    <tr><td><b>대중교통</b></td><td>시간대별 승객 수를 봅니다.</td></tr>
    <tr><td><b>도로와 날씨</b></td><td>실시간 교통 지도와 수록된 교통량·날씨 자료를 봅니다.</td></tr>
    <tr><td rowspan="3" align="center">비교·조회</td><td><b>25구 순위</b></td><td>선택한 구의 판정과 25구 순위, 판정 기준과 출처를 봅니다.</td></tr>
    <tr><td><b>두 동네 비교</b></td><td>두 구의 판정과 수치를 나란히 비교합니다.</td></tr>
    <tr><td><b>전국 등록 조회</b></td><td>시도·차종·용도별 등록 대수를 조회합니다. (2026년 9월 기준 26,706,123대)</td></tr>
    <tr><td rowspan="3" align="center">도움말</td><td><b>기업 FAQ</b></td><td>이용 안내와 현대 EV FAQ를 검색합니다.</td></tr>
    <tr><td><b>물어보기</b></td><td>동네와 자동차 생활에 대해 질문하고 근거 자료를 함께 봅니다.</td></tr>
    <tr><td><b>자료 안내</b></td><td>자료 출처, 기준 시점, 판정 규칙과 한계를 설명합니다.</td></tr>
  </tbody>
</table>

홈을 뺀 지도는 Kakao 지도를 사용합니다. 카카오 응답은 DB에 저장하지 않고, MySQL에 넣은 공공데이터를 지도 위에 표시합니다.

## 세 판정의 기준

서울 25구를 지표 값이 큰 순서로 세워 1~8위, 9~17위, 18~25위로 나눕니다. 순위는 SQL의 `RANK()`로 계산합니다.

| 판정 | 비교하는 값 | 1~8위 / 9~17위 / 18~25위 |
|---|---|---|
| 차량 보유 현황 | 등록 대수 ÷ 세대 수 | 많은 편 / 보통 / 적은 편 |
| 주차하기 좋은 동네 | 주차면 ÷ 등록 대수 | 좋음 / 보통 / 빠듯함 |
| 차가 꼭 필요한 동네 | 하루 대중교통 승객 ÷ 주민 수 | 대중교통으로 충분 / 있으면 편함 / 차가 필요한 편 |

등록과 인구는 2026년 9월, 승객은 2026년 10월 30일 하루 자료입니다. 주차는 표준데이터에 있는 주차장만 세기 때문에 아파트 주차장과 실시간 빈자리는 포함되지 않습니다. 중구와 종로구는 출퇴근 인구 때문에 승객 값이 크게 나올 수 있고, 강서구는 일부 행정동 자료가 빠져 있습니다.

## 기술 스택

| 구분 | 기술 |
|---|---|
| 언어·데이터 처리 | Python 3.14, Pandas |
| 데이터베이스 | MySQL 8, ERDCloud, DBeaver |
| 웹·시각화 | Streamlit 1.67.0, Altair 5.3.0, Kakao Maps JavaScript SDK |
| 수집 | 공공데이터 포털 API 2종, Selenium, BeautifulSoup |
| 협업 | Git, GitHub |

## 프로젝트 구조

```text
SKN38-1st-5Team/
├── app.py          # Streamlit 시작점
├── app_pages/      # 화면별 페이지
├── db/             # DB 연결·SQL 조회, sql/에 테이블 생성 SQL
├── etl/            # API 수집·FAQ 크롤링·정제·적재
├── docs/           # DB 설계 문서, 대표 SQL, ERD
├── data/           # 데이터 출처 기록
└── tests/, test/   # 테스트
```

## ERD

테이블 18개, FK 25개, 총 111,676행입니다.

![2차 2NF ERD](docs/erd_core.png)

[1차 raw ERD](docs/erd_raw.png) · [초기 ERD](database/erd.png) · [DB 설계 문서](docs/db_design.md) · [대표 SQL](docs/sql_showcase.md)

ERD 색상별로 나누면 다음과 같습니다.

| 색상 | 묶음 | 테이블 |
|---|---|---|
| 빨강 | 기준 코드 | `region`, `vehicle_type`, `fuel_scope` |
| 흰색 | 수집 기록 | `source_snapshot` |
| 보라 | 차량 등록 | `registration`, `province_registration` |
| 노랑 | 충전 | `charging_station`, `charger` |
| 주황 | 기업 FAQ | `company`, `faq` |
| 초록 | 지역 | `region_context`, `parking_site`, `region_boundary` |
| 파랑 | 교통 | `traffic_coverage`, `traffic_snapshot`, `transit_coverage`, `transit_ridership_snapshot` |
| 검정 | 날씨 | `weather_snapshot` |

교통과 승객 자료는 받아야 할 범위와 실제로 받은 값을 나눠 저장해서 빠진 데이터를 셀 수 있게 했습니다. 수집한 자료는 `source_snapshot`으로 출처와 수집일을 확인할 수 있습니다.

## 데이터 출처

국토교통부 자동차 등록, 행정안전부 인구·세대, 전국주차장정보표준데이터, 한국환경공단 충전소 API, 서울 TOPIS 교통량, 서울 행정동 승객수, 기상청 ASOS API, 현대자동차 EV FAQ, 통계청 서울 구 경계 등 11종을 사용했습니다. 자세한 내용은 [데이터 출처 기록](data/SOURCES.md)에 있습니다.

DB 덤프, 정제 CSV, 원본 데이터, 기업 FAQ 원문은 재배포 조건 때문에 레포에 넣지 않았습니다.

실행 방법은 [실행 안내](docs/runbook.md)를 참고해 주세요.

## FAQ 수집 방법

저장해 둔 HTML은 `etl.crawl_faq`로 파싱하고, 실제 페이지에서 다시 받을 때는 Selenium을 쓰는 `etl.fetch_faq`를 실행합니다. Chrome이 필요합니다.

```bash
python -m etl.crawl_faq --input path/to/captured.html --fetched-on 2026-11-10 --output data/preview/faq.csv
python -m etl.fetch_faq --timeout 30 --output data/preview/faq_live.csv
```

수집한 CSV는 검토용이라 DB에 자동으로 넣지 않고 Git에도 올리지 않습니다.

## 앞으로의 계획

- `scoring.py`의 보조 점수를 검증해서 화면에 넣을지 정하기
- 주차 요금과 차량 유형별 감면 자료를 모아 주차비 계산 넣기
- 충전기 1기당 전기차 수와 신규 충전소 입지 분석
- 행정동별 등록·주차 데이터를 구해서 행정동 단위로 분석하기

## 회고

| 이름 | 역할 | 회고 |
|---|---|---|
| 고재윤 | 팀장 · PM |  |
| 한기현 | 프론트엔드 |  |
| 박채영 | 백엔드 |  |
| 이현지 | 백엔드 |  |
| 권대원 | 서포터 |  |

---

SK Networks Family AI Camp · SKN38 1st Project · 5Team
