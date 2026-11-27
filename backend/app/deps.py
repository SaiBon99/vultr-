"""Auth header dependencies. Constant-time compares; empty configured secrets reject everything."""

import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from app.config import Settings


class ApiError(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str | None = None) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
        self.run_id: str | None = None  # /crawl 502 and 504: the run's transcript id


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def secrets_match(provided: str | None, expected: str) -> bool:
    if not provided or not expected:
        return False
    a = hashlib.sha256(provided.encode()).digest()
    b = hashlib.sha256(expected.encode()).digest()
    return hmac.compare_digest(a, b)


def require_host_secret(
    settings: SettingsDep,
    x_host_secret: Annotated[str | None, Header()] = None,
) -> None:
    if not secrets_match(x_host_secret, settings.HOST_SECRET.get_secret_value()):
        raise ApiError(401, "Missing or invalid X-Host-Secret", "unauthorized")


def require_reviewer_token(
    settings: SettingsDep,
    x_reviewer_token: Annotated[str | None, Header()] = None,
) -> None:
    if not secrets_match(x_reviewer_token, settings.REVIEWER_TOKEN.get_secret_value()):
        raise ApiError(401, "Missing or invalid X-Reviewer-Token", "unauthorized")


def optional_reviewer_ok(
    settings: SettingsDep,
    x_reviewer_token: Annotated[str | None, Header()] = None,
) -> bool:
    return secrets_match(x_reviewer_token, settings.REVIEWER_TOKEN.get_secret_value())


def require_session_token(
    x_session_token: Annotated[str | None, Header()] = None,
) -> str:
    """Returns the raw token. Phase 1 resolves sha256(token) to a session row in the DB."""
    if not x_session_token:
        raise ApiError(401, "Missing or invalid X-Session-Token", "unauthorized")
    return x_session_token


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


HostAuth = Depends(require_host_secret)
ReviewerAuth = Depends(require_reviewer_token)
SessionAuth = Annotated[str, Depends(require_session_token)]
