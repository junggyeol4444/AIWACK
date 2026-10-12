"""Validate stage tracking and report the next exact step."""
import json
import csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load():
    p=json.loads((ROOT/"docs/progress.json").read_text(encoding="utf-8"))
    with (ROOT/"docs/roadmap_100.csv").open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    done=[int(r["step"]) for r in rows if r["status"]=="DONE"]
    assert len(rows)==100
    assert done==p["completed_steps"]==list(range(1,len(done)+1))
    assert p["next_step"]==len(done)+1
    return p,rows
if __name__=="__main__":
    p,rows=load()
    n=p["next_step"]
    print(f"Completed: {len(p['completed_steps'])}/100")
    print(f"Next: {n}/100 — {rows[n-1]['name']}" if n<=100 else "All 100 stages complete")
