"""Stage 7: database engine, initialization and connectivity health.

Development defaults to SQLite. Supports PostgreSQL URL via psycopg adapter.
"""
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql import func

metadata = MetaData()
system_metadata = Table(
    "system_metadata", metadata,
    Column("id", Integer, primary_key=True),
    Column("key", String(120), nullable=False, unique=True),
    Column("value", String(1000), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

def build_engine(database_url: str) -> Engine:
    if not database_url or not database_url.strip():
        raise ValueError("database_url must be non-empty")
    return create_engine(database_url, pool_pre_ping=True)

def initialize_database(engine: Engine) -> None:
    metadata.create_all(engine)

def database_status(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        if not engine.dialect.has_table(connection, "system_metadata"):
            raise RuntimeError("Database has not been initialized")
    return {"status": "ok", "component": "database", "dialect": engine.dialect.name}
