"""Synthetic subprocess regression for clean official CPU runner selection."""
from pathlib import Path
import os
import json
import sys
import pytest
from validation.real_gguf_preflight import verify_cli


def script(path, *, code, text='SYNTHETIC TEST OUTPUT'):
    path.write_text(f'#!{sys.executable} -S\nimport sys\nprint({text!r})\nsys.exit({code})\n', encoding='utf-8')
    path.chmod(0o755)
    return path


def fixtures(tmp_path):
    model = tmp_path / 'test-only.gguf'
    model.write_bytes(b'GGUF\x00\x00\x00\x00')
    return model, tmp_path / 'evidence.txt', tmp_path / 'chosen.txt'


@pytest.mark.skipif(os.name == 'nt', reason='Fake executable fixture uses Unix shebang; real GGUF is Windows Actions')
def test_clean_official_primary_is_selected_without_fallback(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    primary = script(tmp_path / 'llama-completion.exe', code=0)
    script(tmp_path / 'llama-cli.exe', code=1)
    assert verify_cli(primary, model, evidence, chosen) == primary
    assert chosen.read_text().strip() == str(primary)
    assert [(x['cli'], x['returncode'], x['accepted']) for x in json.loads(evidence.read_text())['attempts']] == [('llama-completion.exe', 0, True)]


@pytest.mark.skipif(os.name == 'nt', reason='Fake executable fixture uses Unix shebang')
def test_nonzero_exit_with_output_cannot_pass_and_clean_alternative_is_used(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    primary = script(tmp_path / 'llama-completion.exe', code=10)
    alternative = script(tmp_path / 'llama-cli.exe', code=0)
    assert verify_cli(primary, model, evidence, chosen) == alternative
    attempts = json.loads(evidence.read_text())['attempts']
    assert [(x['cli'], x['returncode'], x['accepted']) for x in attempts] == [('llama-completion.exe', 10, False), ('llama-cli.exe', 0, True)]


@pytest.mark.skipif(os.name == 'nt', reason='Fake executable fixture uses Unix shebang')
def test_both_failing_preserves_failure_and_never_writes_success_marker(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    primary = script(tmp_path / 'llama-completion.exe', code=5)
    script(tmp_path / 'llama-cli.exe', code=5)
    chosen.write_text('obsolete previous success')
    with pytest.raises(RuntimeError, match='GGUF'):
        verify_cli(primary, model, evidence, chosen)
    assert not chosen.exists()
    assert [x['returncode'] for x in json.loads(evidence.read_text())['attempts']] == [5, 5]


@pytest.mark.skipif(os.name == 'nt', reason='Fake executable fixture uses Unix shebang')
def test_zero_exit_with_no_model_output_is_failure(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    primary = script(tmp_path / 'llama-completion.exe', code=0, text='')
    with pytest.raises(RuntimeError):
        verify_cli(primary, model, evidence, chosen)
    assert not chosen.exists()
    assert json.loads(evidence.read_text())['attempts'][0]['response_beyond_prompt'] is False


def test_rejects_corrupted_model_file_before_inference(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    model.write_bytes(b'BAD!')
    primary = tmp_path / 'llama-completion.exe'
    primary.write_bytes(b'SYNTHETIC')
    with pytest.raises(ValueError, match='GGUF'):
        verify_cli(primary, model, evidence, chosen)
    assert not chosen.exists()


def test_stale_selection_is_invalidated_before_invalid_model(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    model.write_bytes(b'BAD!')
    chosen.write_text('stale success', encoding='utf-8')
    primary = tmp_path / 'llama-cli.exe'
    primary.write_bytes(b'fixture')
    with pytest.raises(ValueError, match='GGUF'):
        verify_cli(primary, model, evidence, chosen)
    assert not chosen.exists()


def test_selection_and_evidence_must_be_distinct(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    primary = tmp_path / 'llama-cli.exe'
    primary.write_bytes(b'fixture')
    with pytest.raises(ValueError, match='겹칩니다'):
        verify_cli(primary, model, evidence, evidence)


def test_selection_symlink_rejected_without_modifying_target(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    primary = tmp_path / 'llama-cli.exe'
    primary.write_bytes(b'fixture')
    original = tmp_path / 'original.txt'
    original.write_text('원본 보존', encoding='utf-8')
    try:
        chosen.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip('Symlink unavailable')
    with pytest.raises(ValueError, match='심볼릭 링크'):
        verify_cli(primary, model, evidence, chosen)
    assert original.read_text(encoding='utf-8') == '원본 보존'


@pytest.mark.skipif(os.name == 'nt', reason='Unix subprocess fixture')
def test_success_marker_is_published_after_real_process_result(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    primary = script(tmp_path / 'llama-cli.exe', code=0)
    chosen.write_text('old marker', encoding='utf-8')
    assert verify_cli(primary, model, evidence, chosen) == primary
    assert chosen.read_text(encoding='utf-8').strip() == str(primary)
    assert json.loads(evidence.read_text(encoding='utf-8'))['selected'] == primary.name


def test_output_dotdot_alias_cannot_replace_model(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    (tmp_path / 'nested').mkdir()
    primary = tmp_path / 'llama-cli.exe'
    primary.write_bytes(b'fixture')
    aliased_model = tmp_path / 'nested' / '..' / model.name
    original = model.read_bytes()
    with pytest.raises(ValueError, match='겹칩니다'):
        verify_cli(primary, model, evidence, aliased_model)
    assert model.read_bytes() == original


def test_evidence_alias_cannot_replace_binary(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    (tmp_path / 'nested').mkdir()
    primary = tmp_path / 'llama-cli.exe'
    primary.write_bytes(b'fixture')
    original = primary.read_bytes()
    with pytest.raises(ValueError, match='겹칩니다'):
        verify_cli(primary, model, tmp_path / 'nested' / '..' / primary.name, chosen)
    assert primary.read_bytes() == original
