"""Explicit local employee-model trial with durable metadata-only audit.

No model starts on assignment or startup. Only the owner pressing the GUI
execute button enters this function. Never store prompt/output/stderr in SQLite.
"""
from __future__ import annotations

import threading
import time

from desktop.model_runtime import run_local_model
from desktop.storage import LocalStore


def invoke_employee_model(store: LocalStore, employee_id: int, prompt: str, *,
                          timeout: int = 60, cancel: threading.Event | None = None,
                          required_tier: str | None = None) -> str:
    """Owner-invoked LOCAL CLI run with start/end/error/cancel audit."""
    # Begin transaction before validating potentially moved/deleted runtime files.
    call_id,config=store.begin_employee_model_call(employee_id,prompt,required_tier=required_tier)
    started=time.monotonic()
    status="failure"
    output_chars=0
    error_kind=""
    try:
        result=run_local_model(config,prompt,timeout=timeout,cancel=cancel)
        if cancel is not None and cancel.is_set():
            raise InterruptedError('관리자가 AI 모델 실행 중 취소했습니다. 응답은 폐기합니다.')
        from desktop.stage87_90_management import stopped
        with store._connect() as con:
            if stopped(con):
                raise PermissionError('비상 정지가 적용되어 모델 응답을 폐기합니다.')
        status="success"
        output_chars=len(result)
        return result
    except InterruptedError:
        status="cancelled"
        error_kind="InterruptedError"
        raise
    except TimeoutError:
        status="timeout"
        error_kind="TimeoutError"
        raise
    except PermissionError:
        # PermissionError subclasses OSError. Persist a stable allowed audit tag.
        error_kind='RuntimeError'
        raise
    except (ValueError,RuntimeError,OSError) as exc:
        error_kind=type(exc).__name__
        raise
    finally:
        duration_ms=max(0,int((time.monotonic()-started)*1000))
        store.finish_employee_model_call(call_id,status,output_chars=output_chars,
                                         duration_ms=duration_ms,error_kind=error_kind)
