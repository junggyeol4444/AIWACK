"""Subprocess codepage regression tests for the synthetic Windows model CLI."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


PROMPT = "총괄 AI 한글 지시: 직원 결과를 보고서로 제출"
MARKER = "AIWACK_WINDOWS_NATIVE_CLI"


def check_utf8_output(command: list[str]) -> None:
    env = os.environ.copy()
    # Simulate the failing Windows runner console encoding even on Linux.
    env["PYTHONIOENCODING"] = "cp1252:strict"
    result = subprocess.run(
        [*command, "-p", PROMPT, "-n", "32"],
        capture_output=True, env=env, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    output = result.stdout.decode("utf-8", errors="strict")
    assert output.startswith(MARKER)
    assert PROMPT in output
    assert "-n 32" in output


def test_python_fixture_handles_korean_under_cp1252() -> None:
    check_utf8_output([sys.executable, str(Path(__file__).with_name("windows_fake_llm.py"))])


def test_packaged_windows_stub_handles_korean_under_cp1252() -> None:
    executable = os.environ.get("AIWACK_NATIVE_SYNTHETIC_RUNNER", "")
    if not executable:
        pytest.skip("Windows executable is only built by the Windows CI job")
    path = Path(executable)
    assert path.is_file() and path.suffix.lower() == ".exe"
    check_utf8_output([str(path)])
