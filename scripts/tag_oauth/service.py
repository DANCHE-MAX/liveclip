#!/usr/bin/env python3
"""Minimal local Qianchuan OAuth/API bridge.

Bound to loopback only. Secrets and tokens are stored in macOS Keychain and
are never written to logs or response bodies.
"""

from __future__ import annotations

import json
import hashlib
import os
import secrets
import subprocess
import threading
import urllib.parse
import urllib.request
import urllib.error
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


APP_ID = os.environ.get("QIANCHUAN_APP_ID", "9000000000000008")
REDIRECT_URI = os.environ.get("QIANCHUAN_REDIRECT_URI", "http://127.0.0.1:8080/callback")
HOST = "127.0.0.1"
PORT = int(os.environ.get("QIANCHUAN_OAUTH_PORT", "8080"))
ACCESS_SERVICE = "liveclip-example-tags-access-token"
REFRESH_SERVICE = "liveclip-example-tags-refresh-token"
SECRET_SERVICE = "liveclip-example-tags-app-secret"
ACCOUNT_ID = os.environ.get("QIANCHUAN_ACCOUNT_ID", "9000000000000005")
TOKEN_KEYCHAIN_ACCOUNT = APP_ID
SECRET_KEYCHAIN_ACCOUNT = APP_ID
AUTH_URL = "https://open.oceanengine.com/audit/oauth.html"
TOKEN_URL = "https://ad.oceanengine.com/open_api/oauth2/access_token/"
REFRESH_URL = "https://ad.oceanengine.com/open_api/oauth2/refresh_token/"
TYPE_URL = "https://api.oceanengine.com/open_api/v3.0/tools/ebp/video/tags/list/"

_state_lock = threading.Lock()
_state = None
_callback_key = None
_callback_result = None
_callback_done = threading.Event()


def _keychain_account(service: str) -> str:
    return SECRET_KEYCHAIN_ACCOUNT if service == SECRET_SERVICE else TOKEN_KEYCHAIN_ACCOUNT


def _keychain_read(service: str) -> str | None:
    try:
        p = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", _keychain_account(service), "-w"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    value = p.stdout.strip()
    return value or None


def _keychain_write(service: str, value: str) -> None:
    subprocess.run(
        ["security", "add-generic-password", "-U", "-s", service, "-a", _keychain_account(service), "-w", value],
        check=True,
        capture_output=True,
        text=True,
    )


