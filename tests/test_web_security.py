from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from netbackup.web_security import (
    clamp_api_limit,
    generate_csrf_token,
    validate_config_content,
    validate_csrf_token,
)


def test_csrf_token_round_trip():
    token = generate_csrf_token()
    validate_csrf_token(token)


def test_csrf_token_rejects_tampered_signature():
    token = generate_csrf_token()
    parts = token.split(":", 2)
    tampered = f"{parts[0]}:{parts[1]}:deadbeef"
    with pytest.raises(HTTPException) as exc:
        validate_csrf_token(tampered)
    assert exc.value.status_code == 403


def test_csrf_token_rejects_expired_token():
    token = generate_csrf_token()
    parts = token.split(":", 2)
    expired = f"{int(time.time()) - 7200}:{parts[1]}:{parts[2]}"
    with pytest.raises(HTTPException) as exc:
        validate_csrf_token(expired)
    assert exc.value.status_code == 403


def test_validate_config_content_rejects_oversized_payload():
    with pytest.raises(HTTPException) as exc:
        validate_config_content("a" * (256 * 1024 + 1))
    assert exc.value.status_code == 413


def test_validate_config_content_rejects_null_bytes():
    with pytest.raises(HTTPException) as exc:
        validate_config_content("devices:\x00")
    assert exc.value.status_code == 400


def test_clamp_api_limit_bounds_values():
    assert clamp_api_limit(0) == 1
    assert clamp_api_limit(9999) == 500
    assert clamp_api_limit(25) == 25
