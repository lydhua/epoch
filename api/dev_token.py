"""Explicitly enabled local token helper, not a registration/login endpoint."""

import argparse
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from api.config import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", type=UUID, required=True)
    parser.add_argument("--minutes", type=int, default=60)
    args = parser.parse_args()
    if os.environ.get("EPOCH_DEV_TOKENS") != "1":
        parser.exit(1, "Set EPOCH_DEV_TOKENS=1 explicitly for local development only.\n")
    if not 1 <= args.minutes <= 1440:
        parser.exit(1, "Token duration must be 1..1440 minutes.\n")
    try:
        settings = Settings.from_env()
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    now = datetime.now(UTC)
    print(
        jwt.encode(
            {
                "sub": str(args.user),
                "iat": now,
                "exp": now + timedelta(minutes=args.minutes),
                "iss": settings.jwt_issuer,
                "aud": settings.jwt_audience,
            },
            settings.jwt_secret,
            algorithm="HS256",
        )
    )


if __name__ == "__main__":
    main()
