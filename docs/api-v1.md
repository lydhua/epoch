# API v1: persistent practice loop

This is a local-development FastAPI/PostgreSQL adapter around `practice/`. It
implements a minimal real study-data loop, not a publicly deployed service. The
frontend is the next product slice; `/docs` is interactive API documentation only.
The API never imports PyTorch or runs training/inference in a request.

## Implemented endpoints

All learning-data endpoints require a verified bearer token. Only health,
readiness, and API documentation are unauthenticated.

| Method/path | Purpose |
| --- | --- |
| `GET /healthz` | Process liveness, without opening a database connection |
| `GET /readyz` | Database access and expected migration revision |
| `POST /collections` | Create an owner-scoped collection |
| `GET /collections` | List the caller's collections |
| `POST /items` | Add a coding problem, flashcard, or exercise |
| `GET /items` | List the caller's items |
| `GET /items/due` | Non-archived items due at the current server time |
| `GET /items/{id}` | Current item and stored schedule |
| `POST /items/{id}/attempts` | Append an attempt and persist its scheduling receipt |
| `GET /items/{id}/attempts` | Read immutable submission receipts |

Lists are arrays with `limit` (1..100, default 50) and `offset` (0..10000, default
0). Ordering is stable by due/creation time and UUID, or collection name and UUID.
Pagination is not a transactional snapshot across separate requests. No collection
or item-create idempotency is promised; only attempt submission has that contract.
Archive, overrides, item editing, deletion/export, and post-submission timing
corrections do not yet have API endpoints.

## Decisions

- **PostgreSQL, not SQLite:** per-item `SELECT FOR UPDATE` serializes read/replay/
  append/update across processes. Unique attempt UUIDs and item/timestamp constraints
  remain database-enforced, not just in-memory checks.
- **Transactional receipts:** attempt, original receipt, and current item schedule
  commit together. A failed schedule update rolls the insertion back. Tests inject
  this failure after insertion and verify a clean retry.
- **Immutable submissions:** no attempt update/delete endpoint exists. The same
  UUID plus the same normalized payload returns the original receipt with status
  200. New attempts return 201. A different payload/item/owner using that UUID
  returns 409. Client-generated UUIDs must be retained across network retries.
- **Historical versus current state:** retries never overwrite a newer schedule.
  Backfilled older attempts are replayed in chronological order; earlier receipts
  stay immutable. `GET /items/{id}` is authoritative for the current schedule.
- **Owner isolation:** the JWT subject determines owner UUID. Every data query is
  scoped to it, and composite foreign keys prevent cross-owner collection/item
  links. Other owners' resources appear as 404, not descriptive authorization errors.
- **Explicit migrations:** Alembic creates the schema. App startup does not create
  or mutate tables. Current schema is compared to metadata in integration tests.
- **Typed boundaries:** input fields reject extras, naive dates, boolean durations,
  nonfinite numbers, and invalid domain content. Timing measurements/corrections
  stay separate; a slow independent solve is not relabeled failure.

JSON input strings are converted into UUIDs, enums, and UTC-aware domain records.
Items retain the original typed content discriminator. Receipts include the
decision, policy version, fingerprint, and exact policy configuration; no card
text or submitted code is needed to schedule. Due-list reads do not reschedule
overdue items or call an ML model.

## Authentication boundary

The prototype verifies **HS256 only**, with an explicit secret of at least 32
bytes, issuer, audience, expiry, issued-at, and UUID subject. There is no insecure
default key and no `X-User-ID` bypass. An unauthenticated request gets 401; invalid
input gets 422; conflicts get 409; database unavailability gets a generic 503.
Secrets/database URLs are omitted from settings representations and error responses.

This is a signed-token boundary, **not a full account system**. The local helper
requires `EPOCH_DEV_TOKENS=1`; it has no HTTP token-minting endpoint. Before public
deployment, choose an identity provider/login flow, adapt token verification to
that provider, and add account lifecycle, key rotation, rate/request limits, TLS,
secrets management, backups/restore, and operational monitoring. Do not expose
this prototype publicly just because signed-token tests pass.

