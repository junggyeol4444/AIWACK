"""실제 직원 GGUF의 관리자 최종 승인 결과로 원본 그대로 제작하는 로컬 코드/문서.

새 AI 답변을 위조하지 않고 기존 직원 실제 실행→직원 결과물 소유자
승인→실제 총괄 GGUF 회수 보고서 소유자 수락을 모두 검사한다.
Python 파일은 문법을 검사하되 실행/설치/배포하거나 품질 합격을 주장하지 않는다.
고객 전송·결제·계정 접속을 하지 않는다.
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path
from uuid import uuid4

from desktop.stage87_90_management import stopped

MAX_BYTES = 32768
FILE_TYPES = {"python": ".py", "markdown": ".md", "text": ".txt"}


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_approved_real_work_products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        artifact_id INTEGER NOT NULL,
        employee_call_id INTEGER NOT NULL,
        chief_report_id INTEGER NOT NULL,
        chief_call_id INTEGER NOT NULL,
        format TEXT NOT NULL CHECK(format IN ('python','markdown','text')),
        artifact_sha256 TEXT NOT NULL CHECK(length(artifact_sha256)=64),
        file_sha256 TEXT NOT NULL CHECK(length(file_sha256)=64),
        filename TEXT NOT NULL UNIQUE,
        byte_count INTEGER NOT NULL CHECK(byte_count BETWEEN 1 AND 32768),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(artifact_id,format))""")
    for kind in ("UPDATE","DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_work_product_immutable_%s
            BEFORE %s ON aiwack_approved_real_work_products
            BEGIN SELECT RAISE(ABORT,'승인된 실제 모델 제작 상품 원본 변경 금지'); END"""
            % (kind.lower(),kind))


def _id(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(name + " 번호는 양의 정수여야 합니다.")
    return value


def _evidence(con, artifact_id):
    row=con.execute("""SELECT a.body,a.sha256,a.review_status,
        r.status,r.employee_id,r.model_call_id,
        h.status,h.employee_id,h.output_chars,
        p.id,p.sha256,p.owner_decision,p.chief_model_call_id,
        hc.status,hc.employee_id,hc.output_chars,p.chief_employee_id
        FROM company_task_artifacts a
        JOIN company_task_runs r ON r.id=a.run_id AND r.task_id=a.task_id
        JOIN ai_model_call_history h ON h.id=r.model_call_id
        JOIN company_chief_task_reports p ON p.artifact_id=a.id
        JOIN ai_model_call_history hc ON hc.id=p.chief_model_call_id
        WHERE a.id=?""",(artifact_id,)).fetchone()
    if not row:
        raise ValueError("실제 직원/총괄 GGUF 호출을 증명하는 기존 결과물이 필요합니다.")
    (body,source_sha,artifact_review,run_state,worker,worker_call,
     worker_status,actual_worker,worker_chars,report_id,report_sha,
     report_review,chief_call,chief_status,chief_employee,chief_chars,
     report_chief)=row
    if (artifact_review!="approved" or report_review!="accepted" or
        run_state!="success" or worker_status!="success" or
        chief_status!="success" or worker!=actual_worker or
        chief_employee!=report_chief or int(worker_chars)<1 or int(chief_chars)<1):
        raise PermissionError("실제 직원·총괄 모델 성공 및 관리자 양쪽 최종 승인이 필요합니다.")
    if not isinstance(body,str) or not body or hashlib.sha256(
            body.encode("utf-8")).hexdigest()!=source_sha:
        raise ValueError("직원 원본 파일 SHA256 불일치")
    if not re.fullmatch("[a-f0-9]{64}", str(report_sha)):
        raise ValueError("실제 총괄 보고서 SHA256 형식 오류")
    chief=con.execute("SELECT body FROM company_chief_task_reports WHERE id=?",
                      (report_id,)).fetchone()
    if not chief or hashlib.sha256(chief[0].encode("utf-8")).hexdigest()!=report_sha:
        raise ValueError("총괄 검토 결과물 SHA256 오류")
    return {"body":body,"artifact_sha256":source_sha,
            "worker_call_id":int(worker_call),"chief_report_id":int(report_id),
            "chief_call_id":int(chief_call)}


def _payload(proof,kind):
    raw=proof["body"].encode("utf-8")
    if not 1<=len(raw)<=MAX_BYTES:
        raise ValueError("실제 제품 파일은 1~32768바이트만 지원합니다.")
    if "\x00" in proof["body"]:
        raise ValueError("바이너리/널 문자를 포함한 원본 파일은 지원하지 않습니다.")
    if kind=="python":
        # This checks syntax only, not execution safety or package quality.
        ast.parse(proof["body"],filename="<승인된 실제 AI 코드>")
    return raw


def folder(store):
    return Path(store.path).resolve().parent / "aiwack_owner_approved_products"


def export(store,artifact_id,kind,note):
    """관리자 직접 요청만 로컬 .py/.md/.txt 실제 제품 파일 생성."""
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    _id(artifact_id,"직원 결과물")
    if kind not in FILE_TYPES:
        raise ValueError("실제 제작 유형은 python / markdown / text입니다.")
    if type(note) is not str or not 5<=len(note.strip())<=200:
        raise ValueError("관리자 파일 제작 사유는 5~200자여야 합니다.")
    directory=folder(store)
    if directory.is_symlink():
        raise ValueError("승인 제품 폴더 심볼릭 링크 금지")
    filename="real_ai_product_"+uuid4().hex+FILE_TYPES[kind]
    path=directory/filename
    wrote=False
    committed=False
    try:
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            initialize(con)
            if stopped(con):
                raise PermissionError("비상정지 중 실제 제품 파일 제작 금지")
            if con.execute("""SELECT 1 FROM aiwack_approved_real_work_products
                WHERE artifact_id=? AND format=?""",(artifact_id,kind)).fetchone():
                raise ValueError("동일 모델 결과물/제품 유형의 기존 원본을 덮어쓸 수 없습니다.")
            proof=_evidence(con,artifact_id)
            raw=_payload(proof,kind)
            directory.mkdir(parents=True,exist_ok=True)
            if directory.is_symlink():
                raise ValueError("승인 제품 경로 심볼릭 링크 금지")
            with path.open("xb") as f:
                wrote=True
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            digest=hashlib.sha256(raw).hexdigest()
            export_id=int(con.execute("""INSERT INTO aiwack_approved_real_work_products(
                artifact_id,employee_call_id,chief_report_id,chief_call_id,
                format,artifact_sha256,file_sha256,filename,byte_count,owner_note)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (artifact_id,proof["worker_call_id"],proof["chief_report_id"],
                 proof["chief_call_id"],kind,proof["artifact_sha256"],digest,
                 filename,len(raw),note.strip())).lastrowid)
        committed=True
        return read(store,export_id)
    except BaseException:
        if wrote and not committed:
            path.unlink(missing_ok=True)
        raise


