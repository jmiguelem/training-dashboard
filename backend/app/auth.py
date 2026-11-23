"""Single-user password login with a signed, expiring session cookie.

Fail closed: if DASHBOARD_PASSWORD is not set, every protected route returns 503.
"""

import hashlib
import hmac
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import config

COOKIE = "td_session"
# Reachable without a session: liveness probe and the login endpoints themselves.
PUBLIC_PATHS = {"/health", "/api/auth/login", "/api/auth/logout", "/api/auth/session"}

router = APIRouter(prefix="/api/auth")

_failures: dict[str, list[float]] = {}
MAX_FAILURES = 5
WINDOW_S = 300


def _key() -> bytes:
    # Derived from the password (or an explicit secret), so changing it logs everyone out.
    seed = config.SESSION_SECRET or config.DASHBOARD_PASSWORD
    return hashlib.sha256(b"training-dashboard-session:" + seed.encode()).digest()


def _sign(payload: str) -> str:
    return hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(now: float | None = None) -> str:
    expires = int((now or time.time()) + config.SESSION_DAYS * 86400)
    return f"{expires}.{_sign(str(expires))}"


def valid_token(token: str | None, now: float | None = None) -> bool:
    if not token or not config.DASHBOARD_PASSWORD:
        return False
    expires, _, sig = token.partition(".")
    if not expires.isdigit() or not hmac.compare_digest(sig, _sign(expires)):
        return False
    return int(expires) > (now or time.time())


def is_authenticated(request: Request) -> bool:
    return valid_token(request.cookies.get(COOKIE))


async def require_login(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in PUBLIC_PATHS:
        return await call_next(request)
    if not (path.startswith("/api/") or path.startswith("/auth/")):
        return await call_next(request)
    if not config.DASHBOARD_PASSWORD:
        return JSONResponse(
            {"detail": "Server is locked: set DASHBOARD_PASSWORD in .env"}, status_code=503
        )
    if not is_authenticated(request):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return await call_next(request)


def _locked_out(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _failures.get(ip, []) if now - t < WINDOW_S]
    _failures[ip] = recent
    return len(recent) >= MAX_FAILURES


class LoginBody(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    if not config.DASHBOARD_PASSWORD:
        raise HTTPException(503, "Server is locked: set DASHBOARD_PASSWORD in .env")
    ip = request.client.host if request.client else "unknown"
    if _locked_out(ip):
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    if not secrets.compare_digest(
        body.password.encode(), config.DASHBOARD_PASSWORD.encode()
    ):
        _failures.setdefault(ip, []).append(time.time())
        raise HTTPException(401, "Wrong password")
    _failures.pop(ip, None)
    response.set_cookie(
        COOKIE,
        make_token(),
        max_age=config.SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/session")
def session(request: Request):
    return {"authenticated": is_authenticated(request)}
