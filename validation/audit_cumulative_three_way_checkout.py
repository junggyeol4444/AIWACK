"""원본 ZIP · main 작업 사본 · 누적 테스트 작업 사본의 읽기 전용 3자 대조.

두 작업 사본이 실제 원격 GitHub HEAD와 동일하다고 추측하지 않는다.
이 도구는 기존 코드를 병합하거나 수정하지 않고 충돌을 전부 식별한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

from validation.audit_cumulative_archives import (
    MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, _read_archive,
)
from validation.windows_path_policy import collision_key, unsafe_part


def _read_checkout(root: Path) -> dict[str, str]:
    """Walk a user-supplied checkout without following symlinks or mutating it."""
    candidate = Path(root)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("대조할 작업 사본은 기존 일반 디렉터리여야 합니다.")
    root = candidate.resolve(strict=True)
    digests: dict[str, str] = {}
    folded: dict[str, str] = {}
    total = 0
    for directory, directories, files in os.walk(root, topdown=True, followlinks=False):
        parent = Path(directory)
        for name in list(directories):
            entry = parent / name
            if name == ".git" and parent == root:
                directories.remove(name)
                continue
            if entry.is_symlink() or not entry.is_dir():
                raise ValueError("작업 사본에 심볼릭 링크 또는 특수 디렉터리가 있습니다.")
            relative = entry.relative_to(root).parts
            if any(unsafe_part(piece) for piece in relative):
                raise ValueError("작업 사본에 Windows 비호환 디렉터리가 있습니다.")
        for name in files:
            path = parent / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("작업 사본에 심볼릭 링크 또는 특수 파일이 있습니다.")
            relative = path.relative_to(root)
            parts = relative.parts
            if not parts or any(unsafe_part(part) for part in parts):
                raise ValueError("작업 사본에 Windows 비호환 파일명이 있습니다.")
            key = relative.as_posix()
            if key != PurePosixPath(key).as_posix():
                raise ValueError("작업 사본의 상대경로가 정규화되지 않았습니다.")
            windows_key = collision_key(key)
            if key in digests or (windows_key in folded and folded[windows_key] != key):
                raise ValueError("작업 사본의 Windows 파일명 충돌이 발견됐습니다.")
            folded[windows_key] = key
            if len(digests) >= MAX_FILES:
                raise ValueError("작업 사본 파일 개수 제한 초과")
            stat_before = path.stat()
            if not 0 <= stat_before.st_size <= MAX_FILE_BYTES:
                raise ValueError("작업 사본 단일 파일 크기 제한 초과")
            total += stat_before.st_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("작업 사본 파일 누적 크기 제한 초과")
            digest = hashlib.sha256()
            actual = 0
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    actual += len(chunk)
                    if actual > stat_before.st_size:
                        raise ValueError("작업 사본 파일이 읽는 중 변경됐습니다.")
                    digest.update(chunk)
            stat_after = path.stat()
            if (actual != stat_before.st_size
                    or stat_after.st_size != stat_before.st_size
                    or stat_after.st_mtime_ns != stat_before.st_mtime_ns
                    or stat_after.st_ino != stat_before.st_ino):
                raise ValueError("작업 사본 파일이 읽는 중 변경됐습니다.")
            digests[key] = digest.hexdigest()
    return digests


def audit_three_way(original_zip: Path, main_checkout: Path, test_checkout: Path,
                    *, history_zip: Path | None = None) -> dict:
    """Expose every original-file discrepancy; never choose a merge winner."""
    original = _read_archive(original_zip)
    main = _read_checkout(main_checkout)
    test = _read_checkout(test_checkout)
    rows = []
    classifications = {}
    for path in sorted(set(original) | set(main) | set(test)):
        a, m, t = original.get(path), main.get(path), test.get(path)
        if a == m == t:
            category = "identical"
        elif a is not None and (m is None or t is None):
            category = "original_missing_from_checkout"
        elif m == t:
            category = "main_and_test_agree"
        elif a == m:
            category = "test_only_change"
        elif a == t:
            category = "main_change_not_in_test"
        elif a is None and m is None:
            category = "new_test_only"
        elif a is None and t is None:
            category = "new_main_only"
        else:
            category = "three_way_conflict"
        classifications[category] = classifications.get(category, 0) + 1
        if category != "identical":
            rows.append({
                "path": path,
                "original_sha256": a,
                "main_sha256": m,
                "test_sha256": t,
                "classification": category,
            })
    history = None
    if history_zip is not None:
        historic = _read_archive(history_zip)
        history = {
            "archive": Path(history_zip).name,
            "total": len(historic),
            "identical_in_test": sum(test.get(p) == sha for p, sha in historic.items()),
            "missing_from_test": sorted(p for p in historic if p not in test),
            "modified_in_test": sorted(
                p for p, sha in historic.items() if p in test and test[p] != sha),
        }
    return {
        "original_archive": Path(original_zip).name,
        "original_count": len(original),
        "main_checkout_files": len(main),
        "test_checkout_files": len(test),
        "classification_counts": classifications,
        "differences": rows,
        "history": history,
        "read_only": True,
        "source_files_modified": False,
        "github_remote_head_verified": False,
        "integration_tests_executed": False,
        "main_merge_performed": False,
        "blocking_discrepancies": (
            classifications.get("original_missing_from_checkout", 0)
            + classifications.get("main_change_not_in_test", 0)
            + classifications.get("three_way_conflict", 0)
            + (len(history["missing_from_test"]) + len(history["modified_in_test"])
               if history else 0)
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="AIWACK 원본 ZIP/main 사본/테스트 사본 읽기 전용 SHA256 3자 대조")
    parser.add_argument("original", type=Path)
    parser.add_argument("main_checkout", type=Path)
    parser.add_argument("test_checkout", type=Path)
    parser.add_argument("--history", type=Path)
    args = parser.parse_args(argv)
    report = audit_three_way(
        args.original, args.main_checkout, args.test_checkout,
        history_zip=args.history)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if report["blocking_discrepancies"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
