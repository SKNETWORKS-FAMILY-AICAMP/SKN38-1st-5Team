# 개발 환경 실행 안내

## 실행 방법

데이터가 적재된 `chachacha` MySQL DB가 필요합니다. (DB 덤프는 팀 내부 전달본 사용)

```bash
# 1. 가상환경과 라이브러리 설치
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 2. 접속 설정 파일 만들기 → DB 접속값과 아래 키 설정 입력
copy .streamlit\secrets.toml.example .streamlit\secrets.toml

# 3. 실행 → 브라우저에서 http://localhost:8510
.venv\Scripts\python -m streamlit run app.py --server.port 8510
```

macOS는 `.venv\Scripts\python` 대신 `.venv/bin/python`, `copy` 대신 `cp`를 사용합니다. 실제 접속값(`secrets.toml`)은 레포에 올리지 않습니다.

실행 전 `.streamlit/secrets.toml`의 DB 설정과 함께 다음 항목의 빈 값을 채웁니다. `javascript_api_key`는 지도 표시, `rest_api_key`는 경로 조회, `[anthropic]`의 `api_key`는 물어보기에 사용합니다.

```toml
[kakao]
javascript_api_key = ""
rest_api_key = ""

[anthropic]
api_key = ""
```

카카오디벨로퍼스에서 카카오맵 사용을 활성화하고, JavaScript 키의 **JavaScript SDK 도메인**에 실제 접속 주소(로컬 예: `http://localhost:8510`)와 배포 주소를 등록합니다. [카카오 설정 안내](https://developers.kakao.com/docs/ko/kakaomap/common)를 참고하세요. JavaScript 키가 없으면 차량 보유와 주차·충전은 대체 지도를 사용하고, 실시간 교통 지도는 안내 문구를 표시합니다.

로컬 MySQL 설정에는 `ssl_ca` 항목을 넣지 않습니다. 이전 예시를 복사했다면 `ssl_ca = ""` 줄을 삭제하세요. `MYSQL_SSL_CA` 환경변수도 명시하면 로컬 TLS가 활성화됩니다. 원격 DB는 이 항목 없이도 TLS·서버 인증서·호스트명을 검증하며, 사설 CA가 필요한 경우에만 실제 CA 인증서 경로를 설정합니다.


검사와 수집 재현 절차는 [README](../README.md)의 해당 절을 참고하세요.
