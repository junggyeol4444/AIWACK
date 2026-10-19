"""Stage 20: authenticated owner-initiated one-turn response from the local chief model.

No mock answer, cloud connection, server, or periodic call. Actual text comes only
from the user-provided local CLI runner. Raw prompts/responses are NOT persisted.
"""
from __future__ import annotations

import threading
from desktop.storage import LocalStore
from desktop.employee_model_runtime import invoke_employee_model
from desktop.company_status import chief_query_with_status


def invoke_chief_model(store: LocalStore, prompt: str, *, timeout: int = 60,
                       cancel: threading.Event | None = None,
                       include_company_status: bool = False) -> str:
    """Require the active CEO reporting role and its assigned local model in SQL."""
    if type(include_company_status) is not bool:
        raise ValueError("회사 현황 조회 옵션이 올바르지 않습니다.")
    chief = store.read_chief_profile()  # owner authentication is enforced here
    if chief is None or chief["lifecycle"] != "draft":
        raise ValueError("활성 총괄 AI가 없습니다. 조직 지휘 체계에서 총괄 AI를 먼저 지정하세요.")
    if chief["model_id"] is None:
        raise ValueError("총괄 AI의 로컬 모델을 먼저 배정하세요.")
    if include_company_status:
        prompt = chief_query_with_status(store, prompt)
    return invoke_employee_model(store, int(chief["employee_id"]), prompt,
                                 timeout=timeout, cancel=cancel, required_tier="ceo")
