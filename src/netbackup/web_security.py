from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .settings import WEB_PASSWORD

_MAX_CONFIG_BYTES = 256 * 1024
_MAX_LOG_BYTES = 512 * 1024
_MAX_API_RUNS_LIMIT = 500
_CSRF_MAX_AGE_SECONDS = 3600

_rate_limit_buckets: dict[str, list[float]] = defaultdict(list)

_CSRF_SECRET = (
    os.getenv("NETBACKUP_CSRF_SECRET")
    or WEB_PASSWORD
    or os.getenv("NETBACKUP_DEFAULT_API_KEY")
    or "netbackup-dev-csrf-secret"
)


def generate_csrf_token() -> str:
    """Return an HMAC-signed CSRF token valid for one hour."""
    nonce = secrets.token_hex(16)
    issued_at = str(int(time.time()))
    payload = f"{issued_at}:{nonce}"
    signature = hmac.new(
        _CSRF_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}:{signature}"


def validate_csrf_token(token: str | None) -> None:
    """Reject missing, malformed, expired, or tampered CSRF tokens."""
    if not token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token required")

    parts = token.split(":", 2)
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    issued_at_text, nonce, signature = parts
    try:
        issued_at = int(issued_at_text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token"
        ) from exc

    if time.time() - issued_at > _CSRF_MAX_AGE_SECONDS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token expired")

    payload = f"{issued_at_text}:{nonce}"
    expected = hmac.new(
        _CSRF_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not secrets.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def enforce_rate_limit(request: Request, *, scope: str, max_requests: int, window_seconds: float) -> None:
    """Apply a simple in-memory per-client rate limit."""
    client_host = request.client.host if request.client else "unknown"
    bucket_key = f"{scope}:{client_host}"
    now = time.time()
    window_start = now - window_seconds
    recent = [timestamp for timestamp in _rate_limit_buckets[bucket_key] if timestamp > window_start]
    if len(recent) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
        )
    recent.append(now)
    _rate_limit_buckets[bucket_key] = recent


def clamp_api_limit(limit: int) -> int:
    """Bound list endpoints to a safe maximum."""
    if limit < 1:
        return 1
    return min(limit, _MAX_API_RUNS_LIMIT)


def validate_config_content(content: str) -> None:
    """Reject oversized inventory payloads before they hit disk."""
    encoded = content.encode("utf-8")
    if len(encoded) > _MAX_CONFIG_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Config file exceeds {_MAX_CONFIG_BYTES // 1024} KB limit",
        )
    if "\x00" in content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Config contains invalid characters")


def read_tail_bytes(path: str, max_bytes: int = _MAX_LOG_BYTES) -> str:
    """Read only the trailing portion of a log file."""
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        data = handle.read()
    return data.decode("utf-8", errors="replace")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach baseline security headers to every response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )
        return response
