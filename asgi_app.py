from pathlib import Path

from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send
import streamlit as st

from security import BOT_NOTICE, is_blocked_user_agent


SECURITY_HEADERS = {
    b"x-frame-options": b"DENY",
    b"x-content-type-options": b"nosniff",
    b"referrer-policy": b"strict-origin-when-cross-origin",
    b"x-robots-tag": b"noindex, nofollow, noarchive",
}


class SecurityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        async def secured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(name, value) for name, value in message.get("headers", [])
                           if name.lower() not in SECURITY_HEADERS]
                message = {**message, "headers": headers + list(SECURITY_HEADERS.items())}
            await send(message)

        # 검색 제외 규칙은 차단 대상 봇도 읽을 수 있어야 한다.
        is_robots_request = scope["type"] == "http" and scope.get("path") == "/robots.txt"
        if not is_robots_request and is_blocked_user_agent(Headers(scope=scope).get("user-agent")):
            if scope["type"] == "websocket":
                # accept 전에 닫으면 ASGI 서버가 HTTP 403으로 연결을 거절한다.
                await send({"type": "websocket.close", "code": 1008})
            else:
                await PlainTextResponse(BOT_NOTICE, status_code=403)(scope, receive, secured_send)
            return
        await self.app(scope, receive, secured_send)


async def robots_txt(request) -> PlainTextResponse:
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


app = st.App(
    Path(__file__).with_name("app.py"),
    routes=[Route("/robots.txt", robots_txt, methods=["GET", "HEAD"])],
    middleware=[Middleware(SecurityMiddleware)],
)
