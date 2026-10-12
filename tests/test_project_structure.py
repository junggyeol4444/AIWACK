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
    assert all(row["status"] in {"DONE", "TODO"} for row in rows)
    assert [int(row["step"]) for row in rows if row["status"] == "DONE"] == list(range(1, 14))

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
    for number in range(1, 14):
        assert f"- [x] {number:03d}." in text
    assert "- [ ] 014." in text
