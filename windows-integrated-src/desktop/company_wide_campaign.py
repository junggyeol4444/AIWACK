"""기존 15부서·31 AI: 실제 총괄 모델 5회 초안 → 관리자가 승인한 30개 직원 업무.

각 부서장/담당 직원의 실제 모델은 기존 승인 업무 실행 경로로 실행된다.
수기 승인·총괄 검수·의존성·비상정지·권한은 우회하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from desktop.company_operations import BLUEPRINT_DEPARTMENTS, assert_running_allowed
from desktop.employee_model_runtime import invoke_employee_model
from desktop.stage87_90_management import stopped


def initialize(con):
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_wide_campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_task_id INTEGER NOT NULL REFERENCES company_tasks(id),
        source_fingerprint TEXT NOT NULL,
        chief_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','approved','rejected')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        approved_at TEXT)''')
    con.execute('''CREATE UNIQUE INDEX IF NOT EXISTS aiwack_wide_active_source
        ON aiwack_wide_campaigns(source_task_id) WHERE state IN ('draft','approved')''')
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_wide_campaign_steps (
        campaign_id INTEGER NOT NULL REFERENCES aiwack_wide_campaigns(id),
        ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 30),
        department_id INTEGER NOT NULL REFERENCES company_departments(id),
        employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        role TEXT NOT NULL CHECK(role IN ('department_head','staff')),
        title TEXT NOT NULL, instruction TEXT NOT NULL,
        chief_model_call_id INTEGER NOT NULL REFERENCES ai_model_call_history(id),
        task_id INTEGER UNIQUE REFERENCES company_tasks(id),
        PRIMARY KEY(campaign_id,ordinal),
        UNIQUE(campaign_id,employee_id))''')
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_wide_chief_rejected_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_task_id INTEGER NOT NULL REFERENCES company_tasks(id),
        chief_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        model_call_id INTEGER NOT NULL UNIQUE REFERENCES ai_model_call_history(id),
        attempt_kind TEXT NOT NULL CHECK(attempt_kind IN ('three_departments','single_department')),
        requested_departments TEXT NOT NULL,
        output_sha256 TEXT NOT NULL CHECK(length(output_sha256)=64),
        output_chars INTEGER NOT NULL CHECK(output_chars>=0),
        error_reason TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for action in ('UPDATE','DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_wide_chief_rejected_no_{action.lower()}
            BEFORE {action} ON aiwack_wide_chief_rejected_attempts
            BEGIN SELECT RAISE(ABORT,'실제 총괄 모델 실패 감사 변경·삭제 금지'); END''')
    for action in ('UPDATE','DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_wide_campaign_step_no_{action.lower()}
            BEFORE {action} ON aiwack_wide_campaign_steps
            WHEN {"OLD.task_id IS NOT NULL" if action == 'UPDATE' else '1'}
            BEGIN SELECT RAISE(ABORT,'승인 후 회사 전체 협업 증빙을 수정·삭제할 수 없습니다'); END''')

    # Genuine chief output for each three-department batch survives a crash.
    con.execute('''CREATE TABLE IF NOT EXISTS aiwack_wide_chief_group_staging (
        source_task_id INTEGER NOT NULL REFERENCES company_tasks(id),
        group_start INTEGER NOT NULL CHECK(group_start IN (0,3,6,9,12)),
        source_fingerprint TEXT NOT NULL,
        roster_sha256 TEXT NOT NULL,
        chief_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id),
        chief_model_id INTEGER NOT NULL,
        group_json TEXT NOT NULL,
        group_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(source_task_id,group_start))''')
    for action in ('UPDATE','DELETE'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS aiwack_wide_staging_no_{action.lower()}
            BEFORE {action} ON aiwack_wide_chief_group_staging
            BEGIN SELECT RAISE(ABORT,'실제 모델 계획 단계별 감사 변경·삭제 금지'); END''')
    cols={row[1] for row in con.execute('PRAGMA table_info(aiwack_wide_campaign_steps)')}
    if 'plan_sha256' not in cols:
        con.execute("ALTER TABLE aiwack_wide_campaign_steps ADD COLUMN plan_sha256 TEXT NOT NULL DEFAULT ''")
    con.execute('''CREATE TRIGGER IF NOT EXISTS aiwack_wide_draft_step_no_edit
        BEFORE UPDATE ON aiwack_wide_campaign_steps WHEN OLD.task_id IS NULL AND (
         NEW.campaign_id!=OLD.campaign_id OR NEW.ordinal!=OLD.ordinal OR
         NEW.department_id!=OLD.department_id OR NEW.employee_id!=OLD.employee_id OR
         NEW.role!=OLD.role OR NEW.title!=OLD.title OR
         NEW.instruction!=OLD.instruction OR NEW.chief_model_call_id!=OLD.chief_model_call_id OR
         NEW.plan_sha256!=OLD.plan_sha256)
        BEGIN SELECT RAISE(ABORT,'승인 전 실제 총괄 계획 수정 금지'); END''')


def _record_genuine_chief_plan_rejection(store, source_task_id, chief, call_id,
                                         attempt_kind, requested, raw, error):
    """Persist actual-model format failures locally; never turn them into tasks.

    Audit metadata only, without exposing private raw prompts/completions in CI.
    An invalid/missing model call cannot be registered as genuine provenance.
    """
    completion=raw if isinstance(raw,str) else repr(raw)
    with store._connect() as con:
        initialize(con)
        call=con.execute('''SELECT employee_id,status FROM ai_model_call_history
                            WHERE id=?''',(int(call_id),)).fetchone()
        if call!=(chief,'success'):
            raise ValueError('총괄 모델 실패 감사의 호출 출처가 불일치합니다.')
        con.execute('''INSERT INTO aiwack_wide_chief_rejected_attempts
            (source_task_id,chief_employee_id,model_call_id,attempt_kind,
             requested_departments,output_sha256,output_chars,error_reason)
             VALUES(?,?,?,?,?,?,?,?)''',(
            source_task_id,chief,int(call_id),attempt_kind,
            json.dumps(list(requested),ensure_ascii=False,separators=(',',':')),
            hashlib.sha256(completion.encode('utf-8')).hexdigest(),
            len(completion),str(error)[:250]))



def _step_digest(campaign_id,ordinal,dept,employee,role,title,instruction,call_id):
    canonical=json.dumps([campaign_id,ordinal,dept,employee,role,title,instruction,call_id],
                         ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _roster_sha256(chief,model,groups):
    canonical=json.dumps([chief,model,groups],ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _verified_staged_group(con,source_task_id,start,fingerprint,roster_sha,
                           chief,model,part):
    row=con.execute('''SELECT source_fingerprint,roster_sha256,chief_employee_id,
        chief_model_id,group_json,group_sha256 FROM aiwack_wide_chief_group_staging
        WHERE source_task_id=? AND group_start=?''',(source_task_id,start)).fetchone()
    if row is None:return None
    if tuple(row[:4])!=(fingerprint,roster_sha,chief,model):
        raise ValueError('기존 단계별 총괄 계획의 업무·조직·모델 변경')
    if hashlib.sha256(row[4].encode('utf-8')).hexdigest()!=row[5]:
        raise ValueError('기존 단계별 총괄 계획 SHA256 손상')
    try:
        entries=json.loads(row[4])
    except (TypeError,ValueError) as error:
        raise ValueError('기존 단계별 총괄 계획 JSON 손상') from error
    if not isinstance(entries,list) or len(entries)!=len(part):
        raise ValueError('기존 단계별 총괄 계획 부서 수 손상')
    parsed={};calls={}
    for item,(dept,name,manager,staff) in zip(entries,part):
        if (not isinstance(item,dict) or item.get('department_id')!=dept
              or item.get('department')!=name or item.get('manager')!=manager
              or item.get('staff')!=staff):
            raise ValueError('기존 단계별 총괄 계획 구성원 불일치')
        title=item.get('title');instruction=item.get('instruction');call_id=item.get('chief_call_id')
        if (not isinstance(title,str) or not isinstance(instruction,str)
              or type(call_id) is not int or call_id<=0
              or not 1<=len(title.strip())<=65 or not 1<=len(instruction.strip())<=330
              or title!=title.strip() or instruction!=instruction.strip()):
            raise ValueError('기존 단계별 실제 총괄 생성 텍스트 손상')
        audited=con.execute('''SELECT employee_id,model_id,status,output_chars
            FROM ai_model_call_history WHERE id=?''',(call_id,)).fetchone()
        if (audited is None or int(audited[0])!=chief or int(audited[1])!=model
              or audited[2]!='success' or int(audited[3])<=0):
            raise ValueError('총괄 GGUF 실제 호출 기록이 단계별 감사와 불일치')
        if con.execute('SELECT 1 FROM aiwack_wide_chief_rejected_attempts WHERE model_call_id=?',
                       (call_id,)).fetchone():
            raise ValueError('실패한 총괄 호출을 계획에 재사용할 수 없습니다.')
        parsed[name]=(title,instruction);calls[name]=call_id
    return parsed,calls


def _save_staged_group(store,source_id,start,fingerprint,roster_sha,chief,
                       model,groups,part,parsed,calls):
    entries=[dict(department_id=dept,department=name,manager=manager,staff=staff,
                  title=parsed[name][0],instruction=parsed[name][1],chief_call_id=calls[name])
             for dept,name,manager,staff in part]
    serialized=json.dumps(entries,ensure_ascii=False,separators=(',',':'))
    digest=hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE');initialize(con)
        if stopped(con):raise PermissionError('비상 정지 상태에서는 계획 저장 금지')
        fp,_=_source(store,con,source_id)
        current,model_id,members=_staff_roster(con)
        if (fp!=fingerprint or current!=chief or model_id!=model
              or members!=groups or _roster_sha256(current,model_id,members)!=roster_sha):
            raise ValueError('총괄 계획 실행 중 원본 업무 또는 모델·조직 변경')
        if con.execute('''SELECT 1 FROM aiwack_wide_campaigns WHERE source_task_id=?
            AND state IN ('draft','approved')''',(source_id,)).fetchone():
            raise ValueError('다른 창에 이미 승인 대기 또는 승인된 계획 존재')
        if _verified_staged_group(con,source_id,start,fingerprint,roster_sha,
                                   chief,model,part) is not None:
            raise ValueError('동시 실행이 이미 해당 부서 계획을 저장했습니다.')
        con.execute('''INSERT INTO aiwack_wide_chief_group_staging
            (source_task_id,group_start,source_fingerprint,roster_sha256,
             chief_employee_id,chief_model_id,group_json,group_sha256)
            VALUES(?,?,?,?,?,?,?,?)''',
            (source_id,start,fingerprint,roster_sha,chief,model,serialized,digest))
        _verified_staged_group(con,source_id,start,fingerprint,roster_sha,chief,model,part)


def staged_plan_progress(store,source_task_id:int)->dict:
    store.require_permission('company:manage')
    with store._connect() as con:
        initialize(con);fingerprint,_=_source(store,con,source_task_id)
        chief,model,groups=_staff_roster(con)
        roster_sha=_roster_sha256(chief,model,groups)
        complete=[start//3+1 for start in range(0,15,3)
            if _verified_staged_group(con,source_task_id,start,fingerprint,roster_sha,
                                      chief,model,groups[start:start+3]) is not None]
    return {'completed_groups':len(complete),'total_groups':5,
            'completed_group_numbers':complete,'requires_owner_approval':True}


def _assert_campaign_plan_matches_genuine_staging(store,con,campaign_id:int)->None:
    plan=con.execute('''SELECT source_task_id,source_fingerprint,chief_employee_id,state
        FROM aiwack_wide_campaigns WHERE id=?''',(campaign_id,)).fetchone()
    if plan is None:raise ValueError('캠페인 원본이 없습니다.')
    fp,_=_source(store,con,plan[0]);chief,model,groups=_staff_roster(con)
    if fp!=plan[1] or chief!=plan[2]:
        raise ValueError('총괄 모델 계획의 기준 업무 또는 총괄 변경')
    roster_sha=_roster_sha256(chief,model,groups)
    rows=con.execute('''SELECT ordinal,department_id,employee_id,role,title,instruction,
        chief_model_call_id,plan_sha256 FROM aiwack_wide_campaign_steps
        WHERE campaign_id=? ORDER BY ordinal''',(campaign_id,)).fetchall()
    if len(rows)!=30:raise ValueError('30단계 계획 원본이 부족합니다.')
    expected=[]
    for start in range(0,15,3):
        part=groups[start:start+3]
        staged=_verified_staged_group(con,plan[0],start,fp,roster_sha,chief,model,part)
        if staged is None:raise ValueError('원본 단계별 총괄 모델 감사 누락')
        parsed,calls=staged
        for dept,name,manager,staff in part:
            title,instruction=parsed[name];cid=calls[name]
            expected.extend(((dept,manager,'department_head',f'{name} 부서장 검토: {title}',
                             ('부서장 분석·계획: '+instruction)[:500],cid),
                             (dept,staff,'staff',f'{name} 담당 실행: {title}',
                             ('부서장 승인된 선행 업무를 확인하고 실제 결과물을 작성: '+instruction)[:500],cid)))
    for row,exp in zip(rows,expected):
        ordinal,*fields=row
        if tuple(fields[:-1])!=exp or fields[-1]!=_step_digest(campaign_id,ordinal,*exp):
            raise ValueError('30업무 본문·모델 호출과 총괄 원본 감사가 일치하지 않습니다.')

def _source(store, con, source_task_id):
    row=store._task_row(con,source_task_id)
    if row[4]!='todo':
        raise ValueError('할 일 상태 기준 업무만 회사 전체 협업으로 확장할 수 있습니다.')
    return store._chief_task_fingerprint(str(row[2]),str(row[3])),row


def _staff_roster(con):
    chief=con.execute('''SELECT e.id,m.model_id FROM ai_reporting_lines r
       JOIN ai_employee_profiles e ON e.id=r.employee_id
       LEFT JOIN ai_employee_model_assignments m ON m.employee_id=e.id
       WHERE r.tier='ceo' AND e.lifecycle='draft' ''').fetchall()
    if len(chief)!=1 or chief[0][1] is None:
        raise ValueError('실제 로컬 모델이 연결된 활성 총괄 AI 한 명이 필요합니다.')
    groups=[]; used={int(chief[0][0])}
    for name,_ in BLUEPRINT_DEPARTMENTS:
        dept=con.execute('SELECT id FROM company_departments WHERE name=?',(name,)).fetchone()
        if not dept:
            raise ValueError('원본 15개 부서 중 누락된 부서: '+name)
        rows=con.execute('''SELECT e.id,r.tier FROM ai_reporting_lines r
            JOIN ai_employee_profiles e ON e.id=r.employee_id
            JOIN ai_employee_model_assignments m ON m.employee_id=e.id
            WHERE e.department_id=? AND e.lifecycle='draft'
                AND r.tier IN ('department_head','staff') ORDER BY r.tier''',(dept[0],)).fetchall()
        if len(rows)!=2 or {r[1] for r in rows}!={'department_head','staff'}:
            raise ValueError('해당 부서의 부서장·직원 각각 한 명과 실제 로컬 모델 배정 필요: '+name)
        members={role:int(employee) for employee,role in rows}
        if any(e in used for e in members.values()):
            raise ValueError('같은 직원이 서로 다른 부서에 중복 지정됐습니다.')
        used.update(members.values())
        groups.append((int(dept[0]),name,members['department_head'],members['staff']))
    if len(used)!=31:
        raise ValueError('총괄 1명과 15개 부서별 부서장·직원 총 31명 필요')
    return int(chief[0][0]),int(chief[0][1]),groups


def _parse_group(raw, expected):
    """Parse only model-generated complete department plans, without synthetic rows."""
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 20000:
        raise ValueError('총괄 모델의 실제 작업 제안이 비어 있거나 너무 깁니다.')
    mapping = {name: (dept, manager, worker)
               for dept, name, manager, worker in expected}
    plans = {}

    def add(name, title, instruction):
        if not all(isinstance(x, str) for x in (name, title, instruction)):
            raise ValueError('총괄 계획의 부서·제목·지시는 문자열이어야 합니다.')
        name = name.strip()
        title = title.strip()
        instruction = instruction.strip()
        if name not in mapping:
            raise ValueError('총괄 계획에 요청하지 않은 부서가 포함됐습니다.')
        if (not 1 <= len(title) <= 65 or not 1 <= len(instruction) <= 330
                or any(ord(c) < 32 for c in title + instruction)):
            raise ValueError('총괄의 부서 지시 길이·내용 오류')
        if name in plans:
            raise ValueError('총괄의 동일 부서 계획이 중복됐습니다.')
        plans[name] = (title, instruction)

    raw = re.sub(r'\x1b\[[0-9;]*m', '', raw).replace('\r', '')
    lines = []
    for line in raw.splitlines():
        line = line.strip().strip('\x00').strip()
        if not line or line.startswith(('~~~', chr(96) * 3, '<|', 'llama_', 'ggml_', '[stats]')):
            continue
        if line.startswith(('main:', 'sampling:', 'system_info:', 'print_info:')):
            continue
        if re.match(r'^(?:total time|eval time|prompt eval time)\s*:', line, re.I):
            continue
        if line.startswith(('TASK:', 'RESPONSE:')):
            line = line.split(':', 1)[1].strip()
        if line:
            lines.append(line)
    json_indices = [i for i, line in enumerate(lines)
                    if line.lstrip().startswith(('{', '['))]
    if json_indices:
        data = None
        for start in json_indices[:2]:
            portion = '\n'.join(lines[start:]).strip()
            try:
                parsed, end = json.JSONDecoder().raw_decode(portion)
            except ValueError:
                continue
            if portion[end:].strip():
                continue
            data = parsed
            break
        if data is None:
            raise ValueError('총괄 JSON 계획이 손상되거나 다른 출력과 섞였습니다.')
        if isinstance(data, dict):
            data = data.get('departments', data.get('부서별계획',
                   data.get('plans', data.get('tasks', data))))
            if isinstance(data, dict):
                rows = []
                for name, fields in data.items():
                    if not isinstance(fields, dict):
                        raise ValueError('총괄 JSON 부서별 구조 오류')
                    if 'department' in fields and fields['department'] != name:
                        raise ValueError('총괄 JSON 부서명 불일치')
                    rows.append({**fields, 'department': name})
                data = rows
        if not isinstance(data, list):
            raise ValueError('총괄 JSON 계획의 목록 구조 오류')
        for row in data:
            if not isinstance(row, dict):
                raise ValueError('총괄 JSON 계획의 항목 구조 오류')
            add(row.get('department', row.get('부서명')),
                row.get('title', row.get('업무 제목', row.get('제목'))),
                row.get('instruction', row.get('작업 지시', row.get('지시'))))
    else:
        for line in lines:
            line = re.sub(r'^\s*(?:[-*]\s+|\d+[.)]\s+)', '', line)
            parts = [x.strip() for x in
                     line.strip().strip('|').replace('｜', '|').replace('¦', '|').split('|')]
            if len(parts) != 3:
                continue
            if (parts[0].lower() in ('department', '부서', '부서명')
                    and parts[1].lower() in ('title', '제목', '업무 제목', '작업 제목')):
                continue
            if all(re.fullmatch(r':?-{3,}:?', part) for part in parts):
                continue
            if not all(parts):
                raise ValueError('총괄의 부서별 계획에 빈 필드가 있습니다.')
            add(*parts)
    if set(plans) != set(mapping):
        raise ValueError('총괄이 필수 3개 부서 중 일부를 누락했습니다.')
    return plans



def _parse_single_real_chief(raw, requested, prompt):
    """Extract an actionable department instruction from a REAL chief response."""
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 12000:
        raise ValueError('실제 총괄 단일 부서 출력이 비어 있거나 너무 깁니다.')
    clean = re.sub(r'\x1b\[[0-9;]*m', '', raw).strip()
    if prompt in clean:
        clean = clean.rsplit(prompt, 1)[-1].strip()
    lines = []
    for line in clean.splitlines():
        line = line.strip()
        if not line or line.startswith(('~~~', chr(96)*3, '<|', 'llama_', 'ggml_')):
            continue
        if line.startswith(('main:', 'sampling:', 'system_info:', 'print_info:')):
            continue
        if line.startswith(('RESPONSE:', 'TASK:')):
            line = line.split(':', 1)[1].strip()
        if line:
            lines.append(line)
    if not lines:
        raise ValueError('실제 총괄 단일 부서 출력에 내용이 없습니다.')
    clean = '\n'.join(lines)
    if clean.startswith('{'):
        try:
            item = json.loads(clean)
        except ValueError as exc:
            raise ValueError('실제 총괄 단일 부서 JSON 출력 손상') from exc
        if not isinstance(item, dict) or item.get('department', item.get('부서명')) != requested:
            raise ValueError('실제 총괄 단일 부서 JSON의 부서 불일치')
        title = item.get('title', item.get('제목', item.get('업무 제목')))
        instruction = item.get('instruction', item.get('지시', item.get('작업 지시')))
    else:
        normalized = [re.sub(r'^\s*(?:[-*]\s+|\d+[.)]\s+)', '',
                      line.replace('｜', '|').replace('¦', '|')).strip()
                      for line in lines]
        rows = [line.strip('|').strip() for line in normalized if '|' in line]
        if len(rows) > 1:
            raise ValueError('총괄 단일 부서 계획에 다중 행이 섞였습니다.')
        if rows:
            parts = [x.strip() for x in rows[0].split('|')]
            if len(parts) == 3:
                if parts[0] != requested:
                    raise ValueError('실제 총괄 단일 부서 출력의 부서 불일치')
                title, instruction = parts[1:]
            elif len(parts) == 2:
                if parts[0] in {name for name, _ in BLUEPRINT_DEPARTMENTS}:
                    raise ValueError('다른 부서를 요청한 단일 총괄 출력입니다.')
                title, instruction = parts
            else:
                raise ValueError('실제 총괄 단일 부서의 구분자 형식 오류')
        else:
            instruction = ' '.join(normalized).strip()
            other = [name for name, _ in BLUEPRINT_DEPARTMENTS if name != requested]
            if any(re.match('^' + re.escape(name) + r'\s*[:：\-]', instruction)
                   for name in other):
                raise ValueError('실제 총괄이 다른 부서로 작업을 배정했습니다.')
            title = instruction[:65]
    if not isinstance(title, str) or not isinstance(instruction, str):
        raise ValueError('실제 총괄 단일 부서의 제목과 지시는 문자열이어야 합니다.')
    title, instruction = title.strip(), instruction.strip()
    if (not 1 <= len(title) <= 65 or not 14 <= len(instruction) <= 330
            or any(ord(c) < 32 for c in title + instruction)
            or instruction == prompt or instruction.startswith('당신은 기존 Windows 로컬 회사')):
        raise ValueError('실제 총괄 단일 부서 지시가 부족하거나 원본 프롬프트를 복사했습니다.')
    return title, instruction


def propose(store,source_task_id:int,*,cancel:threading.Event|None=None):
    """Five REAL chief calls; create 30 drafts only after all five succeed."""
    store.require_permission('company:manage');store.require_permission('agents:manage')
    if type(source_task_id) is not int or source_task_id<=0:
        raise ValueError('기준 업무 번호 오류')
    assert_running_allowed(store)
    with store._connect() as con:
        initialize(con)
        fingerprint,task=_source(store,con,source_task_id)
        chief,chief_model,groups=_staff_roster(con)
        if con.execute('''SELECT 1 FROM aiwack_wide_campaigns
            WHERE source_task_id=? AND state IN ('draft','approved')''',(source_task_id,)).fetchone():
            raise ValueError('이미 진행 중인 회사 전체 협업이 있습니다.')
    steps=[]
    roster_sha=_roster_sha256(chief,chief_model,groups)
    for start in range(0,15,3):
        if cancel is not None and cancel.is_set():
            raise InterruptedError('총괄 일괄 협업 초안 취소')
        assert_running_allowed(store)
        part=groups[start:start+3]
        with store._connect() as con:
            initialize(con)
            recovered=_verified_staged_group(con,source_task_id,start,fingerprint,
                                               roster_sha,chief,chief_model,part)
        if recovered is None:
            parsed=None
            calls={}
        else:
            parsed,calls=recovered
        prompt=('당신은 기존 Windows 로컬 회사의 총괄 AI입니다. 실제 작업을 수행할 3개 부서를 위한 '
                '명확한 텍스트 작업 지시를 각 부서별로 한 줄 작성하세요. 입력된 부서 이름을 그대로 사용하고 '
                '부서명|작업 제목|작업 지시 형태의 3줄만 출력하세요. 다른 부서/외부 결제/계약/게시 지시 금지. '
                '관리자 승인 전에는 실행되지 않습니다.\n'
                f'원본 업무: {str(task[2])[:120]} / {str(task[3])[:400]}\n'
                '담당 부서: '+', '.join(name for _,name,_,_ in part))
        # Strictly bounded, auditable real-model retries for invalid output format.
        # Do not synthesize, guess or auto-approve a malformed department plan.
        for attempt in range(3 if recovered is None else 0):
            if cancel is not None and cancel.is_set():
                raise InterruptedError('취소된 총괄 재호출은 실행하지 않습니다.')
            assert_running_allowed(store)
            query=prompt if attempt==0 else prompt.replace(
                '담당 부서: ',
                '이전 출력은 부서별 정확한 형식을 충족하지 못했습니다. '
                '각 부서명|업무 제목|작업 지시 형태로 정확히 세 줄 작성하세요.\n담당 부서: ')
            raw,call_id=invoke_employee_model(store,chief,query,timeout=90,cancel=cancel,
                                              required_tier='ceo',include_call_id=True)
            if cancel is not None and cancel.is_set():
                raise InterruptedError('총괄 모델 호출 후 취소된 초안은 저장하지 않습니다.')
            try:
                parsed=_parse_group(raw,part)
                calls={name:int(call_id) for _,name,_,_ in part}
                break
            except ValueError as exc:
                _record_genuine_chief_plan_rejection(
                    store,source_task_id,chief,call_id,'three_departments',
                    [name for _,name,_,_ in part],raw,exc)
                # These are REAL failed format attempts, not model-free fallback.
                # A small GGUF that cannot emit three rows may emit one real
                # department instruction per separate audited chief invocation.
                continue
        if parsed is None:
            parsed={}
            calls={}
            for dept,name,manager,staff in part:
                one_prompt=('당신은 기존 Windows 로컬 회사의 총괄 AI입니다. '
                            '반드시 해당 부서만 담당하는 실행 가능한 작업을 작성하세요. '
                            '결제·계약·게시·외부 전송은 금지합니다. '
                            '다른 부서 작업을 작성하지 마세요.\n'
                            f'부서: {name}\n원본 업무: {str(task[2])[:120]} / '
                            f'{str(task[3])[:250]}\n'
                            f'출력 형식: {name}|작업 제목|구체적인 실행 지시')
                for solo_attempt in range(3):
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError('단일 부서 총괄 계획 취소')
                    assert_running_allowed(store)
                    answer,solo_call=invoke_employee_model(
                        store,chief,one_prompt,timeout=90,cancel=cancel,
                        required_tier='ceo',include_call_id=True)
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError('취소된 단일 부서 계획은 저장하지 않습니다.')
                    try:
                        parsed[name]=_parse_single_real_chief(answer,name,one_prompt)
                        calls[name]=int(solo_call)
                        break
                    except ValueError as exc:
                        _record_genuine_chief_plan_rejection(
                            store,source_task_id,chief,solo_call,'single_department',
                            [name],answer,exc)
                        continue
                else:
                    raise ValueError('실제 총괄 모델의 3부서 계획이 세 번 연속 실패하고 단일 부서 재시도도 모두 실패했습니다.')
        if recovered is None:
            _save_staged_group(store,source_task_id,start,fingerprint,roster_sha,
                               chief,chief_model,groups,part,parsed,calls)
        for dept,name,manager,staff in part:
            title,instruction=parsed[name]
            call_id=calls[name]
            steps.append((dept,manager,'department_head',f'{name} 부서장 검토: {title}',
                          ('부서장 분석·계획: '+instruction)[:500],int(call_id)))
            steps.append((dept,staff,'staff',f'{name} 담당 실행: {title}',
                          ('부서장 승인된 선행 업무를 확인하고 실제 결과물을 작성: '+instruction)[:500],int(call_id)))
    if cancel is not None and cancel.is_set():raise InterruptedError('취소된 계획 저장 불가')
    store.require_permission('company:manage');store.require_permission('agents:manage')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE');initialize(con)
        if stopped(con):raise PermissionError('비상정지로 회사 전체 협업 초안 거부')
        fp,_=_source(store,con,source_task_id)
        current,model,current_groups=_staff_roster(con)
        if fp!=fingerprint or current!=chief or model!=chief_model or current_groups!=groups:
            raise ValueError('모델 실행 중 회사 조직/기준 업무가 변경됐습니다.')
        if con.execute('''SELECT 1 FROM aiwack_wide_campaigns WHERE source_task_id=?
             AND state IN ('draft','approved')''',(source_task_id,)).fetchone():
            raise ValueError('다른 Windows 창에 이미 승인 대기 계획이 있습니다.')
        for start in range(0,15,3):
            if _verified_staged_group(con,source_task_id,start,fingerprint,roster_sha,
                                      chief,chief_model,groups[start:start+3]) is None:
                raise ValueError('완성 전 단계별 실제 총괄 모델 감사가 누락됐습니다.')
        ids={int(x[0]) for x in con.execute('''SELECT id FROM ai_model_call_history
            WHERE employee_id=? AND model_id=? AND status='success' AND output_chars>0''',
            (chief,chief_model))}
        if not all(call in ids for *_,call in steps):
            raise ValueError('동일 총괄 AI의 성공한 실제 로컬 모델 호출 감사가 필요합니다.')
        cid=int(con.execute('''INSERT INTO aiwack_wide_campaigns
            (source_task_id,source_fingerprint,chief_employee_id) VALUES(?,?,?)''',
            (source_task_id,fingerprint,chief)).lastrowid)
        for ordinal,(dept,employee,role,title,instruction,call) in enumerate(steps,1):
            seal=_step_digest(cid,ordinal,dept,employee,role,title,instruction,call)
            con.execute('''INSERT INTO aiwack_wide_campaign_steps
                (campaign_id,ordinal,department_id,employee_id,role,title,instruction,
                 chief_model_call_id,plan_sha256)
                VALUES(?,?,?,?,?,?,?,?,?)''',
                (cid,ordinal,dept,employee,role,title,instruction,call,seal))
    return read(store,cid)


def read(store,campaign_id:int):
    store.require_permission('company:manage')
    if type(campaign_id) is not int or campaign_id<=0:raise ValueError('회사 전체 협업 번호 오류')
    with store._connect() as con:
        initialize(con)
        row=con.execute('''SELECT id,source_task_id,state,chief_employee_id
            FROM aiwack_wide_campaigns WHERE id=?''',(campaign_id,)).fetchone()
        if not row:raise ValueError('회사 전체 협업 계획 없음')
        steps=con.execute('''SELECT s.ordinal,d.name,s.employee_id,s.role,s.title,s.task_id,
            t.status,s.chief_model_call_id FROM aiwack_wide_campaign_steps s
            JOIN company_departments d ON d.id=s.department_id
            LEFT JOIN company_tasks t ON t.id=s.task_id
            WHERE s.campaign_id=? ORDER BY s.ordinal''',(campaign_id,)).fetchall()
    return {'id':int(row[0]),'source_task_id':int(row[1]),'state':row[2],
            'chief_employee_id':int(row[3]),'distinct_departments':len({s[1] for s in steps}),
            'distinct_worker_roles':len({s[2] for s in steps}),
            'steps':[dict(zip(('ordinal','department','employee_id','role','title','task_id',
                              'task_status','chief_model_call_id'),x)) for x in steps]}


def approve(store,campaign_id:int):
    """Owner-clicked single SQLite transaction creates 30 REAL reviewed-order tasks."""
    store.require_permission('company:manage');store.require_permission('agents:manage')
    if type(campaign_id) is not int or campaign_id<=0:raise ValueError('계획 번호 오류')
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE');initialize(con)
        if stopped(con):raise PermissionError('비상정지로 계획 승인을 차단했습니다.')
        plan=con.execute('''SELECT source_task_id,source_fingerprint,chief_employee_id,state
            FROM aiwack_wide_campaigns WHERE id=?''',(campaign_id,)).fetchone()
        if not plan or plan[3]!='draft':raise ValueError('승인할 수 있는 초안이 없습니다.')
        fingerprint,_=_source(store,con,plan[0]);chief,_,groups=_staff_roster(con)
        if fingerprint!=plan[1] or chief!=plan[2]:raise ValueError('총괄/업무가 변경됐습니다.')
        steps=con.execute('''SELECT ordinal,department_id,employee_id,role,title,instruction,
                   chief_model_call_id,task_id,plan_sha256
            FROM aiwack_wide_campaign_steps WHERE campaign_id=? ORDER BY ordinal''',
            (campaign_id,)).fetchall()
        expected=[(dept,e,role) for dept,name,manager,staff in groups
                  for e,role in ((manager,'department_head'),(staff,'staff'))]
        if len(steps)!=30 or [(s[1],s[2],s[3]) for s in steps]!=expected:
            raise ValueError('15부서 30역할의 실제 계획이 일치하지 않습니다.')
        for ordinal,dept,employee,role,title,instruction,call_id,task_id,seal in steps:
            if (task_id is not None or not seal or seal!=_step_digest(
                    campaign_id,ordinal,dept,employee,role,title,instruction,call_id)):
                raise ValueError('총괄 원본 생성 계획이 변경됐거나 이미 업무가 연결됨')
        _assert_campaign_plan_matches_genuine_staging(store,con,campaign_id)
        prev=None
        for ordinal,dept,employee,role,title,instruction,call_id,task_id,seal in steps:
            description=f'관리자 승인 회사 전체 협업 #{campaign_id} / {ordinal}/30단계\n{instruction}'
            tid=int(con.execute('INSERT INTO company_tasks(title,description) VALUES(?,?)',
                                (title[:120],description[:1500])).lastrowid)
            con.execute('''INSERT INTO company_task_status_events(task_id,old_status,new_status)
                VALUES(?,NULL,'todo')''',(tid,))
            con.execute('INSERT INTO company_task_routing(task_id,department_id) VALUES(?,?)',(tid,dept))
            con.execute('''INSERT INTO company_task_assignments(task_id,employee_id,reason)
                VALUES(?,?,?)''',(tid,employee,'소유자 승인 회사 전체 협업 계획'))
            con.execute('''INSERT INTO company_task_assignment_events
                (task_id,employee_id,action,detail) VALUES(?,?,'auto_assigned',?)''',
                (tid,employee,f'회사 전체 협업 #{campaign_id} 역할 {role}'))
            con.execute('''INSERT INTO company_chief_task_orders
                (task_id,chief_employee_id,worker_employee_id,instruction,task_fingerprint)
                VALUES(?,?,?,?,?)''',(tid,chief,employee,instruction,
                store._chief_task_fingerprint(title[:120],description[:1500])))
            if prev is not None:
                con.execute('''INSERT INTO company_task_dependencies(task_id,prerequisite_id)
                    VALUES(?,?)''',(tid,prev))
                con.execute('''INSERT INTO company_task_dependency_events
                    (task_id,prerequisite_id,action) VALUES(?,?,'added')''',(tid,prev))
            con.execute('''UPDATE aiwack_wide_campaign_steps SET task_id=?
                WHERE campaign_id=? AND ordinal=? AND task_id IS NULL''',(tid,campaign_id,ordinal))
            prev=tid
        changed=con.execute('''UPDATE aiwack_wide_campaigns
            SET state='approved',approved_at=CURRENT_TIMESTAMP WHERE id=? AND state='draft' ''',
            (campaign_id,))
        if changed.rowcount!=1:raise RuntimeError('기존 계획이 변경됐습니다.')
    return read(store,campaign_id)



def assert_handoff_ready(con, task_id: int) -> dict | None:
    """Fail closed on incomplete or tampered real cross-department handoffs."""
    row=con.execute("""SELECT s.campaign_id,s.ordinal
        FROM aiwack_wide_campaign_steps s
        JOIN aiwack_wide_campaigns c ON c.id=s.campaign_id AND c.state='approved'
        WHERE s.task_id=?""",(task_id,)).fetchone()
    if row is None or int(row[1])==1:return None
    previous=con.execute("""SELECT s.task_id,t.status
        FROM aiwack_wide_campaign_steps s JOIN company_tasks t ON t.id=s.task_id
        WHERE s.campaign_id=? AND s.ordinal=?""",(row[0],row[1]-1)).fetchone()
    if not previous or previous[1]!='done':
        raise ValueError('회사 전체 협업의 직전 단계가 관리자 검수로 완료되지 않았습니다.')
    proof=con.execute("""SELECT a.id,a.body,a.sha256,a.review_status,
          r.status,h.status,h.employee_id,r.employee_id,
          rep.owner_decision,rep.body,rep.sha256,
          ord.chief_employee_id,rep.chief_employee_id
        FROM company_task_artifacts a
        JOIN company_task_runs r ON r.id=a.run_id AND r.task_id=a.task_id
        JOIN ai_model_call_history h ON h.id=r.model_call_id AND h.model_id=r.model_id
        JOIN company_chief_task_dispatches disp ON disp.run_id=r.id
        JOIN company_chief_task_orders ord ON ord.id=disp.order_id
        JOIN company_chief_task_reports rep ON rep.artifact_id=a.id AND rep.order_id=ord.id
        WHERE a.task_id=? ORDER BY a.id DESC LIMIT 1""",(previous[0],)).fetchone()
    if (proof is None or proof[3]!='approved' or proof[4]!='success'
          or proof[5]!='success' or int(proof[6])!=int(proof[7])
          or proof[8]!='accepted' or int(proof[11])!=int(proof[12])):
        raise ValueError('직전 부서 결과의 실제 직원/총괄 모델·관리자 승인 증거가 부족합니다.')
    if (hashlib.sha256(str(proof[1]).encode('utf8')).hexdigest()!=proof[2]
          or hashlib.sha256(str(proof[9]).encode('utf8')).hexdigest()!=proof[10]):
        raise ValueError('직전 부서의 승인 결과물 또는 총괄 검토 SHA256 무결성 오류')
    return {'previous_task_id':int(previous[0]),'artifact_id':int(proof[0]),
            'artifact_sha256':str(proof[2]),'chief_report_sha256':str(proof[10])}



def _verified_step_evidence(con, campaign_id: int, ordinal: int, *,
                            expected_chief: int, require_done: bool = True) -> dict | None:
    """Validate exact campaign task, owner review, call and report joins."""
    row=con.execute("""SELECT s.task_id,s.employee_id,t.status,a.id,a.body,a.sha256,
            a.review_status,r.status,h.status,rep.owner_decision,rep.body,rep.sha256,
            r.employee_id,h.employee_id,ord.worker_employee_id,
            ord.chief_employee_id,rep.chief_employee_id,
            disp.order_id,rep.order_id,ord.task_id,r.task_id,a.task_id,
            r.model_id,h.model_id,rep.artifact_id,disp.run_id,r.id,r.output_chars,h.output_chars
        FROM aiwack_wide_campaign_steps s
        JOIN aiwack_wide_campaigns c ON c.id=s.campaign_id AND c.state='approved'
        JOIN company_tasks t ON t.id=s.task_id
        JOIN company_task_artifacts a ON a.task_id=s.task_id
        JOIN company_task_runs r ON r.id=a.run_id AND r.task_id=s.task_id
        JOIN ai_model_call_history h ON h.id=r.model_call_id
        JOIN company_chief_task_dispatches disp ON disp.run_id=r.id
        JOIN company_chief_task_orders ord ON ord.id=disp.order_id
        JOIN company_chief_task_reports rep ON rep.artifact_id=a.id
        WHERE s.campaign_id=? AND s.ordinal=?
        ORDER BY a.id DESC LIMIT 1""",(campaign_id,ordinal)).fetchone()
    if not row:
        return None
    (task,employee,status,aid,body,sha,review,run_status,call_status,decision,
     report_body,report_sha,run_employee,call_employee,order_worker,
     order_chief,report_chief,dispatch_order,report_order,order_task,
     run_task,artifact_task,run_model,call_model,report_artifact,
     dispatch_run,run_id,run_output_chars,call_output_chars)=row
    if not (status==('done' if require_done else 'in_progress')
            and review=='approved' and run_status=='success'
            and call_status=='success' and decision=='accepted'
            and int(employee)==int(run_employee)==int(call_employee)==int(order_worker)
            and int(expected_chief)==int(order_chief)==int(report_chief)
            and int(dispatch_order)==int(report_order)
            and int(task)==int(order_task)==int(run_task)==int(artifact_task)
            and int(run_model)==int(call_model)
            and int(aid)==int(report_artifact)
            and int(dispatch_run)==int(run_id)
            and int(run_output_chars)>0 and int(call_output_chars)>0):
        return None
    if (hashlib.sha256(str(body).encode('utf8')).hexdigest()!=sha
            or hashlib.sha256(str(report_body).encode('utf8')).hexdigest()!=report_sha):
        return None
    return {'previous_task_id':int(task),'artifact_id':int(aid),
            'artifact_sha256':str(sha),'chief_report_sha256':str(report_sha)}


def _verified_chief_model_call_link(con, campaign_id: int, ordinal: int,
                                    *, expected_chief: int) -> bool:
    """Require the report's own real chief model call after worker inference."""
    row=con.execute("""SELECT rep.chief_model_call_id, h.id, h.employee_id,
          h.status,h.output_chars,rep.chief_employee_id,
          r.model_call_id,r.employee_id,r.status,a.review_status,rep.owner_decision,
          t.status,ord.chief_employee_id,rep.order_id,ord.id,
          a.task_id,r.task_id,ord.task_id
       FROM aiwack_wide_campaign_steps s
       JOIN company_tasks t ON t.id=s.task_id
       JOIN company_task_artifacts a ON a.task_id=t.id
       JOIN company_task_runs r ON r.id=a.run_id
       JOIN company_chief_task_reports rep ON rep.artifact_id=a.id
       JOIN company_chief_task_orders ord ON ord.id=rep.order_id
       LEFT JOIN ai_model_call_history h ON h.id=rep.chief_model_call_id
       WHERE s.campaign_id=? AND s.ordinal=?
       ORDER BY a.id DESC LIMIT 1""",(campaign_id,ordinal)).fetchone()
    if row is None:
        return False
    (report_call,call_id,call_employee,call_state,chars,report_chief,
     worker_call,worker_employee,worker_state,review,decision,task_state,
     order_chief,report_order,order_id,artifact_task,run_task,order_task)=row
    if report_call is None or con.execute(
            'SELECT COUNT(*) FROM company_chief_task_reports WHERE chief_model_call_id=?',
            (report_call,)).fetchone()[0]!=1:
        return False
    if any(type(value) is not int or value<=0 for value in
           (report_call,call_id,call_employee,report_chief,order_chief,
            expected_chief,worker_call)):
        return False
    return bool(call_id==report_call
        and call_employee==report_chief==order_chief==expected_chief
        and call_state=='success' and type(chars) is int and chars>0
        and call_id>worker_call
        and worker_state=='success' and review=='approved' and decision=='accepted'
        and task_state=='done' and report_order==order_id
        and artifact_task==run_task==order_task)


