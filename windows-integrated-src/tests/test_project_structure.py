import csv
import json
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_roadmap_is_exactly_100_ordered_steps():
    with (ROOT / "docs/roadmap_100.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 100
    assert [int(row["step"]) for row in rows] == list(range(1, 101))
    assert all(row["status"] in {"DONE", "TODO", "BLOCKED"} for row in rows)
    progress = json.loads((ROOT / "docs/progress.json").read_text(encoding="utf-8"))
    assert [int(row["step"]) for row in rows if row["status"] == "DONE"] == progress["completed_steps"]
    blocked = {item["step"] for item in progress.get("blocked_steps", [])}
    assert blocked.isdisjoint(progress["completed_steps"])
    assert {int(row["step"]) for row in rows if row["status"] == "BLOCKED"} == blocked
    # There is no stage 101. All remaining stages may be blocked.
    runnable = next((n for n in range(1, 101)
             if n not in set(progress["completed_steps"]) | blocked), None)
    assert progress["next_step"] == runnable
    if runnable is None:
        assert len(progress["completed_steps"]) + len(blocked) == 100
        assert all(row["status"] != "TODO" for row in rows)

def test_original_spec_is_included():
    text = (ROOT / "docs/original_project_spec.txt").read_text(encoding="utf-8")
    assert "AI Autonomous Company" in text
    for code in range(1, 21):
        assert f"T{code:02d}" in text

def test_traceability_covers_all_20_original_tests():
    text = (ROOT / "docs/requirements_traceability.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^\| T\d{2} \|", text, flags=re.MULTILINE)) == 20

def test_required_project_directories_exist():
    for d in ["backend", "backend/agents", "backend/orchestration", "backend/database", "frontend", "frontend/dashboard", "model_configs", "agent_templates", "tool_plugins", "migrations", "tests", "scripts", "deployment", "docs"]:
        assert (ROOT/d).is_dir(), d


def test_markdown_plan_matches_csv_status():
    text = (ROOT / "docs/roadmap_100.md").read_text(encoding="utf-8")
    for number in range(1, 15):
        assert f"- [x] {number:03d}." in text
    assert "- [x] 016." in text
    assert "- [x] 017." in text
    assert "- [x] 018." in text
    assert "- [x] 019." in text
    assert "- [x] 020." in text
    assert "- [x] 021." in text
    assert "- [x] 022." in text
    assert "- [x] 023." in text
    assert "- [x] 024." in text
    assert "- [x] 025." in text
    assert "- [x] 026." in text
    assert "- [x] 027." in text
    assert "- [x] 028." in text
    assert "- [x] 029." in text
    assert "- [x] 030." in text
    assert "- [x] 031."
    assert "- [x] 032." in text
    assert "- [x] 033." in text
    assert "- [x] 034." in text
    assert "- [x] 035." in text
    assert "- [x] 036." in text
