"""Stage57: execute a deliberately tiny, resource-bounded Python AST subset.

This is NOT a Python VM or an OS security sandbox. No eval/exec/import,
subprocesses, filesystem APIs, callable builtins, or arbitrary Python objects
are exposed to the source. Unsupported syntax is rejected *before* evaluation.
For real unrestricted code execution use a separately audited OS isolation layer.
"""
from __future__ import annotations

import ast
import hashlib
import math
import operator
import re
import sqlite3

MAX_CASE_BYTES = 4096
MAX_AST_NODES = 240
MAX_EVALUATIONS = 1200
MAX_CASES = 20
MAX_VALUE_CHARS = 4096
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z', re.ASCII)

class RestrictedCodeError(ValueError):
    pass

# No attribute access, indexing, list comprehensions, imports or dynamic builtins.
_ALLOWED = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Assign,
            ast.Return, ast.If, ast.Pass, ast.Assert, ast.Constant,
            ast.Name, ast.Load, ast.Store, ast.Call, ast.Compare, ast.BinOp,
            ast.UnaryOp, ast.BoolOp, ast.IfExp, ast.Add, ast.Sub, ast.Mult,
            ast.Div, ast.FloorDiv, ast.Mod, ast.USub, ast.UAdd, ast.Not,
            ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt,
            ast.GtE, ast.Is, ast.IsNot)
_BIN = {ast.Add:operator.add, ast.Sub:operator.sub, ast.Mult:operator.mul,
        ast.Div:operator.truediv, ast.FloorDiv:operator.floordiv,
        ast.Mod:operator.mod}
_COMPARE = {ast.Eq:operator.eq, ast.NotEq:operator.ne,
            ast.Lt:operator.lt, ast.LtE:operator.le, ast.Gt:operator.gt,
            ast.GtE:operator.ge, ast.Is:operator.is_, ast.IsNot:operator.is_not}


def _name(s: str) -> None:
    if not isinstance(s,str) or not NAME.fullmatch(s) or s.startswith('_'):
        raise RestrictedCodeError('제한 모드에서 영문 이름만 사용할 수 있습니다.')


def _parse(source: str, *, tests: bool) -> ast.Module:
    from desktop.code_authoring import _source
    if not tests:
        _source(source)
    elif not isinstance(source,str) or len(source.encode('utf-8')) > MAX_CASE_BYTES:
        raise RestrictedCodeError('단언문 입력은 UTF-8 4KiB 이하여야 합니다.')
    try:
        tree = ast.parse(source, mode='exec')
    except (SyntaxError, ValueError, TypeError, RecursionError) as exc:
        raise RestrictedCodeError('Python 구문이 올바르지 않습니다.') from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES or not tree.body:
        raise RestrictedCodeError('검사할 코드가 없거나 AST가 너무 큽니다.')
    for node in nodes:
        if not isinstance(node, _ALLOWED):
            raise RestrictedCodeError('허용하지 않는 Python 구문: '+type(node).__name__)
        if isinstance(node, ast.Name):_name(node.id)
        if isinstance(node, ast.arg):_name(node.arg)
        if isinstance(node, ast.FunctionDef):
            _name(node.name)
            a=node.args
            if node.decorator_list or node.returns or node.type_comment or a.posonlyargs or a.kwonlyargs or a.defaults or a.kw_defaults or a.vararg or a.kwarg or len(a.args)>8:
                raise RestrictedCodeError('간단한 위치 인수 함수만 허용합니다.')
            if len({x.arg for x in a.args}) != len(a.args):
                raise RestrictedCodeError('중복 매개변수')
        if isinstance(node, ast.Assign):
            if len(node.targets)!=1 or not isinstance(node.targets[0],ast.Name):
                raise RestrictedCodeError('하나의 변수 대입만 허용합니다.')
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.keywords or len(node.args)>8:
                raise RestrictedCodeError('사용자 정의 함수의 위치 인수 호출만 허용합니다.')
        if isinstance(node, ast.Constant):
            if type(node.value) not in (int,float,str,bool,type(None)):
                raise RestrictedCodeError('해당 상수 유형은 허용하지 않습니다.')
            _bounded(node.value)
    if tests:
        if len(tree.body)>MAX_CASES or any(not isinstance(n, ast.Assert) or n.msg is not None for n in tree.body):
            raise RestrictedCodeError('테스트는 assert 조건식만 1~20개 허용합니다.')
    else:
        if any(not isinstance(n, (ast.Assign, ast.FunctionDef)) for n in tree.body):
            raise RestrictedCodeError('최상위에는 상수 대입과 함수 정의만 허용합니다.')
        for node in tree.body:
            if isinstance(node,ast.FunctionDef):
                _validate_statements(node.body)
    return tree


