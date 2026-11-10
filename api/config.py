import os
from dataclasses import dataclass, field

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def database_url() -> str:
    value = os.environ.get("EPOCH_DATABASE_URL", "")
    validate_database_url(value)
    return value


def validate_database_url(value: str):
    if not isinstance(value, str):
        raise ValueError("EPOCH_DATABASE_URL must be a PostgreSQL connection URL")
    try:
        parsed = make_url(value)
    except ArgumentError as error:
        raise ValueError("EPOCH_DATABASE_URL must be a PostgreSQL connection URL") from error
    if parsed.drivername != "postgresql+psycopg" or not parsed.database:
        raise ValueError("EPOCH_DATABASE_URL must use postgresql+psycopg and name a database")


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    jwt_secret: str = field(repr=False)
    jwt_issuer: str = "epoch-local"
    jwt_audience: str = "epoch-api"

    def __post_init__(self):
        validate_database_url(self.database_url)
        if not isinstance(self.jwt_secret, str) or len(self.jwt_secret.encode()) < 32:
            raise ValueError(
                "EPOCH_JWT_SECRET must contain at least 32 bytes; no default is provided"
            )
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.jwt_issuer, self.jwt_audience)
        ):
            raise ValueError("JWT issuer and audience must be nonempty")

    @classmethod
    def from_env(cls):
        return cls(
            database_url(),
            os.environ.get("EPOCH_JWT_SECRET", ""),
            os.environ.get("EPOCH_JWT_ISSUER", "epoch-local"),
            os.environ.get("EPOCH_JWT_AUDIENCE", "epoch-api"),
        )
