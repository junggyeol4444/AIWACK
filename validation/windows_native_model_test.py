"""End-to-end Windows subprocess validation using an actual .exe model adapter."""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path

from desktop.model_runtime import ModelConfig, run_local_model, validate_config
from desktop.storage import LocalStore

def main(exe: str) -> None:
    assert sys.platform == "win32", "Must run this test on Windows"
    exe_path = Path(exe).resolve(strict=True)
    assert exe_path.suffix.lower() == ".exe"
    with tempfile.TemporaryDirectory(prefix="aiwack-model-native-") as directory:
        base = Path(directory)
        fake_model = base / "test.gguf"
        fake_model.write_bytes(b"GGUF" + bytes((3, 0, 0, 0)))
        cfg = ModelConfig("real Windows executable smoke", "llama_cpp", str(exe_path), str(fake_model), 16)
        validated = validate_config(cfg)
        assert validated.executable_path == str(exe_path)
        output = run_local_model(validated, "WIN_SUBPROCESS_PROBE_2026", timeout=30)
        assert "AIWACK_WINDOWS_NATIVE_CLI" in output
        assert "WIN_SUBPROCESS_PROBE_2026" in output
        assert "-m" in output and "-p" in output
        store = LocalStore(base / "native.sqlite3")
        store.setup_owner("win_owner", "safe-window-runner-password-2026")
        model_id = store.add_local_model(cfg)
        assert model_id > 0
        store.logout()
        store2 = LocalStore(base / "native.sqlite3")
        store2.login("win_owner", "safe-window-runner-password-2026")
        assert store2.read_local_model(model_id)["name"] == "real Windows executable smoke"
    print("WINDOWS NATIVE MODEL ADAPTER SUBPROCESS AND SQLITE PERSISTENCE PASS (synthetic runner)")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: windows_native_model_test.py PATH_TO_NATIVE_EXE")
    main(sys.argv[1])
