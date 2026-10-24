"""기존 AIWACK 1~21회차 중첩 ZIP 원문을 읽기 전용으로 전수 열거한다.

각 내부 ZIP·원본 파일의 실제 SHA256을 별도 보존한다. 동일 이름의 여러
역사 버전을 임의 선택하거나 현재 소스를 수정하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

try:
    from validation.windows_path_policy import collision_key, unsafe_part
except ImportError:
    from windows_path_policy import collision_key, unsafe_part

MAX_ROOT_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 50000
MAX_DEPTH = 8


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _valid_member(info: zipfile.ZipInfo, aliases: set[str]) -> None:
    name = info.filename
    path = PurePosixPath(name)
    if (not name or name != path.as_posix() or path.is_absolute()
            or "\\" in name or any(unsafe_part(part) for part in path.parts)):
        raise ValueError("안전하지 않은 원본 경로: " + repr(name))
    key = collision_key(name)
    if key in aliases:
        raise ValueError("동일 ZIP 내부 Windows 경로 중복: " + repr(name))
    aliases.add(key)
    mode = (info.external_attr >> 16) & 0o170000
    if mode not in (0, stat.S_IFREG):
        raise ValueError("ZIP 링크·특수 파일: " + repr(name))
    if info.flag_bits & 1:
        raise ValueError("암호화된 원본 ZIP: " + repr(name))
    if info.file_size > MAX_MEMBER_BYTES:
        raise ValueError("원본 ZIP 단일 파일 크기 초과: " + repr(name))


def inventory_nested_zip(archive_path: Path, *, max_depth: int = MAX_DEPTH) -> dict:
    """원본 ZIP의 중첩 파일과 바이트 해시를 반환하며 어떤 파일도 쓰지 않는다."""
    archive_path = Path(archive_path)
    if not (1 <= max_depth <= MAX_DEPTH):
        raise ValueError("ZIP 깊이 제한 오류")
    if not archive_path.is_file() or archive_path.stat().st_size > MAX_ROOT_BYTES:
        raise ValueError("원본 ZIP 파일이 없거나 허용 크기를 초과했습니다.")
    raw = archive_path.read_bytes()
    state = {"total_bytes": 0, "members": 0, "archives": [], "files": []}

    def walk(data: bytes, chain: tuple[str, ...], depth: int) -> None:
        if depth > max_depth:
            raise ValueError("중첩 ZIP 깊이 제한 초과")
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise ValueError("원본 ZIP 형식 오류: " + " !/ ".join(chain))
        state["archives"].append({"chain": list(chain), "sha256": _digest(data),
                                  "bytes": len(data)})
        with zipfile.ZipFile(io.BytesIO(data)) as source:
            aliases: set[str] = set()
            for info in source.infolist():
                if info.is_dir():
                    continue
                _valid_member(info, aliases)
                state["members"] += 1
                state["total_bytes"] += info.file_size
                if (state["members"] > MAX_MEMBERS
                        or state["total_bytes"] > MAX_TOTAL_BYTES):
                    raise ValueError("중첩 ZIP 전체 항목·용량 제한 초과")
                with source.open(info) as stream:
                    payload = stream.read(MAX_MEMBER_BYTES + 1)
                if len(payload) != info.file_size:
                    raise ValueError("원본 ZIP 크기·CRC 불일치: " + info.filename)
                if info.filename.lower().endswith(".zip"):
                    if depth >= max_depth:
                        raise ValueError("중첩 ZIP 깊이 제한 초과: " + info.filename)
                    walk(payload, chain + (info.filename,), depth + 1)
                else:
                    state["files"].append({
                        "archive_chain": list(chain), "path": info.filename,
                        "sha256": _digest(payload), "bytes": len(payload)})
    walk(raw, (archive_path.name,), 1)
    versions: dict[str, set[str]] = {}
    for row in state["files"]:
        versions.setdefault(row["path"], set()).add(row["sha256"])
    return {
        "root_archive": archive_path.name, "root_sha256": _digest(raw),
        "archive_count": len(state["archives"]), "leaf_file_count": len(state["files"]),
        "unique_leaf_paths": len(versions),
        "multi_version_paths": sorted(k for k, v in versions.items() if len(v) > 1),
        "total_uncompressed_bytes_checked": state["total_bytes"],
        "archives": state["archives"], "files": state["files"],
        "read_only": True, "original_versions_auto_selected": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AIWACK 중첩 ZIP 원본 SHA256 읽기 전용 감사")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        result = inventory_nested_zip(args.archive)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        print(json.dumps({"verified": False, "error": str(exc)}, ensure_ascii=False))
        return 3
    body = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(body, encoding="utf-8")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
