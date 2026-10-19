"""Alembic migration environment.

The application supplies a live SQLAlchemy connection so all URL credentials stay
in environment configuration instead of source control.
"""
from alembic import context
from backend.database.connection import metadata

config = context.config
target_metadata = metadata


def run_migrations_online():
    connection = config.attributes.get("connection")
    if connection is None:
        raise RuntimeError("Migration requires an application-managed connection")
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
