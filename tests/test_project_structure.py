import csv
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_roadmap_is_exactly_100_ordered_steps():
    with (ROOT/"docs/roadmap_100.csv").open(encoding="utf-8-sig", newline="") as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==100
    assert [int(r["step"]) for r in rows]==list(range(1,101))
    assert all(r["status"] in {"DONE","TODO"} for r in rows)
    progress=json.loads((ROOT/"docs/progress.json").read_text(encoding="utf-8"))
    assert [int(r["step"]) for r in rows if r["status"]=="DONE"]==progress["completed_steps"]
    assert progress["next_step"]==len(progress["completed_steps"])+1

def test_original_spec_is_included():
    x=(ROOT/"docs/original_project_spec.txt").read_text(encoding="utf-8")
    assert "AI Autonomous Company" in x
    assert all(f"T{i:02d}" in x for i in range(1,21))

def test_traceability_covers_all_20_original_tests():
    x=(ROOT/"docs/requirements_traceability.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^\| T\d{2} \|", x, flags=re.MULTILINE))==20

def test_required_project_directories_exist():
    for d in ["backend","backend/agents","backend/orchestration","backend/database","frontend","frontend/dashboard","model_configs","agent_templates","tool_plugins","migrations","tests","scripts","deployment","docs"]:
        assert (ROOT/d).is_dir(), d
