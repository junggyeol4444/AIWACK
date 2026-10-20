"""Verify actual GGUF inference before any packaged Windows EXE E2E.

A crashed llama-completion.exe is never accepted even if it emits output.
The optional llama-cli.exe alternative must come from the same verified
official archive directory and successfully generate a clean real model reply.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def verify_cli(primary: Path, model: Path, evidence: Path, selection: Path,
               *, timeout: int = 70) -> Path:
    primary = Path(primary).resolve(strict=True)
    model = Path(model).resolve(strict=True)
    evidence = Path(evidence)
    selection = Path(selection)
    if not primary.is_file() or not model.is_file():
        raise ValueError('Actual verified Windows CLI and GGUF files required')
    with model.open('rb') as stream:
        if stream.read(4) != b'GGUF':
            raise ValueError('Actual GGUF file header missing')
    if timeout < 1 or timeout > 120:
        raise ValueError('Invalid preflight timeout')
    selection.unlink(missing_ok=True)
    alternative = primary.with_name('llama-cli.exe')
    candidates = [primary]
    if alternative != primary and alternative.is_file():
        candidates.append(alternative.resolve(strict=True))
    results = []
    selected = None
    for binary in candidates:
        args = [str(binary), '-m', str(model), '-p',
                'Respond with one safe word.', '-n', '16', '--single-turn']
        try:
            completed = subprocess.run(args, shell=False, capture_output=True,
                                       text=True, errors='replace', timeout=timeout,
                                       stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append(f'{binary.name}: {type(exc).__name__}: {str(exc)[:200]}')
            continue
        results.append(f'{binary.name}: returncode={completed.returncode} '
                       f'has_output={bool(completed.stdout.strip())} '
                       f'bytes={len(completed.stdout)}')
        if completed.returncode == 0 and completed.stdout.strip():
            selected = binary
            break
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text('\n'.join(results) + '\n', encoding='utf-8')
    if selected is None:
        raise RuntimeError('No genuine Windows llama.cpp CLI completed a clean GGUF inference')
    selection.parent.mkdir(parents=True, exist_ok=True)
    selection.write_text(str(selected) + '\n', encoding='utf-8')
    return selected


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit('usage: real_gguf_preflight.py CLI GGUF DIAGNOSTICS CHOSEN_PATH')
    chosen = verify_cli(*(Path(p) for p in sys.argv[1:]))
    print('REAL_GGUF_CPU_PREFLIGHT_PASS: ' + chosen.name, flush=True)
