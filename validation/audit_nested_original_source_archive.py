"""기존 AIWACK 원본 소스 다중 ZIP과 로컬 테스트 브랜치의 무변경 전수 대조.

사용자가 준비한 로컬 ZIP/작업 디렉터리를 직접 입력한다. 원본·Git 브랜치
수정/삭제/덮어쓰기/네트워크 요청 없음. 비교 결과는 완료/누락/상충 분리.
이 기능의 실행이 Windows EXE 또는 실제 GGUF 검증을 뜻하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath

DEFAULT_PREFIX = "latest_local_v44_source/AIWACK-Stage54/"
MAX_DEPTH = 5
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_ENTRIES = 10000


def _safe_members(z):
    infos = [i for i in z.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        raise ValueError("원본 ZIP 항목 수가 안전 한도를 초과했습니다.")
    if sum(i.file_size for i in infos) > MAX_TOTAL:
        raise ValueError("원본 ZIP 전체 비압축 크기가 안전 한도를 초과했습니다.")
    if any(i.file_size > MAX_FILE for i in infos):
        raise ValueError("단일 원본 ZIP 항목의 크기가 안전 한도를 초과했습니다.")
    return infos


def _open_snapshot_archive(path: Path, prefix: str):
    """Locate an exact prefix in bounded nested ZIPs; reject ambiguous roots."""
    outer = Path(path).read_bytes()
    candidates = [outer]
    seen = set()
    for depth in range(MAX_DEPTH + 1):
        found = []
        next_level = []
        for raw in candidates:
            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            try:
                z = zipfile.ZipFile(io.BytesIO(raw))
            except (zipfile.BadZipFile, ValueError) as exc:
                raise ValueError("원본 ZIP 파일의 압축 구조가 손상됐습니다.") from exc
            with z:
                infos = _safe_members(z)
                if any(i.filename.startswith(prefix) for i in infos):
                    found.append(raw)
                    continue
                if depth < MAX_DEPTH:
                    for item in infos:
                        if item.filename.lower().endswith(".zip"):
                            next_level.append(z.read(item))
        if found:
            if len(found) != 1 or next_level:
                raise ValueError("동일 원본 경로가 복수 ZIP에 존재해 자동 채택을 거부합니다.")
            return found[0], depth
        candidates = next_level
    raise ValueError("지정한 원본 소스 경로를 중첩 ZIP에서 찾을 수 없습니다.")


def _relative_path(member: str, prefix: str) -> Path:
    if not member.startswith(prefix):
        raise ValueError("원본 소스 경로 접두사가 일치하지 않습니다.")
    value = member[len(prefix):]
    parts = value.split("/")
    if (not value or value.startswith("/") or "\\" in value
            or any(p in ("", ".", "..") or ":" in p or "\x00" in p for p in parts)
            or any(re.search(r'[<>|"?*]', p) for p in parts)):
        raise ValueError("원본 ZIP의 비정상 또는 Windows 비호환 경로")
    return Path(*PurePosixPath(value).parts)


def _sha(data: bytes):
    blob = b"blob " + str(len(data)).encode("ascii") + b"\x00" + data
    return hashlib.sha1(blob).hexdigest(), hashlib.sha256(data).hexdigest()


def audit_archive(archive: Path, checkout: Path, *,
                  prefix: str = DEFAULT_PREFIX,
                  expected_count: int | None = None) -> dict:
    """Read-only audit of every historical source entry against existing files."""
    if expected_count is not None and (
            type(expected_count) is not int or expected_count < 1):
        raise ValueError("원본 예상 파일 수는 양의 정수여야 합니다.")
    root = Path(checkout).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("로컬 저장소 경로는 실제 디렉터리여야 합니다.")
    raw, depth = _open_snapshot_archive(Path(archive), prefix)
    records = []
    collisions = set()
    count = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = _safe_members(z)
        for member in infos:
            if not member.filename.startswith(prefix):
                continue
            relative = _relative_path(member.filename, prefix)
            folded = relative.as_posix().casefold()
            if folded in collisions:
                raise ValueError("Windows에서 충돌하는 대소문자 원본 경로가 존재합니다.")
            collisions.add(folded)
            count += 1
            original = z.read(member)
            original_blob, original_sha = _sha(original)
            target = root.joinpath(*relative.parts)
            actual = target.resolve(strict=False)
            if not actual.is_relative_to(root):
                raise ValueError("대조 경로가 작업 디렉터리를 벗어납니다.")
            if target.is_symlink() or (target.exists() and not target.is_file()):
                status = "unsafe_path"
                current_sha = None
            elif not target.exists():
                status = "missing"
                current_sha = None
            else:
                current_sha = hashlib.sha256(target.read_bytes()).hexdigest()
                status = "match" if current_sha == original_sha else "different"
            records.append({
                "path": relative.as_posix(),
                "status": status,
                "original_git_blob_sha1": original_blob,
                "original_sha256": original_sha,
                "current_sha256": current_sha,
            })
    if not count:
        raise ValueError("원본 파일이 없어서 대조를 진행할 수 없습니다.")
    results = {state: sum(x["status"] == state for x in records)
               for state in ("match", "missing", "different", "unsafe_path")}
    return {
        "format": "AIWACK_ARCHIVE_SOURCE_READ_ONLY_AUDIT_V1",
        "archive_path": str(Path(archive).resolve()),
        "nested_zip_depth": depth,
        "original_prefix": prefix,
        "checkout_path": str(root),
        "expected_count": expected_count,
        "selected_original_files": count,
        "expected_count_matches": expected_count is None or count == expected_count,
        "summary": results,
        "all_originals_match": (
            (expected_count is None or count == expected_count)
            and results["match"] == count),
        "files": records,
        "read_only": True,
        "originals_overwritten": False,
        "source_files_modified": False,
        "main_merged": False,
        "windows_exe_tested": False,
        "real_gguf_tested": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="AIWACK 원본 중첩 ZIP 무변경 대조")
    parser.add_argument("original_zip", type=Path)
    parser.add_argument("checkout", type=Path,
                        help="기존 로컬 테스트 브랜치의 windows-integrated-src 경로")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--report-json", type=Path,
                        help="기존 파일을 덮어쓰지 않는 별도 증빙 JSON 경로")
    args = parser.parse_args(argv)
    report = audit_archive(args.original_zip, args.checkout,
                           expected_count=args.expected_count,
                           prefix=args.prefix)
    if args.report_json is not None:
        serialized = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
                      + "\n").encode("utf-8")
        with args.report_json.open("xb") as output:
            output.write(serialized)
            output.flush()
            os.fsync(output.fileno())
    print(json.dumps({key: report[key] for key in (
        "selected_original_files", "expected_count_matches",
        "summary", "all_originals_match", "read_only")},
        ensure_ascii=False, sort_keys=True))
    return 0 if report["all_originals_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
