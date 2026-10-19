# AIWACK 로컬 데스크톱

`python -m desktop.entry`로 실행되는 네이티브 Tk 창입니다. 소유자 로그인이 필요합니다. 데이터는 Windows `%LOCALAPPDATA%\AIWACK\aiwack.sqlite3`에 저장됩니다. 회사/직원/조직 정보를 저장합니다. 모델 호출은 오직 관리자 수동 추론 시험을 선택한 경우에만 발생합니다.

이번 로컬 전용 16단계에서는 `조직 지휘 체계` 탭과 보고 관계 검증을 구현했습니다. Windows에서 `build_windows_exe.bat`로 별도 빌드할 수 있습니다. GitHub Actions나 예약 워크플로는 포함되어 있지 않습니다.

## Stage 17: Access grants (offline)

`직원 권한·도구` tab stores owner-managed employee grants in SQLite. No actual executor or tool connectors are shipped: all keys describe future capabilities, and all are denied by default. Inactive employees lose grants (permanently) and cannot be granted new rights. Admin/OS/system control is never granted via employee profiles. No network service is used.

## Stage 18 — local model connectors

Owner-only `로컬 AI 모델` tab persists multiple offline model profiles to the *local* SQLite DB. Two CLI adapter types: `llama_cpp` (`llama-cli` + GGUF weights) and `llamafile` (self-contained local executable, optional GGUF). Registering a profile never invokes a binary. Explicit inference-test click invokes the selected trusted local executable without `shell`, with a timeout, cancellation and displayed output. Local binary/model files are NOT bundled or downloaded. The user's own local engine can in principle have networking capabilities; the app itself does not contact remote services. Stage 19 adds owner-only per-employee model assignment, explicit local CLI invocation and metadata-only results history; no autonomous agent execution.


## Stage 19 — model assignment and durable invocation history

Native Tk `직원별 모델·호출` tab maps draft employee profiles to owner-configured local model connector profiles and stores metadata-only invocation records in SQLite. Assigning an employee model does NOT start processes. Calls occur only when an authenticated owner clicks the manual test button; cancellation and failures are recorded without prompt/output data. Deactivating an employee unassigns its model. Model files/weights are never bundled or fetched from any server.


## Stage 20 — CEO-only offline basic chat

`총괄 AI 대화` native Tk tab requires a single chief profile configured in the reporting hierarchy and a local CLI model assigned through the stage-19 tab. An authenticated owner must click Send to launch each local subprocess. The chief's `ceo` role is checked inside the same SQLite transaction as the audit insert. Local subprocess output is displayed in memory, not saved as raw text to SQLite. The stage-19 metadata audit still records call status. Cancel/logout/window close stops active invocation. No fake response, automatic AI work, cloud API, download, or GitHub integration. Each request is one-turn and does not include previous messages. Real GGUF model inference and Windows EXE build are unverified in this environment.


## Stage 21 — On-demand local CEO company status

An authenticated owner may click `회사 현황 조회` from the CEO chat tab to read a consistent SQLite snapshot. This requires the current draft CEO to hold BOTH `company:read` and `local_company_reader` grants. Goal names/statuses additionally require `goals:read` AND `local_goals_reader`; without either, goals (including counts) are withheld. The read never invokes a local process, network, or scheduler. Opt-in checkbox `대화 질문에 회사 현황 포함` explicitly adds bounded, labelled, untrusted data to the locally configured CEO model prompt; unchecked calls are unchanged. Raw prompt/output remain GUI-memory-only. Existing data and SQLite schema are preserved; Windows binary and GGUF inference not verified in the Linux development sandbox.


## Stage 22 — manually edited offline work plans

Authenticated owner uses the `업무 계획` native Tk tab to attach a written plan to an existing company goal, edit the title/description, order 1-30 text steps, and set a draft/ready/archived state. This writes to SQLite `company_work_plans` and `company_work_plan_steps` in a single transaction. Deleting a referenced goal is prohibited. A plan never starts executable tasks or AI calls. The feature requires no server, GitHub or network connection. Linux real-GUI and offline socket-blocked tests pass; Windows EXE build remains unverified.


## Stage 23 — local manually tracked tasks

The authenticated owner uses the `업무 관리` native Tk tab for task creation, editing and status transitions. Tasks are stored in `company_tasks`, status history in `company_task_status_events`, and may link to an existing stage-22 work plan. Such a plan cannot be deleted while referenced. Explicit status transitions are `todo`, `in_progress`, `blocked`, `done`, `cancelled`; completed/cancelled work must be reopened before modification. **No employee assignment or AI execution is performed**; the task store starts no subprocess and makes no network call. Windows EXE is built separately on the user PC with preinstalled PyInstaller.


## Stage 24: local task-to-profile routing

Owner-only `업무 자동 배정` tab stores strict department/job requirements, an auditable chosen employee, and explicit clears. Candidates are draft employee profiles, excluding CEO/department heads. Fair deterministic selection uses count of not-done/not-cancelled tasks and ascending employee ID for ties. No AI model runs. SQLite schema upgrades in place, preserving existing stage23 tasks. Requires a Windows build to distribute an EXE; ZIP is source.


## Stage 29 — bounded parallel local task execution

The owner can launch up to **two independent task drafts** via separate confirmed clicks in the native `AI 업무 실행` tab. The SQLite reservation is atomic, requires distinct active employee assignments, completed prerequisites, and a todo task; two running rows are allowed only for different task/employee IDs. Stage 27's global unique index is migrated non-destructively to per-task/per-employee partial indexes. Cancellation targets only the selected task. Unsaved draft text stays separated in GUI memory and is never auto-persisted. Saving an individual draft still requires the stage-28 owner confirmation. Real Windows EXE and GGUF inference are unverified. The user-provided CLI executable is not OS-sandboxed from network access.

## Stage 30 — chief order and returned artifact review

The new `총괄 AI 지시·회수` native tab requests a local chief text-only instruction draft, requires owner approval to store the immutable instruction, and routes it to the existing staff local runner **only when the owner separately clicks Execute**. The owner must explicitly save the successful worker output before asking the chief to review the entire result (max 1600 characters). The owner explicitly saves and reviews the chief's report; this does not complete the task. SQLite stores approved instructions and saved reports in plaintext; actual GGUF inference and Windows EXE are not verified. No remote service or autonomous job scheduler is started.

## Stage 35 — bounded plan breakdown

The new `복합 업무 세부 계획` Tk tab generates a persisted review-only draft from a ready, active-goal work plan containing 6–30 ordered steps and no existing tasks. One draft item per source step includes a conservative completion-check placeholder and a proposed sequential prerequisite. The owner must explicitly confirm applying the draft to create unassigned todo tasks and dependency audit events atomically; it never starts AI execution. Changed plans invalidate drafts. This is deterministic structural decomposition, **not** semantic AI planning or an offline GGUF inference test.

Stage47: 직원별 장기 기억은 관리자만 수동 저장/조회합니다. SQLite 평문 보관이며 직원 AI의 자동 회상·자율 학습은 아직 없습니다.
