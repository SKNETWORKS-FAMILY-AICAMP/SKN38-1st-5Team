# 차차차

![차차차: 차량 보유 현황·주차하기 좋은 동네·차가 꼭 필요한 동네](docs/screens/chachacha_banner.svg)

## 팀 소개

| 역할 | 이름 | GitHub | 맡은 일 |
|---|---|---|---|
| 팀장 · PM | 고재윤 | [@jjygo](https://github.com/jjygo) | 범위·일정·발표 준비 조율 |
| 프론트엔드 | 한기현 | [@airnsie-sudo](https://github.com/airnsie-sudo) | Streamlit 화면·지도·시연 |
| 백엔드 | 박채영 | [@chaezero03](https://github.com/chaezero03) | 데이터 수집·DB 구축·SQL 조회 |
| 백엔드 | 이현지 | [@ira1234847](https://github.com/ira1234567) | 데이터 수집·DB 구축·SQL 조회 |
| 서포터 | 권대원 | [@SorryToT](https://github.com/SorryToT) | 데이터 확인·문서·발표 자료 |

## 왜 차차차인가요?

내 차를 가지고 편하게 살 동네를 고르려면 주차난, 막히는 출퇴근길, 늘어나는 전기차 충전 인프라까지 따져야 합니다. **차차차**는 서울 25개 구의 차량 보유 현황, 주차 여건, 대중교통 이용 수준을 비교해 "**이 동네는 차를 가지고 살기 편한가**"를 판정과 근거 수치로 보여줍니다.

> *역세권이 대중교통 이용자를 위한 기준이라면, 차차차는 자동차 이용자를 위한 동네 선택 기준입니다.*

공식 과제는 **전국 자동차 등록 현황 및 기업 FAQ 조회시스템**입니다.

## 주요 화면

<table>
  <thead>
    <tr><th>구분</th><th>메뉴</th><th>할 수 있는 것</th></tr>
  </thead>
  <tbody>
    <tr><td rowspan="2" align="center">🏠 시작</td><td><b>우리 동네</b></td><td>서울 지도에서 구를 선택해 세 판정의 분포를 보고, 동네에 맞는 공공 사이트 연결과 자주 찾는 메뉴 바로가기, 서울 자동차 현황을 확인합니다.</td></tr>
    <tr><td><b>동네 찾기</b></td><td>내 상황과 중요하게 보는 기준을 고르면 서울 25구를 내 기준으로 추천하고 전체 순위를 보여줍니다.</td></tr>
    <tr><td rowspan="5" align="center">🔍 동네 살펴보기</td><td><b>차량 보유</b></td><td>서울 25구의 차량 보유 현황을 지도에서 보고 차종별 구성과 서울 평균을 비교합니다.</td></tr>
    <tr><td><b>주차·충전 찾기</b></td><td>동네의 주차 여건을 확인하고 주차장·충전소 위치를 지도에서 찾습니다.</td></tr>
    <tr><td><b>전기차 충전</b></td><td>충전기 구성과 충전소 위치를 살펴봅니다. (실시간 빈자리 정보는 아님)</td></tr>
    <tr><td><b>대중교통</b></td><td>시간대별 승객 흐름으로 차 없이 다닐 때의 동네 모습을 살펴봅니다.</td></tr>
    <tr><td><b>도로와 날씨</b></td><td>실시간 교통 지도와 수록된 시간대별 교통량·날씨 표본을 각각 살펴봅니다.</td></tr>
    <tr><td rowspan="3" align="center">⚖️ 비교·조회</td><td><b>25구 순위</b></td><td>선택한 구의 세 판정 카드, 서울 25구 순위, 판정 기준과 출처를 확인합니다.</td></tr>
    <tr><td><b>두 동네 비교</b></td><td>두 구의 세 판정과 근거를 같은 기준으로 나란히 비교합니다.</td></tr>
    <tr><td><b>전국 등록 조회</b></td><td>시도·차종·용도별 전국 등록대수를 조회합니다. (2026-09 기준 26,706,123대)</td></tr>
    <tr><td rowspan="3" align="center">💡 도움말</td><td><b>기업 FAQ</b></td><td>서비스 이용 안내와 현대 EV FAQ를 검색하고 원문 링크를 확인합니다.</td></tr>
    <tr><td><b>물어보기</b></td><td>동네와 자동차 생활에 대해 질문하고 답변과 근거 자료를 확인합니다.</td></tr>
    <tr><td><b>자료 안내</b></td><td>자료 출처, 기준 시점, 판정 규칙과 자료의 한계를 확인합니다.</td></tr>
  </tbody>
</table>

홈 이외의 지도에는 Kakao 지도를 사용합니다. 카카오 응답은 DB에 저장하지 않으며, MySQL의 공공데이터를 지도에 표시합니다.

## 세 판정의 기준

각 지표의 값이 **큰 구부터** 서울 25구의 순위를 매겨 **1–8위 / 9–17위 / 18–25위**로 나눕니다. 순위는 SQL의 `RANK()` 함수로 계산합니다.

| 판정 | 비교하는 값 | 1–8위 / 9–17위 / 18–25위 |
|---|---|---|
| 차량 보유 현황 | 등록대수 ÷ 세대수 | 많은 편 / 보통 / 적은 편 |
| 주차하기 좋은 동네 | 주차면 ÷ 등록대수 | 좋음 / 보통 / 빠듯함 |
| 차가 꼭 필요한 동네 | 하루 대중교통 승객 ÷ 주민 수 | 대중교통으로 충분 / 있으면 편함 / 차가 필요한 편 |

> ⚠️ 등록·인구는 **2026-09 한 달**, 승객은 **2026-10-30 하루** 자료입니다. 주차는 표준데이터에 수록된 주차장만 비교하며 아파트 주차장과 실시간 빈자리는 포함하지 않습니다. 중구·종로구는 출퇴근 유입으로 승객 값이 커질 수 있고, 강서구는 일부 행정동 자료가 빠져 있습니다.

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
└── tests/, test/   # 자동 검사
```

## ERD

**18개 테이블 · FK 25개 · 총 111,676행**

![핵심 테이블 ERD](docs/erd_core.png)

[원본 보존 ERD](docs/erd_raw.png) · [초기 설계 ERD](database/erd.png) · [DB 설계 문서](docs/db_design.md) · [대표 SQL](docs/sql_showcase.md)

### 8개 도메인 (ERD 색상별 분류)

| 색상 | 도메인 | 테이블 |
|:---:|---|---|
| 🟥 | 기준/코드 (허브) | `region`, `vehicle_type`, `fuel_scope` |
| ⬜ | 메타 (허브) | `source_snapshot` |
| 🟪 | 차량 등록 | `registration`, `province_registration` |
| 🟨 | 충전 인프라 | `charging_station`, `charger` |
| 🟧 | 회사/고객지원 | `company`, `faq` |
| 🟩 | 지역 환경 | `region_context`, `parking_site`, `region_boundary` |
| 🟦 | 교통·이동 | `traffic_coverage`, `traffic_snapshot`, `transit_coverage`, `transit_ridership_snapshot` |
| ⬛ | 외부 환경 | `weather_snapshot` |

**설계 원칙**
- **허브와 업무 도메인 구분**: 모든 테이블이 참조하는 기준/코드·메타는 중립색, 업무 도메인은 고유색으로 표시합니다.
- **수집 범위와 관측값 분리**: 받아야 할 양과 실제 받은 양을 따로 저장해 빠진 데이터를 계산합니다.
- **원본 보존**: 모든 수집 자료는 `source_snapshot`으로 출처·수집일을 추적합니다.

## 데이터 출처

국토교통부 자동차 등록, 행정안전부 인구·세대, 전국주차장정보표준데이터, 한국환경공단 충전소 API, 서울 TOPIS 교통량, 서울 행정동 승객수, 기상청 ASOS API, 현대자동차 EV FAQ, 통계청 서울 구 경계 등 **11종**을 사용합니다. 출처별 수집일·수록량·이용조건은 [데이터 출처 기록](data/SOURCES.md)에 있습니다.

> DB 덤프·정제 CSV·원본 데이터와 기업 FAQ 원문은 재배포 조건 때문에 레포에 포함하지 않습니다.
> 

개발 환경의 MySQL 연결과 실행 방법은 [실행 안내](docs/runbook.md)를 참고하세요.

## FAQ 수집 재현

기존 `etl.crawl_faq`는 저장 HTML을 BeautifulSoup으로 파싱하며 네트워크를 사용하지 않습니다. `--fetched-on`은 파싱 실행일이 아닌 HTML을 실제 확보한 날짜입니다. 생략하면 기존 보관본의 `2026-11-05`를 유지합니다.

```bash
python -m etl.crawl_faq --input path/to/captured.html --fetched-on 2026-11-10 --output data/preview/faq.csv
```

아래 명령을 명시적으로 실행하면 Selenium Chrome으로 고정된 현대 EV 원문을 열고 FAQ 영역을 기다린 뒤 BeautifulSoup으로 추출합니다. Chrome과 Selenium이 사용할 드라이버가 필요하며, Selenium Manager가 드라이버를 준비할 때 네트워크를 사용할 수 있습니다.

```bash
python -m etl.fetch_faq --timeout 30 --output data/preview/faq_live.csv
python -m unittest tests.test_fetch_faq
```

실제 수집일은 `fetched_on`, 한국 시각의 정확한 수집시각은 `collected_at` 열에 기록합니다. 시간 초과·FAQ 구조 변경·중복 질문·출력 실패 시 기존 CSV를 교체하지 않고 브라우저를 종료합니다. 새 수집 CSV는 검토용이며 기존 검산된 수집본이나 DB를 자동 갱신하지 않습니다. 원본·CSV는 Git에 추가하지 않습니다. 위 테스트는 가상 HTML과 모의 브라우저를 사용하여 외부 수집 없이 실행합니다.

## 앞으로의 계획

- **차차차 종합 점수 화면 반영**: `scoring.py` 보조 모델 검증 후 결정
- **맞춤형 주차비 계산**: 주차 요금·차량유형별 감면 데이터 추가 필요
- **EV 전용 모드**: 충전기 1기당 전기차 수, 신규 충전소 입지 분석
- **행정동 단위 분석**: 행정동별 등록·주차 데이터 확보 필요

<!-- 회고: 이 자리에 "## 회고" 섹션을 넣을 예정 -->

---

**SK Networks Family AI Camp · SKN38 1st Project · 5Team**
