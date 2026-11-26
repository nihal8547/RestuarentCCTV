"""Authentication & roles.

Roles: staff (live ops + acknowledge alerts) < manager (+ analytics, reports, settings view)
       < owner (+ edit settings/zones, users, venues).
Auth is enabled with AUTH_ENABLED=1 or by setting ADMIN_PASSWORD (bootstraps the first owner).
Credentials: `Authorization: Bearer <token>` (from POST /api/auth/login), `?token=` (needed for the
<img> video stream and WebSocket), or HTTP Basic (handy for curl / n8n).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from .config import Settings
from .db import Database

RANK = {"staff": 1, "manager": 2, "owner": 3}
OPEN_PATHS = {"/api/health", "/api/auth/login", "/api/config", "/api/hub/ingest"}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, h_b64 = stored.split("$")
        h = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=2 ** 14, r=8, p=1)
        return hmac.compare_digest(h, base64.b64decode(h_b64))
    except Exception:
        return False


class AuthService:
    def __init__(self, settings: Settings, db: Database):
        self.s = settings
        self.db = db
        self.enabled = settings.auth_enabled
        if self.enabled and settings.admin_password and not db.get_user(settings.admin_user):
            db.create_user(settings.admin_user, hash_password(settings.admin_password), "owner",
                           settings.admin_user.title(), time.time())

    # ---- tokens
    def make_token(self, user: dict) -> str:
        payload = {"u": user["username"], "r": user["role"], "n": user.get("display_name") or user["username"],
                   "exp": time.time() + self.s.token_hours * 3600}
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        sig = hmac.new(self.s.auth_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def parse_token(self, token: str) -> dict | None:
        try:
            body, sig = token.rsplit(".", 1)
            good = hmac.new(self.s.auth_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, good):
                return None
            payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            if payload["exp"] < time.time():
                return None
            return {"username": payload["u"], "role": payload["r"], "name": payload["n"]}
        except Exception:
            return None

    def login(self, username: str, password: str) -> dict | None:
        u = self.db.get_user(username)
        if u and verify_password(password, u["pw_hash"]):
            return u
        return None

    def user_from_scope(self, scope) -> dict | None:
        if not self.enabled:
            return {"username": "local", "role": "owner", "name": "Local"}
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return self.parse_token(auth[7:])
        if auth.lower().startswith("basic "):
            try:
                user, _, pw = base64.b64decode(auth[6:]).decode().partition(":")
            except Exception:
                return None
            u = self.login(user, pw)
            return {"username": u["username"], "role": u["role"], "name": u["display_name"]} if u else None
        q = scope.get("query_string", b"").decode()
        for part in q.split("&"):
            if part.startswith("token="):
                from urllib.parse import unquote
                return self.parse_token(unquote(part[6:]))
        return None


class AuthMiddleware:
    def __init__(self, app, auth: AuthService):
        self.app = app
        self.auth = auth

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path = scope["path"]
        guarded = path.startswith("/api/") or path in ("/video_feed", "/ws")
        if not guarded or path in OPEN_PATHS or (scope["type"] == "http" and scope["method"] == "OPTIONS"):
            scope["user"] = self.auth.user_from_scope(scope)  # may be None; open routes don't need it
            return await self.app(scope, receive, send)
        user = self.auth.user_from_scope(scope)
        if user:
            scope["user"] = user
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = b'{"detail":"Unauthorized"}'
        await send({"type": "http.response.start", "status": 401, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
