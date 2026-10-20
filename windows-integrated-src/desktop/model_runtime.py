"""Explicitly invoked local-process LLM adapters; no network transport or downloading.

Real inference requires a user-provided trusted executable and model files.
This module never starts an HTTP server or downloads anything. A subprocess is
unavoidably outside Python's network sandbox; choose trusted local runtimes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import signal
import subprocess
import threading
import time

BACKENDS = {
    "llama_cpp": "llama.cpp (GGUF 모델 + llama-cli 실행파일)",
    "llamafile": "llamafile (모델이 포함된 실행파일, GGUF 선택)",
}
MAX_PROMPT = 3000
MAX_TOKENS = 512
MAX_OUTPUT = 20000


@dataclass(frozen=True)
class ModelConfig:
    name: str
    backend: str
    executable_path: str
    model_path: str
    max_tokens: int = 128


def _local_file(value: str, *, label: str, required: bool = True) -> Path | None:
    if not isinstance(value, str):
        raise ValueError(f"{label}: 로컬 파일 경로를 입력하세요.")
    path_text = value.strip()
    if not path_text:
        if required:
            raise ValueError(f"{label}: 로컬 파일 경로를 입력하세요.")
        return None
    if "\x00" in path_text or path_text.startswith(("http:", "https:", "ftp:", "//", "\\\\")):
        raise ValueError(f"{label}: 인터넷 주소 및 네트워크 공유 경로는 허용하지 않습니다.")
    path = Path(path_text).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError(f"{label}: PC에 존재하는 절대 파일 경로를 입력하세요.")
    resolved = path.resolve(strict=True)
    if os.name == 'nt' and str(resolved).startswith(('\\\\', '//')):
        raise ValueError(f'{label}: 네트워크 공유 파일은 사용할 수 없습니다.')
    return resolved


def validate_config(config: ModelConfig) -> ModelConfig:
    """Reject invalid adapters and nonlocal/missing paths without spawning a process."""
    if not isinstance(config.name, str) or not (1 <= len(config.name.strip()) <= 70):
        raise ValueError("모델 표시 이름은 1~70자여야 합니다.")
    if config.backend not in BACKENDS:
        raise ValueError("알 수 없는 로컬 모델 실행 방식입니다.")
    if type(config.max_tokens) is not int or not (1 <= config.max_tokens <= MAX_TOKENS):
        raise ValueError(f"최대 생성 토큰은 1~{MAX_TOKENS}이어야 합니다.")
    program = _local_file(config.executable_path, label="실행파일")
    if os.name == "nt" and program.suffix.lower() not in {".exe", ".com"}:
        raise ValueError("Windows에서는 EXE 또는 COM 실행파일을 지정하세요.")
    model = _local_file(config.model_path, label="GGUF 모델", required=config.backend == "llama_cpp")
    if model is not None:
        if model.suffix.lower() != ".gguf":
            raise ValueError("GGUF 모델 파일(.gguf)만 허용합니다.")
        with model.open("rb") as stream:
            if stream.read(4) != b"GGUF":
                raise ValueError("GGUF 파일 머리글이 잘못되었습니다. 모델 파일을 확인하세요.")
    return ModelConfig(config.name.strip(), config.backend, str(program), str(model) if model else "", config.max_tokens)


def run_local_model(config: ModelConfig, prompt: str, *, timeout: int = 60,
                    cancel: threading.Event | None = None) -> str:
    """Run a selected LOCAL model executable on explicit demand, without a shell.

    Checks only basic GGUF file header: real inference correctness depends on
    the chosen model/runtime and is not guaranteed by file validation.
    """
    normalized = validate_config(config)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
        raise ValueError(f"질문은 1~{MAX_PROMPT}자여야 합니다.")
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise ValueError("실행 제한 시간은 1~120초여야 합니다.")
    args = [normalized.executable_path]
    if normalized.model_path:
        args.extend(["-m", normalized.model_path])
    args.extend(["-p", prompt.strip(), "-n", str(normalized.max_tokens)])
    # Explicit trusted local executable; no shell, URL, GitHub, cloud API or install.
    # Remove proxy environment variables as defense in depth, not OS-level isolation.
    env = {k: v for k, v in os.environ.items() if k.lower() not in {
        "http_proxy", "https_proxy", "all_proxy", "ftp_proxy", "no_proxy"
    }}
    if cancel is not None and cancel.is_set():
        raise InterruptedError('모델 실행을 취소했습니다.')
    # llama.cpp's completion executable defaults to a chat-template-driven
    # interactive session. A stdin=DEVNULL EOF after output has caused genuine
    # STATUS_HEAP_CORRUPTION (0xC0000374) on Windows CPU runners. Request one
    # bounded turn and clean shutdown, including the modern llama-completion
    # binary. Never retry a failed inference or accept a nonzero exit code.
    if os.path.basename(os.fspath(args[0])).lower() in {
        'llama-cli.exe', 'llama-completion.exe', 'llama-cli', 'llama-completion'
    }:
        args.append('--single-turn')
    try:
        process = subprocess.Popen(args, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   stdin=subprocess.DEVNULL, env=env,
                                   start_new_session=(os.name != "nt"))
    except OSError as exc:
        raise RuntimeError(f"로컬 모델 프로그램 실행 실패: {exc}") from exc
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("모델 실행을 취소했습니다.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("로컬 모델 실행 제한 시간을 초과했습니다.")
            try:
                out, err = process.communicate(timeout=min(.2, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    except (TimeoutError, InterruptedError):
        # Descendants of PyInstaller/llama launchers may retain inherited
        # stdout/stderr handles. Killing only Popen's parent can then block
        # forever in communicate(). Terminate the whole process tree.
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=False, timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.poll() is None:
            process.kill()
        try:
            process.communicate(timeout=8)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            raise RuntimeError("모델 종료 후 출력 핸들이 해제되지 않았습니다.") from exc
        raise
    output = out.decode("utf-8", errors="replace")
    stderr = err.decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise RuntimeError(f"로컬 모델 실행 종료 코드 {process.returncode}: {stderr.strip()[-500:]}")
    if len(output) > MAX_OUTPUT:
        raise ValueError('로컬 모델 응답이 20000자를 초과했습니다. 잘린 결과를 저장하지 않습니다.')
    if not output.strip():
        raise ValueError('로컬 모델이 빈 응답을 반환했습니다.')
    return output.strip()
