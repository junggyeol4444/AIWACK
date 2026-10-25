"""Stage65: owner-invoked real local chief GGUF over immutable financial briefs.

Model advice is a hypothesis, not verified revenue, spending authorization,
autonomous business launch or market validation. Never retries a prior attempt.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import threading
from desktop.stage87_90_management import stopped
from desktop.chief_business_decisions import get as get_brief, initialize as init_briefs


def initialize(con):
    init_briefs(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_real_chief_brief_claims(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      brief_id INTEGER NOT NULL UNIQUE REFERENCES chief_business_briefs(id),
      snapshot_sha256 TEXT NOT NULL CHECK(length(snapshot_sha256)=64),
      prompt_sha256 TEXT NOT NULL CHECK(length(prompt_sha256)=64),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_real_chief_brief_outcomes(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      claim_id INTEGER NOT NULL UNIQUE REFERENCES aiwack_real_chief_brief_claims(id),
      state TEXT NOT NULL CHECK(state IN('success','failed','cancelled','invalid_output')),
      model_call_id INTEGER REFERENCES ai_model_call_history(id),
      output_sha256 TEXT,
      evaluation_id INTEGER REFERENCES financial_assumption_evaluations(id),
      rationale TEXT NOT NULL DEFAULT '' CHECK(length(rationale)<=500),
      risk TEXT NOT NULL DEFAULT '' CHECK(length(risk)<=400),
      unknowns TEXT NOT NULL DEFAULT '' CHECK(length(unknowns)<=400),
      error_kind TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for table in ('aiwack_real_chief_brief_claims','aiwack_real_chief_brief_outcomes'):
        for op in ('UPDATE','DELETE'):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
                BEFORE {op} ON {table}
                BEGIN SELECT RAISE(ABORT,'총괄 GGUF 손익 평가 감사 원본 변경 금지'); END""")


