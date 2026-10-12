import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from backend.database.connection import build_engine, initialize_database, database_status
from backend.main import app

def memory_engine():
    return create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

def test_initialization_is_idempotent():
    engine = memory_engine()
    initialize_database(engine)
    initialize_database(engine)
    assert "system_metadata" in inspect(engine).get_table_names()
    assert database_status(engine) == {"status": "ok", "component": "database", "dialect": "sqlite"}
    engine.dispose()

def test_health_before_initialization_fails():
    engine = memory_engine()
    with pytest.raises(RuntimeError, match="not been initialized"):
        database_status(engine)
    engine.dispose()

def test_blank_connection_string_rejected():
    with pytest.raises(ValueError, match="non-empty"):
        build_engine(" ")

def test_db_health_endpoint_with_live_test_engine():
    with TestClient(app) as client:
        r = client.get("/api/v1/database/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["dialect"] == "sqlite"
