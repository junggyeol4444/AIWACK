# AIWACK Stage47: Employee long-term memory verification

Project: AI Autonomous Company. Source baseline: AIWACK_Stage46_Local_Offline_Source.zip.
Roadmap: 47/100 complete; next 48 (company shared knowledge repository).
Version: 0.1.39. Product completeness estimate: ~17–20% (subjective).

## Implemented
- `desktop/employee_memory.py`: SQLite employee_long_term_memories table, immutable content,
  archive instead of delete, employee-specific queries and owner-mediated inserts.
- Fields: employee_id, kind (fact/lesson/procedure/decision), title, content, source,
  confidence 0–100, optional expires_on (YYYY-MM-DD), created_at, archived_at.
- Defaults omit archived and expired rows. Previously saved data survives restart and
  deactivation of an employee. Archived/expired data can be retrieved through LocalStore.
- `desktop/storage.py`: authenticated owner APIs; `desktop/app.py`: Tkinter memory tab.
- Existing company data and original spec are preserved without rewriting.

## Actual commands and results (Linux environment)
- `python -m pytest -vv`: 541 passed in 64.85 s (exit code 0), after final GUI layout fix.
- `python -m pytest -q tests/test_employee_memory.py`: 24 passed (subsequent targeted run).
- `xvfb-run -a python scripts/stage47_offline_gui_smoke.py`: PASS. Actual Tkinter
  button invocation, employee scoping, search, detail view, archive, logout and login.
- `python scripts/verify_offline_runtime.py`: 15 commands passed. Outbound Python
  sockets blocked in each subprocess, including GUI scripts for previous stages.
- `python -m compileall -q desktop tests scripts`: PASS.
- Original ZIP source comparison: all 195 existing files retained, including
  `docs/original_project_spec.txt` and `dev_company.sqlite3` byte-identically.
- New Stage47 ZIP: integrity and content checks performed after packaging.

## Boundaries
- These are *owner-entered* local memory records, not autonomous AI memory capture,
  retrieval-augmented generation, model fine-tuning or real AI collaboration.
- Single-owner authorization; the SQLite database is not encrypted at rest. A person
  with direct write access to the database file can bypass app-level restrictions.
- Employees have no independent session identity. The employee ID scopes queries;
  it does not imply real agents are isolated by an operating-system security boundary.
- Date-based expiration filters default queries; it does not physically delete records.
- No Windows 10/11 real-device or EXE test and no actual GGUF model inference.
- Local Linux/Xvfb checks cannot establish full Windows compatibility.
- No GitHub, external servers or cloud AI APIs accessed for this implementation.
