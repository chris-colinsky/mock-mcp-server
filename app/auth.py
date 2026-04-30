"""
Bearer-token auth, configured via x-mock-auth at the OAS root.

x-mock-auth:
  type: bearer
  token_env: BEARER_TOKEN     # env var that overrides the configured token
  default: mock-test-token    # used when token_env is unset

If x-mock-auth is absent, the server is unauthenticated.
"""
from __future__ import annotations

import os
from typing import Callable

from fastapi import Depends, HTTPException, Request, status


def build_dependency(auth_spec: dict | None) -> Callable | None:
    """Return a FastAPI dependency that validates the bearer token, or None."""
    if not auth_spec:
        return None
    if auth_spec.get("type") != "bearer":
        raise ValueError(f"unsupported x-mock-auth type: {auth_spec.get('type')!r}")

    expected = os.environ.get(auth_spec.get("token_env", "")) or auth_spec.get("default")
    if not expected:
        raise ValueError("x-mock-auth.bearer requires either an env-resolved value or a 'default'")

    async def verify(request: Request) -> None:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = header[len("Bearer "):].strip()
        if token != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return Depends(verify)