## Local setup

Requirements: Python 3.12/uv, PostgreSQL with UTF-8 encoding, and optional Docker
Compose for the provided local database. Docker is not required if PostgreSQL is
already available. From the repository root:

```sh
uv sync --locked --extra api --group api-test
export EPOCH_POSTGRES_PASSWORD="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export EPOCH_JWT_SECRET="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export EPOCH_DATABASE_URL="postgresql+psycopg://epoch:${EPOCH_POSTGRES_PASSWORD}@localhost:5432/epoch_dev"
docker compose -f infra/compose.yaml up -d --wait db
.venv/bin/alembic -c api/alembic.ini upgrade head
.venv/bin/uvicorn api.app:create_app --factory --host 127.0.0.1 --port 8000
```

The image is pinned to PostgreSQL 17.10 and a verified digest. PostgreSQL binds
only to localhost; its data volume persists. Keep the same database password on
subsequent starts: generating a new environment value does not change an existing
volume's database password. Do not delete the volume to resolve credentials unless
you intend to discard its data.

Uvicorn reads exported environment variables; this setup does not auto-load `.env`.
`.env.example` lists configuration names with no real values. If storing values
in a local `.env`, load it in each terminal and verify it remains ignored. Avoid
mixing `uv run` commands without API extras: they can resync the environment and
remove optional dependencies. The direct `.venv/bin/*` commands above avoid that.

In another terminal with the **same** environment/key, create a local token:

```sh
export EPOCH_DEV_TOKENS=1
export EPOCH_TOKEN="$(.venv/bin/python -m api.dev_token --user 11111111-1111-4111-8111-111111111111)"
```

Open `http://127.0.0.1:8000/docs`, use **Authorize**, then create a collection with
`{"name":"Interview practice"}`. Use its returned ID in `POST /items`:

```json
{
  "collection_id": "<returned collection UUID>",
  "title": "Two Sum",
  "content": {
    "type": "coding_problem",
    "url": "https://leetcode.com/problems/two-sum/",
    "difficulty": "easy"
  },
  "target_seconds": 1800,
  "tags": ["arrays"]
}
```

Submit an attempt with a fresh UUID and an actual timezone-aware occurrence time
at or after item creation, not a copied historical example timestamp:

```json
{
  "id": "<client-generated attempt UUID>",
  "occurred_at": "<actual UTC timestamp, e.g. an ISO 8601 value ending in Z>",
  "outcome": "independent",
  "timing": {"measured_seconds": 2100, "corrected_seconds": 1800},
  "confidence": 4
}
```

Retain that UUID and the same payload if retrying. UI timers remain client-side;
the server accepts explicit timing evidence and does not access LeetCode timers.

## Integration tests

The test database must be disposable and its name must start with `epoch_test`.
Tests create a random private schema, apply real migrations, exercise HTTP and
concurrency, then remove that schema. They never reset an ordinary development or
production database. For the Compose database:

```sh
docker compose -f infra/compose.yaml exec db createdb -U epoch epoch_test_api
export EPOCH_TEST_DATABASE_URL="postgresql+psycopg://epoch:${EPOCH_POSTGRES_PASSWORD}@localhost:5432/epoch_test_api"
.venv/bin/python -m unittest discover -s api/tests -v
```

Without the test URL, integration tests are explicitly skipped, not reported as
passing. CI provides a PostgreSQL 17.10 service. Local validation used a temporary
PostgreSQL 16.2 server over a private Unix socket because Docker is unavailable on
this machine. The Compose configuration has not been run locally. Consult GitHub
Actions for remote results. No local server is left running after tests.

## Next: the frontend

The next slice can now add a React due queue, create-problem form, external problem
links, optional start/pause/resume/reset/edit timer, and outcome submission. Keep a
pending attempt UUID/payload stable for retries and refresh the item's current
schedule after submitting. Start with local development authentication; the actual
production login UX depends on the identity-provider decision. A polished UI does
not need to wait for model experiments, billing, mobile apps, or deployment.
