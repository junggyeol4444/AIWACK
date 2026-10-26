"""Owner-approved local multi-file release from real employee/chief GGUF outputs.

No model execution or fabricated source generation in this module. Each
artifact must already have genuine audited employee and chief model calls,
employee artifact approval, and a separately accepted chief report.

Release files contain the original employee model text bytes, plus a
machine-readable manifest stating exactly what was and was not verified.
No Python execution, installer, publication, customer send, or transaction.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
from uuid import uuid4
import zipfile

from desktop.company_approved_real_products import (
    _evidence, _payload, FILE_TYPES, initialize as initialize_products
)
from desktop.stage87_90_management import stopped

MAX_FILES=20
MAX_ZIP_BYTES=1024*1024
_ENTRY=re.compile(r"([1-9][0-9]{0,17}):(python|markdown|text)\Z")


def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def initialize(con):
    initialize_products(con)
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_actual_model_releases(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL CHECK(length(title) BETWEEN 4 AND 120),
        owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
        filename TEXT NOT NULL UNIQUE,
        bundle_sha256 TEXT NOT NULL CHECK(length(bundle_sha256)=64),
        bundle_bytes INTEGER NOT NULL CHECK(bundle_bytes BETWEEN 1 AND 1048576),
        manifest_json TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_actual_model_release_items(
        release_id INTEGER NOT NULL REFERENCES aiwack_actual_model_releases(id),
        ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 20),
        artifact_id INTEGER NOT NULL REFERENCES company_task_artifacts(id),
        employee_call_id INTEGER NOT NULL REFERENCES ai_model_call_history(id),
        chief_report_id INTEGER NOT NULL REFERENCES company_chief_task_reports(id),
        chief_call_id INTEGER NOT NULL REFERENCES ai_model_call_history(id),
        source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
        kind TEXT NOT NULL CHECK(kind IN ('python','markdown','text')),
        member_name TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK(size_bytes BETWEEN 1 AND 32768),
        PRIMARY KEY(release_id,ordinal),
        UNIQUE(release_id,artifact_id),
        UNIQUE(release_id,member_name))""")
    for table in ("aiwack_actual_model_releases",
                  "aiwack_actual_model_release_items"):
        for op in ("UPDATE","DELETE"):
            con.execute("""CREATE TRIGGER IF NOT EXISTS %s_no_%s
                BEFORE %s ON %s BEGIN
                SELECT RAISE(ABORT,'승인 GGUF 다중 파일 배포 원본 불변'); END"""
                %(table,op.lower(),op,table))


def _parts(spec):
    if type(spec) is not str or not 3<=len(spec)<=600:
        raise ValueError("파일 목록은 업무번호:python 또는 markdown/text 형식입니다.")
    parts=spec.split(",")
    if not 2<=len(parts)<=MAX_FILES:
        raise ValueError("실제 승인 파일 2~20건을 입력하세요.")
    selected=[]
    seen=set()
    for part in parts:
        m=_ENTRY.fullmatch(part.strip())
        if not m:
            raise ValueError("목록 항목은 숫자:python/markdown/text 형식만 가능합니다.")
        aid=int(m.group(1))
        if aid in seen:
            raise ValueError("같은 실제 직원 결과물은 중복 묶음 불가")
        seen.add(aid)
        selected.append((aid,m.group(2)))
    return selected


def _folder(store):
    return Path(store.path).resolve().parent / "aiwack_local_real_model_releases"


def _proofs(con,selected):
    out=[]
    for aid,kind in selected:
        proof=_evidence(con,aid)
        body=_payload(proof,kind)
        member=f"sources/artifact_{aid:018d}{FILE_TYPES[kind]}"
        out.append({"artifact_id":aid,"format":kind,"name":member,
                    "source_sha256":proof["artifact_sha256"],
                    "employee_call_id":proof["worker_call_id"],
                    "chief_report_id":proof["chief_report_id"],
                    "chief_call_id":proof["chief_call_id"],
                    "byte_count":len(body),"sha256":_hash(body),"body":body})
    return out


