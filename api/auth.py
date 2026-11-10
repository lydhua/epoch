from uuid import UUID

import jwt
from fastapi import HTTPException

from api.config import Settings


def authenticate(token: str, settings: Settings) -> UUID:
    """Verify a fixed algorithm/issuer/audience, then derive ownership from sub."""
    try:
        if len(token) > 8192:
            raise ValueError("token too large")
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        return UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError) as error:
        raise HTTPException(
            401, "Invalid or expired bearer token", headers={"WWW-Authenticate": "Bearer"}
        ) from error
