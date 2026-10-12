"""Database initialization, checked Alembic history and persistence.

SQLite is for local verification. PostgreSQL URL is accepted, but real PostgreSQL
startup is not marked verified until that integration is exercised separately.
"""
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, inspect, text
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

ROOT = Path(__file__).resolve().parents[2]


def build_engine(database_url: str) -> Engine:
    if not database_url or not database_url.strip():
        raise ValueError("database_url must be non-empty")
    return create_engine(database_url, pool_pre_ping=True)


def initialize_database(engine: Engine) -> None:
    """Apply versioned migrations and safely adopt the pre-migration stage-7 DB."""
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        cfg.attributes["connection"] = connection
        if "system_metadata" in tables and "alembic_version" not in tables:
            cols = {c["name"] for c in inspect(connection).get_columns("system_metadata")}
            expected = {"id", "key", "value", "created_at"}
            if not expected.issubset(cols):
                raise RuntimeError("Legacy database structure is incompatible with migration 0001")
            command.stamp(cfg, "0001_initial")
        command.upgrade(cfg, "head")


def database_status(engine: Engine) -> dict[str, str]:
    """Verify live connection and migration state, not only process health."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        if not inspect(connection).has_table("system_metadata"):
            raise RuntimeError("Database has not been initialized")
        if not inspect(connection).has_table("alembic_version"):
            raise RuntimeError("Migration history is missing")
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if version != "0001_initial":
            raise RuntimeError(f"Unrecognized database migration revision: {version!r}")
    return {"status": "ok", "component": "database", "dialect": engine.dialect.name, "revision": version}
