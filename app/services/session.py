# app/services/session.py
import os
import hmac
import json
import base64
import hashlib
import time
from typing import Optional, Dict, Any

SESSION_SECRET = os.getenv("SESSION_SECRET") or "OOYyGx1yXg6JdlZoYCpoIV6xCY91mOP4Nt3zMslx9UF1q3jGAi3y-Mw3b_RQ6KMPk2U4kEG6QG_P1Z-2iF5FIQ"
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# 세션 유지 시간 (기본 7일)
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(7 * 24 * 60 * 60)))
COOKIE_NAME = "sl_session"


def _get_secret_bytes() -> bytes:
    if not SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET 환경변수가 설정되어 있지 않습니다.")
    return SESSION_SECRET.encode("utf-8")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_session_token(user_id: int) -> str:
    """
    user_id를 담은 서명된 세션 토큰 생성.
    형식: base64url(payload).base64url(signature)
    """
    now = int(time.time())
    payload: Dict[str, Any] = {
        "uid": user_id,
        "iat": now,
        "exp": now + SESSION_TTL_SECONDS,
        "rnd": os.urandom(8).hex(),  # 매번 랜덤
    }

    payload_bytes = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    secret = _get_secret_bytes()
    sig = hmac.new(secret, payload_bytes, hashlib.sha256).digest()

    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(sig)}"


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """
    토큰 검증 → 유효하면 payload(dict), 아니면 None.
    """
    if not token:
        return None

    try:
        payload_b64, sig_b64 = token.split(".")
    except ValueError:
        return None

    try:
        payload_bytes = _b64url_decode(payload_b64)
        sig_provided = _b64url_decode(sig_b64)

        secret = _get_secret_bytes()
        sig_expected = hmac.new(secret, payload_bytes, hashlib.sha256).digest()

        if not hmac.compare_digest(sig_provided, sig_expected):
            return None

        payload = json.loads(payload_bytes.decode("utf-8"))
        exp = payload.get("exp")
        if not isinstance(exp, int) or exp < int(time.time()):
            return None

        return payload
    except Exception:
        return None