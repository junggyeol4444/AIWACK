"""Windows 재시작 횟수와 무관한 실제 총괄 보고 모델 재시도 한도.

계약 테스트만 작성. 여기의 모의 호출은 실제 GGUF/Windows EXE 실행이 아니다.
전체 기능 개발을 끝낸 뒤 모든 기존·신규 검증과 함께 실행할 것.
"""
import pytest

from desktop import company_campaign_final_report as final_report


class ReadOnlyOwner:
    def __init__(self):
        self.checked = []

    def require_permission(self, name):
        self.checked.append(name)


@pytest.mark.parametrize("attempts,status,remaining", [
    (0, "no_model_attempt", 3),
    (1, "format_failures_only", 2),
    (2, "format_failures_only", 1),
    (3, "format_failures_only", 0),
    (1, "report_saved", 0),
])
def test_real_model_retry_budget_is_preserved_across_gui_restarts(
        monkeypatch, attempts, status, remaining):
    store = ReadOnlyOwner()
    monkeypatch.setattr(
        final_report, "inspect_final_model_attempt_chain",
        lambda _store, _campaign_id: {
            "attempt_count": attempts,
            "failed_format_count": attempts if status != "report_saved" else 0,
            "status": status,
            "evidence_sha256": "a" * 64,
        })
    first = final_report.remaining_final_report_model_attempts(store, 27)
    second = final_report.remaining_final_report_model_attempts(
        ReadOnlyOwner(), 27)
    assert first["remaining_real_model_format_attempts"] == remaining
    assert second["remaining_real_model_format_attempts"] == remaining
    assert first["read_only"] is True
    assert first["automatic_retries_executed"] is False
    assert first["actual_gguf_binary_verified"] is False
    assert store.checked == ["company:manage"]


@pytest.mark.parametrize("attempts,status", [
    (4, "format_failures_only"),
    (True, "format_failures_only"),
    (-1, "format_failures_only"),
    (1, "corrupt_model_log"),
])
def test_damaged_or_excessive_attempt_journal_fails_closed(
        monkeypatch, attempts, status):
    monkeypatch.setattr(
        final_report, "inspect_final_model_attempt_chain",
        lambda *_args, **_kwargs: {
            "attempt_count": attempts,
            "failed_format_count": attempts,
            "status": status,
        })
    with pytest.raises(ValueError, match="감사가 손상"):
        final_report.remaining_final_report_model_attempts(ReadOnlyOwner(), 8)


def test_invalid_owner_campaign_id_fails_before_any_model_audit(monkeypatch):
    def should_not_inspect(*_args, **_kwargs):
        pytest.fail("거부한 업무 번호의 모델 감사 조회는 수행하지 않습니다.")
    monkeypatch.setattr(
        final_report, "inspect_final_model_attempt_chain", should_not_inspect)
    with pytest.raises(ValueError, match="협업 번호"):
        final_report.remaining_final_report_model_attempts(ReadOnlyOwner(), True)