def verified_progress(store, campaign_id: int) -> dict:
    """Read-only sequential owner/employee/chief evidence, not binary GGUF proof."""
    plan=read(store,campaign_id)
    verified=[];waiting=[];next_task=None;genuine_chief_links=0;genuine_prefix=0
    with store._connect() as con:
        initialize(con)
        saved=con.execute('''SELECT source_task_id,source_fingerprint,chief_employee_id
            FROM aiwack_wide_campaigns WHERE id=?''',(campaign_id,)).fetchone()
        if saved is None:
            raise ValueError('계획 기록을 찾을 수 없습니다.')
        current_fp,_=_source(store,con,saved[0])
        if saved[1]!=current_fp or saved[2]!=plan['chief_employee_id']:
            raise ValueError('원본 업무·총괄 AI가 계획 승인 이후 변경됐습니다.')
        for row in plan['steps']:
            task=row['task_id']
            if not task:
                waiting.append({'ordinal':row['ordinal'],'state':'awaiting_campaign_approval'})
                continue
            if row['task_status']!='done' and next_task is None:
                next_task=int(task)
            proof=_verified_step_evidence(con,plan['id'],row['ordinal'],
                                          expected_chief=plan['chief_employee_id'])
            if proof is not None and len(verified)==row['ordinal']-1:
                verified.append({'ordinal':row['ordinal'],'employee_id':row['employee_id'],
                                 'department':row['department'],'artifact_id':proof['artifact_id']})
                if _verified_chief_model_call_link(con,plan['id'],row['ordinal'],
                                                   expected_chief=plan['chief_employee_id']):
                    genuine_chief_links+=1
                    if genuine_prefix==row['ordinal']-1:
                        genuine_prefix+=1
            else:
                waiting.append({'ordinal':row['ordinal'],'state':row['task_status'],
                                'owner_artifact_and_chief_review_required':True})
    return {'campaign_id':campaign_id,'state':plan['state'],
            'verified_completed_tasks':len(verified),'total_tasks':30,
            'verified_distinct_workers':len({v['employee_id'] for v in verified}),
            'verified_distinct_departments':len({v['department'] for v in verified}),
            'next_task_id':next_task,'verified_evidence':verified,'pending':waiting,
            'all_30_tasks_evidence_verified':len(verified)==30,
            'verified_chief_model_call_links':genuine_chief_links,
            'verified_genuine_prefix_tasks':genuine_prefix,
            'all_30_chief_model_call_links_verified':genuine_prefix==30,
            'actual_gguf_binary_verified':False,
            'owner_approval_was_required':True,'automatic_approval':False}


