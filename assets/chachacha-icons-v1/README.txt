차차차 아이콘 패키지 v1

디자인
현재 서비스의 네이비(#27336B), 코랄(#FF7A66), 연보라(#EEF0FA)를 기본으로 합니다.
기존 둥근 자동차와 웃는 표정을 이어가고, 큰 앱 아이콘에 접힌 지도를 더했습니다.
16px 파비콘에서는 지도와 장식선을 빼고 차체 실루엣을 강조했습니다.
mint/는 Desktop/chachacha-brand-v5의 색상을 따른 대체 색상입니다.
기존 logo.svg와 v5 원본은 그대로 보존했습니다.

파일 (navy/와 mint/에 동일하게 제공)
favicon.svg: 확장 가능한 파비콘
favicon.ico: 16, 32, 48, 64px가 들어 있는 멀티사이즈 파일
favicon-{16,32,48,64,128}.png: 크기별 파비콘
app-icon.svg / app-icon-{192,512,1024}.png: 앱 아이콘
apple-touch-icon.png: 180px, 불투명 정사각형 (플랫폼에서 모서리 처리)
app-icon-maskable-512.png: 512px, 불투명 배경과 안전 영역을 둔 아이콘
symbol.svg / symbol-512.png: 배경 투명 자동차 심볼
ui/: 차량, 지도, 주차, 충전, 비교, 위치, 대중교통, 도움말 8종 SVG와 96px PNG
preview.html / preview.png: 실제 크기와 배경별 검토용 시트

Streamlit 적용
app.py의 st.set_page_config(page_icon=...)는 navy/favicon-64.png를 사용합니다.
앱 헤더의 기존 로고는 보존했습니다.

일반 웹 적용 예시 (이 폴더를 /assets/chachacha-icons-v1 에 복사한 경우)
<link rel="icon" type="image/svg+xml" href="/assets/chachacha-icons-v1/navy/favicon.svg">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/chachacha-icons-v1/navy/favicon-32.png">
<link rel="alternate icon" href="/assets/chachacha-icons-v1/navy/favicon.ico">
<link rel="apple-touch-icon" sizes="180x180" href="/assets/chachacha-icons-v1/navy/apple-touch-icon.png">

PWA manifest에 추가할 아이콘 예시
{"src":"/assets/chachacha-icons-v1/navy/app-icon-192.png","sizes":"192x192","type":"image/png","purpose":"any"}
{"src":"/assets/chachacha-icons-v1/navy/app-icon-512.png","sizes":"512x512","type":"image/png","purpose":"any"}
{"src":"/assets/chachacha-icons-v1/navy/app-icon-maskable-512.png","sizes":"512x512","type":"image/png","purpose":"maskable"}
전체 manifest, service worker, 설치 기능은 이 패키지에 포함하지 않습니다.

제작 방식
기존 프로젝트의 SVG 스타일을 이어 직접 작성한 벡터입니다.
AI 이미지 생성 도구/CLI는 사용하지 않았습니다. PNG는 SVG를 librsvg로 렌더링했습니다.
외부 폰트나 이미지 의존성이 없습니다. 수정 시 SVG를 편집한 뒤 PNG/ICO도 다시 내보내세요.
UI SVG는 24px 그리드이며 1.8px 둥근 선과 코랄 포인트를 사용합니다.
UI 아이콘은 밝은 배경용입니다. 파비콘은 독립 배경이 있어 밝은/어두운 탭에 모두 사용할 수 있습니다.

검증
SVG 파싱, PNG 크기·투명도, ICO의 16/32/48/64px 프레임을 검사했습니다.
preview.png를 직접 확인했습니다. app.py 문법 검사와 AppTest에서 코드 예외는 없었습니다.
AppTest에서는 기존 데이터 조회 실패 안내와 자료 없음 화면이 나타났습니다.
샌드박스가 서버 바인딩과 브라우저 실행을 제한하여 실제 브라우저 탭 검증은 완료하지 못했습니다.
설치된 타입 검사기가 없어 별도 타입 검사는 실행하지 않았습니다.
