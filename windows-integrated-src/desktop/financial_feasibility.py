"""Stage64: owner-assumption-only, offline financial *scenario* evaluation.

Not forecasts, verified market data, accounting, sales, settlement, or a
recommendation to spend money. Uses integer KRW and integer basis points to
avoid binary floating point. Local audit is not cryptographically tamper-proof.
"""
from __future__ import annotations

import json
import sqlite3

from desktop.business_portfolio import _hash, _id, _label

LIMIT_KRW = 1_000_000_000_000
MAX_UNITS = 1_000_000
BREAK_EVEN_CAP = 1_000_000_000
_FIELDS = ('unit_price_krw', 'monthly_units', 'unit_cost_krw', 'monthly_fixed_krw',
           'monthly_marketing_krw', 'setup_cost_krw', 'refund_bps', 'payment_fee_bps', 'months')


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS financial_assumption_evaluations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      candidate_id INTEGER REFERENCES opportunity_candidates(id) ON DELETE RESTRICT,
      business_id INTEGER REFERENCES managed_businesses(id) ON DELETE RESTRICT,
      unit_price_krw INTEGER NOT NULL CHECK(unit_price_krw BETWEEN 0 AND 1000000000000),
      monthly_units INTEGER NOT NULL CHECK(monthly_units BETWEEN 0 AND 1000000),
      unit_cost_krw INTEGER NOT NULL CHECK(unit_cost_krw BETWEEN 0 AND 1000000000000),
      monthly_fixed_krw INTEGER NOT NULL CHECK(monthly_fixed_krw BETWEEN 0 AND 1000000000000),
      monthly_marketing_krw INTEGER NOT NULL CHECK(monthly_marketing_krw BETWEEN 0 AND 1000000000000),
      setup_cost_krw INTEGER NOT NULL CHECK(setup_cost_krw BETWEEN 0 AND 1000000000000),
      refund_bps INTEGER NOT NULL CHECK(refund_bps BETWEEN 0 AND 10000),
      payment_fee_bps INTEGER NOT NULL CHECK(payment_fee_bps BETWEEN 0 AND 10000),
      months INTEGER NOT NULL CHECK(months BETWEEN 1 AND 120),
      owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 1 AND 200),
      input_digest TEXT NOT NULL CHECK(length(input_digest)=64),
      result_json TEXT NOT NULL CHECK(length(result_json) BETWEEN 2 AND 6000),
      result_digest TEXT NOT NULL CHECK(length(result_digest)=64),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CHECK((candidate_id IS NOT NULL AND business_id IS NULL) OR
            (candidate_id IS NULL AND business_id IS NOT NULL))
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS financial_assumption_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      evaluation_id INTEGER NOT NULL REFERENCES financial_assumption_evaluations(id) ON DELETE RESTRICT,
      action TEXT NOT NULL CHECK(action='evaluated'),
      detail TEXT NOT NULL CHECK(length(detail) BETWEEN 2 AND 500),
      digest TEXT NOT NULL CHECK(length(digest)=64),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS financial_assumptions_candidate ON financial_assumption_evaluations(candidate_id,id)')
    con.execute('CREATE INDEX IF NOT EXISTS financial_assumptions_business ON financial_assumption_evaluations(business_id,id)')
    for table in ('financial_assumption_evaluations', 'financial_assumption_events'):
        for op in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
              BEFORE {op} ON {table} BEGIN
              SELECT RAISE(ABORT, 'financial scenario audit is append-only'); END''')


def _nonnegative_int(name: str, value: int, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name}: 0~{maximum} 범위의 정수가 필요합니다.')
    return value


def _validate(values: dict) -> dict:
    if not isinstance(values, dict) or set(values) != set(_FIELDS):
        raise ValueError('필수 가정 항목 9개를 정확히 입력해야 합니다.')
    clean = {}
    for key in _FIELDS:
        max_value = 10000 if key.endswith('_bps') else (MAX_UNITS if key == 'monthly_units'
                    else 120 if key == 'months' else LIMIT_KRW)
        if key == 'months':
            if type(values[key]) is not int or not 1 <= values[key] <= 120:
                raise ValueError('평가 기간은 1~120개월 정수여야 합니다.')
            clean[key] = values[key]
        else:
            clean[key] = _nonnegative_int(key, values[key], max_value)
    if clean['refund_bps'] + clean['payment_fee_bps'] > 10000:
        raise ValueError('환불률과 결제 수수료율의 합이 100%를 넘을 수 없습니다.')
    return clean


def _monthly(a: dict, units: int) -> dict:
    gross = a['unit_price_krw'] * units
    # Round the combined deductions ONCE to whole KRW to preserve monotonic
    # net proceeds per additional unit (required by binary-search break-even).
    # Allocate the refund share by truncation and remainder to payment fees.
    # Fees are based on gross even if a transaction is later refunded.
    total_deductions = (gross * (a['refund_bps'] + a['payment_fee_bps']) + 5000) // 10000
    refunds = (gross * a['refund_bps']) // 10000
    fees = total_deductions - refunds
    variable = a['unit_cost_krw'] * units
    costs = variable + a['monthly_fixed_krw'] + a['monthly_marketing_krw'] + fees
    net = gross - refunds - costs
    return {'units': units, 'gross_assumed_krw': gross, 'refunds_assumed_krw': refunds,
            'payment_fees_assumed_krw': fees, 'variable_cost_assumed_krw': variable,
            'fixed_cost_assumed_krw': a['monthly_fixed_krw'],
            'marketing_cost_assumed_krw': a['monthly_marketing_krw'],
            'monthly_net_assumed_krw': net,
            'horizon_net_after_setup_assumed_krw': net * a['months'] - a['setup_cost_krw']}


def calculate(assumptions: dict) -> dict:
    """Deterministic what-if arithmetic, never evidence of future or actual revenue."""
    a = _validate(assumptions)
    low = (a['monthly_units'] * 75) // 100
    high = (a['monthly_units'] * 125 + 99) // 100
    scenarios = {'downside_25pct_units': _monthly(a, low),
                 'base_owner_assumption': _monthly(a, a['monthly_units']),
                 'upside_25pct_units': _monthly(a, high)}
    # Exact integer break-even for the whole horizon, including one-off setup.
    # Do not extrapolate beyond the explicit calculation cap.
    if _monthly(a, BREAK_EVEN_CAP)['horizon_net_after_setup_assumed_krw'] < 0:
        break_even = None
        break_even_note = '가정상 10억 개/월 이내 손익분기점 없음(단위당 마진 또는 비용 확인 필요)'
    else:
        lo, hi = 0, BREAK_EVEN_CAP
        while lo < hi:
            mid = (lo + hi) // 2
            if _monthly(a, mid)['horizon_net_after_setup_assumed_krw'] >= 0:
                hi = mid
            else:
                lo = mid + 1
        break_even = lo
        break_even_note = '가정 기반 월 판매량 손익분기점(실제 수요 검증 아님)'
    return {'scenario_kind': 'owner_entered_unverified_assumptions',
            'currency': 'KRW', 'horizon_months': a['months'],
            'scenarios': scenarios, 'break_even_monthly_units_assumed': break_even,
            'break_even_note': break_even_note,
            'market_demand_verified': False, 'sales_verified': False,
            'actual_revenue_krw': None, 'actual_profit_krw': None,
            'external_actions_executed': False,
            'warning': '관리자 입력값의 산술적 시나리오일 뿐 실제 수요·매출·수익 예측 또는 회계 기록이 아닙니다.'}


def evaluate(con: sqlite3.Connection, subject_kind: str, subject_id: int,
             assumptions: dict, owner_note: str) -> int:
    if subject_kind not in ('candidate', 'business') or type(subject_kind) is not str:
        raise ValueError('대상은 후보(candidate) 또는 등록 사업(business)이어야 합니다.')
    _id(subject_id, '사업/후보')
    owner_note = _label(owner_note, '가정 출처·한계 메모', 200)
    a = _validate(assumptions)
    table = 'opportunity_candidates' if subject_kind == 'candidate' else 'managed_businesses'
    if con.execute(f'SELECT 1 FROM {table} WHERE id=?', (subject_id,)).fetchone() is None:
        raise ValueError('등록된 사업/후보가 없습니다.')
    key = 'candidate_id' if subject_kind == 'candidate' else 'business_id'
    if con.execute(f'SELECT COUNT(*) FROM financial_assumption_evaluations WHERE {key}=?',
                   (subject_id,)).fetchone()[0] >= 100:
        raise ValueError('대상별 평가 기록은 최대 100건입니다.')
    result = calculate(a)
    identity = {'subject_kind': subject_kind, 'subject_id': subject_id,
                'assumptions': a, 'owner_note': owner_note}
    result_text = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    if len(result_text) > 6000:
        raise ValueError('평가 결과가 저장 크기를 초과했습니다.')
    columns = ('candidate_id,business_id,' + ','.join(_FIELDS) +
               ',owner_note,input_digest,result_json,result_digest')
    values = ((subject_id if subject_kind == 'candidate' else None),
              (subject_id if subject_kind == 'business' else None),
              *(a[field] for field in _FIELDS), owner_note, _hash(identity), result_text, _hash(result))
    placeholders = ','.join('?' for _ in values)
    cur = con.execute(f'INSERT INTO financial_assumption_evaluations({columns}) VALUES({placeholders})', values)
    eval_id = int(cur.lastrowid)
    payload = {'evaluation_id': eval_id, 'subject_kind': subject_kind, 'subject_id': subject_id,
               'input_digest': _hash(identity), 'result_digest': _hash(result)}
    detail = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    con.execute('INSERT INTO financial_assumption_events(evaluation_id,action,detail,digest) VALUES(?,?,?,?)',
                (eval_id, 'evaluated', detail, _hash(payload)))
    return eval_id


def report(con: sqlite3.Connection, evaluation_id: int) -> dict:
    _id(evaluation_id, '평가')
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM financial_assumption_evaluations WHERE id=?', (evaluation_id,)).fetchone()
    if row is None:
        raise ValueError('평가 기록이 없습니다.')
    data = dict(row)
    kind = 'candidate' if data['candidate_id'] is not None else 'business'
    subject_id = data['candidate_id'] if kind == 'candidate' else data['business_id']
    a = {name: data[name] for name in _FIELDS}
    identity = {'subject_kind': kind, 'subject_id': subject_id,
                'assumptions': a, 'owner_note': data['owner_note']}
    if _hash(identity) != data['input_digest']:
        raise ValueError('평가 입력 무결성 오류')
    try:
        saved = json.loads(data['result_json'])
    except (ValueError, TypeError) as exc:
        raise ValueError('평가 결과 JSON 손상') from exc
    if not isinstance(saved, dict) or _hash(saved) != data['result_digest'] or saved != calculate(a):
        raise ValueError('평가 결과 무결성 오류')
    history = con.execute('SELECT action,detail,digest FROM financial_assumption_events WHERE evaluation_id=?',
                          (evaluation_id,)).fetchall()
    if len(history) != 1 or history[0]['action'] != 'evaluated':
        raise ValueError('평가 감사 이벤트 누락/중복')
    try:
        payload = json.loads(history[0]['detail'])
    except (ValueError, TypeError) as exc:
        raise ValueError('평가 감사 JSON 손상') from exc
    expected = {'evaluation_id': evaluation_id, 'subject_kind': kind, 'subject_id': subject_id,
                'input_digest': data['input_digest'], 'result_digest': data['result_digest']}
    if payload != expected or _hash(payload) != history[0]['digest']:
        raise ValueError('평가 감사 무결성 오류')
    return {'id': evaluation_id, 'subject_kind': kind, 'subject_id': subject_id,
            'owner_note': data['owner_note'], 'assumptions': a, 'result': saved,
            'created_at': data['created_at']}


def history(con: sqlite3.Connection, subject_kind: str, subject_id: int, limit: int = 30) -> list[dict]:
    if type(subject_kind) is not str or subject_kind not in ('candidate', 'business'):
        raise ValueError('평가 대상 유형이 유효하지 않습니다.')
    _id(subject_id, '사업/후보')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('조회 개수는 1~100입니다.')
    key = 'candidate_id' if subject_kind == 'candidate' else 'business_id'
    table = 'opportunity_candidates' if subject_kind == 'candidate' else 'managed_businesses'
    if con.execute(f'SELECT 1 FROM {table} WHERE id=?', (subject_id,)).fetchone() is None:
        raise ValueError('등록된 사업/후보가 없습니다.')
    ids = [r[0] for r in con.execute(
        f'SELECT id FROM financial_assumption_evaluations WHERE {key}=? ORDER BY id DESC LIMIT ?',
        (subject_id, limit)).fetchall()]
    return [report(con, ident) for ident in ids]
