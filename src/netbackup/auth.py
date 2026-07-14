from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .settings import WEB_AUTH_ENABLED, WEB_HOST, WEB_PASSWORD, WEB_USERNAME

security = HTTPBasic(auto_error=False)
_NETWORK_EXPOSED = WEB_HOST in {"0.0.0.0", "::"}


def require_web_auth(
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    """Require HTTP Basic auth when web credentials are configured."""
    if not WEB_AUTH_ENABLED:
        if _NETWORK_EXPOSED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Authentication is required before exposing the web UI on all network "
                    "interfaces. Set NETBACKUP_WEB_USERNAME and NETBACKUP_WEB_PASSWORD."
                ),
            )
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