def run_next(store,campaign_id:int,*,cancel:threading.Event|None=None,
             require_genuine_provenance:bool=False):
    """Execute next genuine GGUF step only after the previous owner-reviewed step.

    The Windows real-model and owner UI route must require genuine chief
    provenance.  Never mark all 30 complete on status flags alone.
    """
    from desktop.company_operations import execute_approved_chief_cycle
    plan=read(store,campaign_id)
    if plan['state']!='approved':
        raise ValueError('승인된 계획만 실행할 수 있습니다.')
    progress=verified_progress(store,campaign_id)
    pending=[row for row in plan['steps'] if row['task_status']!='done']
    if not pending:
        if not progress['all_30_tasks_evidence_verified']:
            raise ValueError('30개 업무의 실제 직원·총괄·관리자 승인 기록이 부족합니다.')
        if require_genuine_provenance and progress['verified_genuine_prefix_tasks']!=30:
            raise ValueError('30개 업무의 총괄 실제 모델 호출 연결이 불완전합니다.')
        return {'completed':True,'remaining':0}
    step=pending[0]
    if (progress['verified_completed_tasks']!=step['ordinal']-1
            or progress['next_task_id']!=step['task_id']):
        raise ValueError('직전 협업 단계의 실제 증빙·승인·순서가 일치하지 않습니다.')
    if (require_genuine_provenance and
            progress['verified_genuine_prefix_tasks']!=step['ordinal']-1):
        raise ValueError('직전 총괄 실제 모델 호출 연결이 검증되지 않았습니다.')
    result=execute_approved_chief_cycle(store,step['task_id'],cancel=cancel)
    return {'step':step['ordinal'],'department':step['department'],
            'employee_id':step['employee_id'],'work':result,
            'remaining':len(pending),'owner_review_required':True}
