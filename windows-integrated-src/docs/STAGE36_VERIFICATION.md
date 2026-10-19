# Stage 36 — 정기 작업 스케줄러

- Local SQLite recurring schedule table and occurrence audit; disabled by default.
- Owner explicitly enables schedule; intervals 5–10080 minutes.
- Each due check creates one unassigned `todo` task, never launches a model or process.
- Missed intervals are skipped, avoiding mass backlog on restart.
- Tkinter scheduler tab; checks on existing 5-minute logged-in GUI timer and manual button.
- No background service when app closed; Windows EXE and actual GGUF inference not verified.
- Focused tests and GUI smoke results are reported in the assistant's final message; do not infer whole-suite success.
