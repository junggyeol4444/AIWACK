"""실제 CLI 사전검사 실패 차단 및 호환 인수 재시도 회귀."""
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import pytest

spec = importlib.util.spec_from_file_location(
    'aiwack_real_gguf_preflight', Path(__file__).with_name('real_gguf_preflight.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _files(tmp_path):
    cli = tmp_path / 'llama-completion.exe'
    cli.write_bytes(b'original-binary-placeholder')
    gguf = tmp_path / 'genuine.gguf'
    gguf.write_bytes(b'GGUF' + b'fixture-metadata')
    return cli, gguf, tmp_path / 'audit.json', tmp_path / 'selected.txt'


def _result(code, out='', err=''):
    return subprocess.CompletedProcess([], code, stdout=out, stderr=err)


def test_real_output_success_and_audit(tmp_path):
    paths = _files(tmp_path)
    with patch.object(module.subprocess, 'run',
                      return_value=_result(0, module._PROMPT+'\nconfirmed')) as run:
        assert module.verify_cli(*paths) == paths[0]
    assert run.call_count == 1
    report = json.loads(paths[2].read_text())
    assert report['attempts'][0]['accepted'] is True
    assert report['not_windows_gui_acceptance'] is True
    assert paths[3].read_text().strip() == str(paths[0])


def test_prompt_only_never_passes(tmp_path):
    paths = _files(tmp_path)
    with patch.object(module.subprocess, 'run',
                      return_value=_result(0, module._PROMPT)) as run:
        with pytest.raises(RuntimeError): module.verify_cli(*paths)
    assert run.call_count == 1
    assert not paths[3].exists()
    assert json.loads(paths[2].read_text())['selected'] is None


def test_optional_flag_unsupported_retries_minimal_arguments(tmp_path):
    paths = _files(tmp_path)
    with patch.object(module.subprocess, 'run', side_effect=[
        _result(2, '', 'error: unknown argument: --single-turn'),
        _result(0, module._PROMPT + '\nverified')]) as run:
        assert module.verify_cli(*paths) == paths[0]
    assert run.call_count == 2
    assert '--single-turn' in run.call_args_list[0].args[0]
    assert '--single-turn' not in run.call_args_list[1].args[0]


def test_crash_never_retries_same_binary_with_fewer_flags(tmp_path):
    paths = _files(tmp_path)
    with patch.object(module.subprocess, 'run',
                      return_value=_result(-1073740940, 'text', 'heap corruption')) as run:
        with pytest.raises(RuntimeError): module.verify_cli(*paths)
    assert run.call_count == 1
    assert not paths[3].exists()


def test_verified_sibling_binary_fallback(tmp_path):
    paths = _files(tmp_path)
    sibling = tmp_path / 'llama-cli.exe'
    sibling.write_bytes(b'original-sibling-binary-placeholder')
    with patch.object(module.subprocess, 'run', side_effect=[
        _result(-1, '', 'crash'), _result(0, module._PROMPT + '\nhello')]) as run:
        assert module.verify_cli(*paths) == sibling
    assert run.call_count == 2
    assert json.loads(paths[2].read_text())['selected'] == sibling.name


def test_invalid_input_and_timeout_fail_before_inference(tmp_path):
    paths = _files(tmp_path)
    with patch.object(module.subprocess, 'run') as run:
        with pytest.raises(ValueError): module.verify_cli(*paths, timeout=True)
        paths[1].write_bytes(b'not a model')
        with pytest.raises(ValueError): module.verify_cli(*paths)
        run.assert_not_called()
