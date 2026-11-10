import sqlalchemy as sa
from alembic import context

from api.config import database_url
from api.db import metadata


def run(connection):
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=database_url(), target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    run(context.config.attributes["connection"])
else:
    engine = sa.create_engine(database_url(), poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()
