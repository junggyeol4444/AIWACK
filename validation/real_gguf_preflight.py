"""Validate actual SHA-pinned llama.cpp Windows CLI inference before GUI acceptance.

The caller authenticates downloaded binaries. Never substitute fake output.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

_PROMPT = 'Respond with one safe word.'


def _real_response(stdout: str) -> bool:
    """Reject empty and prompt-only output, not merely a successful exit code."""
    if not isinstance(stdout, str):
        return False
    remainder = stdout.replace(_PROMPT, '', 1).strip()
    return bool(remainder and any(char.isalnum() for char in remainder))


def _unsupported_flag(stderr: str) -> bool:
    """Retry without the optional flag only for a diagnosed argument error."""
    text = stderr.lower()
    return any(phrase in text for phrase in (
        'unknown argument', 'unrecognized argument', 'unknown option',
        'unrecognized option', 'invalid option', 'unknown flag'))


def verify_cli(primary: Path, model: Path, evidence: Path, selection: Path,
               *, timeout: int = 70) -> Path:
    primary = Path(primary).resolve(strict=True)
    model = Path(model).resolve(strict=True)
    evidence, selection = Path(evidence), Path(selection)
    if not primary.is_file() or not model.is_file():
        raise ValueError('실제 검증된 Windows CLI 및 GGUF 파일이 필요합니다.')
    if primary.name.lower() not in ('llama-completion.exe', 'llama-cli.exe'):
        raise ValueError('공식 llama.cpp 실행 파일 이름이 아닙니다.')
    with model.open('rb') as stream:
        if stream.read(4) != b'GGUF':
            raise ValueError('실제 GGUF 파일 헤더가 없습니다.')
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise ValueError('실제 모델 사전검사 제한시간 오류')
    alternative = primary.with_name('llama-cli.exe')
    candidates = [primary]
    if alternative != primary and alternative.is_file():
        candidates.append(alternative.resolve(strict=True))
    results = []
    selected = None
    for binary in candidates:
        for optional_single_turn in (True, False):
            args = [str(binary), '-m', str(model), '-p', _PROMPT, '-n', '16']
            if optional_single_turn:
                args.append('--single-turn')
            try:
                completed = subprocess.run(
                    args, shell=False, capture_output=True, text=True,
                    errors='replace', timeout=timeout, stdin=subprocess.DEVNULL)
            except (OSError, subprocess.TimeoutExpired) as exc:
                results.append({'cli': binary.name, 'single_turn': optional_single_turn,
                                'error': type(exc).__name__})
                break
            stdout = completed.stdout or ''
            stderr = completed.stderr or ''
            genuine = completed.returncode == 0 and _real_response(stdout)
            results.append({
                'cli': binary.name, 'single_turn': optional_single_turn,
                'returncode': completed.returncode,
                'stdout_chars': len(stdout),
                'stdout_sha256': hashlib.sha256(stdout.encode('utf-8')).hexdigest(),
                'response_beyond_prompt': _real_response(stdout),
                'stderr_tail': stderr[-300:],
                'accepted': genuine,
            })
            if genuine:
                selected = binary
                break
            # Never mask a crash or failed inference with another command line.
            # Only an optional-flag incompatibility permits one retry.
            if not (optional_single_turn and completed.returncode != 0
                    and _unsupported_flag(stderr)):
                break
        if selected is not None:
            break
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps({
        'direct_real_model_preflight_only': True,
        'not_windows_gui_acceptance': True,
        'attempts': results,
        'selected': selected.name if selected is not None else None,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if selected is None:
        raise RuntimeError('실제 Windows llama.cpp GGUF 추론을 성공적으로 완료한 CLI가 없습니다.')
    selection.parent.mkdir(parents=True, exist_ok=True)
    selection.write_text(str(selected) + '\n', encoding='utf-8')
    return selected


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit('usage: real_gguf_preflight.py CLI GGUF DIAGNOSTICS CHOSEN_PATH')
    chosen = verify_cli(*(Path(p) for p in sys.argv[1:]))
    print('REAL_GGUF_CPU_PREFLIGHT_PASS: ' + chosen.name, flush=True)
