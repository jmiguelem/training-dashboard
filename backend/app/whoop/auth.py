import secrets
import time
from urllib.parse import urlencode

import httpx

from .. import config
from ..db import get_db

STATE_TTL = 600


def build_login_url() -> str:
    state = secrets.token_urlsafe(8)
    with get_db() as conn:
        conn.execute("DELETE FROM oauth_state WHERE created_at < ?", (time.time() - STATE_TTL,))
        conn.execute(
            "INSERT INTO oauth_state (state, created_at) VALUES (?, ?)", (state, time.time())
        )
    params = {
        "client_id": config.WHOOP_CLIENT_ID,
        "redirect_uri": config.WHOOP_REDIRECT_URI,
        "response_type": "code",
        "scope": config.WHOOP_SCOPES,
        "state": state,
    }
    return f"{config.WHOOP_AUTH_URL}?{urlencode(params)}"


def consume_state(state: str) -> bool:
    with get_db() as conn:
        row = conn.execute("SELECT created_at FROM oauth_state WHERE state = ?", (state,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM oauth_state WHERE state = ?", (state,))
        return time.time() - row["created_at"] <= STATE_TTL


def _store_tokens(data: dict) -> None:
    expires_at = time.time() + int(data.get("expires_in", 3600))
    with get_db() as conn:
        conn.execute(
            """INSERT INTO whoop_token (id, access_token, refresh_token, expires_at)
               VALUES (1, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET access_token = excluded.access_token,
                 refresh_token = excluded.refresh_token, expires_at = excluded.expires_at""",
            (data["access_token"], data["refresh_token"], expires_at),
        )


def exchange_code(code: str) -> None:
    resp = httpx.post(
        config.WHOOP_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config.WHOOP_CLIENT_ID,
            "client_secret": config.WHOOP_CLIENT_SECRET,
            "redirect_uri": config.WHOOP_REDIRECT_URI,
        },
        timeout=30,
    )
    resp.raise_for_status()
    _store_tokens(resp.json())


def _refresh(refresh_token: str) -> None:
    resp = httpx.post(
        config.WHOOP_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config.WHOOP_CLIENT_ID,
            "client_secret": config.WHOOP_CLIENT_SECRET,
            "scope": "offline",
        },
        timeout=30,
    )
    resp.raise_for_status()
    _store_tokens(resp.json())


def get_access_token() -> str | None:
    """Return a valid access token, refreshing if within 60s of expiry. None if not connected."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM whoop_token WHERE id = 1").fetchone()
    if not row:
        return None
    if row["expires_at"] - 60 <= time.time():
        _refresh(row["refresh_token"])
        with get_db() as conn:
            row = conn.execute("SELECT * FROM whoop_token WHERE id = 1").fetchone()
    return row["access_token"]


def is_connected() -> bool:
    with get_db() as conn:
        return conn.execute("SELECT 1 FROM whoop_token WHERE id = 1").fetchone() is not None
