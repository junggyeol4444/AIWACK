"""Windows 2022 실 GGUF 30업무 뒤 총괄보고 timeout=180 계약 실패 회귀."""
import ast
import inspect
from desktop import company_campaign_final_report as final
from desktop import model_runtime


def _literal_timeout_values(func, called_name):
    source = inspect.getsource(func)
    tree = ast.parse(source)
    values = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == called_name):
            keyword = next((item for item in node.keywords if item.arg == 'timeout'), None)
            assert keyword is not None, '실제 모델 호출에 timeout을 명시해야 합니다.'
            values.append(ast.literal_eval(keyword.value))
    return values


def test_final_report_timeout_within_actual_model_contract():
    values = _literal_timeout_values(final.propose, 'invoke_employee_model')
    assert values == [120]
    assert all(type(v) is int and 1 <= v <= 120 for v in values)


def test_model_runtime_rejects_timeout_over_120():
    source = inspect.getsource(model_runtime.run_local_model)
    assert '1 <= timeout <= 120' in source
