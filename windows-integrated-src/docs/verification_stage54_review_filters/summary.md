# Stage54 partial: local manual review filters — verification

## Scope and source

- Input: `AIWACK_Stage54_Offline_Followup_Notes_Continuation_Source.zip` (384 archived files).
- Read original project specification, requirements traceability, 100-step CSV and Markdown roadmap, and `docs/progress.json` **from the archived project** before editing. The separately attached original plan was not available in this runtime; its preserved project copy was used.
- New behavior: owner-only `all` / `pending` / `deferred` filter for *manual* URL follow-up annotations. Filter the bounded newest-first scan **before** the 40-row display limit, so a long list of deferred URLs does not obscure remaining pending URLs. Latest `reopen`/`noted` action and no annotation are pending. Manual status is never remote verification.
- No network requests, GitHub, external server, cloud API, software installation, or user-PC access.

## Actual checks

- Targeted related pytest: **51 passed** (`test_offline_research_review_filters.py`, `test_offline_research_followup_notes.py`, `test_offline_research_followups.py`). New file contains **13 tests** including parametrization.
- Full test inventory: **61 distinct test files** split into eight disjoint groups. Results: **880 passed, 1 failed** across those groups. **Do not report the full suite as passed.**
- Group 1: 97 passed (`group_1_pytest.log`).
- Group 2: 132 passed (`group_2_diagnostic.log`); an earlier group execution was interrupted without a completed result (`group_2_pytest.log`).
- Group 3: 147 passed (`group_3_pytest.log`).
- Group 4: 137 passed (`group_4_pytest.log`); orchestration command timed out while the child was running, but the child completed and wrote its pass summary.
- Group 5: 122 passed (`group_5_pytest.log`).
- Group 6: **82 passed, 1 failed** (`group_6_pytest.log`). Failure: **existing** `tests/test_task_parallel.py::test_real_two_local_subprocesses_overlap`, wall-clock assertion `< 1.5s` for two local subprocess runs; measured 2.12s. Four isolated reruns also failed with elapsed time between 1.50s and 2.85s (`group_6_timing_retest*.log`). No modification to that existing test or task runtime was made. This is a timing-sensitive regression failure in the test environment; the root cause was **not** established.
- Group 7: 89 passed (`group_7_diagnostic.log`); earlier group command did not finish.
- Group 8: 74 passed (`group_8_pytest.log`).
- GUI/offline: 5 real Linux Xvfb Tkinter scripts plus `python -m desktop.entry --self-test` exited 0 (`offline_gui_smoke.log`). Each GUI script blocks Python socket connection methods; verified filter selection, append-only note, logout/login, SQLite persistence. The entry self-test did not emit a success line but exited 0.
- Python compile: `python -m compileall -q desktop` passed.
- ZIP source preservation, SQLite byte integrity, original spec byte integrity, ZIP CRC check: see `source_preservation.txt` (written after packaging).

## Unverified / not implemented

- Windows 10/11 physical-machine GUI and build, real GGUF inference, internet research, automated remote content collection and external source authenticity remain **unverified / unimplemented**.
- 54th roadmap step is **in progress**; 1–53 complete. Roadmap completion **53/100 = 53%**. Real product maturity **~20–25%**, subjective estimate rather than tested metric.
