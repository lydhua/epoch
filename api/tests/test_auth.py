import os
import subprocess
import sys
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.app import create_app
from api.auth import authenticate
from api.config import Settings

TEST_SECRET = "synthetic-test-secret-not-for-use-" * 2


def token(settings, owner, **changes):
    now = datetime.now(UTC)
    claims = {
        "sub": str(owner),
        "iat": now,
        "exp": now + timedelta(hours=1),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(claims | changes, settings.jwt_secret, algorithm="HS256")


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings("postgresql+psycopg://localhost/epoch_test", TEST_SECRET)
        self.owner = uuid4()

    def test_signed_subject_and_claim_validation(self):
        self.assertEqual(authenticate(token(self.settings, self.owner), self.settings), self.owner)
        invalid = [
            token(self.settings, self.owner, exp=datetime.now(UTC) - timedelta(seconds=1)),
            token(self.settings, self.owner, aud="other"),
            token(self.settings, self.owner, iss="other"),
            token(self.settings, self.owner, sub="not-a-uuid"),
            token(self.settings, self.owner, iat=datetime.now(UTC) + timedelta(hours=1)),
            jwt.encode({"sub": str(self.owner)}, TEST_SECRET, algorithm="HS256"),
            jwt.encode({"sub": str(self.owner)}, "different-synthetic-key-" * 3, algorithm="HS256"),
            jwt.encode({"sub": str(self.owner)}, TEST_SECRET, algorithm="HS512"),
            "bad.token",
            "x" * 8193,
        ]
        for candidate in invalid:
            with self.subTest(candidate=candidate[:12]), self.assertRaises(HTTPException) as error:
                authenticate(candidate, self.settings)
            self.assertEqual(error.exception.status_code, 401)

    def test_no_default_secret_or_non_postgres_database(self):
        for database, secret in (
            (self.settings.database_url, "short"),
            ("sqlite:///test.db", TEST_SECRET),
        ):
            with self.assertRaises(ValueError):
                Settings(database, secret)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()
        self.assertNotIn(TEST_SECRET, repr(self.settings))

    def test_health_openapi_and_unauthenticated_requests_need_no_database(self):
        with TestClient(create_app(self.settings)) as client:
            self.assertEqual(client.get("/healthz").status_code, 200)
            self.assertEqual(client.get("/items").status_code, 401)
            self.assertEqual(
                client.get("/items", headers={"X-User-ID": str(self.owner)}).status_code, 401
            )
            self.assertIn("/items/{item_id}/attempts", client.get("/openapi.json").json()["paths"])

    def test_dev_token_helper_requires_explicit_enablement(self):
        arguments = [sys.executable, "-m", "api.dev_token", "--user", str(self.owner)]
        env = os.environ | {
            "EPOCH_DATABASE_URL": self.settings.database_url,
            "EPOCH_JWT_SECRET": TEST_SECRET,
            "EPOCH_JWT_ISSUER": self.settings.jwt_issuer,
            "EPOCH_JWT_AUDIENCE": self.settings.jwt_audience,
        }
        env.pop("EPOCH_DEV_TOKENS", None)
        disabled = subprocess.run(arguments, env=env, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(disabled.returncode, 0)
        self.assertEqual(disabled.stdout, "")
        enabled = subprocess.run(
            arguments,
            env=env | {"EPOCH_DEV_TOKENS": "1"},
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        self.assertEqual(authenticate(enabled.stdout.strip(), self.settings), self.owner)

    def test_invalid_json_values_return_validation_errors_without_echoing_input(self):
        headers = {
            "Authorization": "Bearer " + token(self.settings, self.owner),
            "Content-Type": "application/json",
        }
        bodies = [
            '{"name":"private content\\u0000"}',
            '{"name":"private content\\ud800"}',
            '{"name":1e999}',
            '{"name":NaN}',
            '{"name":"valid", "\\ud800":0}',
        ]
        with TestClient(create_app(self.settings)) as client:
            for body in bodies:
                with self.subTest(body=body):
                    response = client.post("/collections", content=body, headers=headers)
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertNotIn("private content", response.text)


if __name__ == "__main__":
    unittest.main()
