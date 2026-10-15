"""SYNTHETIC Windows subprocess fixture; never real GGUF/AI inference.

Its output is UTF-8 independent of the Windows console code page. This matters
when the owner enters a Korean chief-to-staff instruction through the GUI.
"""
from __future__ import annotations

import sys


def main() -> None:
    if sys.stdout is None:
        raise RuntimeError("Synthetic CLI requires a console stdout stream")
    # CP1252 Windows runner stdout cannot print Korean argv by default, whereas
    # desktop.model_runtime.run_local_model decodes subprocess bytes as UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    print("AIWACK_WINDOWS_NATIVE_CLI", " ".join(sys.argv[1:])[:180])


if __name__ == "__main__":
    main()
