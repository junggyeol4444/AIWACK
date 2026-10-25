"""AIWACK 과거 누적 원본 ZIP과 최신 보존 ZIP의 바이트 단위 전수 대조.

ZIP을 풀거나 원본을 수정하지 않는다. GitHub 원격 브랜치 자체의 대조와
동일하다고 주장하지 않는다. 안전하지 않은 경로·중복·ZIP 폭탄은 거부한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

if __package__:
    from validation.windows_path_policy import collision_key, unsafe_part
else:
    from windows_path_policy import collision_key, unsafe_part

MAX_FILES = 20000
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 300


def _read_archive(path: Path) -> dict[str, str]:
    """SHA256 each safe regular ZIP member without extracting anything."""
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise ValueError('원본 ZIP은 기존 일반 파일이어야 합니다.')
    result: dict[str, str] = {}
    folded: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES:
            raise ValueError('ZIP 원본 파일 개수 제한 초과')
        total = 0
        for info in members:
            if info.is_dir():
                continue
            raw = info.filename
            canonical = PurePosixPath(raw).as_posix()
            if (not raw or raw != canonical or '\\' in raw or '\x00' in raw
                    or PurePosixPath(raw).is_absolute()
                    or any(unsafe_part(part) for part in PurePosixPath(raw).parts)):
                raise ValueError('ZIP 원본 경로가 Windows에서 안전하지 않습니다.')
            if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                raise ValueError('ZIP 원본에 심볼릭 링크가 포함돼 있습니다.')
            key = collision_key(raw)
            if raw in result or (key in folded and folded[key] != raw):
                raise ValueError('ZIP 원본에 중복·Windows 경로 충돌이 있습니다.')
            folded[key] = raw
            if info.file_size < 0 or info.file_size > MAX_FILE_BYTES:
                raise ValueError('ZIP 원본 단일 파일 크기 제한 초과')
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError('ZIP 원본 전체 압축 해제 크기 제한 초과')
            if info.file_size and (
                info.compress_size <= 0
                or info.file_size > MAX_COMPRESSION_RATIO * info.compress_size):
                raise ValueError('ZIP 원본 압축 비율 제한 초과')
            digest = hashlib.sha256()
            with archive.open(info) as stream:
                actual = 0
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    actual += len(chunk)
                    if actual > info.file_size:
                        raise ValueError('ZIP 원본 선언 크기보다 큰 내용')
                    digest.update(chunk)
                if actual != info.file_size:
                    raise ValueError('ZIP 원본 선언 크기와 실제 내용이 다릅니다.')
            result[raw] = digest.hexdigest()
    return result


def audit_archives(original: Path, cumulative: Path, *,
                   history: Path | None = None) -> dict:
    """Read-only original vs cumulative ZIP comparison, including history."""
    a = _read_archive(original)
    b = _read_archive(cumulative)
    unchanged = [name for name in sorted(a) if name in b and a[name] == b[name]]
    modified = [{'path':name,'original_sha256':a[name],
                 'cumulative_sha256':b[name]}
                for name in sorted(a) if name in b and a[name] != b[name]]
    missing = [{'path':name,'original_sha256':a[name]}
               for name in sorted(a) if name not in b]
    added = [{'path':name,'cumulative_sha256':b[name]}
             for name in sorted(b) if name not in a]
    result = {
        'original_archive':Path(original).name,
        'cumulative_archive':Path(cumulative).name,
        'original_files':len(a),
        'cumulative_files':len(b),
        'identical_files':len(unchanged),
        'modified_files':modified,
        'missing_files':missing,
        'added_files':added,
        'original_fully_preserved_byte_identical':not (modified or missing),
        'archive_members_extracted':False,
        'original_files_modified':False,
        'remote_github_branch_verified':False,
    }
    if history is not None:
        h = _read_archive(history)
        result['history'] = {
            'archive':Path(history).name,
            'source_files':len(h),
            'identical_files':sum(b.get(name)==digest for name,digest in h.items()),
            'modified_files':[name for name,digest in sorted(h.items())
                              if name in b and b[name]!=digest],
            'missing_files':[name for name in sorted(h) if name not in b],
            'github_individual_restore_verified':False,
        }
    return result


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='AIWACK ZIP 원본 보존형 SHA256 전수 대조')
    parser.add_argument('original',type=Path)
    parser.add_argument('cumulative',type=Path)
    parser.add_argument('--history',type=Path)
    args=parser.parse_args(argv)
    report=audit_archives(args.original,args.cumulative,history=args.history)
    print(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2))
    return 0 if report['original_fully_preserved_byte_identical'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
