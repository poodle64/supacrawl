"""API key authentication dependency."""

import os

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> str | None:
    """Validate Bearer token against ``SUPACRAWL_API_KEY``.

    If the environment variable is **not** set, all requests are allowed
    (open mode). If it **is** set, the request must carry a matching
    ``Authorization: Bearer <token>`` header.

    Returns:
        The validated API key, or ``None`` when auth is disabled.
    """
    expected = os.environ.get("SUPACRAWL_API_KEY")

    if expected is None:
        # Auth disabled; pass all requests through.
        return None

    if credentials is None or credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return credentials.credentials
