# Stage 40 — Autonomous operations integration verification

Scope: local event -> task -> durable queue -> claim -> restart -> owner-approved recovery -> resolve, with SQLite persistence; scheduler, roadmap and queue regression tests.

Changes:
- Added `tests/test_stage40_integration.py` end-to-end SQLite restart/recovery integration test.
- Fixed `docs/roadmap_100.csv` inconsistencies: 37 and 39 had been marked TODO despite `docs/progress.json` listing them complete.
- Synchronized roadmap Markdown and CSV through stage 40.
- Removed outdated hardcoded stage-36 assertion from `tests/test_project_structure.py`, now comparing CSV to `docs/progress.json`.

Verified: `python -m pytest -q tests/test_stage40_integration.py tests/test_project_structure.py tests/test_recurring_scheduler.py tests/test_event_task_engine.py tests/test_task_queue.py tests/test_queue_recovery.py` -> 17 passed.

Full test suite: `python -m pytest -q -x` previously failed at the outdated roadmap assertion (234 passed, 1 failed); after correction a subsequent full-suite attempt exceeded the execution time limit at approximately 53% without reporting another failure. Full suite therefore NOT verified.

Limitations: No unattended AI inference or actual autonomous execution proven. No Windows hardware or GGUF inference tests. No actual external integrations. No GitHub or cloud API used.