def _json_request(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "ExampleBrand-Qianchuan-OAuth/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(1_000_000)
    except urllib.error.HTTPError as exc:
        raw = exc.read(1_000_000)
        try:
            body = json.loads(raw.decode("utf-8"))
            if isinstance(body, dict):
                return body
        except Exception:
            pass
        return {"code": exc.code, "message": "token endpoint returned HTTP error"}
    parsed = json.loads(raw.decode("utf-8"))
    return parsed if isinstance(parsed, dict) else {"code": -1, "message": "invalid response"}


def _safe_result(data: dict) -> dict:
    """Return only non-secret status fields."""
    out = {"code": data.get("code"), "message": data.get("message", "")}
    if data.get("request_id"):
        out["request_id"] = data["request_id"]
    token_data = data.get("data")
    if isinstance(token_data, dict):
        for key in ("expires_in", "refresh_token_expires_in"):
            if key in token_data:
                out[key] = token_data[key]
    return out


def _exchange_auth_code(auth_code: str) -> dict:
    app_secret = _keychain_read(SECRET_SERVICE)
    if not app_secret:
        return {"code": 40190, "message": f"missing Keychain secret: {SECRET_SERVICE}"}
    data = _json_request(
        TOKEN_URL,
        {"app_id": int(APP_ID), "secret": app_secret, "grant_type": "auth_code", "auth_code": auth_code},
    )
    token_data = data.get("data")
    if data.get("code") == 0 and isinstance(token_data, dict):
        access = token_data.get("access_token")
        refresh = token_data.get("refresh_token")
        # Some Ocean Engine token responses may omit one rotated token.
        # Persist each returned credential independently so a fresh access
        # token is never discarded merely because refresh_token is absent.
        if access:
            _keychain_write(ACCESS_SERVICE, access)
        if refresh:
            _keychain_write(REFRESH_SERVICE, refresh)
    return _safe_result(data)


def _refresh_token() -> dict:
    app_secret = _keychain_read(SECRET_SERVICE)
    refresh = _keychain_read(REFRESH_SERVICE)
    if not app_secret:
        return {"code": 40190, "message": f"missing Keychain secret: {SECRET_SERVICE}"}
    if not refresh:
        return {"code": 40191, "message": f"missing Keychain refresh token: {REFRESH_SERVICE}"}
    data = _json_request(
        REFRESH_URL,
        {"app_id": int(APP_ID), "secret": app_secret, "grant_type": "refresh_token", "refresh_token": refresh},
    )
    token_data = data.get("data")
    if data.get("code") == 0 and isinstance(token_data, dict):
        access = token_data.get("access_token")
        new_refresh = token_data.get("refresh_token")
        if access:
            _keychain_write(ACCESS_SERVICE, access)
        if new_refresh:
            _keychain_write(REFRESH_SERVICE, new_refresh)
    return _safe_result(data)


def _probe_account() -> dict:
    access = _keychain_read(ACCESS_SERVICE)
    if not access:
        return {"code": 40101, "message": "missing access token"}
    qs = urllib.parse.urlencode({"account_id": 9000000000000006, "account_type": "EBP", "material_ids": json.dumps([9000000000000010])})
    req = urllib.request.Request(
        f"{TYPE_URL}?{qs}",
        headers={"Access-Token": access, "User-Agent": "ExampleBrand-Qianchuan-OAuth/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(1_000_000)
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # no secret in exception text
        return {"code": 50001, "message": f"probe failed: {type(exc).__name__}"}
    safe = _safe_result(data)
    if data.get("code") == 0:
        body = data.get("data") or {}
        if isinstance(body.get("data"), dict):
            body = body["data"]
        safe["materials"] = body.get("materials", [])
        safe["errors"] = body.get("errors", [])
        if safe["errors"] or not safe["materials"]:
            safe["platform_code"] = 0
            safe["code"] = 40001
            safe["message"] = "标签接口可访问，但目标素材不可核实"
    return safe


class Handler(BaseHTTPRequestHandler):
    server_version = "ExampleBrand-Qianchuan-OAuth/1.0"

    def log_message(self, fmt, *args):  # never log query strings/auth codes
        print(f"[qianchuan-oauth] {self.command} {self.path.split('?', 1)[0]}", flush=True)

    def _send(self, status: int, body: str, content_type: str = "text/html; charset=utf-8"):
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        global _state, _callback_key, _callback_result, _callback_done
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send(
                HTTPStatus.OK,
                json.dumps(
                    {
                        "ok": True,
                        "listen": f"{HOST}:{PORT}",
                        "app_id": APP_ID,
                        "secret_present": bool(_keychain_read(SECRET_SERVICE)),
                        "access_token_present": bool(_keychain_read(ACCESS_SERVICE)),
                        "refresh_token_present": bool(_keychain_read(REFRESH_SERVICE)),
                    },
                    ensure_ascii=False,
                ),
                "application/json; charset=utf-8",
            )
            return

        if parsed.path == "/start":
            with _state_lock:
                _state = secrets.token_urlsafe(24)
                _callback_key = None
                _callback_result = None
                _callback_done = threading.Event()
                state = _state
            params = {
                "app_id": APP_ID,
                "is_new_connect": "0",
                "is_new_user": "0",
                "material_auth": "1",
                "state": state,
            }
            location = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", location)
            self.end_headers()
            return

        if parsed.path == "/callback":
            auth_code = query.get("auth_code", [""])[0]
            returned_state = query.get("state", [""])[0]
            material_status = query.get("material_auth_status", ["0"])[0]
            if not auth_code:
                self._send(HTTPStatus.BAD_REQUEST, "缺少 auth_code，未执行任何 token 操作。")
                return
            fingerprint = hashlib.sha256((returned_state + '\0' + auth_code).encode()).hexdigest()
            with _state_lock:
                if not _state or not secrets.compare_digest(returned_state, _state):
                    self._send(HTTPStatus.BAD_REQUEST, "state 校验失败，已拒绝该回调。")
                    return
                if _callback_key and _callback_key != fingerprint:
                    self._send(HTTPStatus.BAD_REQUEST, "授权回调不匹配，已拒绝。")
                    return
                owner = _callback_key is None
                if owner:
                    _callback_key = fingerprint
                done = _callback_done
            if not owner:
                if not done.wait(30):
                    self._send(HTTPStatus.ACCEPTED, "授权处理中，请稍后查看状态。")
                    return
                with _state_lock:
                    result = _callback_result
                self._send(HTTPStatus.OK, json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
                return
            try:
                result = _exchange_auth_code(auth_code) if material_status == "1" else {"code": 40301, "message": "素材权限未授权"}
            except Exception as exc:
                result = {"code": 50002, "message": f"token exchange failed: {type(exc).__name__}"}
            with _state_lock:
                if done is _callback_done:
                    _callback_result = result
                done.set()
            self._send(HTTPStatus.OK, json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if parsed.path == "/callback-status":
            with _state_lock:
                result = _callback_result if _callback_result is not None else {"status": "pending" if _callback_key else "not_received"}
            self._send(HTTPStatus.OK, json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if parsed.path == "/refresh":
            try:
                result = _refresh_token()
            except Exception as exc:
                result = {"code": 50003, "message": f"refresh failed: {type(exc).__name__}"}
            self._send(HTTPStatus.OK, json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if parsed.path == "/probe":
            self._send(HTTPStatus.OK, json.dumps(_probe_account(), ensure_ascii=False), "application/json; charset=utf-8")
            return

        self._send(HTTPStatus.NOT_FOUND, "Not found")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[qianchuan-oauth] listening on http://{HOST}:{PORT}", flush=True)
    print(f"[qianchuan-oauth] open http://{HOST}:{PORT}/start to authorize", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