def _validate_statements(nodes):
    for node in nodes:
        if isinstance(node,ast.Assign):continue
        if isinstance(node,(ast.Return,ast.Pass)):continue
        if isinstance(node,ast.If):
            _validate_statements(node.body); _validate_statements(node.orelse); continue
        raise RestrictedCodeError('함수에서는 대입·return·if·pass만 허용합니다.')


def _bounded(value):
    if type(value) is int and value.bit_length()>128:
        raise RestrictedCodeError('정수 크기 제한(128비트)')
    if type(value) is float and not math.isfinite(value):
        raise RestrictedCodeError('비유한 숫자는 허용하지 않습니다.')
    if type(value) is str and len(value)>MAX_VALUE_CHARS:
        raise RestrictedCodeError('문자열 길이 제한')
    if type(value) not in (int,float,str,bool,type(None)):
        raise RestrictedCodeError('허용되지 않는 계산 결과')
    return value


class _Runner:
    def __init__(self, tree):
        self.functions={};self.globals={};self.steps=0;self.stack=[]
        for stmt in tree.body:
            if isinstance(stmt,ast.FunctionDef):
                if stmt.name in self.functions or stmt.name in self.globals:
                    raise RestrictedCodeError('중복 이름')
                self.functions[stmt.name]=stmt
            else:
                if stmt.targets[0].id in self.functions or stmt.targets[0].id in self.globals:
                    raise RestrictedCodeError('중복 이름')
                self.globals[stmt.targets[0].id]=self.eval(stmt.value,{})

    def tick(self):
        self.steps+=1
        if self.steps>MAX_EVALUATIONS:raise RestrictedCodeError('계산 횟수 제한')

    def eval(self,node,scope):
        self.tick()
        if isinstance(node,ast.Constant): return _bounded(node.value)
        if isinstance(node,ast.Name):
            if node.id in scope:return scope[node.id]
            if node.id in self.globals:return self.globals[node.id]
            raise RestrictedCodeError('정의되지 않은 변수: '+node.id)
        if isinstance(node,ast.UnaryOp):
            v=self.eval(node.operand,scope)
            if isinstance(node.op,ast.Not):return not bool(v)
            if type(v) not in (int,float):raise RestrictedCodeError('숫자 연산만 허용합니다.')
            return _bounded(-v if isinstance(node.op,ast.USub) else +v)
        if isinstance(node,ast.BinOp):
            a=self.eval(node.left,scope);b=self.eval(node.right,scope)
            if type(a) not in (int,float) or type(b) not in (int,float):
                # Only bounded string concatenation; no arbitrary multiplication.
                if type(a) is str and type(b) is str and isinstance(node.op,ast.Add):
                    if len(a)+len(b)>MAX_VALUE_CHARS:raise RestrictedCodeError('문자열 크기 제한')
                    return a+b
                raise RestrictedCodeError('지원하지 않는 자료형 연산')
            if isinstance(node.op,ast.Mult) and (abs(a)>1e30 or abs(b)>1e30):
                raise RestrictedCodeError('수치 곱셈 크기 제한')
            try:result=_BIN[type(node.op)](a,b)
            except (ZeroDivisionError,OverflowError,ValueError) as exc:
                raise RestrictedCodeError('산술 연산 실패') from exc
            return _bounded(result)
        if isinstance(node,ast.BoolOp):
            value=None
            for part in node.values:
                value=self.eval(part,scope)
                if isinstance(node.op,ast.And) and not value:break
                if isinstance(node.op,ast.Or) and value:break
            return value
        if isinstance(node,ast.IfExp):return self.eval(node.body if self.eval(node.test,scope) else node.orelse,scope)
        if isinstance(node,ast.Compare):
            last=self.eval(node.left,scope)
            for op,nextnode in zip(node.ops,node.comparators):
                right=self.eval(nextnode,scope)
                if type(op) in (ast.Lt,ast.LtE,ast.Gt,ast.GtE) and type(last)!=type(right):
                    raise RestrictedCodeError('서로 다른 유형은 크기 비교 불가')
                if not _COMPARE[type(op)](last,right):return False
                last=right
            return True
        if isinstance(node,ast.Call):
            name=node.func.id
            if name not in self.functions:raise RestrictedCodeError('등록된 함수만 호출할 수 있습니다.')
            fn=self.functions[name]
            if name in self.stack or len(self.stack)>=6:
                raise RestrictedCodeError('재귀 또는 호출 깊이 제한')
            if len(node.args)!=len(fn.args.args):raise RestrictedCodeError('함수 인수 수가 다릅니다.')
            arguments=[self.eval(part,scope) for part in node.args]
            self.stack.append(name)
            try:
                return self.statements(fn.body,dict(zip((p.arg for p in fn.args.args),arguments)))[1]
            finally:self.stack.pop()
        raise RestrictedCodeError('허용되지 않는 표현식')

    def statements(self,nodes,scope):
        for node in nodes:
            self.tick()
            if isinstance(node,ast.Pass):continue
            if isinstance(node,ast.Assign):scope[node.targets[0].id]=self.eval(node.value,scope)
            elif isinstance(node,ast.Return):return True, self.eval(node.value,scope) if node.value else None
            elif isinstance(node,ast.If):
                complete,result=self.statements(node.body if self.eval(node.test,scope) else node.orelse,scope)
                if complete:return True,result
            else:raise RestrictedCodeError('허용되지 않는 명령')
        return False,None


