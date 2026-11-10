import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Callable
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from api.auth import authenticate
from api.config import Settings
from api.db import attempts, collections, items
from api.schemas import AttemptCreate, CollectionCreate, ItemCreate
from practice.models import Collection, utc, validate_membership
from practice.scheduler import Policy, schedule

bearer = HTTPBearer(auto_error=False)
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10_000)]


def create_app(
    settings: Settings | None = None,
    *,
    engine=None,
    clock: Callable[[], datetime] | None = None,
    policy: Policy | None = None,
) -> FastAPI:
    settings = Settings.from_env() if settings is None else settings
    owns_engine = engine is None
    engine = (
        sa.create_engine(settings.database_url, pool_pre_ping=True) if engine is None else engine
    )
    if engine.dialect.name != "postgresql":
        raise ValueError("the API requires PostgreSQL; SQLite is not a substitute for row locking")
    clock = (lambda: datetime.now(UTC)) if clock is None else clock
    policy = Policy() if policy is None else policy

    @asynccontextmanager
    async def lifespan(app):
        yield
        if owns_engine:
            engine.dispose()

    app = FastAPI(title="Epoch API", version="0.1.0", lifespan=lifespan)

    def owner(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> UUID:
        if credentials is None:
            raise HTTPException(
                401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"}
            )
        return authenticate(credentials.credentials, settings)

    Owner = Annotated[UUID, Depends(owner)]

    def now():
        return utc(clock(), "server clock")

    def domain(call):
        try:
            return call()
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    def owned_item(connection, identity, owner_id, *, lock=False):
        query = sa.select(items).where(items.c.id == identity, items.c.owner_id == owner_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        if row is None:
            raise HTTPException(404, "Item not found")
        return row

    def item_domain(row):
        return ItemCreate.model_validate(row["payload"]).domain(
            row["id"], row["owner_id"], row["created_at"], row["archived"]
        )

    def item_view(row, evaluated_at):
        return dict(
            id=row["id"],
            **row["payload"],
            created_at=row["created_at"],
            archived=row["archived"],
            schedule=row["current_schedule"],
            is_due=not row["archived"] and row["next_due_at"] <= evaluated_at,
        )

    def replay_receipt(row, event, digest):
        if (row["owner_id"], row["item_id"], row["payload_hash"]) != (
            event.owner_id,
            event.item_id,
            digest,
        ):
            raise HTTPException(409, "Attempt ID already has a different payload")
        return JSONResponse(row["receipt"], status_code=200)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, error):
        return JSONResponse({"detail": "Conflicting database record"}, status_code=409)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Raw inputs may contain nonfinite numbers or invalid Unicode, which cannot
        # be encoded in a JSON response. Do not echo learning content in errors.
        details = [{key: entry[key] for key in ("type", "loc", "msg")} for entry in error.errors()]
        return Response(
            json.dumps({"detail": details}), status_code=422, media_type="application/json"
        )

    @app.exception_handler(OperationalError)
    async def unavailable(request, error):
        return JSONResponse({"detail": "Database unavailable"}, status_code=503)

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        try:
            with engine.connect() as connection:
                versions = (
                    connection.execute(sa.text("SELECT version_num FROM alembic_version"))
                    .scalars()
                    .all()
                )
                if versions != ["0001_practice"]:
                    raise HTTPException(503, "Database migrations are not current")
        except SQLAlchemyError as error:
            raise HTTPException(503, "Database unavailable or migrations missing") from error
        return {"status": "ready"}

    @app.post("/collections", status_code=201)
    def create_collection(body: CollectionCreate, owner_id: Owner):
        record = domain(lambda: Collection(uuid4(), owner_id, body.name))
        with engine.begin() as connection:
            connection.execute(collections.insert().values(**asdict(record)))
        return record

    @app.get("/collections")
    def list_collections(owner_id: Owner, limit: Limit = 50, offset: Offset = 0):
        with engine.connect() as connection:
            query = (
                sa.select(collections)
                .where(collections.c.owner_id == owner_id)
                .order_by(collections.c.name, collections.c.id)
                .limit(limit)
                .offset(offset)
            )
            rows = connection.execute(query).mappings().all()
        return [dict(row) for row in rows]

    @app.post("/items", status_code=201)
    def create_item(body: ItemCreate, owner_id: Owner):
        timestamp = now()
        record = domain(lambda: body.domain(uuid4(), owner_id, timestamp))
        decision = schedule(record, [], now=timestamp, policy=policy)
        values = dict(
            id=record.id,
            owner_id=owner_id,
            collection_id=body.collection_id,
            payload=body.model_dump(mode="json"),
            created_at=timestamp,
            archived=False,
            next_due_at=decision.next_due_at,
            current_schedule=jsonable_encoder({"decision": decision, "policy": asdict(policy)}),
        )
        with engine.begin() as connection:
            collection = (
                connection.execute(
                    sa.select(collections).where(
                        collections.c.id == body.collection_id, collections.c.owner_id == owner_id
                    )
                )
                .mappings()
                .one_or_none()
            )
            if collection is None:
                raise HTTPException(404, "Collection not found")
            domain(lambda: validate_membership(Collection(**dict(collection)), record))
            connection.execute(items.insert().values(**values))
        return item_view(values, timestamp)

    @app.get("/items/due")
    def due_items(owner_id: Owner, limit: Limit = 50, offset: Offset = 0):
        timestamp = now()
        with engine.connect() as connection:
            query = (
                sa.select(items)
                .where(
                    items.c.owner_id == owner_id,
                    items.c.archived.is_(False),
                    items.c.next_due_at <= timestamp,
                )
                .order_by(items.c.next_due_at, items.c.id)
                .limit(limit)
                .offset(offset)
            )
            rows = connection.execute(query).mappings().all()
        return [item_view(row, timestamp) for row in rows]

    @app.get("/items")
    def list_items(owner_id: Owner, limit: Limit = 50, offset: Offset = 0):
        timestamp = now()
        with engine.connect() as connection:
            query = (
                sa.select(items)
                .where(items.c.owner_id == owner_id)
                .order_by(items.c.created_at, items.c.id)
                .limit(limit)
                .offset(offset)
            )
            rows = connection.execute(query).mappings().all()
        return [item_view(row, timestamp) for row in rows]

    @app.get("/items/{item_id}")
    def get_item(item_id: UUID, owner_id: Owner):
        with engine.connect() as connection:
            return item_view(owned_item(connection, item_id, owner_id), now())

    @app.get("/items/{item_id}/attempts")
    def history(item_id: UUID, owner_id: Owner, limit: Limit = 50, offset: Offset = 0):
        with engine.connect() as connection:
            owned_item(connection, item_id, owner_id)
            query = (
                sa.select(attempts.c.receipt)
                .where(attempts.c.owner_id == owner_id, attempts.c.item_id == item_id)
                .order_by(attempts.c.occurred_at, attempts.c.id)
                .limit(limit)
                .offset(offset)
            )
            rows = connection.execute(query).scalars().all()
        return rows

    @app.post("/items/{item_id}/attempts")
    def submit(item_id: UUID, body: AttemptCreate, owner_id: Owner):
        event = domain(lambda: body.domain(owner_id, item_id))
        encoded = jsonable_encoder(event)
        digest = hashlib.sha256(
            json.dumps(encoded, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        with engine.begin() as connection:
            # Serialize each item's read/replay/append/schedule update across processes.
            row = owned_item(connection, item_id, owner_id, lock=True)
            timestamp = now()
            existing = (
                connection.execute(sa.select(attempts).where(attempts.c.id == event.id))
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return replay_receipt(existing, event, digest)
            if row["archived"]:
                raise HTTPException(409, "Archived items cannot accept new attempts")
            previous = (
                connection.execute(
                    sa.select(attempts.c.event)
                    .where(attempts.c.owner_id == owner_id, attempts.c.item_id == item_id)
                    .order_by(attempts.c.occurred_at)
                )
                .scalars()
                .all()
            )
            events = [
                AttemptCreate.model_validate(
                    {
                        key: value
                        for key, value in entry.items()
                        if key not in {"owner_id", "item_id"}
                    }
                ).domain(owner_id, item_id)
                for entry in previous
            ]
            decision = domain(
                lambda: schedule(item_domain(row), events + [event], now=timestamp, policy=policy)
            )
            receipt = jsonable_encoder(
                {"attempt": event, "decision": decision, "policy": asdict(policy)}
            )
            inserted = connection.execute(
                insert(attempts)
                .values(
                    id=event.id,
                    owner_id=owner_id,
                    item_id=item_id,
                    occurred_at=event.occurred_at,
                    submitted_at=timestamp,
                    payload_hash=digest,
                    event=encoded,
                    receipt=receipt,
                )
                .on_conflict_do_nothing(index_elements=[attempts.c.id])
                .returning(attempts.c.id)
            ).scalar_one_or_none()
            if inserted is None:
                # A concurrent request on another item may have used the same UUID.
                existing = (
                    connection.execute(sa.select(attempts).where(attempts.c.id == event.id))
                    .mappings()
                    .one()
                )
                return replay_receipt(existing, event, digest)
            connection.execute(
                items.update()
                .where(items.c.id == item_id, items.c.owner_id == owner_id)
                .values(
                    next_due_at=decision.next_due_at,
                    current_schedule=jsonable_encoder(
                        {"decision": decision, "policy": asdict(policy)}
                    ),
                )
            )
        return JSONResponse(receipt, status_code=201)

    return app
