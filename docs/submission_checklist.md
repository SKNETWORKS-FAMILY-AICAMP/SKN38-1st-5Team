# 과제 요구사항과 제출 산출물 점검표

## 요구사항과 구현 위치

| 요구사항 | 구현·근거 | 확인 방법 |
|---|---|---|
| 업무 도메인 데이터 정의 | `data/SOURCES.md`, `docs/db_design.md` | 차량·주차·충전·이동 데이터의 출처·시점·범위 확인 |
| BeautifulSoup 수집·파싱 | `etl/crawl_faq.py` | 저장 HTML의 FAQ 영역을 파싱하고 누락·중복 질문 차단 |
| Selenium 수집 | `etl/fetch_faq.py` | 고정 출처의 FAQ 영역 대기, BeautifulSoup 추출, 수집시각 기록 |
| MySQL 설계·적재 | `db/sql/schema.sql`, `etl/load.py`, `db/init_schema.py` | 키·제약조건·적재 검증. 운영 DB에는 초기화 명령 실행 금지 |
| Python과 MySQL SQL 조회 | `db/connection.py`, `db/queries.py` | SQLAlchemy/PyMySQL 연결 및 매개변수 바인딩 |
| Streamlit GUI | `app.py`, `app_pages/` | 검색·필터·지도·통계·비교 조회 |

## 제출할 세 가지 묶음

### 1. 데이터베이스 설계 문서

- `docs/db_design.md`: 테이블·관계·설계 근거
- `docs/erd_core.png`, `docs/erd_raw.png`: ERD
- `db/sql/`: 실제 데이터가 없는 테이블 정의·변경 SQL
- `docs/sql_showcase.md`: 조회 SQL 설명

### 2. 수집 데이터

원본 HTML·CSV·DB 덤프는 저장소에 포함하지 않는다. 이용조건과 제출기관의 전달 방식을 확인한 뒤 접근이 제한된 경로로 별도 제출한다.

- 원본·정제 파일과 파일별 행 수
- 출처 URL, 실제 수집일·기준일, 수집 방법
- 파일 해시와 검증 결과
- 원본 재배포가 제한되면 허용되는 제출 범위와 재현 절차
- 실제 비밀번호·API 키·개인정보·불필요한 로그 제외

새 Selenium 수집 결과는 검토용 CSV다. 과거 검산 수집본이나 DB를 자동으로 교체하지 않는다. 수집기를 추가한 것과 실제 사이트에서 성공적으로 수집한 것은 구분한다.

### 3. 데이터 조회 프로그램

- `app.py`, `app_pages/`, 조회·지도·화면 모듈
- `db/connection.py`, `db/queries.py`
- `requirements.txt`, `requirements.lock.txt`
- 실제 비밀값이 없는 `.streamlit/secrets.toml.example`
- README 실행 방법

## 재현 시 필요한 준비

1. README의 Python 버전과 고정 의존성 목록을 사용한다.
2. MySQL에 팀 내부 전달본을 적재하고 개인 접속정보를 설정한다.
3. `python scripts/fetch_boundary.py`로 공개 지도 원본을 검증해 복원한다.
4. 공개 전 검사를 실행한다.
5. Selenium 실제 수집은 Chrome·드라이버·네트워크·사이트 접근 조건이 준비된 경우에만 명시적으로 실행한다.

AWS 가입이나 외부 배포는 이 과제의 MySQL 연동·조회 구현을 확인하기 위한 필수 조건이 아니다. 현재 AWS 배포 계획은 취소된 상태다.
