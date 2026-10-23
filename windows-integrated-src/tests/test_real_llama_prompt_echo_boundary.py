"""No model is simulated as an actual GGUF acceptance in these unit tests."""
from desktop.model_runtime import _extract_llama_completion
import pytest


def test_exact_input_echo_removed_preserves_full_genuine_text():
    prompt='승인된 직원 지시'
    answer='직원이 생성한 결과 보고입니다.'
    assert _extract_llama_completion(prompt+'\n'+answer,prompt)==answer


def test_unrelated_banner_never_silently_removed():
    prompt='승인된 직원 지시'
    raw='unrecognized banner\n'+prompt+'\n실제 생성'
    assert _extract_llama_completion(raw,prompt)==raw


def test_echo_only_rejected():
    with pytest.raises(ValueError,match='생성 응답'):
        _extract_llama_completion('업무 지시','업무 지시')


def test_prompt_appearing_in_model_reply_is_not_removed():
    assert _extract_llama_completion('답변에 업무 지시가 있습니다','업무 지시')=='답변에 업무 지시가 있습니다'


def test_exact_echo_after_only_whitespace():
    assert _extract_llama_completion('\n  업무\n실제 생성','업무')=='실제 생성'
