"""REAL end-to-end runtime check: subprocess -> TCP HTTP -> SQL DB -> restart.

This is deliberately not a mocked TestClient/unit test. It launches two real
Uvicorn processes on localhost and makes HTTP requests using the standard lib.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fetch(base, path, payload=None):
    raw = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(base + path, data=raw, headers=headers, method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=3) as response:
        return response.status, response.read().decode()


def startup(port, db):
    env = dict(os.environ, COMPANY_DATABASE_URL="sqlite+pysqlite:///" + str(db))
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT,
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if p.poll() is not None:
            raise RuntimeError("Server exited early: " + p.communicate()[0])
        try:
            status, body = fetch(base, "/api/v1/health")
            if status == 200:
                return p, base
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    p.terminate()
    raise TimeoutError("Uvicorn did not start")


def stop(p):
    p.terminate()
    try:
        output = p.communicate(timeout=8)[0]
    except subprocess.TimeoutExpired:
        p.kill()
        output = p.communicate()[0]
    if p.returncode not in (0, -15, 15, -2):
        raise RuntimeError("Server terminated abnormally: " + output[-1500:])
    return output


def run():
    with tempfile.TemporaryDirectory(prefix="aiwack-real-smoke-") as tmp:
        db = Path(tmp) / "company.sqlite3"
        first_port = free_port()
        p, base = startup(first_port, db)
        try:
            status, body = fetch(base, "/diagnostics")
            assert status == 200 and "저장·재시작" in body, "Browser-facing diagnostics missing"
            status, body = fetch(base, "/docs")
            assert status == 200 and "swagger-ui" in body.lower(), "Swagger UI did not serve"
            status, body = fetch(base, "/api/v1/database/health")
            d = json.loads(body)
            assert status == 200 and d["status"] == "ok" and d["revision"] == "0001_initial", d
            marker = "live HTTP data survives server restart"
            status, body = fetch(base, "/api/v1/diagnostics/checkpoint", {"message": marker})
            assert status == 200 and json.loads(body)["status"] == "saved"
            print("PASS: real process started, UI served, DB migrated, HTTP POST committed")
        finally:
            stop(p)
        assert db.is_file() and db.stat().st_size > 0, "Physical SQLite database is missing"
        second_port = free_port()
        p, base = startup(second_port, db)
        try:
            status, body = fetch(base, "/api/v1/diagnostics/checkpoint")
            assert status == 200 and json.loads(body)["message"] == marker, body
            print("PASS: real process restarted and persisted marker read via HTTP")
        finally:
            stop(p)
    print("PASS: true HTTP/process/database/restart smoke test")


if __name__ == "__main__":
    run()
