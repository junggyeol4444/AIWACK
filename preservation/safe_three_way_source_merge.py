"""AIWACK 역사 원본 ZIP A / 누적 ZIP B / 현재 소스 3방향 보존형 병합.

이 파일은 개발용 Windows 로컬 EXE 소스 통합 도구이다. GUI 실행·실 GGUF
통합검증/오류 수정이 아니다. Python 표준 라이브러리만 사용한다.

입력: 과거 원본 소스 ZIP A, 누적 개발 ZIP B, 현재 소스 체크아웃 root.
출력: 원본 체크아웃 *외부*의 새로운 stage 경로에만 후보/충돌/manifest.
main 또는 사용자 DB의 원본을 절대 직접 수정하지 않는다.
입력이 동일한 부분의 소스 병합 후보는 만들고, 겹치는 변경/바이너리/
미확인 충돌은 원문 3개를 모두 저장해 수동 판단 대상으로 남긴다.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

MAX_ITEM=8*1024*1024
TEXT_SUFFIXES={
    ".py",".md",".txt",".json",".yaml",".yml",".toml",".ini",
    ".cfg",".bat",".ps1",".sh",".csv",".html",".xml",".js",
    ".css",".patch",".properties",".gradle",".gitignore",
}
PRIVATE_NAMES={"dev_company.sqlite3"}
BINARY_EXTENSIONS={".sqlite3",".db",".pem",".key",".p12",".pfx",".crt"}


def _sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"))


def _safe_path(name):
    if not isinstance(name,str) or not name or "\\" in name or "\x00" in name:
        raise ValueError("ZIP 파일 경로 문자 오류")
    pure=PurePosixPath(name)
    if (pure.is_absolute() or any(x in ("",".","..") for x in name.split("/"))
            or re.match(r"^[A-Za-z]:",name)):
        raise ValueError("ZIP 절대 경로/상위 경로 차단: "+name[:80])
    return pure


def _skip(path):
    return (path.name.casefold() in PRIVATE_NAMES
            or path.suffix.casefold() in BINARY_EXTENSIONS
            or ".git" in path.parts)


def _manifest_zip(z:zipfile.ZipFile):
    result={}
    casefold={}
    for item in z.infolist():
        if item.is_dir():
            continue
        path=_safe_path(item.filename)
        key=path.as_posix()
        win=key.casefold()
        if key in result or (win in casefold and casefold[win]!=key):
            raise ValueError("ZIP 경로 중복/Windows 대소문자 충돌: "+key)
        casefold[win]=key
        mode=item.external_attr>>16
        if stat.S_IFMT(mode)==stat.S_IFLNK:
            raise ValueError("ZIP 심볼릭 링크/외부 링크 차단: "+key)
        if item.file_size>MAX_ITEM:
            raise ValueError("ZIP 한 파일 8MiB 초과: "+key)
        result[key]=item
    return result


def _read(z,item):
    with z.open(item,"r") as stream:
        data=stream.read(MAX_ITEM+1)
    if len(data)>MAX_ITEM:
        raise ValueError("ZIP 압축 해제 용량 제한")
    return data


def _read_current(root,path):
    target=root.joinpath(*PurePosixPath(path).parts)
    if target.is_symlink():
        raise ValueError("현재 소스 심볼릭 링크: "+path)
    if not target.exists():
        return None
    if not target.is_file():
        raise ValueError("현재 소스는 일반 파일만 병합 가능합니다: "+path)
    for part in target.relative_to(root).parents:
        if part==Path("."):
            break
    if target.stat().st_size>MAX_ITEM:
        raise ValueError("현재 소스 8MiB 초과: "+path)
    return target.read_bytes()


def _edits(base,variant):
    matcher=difflib.SequenceMatcher(None,base,variant,autojunk=False)
    return [(a,b,variant[c:d]) for op,a,b,c,d in matcher.get_opcodes()
            if op!="equal"]


def _conflict(a,b):
    x,y,_=a
    u,v,_=b
    if x==y and u==v:
        return x==u
    if x==y:
        return u<=x<=v
    if u==v:
        return x<=u<=y
    return x<v and u<y


def three_way(base:bytes,later:bytes,current:bytes)->bytes|None:
    """Merge only changes in disjoint base line ranges, otherwise abstain."""
    if later==current:
        return later
    if current==base:
        return later
    if later==base:
        return current
    if any(b"\x00" in value for value in (base,later,current)):
        return None
    old=base.splitlines(keepends=True)
    left=later.splitlines(keepends=True)
    right=current.splitlines(keepends=True)
    edits_left=_edits(old,left)
    edits_right=_edits(old,right)
    for a in edits_left:
        for b in edits_right:
            if _conflict(a,b):
                return None
    new=list(old)
    for a,b,part in sorted(edits_left+edits_right,key=lambda v:v[0],reverse=True):
        new[a:b]=part
    result=b"".join(new)
    return result if len(result)<=MAX_ITEM else None


def _output(stage,rel,raw):
    path=stage.joinpath(*PurePosixPath(rel).parts)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or path.exists():
        raise FileExistsError("과거 소스 후보 파일을 덮어쓸 수 없습니다: "+str(path))
    with path.open("xb") as f:
        f.write(raw)


def prepare(original:Path,later:Path,checkout:Path,stage:Path):
    original,later,checkout,stage=(
        original.resolve(),later.resolve(),checkout.resolve(),stage.resolve())
    if not checkout.is_dir():
        raise ValueError("현재 main 체크아웃 폴더가 없습니다.")
    if stage.exists():
        raise FileExistsError("새로운 출력 폴더만 허용: "+str(stage))
    if stage==checkout or checkout in stage.parents or stage in checkout.parents:
        raise PermissionError("현재 원본 소스 또는 상위 경로 안에 병합 파일 생성 금지")
    if not original.is_file() or not later.is_file():
        raise ValueError("원본 A / 누적 B ZIP 파일이 필요합니다.")
    records=[]
    with zipfile.ZipFile(original) as a,zipfile.ZipFile(later) as b:
        aa=_manifest_zip(a)
        bb=_manifest_zip(b)
        for name in sorted(set(aa)|set(bb)):
            p=_safe_path(name)
            if _skip(p):
                records.append({"path":name,"state":"skipped_private_or_db"})
                continue
            base=_read(a,aa[name]) if name in aa else None
            latest=_read(b,bb[name]) if name in bb else None
            present=_read_current(checkout,name)
            entry={"path":name,"original_sha256":_sha(base) if base is not None else None,
                   "later_sha256":_sha(latest) if latest is not None else None,
                   "main_sha256":_sha(present) if present is not None else None}
            state="unchanged"
            candidate=None
            if latest is None:
                state="original_only_preserved_in_manifest"
            elif present==latest:
                state="already_integrated"
            elif base is None:
                if present is None:
                    state="missing_historical_file_stage"
                    candidate=latest
                else:
                    state="later_added_but_main_has_different_file"
            elif base==latest:
                state="original_unchanged_current_preserved"
            elif present==base or present is None:
                if present is None:
                    state="source_absent_in_main_stage_modified_candidate"
                else:
                    state="original_main_unchanged_stage_later"
                candidate=latest
            elif (present is not None
                    and p.suffix.casefold() in TEXT_SUFFIXES):
                merged=three_way(base,latest,present)
                if merged is None:
                    state="overlapping_changes_manual_merge"
                elif merged==present:
                    state="later_changes_already_in_main_by_content"
                else:
                    state="nonoverlap_three_way_candidate"
                    candidate=merged
            else:
                state="binary_or_unknown_manual_merge"
            entry["state"]=state
            if candidate is not None:
                destination="staged/"+name
                _output(stage,destination,candidate)
                entry["candidate_path"]=destination
                entry["candidate_sha256"]=_sha(candidate)
            elif state.endswith("manual_merge") or state=="later_added_but_main_has_different_file":
                for label,blob in (("base",base),("later",latest),("main",present)):
                    if blob is None:
                        continue
                    dest="conflicts/"+name+"."+label
                    _output(stage,dest,blob)
                    entry[label+"_preservation_path"]=dest
            records.append(entry)
    totals={}
    for item in records:
        s=item["state"]
        totals[s]=totals.get(s,0)+1
    report={
        "format":"AIWACK_preservation_three_way_candidate_v1",
        "inputs":{"original_zip_sha256":_sha(original.read_bytes()),
                  "cumulative_zip_sha256":_sha(later.read_bytes())},
        "counts":totals,
        "main_never_modified":True,
        "customer_database_not_copied":True,
        "conflicts_not_silently_overwritten":True,
        "all_candidate_files_require_explicit_owner_review_before_main":True,
        "files":records}
    _output(stage,"MANIFEST.json",(_canonical(report)+"\n").encode("utf-8"))
    return {"stage":str(stage),"file_count":len(records),
            "counts":totals,"manifest_sha256":_sha(_canonical(report).encode("utf-8")),
            "source_changed":False,"whole_project_merged":False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original",required=True,type=Path)
    parser.add_argument("--cumulative",required=True,type=Path)
    parser.add_argument("--main-checkout",required=True,type=Path)
    parser.add_argument("--stage",required=True,type=Path)
    args=parser.parse_args(argv)
    summary=prepare(args.original,args.cumulative,args.main_checkout,args.stage)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    sys.exit(main())
