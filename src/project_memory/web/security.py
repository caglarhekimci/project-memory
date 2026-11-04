import hashlib
import hmac
import secrets
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from project_memory.domain.ports import MemoryStore
from project_memory.settings import Settings


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, maximum: int = 262_144) -> None:
        self.app = app
        self.maximum = maximum

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        messages: list[Message] = []
        count = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            count += len(message.get("body", b""))
            if count > self.maximum:
                await JSONResponse({"detail": "İstek boyutu sınırı aşıldı."}, status_code=413)(
                    scope, receive, send
                )
                return
            messages.append(message)
            if not message.get("more_body", False):
                break
        index = 0

        async def replay() -> Message:
            nonlocal index
            if index < len(messages):
                value = messages[index]
                index += 1
                return value
            return await receive()

        await self.app(scope, replay, send)


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class OwnerAuth:
    def __init__(self, settings: Settings, store: MemoryStore) -> None:
        self.settings = settings
        self.store = store
        self.failures: OrderedDict[str, list[float]] = OrderedDict()
        self.lock = threading.Lock()

    def same_origin(self, request: Request) -> None:
        if request.headers.get("origin") != self.settings.origin:
            raise HTTPException(403, "Bu işlem yalnızca uygulamanın kendi adresinden yapılabilir.")

    def require_owner(self, request: Request) -> None:
        token = request.cookies.get("pm_session", "")
        if (
            not token
            or len(token) > 128
            or not self.store.session_valid(digest_token(token), datetime.now(UTC))
        ):
            raise HTTPException(401, "Oturum açmanız gerekiyor.")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            self.same_origin(request)

    def login(self, request: Request, response: Response, password: str) -> None:
        self.same_origin(request)
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self.lock:
            attempts = [t for t in self.failures.get(ip, []) if now - t < 60]
            if len(attempts) >= 5:
                raise HTTPException(
                    429, "Çok sayıda giriş denemesi yapıldı. Bir dakika sonra tekrar deneyin."
                )
            if not hmac.compare_digest(
                password.encode(), self.settings.app_password.get_secret_value().encode()
            ):
                self.failures[ip] = [*attempts, now]
                while len(self.failures) > 1024:
                    self.failures.popitem(last=False)
                raise HTTPException(401, "Parola doğru değil.")
            self.failures.pop(ip, None)
        token = secrets.token_urlsafe(32)
        previous = request.cookies.get("pm_session", "")
        if previous:
            self.store.revoke_session(digest_token(previous))
        self.store.create_session(digest_token(token), datetime.now(UTC) + timedelta(hours=8))
        response.set_cookie(
            "pm_session",
            token,
            max_age=8 * 3600,
            httponly=True,
            secure=self.settings.origin.startswith("https://"),
            samesite="strict",
            path="/",
        )

    def logout(self, request: Request, response: Response) -> None:
        self.store.revoke_session(digest_token(request.cookies.get("pm_session", "")))
        response.delete_cookie("pm_session", path="/")
