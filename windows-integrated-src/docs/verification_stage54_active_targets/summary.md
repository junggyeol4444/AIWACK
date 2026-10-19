# Stage54 partial — inert HTML active targets (2026-10-14)

## Baseline and original requirements
- Base archive: `AIWACK_Stage54_Offline_HTML_Navigation_Preview_Continuation_Source.zip` (694 files).
- Confirmed in ZIP: `docs/original_project_spec.txt`, `docs/requirements_traceability.md`, `docs/roadmap_100.csv`, `docs/roadmap_100.md`, `docs/progress.json`.
- No separate original planning-text attachment was identifiable in the mounted files; the original text inside the ZIP is unmodified.
- Stage 1–53 marked DONE, 54 internet research/collection unfinished, 55+ untouched.

## Actual code changes
- New passive capped scanner in `desktop/research_captures.py` records `form action`, `iframe src`, and `script src`, including declared form method. Relative addresses use **owner-entered** source URL (ignores untrusted `<base>`).
- Per HTML at most 8 entries, 4 examples; same-origin, other-origin and invalid non-HTTP candidate strings. Invisible markup in script/style/template bodies is ignored; a script tag's own src is evaluated as a string. Does not submit/execute anything.
- `desktop/app.py` reports per-file and overall counters with explicit approval warning. Existing duplicate guard, race/review token, owner authentication, read-only preview, SQLite schema and original data retained.
- `tests/test_offline_research_active_targets.py` and `scripts/stage54_active_targets_gui_smoke.py` cover normal, suspicious, missing and malformed targets, read-only checks, blocked sockets and explicit import approval.
- `scripts/verify_offline_runtime.py` includes the GUI scenario.

## Limitations
- This is static inspection, *not* a browser implementation, a security verdict, or an observed source claim; it does not verify DNS/URL origin or prove that a page would actually load resources.
- Form submit behavior (button overrides, complex HTML/JS), remote data retrieval and authentication not implemented; never open/save URL content automatically.
- Windows 10/11 real device, EXE, local GGUF inference, long-duration operation not verified.
- Roadmap: 53/100 done; stage54 in progress, actual internet research and auto collection not implemented; subjective product completeness estimate 20–25%.

## Test results
- Full pytest in one run: **1212 passed, 0 failed in 128.48s** (`full_pytest.log`, `.exit`). This includes 15 new tests.
- Related parser/source preview pytest: **43 passed** (`related_pytest.log`), after correcting one invalid empty-body test fixture.
- Tkinter real GUI smoke: passed via Linux Xvfb (`gui_smoke.log`); cancel kept SQLite untouched and owner approval registered once.
- Offline desktop runtime: **49/49 commands passed** with Python socket/DNS methods blocked (`offline_runtime.log`, `.exit`), including the new GUI scenario.
- Python `compileall` succeeded for desktop/tests/scripts; Windows native verification not performed.
- All baseline 694 files retained: 688 byte-identical, 6 modified existing files (`source_preservation.json`); original plan, requirements traceability, CSV roadmap and SQLite data SHA-256 preserved.
- Archive re-extraction test results: see `reextract_related_pytest.log` and `reextract_gui.log`.

