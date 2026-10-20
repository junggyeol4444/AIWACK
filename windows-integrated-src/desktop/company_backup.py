"""Owner-triggered, lossless SQLite online snapshots and verified restore copies.

Never overwrites the live application database or restores in a running EXE.
All actions stay in the owner's local AIWACK data directory.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from desktop.storage import user_data_dir


def _folder(root: Path | None = None) -> Path:
    base=(Path(root) if root is not None else user_data_dir()).expanduser().resolve()
    target=base/'verified_backups'
    if target.is_symlink():
        raise PermissionError('백업 폴더 심볼릭 링크는 허용하지 않습니다.')
    target.mkdir(parents=True,exist_ok=True)
    return target


def _digest(path: Path) -> str:
    sha=hashlib.sha256()
    with path.open('rb') as fp:
        for chunk in iter(lambda: fp.read(1024*1024),b''):
            sha.update(chunk)
    return sha.hexdigest()


def _validate_db(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError('백업 파일이 없거나 외부 링크입니다.')
    # Read only: validation must not create a blank database on missing files.
    con=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)
    try:
        if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('SQLite 무결성 검사가 실패했습니다.')
        if con.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('SQLite 외래 키 무결성 검사가 실패했습니다.')
    finally:
        con.close()


def create_snapshot(store, *, root: Path | None = None) -> dict:
    """Capture a consistent live SQLite backup while the EXE can remain open."""
    store.require_permission('company:manage')
    folder=_folder(root)
    token=uuid4().hex
    filename='aiwack_backup_'+token+'.sqlite3'
    temp=folder/('.'+filename+'.partial')
    target=folder/filename
    manifest=folder/(filename+'.json')
    source=None
    destination=None
    try:
        source=sqlite3.connect(str(store.path),timeout=20)
        destination=sqlite3.connect(str(temp),timeout=20)
        source.backup(destination,pages=64,sleep=0.03)
        destination.close()
        destination=None
        source.close()
        source=None
        _validate_db(temp)
        digest=_digest(temp)
        os.replace(temp,target)
        metadata={'file_name':filename,'sha256':digest,'bytes':target.stat().st_size,
                  'sqlite_integrity':'ok','live_database_overwritten':False}
        # Manifest is written last, so incomplete snapshots are not advertised.
        with manifest.open('x',encoding='utf-8') as out:
            json.dump(metadata,out,ensure_ascii=False,indent=2)
            out.flush()
            os.fsync(out.fileno())
        return {'path':str(target),'manifest':str(manifest),**metadata}
    finally:
        if destination is not None:destination.close()
        if source is not None:source.close()
        temp.unlink(missing_ok=True)


def verify_snapshot(store, snapshot_file: Path, *, root: Path | None = None) -> dict:
    store.require_permission('company:manage')
    folder=_folder(root)
    path=Path(snapshot_file)
    # No path escape, custom paths or symlinks.
    if path.parent.resolve()!=folder or path.is_symlink() or not path.name.startswith('aiwack_backup_'):
        raise PermissionError('AIWACK 전용 백업 폴더의 실제 파일만 확인할 수 있습니다.')
    manifest=Path(str(path)+'.json')
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError('백업 감사 메타데이터가 없습니다.')
    info=json.loads(manifest.read_text(encoding='utf-8'))
    if info.get('file_name')!=path.name or _digest(path)!=info.get('sha256'):
        raise RuntimeError('백업 파일의 SHA256이 원본 감사 기록과 다릅니다.')
    _validate_db(path)
    return {'path':str(path),'sha256':info['sha256'],'verified':True}


def restore_into_new_copy(store, snapshot_file: Path, *, root: Path | None = None) -> dict:
    """Prepare a separately verified database COPY; never swap the active DB."""
    store.require_permission('company:manage')
    verified=verify_snapshot(store,snapshot_file,root=root)
    folder=_folder(root)
    path=folder/('aiwack_restore_candidate_'+uuid4().hex+'.sqlite3')
    src=None
    dest=None
    try:
        src=sqlite3.connect(Path(snapshot_file).as_uri()+'?mode=ro',uri=True)
        dest=sqlite3.connect(str(path))
        src.backup(dest,pages=64,sleep=0.03)
        dest.close()
        dest=None
        src.close()
        src=None
        _validate_db(path)
        if _digest(path)!=verified['sha256']:
            raise RuntimeError('복원된 DB 복사본의 SHA256이 원본과 다릅니다.')
        return {'restored_copy':str(path),'live_database_untouched':True,
                'sha256':verified['sha256']}
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        if dest is not None:dest.close()
        if src is not None:src.close()
