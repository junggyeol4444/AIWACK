"""SYNTHETIC Windows subprocess fixture; never real GGUF/AI inference.

Its output is UTF-8 independent of the Windows console code page. This matters
when the owner enters a Korean chief-to-staff instruction through the GUI.
"""
from __future__ import annotations

import os
import sys
import time


def main() -> None:
    if sys.stdout is None:
        raise RuntimeError("Synthetic CLI requires a console stdout stream")
    # CP1252 Windows runner stdout cannot print Korean argv by default, whereas
    # desktop.model_runtime.run_local_model decodes subprocess bytes as UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    # Opt-in delay for subprocess cancellation and timeout CI. Never AI inference.
    stall = os.environ.get("AIWACK_SYNTHETIC_STALL_SECONDS")
    if stall is not None:
        if stall != "15":
            raise ValueError("Only the test-defined 15-second stall is supported")
        # Optional child inherits model stdout/stderr; killing only the launcher
        # leaves communicate() blocked even after a timeout. This is a fixture,
        # not an inference engine or a legitimate employee process.
        descendant = os.environ.get("AIWACK_SYNTHETIC_DESCENDANT_PIPE", "")
        if descendant not in ("", "1"):
            raise ValueError("Invalid synthetic child-pipe test flag")
        if descendant == "1":
            import subprocess
            if os.name == "nt":
                command = ["powershell.exe", "-NoProfile", "-NonInteractive",
                           "-Command", "Start-Sleep -Seconds 15"]
            else:
                command = [sys.executable, "-c", "import time; time.sleep(15)"]
            subprocess.Popen(command, stdin=subprocess.DEVNULL,
                             stdout=sys.stdout, stderr=sys.stderr)
        time.sleep(15)
    print("AIWACK_WINDOWS_NATIVE_CLI", " ".join(sys.argv[1:])[:180])


if __name__ == "__main__":
    main()
