from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .settings import WEB_AUTH_ENABLED, WEB_PASSWORD, WEB_USERNAME

security = HTTPBasic(auto_error=False)


def require_web_auth(
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    """Require HTTP Basic auth when web credentials are configured."""
    if not WEB_AUTH_ENABLED:
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    username_ok = secrets.compare_digest(credentials.username, WEB_USERNAME or "")
    password_ok = secrets.compare_digest(credentials.password, WEB_PASSWORD or "")
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
