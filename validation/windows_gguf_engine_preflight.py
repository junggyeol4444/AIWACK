"""Diagnose Windows llama.cpp subprocess exit before REAL GUI acceptance.

DIAGNOSTIC ONLY. NEVER count direct runner calls as the user's GUI E2E.
Run same verified llama-completion.exe/GGUF on the Windows CI host, capture
public-runner return code, signal, output byte count, stderr tail.
Never connect to application DB or alter owner approval.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

def run(executable: Path, model: Path, dest: Path):
    assert os.name == "nt"
    assert executable.is_file() and executable.name.lower() == "llama-completion.exe"
    assert model.is_file()
    with model.open("rb") as stream:
        assert stream.read(4) == b"GGUF"
    dest.mkdir(parents=True, exist_ok=True)
    prompts = [
        "Write exactly one sentence confirming that a local model ran.",
        "Briefly summarize a small offline report with three priorities and one risk.",
    ]
    results = []
    for i, prompt in enumerate(prompts, 1):
        started = time.monotonic()
        argv = [str(executable), "-m", str(model), "-p", prompt, "-n", "32"]
        try:
            out = subprocess.run(argv, shell=False, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=60, check=False)
            record = {"probe":i, "return_code":out.returncode,
                      "stdout_bytes":len(out.stdout),
                      "duration_seconds":round(time.monotonic()-started,2),
                      "stderr_tail":out.stderr.decode("utf-8",errors="replace")[-1400:]}
        except (OSError, subprocess.TimeoutExpired) as e:
            record = {"probe":i, "error_type":type(e).__name__,
                      "duration_seconds":round(time.monotonic()-started,2)}
        results.append(record)
        print("WINDOWS_REAL_GGUF_ENGINE_DIAGNOSTIC", json.dumps(
            record,ensure_ascii=False),flush=True)
    (dest/"engine-preflight.json").write_text(json.dumps({
        "direct_cli_diagnostic_only":True,
        "not_a_gui_validation":True,
        "probe_results":results,
    },ensure_ascii=False,indent=2),encoding="utf-8")
    if not all(r.get("return_code")==0 and r.get("stdout_bytes",0)>0 for r in results):
        raise AssertionError("Verified Windows GGUF runner preflight failed; "
                             "see engine-preflight.json for actual stderr and exit status")
if __name__=="__main__":
    if len(sys.argv)!=4:
        raise SystemExit("usage: windows_gguf_engine_preflight.py llama-completion.exe model.gguf artifacts_dir")
    run(*(Path(s).resolve() for s in sys.argv[1:]))
