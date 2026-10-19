# AIWACK Stage49 — 지식 검색·출처·접근 권한 관리

- **Baseline:** `AIWACK_Stage48_Local_Offline_Source.zip` / `docs/progress.json` stages 1–48 complete, next 49.
- **Result:** Roadmap **49/100 (49%)**, next stage 50 `성과 평가와 업무 개선 제안`.
- **App version:** 0.1.41. **Estimated substantial product completeness:** approximately 18–22% (subjective estimate, separate from step count).

## Implementation

- `desktop/knowledge_access.py`: owner-only literal substring search over document title, body, original source and extra source references; bounded input, default archived exclusion, deterministic newest-first pagination limit.
- Existing Stage48 knowledge documents stay **owner-only by default**, even if initialized without an ACL row. Three modes: `owner_only`, `restricted` (explicit read grants), `company` (all active employee profile IDs). Mode transitions away from restricted delete old grants; archived docs never exposed in employee preview.
- Provenance reference annotations (`manual`, `local_file`, `internal_record`, `website_reference`) are append-only and explicitly `unverified`. No actual file existence check, website visit, source trust certification or automated factual verification is done.
- Per-document access change audit, add/revoke reads, SQLite FK checks and restricted no-delete/no-update triggers for provenance/audit. All app-layer write/read entry points require active owner authentication. An owner can simulate an employee's read access, **not** log in as that AI.
- `desktop/app.py`: native Tkinter search, source registration, visibility setting, grant/revoke and owner-only employee access preview, embedded in existing `회사 공동 지식 저장소` screen.
- `desktop/storage.py`: additive schema initialization and authenticated APIs, preserving existing records and storage paths.
- Fixed existing Markdown roadmap checkbox discrepancy for completed stage 47 (CSV/progress already marked DONE).

## Actual verification (Linux environment, 2026-10-13)

- `python -m pytest -q tests/test_knowledge_access.py tests/test_company_knowledge.py`: **44 passed**.
- `python -m pytest -vv --maxfail=1`: **585 passed in 68.34s** (exit 0). A preceding `pytest -q` run timed out and is **not** claimed as passing; the completed verbose run passed all tests.
- `xvfb-run -a python scripts/stage49_offline_gui_smoke.py`: PASS actual Tkinter button interactions for save/search/metadata/restricted grants/revoke/preview/restart.
- `python scripts/verify_offline_runtime.py`: **17 commands passed** including native GUI under Linux Xvfb, Python outbound socket calls blocked.
- `python -m compileall -q desktop tests scripts`: PASS.
- The cumulative ZIP is verified for member integrity and historical file preservation separately after packaging.

## Limitations

- Employee authorization is simulated by owner-invoked preview and applies only to these knowledge query helper APIs, **not** to real AI employee sessions. The owner can always access all documents. No independently authenticated employee, automatic AI knowledge retrieval, prompt augmentation, source verification or network integration exists.
- SQLite file is **not encrypted**. Direct filesystem access to the database is outside the app's owner authentication and SQLite triggers can be bypassed by administrators with DB file control.
- Python socket blocking in tests is not an OS firewall; no comprehensive network-exfiltration guarantee. No GitHub, external servers or cloud AI APIs were accessed during this task.
- Windows 10/11 physical device and packaged Windows EXE not tested. No live GGUF inference tested.
