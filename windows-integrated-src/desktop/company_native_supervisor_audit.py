"""실제 Windows 외부 감시 프로그램 JSONL 감사 읽기 전용 조회.

파일이 없거나 손상되면 그대로 표시하고, 24시간 가동 합격으로 추론하지 않는다.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


def history(store, limit=80):
    store.require_permission("company:manage")
    if type(limit) is not int or not 1<=limit<=300:
        raise ValueError("감시 감사 조회는 1~300건입니다.")
    path = Path(os.environ.get("LOCALAPPDATA") or Path.home())/"AIWACK"/"native_supervisor.jsonl"
    if not path.is_file():
        return {"exists":False,"events":[],"verified_continuous_24h":False,
                "gui_process_alive_now_verified":False,"read_only":True}
    digest = hashlib.sha256()
    tail = b""
    size = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            tail = (tail+chunk)[-1048576:]
    truncated = size > len(tail)
    if truncated:
        tail = tail.split(b"\n",1)[-1]
    raw_lines = tail.splitlines()
    events = []
    invalid = 0
    for line in raw_lines[-limit:]:
        try:
            item = json.loads(line.decode("utf-8"))
            if not isinstance(item,dict) or "kind" not in item or "utc" not in item:
                raise ValueError("감시 JSONL 형식 누락")
            events.append(item)
        except (UnicodeError,ValueError,TypeError):
            invalid += 1
    kinds = {}
    for item in events:
        kind = str(item["kind"])
        kinds[kind] = kinds.get(kind,0)+1
    return {"exists":True,"size_bytes":size,"file_sha256":digest.hexdigest(),
            "events":events,"events_in_page":len(events),
            "invalid_lines_in_page":invalid,"tail_truncated":truncated,
            "event_kind_counts_in_page":kinds,
            "observed_at_utc":datetime.now(timezone.utc).isoformat(),
            "verified_continuous_24h":False,
            "gui_process_alive_now_verified":False,
            "model_or_payment_replayed":False,"read_only":True}