def read(store,product_id):
    store.require_permission("company:manage")
    _id(product_id,"실제 AI 제작물")
    with store._connect() as con:
        initialize(con)
        row=con.execute("""SELECT artifact_id,employee_call_id,chief_report_id,
            chief_call_id,format,artifact_sha256,file_sha256,filename,byte_count,
            created_at FROM aiwack_approved_real_work_products WHERE id=?""",
            (product_id,)).fetchone()
        if row is None:raise ValueError("원본 제품 파일 기록이 없습니다.")
        aid,worker_call,chief_report,chief_call,kind,source_sha,file_sha,name,size,created=row
        proof=_evidence(con,int(aid))
        if (source_sha!=proof["artifact_sha256"] or
            worker_call!=proof["worker_call_id"] or
            chief_report!=proof["chief_report_id"] or
            chief_call!=proof["chief_call_id"]):
            raise ValueError("파일/직원/총괄 승인 원본이 변경됐습니다.")
        expected=_payload(proof,kind)
    suffix=FILE_TYPES[kind]
    if not re.fullmatch(r"real_ai_product_[a-f0-9]{32}"+re.escape(suffix),name):
        raise ValueError("승인된 제품 경로 이름 무결성 오류")
    target=folder(store)/name
    if folder(store).is_symlink() or target.is_symlink() or not target.is_file():
        raise ValueError("실제 AI 제품 파일 누락/심볼릭 링크")
    actual=target.read_bytes()
    if (actual!=expected or len(actual)!=size or
        hashlib.sha256(actual).hexdigest()!=file_sha):
        raise ValueError("로컬 실제 제품 파일 원본 SHA256 훼손")
    return {"id":product_id,"artifact_id":int(aid),"format":kind,
            "filename":str(target),"byte_count":int(size),"sha256":file_sha,
            "created_at":created,"employee_model_call_id":int(worker_call),
            "chief_model_call_id":int(chief_call),
            "manager_accepted":True,"customer_delivered":False,
            "published":False,"code_executed":False,"code_runtime_quality_verified":False,
            "real_revenue_confirmed":False}


def history(store,limit=30):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("실제 제품 파일 이력 1~100건")
    with store._connect() as con:
        initialize(con)
        ids=[int(row[0]) for row in con.execute("""SELECT id FROM
            aiwack_approved_real_work_products ORDER BY id DESC LIMIT ?""",
            (limit,)).fetchall()]
    return [read(store,item) for item in ids]
