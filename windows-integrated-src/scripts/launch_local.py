"""Start local prototype on loopback only; never expose unauthenticated diagnostics."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    import uvicorn
    print("AI Autonomous Company (early prototype) - http://127.0.0.1:8000/diagnostics", flush=True)
    print("Press Ctrl+C to stop. No company AI employees are running yet.", flush=True)
    uvicorn.run("backend.main:app", host="127.0.0.1", port=int(os.environ.get("COMPANY_LOCAL_PORT", "8000")), log_level="info")
