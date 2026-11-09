import os

# AppTest에는 요청 헤더가 없으므로 테스트 환경에서 봇 차단을 끈다.
os.environ.setdefault("CHACHACHA_ALLOW_BOTS", "1")