def _manifest(title,items):
    return {"format_version":1,"title":title,
            "source":"stored_real_employee_model_artifacts",
            "employee_and_chief_call_audited":True,
            "employee_artifacts_owner_approved":True,
            "chief_reports_owner_accepted":True,
            "independent_windows_gguf_soak_verified":False,
            "python_code_executed_or_quality_verified":False,
            "external_published_or_delivered":False,
            "customer_payment_or_revenue_verified":False,
            "items":[{k:v for k,v in p.items() if k!="body"} for p in items]}


def _archive_bytes(manifest,items):
    sink=io.BytesIO()
    with zipfile.ZipFile(sink,"w",compression=zipfile.ZIP_STORED,
                         allowZip64=False) as archive:
        for item in items:
            info=zipfile.ZipInfo(item["name"],date_time=(2020,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_STORED
            info.external_attr=0o100644<<16
            archive.writestr(info,item["body"])
        info=zipfile.ZipInfo("manifest.json",date_time=(2020,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_STORED
        info.external_attr=0o100644<<16
        archive.writestr(info,(_json(manifest)+"\n").encode("utf-8"))
    result=sink.getvalue()
    if not 1<=len(result)<=MAX_ZIP_BYTES:
        raise ValueError("AI 실제 코드·상품 묶음 용량 1MiB 초과")
    return result


def create(store,title,spec,owner_note):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if type(title) is not str or not 4<=len(title.strip())<=120 or "\x00" in title:
        raise ValueError("실제 배포 묶음 제목은 4~120자입니다.")
    if type(owner_note) is not str or not 5<=len(owner_note.strip())<=200:
        raise ValueError("관리자 파일 묶음 생성 사유는 5~200자입니다.")
    selected=_parts(spec)
    target_folder=_folder(store)
    if target_folder.is_symlink():
        raise ValueError("파일 제작 저장소 심볼릭 링크 금지")
    name="approved_real_release_"+uuid4().hex+".zip"
    dest=target_folder/name
    wrote=committed=False
    try:
        with store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            initialize(con)
            if stopped(con):
                raise PermissionError("비상정지 중 실제 GGUF 승인 파일 묶음 생성 금지")
            items=_proofs(con,selected)
            manifest=_manifest(title.strip(),items)
            manifest_json=_json(manifest)
            manifest_sha=_hash(manifest_json.encode("utf-8"))
            raw=_archive_bytes(manifest,items)
            target_folder.mkdir(parents=True,exist_ok=True)
            if target_folder.is_symlink():
                raise ValueError("GGUF 묶음 경로 심볼릭 링크 금지")
            with dest.open("xb") as stream:
                wrote=True
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            rid=int(con.execute("""INSERT INTO aiwack_actual_model_releases(
                title,owner_note,filename,bundle_sha256,bundle_bytes,
                manifest_json,manifest_sha256) VALUES(?,?,?,?,?,?,?)""",
                (title.strip(),owner_note.strip(),name,_hash(raw),
                 len(raw),manifest_json,manifest_sha)).lastrowid)
            for i,p in enumerate(items,1):
                con.execute("""INSERT INTO aiwack_actual_model_release_items(
                    release_id,ordinal,artifact_id,employee_call_id,chief_report_id,
                    chief_call_id,source_sha256,kind,member_name,size_bytes)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (rid,i,p["artifact_id"],p["employee_call_id"],
                     p["chief_report_id"],p["chief_call_id"],p["source_sha256"],
                     p["format"],p["name"],p["byte_count"]))
        committed=True
        return read(store,rid)
    except BaseException:
        if wrote and not committed:
            dest.unlink(missing_ok=True)
        raise


def read(store,release_id):
    store.require_permission("company:manage")
    if type(release_id) is not int or release_id<1:
        raise ValueError("실제 GGUF 코드 패키지 번호 오류")
    with store._connect() as con:
        initialize(con)
        row=con.execute("""SELECT title,filename,bundle_sha256,bundle_bytes,
            manifest_json,manifest_sha256,created_at
            FROM aiwack_actual_model_releases WHERE id=?""",
            (release_id,)).fetchone()
        if not row:
            raise ValueError("실제 GGUF 승인 배포 파일 원본이 없습니다.")
        title,name,sha,size,mtext,msha,created=row
        if _hash(mtext.encode("utf-8"))!=msha:
            raise ValueError("다중 AI 제품 구성 원본 SHA256 불일치")
        manifest=json.loads(mtext)
        rows=con.execute("""SELECT artifact_id,kind,member_name,source_sha256,
            employee_call_id,chief_report_id,chief_call_id,size_bytes FROM
            aiwack_actual_model_release_items WHERE release_id=? ORDER BY ordinal""",
            (release_id,)).fetchall()
        if not 2<=len(rows)<=MAX_FILES:
            raise ValueError("다중 AI 결과물 증빙 2~20개 누락")
        selected=[(int(r[0]),str(r[1])) for r in rows]
        fresh=_proofs(con,selected)
        if manifest!=_manifest(title,fresh):
            raise ValueError("GGUF 다중 파일 원본·모델 감사·관리자 승인 변경")
        for row,p in zip(rows,fresh):
            if (row[2]!=p["name"] or row[3]!=p["source_sha256"] or
                row[4]!=p["employee_call_id"] or
                row[5]!=p["chief_report_id"] or
                row[6]!=p["chief_call_id"] or row[7]!=p["byte_count"]):
                raise ValueError("저장된 GGUF 파일 묶음 원본 근거 변경")
    if not re.fullmatch(r"approved_real_release_[a-f0-9]{32}\.zip",name):
        raise ValueError("기존 GGUF 제품 원본 파일명 무결성 오류")
    directory=_folder(store)
    p=directory/name
    if directory.is_symlink() or p.is_symlink() or not p.is_file():
        raise ValueError("로컬 GGUF 배포 파일이 없거나 심볼릭 링크입니다")
    raw=p.read_bytes()
    if len(raw)!=size or _hash(raw)!=sha or len(raw)>MAX_ZIP_BYTES:
        raise ValueError("실제 GGUF 묶음 ZIP 파일 원본 SHA256 불일치")
    # Byte-verify each original model output and enforce fixed member names.
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names=archive.namelist()
        expected=[item["name"] for item in fresh]+["manifest.json"]
        if names!=expected:
            raise ValueError("GGUF 로컬 ZIP 파일 항목 무단 추가/누락")
        for item in fresh:
            if archive.read(item["name"])!=item["body"]:
                raise ValueError("직원 GGUF 실제 출력 원문 ZIP 내용 손상")
        if archive.read("manifest.json")!=(_json(manifest)+"\n").encode("utf-8"):
            raise ValueError("GGUF 배포 매니페스트 원문 손상")
    return {"id":release_id,"title":title,"path":str(p),"bytes":size,
            "sha256":sha,"created_at":created,"files":len(fresh),
            "source_artifact_ids":[a for a,_ in selected],
            "owner_approved_employee_and_chief_audits":True,
            "code_executed":False,"published_or_customer_delivered":False,
            "external_payments_executed":False,
            "independent_runtime_quality_verified":False}


def history(store,limit=30):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=50:
        raise ValueError("실제 GGUF 다중 파일 배포 목록 1~50건")
    with store._connect() as con:
        initialize(con)
        ids=[int(r[0]) for r in con.execute("""SELECT id FROM
            aiwack_actual_model_releases ORDER BY id DESC LIMIT ?""",
            (limit,)).fetchall()]
    return [read(store,i) for i in ids]
