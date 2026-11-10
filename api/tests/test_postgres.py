import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

from api.app import create_app
from api.config import Settings, validate_database_url
from api.db import attempts, collections, items
from api.tests.test_auth import TEST_SECRET, token

DATABASE = os.environ.get("EPOCH_TEST_DATABASE_URL")


@unittest.skipUnless(
    DATABASE, "set EPOCH_TEST_DATABASE_URL to a disposable PostgreSQL test database"
)
class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        validate_database_url(DATABASE)
        if not sa.engine.make_url(DATABASE).database.startswith("epoch_test"):
            raise ValueError("test database name must start with epoch_test")
        cls.schema = "api_test_" + uuid4().hex
        cls.admin = sa.create_engine(DATABASE)
        with cls.admin.begin() as connection:
            connection.execute(sa.schema.CreateSchema(cls.schema))
        cls.engine = sa.create_engine(
            DATABASE, connect_args={"options": f"-csearch_path={cls.schema}"}
        )
        cls.migrate("upgrade", "head")

    @classmethod
    def migrate(cls, operation, revision=None):
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with cls.engine.begin() as connection:
            config.attributes["connection"] = connection
            if revision is None:
                getattr(command, operation)(config)
            else:
                getattr(command, operation)(config, revision)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.begin() as connection:
            connection.execute(sa.schema.DropSchema(cls.schema, cascade=True))
        cls.admin.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            for table in (attempts, items, collections):
                connection.execute(table.delete())
        self.settings = Settings(DATABASE, TEST_SECRET)
        self.owner, self.other = uuid4(), uuid4()
        self.now = datetime(2026, 1, 1, tzinfo=UTC)
        self.app = create_app(self.settings, engine=self.engine, clock=lambda: self.now)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + token(self.settings, self.owner)}
        self.other_headers = {"Authorization": "Bearer " + token(self.settings, self.other)}
        response = self.client.post("/collections", json={"name": "Practice"}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        self.collection = response.json()["id"]

    def problem(self, **changes):
        body = {
            "collection_id": self.collection,
            "title": "Two Sum",
            "content": {
                "type": "coding_problem",
                "url": "https://leetcode.com/problems/two-sum/",
                "difficulty": "medium",
            },
        }
        response = self.client.post("/items", json=body | changes, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def event(self, **changes):
        return {
            "id": str(uuid4()),
            "occurred_at": self.now.isoformat(),
            "outcome": "independent",
        } | changes

    def submit(self, identity, event, headers=None):
        return self.client.post(
            f"/items/{identity}/attempts",
            json=event,
            headers=self.headers if headers is None else headers,
        )

    def test_practice_loop_and_due_dates(self):
        record = self.problem(target_seconds=1800)
        self.assertEqual(
            self.client.get("/items/due", headers=self.headers).json()[0]["id"], record["id"]
        )
        receipt = self.submit(record["id"], self.event(timing={"measured_seconds": 2400}))
        self.assertEqual(receipt.status_code, 201, receipt.text)
        decision = receipt.json()["decision"]
        self.assertEqual(decision["state"], "consolidating")
        self.assertFalse(decision["time_goal_met"])
        self.assertEqual(self.client.get("/items/due", headers=self.headers).json(), [])
        self.now += timedelta(days=1)
        receipt = self.submit(record["id"], self.event())
        self.assertEqual(receipt.json()["decision"]["state"], "maintenance")
        self.assertEqual(
            len(self.client.get(f"/items/{record['id']}/attempts", headers=self.headers).json()), 2
        )
        self.now += timedelta(days=8)
        self.assertTrue(
            self.client.get(f"/items/{record['id']}", headers=self.headers).json()["is_due"]
        )
        self.assertEqual(self.client.get("/readyz").status_code, 200)

    def test_retry_returns_original_receipt_without_rewriting_newer_schedule(self):
        record = self.problem()
        first = self.event(timing={"measured_seconds": 1200, "corrected_seconds": 600})
        original = self.submit(record["id"], first)
        self.now += timedelta(days=1)
        self.assertEqual(self.submit(record["id"], self.event()).status_code, 201)
        before = self.client.get(f"/items/{record['id']}", headers=self.headers).json()
        retry = self.submit(record["id"], first)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json(), original.json())
        self.assertEqual(
            self.client.get(f"/items/{record['id']}", headers=self.headers).json(), before
        )
        self.assertEqual(
            self.submit(record["id"], first | {"outcome": "not_solved"}).status_code, 409
        )

    def test_ownership_is_enforced_everywhere_and_in_foreign_keys(self):
        record = self.problem()
        for path in (f"/items/{record['id']}", f"/items/{record['id']}/attempts"):
            self.assertEqual(self.client.get(path, headers=self.other_headers).status_code, 404)
        for path in ("/items", "/items/due", "/collections"):
            self.assertEqual(self.client.get(path, headers=self.other_headers).json(), [])
        self.assertEqual(
            self.submit(record["id"], self.event(), self.other_headers).status_code, 404
        )
        self.assertEqual(
            self.client.post(
                "/items",
                json={
                    "collection_id": self.collection,
                    "title": "Other",
                    "content": {"type": "exercise", "instructions": "Explain"},
                },
                headers=self.other_headers,
            ).status_code,
            404,
        )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                items.insert().values(
                    id=uuid4(),
                    owner_id=self.other,
                    collection_id=UUID(self.collection),
                    payload={},
                    created_at=self.now,
                    archived=False,
                    next_due_at=self.now,
                    current_schedule={},
                )
            )

    def test_validation_and_failed_attempts_leave_no_partial_writes(self):
        record = self.problem()
        for changes in (
            {"occurred_at": "2026-01-01T00:00:00"},
            {"occurred_at": (self.now + timedelta(days=1)).isoformat()},
            {"owner_id": str(self.other)},
            {"timing": {"measured_seconds": True}},
            {"confidence": True},
            {"timing": {"corrected_seconds": -1}},
        ):
            response = self.submit(record["id"], self.event(**changes))
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(
            self.client.get(f"/items/{record['id']}/attempts", headers=self.headers).json(), []
        )
        self.assertEqual(
            self.client.get(f"/items/{record['id']}", headers=self.headers).json()["schedule"],
            record["schedule"],
        )

    def test_concurrent_duplicate_and_distinct_attempts(self):
        record = self.problem()
        event = self.event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.submit(record["id"], event), range(2)))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 201])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.now += timedelta(days=10)
        one = self.event(occurred_at=(self.now - timedelta(days=2)).isoformat())
        two = self.event(occurred_at=(self.now - timedelta(days=1)).isoformat())
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda event: self.submit(record["id"], event), [one, two]))
        self.assertEqual([r.status_code for r in responses], [201, 201])
        current = self.client.get(f"/items/{record['id']}", headers=self.headers).json()
        self.assertEqual(current["schedule"]["decision"]["attempts"], 3)
        self.assertEqual(
            len(self.client.get(f"/items/{record['id']}/attempts", headers=self.headers).json()), 3
        )

    def test_same_timestamp_conflict_and_cross_item_idempotency_conflict(self):
        record, second = self.problem(), self.problem()
        event = self.event()
        self.assertEqual(self.submit(record["id"], event).status_code, 201)
        self.assertEqual(self.submit(record["id"], self.event()).status_code, 422)
        self.assertEqual(self.submit(second["id"], event).status_code, 409)
        self.assertEqual(
            self.client.get(f"/items/{second['id']}/attempts", headers=self.headers).json(), []
        )

    def test_schedule_update_failure_rolls_back_insert_and_allows_retry(self):
        record = self.problem()
        event = self.event()

        def fail_update(connection, cursor, statement, parameters, context, many):
            if statement.startswith("UPDATE items "):
                raise OperationalError(statement, parameters, RuntimeError("synthetic failure"))

        sa.event.listen(self.engine, "before_cursor_execute", fail_update)
        try:
            response = self.submit(record["id"], event)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("synthetic failure", response.text)
        finally:
            sa.event.remove(self.engine, "before_cursor_execute", fail_update)
        self.assertEqual(
            self.client.get(f"/items/{record['id']}/attempts", headers=self.headers).json(), []
        )
        self.assertEqual(
            self.client.get(f"/items/{record['id']}", headers=self.headers).json()["schedule"],
            record["schedule"],
        )
        self.assertEqual(self.submit(record["id"], event).status_code, 201)

    def test_validation_clock_is_read_after_the_item_lock(self):
        record = self.problem()
        event = self.event(occurred_at=(self.now + timedelta(seconds=1)).isoformat())

        def advance_while_locking(connection, cursor, statement, parameters, context, many):
            if "FROM items" in statement and "FOR UPDATE" in statement:
                self.now += timedelta(seconds=2)

        sa.event.listen(self.engine, "after_cursor_execute", advance_while_locking)
        try:
            response = self.submit(record["id"], event)
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(
                datetime.fromisoformat(response.json()["decision"]["evaluated_at"]), self.now
            )
        finally:
            sa.event.remove(self.engine, "after_cursor_execute", advance_while_locking)

    def test_concurrent_cross_item_uuid_conflict_does_not_update_losing_item(self):
        first, second = self.problem(), self.problem()
        event = self.event()
        barrier = Barrier(2)

        def pause_empty_id_lookup(connection, cursor, statement, parameters, context, many):
            if "WHERE attempts.id =" in statement and not connection.info.get("paused_lookup"):
                connection.info["paused_lookup"] = True
                barrier.wait(timeout=10)

        sa.event.listen(self.engine, "after_cursor_execute", pause_empty_id_lookup)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(
                    pool.map(lambda record: self.submit(record["id"], event), [first, second])
                )
        finally:
            sa.event.remove(self.engine, "after_cursor_execute", pause_empty_id_lookup)
        self.assertEqual(sorted(r.status_code for r in responses), [201, 409])
        loser = [first, second][[r.status_code for r in responses].index(409)]
        current = self.client.get(f"/items/{loser['id']}", headers=self.headers).json()
        self.assertEqual(current["schedule"], loser["schedule"])
        self.assertEqual(
            self.client.get(f"/items/{loser['id']}/attempts", headers=self.headers).json(), []
        )

    def test_non_card_content_and_pagination(self):
        self.problem(content={"type": "flashcard", "front": "Q", "back": "A"})
        self.problem(content={"type": "exercise", "instructions": "Explain"})
        self.assertEqual(len(self.client.get("/items?limit=1", headers=self.headers).json()), 1)
        self.assertEqual(
            len(self.client.get("/items?limit=1&offset=1", headers=self.headers).json()), 1
        )
        self.assertEqual(self.client.get("/items?limit=101", headers=self.headers).status_code, 422)

    def test_migration_round_trip_and_metadata_match(self):
        self.migrate("check")
        self.migrate("downgrade", "base")
        self.assertEqual(self.client.get("/readyz").status_code, 503)
        self.migrate("upgrade", "head")
        self.assertEqual(self.client.get("/readyz").status_code, 200)
        self.migrate("check")

    def test_alembic_cli_uses_environment_without_auth_settings(self):
        url = sa.engine.make_url(DATABASE).update_query_dict(
            {"options": f"-csearch_path={self.schema}"}
        )
        env = os.environ | {"EPOCH_DATABASE_URL": url.render_as_string(hide_password=False)}
        env.pop("EPOCH_JWT_SECRET", None)
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "api/alembic.ini", "current"],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0001_practice", result.stdout)

    def test_revision_template_generates_valid_migration_without_editing_project(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(__file__).resolve().parents[1]
            scripts = Path(directory) / "migrations"
            shutil.copytree(source / "migrations", scripts)
            config = Config(str(source / "alembic.ini"))
            config.set_main_option("script_location", str(scripts))
            with self.engine.begin() as connection:
                config.attributes["connection"] = connection
                revision = command.revision(config, message="schema check", autogenerate=True)
            self.assertTrue(Path(revision.path).is_file())
            ast.parse(Path(revision.path).read_text())


if __name__ == "__main__":
    unittest.main()