def execute_restricted_tests(source:str, cases:str) -> dict:
    """Deterministic limited AST evaluation of saved source against owner assertions."""
    source_tree=_parse(source,tests=False)
    case_tree=_parse(cases,tests=True)
    names={node.name for node in source_tree.body if isinstance(node,ast.FunctionDef)}
    for tree in (source_tree,case_tree):
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and node.func.id not in names:
                raise RestrictedCodeError('사용자 정의 함수 외 호출 금지: '+node.func.id)
    runner=_Runner(source_tree)
    rows=[]
    for idx,case in enumerate(case_tree.body,1):
        try:
            ok=runner.eval(case.test,{}) is True
            rows.append({'case':idx,'passed':ok,'detail':'통과' if ok else '조건 불일치'})
        except (RestrictedCodeError,ArithmeticError) as exc:
            rows.append({'case':idx,'passed':False,'detail':str(exc)[:100]})
    return {'passed':sum(r['passed'] for r in rows),'total':len(rows),'results':rows,
            'source_sha256':hashlib.sha256(source.encode('utf-8')).hexdigest(),
            'tests_sha256':hashlib.sha256(cases.encode('utf-8')).hexdigest()}


def initialize(con:sqlite3.Connection)->None:
    con.execute('''CREATE TABLE IF NOT EXISTS restricted_code_test_runs (
        id INTEGER PRIMARY KEY,artifact_id INTEGER NOT NULL REFERENCES local_code_artifacts(id) ON DELETE RESTRICT,
        version INTEGER NOT NULL,source_digest TEXT NOT NULL,tests_digest TEXT NOT NULL,
        passed INTEGER NOT NULL,total INTEGER NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('passed','failed')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for verb in ('UPDATE','DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS restricted_code_test_runs_no_{verb.lower()}
        BEFORE {verb} ON restricted_code_test_runs BEGIN
        SELECT RAISE(ABORT,'restricted test history is immutable'); END''')


def record(con:sqlite3.Connection,artifact:dict,result:dict)->int:
    if artifact['digest']!=result['source_sha256']:
        raise RestrictedCodeError('실행 전 원본 코드 해시 불일치')
    cur=con.execute('''INSERT INTO restricted_code_test_runs
        (artifact_id,version,source_digest,tests_digest,passed,total,status)
        VALUES (?,?,?,?,?,?,?)''',
        (artifact['id'],artifact['version'],artifact['digest'],result['tests_sha256'],
         result['passed'],result['total'],'passed' if result['passed']==result['total'] else 'failed'))
    return cur.lastrowid
