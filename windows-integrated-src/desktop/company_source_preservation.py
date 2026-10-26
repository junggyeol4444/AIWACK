"""Native Windows EXE adapter for the EXISTING historical source 3-way tool.

Uses preservation.safe_three_way_source_merge from the original repo, never
reimplements the 3-way algorithm and never modifies main, user databases or
ZIP inputs. Owner selects A/B ZIP and an existing main checkout; all output
goes to a NEW external stage directory. Candidate != approved merge.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from desktop.stage87_90_management import stopped


def _core():
    # This is bundled from the original preservation/ tool by PyInstaller.
    from preservation import safe_three_way_source_merge as original_tool
    return original_tool


def _paths(original_zip,cumulative_zip,checkout,stage):
    values=(original_zip,cumulative_zip,checkout,stage)
    if any(type(x) is not str or not x.strip() for x in values):
        raise ValueError("원본 ZIP A·누적 ZIP B·현재 main 체크아웃·별도 출력 폴더를 모두 선택하세요")
    a,b,root,out=(Path(v).expanduser().resolve() for v in values)
    if a==b or not a.is_file() or not b.is_file():
        raise ValueError("서로 다른 원본 A와 누적 B ZIP 파일이 필요합니다")
    if a.suffix.lower()!=".zip" or b.suffix.lower()!=".zip":
        raise ValueError("실제 ZIP 파일만 선택하세요")
    if not root.is_dir() or not (root/".git").exists():
        raise ValueError("현재 main Git 체크아웃(.git)이 있는 폴더가 필요합니다")
    if out.exists() or out==root or root in out.parents or out in root.parents:
        raise PermissionError("출력 폴더는 기존 main 체크아웃 외부의 새 폴더여야 합니다")
    if out==a or out==b:
        raise PermissionError("ZIP 입력 경로를 출력으로 사용할 수 없습니다")
    if (a.is_symlink() or b.is_symlink() or root.is_symlink()
            or out.is_symlink()):
        raise PermissionError("ZIP·현재 소스·출력 경로 심볼릭 링크 금지")
    return a,b,root,out


def _sha(path):
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk=stream.read(1024*1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aiwack_source_preservation_runs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      original_zip_sha256 TEXT NOT NULL CHECK(length(original_zip_sha256)=64),
      cumulative_zip_sha256 TEXT NOT NULL CHECK(length(cumulative_zip_sha256)=64),
      checkout_path TEXT NOT NULL,
      stage_path TEXT NOT NULL UNIQUE,
      manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
      original_entry_count INTEGER NOT NULL,
      cumulative_entry_count INTEGER NOT NULL,
      file_count INTEGER NOT NULL,
      states_json TEXT NOT NULL,
      owner_note TEXT NOT NULL CHECK(length(owner_note) BETWEEN 5 AND 200),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    for op in ("UPDATE","DELETE"):
        con.execute("""CREATE TRIGGER IF NOT EXISTS aiwack_preservation_runs_no_%s
            BEFORE %s ON aiwack_source_preservation_runs BEGIN
            SELECT RAISE(ABORT,'역사 ZIP 후보 생성 감사 원본 변경 금지'); END"""%
            (op.lower(),op))


def _zip_counts(a,b):
    core=_core()
    counts=[]
    for path in (a,b):
        with zipfile.ZipFile(path,"r") as archive:
            manifest=core._manifest_zip(archive)
            counts.append(len(manifest))
    return counts


def preview(store,original_zip,cumulative_zip,checkout,stage):
    store.require_permission("company:manage")
    a,b,root,out=_paths(original_zip,cumulative_zip,checkout,stage)
    original_count,cumulative_count=_zip_counts(a,b)
    return {
        "original_zip_sha256":_sha(a),
        "cumulative_zip_sha256":_sha(b),
        "original_entry_count":original_count,
        "cumulative_entry_count":cumulative_count,
        "historical_1099_expected":1099,
        "historical_1171_expected":1171,
        "count_matches_historical_claim":(
            original_count==1099 and cumulative_count==1171),
        "checkout_path":str(root),"stage_path":str(out),
        "candidate_generated":False,"original_zip_untouched":True,
        "main_source_untouched":True,"whole_project_merged":False,
        "sqlite_user_db_untouched":True,
        "needs_owner_review_before_any_main_integration":True
    }


def stage_candidates(store,original_zip,cumulative_zip,checkout,stage,owner_note):
    store.require_permission("company:manage")
    store.require_permission("agents:manage")
    if (type(owner_note) is not str or
        not 5<=len(owner_note.strip())<=200 or
        any(ord(c)<32 or ord(c)==127 for c in owner_note)):
        raise ValueError("관리자 병합 후보 생성 사유는 제어문자 없는 5~200자")
    a,b,root,out=_paths(original_zip,cumulative_zip,checkout,stage)
    original_count,cumulative_count=_zip_counts(a,b)
    before_a=_sha(a)
    before_b=_sha(b)
    with store._connect() as con:
        initialize(con)
        if stopped(con):
            raise PermissionError("비상정지 중 원본 후보 생성 금지")
        if con.execute("""SELECT 1 FROM aiwack_source_preservation_runs
            WHERE stage_path=?""",(str(out),)).fetchone():
            raise ValueError("이 출력 경로로 과거 병합 후보를 이미 생성했습니다")
    # Calls the EXISTING historical preservation tool unchanged.
    # Output only under a new external stage, never inside main.
    result=_core().prepare(a,b,root,out)
    manifest_path=out/"MANIFEST.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("후보 생성 후 매니페스트 누락")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("inputs",{}).get("original_zip_sha256")!=before_a or
        manifest.get("inputs",{}).get("cumulative_zip_sha256")!=before_b or
        _sha(a)!=before_a or _sha(b)!=before_b):
        raise PermissionError("후보 생성 중 원본 ZIP 입력 변경 감지")
    states=manifest.get("counts")
    if not isinstance(states,dict) or result["file_count"]!=len(manifest.get("files",[])):
        raise ValueError("기존 병합 후보 결과의 매니페스트 불일치")
    # Manifest SHA is actual saved file bytes, not a second serialization.
    manifest_sha=_sha(manifest_path)
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        initialize(con)
        if stopped(con):
            raise PermissionError("후보 생성 후 비상정지: 파일은 보존하고 기록은 중단")
        rid=int(con.execute("""INSERT INTO aiwack_source_preservation_runs(
            original_zip_sha256,cumulative_zip_sha256,checkout_path,
            stage_path,manifest_sha256,original_entry_count,
            cumulative_entry_count,file_count,states_json,owner_note)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (before_a,before_b,str(root),str(out),manifest_sha,
             original_count,cumulative_count,result["file_count"],
             json.dumps(states,ensure_ascii=False,sort_keys=True),
             owner_note.strip())).lastrowid)
    return {"run_id":rid,"original_entry_count":original_count,
            "cumulative_entry_count":cumulative_count,
            "manifest_file_sha256":manifest_sha,**result,
            "historical_count_claim_confirmed":(
                original_count==1099 and cumulative_count==1171),
            "candidates_applied_to_main":False,
            "manual_conflicts_resolved":False,
            "whole_project_merged":False}


def history(store,limit=30):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("역사 소스 보존 감사 조회 범위 1~100건")
    with store._connect() as con:
        initialize(con)
        rows=con.execute("""SELECT id,original_zip_sha256,cumulative_zip_sha256,
            checkout_path,stage_path,manifest_sha256,original_entry_count,
            cumulative_entry_count,file_count,states_json,owner_note,created_at
            FROM aiwack_source_preservation_runs
            ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
    fields=("id","original_zip_sha256","cumulative_zip_sha256",
            "checkout_path","stage_path","manifest_sha256","original_entry_count",
            "cumulative_entry_count","file_count","states_json","owner_note",
            "created_at")
    output=[]
    for row in rows:
        item=dict(zip(fields,row))
        item["counts"]=json.loads(item.pop("states_json"))
        item["candidate_only"]=True
        item["main_modified_by_this_operation"]=False
        item["manual_conflicts_resolved"]=False
        output.append(item)
    return output
