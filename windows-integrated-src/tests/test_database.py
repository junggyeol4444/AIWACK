import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from backend.database.connection import build_engine, initialize_database, database_status, metadata
from backend.main import app


def memory_engine():
    return create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def test_initialization_is_idempotent_and_versioned():
    engine = memory_engine()
    initialize_database(engine)
    initialize_database(engine)
    assert {"system_metadata", "alembic_version"}.issubset(inspect(engine).get_table_names())
    assert database_status(engine)["revision"] == "0001_initial"
    engine.dispose()


def test_health_before_initialization_fails():
    engine = memory_engine()
    with pytest.raises(RuntimeError, match="not been initialized"):
        database_status(engine)
    engine.dispose()


def test_blank_connection_string_rejected():
    with pytest.raises(ValueError, match="non-empty"):
        build_engine(" ")


def test_legacy_stage7_db_migrates_without_dropping_data():
    engine = memory_engine()
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO system_metadata (key, value) VALUES ('original', 'preserved')"))
    initialize_database(engine)
    with engine.connect() as connection:
        actual = connection.execute(text("SELECT value FROM system_metadata WHERE key='original'")).scalar_one()
    assert actual == "preserved"
    assert database_status(engine)["revision"] == "0001_initial"
    engine.dispose()


def test_reject_incompatible_legacy_schema():
    engine = memory_engine()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE system_metadata (id INTEGER PRIMARY KEY)"))
    with pytest.raises(RuntimeError, match="incompatible"):
        initialize_database(engine)
    engine.dispose()


def test_db_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/v1/database/health")
        assert response.status_code == 200
        assert response.json()["revision"] == "0001_initial"


def test_checkpoint_roundtrip_in_process():
    with TestClient(app) as client:
        assert client.post("/api/v1/diagnostics/checkpoint", json={"message": "save restart test"}).json() == {"message": "save restart test", "status": "saved"}
        assert client.get("/api/v1/diagnostics/checkpoint").json()["message"] == "save restart test"
        assert "저장·재시작" in client.get("/diagnostics").text


def test_checkpoint_validation():
    with TestClient(app) as client:
        assert client.post("/api/v1/diagnostics/checkpoint", json={"message": ""}).status_code == 422
        assert client.post("/api/v1/diagnostics/checkpoint", json={"message": "x" * 121}).status_code == 422
