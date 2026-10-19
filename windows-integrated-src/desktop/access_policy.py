"""Stage 17: offline employee permission/tool configuration vocabulary.

These named grants are deny-by-default. Stage 21 implements only an
internal read-only CEO company/goals viewer; other task/document tools remain
unimplemented. Owner authentication is separate and never delegated.
"""
from __future__ import annotations

from collections.abc import Iterable

# key: Korean label; these grants are for future AI runtimes, not owner rights.
CAPABILITIES: dict[str, str] = {
    "company:read": "회사 정보 읽기(총괄 AI 로컬 조회)",
    "goals:read": "운영 목표 읽기(별도 로컬 조회 허가)",
    "tasks:propose": "업무 초안 제안(아직 미구현)",
    "documents:draft": "문서 초안 작성(아직 미구현)",
}
# A tool cannot be configured without its required permission. None is run.
TOOLS: dict[str, tuple[str, str]] = {
    "local_company_reader": ("회사 정보 읽기(총괄 AI 로컬 읽기 전용)", "company:read"),
    "local_goals_reader": ("회사 목표 읽기(총괄 AI 로컬 읽기 전용)", "goals:read"),
    "local_task_drafter": ("업무 제안 도구(실행 미구현)", "tasks:propose"),
    "local_document_drafter": ("문서 초안 도구(실행 미구현)", "documents:draft"),
}


def validate_grants(capabilities: Iterable[str], tools: Iterable[str]) -> tuple[set[str], set[str]]:
    """Reject unknown, malformed, duplicate and inconsistent grants."""
    if isinstance(capabilities, (str, bytes)) or not isinstance(capabilities, (tuple, list, set, frozenset)):
        raise ValueError("권한 목록의 형식이 올바르지 않습니다.")
    if isinstance(tools, (str, bytes)) or not isinstance(tools, (tuple, list, set, frozenset)):
        raise ValueError("도구 목록의 형식이 올바르지 않습니다.")
    cap_list, tool_list = list(capabilities), list(tools)
    if any(not isinstance(x, str) or x not in CAPABILITIES for x in cap_list) or len(cap_list) != len(set(cap_list)):
        raise ValueError("허용되지 않거나 중복된 직원 권한입니다.")
    if any(not isinstance(x, str) or x not in TOOLS for x in tool_list) or len(tool_list) != len(set(tool_list)):
        raise ValueError("허용되지 않거나 중복된 직원 도구입니다.")
    caps, allowed = set(cap_list), set(tool_list)
    if any(TOOLS[x][1] not in caps for x in allowed):
        raise ValueError("도구를 허용하려면 해당 조회·초안 권한도 허용해야 합니다.")
    return caps, allowed
