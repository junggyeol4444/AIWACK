"""Stages 27–29: owner-triggered offline text-draft task run, now bounded parallel.

Uses the existing trusted local CLI adapter; it cannot invoke task tools,
write output files, browse the web, approve costs or complete the task.
Model text is returned only to the current caller and not saved in SQLite.
"""
from __future__ import annotations

import threading
import time

from desktop.model_runtime import run_local_model
from desktop.storage import LocalStore


def invoke_task_execution(store: LocalStore, task_id: int, *, timeout: int = 60,
                          cancel: threading.Event | None = None) -> str:
    """Atomically reserve a task, call local model once, finalize both audit trails.

    On failure the task becomes blocked; on success it remains in_progress
    for human review. A process crash leaves an auditable 'running' row which
    the owner can explicitly recover; there is no silent automatic retry.
    """
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise ValueError('실행 제한 시간은 1~120초여야 합니다.')
    if cancel is not None and cancel.is_set():
        raise InterruptedError('실행 시작 전 취소되었습니다.')
    run_id, config, prompt = store.begin_task_execution(task_id)
    started = time.monotonic()
    status, error_kind, output_chars = 'failure', '', 0
    try:
        response = run_local_model(config, prompt, timeout=timeout, cancel=cancel)
        # A late owner stop cannot become a successful audited task.
        if cancel is not None and cancel.is_set():
            raise InterruptedError('관리자가 직원 실행 중 취소했습니다. 응답은 폐기합니다.')
        from desktop.stage87_90_management import stopped
        with store._connect() as con:
            if stopped(con):
                raise PermissionError('비상 정지가 적용되어 직원 결과를 폐기합니다.')
        status = 'success'
        output_chars = len(response)
        return response
    except InterruptedError:
        status, error_kind = 'cancelled', 'InterruptedError'
        raise
    except TimeoutError:
        status, error_kind = 'timeout', 'TimeoutError'
        raise
    except Exception as exc:
        error_kind = type(exc).__name__ if type(exc).__name__ in {
            'ValueError', 'RuntimeError', 'OSError'
        } else 'RuntimeError'
        raise
    finally:
        store.finish_task_execution(run_id, status, output_chars=output_chars,
                                    duration_ms=max(0, int((time.monotonic()-started)*1000)),
                                    error_kind=error_kind)