def _parse(raw, ids):
    if type(raw) is not str or len(raw)>12000: raise ValueError('실제 총괄 모델 응답 길이 오류')
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out: raise ValueError('중복 모델 JSON 필드')
            out[key]=value
        return out
    try:
        obj=json.loads(raw.strip(),object_pairs_hook=unique,
                       parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    except (TypeError,ValueError) as exc:
        raise ValueError('총괄 손익 비교 JSON 출력 형식 오류') from exc
    if type(obj) is not dict or set(obj)!={'evaluation_id','rationale','risk','unknowns'}:
        raise ValueError('총괄 손익 비교 JSON 필드 오류')
    selected=obj['evaluation_id']
    if selected is not None and (type(selected) is not int or selected not in ids):
        raise ValueError('실제 총괄이 보고서에 없는 평가를 선택했습니다.')
    for name,maxlen in [('rationale',500),('risk',400),('unknowns',400)]:
        if type(obj[name]) is not str or not 1<=len(obj[name].strip())<=maxlen:
            raise ValueError('총괄 모델 '+name+' 출력 길이 오류')
        obj[name]=obj[name].strip()
    return obj


def analyze(store, brief_id: int, *, cancel: threading.Event|None=None) -> dict:
    store.require_permission('company:manage')
    store.require_permission('agents:manage')
    if type(brief_id) is not int or brief_id<=0:
        raise ValueError('실제 총괄 AI 검토 보고 번호 오류')
    with store._connect() as con:
        initialize(con)
        con.execute('BEGIN IMMEDIATE')
        if stopped(con): raise PermissionError('비상정지 중 GGUF 손익 판단 금지')
        brief=get_brief(con,brief_id)
        if brief['review_status']!='pending':
            raise PermissionError('이미 소유자가 검토한 보고서는 모델 재호출 금지')
        rows=brief['snapshot']['items']
        ids={int(row['evaluation_id']) for row in rows}
        lines='\n'.join(
            f"평가 #{int(r['evaluation_id'])} 기간 {int(r['months'])}개월 "
            f"하방 가정 순액 {int(r['downside_assumed_krw'])}원 "
            f"기준 가정 순액 {int(r['base_assumed_krw'])}원 "
            f"상방 가정 순액 {int(r['upside_assumed_krw'])}원"
            for r in rows)
        prompt=(
            '당신은 실제 로컬 총괄 GGUF 모델입니다. 다음 손익 숫자는 전부 '
            '관리자의 미검증 사업 가정이며 실제 매출/수요가 아닙니다. '
            '사업 실행·자금 사용·외부 게시·고객 접촉 금지. '
            '평가 하나를 가설적으로 선택하거나 판단이 불가능하면 null을 선택하십시오. '
            'JSON 객체 하나만 출력: '
            '{"evaluation_id":null,"rationale":"판단 근거","risk":"하방 위험",'
            '"unknowns":"검증되지 않은 항목"}. '
            'evaluation_id는 아래 평가 번호 중에서만 고르십시오.\n'
            '--- 미검증 입력 가정 ---\n'+lines+'\n--- 입력 끝 ---')
        if len(prompt)>3000: raise ValueError('총괄 GGUF 입력 3000자 한도 초과')
        snapshot_hash=hashlib.sha256(
            json.dumps(brief['snapshot'],ensure_ascii=False,sort_keys=True,
                       separators=(',',':')).encode('utf8')).hexdigest()
        claim=int(con.execute("""INSERT INTO aiwack_real_chief_brief_claims
            (brief_id,snapshot_sha256,prompt_sha256) VALUES(?,?,?)""",
            (brief_id,snapshot_hash,hashlib.sha256(prompt.encode('utf8')).hexdigest())).lastrowid)
    call_id=None;raw=None;digest=None
    try:
        if cancel is not None and cancel.is_set():
            raise InterruptedError('관리자가 모델 시작 전에 취소')
        from desktop.chief_runtime import invoke_chief_model
        raw,call_id=invoke_chief_model(store,prompt,timeout=120,cancel=cancel,
                                       include_call_id=True)
        digest=hashlib.sha256(raw.encode('utf8')).hexdigest()
        if cancel is not None and cancel.is_set(): raise InterruptedError('취소 후 결과 폐기')
        result=_parse(raw,ids)
        with store._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if stopped(con) or (cancel is not None and cancel.is_set()):
                raise InterruptedError('비상정지 또는 취소로 결과 저장 금지')
            con.execute("""INSERT INTO aiwack_real_chief_brief_outcomes
                (claim_id,state,model_call_id,output_sha256,evaluation_id,
                 rationale,risk,unknowns)
                VALUES(?,'success',?,?,?,?,?,?)""",
                (claim,call_id,digest,result['evaluation_id'],
                 result['rationale'],result['risk'],result['unknowns']))
        return {'brief_id':brief_id,'claim_id':claim,'model_call_id':call_id,
                'output_sha256':digest,**result,'verified_revenue':False,
                'owner_approval_required':True,'business_launched':False,
                'financial_action_executed':False}
    except Exception as exc:
        state=('cancelled' if isinstance(exc,InterruptedError)
               else 'invalid_output' if isinstance(exc,ValueError) and raw is not None
               else 'failed')
        try:
            with store._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                if not con.execute("SELECT 1 FROM aiwack_real_chief_brief_outcomes WHERE claim_id=?",
                                   (claim,)).fetchone():
                    con.execute("""INSERT INTO aiwack_real_chief_brief_outcomes
                        (claim_id,state,model_call_id,output_sha256,error_kind)
                        VALUES(?,?,?,?,?)""",
                        (claim,state,call_id,digest,type(exc).__name__[:70]))
        except (sqlite3.Error,OSError):
            pass
        raise


def history(store, *, limit: int=50) -> list[dict]:
    store.require_permission('company:manage')
    if type(limit) is not int or not 1<=limit<=200:
        raise ValueError('실제 총괄 사업 비교 감사 조회 1~200건')
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT c.brief_id,c.snapshot_sha256,c.prompt_sha256,
            COALESCE(o.state,'unfinished'),o.model_call_id,o.output_sha256,
            o.evaluation_id,o.rationale,o.risk,o.unknowns,o.error_kind
            FROM aiwack_real_chief_brief_claims c
            LEFT JOIN aiwack_real_chief_brief_outcomes o ON o.claim_id=c.id
            ORDER BY c.id DESC LIMIT ?""",(limit,)).fetchall()
    labels=('brief_id','snapshot_sha256','prompt_sha256','state','model_call_id',
            'output_sha256','evaluation_id','rationale','risk','unknowns','error_kind')
    return [dict(zip(labels,row)) for row in rows]
