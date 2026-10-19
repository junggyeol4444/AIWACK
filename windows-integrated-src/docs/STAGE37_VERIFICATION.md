# Stage 37 — Local event-driven task creation

- Event types: manual_alert, local_failure, review_requested; stored in SQLite.
- An event_key deduplicates repeated submissions. Conversion is bounded and transactional; produces unassigned todo tasks, not AI executions.
- UI: local event panel with explicit submit and dispatch buttons.
- No webhooks, external event ingestion, background service, AI model inference, or Windows EXE verification.
- Targeted tests: 6 passed (3 new + 3 scheduler). Full suite attempted but did not finish within execution limit; do not claim full regression pass.
