"""Synthetic subprocess regression for clean official CPU runner selection."""
from pathlib import Path
import os
import sys
import pytest
from validation.real_gguf_preflight import verify_cli


def script(path, *, code, text='SYNTHETIC TEST OUTPUT'):
    path.write_text(f'#!{sys.executable}\nimport sys\nprint({text!r})\nsys.exit({code})\n', encoding='utf-8')
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
    assert evidence.read_text().count('returncode=') == 1


@pytest.mark.skipif(os.name == 'nt', reason='Fake executable fixture uses Unix shebang')
def test_nonzero_exit_with_output_cannot_pass_and_clean_alternative_is_used(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    primary = script(tmp_path / 'llama-completion.exe', code=10)
    alternative = script(tmp_path / 'llama-cli.exe', code=0)
    assert verify_cli(primary, model, evidence, chosen) == alternative
    report = evidence.read_text()
    assert 'llama-completion.exe: returncode=10 has_output=True' in report
    assert 'llama-cli.exe: returncode=0 has_output=True' in report


@pytest.mark.skipif(os.name == 'nt', reason='Fake executable fixture uses Unix shebang')
def test_both_failing_preserves_failure_and_never_writes_success_marker(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    primary = script(tmp_path / 'llama-completion.exe', code=5)
    script(tmp_path / 'llama-cli.exe', code=5)
    chosen.write_text('obsolete previous success')
    with pytest.raises(RuntimeError, match='No genuine'):
        verify_cli(primary, model, evidence, chosen)
    assert not chosen.exists()
    assert evidence.read_text().count('returncode=5') == 2


@pytest.mark.skipif(os.name == 'nt', reason='Fake executable fixture uses Unix shebang')
def test_zero_exit_with_no_model_output_is_failure(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    primary = script(tmp_path / 'llama-completion.exe', code=0, text='')
    with pytest.raises(RuntimeError):
        verify_cli(primary, model, evidence, chosen)
    assert not chosen.exists()
    assert 'has_output=False' in evidence.read_text()


def test_rejects_corrupted_model_file_before_inference(tmp_path):
    model, evidence, chosen = fixtures(tmp_path)
    model.write_bytes(b'BAD!')
    primary = tmp_path / 'llama-completion.exe'
    primary.write_bytes(b'SYNTHETIC')
    with pytest.raises(ValueError, match='GGUF'):
        verify_cli(primary, model, evidence, chosen)
    assert not chosen.exists()
