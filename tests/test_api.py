from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)

def test_root_endpoint():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "development"

def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["component"] == "api"

def test_versioned_health_endpoint():
    assert client.get("/api/v1/health").json() == client.get("/health").json()

def test_openapi_available():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/api/v1/health" in r.json()["paths"]

def test_no_unapproved_agent_execution_endpoint():
    assert client.post("/api/v1/agents/execute").status_code == 404
