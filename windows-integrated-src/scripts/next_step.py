"""Validate stage tracking and report the next exact step."""
import json
import csv
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def load():
    p=json.loads((ROOT/'docs/progress.json').read_text(encoding='utf-8'))
    with (ROOT/'docs/roadmap_100.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    done=[int(r['step']) for r in rows if r['status']=='DONE']
    assert len(rows)==100
    assert done==p['completed_steps']
    blocked={b['step'] for b in p.get('blocked_steps',[])}
    assert not (blocked & set(done))
    assert all(rows[s-1]['status']=='BLOCKED' for s in blocked)
    assert p['next_step']==next((n for n in range(1,101) if n not in set(done)|blocked),101)
    return p,rows
if __name__=='__main__':
    p,rows=load();n=p['next_step']
    print(f"Completed: {len(p['completed_steps'])}/100; Blocked: {[b['step'] for b in p.get('blocked_steps',[])]}")
    print(f"Next: {n}/100 — {rows[n-1]['name']}" if n<=100 else 'All 100 stages complete')
