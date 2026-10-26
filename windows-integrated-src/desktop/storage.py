"""Durable offline SQLite data and the single local owner identity.

The password-derived key authenticates a session. It does NOT encrypt the DB.
No remote authentication, external accounts, or financial operations exist yet.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import time

APP_DIR_NAME = "AIWACK"
MAX_PARALLEL_TASK_RUNS = 2  # Conservative bound for local RAM/GPU usage.
CHECKPOINT_KEY = "local_manual_test"
DESIGNATION_KINDS = frozenset({"rank", "job", "role"})  # Rank / job / responsibility role; NOT RBAC permissions.
HASH_ITERATIONS = 310_000
MAX_FAILURES = 5
LOCK_SECONDS = 60
OWNER_PERMISSIONS = frozenset({"notes:read", "notes:write", "company:manage", "agents:manage", "expenses:approve"})


class AuthenticationError(PermissionError):
    """Authentication failed, owner account locked, or action unauthorized."""


def user_data_dir() -> Path:
    """Return a persistent writable directory, never PyInstaller's temp folder."""
    override = os.getenv("AIWACK_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / "AppData" / "Local" / APP_DIR_NAME
    base = os.getenv("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / APP_DIR_NAME


class LocalStore:
    """Single-owner authentication controls notes stored in the local file."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else user_data_dir() / "aiwack.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._logged_in = False
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # A context-managed sqlite3 connection only commits: always close on Windows.
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as con:
            # Preserve local data from the previous EXE version.
            from desktop.direct_messages import initialize as initialize_messages
            initialize_messages(con)
            from desktop.department_chat import initialize as initialize_department_chat
            initialize_department_chat(con)
            from desktop.project_chat import initialize as initialize_project_chat
            initialize_project_chat(con)
            from desktop.meetings import initialize as initialize_meetings
            initialize_meetings(con)
            from desktop.meeting_opinions import initialize as initialize_meeting_opinions
            initialize_meeting_opinions(con)
            from desktop.meeting_decisions import initialize as initialize_meeting_decisions
            initialize_meeting_decisions(con)
            from desktop.company_meeting_ai import initialize as initialize_real_meeting_ai
            initialize_real_meeting_ai(con)
            from desktop.employee_memory import initialize as initialize_employee_memory
            initialize_employee_memory(con)
            from desktop.company_knowledge import initialize as initialize_company_knowledge
            initialize_company_knowledge(con)
            from desktop.knowledge_access import initialize as initialize_knowledge_access
            initialize_knowledge_access(con)
            from desktop.tool_registry import initialize as initialize_tool_registry
            initialize_tool_registry(con)
            from desktop.tool_approvals import initialize as initialize_tool_approvals
            initialize_tool_approvals(con)
            from desktop.company_approved_tool_execution import initialize as initialize_tool_execution
            initialize_tool_execution(con)
            from desktop.managed_documents import initialize as initialize_managed_documents
            initialize_managed_documents(con)
            from desktop.code_authoring import initialize as initialize_code_authoring
            initialize_code_authoring(con)
            from desktop.restricted_code_tests import initialize as initialize_restricted_code_tests
            initialize_restricted_code_tests(con)
            from desktop.media_tool_adapters import initialize as initialize_media_tool_adapters
            initialize_media_tool_adapters(con)
            from desktop.offline_service_integrations import initialize as initialize_service_integrations
            initialize_service_integrations(con)
            from desktop.tool_use_audit import initialize as initialize_tool_use_audit
            initialize_tool_use_audit(con)
            from desktop.business_portfolio import initialize as initialize_business_portfolio
            initialize_business_portfolio(con)
            from desktop.business_discovery import initialize as initialize_business_discovery
            initialize_business_discovery(con)
            from desktop.research_captures import initialize as initialize_research_captures
            initialize_research_captures(con)
            from desktop.public_web_research import initialize as initialize_public_web_research
            initialize_public_web_research(con)
            from desktop.public_site_crawler import initialize as initialize_public_site_crawler
            initialize_public_site_crawler(con)
            from desktop.market_evidence import initialize as initialize_market_evidence
            initialize_market_evidence(con)
            from desktop.financial_feasibility import initialize as initialize_financial_feasibility
            initialize_financial_feasibility(con)
            from desktop.chief_business_decisions import initialize as initialize_chief_business_decisions
            initialize_chief_business_decisions(con)
            from desktop.business_projects import initialize as initialize_business_projects
            initialize_business_projects(con)
            from desktop.product_catalog import initialize as initialize_product_catalog
            initialize_product_catalog(con)
            from desktop.product_production import initialize as initialize_product_production
            initialize_product_production(con)
            from desktop.product_release_review import initialize as initialize_product_release_review
            initialize_product_release_review(con)
            from desktop.service_operations_plan import initialize as initialize_service_operations_plan
            initialize_service_operations_plan(con)
            from desktop.sales_channel_contracts import initialize as initialize_sales_channel_contracts
            initialize_sales_channel_contracts(con)
            from desktop.offline_listing_prices import initialize as initialize_offline_listing_prices
            initialize_offline_listing_prices(con)
            from desktop.offline_order_simulations import initialize as initialize_offline_order_simulations
            initialize_offline_order_simulations(con)
            from desktop.offline_payment_verification import initialize as initialize_offline_payment_verification
            initialize_offline_payment_verification(con)
            from desktop.offline_payment_event_dedup import initialize as initialize_synthetic_event_dedup
            initialize_synthetic_event_dedup(con)
            from desktop.offline_delivery_simulations import initialize as initialize_mock_deliveries
            initialize_mock_deliveries(con)
            from desktop.offline_subscription_refund import initialize as initialize_mock_subscriptions
            initialize_mock_subscriptions(con)
            from desktop.local_synthetic_support import initialize as initialize_mock_support
            initialize_mock_support(con)
            from desktop.local_hypothetical_finance import initialize as initialize_hypothetical_finance
            initialize_hypothetical_finance(con)
            from desktop.local_budget_scenarios import initialize as initialize_budget_scenarios
            initialize_budget_scenarios(con)
            from desktop.local_company_diagnostics import initialize as initialize_company_diagnostics
            initialize_company_diagnostics(con)
            from desktop.local_staff_model_dashboard import initialize as initialize_staff_model_dashboard
            initialize_staff_model_dashboard(con)
            from desktop.stage87_90_management import initialize as initialize_management_control
            initialize_management_control(con)
            from desktop.stage91_93_security import initialize as initialize_stage91_93_security
            initialize_stage91_93_security(con)
            from desktop.performance_reviews import initialize as initialize_performance_reviews
            initialize_performance_reviews(con)
            from desktop.task_queue import initialize as initialize_queue
            initialize_queue(con)
            from desktop.recurring_scheduler import initialize
            initialize(con)
            from desktop.event_task_engine import initialize as initialize_events
            initialize_events(con)
            con.execute("""
                CREATE TABLE IF NOT EXISTS system_metadata (
                    id INTEGER PRIMARY KEY,
                    key VARCHAR(120) NOT NULL UNIQUE,
                    value VARCHAR(1000) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS owner_accounts (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    username TEXT NOT NULL,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    iterations INTEGER NOT NULL,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS company_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    mission TEXT NOT NULL DEFAULT '',
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'planned',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Stage 22: durable human-edited goal-linked work plans. A plan is
            # NOT an executable task or autonomous instruction. SQLite FK
            # protects goals with plans; ordered steps are atomic with the plan.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_work_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id INTEGER NOT NULL REFERENCES company_goals(id) ON DELETE RESTRICT,
                    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft'
                        CHECK(status IN ('draft', 'ready', 'archived')),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_work_plan_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL REFERENCES company_work_plans(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 30),
                    instruction TEXT NOT NULL CHECK(length(trim(instruction)) BETWEEN 1 AND 200),
                    UNIQUE(plan_id, position)
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS work_plan_goal_idx ON company_work_plans(goal_id)")
            con.execute("CREATE INDEX IF NOT EXISTS work_plan_steps_idx ON company_work_plan_steps(plan_id,position)")

            # Stage 23: tasks are manually tracked records, NOT executable AI jobs.
            # Optional link to a stage-22 plan is protected from accidental deletion.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER REFERENCES company_work_plans(id) ON DELETE RESTRICT,
                    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
                    description TEXT NOT NULL DEFAULT '' CHECK(length(description) <= 1000),
                    status TEXT NOT NULL DEFAULT 'todo'
                        CHECK(status IN ('todo','in_progress','blocked','done','cancelled')),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_status_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES company_tasks(id) ON DELETE CASCADE,
                    old_status TEXT,
                    new_status TEXT NOT NULL,
                    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS task_plan_idx ON company_tasks(plan_id)")
            con.execute("CREATE INDEX IF NOT EXISTS task_events_idx ON company_task_status_events(task_id,id)")


            # Stage 25: priority is optional metadata for old task rows; never
            # silently rewrite pre-existing task data during schema upgrades.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_priorities (
                    task_id INTEGER PRIMARY KEY REFERENCES company_tasks(id) ON DELETE CASCADE,
                    priority TEXT NOT NULL CHECK(priority IN ('low','normal','high','urgent')),
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_priority_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES company_tasks(id) ON DELETE CASCADE,
                    old_priority TEXT NOT NULL,
                    new_priority TEXT NOT NULL,
                    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK(new_priority IN ('low','normal','high','urgent'))
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS task_priority_events_idx ON company_task_priority_events(task_id,id)")

            # Stage 26: directed prerequisites (task_id depends on prerequisite_id).
            # Never rewrite old task rows; protect prerequisites from deletion.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_dependencies (
                    task_id INTEGER NOT NULL REFERENCES company_tasks(id) ON DELETE CASCADE,
                    prerequisite_id INTEGER NOT NULL REFERENCES company_tasks(id) ON DELETE RESTRICT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (task_id, prerequisite_id),
                    CHECK(task_id != prerequisite_id)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_dependency_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES company_tasks(id) ON DELETE CASCADE,
                    prerequisite_id INTEGER NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('added','removed')),
                    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS task_dependency_upstream_idx "
                        "ON company_task_dependencies(prerequisite_id,task_id)")
            con.execute("CREATE INDEX IF NOT EXISTS task_dependency_events_idx "
                        "ON company_task_dependency_events(task_id,id)")

            # Stage 29: owner-triggered bounded parallel local task execution.
            # Only metadata is stored: NEVER task prompts, outputs, stderr or paths.
            # A stale 'running' row after a crash requires explicit owner recovery.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES company_tasks(id) ON DELETE RESTRICT,
                    employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
                    model_id INTEGER NOT NULL,
                    model_name TEXT NOT NULL,
                    model_call_id INTEGER NOT NULL UNIQUE REFERENCES ai_model_call_history(id) ON DELETE RESTRICT,
                    status TEXT NOT NULL DEFAULT 'running'
                        CHECK(status IN ('running','success','failure','cancelled','timeout','interrupted')),
                    prompt_chars INTEGER NOT NULL CHECK(prompt_chars BETWEEN 1 AND 3000),
                    output_chars INTEGER NOT NULL DEFAULT 0 CHECK(output_chars BETWEEN 0 AND 20000),
                    duration_ms INTEGER NOT NULL DEFAULT 0 CHECK(duration_ms >= 0),
                    error_kind TEXT NOT NULL DEFAULT '',
                    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS task_runs_task_idx ON company_task_runs(task_id,id DESC)")
            # Speed up crash audits of unfinished work without rewriting any rows.
            con.execute("CREATE INDEX IF NOT EXISTS task_runs_running_audit_idx "
                        "ON company_task_runs(id DESC) WHERE status='running'")
            # Stage 27 installed a global single-flight partial unique index.
            # Migration only drops that INDEX, never an existing running row.
            con.execute("DROP INDEX IF EXISTS task_runs_one_running_idx")
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS task_runs_task_running_idx "
                        "ON company_task_runs(task_id) WHERE status='running'")
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS task_runs_employee_running_idx "
                        "ON company_task_runs(employee_id) WHERE status='running'")

            # Stage 28: explicit owner-saved textual results, not auto-saved model output.
            # Revisions are immutable; review decisions have append-only audit events.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES company_tasks(id) ON DELETE RESTRICT,
                    run_id INTEGER NOT NULL UNIQUE REFERENCES company_task_runs(id) ON DELETE RESTRICT,
                    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
                    body TEXT NOT NULL CHECK(length(body) BETWEEN 1 AND 20000),
                    sha256 TEXT NOT NULL CHECK(length(sha256)=64),
                    review_status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(review_status IN ('pending','approved','changes_requested','rejected')),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at DATETIME
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_artifact_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id INTEGER NOT NULL REFERENCES company_task_artifacts(id) ON DELETE RESTRICT,
                    old_status TEXT NOT NULL,
                    new_status TEXT NOT NULL CHECK(new_status IN ('approved','changes_requested','rejected')),
                    note TEXT NOT NULL CHECK(length(note) <= 1000),
                    reviewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS task_artifacts_task_idx ON company_task_artifacts(task_id,id DESC)")
            con.execute("CREATE INDEX IF NOT EXISTS task_artifact_reviews_idx ON company_task_artifact_reviews(artifact_id,id)")

            # Stage 30: explicit chief -> worker text orders and chief result reports.
            # No order triggers a model call by itself; owner confirmation is mandatory.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_chief_task_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL UNIQUE REFERENCES company_tasks(id) ON DELETE RESTRICT,
                    chief_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
                    worker_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
                    instruction TEXT NOT NULL CHECK(length(trim(instruction)) BETWEEN 1 AND 600),
                    task_fingerprint TEXT NOT NULL CHECK(length(task_fingerprint)=64),
                    approved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_chief_task_dispatches (
                    order_id INTEGER PRIMARY KEY REFERENCES company_chief_task_orders(id) ON DELETE RESTRICT,
                    run_id INTEGER NOT NULL UNIQUE REFERENCES company_task_runs(id) ON DELETE RESTRICT,
                    dispatched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_chief_task_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL UNIQUE REFERENCES company_chief_task_orders(id) ON DELETE RESTRICT,
                    artifact_id INTEGER NOT NULL UNIQUE REFERENCES company_task_artifacts(id) ON DELETE RESTRICT,
                    chief_employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
                    body TEXT NOT NULL CHECK(length(trim(body)) BETWEEN 1 AND 10000),
                    sha256 TEXT NOT NULL CHECK(length(sha256)=64),
                    owner_decision TEXT NOT NULL DEFAULT 'pending'
                        CHECK(owner_decision IN ('pending','accepted','rejected')),
                    owner_note TEXT NOT NULL DEFAULT '' CHECK(length(owner_note) <= 1000),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at DATETIME
                )
            """)

            # Additive migration: preserve existing owner-entered reports.
            # NULL means a legacy/manual report, not verified GGUF inference.
            if 'chief_model_call_id' not in {
                row[1] for row in con.execute('PRAGMA table_info(company_chief_task_reports)')
            }:
                con.execute('ALTER TABLE company_chief_task_reports '
                            'ADD COLUMN chief_model_call_id INTEGER REFERENCES ai_model_call_history(id)')
            con.execute('CREATE UNIQUE INDEX IF NOT EXISTS chief_report_model_call_unique '
                        'ON company_chief_task_reports(chief_model_call_id) '
                        'WHERE chief_model_call_id IS NOT NULL')

            # Stage 31: bounded-content, append-only aggregate health snapshots.
            # Monitoring never changes tasks, runs, reports, or employee data.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_health_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    severity TEXT NOT NULL CHECK(severity IN ('ok','attention','critical')),
                    metrics_json TEXT NOT NULL,
                    issues_json TEXT NOT NULL,
                    signature TEXT NOT NULL CHECK(length(signature)=64),
                    checked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS health_checks_time_idx "
                        "ON company_health_checks(checked_at DESC,id DESC)")

            # Stage 32: aggregate-only detection checkpoints; no business text,
            # model output, prompts, or raw goal/task descriptions are stored.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_detection_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    severity TEXT NOT NULL CHECK(severity IN ('ok','attention','critical')),
                    signals_json TEXT NOT NULL,
                    signature TEXT NOT NULL CHECK(length(signature)=64),
                    checked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS detection_checks_time_idx "
                        "ON company_detection_checks(checked_at DESC,id DESC)")

            # Stage 33: local signal-driven draft tasks. Creation is automatic
            # only for proposals; owner approval is required for real tasks.
            # Unique source identity prevents periodic duplicate proposals.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_kind TEXT NOT NULL
                        CHECK(source_kind IN ('active_goal','ready_plan','blocked_task')),
                    source_id INTEGER NOT NULL CHECK(source_id > 0),
                    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
                    description TEXT NOT NULL CHECK(length(description) <= 1000),
                    origin TEXT NOT NULL DEFAULT 'rule' CHECK(origin IN ('rule','local_ai')),
                    model_updated_at DATETIME,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','approved','rejected','stale')),
                    approved_task_id INTEGER UNIQUE REFERENCES company_tasks(id) ON DELETE RESTRICT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    decided_at DATETIME,
                    UNIQUE(source_kind, source_id),
                    CHECK((status='approved' AND approved_task_id IS NOT NULL)
                       OR (status!='approved' AND approved_task_id IS NULL))
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS task_proposals_status_idx "
                        "ON company_task_proposals(status,id DESC)")

            # Stage 34: immutable decision-support snapshots for Stage33 drafts.
            # This table is additive and never rewrites existing task priorities.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id INTEGER NOT NULL REFERENCES company_task_proposals(id) ON DELETE RESTRICT,
                    fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64),
                    feasibility TEXT NOT NULL CHECK(feasibility IN
                        ('needs_plan','needs_assignment','needs_breakdown','needs_unblocking')),
                    recommended_priority TEXT NOT NULL CHECK(recommended_priority IN
                        ('low','normal','high','urgent')),
                    score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
                    reason TEXT NOT NULL CHECK(length(reason) BETWEEN 1 AND 600),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS task_assessments_latest_idx "
                        "ON company_task_assessments(proposal_id,id DESC)")

            # Stage 35: additive review-only breakdowns. Approval alone creates
            # unassigned todo tasks, never invokes models or processes.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_breakdowns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL REFERENCES company_work_plans(id) ON DELETE CASCADE,
                    fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64),
                    status TEXT NOT NULL DEFAULT 'draft'
                        CHECK(status IN ('draft','applied','stale','rejected')),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    decided_at DATETIME,
                    UNIQUE(plan_id,fingerprint)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_breakdown_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    breakdown_id INTEGER NOT NULL REFERENCES company_task_breakdowns(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 30),
                    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
                    detail TEXT NOT NULL CHECK(length(detail) <= 1000),
                    prerequisite_position INTEGER CHECK(prerequisite_position IS NULL
                        OR (prerequisite_position >= 1 AND prerequisite_position < position)),
                    task_id INTEGER UNIQUE REFERENCES company_tasks(id) ON DELETE RESTRICT,
                    UNIQUE(breakdown_id,position)
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS breakdown_plan_idx "
                        "ON company_task_breakdowns(plan_id,id DESC)")
            con.execute("CREATE INDEX IF NOT EXISTS breakdown_item_idx "
                        "ON company_task_breakdown_items(breakdown_id,position)")

            # Stage 24: local task routing requirements and selected AI profile.
            # Selection is metadata: no model execution, networking, or privilege grants.
            # Existing stage-23 task rows remain unchanged during schema upgrade.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_routing (
                    task_id INTEGER PRIMARY KEY REFERENCES company_tasks(id) ON DELETE CASCADE,
                    department_id INTEGER REFERENCES company_departments(id) ON DELETE RESTRICT,
                    job_id INTEGER REFERENCES company_designations(id) ON DELETE RESTRICT
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_assignments (
                    task_id INTEGER PRIMARY KEY REFERENCES company_tasks(id) ON DELETE CASCADE,
                    employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
                    reason TEXT NOT NULL,
                    assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_task_assignment_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES company_tasks(id) ON DELETE CASCADE,
                    employee_id INTEGER REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
                    action TEXT NOT NULL CHECK(action IN ('auto_assigned','cleared','requirements_changed','employee_changed','employee_inactive')),
                    detail TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS task_assignee_idx ON company_task_assignments(employee_id)")
            con.execute("CREATE INDEX IF NOT EXISTS task_assignment_history_idx ON company_task_assignment_events(task_id,id)")

            # Stage 18: owner-managed local model registry. Models and credentials
            # are never downloaded, started, or probed during database startup.
            con.execute("""
                CREATE TABLE IF NOT EXISTS ai_local_models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    backend TEXT NOT NULL CHECK(backend IN ('llama_cpp', 'llamafile')),
                    executable_path TEXT NOT NULL,
                    model_path TEXT NOT NULL DEFAULT '',
                    max_tokens INTEGER NOT NULL CHECK(max_tokens BETWEEN 1 AND 512),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Stage 12: stable department identifiers; future staff can reference these.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_departments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Stage 13: job/position taxonomy with stable IDs for future employee assignment.
            # Role labels here do not grant any operating-system or owner privileges.
            con.execute("""
                CREATE TABLE IF NOT EXISTS company_designations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK(kind IN ('rank', 'job', 'role')),
                    name TEXT NOT NULL COLLATE NOCASE,
                    description TEXT NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (kind, name)
                )
            """)

            # Stage 14: AI employee *information* only. Records are drafts, not
            # executable agents. Referential links remain stable across restarts.
            # Deleting a referenced department/designation must be rejected.
            con.execute("""
                CREATE TABLE IF NOT EXISTS ai_employee_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_key TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    display_name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    department_id INTEGER REFERENCES company_departments(id) ON DELETE RESTRICT,
                    rank_id INTEGER REFERENCES company_designations(id) ON DELETE RESTRICT,
                    job_id INTEGER REFERENCES company_designations(id) ON DELETE RESTRICT,
                    role_id INTEGER REFERENCES company_designations(id) ON DELETE RESTRICT,
                    lifecycle TEXT NOT NULL DEFAULT 'draft' CHECK(lifecycle IN ('draft', 'inactive')),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK(length(trim(employee_key)) BETWEEN 3 AND 64),
                    CHECK(length(trim(display_name)) BETWEEN 1 AND 80)
                )
            """)
            # Prevent moving a designation to a different classification if
            # any employee draft currently references it. This complements the
            # insert/update triggers below.
            con.execute("""
                CREATE TRIGGER IF NOT EXISTS ai_employee_designation_kind_guard
                BEFORE UPDATE OF kind ON company_designations
                WHEN OLD.kind <> NEW.kind
                BEGIN
                    SELECT RAISE(ABORT, 'designation used by employee')
                    WHERE EXISTS (
                        SELECT 1 FROM ai_employee_profiles WHERE
                            (OLD.kind='rank' AND rank_id=OLD.id) OR
                            (OLD.kind='job' AND job_id=OLD.id) OR
                            (OLD.kind='role' AND role_id=OLD.id));
                END
            """)
            # SQLite foreign keys check the identifier but not its designation
            # classification. Guard every insert/update, including direct SQL.
            for operation in ('INSERT', 'UPDATE'):
                con.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS ai_employee_kind_{operation.lower()}
                    BEFORE {operation} ON ai_employee_profiles
                    BEGIN
                        SELECT RAISE(ABORT, 'rank_id kind mismatch')
                        WHERE NEW.rank_id IS NOT NULL AND NOT EXISTS (
                            SELECT 1 FROM company_designations
                            WHERE id=NEW.rank_id AND kind='rank');
                        SELECT RAISE(ABORT, 'job_id kind mismatch')
                        WHERE NEW.job_id IS NOT NULL AND NOT EXISTS (
                            SELECT 1 FROM company_designations
                            WHERE id=NEW.job_id AND kind='job');
                        SELECT RAISE(ABORT, 'role_id kind mismatch')
                        WHERE NEW.role_id IS NOT NULL AND NOT EXISTS (
                            SELECT 1 FROM company_designations
                            WHERE id=NEW.role_id AND kind='role');
                    END
                """)

            # Stage 16: the organizational reporting tree is metadata only.
            # Does not grant permissions or start AI workers.
            con.execute("""
                CREATE TABLE IF NOT EXISTS ai_reporting_lines (
                    employee_id INTEGER PRIMARY KEY REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
                    tier TEXT NOT NULL CHECK(tier IN ('ceo', 'department_head', 'staff')),
                    manager_id INTEGER REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
                    CHECK(manager_id IS NULL OR employee_id <> manager_id)
                )
            """)
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ai_reporting_single_ceo
                ON ai_reporting_lines(tier) WHERE tier='ceo'
            """)
            con.execute("""
                CREATE INDEX IF NOT EXISTS ai_reporting_manager_id ON ai_reporting_lines(manager_id)
            """)
            for operation in ('INSERT', 'UPDATE'):
                con.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS ai_reporting_validate_{operation.lower()}
                    BEFORE {operation} ON ai_reporting_lines
                    BEGIN
                        SELECT RAISE(ABORT, 'inactive employee cannot be assigned')
                        WHERE NOT EXISTS (SELECT 1 FROM ai_employee_profiles
                                          WHERE id=NEW.employee_id AND lifecycle='draft');
                        SELECT RAISE(ABORT, 'ceo needs no department or manager')
                        WHERE NEW.tier='ceo' AND
                            (NEW.manager_id IS NOT NULL OR
                             (SELECT department_id FROM ai_employee_profiles WHERE id=NEW.employee_id) IS NOT NULL);
                        SELECT RAISE(ABORT, 'manager and department required')
                        WHERE NEW.tier<>'ceo' AND (NEW.manager_id IS NULL OR
                            (SELECT department_id FROM ai_employee_profiles WHERE id=NEW.employee_id) IS NULL);
                        SELECT RAISE(ABORT, 'department head must report to ceo')
                        WHERE NEW.tier='department_head' AND NOT EXISTS (
                            SELECT 1 FROM ai_reporting_lines l
                            JOIN ai_employee_profiles e ON e.id=l.employee_id
                            WHERE l.employee_id=NEW.manager_id AND l.tier='ceo' AND e.lifecycle='draft');
                        SELECT RAISE(ABORT, 'staff must report to head in same department')
                        WHERE NEW.tier='staff' AND NOT EXISTS (
                            SELECT 1 FROM ai_reporting_lines l
                            JOIN ai_employee_profiles boss ON boss.id=l.employee_id
                            JOIN ai_employee_profiles staff ON staff.id=NEW.employee_id
                            WHERE l.employee_id=NEW.manager_id AND l.tier='department_head'
                              AND boss.lifecycle='draft' AND boss.department_id=staff.department_id);
                        SELECT RAISE(ABORT, 'cannot change tier of a manager with reports')
                        WHERE EXISTS (SELECT 1 FROM ai_reporting_lines children
                                      WHERE children.manager_id=NEW.employee_id)
                          AND (NEW.tier<>(SELECT tier FROM ai_reporting_lines WHERE employee_id=NEW.employee_id)
                               OR NEW.employee_id<>OLD.employee_id);
                    END
                """ if operation == 'UPDATE' else f"""
                    CREATE TRIGGER IF NOT EXISTS ai_reporting_validate_insert
                    BEFORE INSERT ON ai_reporting_lines
                    BEGIN
                        SELECT RAISE(ABORT, 'inactive employee cannot be assigned')
                        WHERE NOT EXISTS (SELECT 1 FROM ai_employee_profiles
                                          WHERE id=NEW.employee_id AND lifecycle='draft');
                        SELECT RAISE(ABORT, 'ceo needs no department or manager')
                        WHERE NEW.tier='ceo' AND (NEW.manager_id IS NOT NULL OR
                            (SELECT department_id FROM ai_employee_profiles WHERE id=NEW.employee_id) IS NOT NULL);
                        SELECT RAISE(ABORT, 'manager and department required')
                        WHERE NEW.tier<>'ceo' AND (NEW.manager_id IS NULL OR
                            (SELECT department_id FROM ai_employee_profiles WHERE id=NEW.employee_id) IS NULL);
                        SELECT RAISE(ABORT, 'department head must report to ceo')
                        WHERE NEW.tier='department_head' AND NOT EXISTS (
                            SELECT 1 FROM ai_reporting_lines l JOIN ai_employee_profiles e ON e.id=l.employee_id
                            WHERE l.employee_id=NEW.manager_id AND l.tier='ceo' AND e.lifecycle='draft');
                        SELECT RAISE(ABORT, 'staff must report to head in same department')
                        WHERE NEW.tier='staff' AND NOT EXISTS (
                            SELECT 1 FROM ai_reporting_lines l JOIN ai_employee_profiles boss ON boss.id=l.employee_id
                            JOIN ai_employee_profiles staff ON staff.id=NEW.employee_id
                            WHERE l.employee_id=NEW.manager_id AND l.tier='department_head'
                              AND boss.lifecycle='draft' AND boss.department_id=staff.department_id);
                    END
                """)
            con.execute("""
                CREATE TRIGGER IF NOT EXISTS ai_reporting_no_delete_manager
                BEFORE DELETE ON ai_reporting_lines
                WHEN EXISTS (SELECT 1 FROM ai_reporting_lines WHERE manager_id=OLD.employee_id)
                BEGIN SELECT RAISE(ABORT, 'manager has reports'); END
            """)
            con.execute("""
                CREATE TRIGGER IF NOT EXISTS ai_reporting_protect_employee
                BEFORE UPDATE OF department_id, lifecycle ON ai_employee_profiles
                BEGIN
                    SELECT RAISE(ABORT, 'manager has reports; cannot deactivate or move')
                    WHERE EXISTS (SELECT 1 FROM ai_reporting_lines WHERE manager_id=OLD.id)
                      AND (NEW.lifecycle='inactive' OR NEW.department_id IS NOT OLD.department_id);
                    SELECT RAISE(ABORT, 'ceo must not belong to a department')
                    WHERE NEW.department_id IS NOT NULL AND EXISTS (
                        SELECT 1 FROM ai_reporting_lines WHERE employee_id=OLD.id AND tier='ceo');
                    SELECT RAISE(ABORT, 'assigned head or staff must have department')
                    WHERE NEW.department_id IS NULL AND EXISTS (
                        SELECT 1 FROM ai_reporting_lines WHERE employee_id=OLD.id AND tier<>'ceo');
                    SELECT RAISE(ABORT, 'employee must match manager department')
                    WHERE EXISTS (
                        SELECT 1 FROM ai_reporting_lines l
                        JOIN ai_employee_profiles mgr ON mgr.id=l.manager_id
                        WHERE l.employee_id=OLD.id AND l.tier='staff'
                          AND NEW.department_id IS NOT mgr.department_id);
                END
            """)

            # Stage 17: local-only permission/tool policy storage.
            # Foreign keys guarantee grants cannot exist for unknown employees.
            # No arbitrary tool name, operating-system command or remote URL.
            con.execute("""
                CREATE TABLE IF NOT EXISTS ai_employee_capability_grants (
                    employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE CASCADE,
                    capability TEXT NOT NULL CHECK(capability IN (
                        'company:read', 'goals:read', 'tasks:propose', 'documents:draft')),
                    PRIMARY KEY (employee_id, capability)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS ai_employee_tool_grants (
                    employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE CASCADE,
                    tool_key TEXT NOT NULL CHECK(tool_key IN (
                        'local_company_reader', 'local_goals_reader',
                        'local_task_drafter', 'local_document_drafter')),
                    PRIMARY KEY (employee_id, tool_key)
                )
            """)
            # 기존 SQLite CHECK와 이전 도구 부여 기록을 보존하면서 Windows 전용
            # 신규 도구 권한을 별도 테이블에 추가한다(기존 테이블 재작성 금지).
            con.execute("""CREATE TABLE IF NOT EXISTS ai_employee_native_tool_grants (
                employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE CASCADE,
                tool_key TEXT NOT NULL CHECK(tool_key='local_windows_version_reader'),
                PRIMARY KEY(employee_id,tool_key))""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS ai_native_tool_grant_requires_capability
                BEFORE INSERT ON ai_employee_native_tool_grants
                WHEN NOT EXISTS (SELECT 1 FROM ai_employee_profiles
                                  WHERE id=NEW.employee_id AND lifecycle='draft')
                  OR NOT EXISTS (SELECT 1 FROM ai_employee_capability_grants
                                 WHERE employee_id=NEW.employee_id AND capability='company:read')
                BEGIN SELECT RAISE(ABORT,'native tool requires active company:read grant'); END""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS ai_native_tool_revoke_with_company_read
                AFTER DELETE ON ai_employee_capability_grants
                WHEN OLD.capability='company:read'
                BEGIN DELETE FROM ai_employee_native_tool_grants
                      WHERE employee_id=OLD.employee_id; END""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS ai_native_tool_revoke_on_deactivation
                AFTER UPDATE OF lifecycle ON ai_employee_profiles
                WHEN NEW.lifecycle='inactive' AND OLD.lifecycle<>'inactive'
                BEGIN DELETE FROM ai_employee_native_tool_grants
                      WHERE employee_id=NEW.id; END""")
            # Fail closed at the database layer: never grant inactive employees.
            for table in ('ai_employee_capability_grants', 'ai_employee_tool_grants'):
                con.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS {table}_active_only
                    BEFORE INSERT ON {table}
                    WHEN NOT EXISTS (SELECT 1 FROM ai_employee_profiles
                        WHERE id=NEW.employee_id AND lifecycle='draft')
                    BEGIN SELECT RAISE(ABORT, 'inactive employee cannot receive grants'); END
                """)
            # Raw SQL must not bypass tool-to-capability dependency rules.
            # The application never executes these tools; policy is enforced anyway.
            con.execute("""
                CREATE TRIGGER IF NOT EXISTS ai_tool_grant_requires_capability
                BEFORE INSERT ON ai_employee_tool_grants
                WHEN NOT EXISTS (
                    SELECT 1 FROM ai_employee_capability_grants p
                    WHERE p.employee_id=NEW.employee_id AND p.capability=(
                        CASE NEW.tool_key
                            WHEN 'local_company_reader' THEN 'company:read'
                            WHEN 'local_goals_reader' THEN 'goals:read'
                            WHEN 'local_task_drafter' THEN 'tasks:propose'
                            WHEN 'local_document_drafter' THEN 'documents:draft'
                        END))
                BEGIN SELECT RAISE(ABORT, 'tool requires capability'); END
            """)
            con.execute("""
                CREATE TRIGGER IF NOT EXISTS ai_tool_revoke_with_capability
                AFTER DELETE ON ai_employee_capability_grants
                BEGIN
                    DELETE FROM ai_employee_tool_grants
                    WHERE employee_id=OLD.employee_id AND tool_key=(
                        CASE OLD.capability
                            WHEN 'company:read' THEN 'local_company_reader'
                            WHEN 'goals:read' THEN 'local_goals_reader'
                            WHEN 'tasks:propose' THEN 'local_task_drafter'
                            WHEN 'documents:draft' THEN 'local_document_drafter'
                        END);
                END
            """)
            # Deactivation removes grants permanently: reactivation does not silently restore rights.
            con.execute("""
                CREATE TRIGGER IF NOT EXISTS ai_employee_revoke_on_deactivation
                AFTER UPDATE OF lifecycle ON ai_employee_profiles
                WHEN NEW.lifecycle='inactive' AND OLD.lifecycle<>'inactive'
                BEGIN
                    DELETE FROM ai_employee_capability_grants WHERE employee_id=NEW.id;
                    DELETE FROM ai_employee_tool_grants WHERE employee_id=NEW.id;
                END
            """)

            # Stage 19: owner-assigned local model for each employee. This is
            # configuration metadata, not automatic agent execution or API access.
            con.execute("""
                CREATE TABLE IF NOT EXISTS ai_employee_model_assignments (
                    employee_id INTEGER PRIMARY KEY REFERENCES ai_employee_profiles(id) ON DELETE CASCADE,
                    model_id INTEGER NOT NULL REFERENCES ai_local_models(id) ON DELETE RESTRICT,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for operation in ('INSERT', 'UPDATE'):
                con.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS ai_model_assignment_draft_{operation.lower()}
                    BEFORE {operation} ON ai_employee_model_assignments
                    WHEN NOT EXISTS (SELECT 1 FROM ai_employee_profiles
                                     WHERE id=NEW.employee_id AND lifecycle='draft')
                    BEGIN SELECT RAISE(ABORT, 'model assignment requires active draft'); END
                """)
            con.execute("""
                CREATE TRIGGER IF NOT EXISTS ai_employee_model_unbind_inactive
                AFTER UPDATE OF lifecycle ON ai_employee_profiles
                WHEN NEW.lifecycle='inactive' AND OLD.lifecycle<>'inactive'
                BEGIN
                    DELETE FROM ai_employee_model_assignments WHERE employee_id=NEW.id;
                END
            """)
            # Historical model IDs/names are snapshots, not an FK: deleting a
            # model must not erase the audit. Prompts and model output are NEVER stored.
            con.execute("""
                CREATE TABLE IF NOT EXISTS ai_model_call_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
                    model_id INTEGER NOT NULL,
                    model_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running'
                        CHECK(status IN ('running','success','failure','cancelled','timeout')),
                    prompt_chars INTEGER NOT NULL CHECK(prompt_chars BETWEEN 1 AND 3000),
                    output_chars INTEGER NOT NULL DEFAULT 0 CHECK(output_chars BETWEEN 0 AND 20000),
                    duration_ms INTEGER NOT NULL DEFAULT 0 CHECK(duration_ms >= 0),
                    error_kind TEXT NOT NULL DEFAULT '',
                    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME
                )
            """)
            con.execute("""
                CREATE INDEX IF NOT EXISTS ai_model_call_history_employee
                ON ai_model_call_history(employee_id, id DESC)
            """)
            # Existing Windows DBs obtain the 15-department campaign schema on startup.
            # This is additive; no prior tables or user records are overwritten.
            from desktop.company_wide_campaign import initialize as initialize_wide_campaign
            initialize_wide_campaign(con)

    def has_owner(self) -> bool:
        with self._connect() as con:
            return con.execute("SELECT 1 FROM owner_accounts WHERE id = 1").fetchone() is not None

    @property
    def is_authenticated(self) -> bool:
        return self._logged_in

    def setup_owner(self, username: str, password: str) -> None:
        """First-run setup; a second owner cannot overwrite credentials."""
        username = username.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
            raise ValueError("관리자 ID는 영문·숫자·._-로 3~32자여야 합니다.")
        if not isinstance(password, str) or not (12 <= len(password) <= 1024) or password.isspace():
            raise ValueError("비밀번호는 12~1024자로 설정하세요.")
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
        try:
            with self._connect() as con:
                con.execute(
                    "INSERT INTO owner_accounts (id, username, password_salt, password_hash, iterations) "
                    "VALUES (1, ?, ?, ?, ?)",
                    (username, salt, digest, HASH_ITERATIONS),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthenticationError("관리자 계정은 이미 생성되어 있습니다.") from exc
        self._logged_in = True

    def login(self, username: str, password: str) -> None:
        """Authenticate once per process; throttle repeated failures across restarts."""
        self._logged_in = False
        if not isinstance(username, str) or not isinstance(password, str):
            raise AuthenticationError("계정 또는 비밀번호가 올바르지 않습니다.")
        error = None
        with self._connect() as con:
            row = con.execute(
                "SELECT username, password_salt, password_hash, iterations, failed_attempts, locked_until "
                "FROM owner_accounts WHERE id = 1"
            ).fetchone()
            if row is None:
                error = "관리자 계정을 먼저 설정해야 합니다."
            elif row[5] > int(time.time()):
                error = "로그인 시도가 너무 많습니다. 1분 후 다시 시도하세요."
            else:
                is_valid = hmac.compare_digest(str(row[0]), username) and hmac.compare_digest(
                    hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), row[1], int(row[3])), row[2]
                )
                if is_valid:
                    con.execute("UPDATE owner_accounts SET failed_attempts=0, locked_until=0 WHERE id=1")
                else:
                    attempts = row[4] + 1
                    con.execute("UPDATE owner_accounts SET failed_attempts=?, locked_until=? WHERE id=1",
                                (attempts, int(time.time()) + LOCK_SECONDS if attempts >= MAX_FAILURES else 0))
                    error = "계정 또는 비밀번호가 올바르지 않습니다."
        if error:
            raise AuthenticationError(error)
        self._logged_in = True

    def logout(self) -> None:
        self._logged_in = False

    def require_permission(self, permission: str) -> None:
        if not self._logged_in or permission not in OWNER_PERMISSIONS:
            raise AuthenticationError("관리자 로그인이 필요한 작업입니다.")

    def role(self) -> str | None:
        return "owner" if self._logged_in else None

    @staticmethod
    def _validated_text(value: str, field: str, limit: int, *, required: bool = False) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} 항목은 문자열이어야 합니다.")
        cleaned = value.strip()
        if len(cleaned) > limit or (required and not cleaned):
            raise ValueError(f"{field} 항목은 {'1~' if required else '0~'}{limit}자여야 합니다.")
        return cleaned

    def read_company(self) -> dict[str, str]:
        """Return the persisted company profile or safe empty first-run defaults."""
        self.require_permission("company:manage")
        with self._connect() as con:
            row = con.execute("SELECT name, description, mission FROM company_profile WHERE id=1").fetchone()
        return dict(zip(("name", "description", "mission"), row)) if row else {
            "name": "AI Autonomous Company", "description": "", "mission": ""
        }

    def save_company(self, name: str, description: str, mission: str) -> None:
        """Write only after an authenticated owner confirms the changes."""
        self.require_permission("company:manage")
        fields = (
            self._validated_text(name, "회사명", 80, required=True),
            self._validated_text(description, "회사 소개", 500),
            self._validated_text(mission, "운영 방향", 500),
        )
        with self._connect() as con:
            con.execute("""
                INSERT INTO company_profile (id, name, description, mission) VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                    description=excluded.description, mission=excluded.mission,
                    updated_at=CURRENT_TIMESTAMP
            """, fields)

    def list_goals(self) -> list[dict[str, object]]:
        self.require_permission("company:manage")
        with self._connect() as con:
            rows = con.execute("SELECT id, title, detail, status FROM company_goals ORDER BY id").fetchall()
        return [dict(zip(("id", "title", "detail", "status"), row)) for row in rows]

    def _require_goal_id(self, goal_id: int) -> None:
        if not isinstance(goal_id, int) or isinstance(goal_id, bool) or goal_id < 1:
            raise ValueError("올바른 목표 ID가 필요합니다.")

    def add_goal(self, title: str, detail: str = "") -> int:
        self.require_permission("company:manage")
        validated = (self._validated_text(title, "목표명", 120, required=True),
                     self._validated_text(detail, "목표 설명", 500))
        with self._connect() as con:
            cursor = con.execute("INSERT INTO company_goals (title, detail) VALUES (?, ?)", validated)
            return int(cursor.lastrowid)

    def update_goal(self, goal_id: int, title: str, detail: str, status: str) -> None:
        self.require_permission("company:manage")
        self._require_goal_id(goal_id)
        if status not in {"planned", "active", "done", "paused"}:
            raise ValueError("올바르지 않은 목표 상태입니다.")
        values = (self._validated_text(title, "목표명", 120, required=True),
                  self._validated_text(detail, "목표 설명", 500), status, goal_id)
        with self._connect() as con:
            cursor = con.execute("""
                UPDATE company_goals SET title=?, detail=?, status=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, values)
            if cursor.rowcount != 1:
                raise ValueError("선택한 목표를 찾을 수 없습니다.")

    def delete_goal(self, goal_id: int) -> None:
        self.require_permission("company:manage")
        self._require_goal_id(goal_id)
        with self._connect() as con:
            try:
                cursor = con.execute("DELETE FROM company_goals WHERE id=?", (goal_id,))
            except sqlite3.IntegrityError as exc:
                raise ValueError("연결된 업무 계획이 있어 목표를 삭제할 수 없습니다. 계획을 먼저 삭제하세요.") from exc
            if cursor.rowcount != 1:
                raise ValueError("선택한 목표를 찾을 수 없습니다.")

    @staticmethod
    def _plan_id(value: int, label: str = "업무 계획") -> int:
        if type(value) is not int or value < 1:
            raise ValueError(f"올바른 {label} 번호가 필요합니다.")
        return value

    @classmethod
    def _plan_values(cls, title: str, description: str, steps: list[str], status: str) -> tuple[str, str, list[str]]:
        heading = cls._validated_text(title, "계획명", 120, required=True)
        details = cls._validated_text(description, "계획 설명", 1000)
        if status not in {"draft", "ready", "archived"}:
            raise ValueError("올바르지 않은 계획 상태입니다.")
        if not isinstance(steps, list) or not (1 <= len(steps) <= 30):
            raise ValueError("계획의 실행 순서는 1~30개를 작성해야 합니다.")
        cleaned = [cls._validated_text(step, "실행 순서", 200, required=True) for step in steps]
        return heading, details, cleaned

    def add_work_plan(self, goal_id: int, title: str, description: str,
                      steps: list[str], status: str = "draft") -> int:
        """Store a manual plan and all ordered steps in one transaction; never execute."""
        self.require_permission("company:manage")
        goal_id = self._plan_id(goal_id, "목표")
        heading, details, cleaned = self._plan_values(title, description, steps, status)
        with self._connect() as con:
            if con.execute("SELECT 1 FROM company_goals WHERE id=?", (goal_id,)).fetchone() is None:
                raise ValueError("연결할 목표가 존재하지 않습니다.")
            cursor = con.execute("INSERT INTO company_work_plans(goal_id,title,description,status) VALUES(?,?,?,?)",
                                 (goal_id, heading, details, status))
            identifier = int(cursor.lastrowid)
            con.executemany("INSERT INTO company_work_plan_steps(plan_id,position,instruction) VALUES(?,?,?)",
                            [(identifier, index, step) for index, step in enumerate(cleaned, start=1)])
            return identifier

    def update_work_plan(self, plan_id: int, goal_id: int, title: str, description: str,
                         steps: list[str], status: str = "draft") -> None:
        self.require_permission("company:manage")
        plan_id, goal_id = self._plan_id(plan_id), self._plan_id(goal_id, "목표")
        heading, details, cleaned = self._plan_values(title, description, steps, status)
        with self._connect() as con:
            if con.execute("SELECT 1 FROM company_goals WHERE id=?", (goal_id,)).fetchone() is None:
                raise ValueError("연결할 목표가 존재하지 않습니다.")
            cursor = con.execute("""UPDATE company_work_plans SET goal_id=?,title=?,description=?,status=?,
                                   updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                                 (goal_id, heading, details, status, plan_id))
            if cursor.rowcount != 1:
                raise ValueError("선택한 업무 계획을 찾을 수 없습니다.")
            con.execute("DELETE FROM company_work_plan_steps WHERE plan_id=?", (plan_id,))
            con.executemany("INSERT INTO company_work_plan_steps(plan_id,position,instruction) VALUES(?,?,?)",
                            [(plan_id, index, step) for index, step in enumerate(cleaned, start=1)])

    def read_work_plan(self, plan_id: int) -> dict[str, object]:
        self.require_permission("company:manage")
        plan_id = self._plan_id(plan_id)
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            row = con.execute("""SELECT p.id,p.goal_id,g.title AS goal_title,p.title,p.description,p.status,
                                 p.created_at,p.updated_at FROM company_work_plans p
                                 JOIN company_goals g ON g.id=p.goal_id WHERE p.id=?""", (plan_id,)).fetchone()
            if row is None:
                raise ValueError("선택한 업무 계획을 찾을 수 없습니다.")
            steps = con.execute("""SELECT instruction FROM company_work_plan_steps
                                   WHERE plan_id=? ORDER BY position""", (plan_id,)).fetchall()
            return {**dict(row), "steps": [str(step[0]) for step in steps]}

    def list_work_plans(self, goal_id: int | None = None) -> list[dict[str, object]]:
        self.require_permission("company:manage")
        if goal_id is not None:
            goal_id = self._plan_id(goal_id, "목표")
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            query = """SELECT p.id,p.goal_id,g.title AS goal_title,p.title,p.description,p.status,
                        COUNT(s.id) AS steps_count FROM company_work_plans p
                        JOIN company_goals g ON g.id=p.goal_id
                        LEFT JOIN company_work_plan_steps s ON s.plan_id=p.id"""
            params = () if goal_id is None else (goal_id,)
            if goal_id is not None:
                query += " WHERE p.goal_id=?"
            query += " GROUP BY p.id ORDER BY p.id"
            return [dict(row) for row in con.execute(query, params)]

    def delete_work_plan(self, plan_id: int) -> None:
        self.require_permission("company:manage")
        plan_id = self._plan_id(plan_id)
        with self._connect() as con:
            try:
                cursor = con.execute("DELETE FROM company_work_plans WHERE id=?", (plan_id,))
            except sqlite3.IntegrityError as exc:
                raise ValueError("연결된 업무가 있으므로 계획을 삭제할 수 없습니다. 업무 연결을 먼저 해제하세요.") from exc
            if cursor.rowcount != 1:
                raise ValueError("선택한 업무 계획을 찾을 수 없습니다.")

    # Stage 25 — owner-defined priority, not an automated AI scheduler.
    TASK_PRIORITIES = ("low", "normal", "high", "urgent")
    PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}

    def set_task_priority(self, task_id: int, priority: str) -> bool:
        """Atomically save a manual priority change and immutable event.

        Returns False for a no-op. Old tasks without a priority row are normal.
        Priority has no effect on task status, assignment, or AI execution.
        """
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        if not isinstance(priority, str) or priority not in self.TASK_PRIORITIES:
            raise ValueError("올바르지 않은 업무 우선순위입니다.")
        with self._connect() as con:
            self._task_row(con, task_id)
            existing = con.execute("SELECT priority FROM company_task_priorities WHERE task_id=?", (task_id,)).fetchone()
            previous = existing[0] if existing else "normal"
            if previous == priority:
                return False
            con.execute("""INSERT INTO company_task_priorities(task_id,priority) VALUES(?,?)
                ON CONFLICT(task_id) DO UPDATE SET priority=excluded.priority,updated_at=CURRENT_TIMESTAMP""",
                (task_id, priority))
            con.execute("""INSERT INTO company_task_priority_events(task_id,old_priority,new_priority)
                VALUES(?,?,?)""", (task_id, previous, priority))
        return True

    def list_task_priority_events(self, task_id: int) -> list[dict[str, object]]:
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            self._task_row(con, task_id)
            return [dict(row) for row in con.execute("""SELECT id,old_priority,new_priority,changed_at
                FROM company_task_priority_events WHERE task_id=? ORDER BY id""", (task_id,))]

    # Stage 23 — owner-only local task records. No AI invocation or scheduling.
    TASK_TRANSITIONS = {
        "todo": frozenset({"in_progress", "blocked", "cancelled"}),
        "in_progress": frozenset({"blocked", "done", "cancelled"}),
        "blocked": frozenset({"todo", "in_progress", "cancelled"}),
        "done": frozenset({"todo"}),  # explicit owner reopen
        "cancelled": frozenset({"todo"}),
    }

    @classmethod
    def _task_values(cls, title: str, description: str, plan_id: int | None) -> tuple[str, str, int | None]:
        heading = cls._validated_text(title, "업무 제목", 120, required=True)
        detail = cls._validated_text(description, "업무 설명", 1000)
        if plan_id is not None:
            cls._plan_id(plan_id)
        return heading, detail, plan_id

    @staticmethod
    def _task_row(con: sqlite3.Connection, task_id: int):
        row = con.execute("SELECT id,plan_id,title,description,status,created_at,updated_at,completed_at "
                          "FROM company_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("선택한 업무를 찾을 수 없습니다.")
        return row

    def add_task(self, title: str, description: str = "", plan_id: int | None = None) -> int:
        """Create a new *unassigned* todo record; never start an agent or process."""
        self.require_permission("company:manage")
        heading, detail, plan_id = self._task_values(title, description, plan_id)
        with self._connect() as con:
            if plan_id is not None and con.execute("SELECT 1 FROM company_work_plans WHERE id=?", (plan_id,)).fetchone() is None:
                raise ValueError("연결할 업무 계획을 찾을 수 없습니다.")
            task_id = int(con.execute("INSERT INTO company_tasks(plan_id,title,description) VALUES(?,?,?)",
                                      (plan_id, heading, detail)).lastrowid)
            con.execute("INSERT INTO company_task_status_events(task_id,old_status,new_status) VALUES(?,NULL,'todo')", (task_id,))
        return task_id

    def read_task(self, task_id: int) -> dict[str, object]:
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            task = dict(self._task_row(con, task_id))
            row = con.execute("SELECT priority FROM company_task_priorities WHERE task_id=?", (task_id,)).fetchone()
            task["priority"] = row[0] if row else "normal"
            return task

    def list_tasks(self, plan_id: int | None = None) -> list[dict[str, object]]:
        self.require_permission("company:manage")
        if plan_id is not None:
            self._plan_id(plan_id)
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            sql = """SELECT t.id,t.plan_id,p.title AS plan_title,t.title,t.description,t.status,
                     t.created_at,t.updated_at,t.completed_at,
                     COALESCE(pr.priority,'normal') AS priority FROM company_tasks t
                     LEFT JOIN company_work_plans p ON p.id=t.plan_id
                     LEFT JOIN company_task_priorities pr ON pr.task_id=t.id"""
            args = () if plan_id is None else (plan_id,)
            if plan_id is not None:
                sql += " WHERE t.plan_id=?"
            # Prioritize open work; finished/cancelled records follow in ID order.
            sql += """ ORDER BY CASE WHEN t.status IN ('done','cancelled') THEN 1 ELSE 0 END,
                CASE WHEN t.status IN ('done','cancelled') THEN 0 ELSE
                    CASE COALESCE(pr.priority,'normal')
                        WHEN 'urgent' THEN 0 WHEN 'high' THEN 1
                        WHEN 'normal' THEN 2 ELSE 3 END END, t.id"""
            return [dict(row) for row in con.execute(sql,args)]

    def update_task(self, task_id: int, title: str, description: str = "",
                    plan_id: int | None = None) -> None:
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        heading, detail, plan_id = self._task_values(title, description, plan_id)
        with self._connect() as con:
            row = self._task_row(con, task_id)
            if self._task_is_running(con, task_id):
                raise ValueError("로컬 AI 실행 중인 업무는 수정할 수 없습니다.")
            if row[4] in ("done", "cancelled"):
                raise ValueError("완료·취소된 업무는 재개 상태로 전환한 뒤 수정하세요.")
            if plan_id is not None and con.execute("SELECT 1 FROM company_work_plans WHERE id=?",(plan_id,)).fetchone() is None:
                raise ValueError("연결할 업무 계획을 찾을 수 없습니다.")
            con.execute("""UPDATE company_tasks SET plan_id=?,title=?,description=?,updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""", (plan_id,heading,detail,task_id))

    def set_task_status(self, task_id: int, new_status: str) -> None:
        """Explicit owner transition, atomically saved with immutable status event."""
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        if not isinstance(new_status, str) or new_status not in self.TASK_TRANSITIONS:
            raise ValueError("올바르지 않은 업무 상태입니다.")
        with self._connect() as con:
            # Serialize dependency checks and status writes across GUI/processes.
            con.execute("BEGIN IMMEDIATE")
            old_status = str(self._task_row(con, task_id)[4])
            if self._task_is_running(con, task_id):
                raise ValueError("로컬 AI 실행 중에는 업무 상태를 변경할 수 없습니다.")
            if new_status not in self.TASK_TRANSITIONS[old_status]:
                raise ValueError(f"허용되지 않은 상태 변경: {old_status} → {new_status}")
            if new_status == 'done':
                # GUI·일반 API를 통한 수동 완료도 동일한 협업 증빙을 검사.
                from desktop.company_department_progress import assert_collaboration_completion
                assert_collaboration_completion(con, task_id)
            if new_status in ("in_progress", "done"):
                pending = self._pending_prerequisites(con, task_id)
                if pending:
                    raise ValueError(f"선행 업무가 완료되지 않았습니다: {', '.join(map(str,pending))}")
            if old_status == "done" and new_status == "todo":
                # Reopening a completed prerequisite must not silently invalidate
                # work already started or completed by its dependents.
                active = [r[0] for r in con.execute("""
                    SELECT d.task_id FROM company_task_dependencies d
                    JOIN company_tasks t ON t.id=d.task_id
                    WHERE d.prerequisite_id=? AND t.status IN ('in_progress','done')
                    ORDER BY d.task_id""", (task_id,))]
                if active:
                    raise ValueError(f"진행·완료된 후속 업무가 있어 선행 업무를 재개할 수 없습니다: {active}")
            con.execute("""UPDATE company_tasks SET status=?,updated_at=CURRENT_TIMESTAMP,
                           completed_at=CASE WHEN ?='done' THEN CURRENT_TIMESTAMP ELSE NULL END
                           WHERE id=?""", (new_status,new_status,task_id))
            con.execute("""INSERT INTO company_task_status_events(task_id,old_status,new_status)
                           VALUES(?,?,?)""", (task_id,old_status,new_status))

    def list_task_status_events(self, task_id: int) -> list[dict[str, object]]:
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            self._task_row(con, task_id)
            return [dict(row) for row in con.execute("""SELECT id,old_status,new_status,changed_at
                     FROM company_task_status_events WHERE task_id=? ORDER BY id""",(task_id,))]

    def delete_task(self, task_id: int) -> None:
        """Owner-only explicit deletion; running work is never silently removed."""
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        with self._connect() as con:
            row = self._task_row(con,task_id)
            if con.execute("SELECT 1 FROM company_task_breakdown_items WHERE task_id=?", (task_id,)).fetchone():
                raise ValueError('승인된 세부 계획 업무는 감사 기록 보호를 위해 삭제할 수 없습니다.')
            if con.execute("SELECT 1 FROM company_task_proposals WHERE approved_task_id=?", (task_id,)).fetchone():
                raise ValueError('자동 제안에서 승인된 업무는 감사 기록 보호를 위해 삭제할 수 없습니다.')
            if con.execute("SELECT 1 FROM company_chief_task_orders WHERE task_id=?",(task_id,)).fetchone():
                raise ValueError('승인된 총괄 AI 지시가 있는 업무는 감사 기록 보호를 위해 삭제할 수 없습니다.')
            if con.execute("SELECT 1 FROM company_task_runs WHERE task_id=?", (task_id,)).fetchone():
                raise ValueError("AI 실행 이력이 있는 업무는 감사 기록 보호를 위해 삭제할 수 없습니다.")
            if row[4] in ("in_progress", "done"):
                raise ValueError("진행 중·완료된 업무는 삭제할 수 없습니다. 취소 또는 재개 후 처리하세요.")
            if con.execute("SELECT 1 FROM company_task_dependencies WHERE prerequisite_id=?",
                           (task_id,)).fetchone():
                raise ValueError("후속 업무가 연결된 선행 업무는 삭제할 수 없습니다. 의존성을 먼저 해제하세요.")
            con.execute("DELETE FROM company_tasks WHERE id=?",(task_id,))


    # Stage 30: all APIs require the authenticated owner; a chief suggestion
    # becomes a dispatchable instruction only after explicit owner approval.
    @staticmethod
    def _chief_task_fingerprint(title: str, description: str) -> str:
        return hashlib.sha256((title+'\0'+description).encode('utf-8')).hexdigest()

    def approve_chief_task_order(self, task_id: int, instruction: str) -> int:
        self.require_permission('company:manage')
        self.require_permission('agents:manage')
        task_id=self._plan_id(task_id,'업무')
        instruction=self._validated_text(instruction,'총괄 AI 지시',600,required=True)
        if '\x00' in instruction:
            raise ValueError('총괄 AI 지시에 NUL 문자는 사용할 수 없습니다.')
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            task=self._task_row(con,task_id)
            if task[4]!='todo':
                raise ValueError('할 일 상태의 업무만 지시를 승인할 수 있습니다.')
            if con.execute('SELECT 1 FROM company_task_runs WHERE task_id=?',(task_id,)).fetchone():
                raise ValueError('이미 실행 이력이 있는 업무에는 지시를 추가할 수 없습니다.')
            chief=con.execute("""SELECT e.id,e.lifecycle,em.model_id FROM ai_reporting_lines r
                JOIN ai_employee_profiles e ON e.id=r.employee_id
                LEFT JOIN ai_employee_model_assignments em ON em.employee_id=e.id
                WHERE r.tier='ceo'""").fetchone()
            if chief is None or chief[1]!='draft' or chief[2] is None:
                raise ValueError('활성 총괄 AI와 로컬 모델 배정이 필요합니다.')
            worker=con.execute("""SELECT e.id,e.lifecycle FROM company_task_assignments a
                JOIN ai_employee_profiles e ON e.id=a.employee_id
                LEFT JOIN ai_reporting_lines r ON r.employee_id=e.id
                WHERE a.task_id=? AND (r.tier IS NULL OR r.tier='staff')""",
                (task_id,)).fetchone()
            if worker is None or worker[1]!='draft':
                raise ValueError('활성 담당 AI 직원 배정이 필요합니다.')
            if con.execute('SELECT 1 FROM company_chief_task_orders WHERE task_id=?',(task_id,)).fetchone():
                raise ValueError('이미 승인된 지시가 있습니다. 중복 승인은 허용하지 않습니다.')
            try:
                return int(con.execute("""INSERT INTO company_chief_task_orders
                    (task_id,chief_employee_id,worker_employee_id,instruction,task_fingerprint)
                    VALUES(?,?,?,?,?)""",(task_id,chief[0],worker[0],instruction,
                    self._chief_task_fingerprint(str(task[2]),str(task[3])))).lastrowid)
            except sqlite3.IntegrityError as exc:
                raise ValueError('총괄 AI 지시 저장 중 연결된 데이터가 변경됐습니다.') from exc

    def read_chief_task_order(self, task_id: int) -> dict[str, object] | None:
        self.require_permission('company:manage')
        task_id=self._plan_id(task_id,'업무')
        with self._connect() as con:
            con.row_factory=sqlite3.Row
            self._task_row(con,task_id)
            row=con.execute('SELECT * FROM company_chief_task_orders WHERE task_id=?',(task_id,)).fetchone()
            return dict(row) if row else None

    def chief_task_report_context(self, artifact_id: int) -> dict[str, object]:
        """Read the exact approved order and owner-saved worker result; no model call."""
        self.require_permission('company:manage')
        self.require_permission('agents:manage')
        artifact_id=self._plan_id(artifact_id,'결과물')
        with self._connect() as con:
            con.row_factory=sqlite3.Row
            row=con.execute("""SELECT o.id AS order_id,o.task_id,o.chief_employee_id,
                o.instruction,a.id AS artifact_id,a.body,a.sha256,a.review_status,
                r.status AS run_status
                FROM company_task_artifacts a
                JOIN company_chief_task_dispatches d ON d.run_id=a.run_id
                JOIN company_chief_task_orders o ON o.id=d.order_id
                JOIN company_task_runs r ON r.id=a.run_id
                WHERE a.id=?""",(artifact_id,)).fetchone()
            if row is None or row['run_status']!='success':
                raise ValueError('승인된 총괄 AI 지시에서 성공한 실행의 저장된 결과물만 회수할 수 있습니다.')
            return dict(row)

    def save_chief_task_report(self, artifact_id: int, body: str, *,
                               lease_token: str | None = None,
                               model_call_id: int | None = None) -> int:
        """Save owner-visible review, fencing stale automatic model invocations.

        A manual owner save may omit a token; an in-flight model must supply
        its own durable lease token, checked in the SAME SQLite transaction.
        """
        self.require_permission('company:manage')
        self.require_permission('agents:manage')
        artifact_id=self._plan_id(artifact_id,'결과물')
        if not isinstance(body,str) or not body.strip() or len(body)>10000 or '\x00' in body:
            raise ValueError('총괄 AI 회수 의견은 1~10000자의 텍스트여야 합니다.')
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute("""SELECT o.id,o.chief_employee_id FROM company_task_artifacts a
                JOIN company_chief_task_dispatches d ON d.run_id=a.run_id
                JOIN company_chief_task_orders o ON o.id=d.order_id
                JOIN company_task_runs r ON r.id=a.run_id
                WHERE a.id=? AND r.status='success'""",(artifact_id,)).fetchone()
            if row is None:
                raise ValueError('승인된 지시와 연결된 성공 결과물이 필요합니다.')
            has_lease_table = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='aiwack_chief_review_leases'").fetchone() is not None
            if lease_token is None and has_lease_table and con.execute(
                    'SELECT 1 FROM aiwack_chief_review_leases WHERE artifact_id=?',
                    (artifact_id,)).fetchone():
                raise PermissionError('진행 중인 총괄 AI 검토가 있어 수동 보고서 저장을 차단합니다.')
            if lease_token is not None:
                from desktop.stage87_90_management import stopped as emergency_stopped
                if emergency_stopped(con):
                    raise PermissionError('비상 정지 이후 총괄 AI 모델 응답은 저장하지 않습니다.')
                if (not has_lease_table or type(lease_token) is not str
                        or len(lease_token) != 32 or not con.execute('''SELECT 1 FROM aiwack_chief_review_leases
                            WHERE artifact_id=? AND owner_token=?''',
                            (artifact_id, lease_token)).fetchone()):
                    raise PermissionError('총괄 AI 검토 잠금이 변경됐습니다. 이전 모델 응답을 저장하지 않습니다.')
            if con.execute('SELECT 1 FROM company_chief_task_reports WHERE order_id=? OR artifact_id=?',
                           (row[0],artifact_id)).fetchone():
                raise ValueError('이미 저장된 총괄 AI 회수 보고서는 변경할 수 없습니다.')
            if model_call_id is not None:
                if type(model_call_id) is not int or model_call_id <= 0:
                    raise ValueError('총괄 실제 모델 호출 번호가 올바르지 않습니다.')
                call=con.execute("""SELECT h.employee_id,h.model_id,h.status,h.output_chars,
                       m.model_id FROM ai_model_call_history h
                       LEFT JOIN ai_employee_model_assignments m ON m.employee_id=h.employee_id
                       WHERE h.id=?""",(model_call_id,)).fetchone()
                if (not call or int(call[0])!=int(row[1]) or
                        call[1] is None or call[1]!=call[4] or
                        call[2]!='success' or int(call[3])<=0):
                    raise ValueError('총괄 실제 모델 호출 감사가 승인 지시와 일치하지 않습니다.')
            # Persisted reports may not bypass owner-approved head handoff.
            from desktop.company_department_head_review import _verified_in_tx
            if con.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                AND name='aiwack_chief_department_proposal_decisions'""").fetchone():
                needs_head=con.execute("""SELECT 1 FROM
                    aiwack_chief_department_proposal_decisions d
                    JOIN company_task_artifacts a ON a.task_id=d.task_id
                    WHERE a.id=? AND d.decision='approved'""",
                    (artifact_id,)).fetchone()
                if needs_head:
                    proof=_verified_in_tx(con,artifact_id)
                    if not proof or proof['decision']!='forward' or proof['verdict']!='accept':
                        raise PermissionError('실제 부서장 GGUF 검토·관리자 개별 인계 승인 필요')
            digest=hashlib.sha256(body.encode('utf-8')).hexdigest()
            return int(con.execute("""INSERT INTO company_chief_task_reports
                (order_id,artifact_id,chief_employee_id,body,sha256,chief_model_call_id)
                VALUES(?,?,?,?,?,?)""",
                (row[0],artifact_id,row[1],body,digest,model_call_id)).lastrowid)

    def read_chief_task_report(self, report_id: int) -> dict[str, object]:
        self.require_permission('company:manage')
        report_id=self._plan_id(report_id,'총괄 AI 보고서')
        with self._connect() as con:
            con.row_factory=sqlite3.Row
            row=con.execute('SELECT * FROM company_chief_task_reports WHERE id=?',(report_id,)).fetchone()
            if row is None:
                raise ValueError('보고서를 찾을 수 없습니다.')
            return dict(row)

    def find_chief_task_report(self, artifact_id: int) -> dict[str, object] | None:
        self.require_permission('company:manage')
        artifact_id=self._plan_id(artifact_id,'결과물')
        with self._connect() as con:
            con.row_factory=sqlite3.Row
            row=con.execute('SELECT * FROM company_chief_task_reports WHERE artifact_id=?',
                            (artifact_id,)).fetchone()
            return dict(row) if row else None

    def review_chief_task_report(self, report_id: int, decision: str, note: str = '') -> None:
        self.require_permission('company:manage')
        report_id=self._plan_id(report_id,'총괄 AI 보고서')
        if decision not in ('accepted','rejected'):
            raise ValueError('승인 또는 반려 중 하나를 선택하세요.')
        note=self._validated_text(note,'관리자 검토 의견',1000)
        with self._connect() as con:
            changed=con.execute("""UPDATE company_chief_task_reports
                SET owner_decision=?,owner_note=?,reviewed_at=CURRENT_TIMESTAMP
                WHERE id=? AND owner_decision='pending'""",(decision,note,report_id)).rowcount
            if changed!=1:
                raise ValueError('보고서가 없거나 이미 검토되었습니다.')
            # Neither a chief report nor owner review silently marks task done.

    # Stage 29: parallel runs require distinct tasks and employees, capped at two.
    @staticmethod
    def _task_is_running(con: sqlite3.Connection, task_id: int) -> bool:
        return con.execute("SELECT 1 FROM company_task_runs WHERE task_id=? AND status='running'",
                           (task_id,)).fetchone() is not None

    @staticmethod
    def _task_prompt(title: str, description: str) -> str:
        # No external tools, OS commands or autonomous side effects are available.
        # The task description is untrusted model input, not an OS instruction.
        prompt = ("당신은 오프라인 AI 직원입니다. 아래 업무에 대해 텍스트 초안을 작성하세요. "
                  "외부 접속, 파일 변경, 결제, 실제 실행을 수행하지 마세요. "
                  "최종 승인과 완료 처리는 관리자가 수행합니다.\n"
                  f"업무 제목: {title}\n업무 설명: {description or '(없음)'}")
        if len(prompt) > 3000:
            raise ValueError("업무 설명이 모델 입력 제한(3000자)을 초과했습니다.")
        return prompt

    def begin_task_execution(self, task_id: int):
        """Atomically reserve one of at most two independent task runs.

        Returns (run_id, frozen_model_config, prompt). Nothing executes here.
        This deliberately does not authorize an AI tool, payment or network call.
        """
        self.require_permission("company:manage")
        self.require_permission("agents:manage")
        task_id = self._plan_id(task_id, "업무")
        from desktop.model_runtime import ModelConfig
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            from desktop.stage87_90_management import stopped as emergency_stopped
            if emergency_stopped(con):
                raise PermissionError("비상 정지 상태에서는 직원 AI 실행을 시작할 수 없습니다.")
            task = self._task_row(con, task_id)
            if task[4] != "todo":
                raise ValueError("할 일(todo) 상태의 업무만 AI 실행을 시작할 수 있습니다.")
            # 모든 직원 실행 진입점에서 부서 협업의 실제 승인 선행 실증 확인.
            from desktop.company_department_progress import assert_collaboration_prerequisites
            assert_collaboration_prerequisites(con, task_id)
            pending = self._pending_prerequisites(con, task_id)
            if pending:
                raise ValueError(f"미완료 선행 업무: {', '.join(map(str, pending))}")
            from desktop.company_wide_campaign import assert_handoff_ready
            handoff_proof = assert_handoff_ready(con,task_id)
            running_count = con.execute("SELECT COUNT(*) FROM company_task_runs WHERE status='running'").fetchone()[0]
            if running_count >= MAX_PARALLEL_TASK_RUNS:
                raise ValueError("동시 실행 한도(2개)에 도달했습니다. 실행을 종료하거나 중단 기록을 복구하세요.")
            row = con.execute("""SELECT e.id,e.lifecycle,e.department_id,e.job_id,
                       m.id,m.name,m.backend,m.executable_path,m.model_path,m.max_tokens
                FROM company_task_assignments a
                JOIN ai_employee_profiles e ON e.id=a.employee_id
                JOIN ai_employee_model_assignments em ON em.employee_id=e.id
                JOIN ai_local_models m ON m.id=em.model_id
                LEFT JOIN ai_reporting_lines r ON r.employee_id=e.id
                WHERE a.task_id=? AND (r.tier IS NULL OR r.tier='staff' OR
                    (r.tier='department_head' AND EXISTS (
                      SELECT 1 FROM aiwack_wide_campaign_steps ws
                      JOIN aiwack_wide_campaigns wp ON wp.id=ws.campaign_id AND wp.state='approved'
                      WHERE ws.task_id=a.task_id AND ws.employee_id=e.id
                        AND ws.role='department_head')))""",
                (task_id,)).fetchone()
            if row is None or row[1] != 'draft':
                raise ValueError("활성 담당 AI 직원과 로컬 모델 배정이 모두 필요합니다.")
            employee_id,_,employee_dept,employee_job,model_id,name,backend,exe,model_path,tokens = row
            if con.execute("SELECT 1 FROM company_task_runs WHERE employee_id=? AND status='running'",
                           (employee_id,)).fetchone():
                raise ValueError("같은 AI 직원은 두 업무를 동시에 실행할 수 없습니다.")
            requirements = con.execute("SELECT department_id,job_id FROM company_task_routing WHERE task_id=?",
                                       (task_id,)).fetchone()
            if requirements and ((requirements[0] is not None and requirements[0] != employee_dept)
                                 or (requirements[1] is not None and requirements[1] != employee_job)):
                raise ValueError("담당 직원의 부서·직무가 업무 배정 조건과 일치하지 않습니다.")
            prompt = self._task_prompt(str(task[2]), str(task[3]))
            order = con.execute("""SELECT id,chief_employee_id,worker_employee_id,instruction,
                       task_fingerprint FROM company_chief_task_orders WHERE task_id=?""",
                       (task_id,)).fetchone()
            if order is not None:
                order_id,chief_id,worker_id,instruction,fingerprint = order
                if worker_id != employee_id:
                    raise ValueError('총괄 AI 지시 승인 후 담당 직원이 변경됐습니다. 실행할 수 없습니다.')
                if fingerprint != self._chief_task_fingerprint(str(task[2]),str(task[3])):
                    raise ValueError('총괄 AI 지시 승인 후 업무 내용이 변경됐습니다. 실행할 수 없습니다.')
                if con.execute('SELECT 1 FROM company_chief_task_dispatches WHERE order_id=?',
                               (order_id,)).fetchone():
                    raise ValueError('총괄 AI 지시는 이미 실행됐습니다. 중복 실행을 막습니다.')
                chief = con.execute("""SELECT e.lifecycle,em.model_id FROM ai_reporting_lines r
                    JOIN ai_employee_profiles e ON e.id=r.employee_id
                    LEFT JOIN ai_employee_model_assignments em ON em.employee_id=e.id
                    WHERE r.tier='ceo' AND e.id=?""",(chief_id,)).fetchone()
                if chief is None or chief[0]!='draft' or chief[1] is None:
                    raise ValueError('총괄 AI가 변경되었거나 비활성화되어 지시를 실행할 수 없습니다.')
                prompt = ("당신은 오프라인 AI 직원입니다. 다음은 관리자가 승인한 총괄 AI의 텍스트 지시입니다. "
                          "파일 변경·외부 접속·결제·도구 실행을 하지 말고 텍스트 초안만 답하세요. "
                          "업무 완료와 결과 검수는 관리자가 결정합니다.\n"
                          f"업무 제목: {task[2]}\n업무 설명: {task[3]}\n승인된 지시: {instruction}")
                if len(prompt)>3000:
                    raise ValueError('승인된 지시가 로컬 모델 입력 한도를 초과했습니다.')
            # An earlier worker's result is context, never a new instruction.
            from desktop.company_dependency_evidence_seal import assert_current_in_tx
            # Recheck in the original BEGIN IMMEDIATE model-run transaction:
            # a queue preview cannot authorize a changed predecessor result.
            assert_current_in_tx(con,task_id)
            from desktop.company_handoffs import dependency_context
            dependency_text=dependency_context(con,task_id,budget=min(700,max(0,3000-len(prompt))))
            if handoff_proof is not None:
                expected=f"[업무 #{handoff_proof['previous_task_id']}·승인 결과물 #{handoff_proof['artifact_id']}]"
                if expected not in dependency_text:
                    raise ValueError('검증된 선행 부서 결과가 직원 모델 입력 범위에 포함되지 않았습니다.')
            prompt+=dependency_text
            from desktop.company_handoffs import curated_company_context
            prompt+=curated_company_context(con,str(task[2]),
                                             budget=min(450,max(0,3000-len(prompt))))
            # Only owner-approved, provenance-verified cross-department GGUF
            # opinions may enter the real employee's text prompt. They never
            # overwrite chief orders, grant tools, or bypass task prerequisites.
            from desktop.company_peer_context import approved_context
            prompt+=approved_context(
                con,task_id,employee_id,
                budget=min(450,max(0,3000-len(prompt))))
            config = ModelConfig(str(name),str(backend),str(exe),str(model_path),int(tokens))
            # Record the same local invocation in the existing model call audit.
            call_id = int(con.execute("""INSERT INTO ai_model_call_history
                (employee_id,model_id,model_name,prompt_chars) VALUES(?,?,?,?)""",
                (employee_id,model_id,name,len(prompt))).lastrowid)
            run_id = int(con.execute("""INSERT INTO company_task_runs
                (task_id,employee_id,model_id,model_name,model_call_id,prompt_chars)
                VALUES(?,?,?,?,?,?)""",
                (task_id,employee_id,model_id,name,call_id,len(prompt))).lastrowid)
            if order is not None:
                con.execute("INSERT INTO company_chief_task_dispatches(order_id,run_id) VALUES(?,?)",
                            (order[0],run_id))
            con.execute("""UPDATE company_tasks SET status='in_progress',updated_at=CURRENT_TIMESTAMP
                WHERE id=?""", (task_id,))
            con.execute("""INSERT INTO company_task_status_events(task_id,old_status,new_status)
                VALUES(?,'todo','in_progress')""", (task_id,))
        return run_id,config,prompt

    def finish_task_execution(self, run_id: int, status: str, *, output_chars: int = 0,
                              duration_ms: int = 0, error_kind: str = "") -> None:
        """Finalize task and model audits together; never mark the task done."""
        self.require_permission("company:manage")
        self.require_permission("agents:manage")
        if type(run_id) is not int or run_id < 1:
            raise ValueError("실행 ID가 올바르지 않습니다.")
        if status not in {'success','failure','cancelled','timeout','interrupted'}:
            raise ValueError("실행 결과 코드가 올바르지 않습니다.")
        if type(output_chars) is not int or not 0 <= output_chars <= 20000:
            raise ValueError("출력 길이가 올바르지 않습니다.")
        if type(duration_ms) is not int or duration_ms < 0:
            raise ValueError("소요 시간이 올바르지 않습니다.")
        if error_kind not in {'','ValueError','RuntimeError','OSError','TimeoutError','InterruptedError'}:
            raise ValueError("오류 종류가 올바르지 않습니다.")
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute("SELECT task_id,model_call_id FROM company_task_runs WHERE id=? AND status='running'",
                              (run_id,)).fetchone()
            if row is None:
                raise ValueError("실행 기록이 없거나 이미 종료됐습니다.")
            task_id,call_id=row
            from desktop.stage87_90_management import stopped as emergency_stopped
            rejected_late_success = status == 'success' and emergency_stopped(con)
            if rejected_late_success:
                status, output_chars, error_kind = 'failure', 0, 'RuntimeError'
            model_status = 'failure' if status == 'interrupted' else status
            changed = con.execute("""UPDATE ai_model_call_history SET status=?,output_chars=?,duration_ms=?,
                error_kind=?,completed_at=CURRENT_TIMESTAMP WHERE id=? AND status='running'""",
                (model_status,output_chars,duration_ms,error_kind,call_id)).rowcount
            if changed != 1:
                raise ValueError("모델 호출 기록이 이미 종료됐습니다.")
            con.execute("""UPDATE company_task_runs SET status=?,output_chars=?,duration_ms=?,
                error_kind=?,completed_at=CURRENT_TIMESTAMP WHERE id=? AND status='running'""",
                (status,output_chars,duration_ms,error_kind,run_id))
            # Failed/cancelled runs are blocked for explicit owner review/retry.
            # Success remains in_progress until human review in later stages.
            if status != 'success':
                con.execute("""UPDATE company_tasks SET status='blocked',updated_at=CURRENT_TIMESTAMP
                    WHERE id=? AND status='in_progress'""", (task_id,))
                con.execute("""INSERT INTO company_task_status_events(task_id,old_status,new_status)
                    VALUES(?,'in_progress','blocked')""", (task_id,))
        if rejected_late_success:
            raise PermissionError('비상 정지로 완료된 직원 실행 응답을 폐기했습니다.')

    def recover_interrupted_task_run(self, run_id: int) -> None:
        """Owner explicitly closes a stale running row after app/process crash.

        Do not use this while a live model subprocess may still be running.
        """
        self.finish_task_execution(run_id,'interrupted',error_kind='RuntimeError')

    def list_task_runs(self, task_id: int | None = None, *, limit: int = 100) -> list[dict[str, object]]:
        self.require_permission('company:manage')
        if task_id is not None:
            task_id=self._plan_id(task_id,'업무')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('조회 건수는 1~200이어야 합니다.')
        with self._connect() as con:
            con.row_factory=sqlite3.Row
            if task_id is not None:
                self._task_row(con,task_id)
            query="""SELECT id,task_id,employee_id,model_id,model_name,model_call_id,status,
                      prompt_chars,output_chars,duration_ms,error_kind,started_at,completed_at
                      FROM company_task_runs"""
            args=() if task_id is None else (task_id,)
            if task_id is not None:
                query+=' WHERE task_id=?'
            query+=' ORDER BY id DESC LIMIT ?'
            return [dict(row) for row in con.execute(query,args+(limit,))]

    # Stage 28: owner explicitly persists text from a successful local run.
    # Artifact content is plaintext in the user's SQLite DB (NOT encrypted).
    def save_task_artifact(self, task_id: int, run_id: int, title: str, body: str) -> int:
        self.require_permission('company:manage')
        task_id = self._plan_id(task_id, '업무')
        run_id = self._plan_id(run_id, '실행')
        title = self._validated_text(title, '결과물 제목', 120, required=True)
        if not isinstance(body, str) or not body.strip() or len(body) > 20000 or '\x00' in body:
            raise ValueError('결과물 본문은 1~20000자의 텍스트여야 합니다.')
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            self._task_row(con, task_id)
            from desktop.stage87_90_management import stopped as emergency_stopped
            if emergency_stopped(con):
                raise PermissionError('비상 정지 상태에서는 새 AI 결과물을 저장하지 않습니다.')
            row = con.execute('SELECT task_id,status FROM company_task_runs WHERE id=?', (run_id,)).fetchone()
            if row is None or row[0] != task_id or row[1] != 'success':
                raise ValueError('선택한 업무에서 성공한 로컬 AI 실행 결과만 저장할 수 있습니다.')
            if con.execute('SELECT 1 FROM company_task_artifacts WHERE run_id=?', (run_id,)).fetchone():
                raise ValueError('이 실행 결과는 이미 저장되었습니다. 기존 결과물은 변경할 수 없습니다.')
            return int(con.execute("""INSERT INTO company_task_artifacts
                (task_id,run_id,title,body,sha256) VALUES(?,?,?,?,?)""",
                (task_id,run_id,title,body,digest)).lastrowid)

    def list_task_artifacts(self, task_id: int | None = None) -> list[dict[str, object]]:
        self.require_permission('company:manage')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            if task_id is not None:
                self._task_row(con,self._plan_id(task_id,'업무'))
            where = '' if task_id is None else ' WHERE task_id=?'
            args = () if task_id is None else (task_id,)
            # Full body is available via read_task_artifact, not list previews.
            return [dict(row) for row in con.execute("""SELECT id,task_id,run_id,title,sha256,
                review_status,created_at,reviewed_at FROM company_task_artifacts"""+where+
                ' ORDER BY id DESC',args)]

    def read_task_artifact(self, artifact_id: int) -> dict[str, object]:
        self.require_permission('company:manage')
        artifact_id = self._plan_id(artifact_id,'결과물')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            row = con.execute('SELECT * FROM company_task_artifacts WHERE id=?',(artifact_id,)).fetchone()
            if row is None:
                raise ValueError('선택한 결과물을 찾을 수 없습니다.')
            return dict(row)

    def review_task_artifact(self, artifact_id: int, decision: str, note: str = '') -> None:
        self.require_permission('company:manage')
        artifact_id = self._plan_id(artifact_id,'결과물')
        if decision not in ('approved','changes_requested','rejected') or type(decision) is not str:
            raise ValueError('검수 결과는 승인·수정 요청·반려 중 하나여야 합니다.')
        note = self._validated_text(note,'검수 의견',1000)
        if decision != 'approved' and not note:
            raise ValueError('수정 요청·반려에는 검수 의견이 필요합니다.')
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT review_status FROM company_task_artifacts WHERE id=?',
                              (artifact_id,)).fetchone()
            if row is None:
                raise ValueError('선택한 결과물을 찾을 수 없습니다.')
            if row[0] != 'pending':
                raise ValueError('이미 검수된 결과물은 재검수할 수 없습니다. 새 실행 결과를 저장하세요.')
            con.execute("""UPDATE company_task_artifacts SET review_status=?,reviewed_at=CURRENT_TIMESTAMP
                           WHERE id=?""",(decision,artifact_id))
            con.execute("""INSERT INTO company_task_artifact_reviews
                           (artifact_id,old_status,new_status,note) VALUES(?,?,?,?)""",
                        (artifact_id,'pending',decision,note))
            # Reviewing never silently marks the underlying task done.

    def list_task_artifact_reviews(self, artifact_id: int) -> list[dict[str, object]]:
        self.require_permission('company:manage')
        artifact_id = self._plan_id(artifact_id,'결과물')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            if not con.execute('SELECT 1 FROM company_task_artifacts WHERE id=?',(artifact_id,)).fetchone():
                raise ValueError('선택한 결과물을 찾을 수 없습니다.')
            return [dict(row) for row in con.execute("""SELECT id,artifact_id,old_status,new_status,note,reviewed_at
                    FROM company_task_artifact_reviews WHERE artifact_id=? ORDER BY id""",(artifact_id,))]

    # Stage 26: human-maintained prerequisite graph; no automatic task execution.
    @staticmethod
    def _pending_prerequisites(con: sqlite3.Connection, task_id: int) -> list[int]:
        return [int(row[0]) for row in con.execute("""
            SELECT d.prerequisite_id FROM company_task_dependencies d
            JOIN company_tasks t ON t.id=d.prerequisite_id
            WHERE d.task_id=? AND t.status!='done' ORDER BY d.prerequisite_id
        """, (task_id,))]

    def add_task_dependency(self, task_id: int, prerequisite_id: int) -> bool:
        """Add one prerequisite atomically; reject cycles, self-links and duplicates.

        Returns False if the exact edge already exists. An active/finished task
        must be returned to todo/blocked before changing its prerequisites.
        """
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "후속 업무")
        prerequisite_id = self._plan_id(prerequisite_id, "선행 업무")
        if task_id == prerequisite_id:
            raise ValueError("업무를 자기 자신의 선행 업무로 지정할 수 없습니다.")
        with self._connect() as con:
            # A competing writer must not add the opposite edge between cycle
            # detection and this INSERT (SQLite serializes IMMEDIATE writers).
            con.execute("BEGIN IMMEDIATE")
            downstream = self._task_row(con, task_id)
            self._task_row(con, prerequisite_id)
            if downstream[4] not in ("todo", "blocked"):
                raise ValueError("진행·완료·취소된 업무는 의존성을 추가할 수 없습니다.")
            if con.execute("""SELECT 1 FROM company_task_dependencies
                            WHERE task_id=? AND prerequisite_id=?""",
                           (task_id, prerequisite_id)).fetchone():
                return False
            # From proposed upstream, follow existing upstream edges. If we
            # can reach the downstream node, the new edge would close a cycle.
            cycle = con.execute("""
                WITH RECURSIVE ancestors(id) AS (
                    SELECT prerequisite_id FROM company_task_dependencies WHERE task_id=?
                    UNION
                    SELECT d.prerequisite_id FROM company_task_dependencies d
                    JOIN ancestors a ON d.task_id=a.id
                ) SELECT 1 FROM ancestors WHERE id=? LIMIT 1
            """, (prerequisite_id, task_id)).fetchone()
            if cycle:
                raise ValueError("순환 의존성은 등록할 수 없습니다.")
            con.execute("""INSERT INTO company_task_dependencies(task_id,prerequisite_id)
                           VALUES(?,?)""", (task_id, prerequisite_id))
            con.execute("""INSERT INTO company_task_dependency_events(task_id,prerequisite_id,action)
                           VALUES(?,?,'added')""", (task_id, prerequisite_id))
        return True

    def remove_task_dependency(self, task_id: int, prerequisite_id: int) -> bool:
        """Remove one edge, retaining its audit history. Returns False if absent."""
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "후속 업무")
        prerequisite_id = self._plan_id(prerequisite_id, "선행 업무")
        with self._connect() as con:
            self._task_row(con, task_id)
            self._task_row(con, prerequisite_id)
            deleted = con.execute("""DELETE FROM company_task_dependencies
                WHERE task_id=? AND prerequisite_id=?""", (task_id, prerequisite_id)).rowcount
            if not deleted:
                return False
            con.execute("""INSERT INTO company_task_dependency_events(task_id,prerequisite_id,action)
                           VALUES(?,?,'removed')""", (task_id, prerequisite_id))
        return True

    def list_task_dependencies(self, task_id: int) -> list[dict[str, object]]:
        """Direct prerequisites for a dependent task, with current readiness."""
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "후속 업무")
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            self._task_row(con, task_id)
            return [dict(row) for row in con.execute("""
                SELECT d.prerequisite_id, t.title, t.status,
                       CASE WHEN t.status='done' THEN 1 ELSE 0 END AS satisfied,
                       d.created_at FROM company_task_dependencies d
                JOIN company_tasks t ON t.id=d.prerequisite_id
                WHERE d.task_id=? ORDER BY d.prerequisite_id
            """, (task_id,))]

    def list_task_dependency_events(self, task_id: int) -> list[dict[str, object]]:
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "후속 업무")
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            self._task_row(con, task_id)
            return [dict(row) for row in con.execute("""
                SELECT id,prerequisite_id,action,changed_at
                FROM company_task_dependency_events WHERE task_id=? ORDER BY id
            """, (task_id,))]

    def task_dependency_readiness(self, task_id: int) -> dict[str, object]:
        """Read-only blocker summary; no state transition or AI execution."""
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        with self._connect() as con:
            self._task_row(con, task_id)
            pending = self._pending_prerequisites(con, task_id)
            total = con.execute("SELECT COUNT(*) FROM company_task_dependencies WHERE task_id=?",
                                (task_id,)).fetchone()[0]
            return {"ready": not pending, "pending_ids": pending, "total": total}

    # Stage 24: assign *metadata* to a matching stored AI profile; no AI worker runs.
    @staticmethod
    def _clear_task_assignment_in_tx(con: sqlite3.Connection, task_id: int, action: str, detail: str) -> bool:
        row = con.execute("SELECT employee_id FROM company_task_assignments WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            return False
        con.execute("DELETE FROM company_task_assignments WHERE task_id=?", (task_id,))
        con.execute("""INSERT INTO company_task_assignment_events(task_id,employee_id,action,detail)
                       VALUES(?,?,?,?)""", (task_id, row[0], action, detail))
        return True

    def save_task_requirements(self, task_id: int, department_id: int | None = None,
                               job_id: int | None = None) -> None:
        """Strictly match department/job; NULL means no restriction on that dimension."""
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        dept = self._validate_reference(department_id, "부서")
        job = self._validate_reference(job_id, "직무")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            task = self._task_row(con, task_id)
            if task[4] != "todo":
                raise ValueError("할 일 상태의 업무만 배정 조건을 변경할 수 있습니다.")
            if dept is not None and con.execute("SELECT 1 FROM company_departments WHERE id=?", (dept,)).fetchone() is None:
                raise ValueError("존재하지 않는 부서입니다.")
            if job is not None and con.execute("SELECT 1 FROM company_designations WHERE id=? AND kind='job'", (job,)).fetchone() is None:
                raise ValueError("존재하지 않거나 직무가 아닌 분류입니다.")
            current = con.execute("SELECT department_id,job_id FROM company_task_routing WHERE task_id=?", (task_id,)).fetchone()
            if current is not None and tuple(current) == (dept, job):
                return
            if current is None and (dept,job) == (None,None):
                return
            con.execute("""INSERT INTO company_task_routing(task_id,department_id,job_id) VALUES(?,?,?)
                           ON CONFLICT(task_id) DO UPDATE SET department_id=excluded.department_id,job_id=excluded.job_id""",
                        (task_id, dept, job))
            self._clear_task_assignment_in_tx(con,task_id,"requirements_changed", "업무의 부서/직무 조건 변경")

    def read_task_routing(self, task_id: int) -> dict[str, object]:
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        with self._connect() as con:
            self._task_row(con, task_id)
            row = con.execute("""SELECT r.department_id,r.job_id,a.employee_id,e.display_name,a.reason,a.assigned_at
                      FROM company_tasks t LEFT JOIN company_task_routing r ON r.task_id=t.id
                      LEFT JOIN company_task_assignments a ON a.task_id=t.id
                      LEFT JOIN ai_employee_profiles e ON e.id=a.employee_id WHERE t.id=?""", (task_id,)).fetchone()
        keys = ("department_id", "job_id", "employee_id", "employee_name", "reason", "assigned_at")
        return dict(zip(keys,row))

    def list_task_assignment_events(self, task_id: int) -> list[dict[str, object]]:
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        with self._connect() as con:
            self._task_row(con, task_id)
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute("""SELECT id,employee_id,action,detail,created_at
                     FROM company_task_assignment_events WHERE task_id=? ORDER BY id""", (task_id,))]

    def auto_assign_task(self, task_id: int) -> dict[str, object]:
        """Deterministic strict-match routing, lowest open workload then stable ID.

        Owner explicitly invokes this action. Profiles without a hierarchy tier
        or with tier 'staff' are eligible; chief/head are excluded. No grant or
        model is invoked. Existing assignments stay stable until explicitly cleared.
        """
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id, "업무")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            task = self._task_row(con,task_id)
            if task[4] != "todo":
                raise ValueError("할 일(todo) 상태의 업무만 자동 배정할 수 있습니다.")
            existing = con.execute("SELECT employee_id FROM company_task_assignments WHERE task_id=?", (task_id,)).fetchone()
            if existing is not None:
                # Never silently redistribute work during a second button click.
                row = con.execute("""SELECT e.id,e.display_name FROM ai_employee_profiles e
                     WHERE e.id=? AND e.lifecycle='draft'""", (existing[0],)).fetchone()
                if row:
                    return {"employee_id": row[0], "employee_name": row[1], "changed": False}
                self._clear_task_assignment_in_tx(con,task_id,"employee_inactive","비활성 직원 재검토")
            requirements=con.execute("SELECT department_id,job_id FROM company_task_routing WHERE task_id=?",(task_id,)).fetchone()
            department_id,job_id = tuple(requirements) if requirements else (None,None)
            candidates=con.execute("""SELECT e.id,e.display_name,
               (SELECT COUNT(*) FROM company_task_assignments a
                JOIN company_tasks t ON t.id=a.task_id
                WHERE a.employee_id=e.id AND t.status NOT IN ('done','cancelled')) AS open_count
                FROM ai_employee_profiles e
                LEFT JOIN ai_reporting_lines r ON r.employee_id=e.id
                WHERE e.lifecycle='draft' AND (r.tier IS NULL OR r.tier='staff')
                  AND (? IS NULL OR e.department_id=?)
                  AND (? IS NULL OR e.job_id=?)
                ORDER BY CASE WHEN EXISTS (SELECT 1 FROM ai_employee_model_assignments m WHERE m.employee_id=e.id) THEN 0 ELSE 1 END, open_count,e.id LIMIT 1""",
                (department_id,department_id,job_id,job_id)).fetchone()
            if candidates is None:
                raise ValueError("조건에 맞는 활성 직원이 없습니다. 부서·직무 조건이나 직원 상태를 확인하세요.")
            employee_id,display_name,open_count=candidates
            reason=f"부서={department_id or '전체'}, 직무={job_id or '전체'}, 미완료 배정={open_count}건, 동률 시 직원 ID 오름차순"
            con.execute("INSERT INTO company_task_assignments(task_id,employee_id,reason) VALUES(?,?,?)",
                        (task_id,employee_id,reason))
            con.execute("""INSERT INTO company_task_assignment_events(task_id,employee_id,action,detail)
                           VALUES(?,?,'auto_assigned',?)""",(task_id,employee_id,reason))
            return {"employee_id":employee_id,"employee_name":display_name,"changed":True,"reason":reason}

    def clear_task_assignment(self, task_id: int) -> None:
        self.require_permission("company:manage")
        task_id = self._plan_id(task_id,"업무")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            task=self._task_row(con,task_id)
            if task[4] != "todo":
                raise ValueError("할 일 상태의 업무에서만 담당자를 해제할 수 있습니다.")
            if not self._clear_task_assignment_in_tx(con,task_id,"cleared","관리자 명시적 배정 해제"):
                raise ValueError("해제할 담당자가 없습니다.")

    def list_departments(self) -> list[dict[str, object]]:
        """Departments are local company structure, not running AI employees."""
        self.require_permission("company:manage")
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, name, description FROM company_departments ORDER BY id"
            ).fetchall()
        return [dict(zip(("id", "name", "description"), row)) for row in rows]

    @staticmethod
    def _department_id(department_id: int) -> None:
        if isinstance(department_id, bool) or not isinstance(department_id, int) or department_id < 1:
            raise ValueError("올바른 부서 번호를 선택하세요.")

    @staticmethod
    def _validated_department(name: str, description: str) -> tuple[str, str]:
        return (
            LocalStore._validated_text(name, "부서명", 80, required=True),
            LocalStore._validated_text(description, "부서 설명", 500),
        )

    @staticmethod
    def _ensure_unique_department(con: sqlite3.Connection, name: str, except_id: int | None = None) -> None:
        # casefold also handles non-ASCII names that SQLite's NOCASE cannot.
        rows = con.execute("SELECT id, name FROM company_departments").fetchall()
        if any(row[1].casefold() == name.casefold() and row[0] != except_id for row in rows):
            raise ValueError("같은 이름의 부서가 이미 존재합니다.")

    def add_department(self, name: str, description: str = "") -> int:
        self.require_permission("company:manage")
        validated = self._validated_department(name, description)
        with self._connect() as con:
            self._ensure_unique_department(con, validated[0])
            try:
                cursor = con.execute(
                    "INSERT INTO company_departments (name, description) VALUES (?, ?)", validated
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("같은 이름의 부서가 이미 존재합니다.") from exc
            return int(cursor.lastrowid)

    def update_department(self, department_id: int, name: str, description: str = "") -> None:
        self.require_permission("company:manage")
        self._department_id(department_id)
        validated = self._validated_department(name, description)
        with self._connect() as con:
            self._ensure_unique_department(con, validated[0], except_id=department_id)
            try:
                cursor = con.execute(
                    "UPDATE company_departments SET name=?, description=?, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?", (*validated, department_id)
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("같은 이름의 부서가 이미 존재합니다.") from exc
            if cursor.rowcount != 1:
                raise ValueError("선택한 부서를 찾을 수 없습니다.")

    def delete_department(self, department_id: int) -> None:
        self.require_permission("company:manage")
        self._department_id(department_id)
        with self._connect() as con:
            try:
                cursor = con.execute("DELETE FROM company_departments WHERE id=?", (department_id,))
            except sqlite3.IntegrityError as exc:
                raise ValueError("연결된 직원이나 데이터가 있어 부서를 삭제할 수 없습니다.") from exc
            if cursor.rowcount != 1:
                raise ValueError("선택한 부서를 찾을 수 없습니다.")

    # Stage 13. Catalog metadata only; account/agent permissions remain untouched.
    @staticmethod
    def _validate_designation_kind(kind: str) -> str:
        if not isinstance(kind, str) or kind not in DESIGNATION_KINDS:
            raise ValueError("직급·직무·역할 유형 중 하나를 선택하세요.")
        return kind

    @staticmethod
    def _designation_id(designation_id: int) -> None:
        if isinstance(designation_id, bool) or not isinstance(designation_id, int) or designation_id < 1:
            raise ValueError("올바른 직급·직무·역할 번호가 필요합니다.")

    @staticmethod
    def _unique_designation(con: sqlite3.Connection, kind: str, name: str,
                            except_id: int | None = None) -> None:
        rows = con.execute("SELECT id, name FROM company_designations WHERE kind=?", (kind,)).fetchall()
        if any(existing_name.casefold() == name.casefold() and identifier != except_id
               for identifier, existing_name in rows):
            raise ValueError("같은 유형에 동일한 이름이 이미 존재합니다.")

    def list_designations(self, kind: str | None = None) -> list[dict[str, object]]:
        self.require_permission("company:manage")
        if kind is not None:
            self._validate_designation_kind(kind)
        with self._connect() as con:
            if kind is None:
                rows = con.execute(
                    "SELECT id, kind, name, description FROM company_designations ORDER BY id"
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT id, kind, name, description FROM company_designations WHERE kind=? ORDER BY id",
                    (kind,),
                ).fetchall()
        return [dict(zip(("id", "kind", "name", "description"), row)) for row in rows]

    def add_designation(self, kind: str, name: str, description: str = "") -> int:
        self.require_permission("company:manage")
        kind = self._validate_designation_kind(kind)
        name = self._validated_text(name, "명칭", 80, required=True)
        description = self._validated_text(description, "설명", 500)
        with self._connect() as con:
            self._unique_designation(con, kind, name)
            try:
                cursor = con.execute(
                    "INSERT INTO company_designations (kind, name, description) VALUES (?, ?, ?)",
                    (kind, name, description),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("같은 유형에 동일한 이름이 이미 존재합니다.") from exc
            return int(cursor.lastrowid)

    def update_designation(self, designation_id: int, kind: str, name: str,
                           description: str = "") -> None:
        self.require_permission("company:manage")
        self._designation_id(designation_id)
        kind = self._validate_designation_kind(kind)
        name = self._validated_text(name, "명칭", 80, required=True)
        description = self._validated_text(description, "설명", 500)
        with self._connect() as con:
            self._unique_designation(con, kind, name, except_id=designation_id)
            try:
                cursor = con.execute(
                    "UPDATE company_designations SET kind=?, name=?, description=?, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (kind, name, description, designation_id),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("같은 유형에 동일한 이름이 이미 존재합니다.") from exc
            if cursor.rowcount != 1:
                raise ValueError("선택한 직급·직무·역할을 찾을 수 없습니다.")

    def delete_designation(self, designation_id: int) -> None:
        self.require_permission("company:manage")
        self._designation_id(designation_id)
        with self._connect() as con:
            try:
                cursor = con.execute("DELETE FROM company_designations WHERE id=?", (designation_id,))
            except sqlite3.IntegrityError as exc:
                raise ValueError("사용 중인 직급·직무·역할은 삭제할 수 없습니다.") from exc
            if cursor.rowcount != 1:
                raise ValueError("선택한 직급·직무·역할을 찾을 수 없습니다.")

    # Stage 14 repository: durable, owner-only employee metadata. Creating a
    # draft here never starts an AI model, grants agent rights, or invokes tools.
    @staticmethod
    def _validate_employee_id(employee_id: int) -> None:
        if isinstance(employee_id, bool) or not isinstance(employee_id, int) or employee_id < 1:
            raise ValueError("올바른 AI 직원 정보 번호가 필요합니다.")

    @staticmethod
    def _validate_reference(value: int | None, label: str) -> int | None:
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            raise ValueError(f"{label} 번호가 올바르지 않습니다.")
        return value

    def add_employee_draft(self, employee_key: str, display_name: str,
                           description: str = '', *, department_id: int | None = None,
                           rank_id: int | None = None, job_id: int | None = None,
                           role_id: int | None = None) -> int:
        """Store a non-executable record. Employee UI and lifecycle follow in stage 15."""
        self.require_permission("agents:manage")
        if not isinstance(employee_key, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{2,63}', employee_key):
            raise ValueError("직원 식별자는 영문 시작, 3~64자의 영문·숫자·_-만 허용합니다.")
        values = (
            employee_key,
            self._validated_text(display_name, "직원명", 80, required=True),
            self._validated_text(description, "직원 설명", 500),
            self._validate_reference(department_id, "부서"),
            self._validate_reference(rank_id, "직급"),
            self._validate_reference(job_id, "직무"),
            self._validate_reference(role_id, "역할"),
        )
        with self._connect() as con:
            try:
                cursor = con.execute("""
                    INSERT INTO ai_employee_profiles
                        (employee_key, display_name, description, department_id,
                         rank_id, job_id, role_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, values)
            except sqlite3.IntegrityError as exc:
                raise ValueError("중복 직원 식별자 또는 유효하지 않은 부서·직급·직무·역할입니다.") from exc
            return int(cursor.lastrowid)

    def update_employee_record(self, employee_id: int, display_name: str,
                               description: str = '', *, department_id: int | None = None,
                               rank_id: int | None = None, job_id: int | None = None,
                               role_id: int | None = None) -> None:
        """Edit only metadata. Employee key and lifecycle remain immutable here."""
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        values = (
            self._validated_text(display_name, "직원명", 80, required=True),
            self._validated_text(description, "직원 설명", 500),
            self._validate_reference(department_id, "부서"),
            self._validate_reference(rank_id, "직급"),
            self._validate_reference(job_id, "직무"),
            self._validate_reference(role_id, "역할"),
            employee_id,
        )
        try:
            with self._connect() as con:
                con.execute("BEGIN IMMEDIATE")
                if con.execute("SELECT 1 FROM company_task_runs WHERE employee_id=? AND status='running'",
                               (employee_id,)).fetchone():
                    raise ValueError("로컬 AI 업무 실행 중에는 직원 정보를 변경할 수 없습니다.")
                before = con.execute("SELECT department_id,job_id FROM ai_employee_profiles WHERE id=?", (employee_id,)).fetchone()
                cursor = con.execute("""
                    UPDATE ai_employee_profiles
                    SET display_name=?, description=?, department_id=?, rank_id=?,
                        job_id=?, role_id=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                """, values)
                if cursor.rowcount != 1:
                    raise ValueError("수정할 직원 정보를 찾을 수 없습니다.")
                if before is not None and tuple(before) != (values[2],values[4]):
                    assigned = con.execute("SELECT task_id FROM company_task_assignments WHERE employee_id=?", (employee_id,)).fetchall()
                    for (task_id,) in assigned:
                        self._clear_task_assignment_in_tx(con,task_id,"employee_changed","직원 부서/직무 변경으로 배정 취소")
        except sqlite3.IntegrityError as exc:
            raise ValueError("유효하지 않은 부서·직급·직무·역할입니다.") from exc

    def set_employee_inactive(self, employee_id: int) -> None:
        """Deactivate a stored profile; no AI worker is running at this stage."""
        self._set_employee_lifecycle(employee_id, expected='draft', target='inactive')

    def restore_employee_draft(self, employee_id: int) -> None:
        """Restore an inactive profile to a non-executable draft, never start AI."""
        self._set_employee_lifecycle(employee_id, expected='inactive', target='draft')

    def _set_employee_lifecycle(self, employee_id: int, *, expected: str,
                                target: str) -> None:
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        try:
            with self._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                if con.execute("SELECT 1 FROM company_task_runs WHERE employee_id=? AND status='running'",
                               (employee_id,)).fetchone():
                    raise ValueError("로컬 AI 업무 실행 중에는 직원을 비활성화할 수 없습니다.")
                cursor = con.execute("""
                    UPDATE ai_employee_profiles SET lifecycle=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=? AND lifecycle=?
                """, (target, employee_id, expected))
                if cursor.rowcount != 1:
                    raise ValueError("직원 정보가 없거나 이미 해당 상태입니다.")
                if target == 'inactive':
                    assigned = con.execute("SELECT task_id FROM company_task_assignments WHERE employee_id=?", (employee_id,)).fetchall()
                    for (task_id,) in assigned:
                        self._clear_task_assignment_in_tx(con,task_id,"employee_inactive","직원 비활성화로 배정 취소")
        except sqlite3.IntegrityError as exc:
            raise ValueError("하위 직원이 있는 관리자는 먼저 직원의 배정을 변경해야 합니다.") from exc

    def list_employee_records(self) -> list[dict[str, object]]:
        """Inspect stored drafts only; never implies running AI employees."""
        self.require_permission("agents:manage")
        with self._connect() as con:
            rows = con.execute("""
                SELECT id, employee_key, display_name, description,
                       department_id, rank_id, job_id, role_id, lifecycle
                FROM ai_employee_profiles ORDER BY id
            """).fetchall()
        keys = ("id", "employee_key", "display_name", "description", "department_id",
                "rank_id", "job_id", "role_id", "lifecycle")
        return [dict(zip(keys, row)) for row in rows]

    def read_employee_record(self, employee_id: int) -> dict[str, object]:
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        for record in self.list_employee_records():
            if record["id"] == employee_id:
                return record
        raise ValueError("직원 정보 기록을 찾을 수 없습니다.")

    # Stage 16: validated CEO -> department head -> employee reporting metadata.
    # Employees remain non-executable drafts; no AI call happens here.
    def assign_reporting_line(self, employee_id: int, tier: str,
                              manager_id: int | None = None) -> None:
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        if tier not in ("ceo", "department_head", "staff"):
            raise ValueError("계층은 총괄 AI, 부서장, 직원 중 하나여야 합니다.")
        self._validate_reference(manager_id, "상급자")
        if tier == "ceo" and manager_id is not None:
            raise ValueError("총괄 AI는 상급자를 지정할 수 없습니다.")
        if tier != "ceo" and manager_id is None:
            raise ValueError("부서장과 직원은 상급자를 선택해야 합니다.")
        try:
            with self._connect() as con:
                con.execute("BEGIN IMMEDIATE")
                if con.execute("SELECT 1 FROM company_task_runs WHERE employee_id=? AND status='running'",
                               (employee_id,)).fetchone():
                    raise ValueError('업무 실행 중에는 직원 지휘 계층을 변경할 수 없습니다.')
                con.execute("""
                    INSERT INTO ai_reporting_lines (employee_id, tier, manager_id)
                    VALUES (?, ?, ?) ON CONFLICT(employee_id) DO UPDATE SET
                    tier=excluded.tier, manager_id=excluded.manager_id
                """, (employee_id, tier, manager_id))
                if tier != 'staff':
                    assigned = con.execute("SELECT task_id FROM company_task_assignments WHERE employee_id=?", (employee_id,)).fetchall()
                    for (task_id,) in assigned:
                        self._clear_task_assignment_in_tx(con,task_id,"employee_changed","직원 지휘 계층 변경으로 배정 취소")
        except sqlite3.IntegrityError as exc:
            raise ValueError("조직 계층 규칙 위반: 총괄 AI 중복, 부서 불일치, 순환 또는 비활성 직원을 확인하세요.") from exc

    def unassign_reporting_line(self, employee_id: int) -> None:
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        try:
            with self._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                if con.execute("SELECT 1 FROM company_task_runs WHERE employee_id=? AND status='running'",
                               (employee_id,)).fetchone():
                    raise ValueError('업무 실행 중에는 직원 지휘 계층을 해제할 수 없습니다.')
                result = con.execute("DELETE FROM ai_reporting_lines WHERE employee_id=?", (employee_id,))
                if result.rowcount != 1:
                    raise ValueError("해제할 보고 관계가 없습니다.")
        except sqlite3.IntegrityError as exc:
            raise ValueError("하위 직원이 있는 관리자는 먼저 하위 직원의 배정을 해제해야 합니다.") from exc

    def list_reporting_lines(self) -> list[dict[str, object]]:
        self.require_permission("agents:manage")
        with self._connect() as con:
            rows = con.execute("""
                SELECT employee_id, tier, manager_id FROM ai_reporting_lines
                ORDER BY CASE tier WHEN 'ceo' THEN 0 WHEN 'department_head' THEN 1 ELSE 2 END,
                         employee_id
            """).fetchall()
        return [dict(zip(("employee_id", "tier", "manager_id"), row)) for row in rows]

    # Stage 20: read the one owner-designated chief; do not auto-start any engine.
    def read_chief_profile(self) -> dict[str, object] | None:
        self.require_permission("agents:manage")
        with self._connect() as con:
            row = con.execute("""SELECT e.id,e.display_name,e.lifecycle,a.model_id,m.name
                FROM ai_reporting_lines r
                JOIN ai_employee_profiles e ON e.id=r.employee_id
                LEFT JOIN ai_employee_model_assignments a ON a.employee_id=e.id
                LEFT JOIN ai_local_models m ON m.id=a.model_id
                WHERE r.tier='ceo'""").fetchone()
        return dict(zip(("employee_id","display_name","lifecycle","model_id","model_name"),row)) if row else None

    # Stage 17: agent-policy data only. No network, OS, or AI tool invocation.
    def read_employee_access(self, employee_id: int) -> dict[str, list[str]]:
        """Owner can inspect a profile's configured capabilities and tools."""
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        with self._connect() as con:
            if con.execute("SELECT 1 FROM ai_employee_profiles WHERE id=?", (employee_id,)).fetchone() is None:
                raise ValueError("직원 정보가 존재하지 않습니다.")
            capabilities = [x[0] for x in con.execute(
                "SELECT capability FROM ai_employee_capability_grants WHERE employee_id=? ORDER BY capability", (employee_id,))]
            tools = [x[0] for x in con.execute(
                "SELECT tool_key FROM ai_employee_tool_grants WHERE employee_id=? ORDER BY tool_key", (employee_id,))]
            tools += [x[0] for x in con.execute(
                "SELECT tool_key FROM ai_employee_native_tool_grants WHERE employee_id=?", (employee_id,))]
            tools.sort()
        return {"capabilities": capabilities, "tools": tools}

    def save_employee_access(self, employee_id: int, capabilities: list[str] | set[str],
                             tools: list[str] | set[str]) -> None:
        """Atomic replace, default deny. Never grant owner/admin privileges."""
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        from desktop.access_policy import validate_grants
        caps, tool_keys = validate_grants(capabilities, tools)
        with self._connect() as con:
            if con.execute("SELECT 1 FROM company_task_runs WHERE employee_id=? AND status='running'",
                           (employee_id,)).fetchone():
                raise ValueError("로컬 AI 업무 실행 중에는 직원 권한을 변경할 수 없습니다.")
            row = con.execute("SELECT lifecycle FROM ai_employee_profiles WHERE id=?", (employee_id,)).fetchone()
            if row is None:
                raise ValueError("직원 정보가 존재하지 않습니다.")
            if row[0] != "draft":
                raise ValueError("비활성 직원에게는 권한이나 도구를 설정할 수 없습니다.")
            con.execute("DELETE FROM ai_employee_native_tool_grants WHERE employee_id=?", (employee_id,))
            con.execute("DELETE FROM ai_employee_tool_grants WHERE employee_id=?", (employee_id,))
            con.execute("DELETE FROM ai_employee_capability_grants WHERE employee_id=?", (employee_id,))
            con.executemany("INSERT INTO ai_employee_capability_grants(employee_id, capability) VALUES (?, ?)",
                            [(employee_id, x) for x in sorted(caps)])
            con.executemany("INSERT INTO ai_employee_tool_grants(employee_id, tool_key) VALUES (?, ?)",
                            [(employee_id, x) for x in sorted(tool_keys - {'local_windows_version_reader'})])
            if 'local_windows_version_reader' in tool_keys:
                con.execute("INSERT INTO ai_employee_native_tool_grants(employee_id,tool_key) VALUES(?,?)",
                            (employee_id,'local_windows_version_reader'))

    def is_employee_allowed(self, employee_id: int, capability: str,
                            tool_key: str | None = None) -> bool:
        """Fail-closed policy query for *future* executors; DOES NOT invoke tools."""
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        from desktop.access_policy import CAPABILITIES, TOOLS
        if not isinstance(capability, str) or capability not in CAPABILITIES or (
                tool_key is not None and (not isinstance(tool_key, str)
                or tool_key not in TOOLS or TOOLS[tool_key][1] != capability)):
            return False
        with self._connect() as con:
            row = con.execute("SELECT lifecycle FROM ai_employee_profiles WHERE id=?", (employee_id,)).fetchone()
            if not row or row[0] != "draft":
                return False
            granted = con.execute("SELECT 1 FROM ai_employee_capability_grants WHERE employee_id=? AND capability=?",
                                  (employee_id, capability)).fetchone() is not None
            if not granted or tool_key is None:
                return granted
            grant_table = ('ai_employee_native_tool_grants' if tool_key == 'local_windows_version_reader'
                           else 'ai_employee_tool_grants')
            return con.execute(f"SELECT 1 FROM {grant_table} WHERE employee_id=? AND tool_key=?",
                               (employee_id, tool_key)).fetchone() is not None

    def require_employee_access(self, employee_id: int, capability: str,
                                tool_key: str | None = None) -> None:
        """Authoritative explicit deny; future execution paths must call this first."""
        if not self.is_employee_allowed(employee_id, capability, tool_key):
            raise AuthenticationError("AI 직원에게 해당 작업 권한이나 도구 사용 허가가 없습니다.")

    def list_local_models(self) -> list[dict[str, object]]:
        """Read local model connector profiles (no network requests)."""
        self.require_permission("agents:manage")
        with self._connect() as con:
            rows = con.execute("""SELECT id, name, backend, executable_path, model_path, max_tokens
                                  FROM ai_local_models ORDER BY id""").fetchall()
        return [dict(zip(("id", "name", "backend", "executable_path", "model_path", "max_tokens"), r))
                for r in rows]

    def read_local_model(self, model_id: int) -> dict[str, object]:
        self.require_permission("agents:manage")
        if type(model_id) is not int or model_id < 1:
            raise ValueError("모델 ID가 올바르지 않습니다.")
        with self._connect() as con:
            row = con.execute("""SELECT id, name, backend, executable_path, model_path, max_tokens
                                 FROM ai_local_models WHERE id=?""", (model_id,)).fetchone()
        if row is None:
            raise ValueError("등록된 모델이 없습니다.")
        return dict(zip(("id", "name", "backend", "executable_path", "model_path", "max_tokens"), row))

    def add_local_model(self, config) -> int:
        self.require_permission("agents:manage")
        from desktop.model_runtime import validate_config
        clean = validate_config(config)
        try:
            with self._connect() as con:
                cur = con.execute("""INSERT INTO ai_local_models
                    (name, backend, executable_path, model_path, max_tokens)
                    VALUES (?, ?, ?, ?, ?)""",
                    (clean.name, clean.backend, clean.executable_path, clean.model_path, clean.max_tokens))
                return int(cur.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise ValueError("이미 사용 중인 모델 이름입니다.") from exc

    def update_local_model(self, model_id: int, config) -> None:
        self.require_permission("agents:manage")
        if type(model_id) is not int or model_id < 1:
            raise ValueError("모델 ID가 올바르지 않습니다.")
        from desktop.model_runtime import validate_config
        clean = validate_config(config)
        try:
            with self._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                if con.execute("SELECT 1 FROM company_task_runs WHERE model_id=? AND status='running'",
                               (model_id,)).fetchone():
                    raise ValueError('업무 실행 중인 로컬 모델은 변경할 수 없습니다.')
                cur = con.execute("""UPDATE ai_local_models SET name=?, backend=?, executable_path=?,
                    model_path=?, max_tokens=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (clean.name, clean.backend, clean.executable_path, clean.model_path, clean.max_tokens, model_id))
                if cur.rowcount != 1:
                    raise ValueError("등록된 모델이 없습니다.")
        except sqlite3.IntegrityError as exc:
            raise ValueError("이미 사용 중인 모델 이름입니다.") from exc

    def delete_local_model(self, model_id: int) -> None:
        self.require_permission("agents:manage")
        if type(model_id) is not int or model_id < 1:
            raise ValueError("모델 ID가 올바르지 않습니다.")
        try:
            with self._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                if con.execute("SELECT 1 FROM company_task_runs WHERE model_id=? AND status='running'",
                               (model_id,)).fetchone():
                    raise ValueError('업무 실행 중인 로컬 모델은 삭제할 수 없습니다.')
                if con.execute("DELETE FROM ai_local_models WHERE id=?", (model_id,)).rowcount != 1:
                    raise ValueError("등록된 모델이 없습니다.")
        except sqlite3.IntegrityError as exc:
            raise ValueError("AI 직원에게 배정된 모델입니다. 직원 배정을 먼저 해제하세요.") from exc

    # Stage 19: per-employee LOCAL model binding and minimal privacy-preserving audit.
    def set_employee_model(self, employee_id: int, model_id: int | None) -> None:
        """Assign/unassign one existing local model. Never start the model."""
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        if model_id is not None and (type(model_id) is not int or model_id < 1):
            raise ValueError("모델 ID가 올바르지 않습니다.")
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute("SELECT 1 FROM company_task_runs WHERE employee_id=? AND status='running'",
                           (employee_id,)).fetchone():
                raise ValueError("로컬 AI 업무 실행 중에는 직원 모델을 변경할 수 없습니다.")
            row = con.execute("SELECT lifecycle FROM ai_employee_profiles WHERE id=?", (employee_id,)).fetchone()
            if row is None:
                raise ValueError("직원 정보가 존재하지 않습니다.")
            if model_id is None:
                con.execute("DELETE FROM ai_employee_model_assignments WHERE employee_id=?", (employee_id,))
                return
            if row[0] != "draft":
                raise ValueError("비활성 직원에게는 모델을 배정할 수 없습니다.")
            if con.execute("SELECT 1 FROM ai_local_models WHERE id=?", (model_id,)).fetchone() is None:
                raise ValueError("등록된 로컬 모델이 없습니다.")
            con.execute("""INSERT INTO ai_employee_model_assignments (employee_id,model_id)
                VALUES (?,?) ON CONFLICT(employee_id) DO UPDATE SET
                model_id=excluded.model_id,updated_at=CURRENT_TIMESTAMP""", (employee_id,model_id))

    def read_employee_model(self, employee_id: int) -> dict[str, object] | None:
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        with self._connect() as con:
            if con.execute("SELECT 1 FROM ai_employee_profiles WHERE id=?", (employee_id,)).fetchone() is None:
                raise ValueError("직원 정보가 존재하지 않습니다.")
            row = con.execute("""SELECT a.employee_id,a.model_id,m.name,m.backend
                FROM ai_employee_model_assignments a JOIN ai_local_models m ON m.id=a.model_id
                WHERE a.employee_id=?""", (employee_id,)).fetchone()
        return dict(zip(("employee_id","model_id","model_name","backend"),row)) if row else None

    def list_employee_models(self) -> list[dict[str, object]]:
        self.require_permission("agents:manage")
        with self._connect() as con:
            rows = con.execute("""SELECT a.employee_id,e.display_name,a.model_id,m.name
                FROM ai_employee_model_assignments a
                JOIN ai_employee_profiles e ON e.id=a.employee_id
                JOIN ai_local_models m ON m.id=a.model_id ORDER BY a.employee_id""").fetchall()
        return [dict(zip(("employee_id","employee_name","model_id","model_name"),x)) for x in rows]

    def begin_employee_model_call(self, employee_id: int, prompt: str, *,
                                  required_tier: str | None = None) -> tuple[int, object]:
        """Log *manual owner initiated* call before subprocess; return frozen config.

        Does not log prompts, outputs, executable paths, or secrets.
        The caller must finish the record on success, error or cancellation.
        """
        self.require_permission("agents:manage")
        self._validate_employee_id(employee_id)
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 3000:
            raise ValueError("질문은 1~3000자여야 합니다.")
        if required_tier not in (None, "ceo"):
            raise ValueError("지원하지 않는 총괄 AI 역할 조건입니다.")
        from desktop.model_runtime import ModelConfig
        with self._connect() as con:
            from desktop.stage87_90_management import stopped as emergency_stopped
            if emergency_stopped(con):
                raise PermissionError("비상 정지 상태에서는 직원 AI 호출을 시작할 수 없습니다.")
            row = con.execute("""SELECT m.id,m.name,m.backend,m.executable_path,m.model_path,m.max_tokens
                FROM ai_employee_model_assignments a
                JOIN ai_local_models m ON m.id=a.model_id
                JOIN ai_employee_profiles e ON e.id=a.employee_id
                WHERE a.employee_id=? AND e.lifecycle='draft'
                AND (? IS NULL OR EXISTS (SELECT 1 FROM ai_reporting_lines r
                    WHERE r.employee_id=e.id AND r.tier=?))""",
                (employee_id,required_tier,required_tier)).fetchone()
            if row is None:
                if required_tier == "ceo":
                    raise ValueError("총괄 AI로 지정된 활성 직원에게 로컬 모델을 먼저 배정하세요.")
                raise ValueError("활성 직원에게 배정된 로컬 모델이 없습니다.")
            model_id,name,backend,exe,model_path,tokens=row
            cur = con.execute("""INSERT INTO ai_model_call_history
                (employee_id,model_id,model_name,prompt_chars) VALUES(?,?,?,?)""",
                (employee_id,model_id,name,len(prompt)))
            call_id=int(cur.lastrowid)
        return call_id,ModelConfig(name,backend,exe,model_path,int(tokens))

    def finish_employee_model_call(self, call_id: int, status: str, *,
                                    output_chars: int = 0, duration_ms: int = 0,
                                    error_kind: str = "") -> None:
        self.require_permission("agents:manage")
        if type(call_id) is not int or call_id < 1:
            raise ValueError("기록 ID가 올바르지 않습니다.")
        if status not in {"success","failure","cancelled","timeout"}:
            raise ValueError("호출 결과 코드가 올바르지 않습니다.")
        if type(output_chars) is not int or not 0 <= output_chars <= 20000:
            raise ValueError("출력 길이가 올바르지 않습니다.")
        if type(duration_ms) is not int or duration_ms < 0:
            raise ValueError("호출 소요 시간이 올바르지 않습니다.")
        # The error label is an allowlisted constant, NEVER raw stderr/exception text.
        if error_kind not in {"","ValueError","RuntimeError","OSError","TimeoutError","InterruptedError"}:
            raise ValueError("오류 분류가 올바르지 않습니다.")
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            from desktop.stage87_90_management import stopped as emergency_stopped
            rejected_late_success = status == 'success' and emergency_stopped(con)
            if rejected_late_success:
                status, output_chars, error_kind = 'failure', 0, 'RuntimeError'
            changed=con.execute("""UPDATE ai_model_call_history SET
                status=?,output_chars=?,duration_ms=?,error_kind=?,completed_at=CURRENT_TIMESTAMP
                WHERE id=? AND status='running'""",
                (status,output_chars,duration_ms,error_kind,call_id)).rowcount
            if changed != 1:
                raise ValueError("기록이 존재하지 않거나 이미 완료됐습니다.")
        if rejected_late_success:
            raise PermissionError('비상 정지로 완료된 모델 응답을 폐기했습니다.')

    def list_employee_model_calls(self, employee_id: int | None = None, *,
                                  limit: int = 100) -> list[dict[str, object]]:
        self.require_permission("agents:manage")
        if employee_id is not None:
            self._validate_employee_id(employee_id)
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("기록 조회는 1~200건만 가능합니다.")
        fields=("id","employee_id","model_id","model_name","status","prompt_chars",
                "output_chars","duration_ms","error_kind","started_at","completed_at")
        query="SELECT "+",".join(fields)+" FROM ai_model_call_history"
        args:tuple=()
        if employee_id is not None:
            query+=" WHERE employee_id=?"
            args=(employee_id,)
        query+=" ORDER BY id DESC LIMIT ?"
        with self._connect() as con:
            rows=con.execute(query,args+(limit,)).fetchall()
        return [dict(zip(fields,r)) for r in rows]


    # Stage 31: owner-only local company health monitor. This intentionally
    # does not reuse chief privileges or feed sensitive records to an LLM.
    def read_company_health(self) -> dict[str, object]:
        """Live read-only aggregate; does not create a check-history row."""
        self.require_permission('company:manage')
        from desktop.health_monitor import evaluate_company_health
        with self._connect() as con:
            con.execute('BEGIN')  # consistent snapshot, including all counts
            return evaluate_company_health(con)

    def check_company_health(self, *, force: bool = False) -> dict[str, object]:
        """Check current state and save a summary on change or once per hour.

        Manual force=True saves a new checkpoint even when values are unchanged.
        Automatic checks are deduplicated, avoiding a row on every GUI tick.
        """
        self.require_permission('company:manage')
        if type(force) is not bool:
            raise ValueError('강제 저장 설정이 올바르지 않습니다.')
        from desktop.health_monitor import evaluate_company_health
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            report = evaluate_company_health(con)
            metrics_json = json.dumps(report['metrics'], ensure_ascii=False, sort_keys=True)
            issues_json = json.dumps(report['issues'], ensure_ascii=False, sort_keys=True)
            signature = hashlib.sha256(
                (report['severity'] + '\n' + metrics_json + '\n' + issues_json).encode('utf-8')
            ).hexdigest()
            last = con.execute("""
                SELECT id,signature,checked_at,
                    (checked_at <= datetime('now','-1 hour')) AS expired
                FROM company_health_checks ORDER BY id DESC LIMIT 1
            """).fetchone()
            recorded = force or last is None or last[1] != signature or bool(last[3])
            if recorded:
                check_id = int(con.execute("""
                    INSERT INTO company_health_checks(severity,metrics_json,issues_json,signature)
                    VALUES (?,?,?,?)
                """, (report['severity'], metrics_json, issues_json, signature)).lastrowid)
                checked_at = con.execute(
                    'SELECT checked_at FROM company_health_checks WHERE id=?', (check_id,)
                ).fetchone()[0]
            else:
                check_id, checked_at = int(last[0]), str(last[2])
            return {**report, 'check_id': check_id,
                    'checked_at': checked_at, 'recorded': recorded}

    def list_company_health_checks(self, *, limit: int = 30) -> list[dict[str, object]]:
        self.require_permission('company:manage')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('조회 건수는 1~100 사이여야 합니다.')
        with self._connect() as con:
            rows = con.execute("""
                SELECT id,severity,metrics_json,issues_json,checked_at
                FROM company_health_checks ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
        return [{'id': row[0], 'severity': row[1],
                 'metrics': json.loads(row[2]), 'issues': json.loads(row[3]),
                 'checked_at': row[4]} for row in rows]

    # Stage 32: owner-only read-only local problem/opportunity detection.
    # Opportunity signals are *unvalidated internal candidates*, not market
    # research, AI-generated proposals, or permission to create/run tasks.
    def read_company_signals(self) -> dict[str, object]:
        self.require_permission('company:manage')
        from desktop.opportunity_detector import detect_company_signals
        with self._connect() as con:
            con.execute('BEGIN')
            return detect_company_signals(con)

    def check_company_signals(self, *, force: bool = False) -> dict[str, object]:
        self.require_permission('company:manage')
        if type(force) is not bool:
            raise ValueError('강제 저장 설정이 올바르지 않습니다.')
        from desktop.opportunity_detector import detect_company_signals
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            report = detect_company_signals(con)
            # History is intentionally aggregate-only. No IDs, titles or
            # owner-authored content. Current sample IDs are read live only.
            history_signals = [
                {'kind': x['kind'], 'code': x['code'],
                 'severity': x['severity'], 'count': x['count']}
                for x in report['signals']
            ]
            payload = json.dumps(history_signals, ensure_ascii=False,
                                 sort_keys=True, separators=(',', ':'))
            signature = hashlib.sha256((report['severity'] + '\n' + payload).encode('utf-8')).hexdigest()
            last = con.execute("""
                SELECT id,signature,checked_at,
                    (checked_at <= datetime('now','-1 hour')) AS expired
                FROM company_detection_checks ORDER BY id DESC LIMIT 1
            """).fetchone()
            recorded = force or last is None or last[1] != signature or bool(last[3])
            if recorded:
                check_id = int(con.execute("""
                    INSERT INTO company_detection_checks(severity,signals_json,signature)
                    VALUES (?,?,?)
                """, (report['severity'], payload, signature)).lastrowid)
                checked_at = con.execute(
                    'SELECT checked_at FROM company_detection_checks WHERE id=?', (check_id,)
                ).fetchone()[0]
            else:
                check_id, checked_at = int(last[0]), str(last[2])
            return {**report, 'check_id': check_id,
                    'checked_at': checked_at, 'recorded': recorded}

    def list_company_detection_checks(self, *, limit: int = 30) -> list[dict[str, object]]:
        self.require_permission('company:manage')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('조회 건수는 1~100 사이여야 합니다.')
        with self._connect() as con:
            rows = con.execute("""
                SELECT id,severity,signals_json,checked_at
                FROM company_detection_checks ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
        return [{'id': row[0], 'severity': row[1],
                 'signals': json.loads(row[2]), 'checked_at': row[3]}
                for row in rows]

    # Stage 33: scan automatically generates *drafts*, not executable work.
    # An owner must approve a draft in a separate transaction before an
    # unassigned todo task is inserted. No AI process is called here.
    def scan_autonomous_task_proposals(self, *, limit: int = 30) -> dict[str, object]:
        self.require_permission('company:manage')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('제안 생성 상한은 1~100이어야 합니다.')
        from desktop.autonomous_task_proposals import (
            is_source_eligible, source_candidates, proposal_text,
        )
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            # Mark proposals whose source no longer needs attention. This does
            # not touch existing tasks or mutate any goal/plan/source row.
            pending = con.execute("""SELECT id,source_kind,source_id
                FROM company_task_proposals WHERE status='pending'""").fetchall()
            stale = 0
            for proposal_id, kind, source_id in pending:
                if not is_source_eligible(con, kind, int(source_id)):
                    con.execute("""UPDATE company_task_proposals
                        SET status='stale',decided_at=CURRENT_TIMESTAMP
                        WHERE id=? AND status='pending'""", (proposal_id,))
                    stale += 1
            created: list[int] = []
            for kind, source_id in source_candidates(con, limit):
                title, description = proposal_text(kind, source_id)
                proposal_id = con.execute("""INSERT INTO company_task_proposals
                    (source_kind,source_id,title,description)
                    VALUES(?,?,?,?)""", (kind, source_id, title, description)).lastrowid
                created.append(int(proposal_id))
            # Stage34: bounded, offline and non-executing analysis on every scan.
            from desktop.task_feasibility import assess_pending
            assess_pending(con, limit=100)
            total_pending = int(con.execute("""SELECT COUNT(*) FROM company_task_proposals
                WHERE status='pending'""").fetchone()[0])
            return {'created_ids': created, 'stale_count': stale,
                    'pending_count': total_pending}

    def list_autonomous_task_proposals(self, *, limit: int = 100) -> list[dict[str, object]]:
        self.require_permission('company:manage')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('조회 건수는 1~200이어야 합니다.')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute("""SELECT id,source_kind,source_id,
                title,description,origin,model_updated_at,status,approved_task_id,created_at,decided_at
                FROM company_task_proposals ORDER BY id DESC LIMIT ?""", (limit,))]

    def analyze_task_proposals(self, *, limit: int = 100) -> dict[str, int]:
        """Refresh stored readiness/ranking for pending drafts, without actions."""
        self.require_permission('company:manage')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('분석 건수는 1~200 사이여야 합니다.')
        from desktop.task_feasibility import assess_pending
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return assess_pending(con, limit=limit)

    def list_task_proposal_assessments(self, *, limit: int = 200) -> list[dict[str, object]]:
        """Latest analysis per proposal, sorted by score; never ranks as runnable."""
        self.require_permission('company:manage')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('분석 조회 건수는 1~200 사이여야 합니다.')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute("""SELECT a.id,a.proposal_id,
                a.feasibility,a.recommended_priority,a.score,a.reason,a.created_at,
                p.status AS proposal_status,p.source_kind,p.source_id
                FROM company_task_assessments a
                JOIN company_task_proposals p ON p.id=a.proposal_id
                WHERE a.id=(SELECT MAX(b.id) FROM company_task_assessments b
                            WHERE b.proposal_id=a.proposal_id)
                ORDER BY CASE WHEN p.status='pending' THEN 0 ELSE 1 END,
                         a.score DESC,a.proposal_id ASC LIMIT ?""", (limit,))]

    def list_task_proposal_assessment_history(self, proposal_id: int) -> list[dict[str, object]]:
        """Owner-only immutable analysis history, including previous input changes."""
        self.require_permission('company:manage')
        proposal_id = self._plan_id(proposal_id, '업무 제안')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute("""SELECT id,proposal_id,feasibility,
                recommended_priority,score,reason,created_at FROM company_task_assessments
                WHERE proposal_id=? ORDER BY id""", (proposal_id,))]

    def save_local_ai_task_proposal(self, proposal_id: int,
                                    title: str, description: str) -> bool:
        """Store inert local-model output, never an executable instruction.

        Atomic eligibility recheck protects against background results arriving
        after the goal/plan/task has changed. Only a pending rule draft can be
        replaced once; it still needs explicit owner approval to become a task.
        """
        self.require_permission('company:manage')
        self.require_permission('agents:manage')
        proposal_id = self._plan_id(proposal_id, '업무 제안')
        heading, detail, _ = self._task_values(title, description, None)
        from desktop.autonomous_task_proposals import is_source_eligible
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute("""SELECT source_kind,source_id,status,origin
                FROM company_task_proposals WHERE id=?""", (proposal_id,)).fetchone()
            if row is None or row[2] != 'pending' or row[3] != 'rule':
                raise ValueError('AI 초안을 저장할 수 없는 제안입니다.')
            if not is_source_eligible(con, row[0], int(row[1])):
                con.execute("""UPDATE company_task_proposals
                    SET status='stale',decided_at=CURRENT_TIMESTAMP WHERE id=?""", (proposal_id,))
                return False
            con.execute("""UPDATE company_task_proposals
                SET title=?,description=?,origin='local_ai',model_updated_at=CURRENT_TIMESTAMP
                WHERE id=?""", (heading, detail, proposal_id))
            from desktop.task_feasibility import assess_pending
            assess_pending(con, limit=200)
            return True

    def approve_autonomous_task_proposal(self, proposal_id: int) -> int | None:
        """Owner approval: atomically recheck eligibility and create ONE todo.

        Returns None (and marks stale) if the source changed. This avoids
        approving a proposal based on an outdated scan or GUI selection.
        """
        self.require_permission('company:manage')
        proposal_id = self._plan_id(proposal_id, '업무 제안')
        from desktop.autonomous_task_proposals import is_source_eligible
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute("""SELECT source_kind,source_id,title,description,status
                FROM company_task_proposals WHERE id=?""", (proposal_id,)).fetchone()
            if row is None:
                raise ValueError('업무 제안을 찾을 수 없습니다.')
            kind, source_id, title, description, status = row
            if status != 'pending':
                raise ValueError('대기 중인 업무 제안만 승인할 수 있습니다.')
            if not is_source_eligible(con, kind, int(source_id)):
                con.execute("""UPDATE company_task_proposals
                    SET status='stale',decided_at=CURRENT_TIMESTAMP WHERE id=?""", (proposal_id,))
                return None
            plan_id = int(source_id) if kind == 'ready_plan' else None
            task_id = int(con.execute("""INSERT INTO company_tasks(plan_id,title,description)
                VALUES(?,?,?)""", (plan_id, title, description)).lastrowid)
            con.execute("""INSERT INTO company_task_status_events
                (task_id,old_status,new_status) VALUES(?,NULL,'todo')""", (task_id,))
            con.execute("""UPDATE company_task_proposals
                SET status='approved',approved_task_id=?,decided_at=CURRENT_TIMESTAMP
                WHERE id=?""", (task_id, proposal_id))
            return task_id

    def reject_autonomous_task_proposal(self, proposal_id: int) -> None:
        self.require_permission('company:manage')
        proposal_id = self._plan_id(proposal_id, '업무 제안')
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            changed = con.execute("""UPDATE company_task_proposals
                SET status='rejected',decided_at=CURRENT_TIMESTAMP
                WHERE id=? AND status='pending'""", (proposal_id,)).rowcount
            if not changed:
                raise ValueError('대기 중인 업무 제안만 거절할 수 있습니다.')

    # Stage 35: explicit review and application of deterministic plan breakdowns.
    def generate_task_breakdown(self, plan_id: int) -> int:
        """Create/reuse a draft; never create tasks or invoke an AI model."""
        self.require_permission('company:manage')
        plan_id = self._plan_id(plan_id)
        from desktop.task_breakdown import source_snapshot, detail_items
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            snapshot = source_snapshot(con, plan_id)
            if snapshot is None:
                raise ValueError('활성 목표의 준비 완료 계획(6~30단계, 기존 업무 없음)만 분할할 수 있습니다.')
            fingerprint, steps = snapshot
            con.execute("""UPDATE company_task_breakdowns SET status='stale',
                decided_at=CURRENT_TIMESTAMP WHERE plan_id=? AND status='draft'
                AND fingerprint!=?""", (plan_id, fingerprint))
            existing = con.execute('''SELECT id,status FROM company_task_breakdowns
                WHERE plan_id=? AND fingerprint=?''', (plan_id, fingerprint)).fetchone()
            if existing:
                if existing[1] != 'draft':
                    raise ValueError('이미 처리된 동일한 계획 버전입니다. 계획을 수정한 뒤 다시 생성하세요.')
                return int(existing[0])
            breakdown_id = int(con.execute('''INSERT INTO company_task_breakdowns
                (plan_id,fingerprint) VALUES(?,?)''', (plan_id, fingerprint)).lastrowid)
            con.executemany('''INSERT INTO company_task_breakdown_items
                (breakdown_id,position,title,detail,prerequisite_position)
                VALUES(?,?,?,?,?)''', [(breakdown_id,*item) for item in detail_items(steps)])
            return breakdown_id

    def list_task_breakdowns(self, *, limit: int = 100) -> list[dict[str, object]]:
        self.require_permission('company:manage')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('조회 건수는 1~200이어야 합니다.')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            rows = con.execute('''SELECT b.id,b.plan_id,p.title AS plan_title,
                b.status,b.fingerprint,b.created_at,b.decided_at,
                COUNT(i.id) AS item_count FROM company_task_breakdowns b
                JOIN company_work_plans p ON p.id=b.plan_id
                JOIN company_task_breakdown_items i ON i.breakdown_id=b.id
                GROUP BY b.id ORDER BY b.id DESC LIMIT ?''', (limit,)).fetchall()
            return [dict(row) for row in rows]

    def read_task_breakdown(self, breakdown_id: int) -> dict[str, object]:
        self.require_permission('company:manage')
        breakdown_id = self._plan_id(breakdown_id, '세부 계획')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            row = con.execute('''SELECT id,plan_id,fingerprint,status,created_at,decided_at
                FROM company_task_breakdowns WHERE id=?''', (breakdown_id,)).fetchone()
            if row is None:
                raise ValueError('세부 계획을 찾을 수 없습니다.')
            items = [dict(item) for item in con.execute('''SELECT position,title,detail,
                prerequisite_position,task_id FROM company_task_breakdown_items
                WHERE breakdown_id=? ORDER BY position''', (breakdown_id,))]
            return {**dict(row), 'items': items}

    def reject_task_breakdown(self, breakdown_id: int) -> None:
        self.require_permission('company:manage')
        breakdown_id = self._plan_id(breakdown_id, '세부 계획')
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            changed = con.execute('''UPDATE company_task_breakdowns
                SET status='rejected',decided_at=CURRENT_TIMESTAMP
                WHERE id=? AND status='draft' ''', (breakdown_id,)).rowcount
            if not changed:
                raise ValueError('대기 중인 세부 계획만 거절할 수 있습니다.')

    def apply_task_breakdown(self, breakdown_id: int) -> list[int] | None:
        """Owner-only atomic approval: create todo tasks and linear prerequisites.

        Returns None for a stale source (and persists stale status). All other
        failures roll back; no partial task graph is ever committed.
        """
        self.require_permission('company:manage')
        breakdown_id = self._plan_id(breakdown_id, '세부 계획')
        from desktop.task_breakdown import source_snapshot, detail_items
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('''SELECT plan_id,fingerprint,status
                FROM company_task_breakdowns WHERE id=?''', (breakdown_id,)).fetchone()
            if row is None or row[2] != 'draft':
                raise ValueError('승인 대기 중인 세부 계획만 적용할 수 있습니다.')
            plan_id, fingerprint = int(row[0]), str(row[1])
            snapshot = source_snapshot(con, plan_id)
            if snapshot is None or snapshot[0] != fingerprint:
                con.execute('''UPDATE company_task_breakdowns
                    SET status='stale',decided_at=CURRENT_TIMESTAMP WHERE id=?''', (breakdown_id,))
                return None
            items = con.execute('''SELECT id,position,title,detail,prerequisite_position,task_id
                FROM company_task_breakdown_items WHERE breakdown_id=? ORDER BY position''',
                (breakdown_id,)).fetchall()
            if len(items) != len(snapshot[1]) or not items:
                raise ValueError('세부 계획 단계가 원본과 일치하지 않습니다.')
            # A draft is an immutable snapshot, not a mutable command channel.
            # Reject direct SQLite tampering even if its FK/length checks pass.
            expected = detail_items(snapshot[1])
            if [(r[1], r[2], r[3], r[4]) for r in items] != expected:
                raise ValueError('세부 계획 초안 내용이 손상되었습니다.')
            created: dict[int, int] = {}
            for item_id, position, title, detail, predecessor, existing_task in items:
                if existing_task is not None or position != len(created) + 1:
                    raise ValueError('세부 계획 단계가 손상되었습니다.')
                if predecessor != (position - 1 if position > 1 else None):
                    raise ValueError('세부 계획 의존성이 손상되었습니다.')
                task_id = int(con.execute('''INSERT INTO company_tasks(plan_id,title,description)
                    VALUES(?,?,?)''', (plan_id, title, detail)).lastrowid)
                con.execute('''INSERT INTO company_task_status_events
                    (task_id,old_status,new_status) VALUES(?,NULL,'todo')''', (task_id,))
                if predecessor is not None:
                    con.execute('''INSERT INTO company_task_dependencies(task_id,prerequisite_id)
                        VALUES(?,?)''', (task_id, created[predecessor]))
                    con.execute('''INSERT INTO company_task_dependency_events
                        (task_id,prerequisite_id,action) VALUES(?,?,'added')''',
                        (task_id, created[predecessor]))
                con.execute('''UPDATE company_task_breakdown_items SET task_id=? WHERE id=?''',
                            (task_id, item_id))
                created[int(position)] = task_id
            con.execute('''UPDATE company_task_breakdowns
                SET status='applied',decided_at=CURRENT_TIMESTAMP WHERE id=?''', (breakdown_id,))
            return [created[position] for position in sorted(created)]

    # Stage 21: an owner's local CEO can *read* a permission-scoped, consistent
    # snapshot of the company state. This is NOT an automatic monitoring job.
    def read_chief_company_status(self) -> dict[str, object]:
        self.require_permission("agents:manage")
        with self._connect() as con:
            con.execute("BEGIN")  # all figures refer to the same SQLite snapshot
            chief = con.execute("""SELECT e.id, e.display_name, e.lifecycle
                FROM ai_reporting_lines r JOIN ai_employee_profiles e ON e.id=r.employee_id
                WHERE r.tier='ceo'""").fetchone()
            if chief is None or chief[2] != 'draft':
                raise ValueError("활성 총괄 AI가 없습니다. 조직 지휘 체계에서 지정하세요.")
            chief_id = int(chief[0])
            grants = {r[0] for r in con.execute(
                "SELECT capability FROM ai_employee_capability_grants WHERE employee_id=?", (chief_id,))}
            tools = {r[0] for r in con.execute(
                "SELECT tool_key FROM ai_employee_tool_grants WHERE employee_id=?", (chief_id,))}
            if 'company:read' not in grants or 'local_company_reader' not in tools:
                raise AuthenticationError("총괄 AI의 회사 정보 조회 권한과 로컬 회사 조회 도구가 필요합니다.")
            company = con.execute("SELECT name, description, mission FROM company_profile WHERE id=1").fetchone()
            if company is None:
                company = ('AI Autonomous Company', '', '')
            total_dept = con.execute('SELECT COUNT(*) FROM company_departments').fetchone()[0]
            departments = [r[0] for r in con.execute(
                'SELECT name FROM company_departments ORDER BY id LIMIT 15')]
            counts = dict(con.execute('SELECT lifecycle,COUNT(*) FROM ai_employee_profiles GROUP BY lifecycle').fetchall())
            goals_authorized = 'goals:read' in grants and 'local_goals_reader' in tools
            goals = []
            goal_count = None
            if goals_authorized:
                goal_count = con.execute('SELECT COUNT(*) FROM company_goals').fetchone()[0]
                goals = [dict(zip(('title','status'), r)) for r in con.execute(
                    'SELECT title,status FROM company_goals ORDER BY id LIMIT 15')]
        return {
            'chief_name': str(chief[1]),
            'company': dict(zip(('name','description','mission'), company)),
            'department_total': int(total_dept),
            'department_names': departments,
            'employee_total': sum(counts.values()),
            'employee_draft': int(counts.get('draft', 0)),
            'employee_inactive': int(counts.get('inactive', 0)),
            'goals_authorized': goals_authorized,
            'goal_total': goal_count,
            'goals': goals,
        }

    def save_note(self, value: str) -> None:
        self.require_permission("notes:write")
        note = value.strip()
        if not note or len(note) > 120:
            raise ValueError("메모는 1~120자여야 합니다.")
        with self._connect() as con:
            con.execute(
                "INSERT INTO system_metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (CHECKPOINT_KEY, note),
            )

    def read_note(self) -> str:
        self.require_permission("notes:read")
        with self._connect() as con:
            row = con.execute(
                "SELECT value FROM system_metadata WHERE key = ?", (CHECKPOINT_KEY,)
            ).fetchone()
        return row[0] if row else ""

    def health(self) -> dict[str, str]:
        with self._connect() as con:
            result = con.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite 파일 무결성 오류: {result}")
        return {"status": "ok", "database": str(self.path), "storage": "SQLite"}

    # Stage36: schedules are disabled by default; only create unassigned todo records.
    def add_recurring_schedule(self, title: str, description: str = '', interval_minutes: int = 1440) -> int:
        self.require_permission('company:manage')
        heading = self._validated_text(title, '일정 제목', 120, required=True)
        detail = self._validated_text(description, '일정 설명', 1000)
        if type(interval_minutes) is not int or not 5 <= interval_minutes <= 10080:
            raise ValueError('반복 간격은 5~10080분이어야 합니다.')
        with self._connect() as con:
            return int(con.execute('INSERT INTO recurring_task_schedules(title,description,interval_minutes,next_due) VALUES(?,?,?,?)',
                (heading, detail, interval_minutes, int(time.time()) + interval_minutes * 60)).lastrowid)

    def list_recurring_schedules(self) -> list[dict[str, object]]:
        self.require_permission('company:manage')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute('SELECT * FROM recurring_task_schedules ORDER BY id')]

    def set_recurring_schedule_enabled(self, schedule_id: int, enabled: bool) -> None:
        self.require_permission('company:manage')
        self._plan_id(schedule_id, '일정')
        if type(enabled) is not bool:
            raise ValueError('활성 상태가 올바르지 않습니다.')
        with self._connect() as con:
            row = con.execute('SELECT enabled,interval_minutes FROM recurring_task_schedules WHERE id=?', (schedule_id,)).fetchone()
            if row is None:
                raise ValueError('일정을 찾을 수 없습니다.')
            if enabled and not row[0]:
                # Enabling starts a fresh interval, no retroactive runs.
                con.execute('UPDATE recurring_task_schedules SET enabled=1,next_due=? WHERE id=?',
                            (int(time.time()) + row[1]*60, schedule_id))
            else:
                con.execute('UPDATE recurring_task_schedules SET enabled=? WHERE id=?', (int(enabled),schedule_id))

    def run_due_recurring_schedules(self, *, now: int | None = None) -> list[int]:
        self.require_permission('company:manage')
        from desktop.recurring_scheduler import dispatch
        with self._connect() as con:
            # Serialize due selection and occurrence insertion across multiple EXE sessions.
            con.execute('BEGIN IMMEDIATE')
            return dispatch(con, int(time.time()) if now is None else now)

    def list_recurring_skipped_windows(self, *, limit: int = 100) -> list[dict[str, object]]:
        """정기 업무 재시작 때 실행되지 않은 주기 구간을 원본 그대로 조회."""
        self.require_permission('company:manage')
        from desktop.recurring_scheduler import skipped_windows
        with self._connect() as con:
            return skipped_windows(con, limit=limit)

    def list_recurring_occurrences(self) -> list[dict[str, object]]:
        self.require_permission('company:manage')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute('SELECT * FROM recurring_task_occurrences ORDER BY id')]

    # Stage37: local allowlisted events; no external listeners or automatic AI calls.
    def submit_local_event(self, event_key: str, event_type: str, summary: str, details: str = '') -> int:
        self.require_permission('company:manage')
        from desktop.event_task_engine import EVENT_TYPES
        key = self._validated_text(event_key, '이벤트 키', 120, required=True)
        if event_type not in EVENT_TYPES or type(event_type) is not str:
            raise ValueError('지원하지 않는 이벤트 유형입니다.')
        heading = self._validated_text(summary, '이벤트 제목', 100, required=True)
        body = self._validated_text(details, '이벤트 설명', 1000)
        with self._connect() as con:
            con.execute('INSERT OR IGNORE INTO local_task_events(event_key,event_type,summary,details) VALUES(?,?,?,?)',
                        (key,event_type,heading,body))
            return int(con.execute('SELECT id FROM local_task_events WHERE event_key=?', (key,)).fetchone()[0])

    def dispatch_local_events(self, limit: int = 20) -> list[int]:
        self.require_permission('company:manage')
        from desktop.event_task_engine import dispatch
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return dispatch(con, limit)

    def list_local_events(self) -> list[dict[str, object]]:
        self.require_permission('company:manage')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute('SELECT * FROM local_task_events ORDER BY id DESC LIMIT 200')]

    # Stage38: explicit durable queue and bounded retries; no automatic AI invocation.
    def enqueue_task(self, task_id: int, max_attempts: int = 3) -> int:
        self.require_permission('company:manage')
        task_id = self._plan_id(task_id, '업무')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
            raise ValueError('재시도 횟수는 1~10이어야 합니다.')
        from desktop.task_queue import log
        with self._connect() as con:
            task = con.execute('SELECT status FROM company_tasks WHERE id=?',(task_id,)).fetchone()
            if task is None or task[0] in ('done','cancelled'):
                raise ValueError('대기열에 등록할 수 없는 업무입니다.')
            con.execute('INSERT OR IGNORE INTO local_task_queue(task_id,max_attempts) VALUES(?,?)',(task_id,max_attempts))
            row=con.execute('SELECT id FROM local_task_queue WHERE task_id=?',(task_id,)).fetchone()
            queue_id=int(row[0])
            if con.execute('SELECT COUNT(*) FROM local_task_queue_events WHERE queue_id=?',(queue_id,)).fetchone()[0]==0:
                log(con,queue_id,'enqueued')
            return queue_id

    def claim_queued_task(self, *, now: int | None = None) -> dict[str,int] | None:
        self.require_permission('company:manage')
        from desktop.task_queue import claim
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return claim(con,int(time.time()) if now is None else now)

    def resolve_queued_task(self, queue_id: int, success: bool, error: str = '', *, now: int | None = None) -> str:
        self.require_permission('company:manage')
        queue_id=self._plan_id(queue_id,'대기열')
        if type(success) is not bool:
            raise ValueError('결과 유형이 올바르지 않습니다.')
        detail=self._validated_text(error,'오류',500)
        if not success and not detail:
            raise ValueError('실패 사유가 필요합니다.')
        from desktop.task_queue import resolve
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return resolve(con,queue_id,success,detail,int(time.time()) if now is None else now)

    def recover_queued_task(self, queue_id: int, *, now: int | None = None) -> str:
        """Explicit owner recovery; caller must ensure old process is no longer running."""
        self.require_permission('company:manage')
        queue_id = self._plan_id(queue_id, '대기열')
        from desktop.task_queue import recover_claimed
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return recover_claimed(con, queue_id, int(time.time()) if now is None else now)

    def list_queued_tasks(self) -> list[dict[str,object]]:
        self.require_permission('company:manage')
        with self._connect() as con:
            con.row_factory=sqlite3.Row
            return [dict(r) for r in con.execute('SELECT q.*,t.title FROM local_task_queue q JOIN company_tasks t ON t.id=q.task_id ORDER BY q.id DESC')]

    def list_queue_events(self, queue_id: int) -> list[dict[str,object]]:
        self.require_permission('company:manage')
        queue_id=self._plan_id(queue_id,'대기열')
        with self._connect() as con:
            con.row_factory=sqlite3.Row
            return [dict(r) for r in con.execute('SELECT * FROM local_task_queue_events WHERE queue_id=? ORDER BY id',(queue_id,))]

    # Stage41: owner-mediated local message records. No AI sends messages autonomously.
    def send_direct_message(self, sender_id: int, recipient_id: int, subject: str, body: str) -> int:
        self.require_permission("agents:manage")
        from desktop.direct_messages import send
        with self._connect() as con:
            return int(send(con,sender_id,recipient_id,subject,body))

    def list_direct_messages(self, employee_id: int | None = None) -> list[dict]:
        self.require_permission("agents:manage")
        if employee_id is not None and (type(employee_id) is not int or employee_id < 1):
            raise ValueError("유효한 직원 ID가 필요합니다.")
        with self._connect() as con:
            sql="SELECT id,sender_id,recipient_id,subject,body,created_at,read_at FROM employee_direct_messages"
            args=()
            if employee_id is not None:
                sql+=" WHERE sender_id=? OR recipient_id=?"
                args=(employee_id,employee_id)
            rows=con.execute(sql+" ORDER BY id DESC LIMIT 500",args).fetchall()
        return [dict(zip(('id','sender_id','recipient_id','subject','body','created_at','read_at'),r)) for r in rows]

    def mark_direct_message_read(self, message_id: int) -> bool:
        self.require_permission("agents:manage")
        if type(message_id) is not int or message_id < 1:
            raise ValueError("유효한 메시지 ID가 필요합니다.")
        with self._connect() as con:
            result=con.execute("UPDATE employee_direct_messages SET read_at=CURRENT_TIMESTAMP WHERE id=? AND read_at IS NULL",(message_id,))
            return result.rowcount==1

    # Stage42: local owner-mediated, department-scoped collaboration history.
    # Agent autonomy and live messaging are explicitly out of scope.
    def send_department_message(self, department_id: int, sender_id: int, body: str) -> int:
        self.require_permission("agents:manage")
        from desktop.department_chat import send
        with self._connect() as con:
            return send(con, department_id, sender_id, body)

    def list_department_messages(self, department_id: int, limit: int = 200) -> list[dict]:
        self.require_permission("agents:manage")
        from desktop.department_chat import list_messages
        with self._connect() as con:
            return list_messages(con, department_id, limit)

    # Stage43: owner-managed local project coordination rooms (not real business execution).
    def create_project_room(self, name: str, description: str = '') -> int:
        self.require_permission('agents:manage')
        from desktop.project_chat import create_room
        with self._connect() as con:
            return create_room(con, name, description)

    def list_project_rooms(self) -> list[dict]:
        self.require_permission('agents:manage')
        from desktop.project_chat import list_rooms
        with self._connect() as con:
            return list_rooms(con)

    def add_project_participant(self, project_id: int, employee_id: int) -> None:
        self.require_permission('agents:manage')
        from desktop.project_chat import add_participant
        with self._connect() as con:
            add_participant(con, project_id, employee_id)

    def remove_project_participant(self, project_id: int, employee_id: int) -> None:
        self.require_permission('agents:manage')
        from desktop.project_chat import remove_participant
        with self._connect() as con:
            remove_participant(con, project_id, employee_id)

    def list_project_participants(self, project_id: int) -> list[dict]:
        self.require_permission('agents:manage')
        from desktop.project_chat import list_participants
        with self._connect() as con:
            return list_participants(con, project_id)

    def send_project_message(self, project_id: int, sender_id: int, body: str) -> int:
        self.require_permission('agents:manage')
        from desktop.project_chat import send
        with self._connect() as con:
            return send(con, project_id, sender_id, body)

    def list_project_messages(self, project_id: int, limit: int = 200) -> list[dict]:
        self.require_permission('agents:manage')
        from desktop.project_chat import list_messages
        with self._connect() as con:
            return list_messages(con, project_id, limit)

    # Stage44: local owner-only meeting agenda and attendee records.
    # The meetings are not AI-generated discussions or decisions.
    def create_meeting(self, title: str, purpose: str = '') -> int:
        self.require_permission('agents:manage')
        from desktop.meetings import create
        with self._connect() as con:
            return create(con, title, purpose)

    def list_meetings(self) -> list[dict]:
        self.require_permission('agents:manage')
        from desktop.meetings import list_meetings
        with self._connect() as con:
            return list_meetings(con)

    def read_meeting(self, meeting_id: int) -> dict:
        self.require_permission('agents:manage')
        from desktop.meetings import read
        with self._connect() as con:
            return read(con, meeting_id)

    def add_meeting_agenda(self, meeting_id: int, topic: str) -> int:
        self.require_permission('agents:manage')
        from desktop.meetings import add_agenda
        with self._connect() as con:
            return add_agenda(con, meeting_id, topic)

    def add_meeting_attendee(self, meeting_id: int, employee_id: int) -> None:
        self.require_permission('agents:manage')
        from desktop.meetings import add_attendee
        with self._connect() as con:
            add_attendee(con, meeting_id, employee_id)

    def remove_meeting_attendee(self, meeting_id: int, employee_id: int) -> None:
        self.require_permission('agents:manage')
        from desktop.meetings import remove_attendee
        with self._connect() as con:
            remove_attendee(con, meeting_id, employee_id)

    def set_meeting_status(self, meeting_id: int, status: str) -> None:
        self.require_permission('agents:manage')
        from desktop.meetings import set_status
        with self._connect() as con:
            set_status(con, meeting_id, status)

    # Stage45: administrator-recorded opinions. Nothing is generated by AI.
    def add_meeting_opinion(self, meeting_id: int, agenda_id: int, employee_id: int,
                            stance: str, reasoning: str, evidence: str = '', alternative: str = '') -> int:
        self.require_permission('agents:manage')
        from desktop.meeting_opinions import add
        with self._connect() as con:
            return add(con, meeting_id, agenda_id, employee_id, stance, reasoning, evidence, alternative)

    def run_real_meeting_employee_opinion(self, meeting_id: int, agenda_id: int,
                                          employee_id: int, *, cancel=None) -> dict:
        from desktop.company_meeting_ai import run_one
        return run_one(self, meeting_id, agenda_id, employee_id, cancel=cancel)

    def run_real_meeting_attendees(self, meeting_id: int, agenda_id: int, *,
                                   cancel=None, timeout: int=90, max_employees: int=30) -> dict:
        from desktop.company_meeting_ai import run_attendees
        return run_attendees(self,meeting_id,agenda_id,cancel=cancel,
                             timeout=timeout,max_employees=max_employees)

    def real_meeting_opinion_audit(self, meeting_id: int) -> list[dict]:
        from desktop.company_meeting_ai import report
        return report(self, meeting_id)

    def list_meeting_opinions(self, meeting_id: int) -> list[dict]:
        self.require_permission('agents:manage')
        from desktop.meeting_opinions import list_opinions
        with self._connect() as con:
            return list_opinions(con, meeting_id)

    def compare_meeting_opinions(self, meeting_id: int) -> dict:
        self.require_permission('agents:manage')
        from desktop.meeting_opinions import compare
        with self._connect() as con:
            return compare(con, meeting_id)

    # Stage46: deliberate authenticated owner decisions and linked local todo records.
    def decide_meeting_agenda(self, meeting_id: int, agenda_id: int,
                              outcome: str, rationale: str, acknowledge: bool = False) -> int:
        self.require_permission('agents:manage')
        self.require_permission('company:manage')
        from desktop.meeting_decisions import decide
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return decide(con, meeting_id, agenda_id, outcome, rationale, acknowledge)

    def create_meeting_followup(self, decision_id: int, employee_id: int,
                                title: str, description: str = '') -> int:
        self.require_permission('agents:manage')
        self.require_permission('company:manage')
        from desktop.meeting_decisions import create_followup
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create_followup(con, decision_id, employee_id, title, description)

    def list_meeting_decisions(self, meeting_id: int) -> list[dict]:
        self.require_permission('agents:manage')
        self.require_permission('company:manage')
        from desktop.meeting_decisions import list_decisions
        with self._connect() as con:
            return list_decisions(con, meeting_id)

    # Stage48: owner-only company shared knowledge (not automatically exposed to agents).
    def create_company_knowledge(self, kind: str, title: str, content: str, source: str) -> int:
        self.require_permission('company:manage')
        from desktop.company_knowledge import create
        with self._connect() as con:
            return int(create(con, kind, title, content, source))

    def list_company_knowledge(self, *, include_archived: bool = False, limit: int = 200) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.company_knowledge import list_documents
        with self._connect() as con:
            return list_documents(con, include_archived=include_archived, limit=limit)

    def read_company_knowledge(self, document_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.company_knowledge import read
        with self._connect() as con:
            return read(con, document_id)

    def archive_company_knowledge(self, document_id: int) -> bool:
        self.require_permission('company:manage')
        from desktop.company_knowledge import archive
        with self._connect() as con:
            return archive(con, document_id)

    # Stage49: administrator search/source metadata and simulated employee read ACL.
    # These APIs require owner login; there are NO employee sessions yet.
    def search_company_knowledge(self, query: str = '', *, include_archived: bool = False,
                                 limit: int = 200) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.knowledge_access import search
        with self._connect() as con:
            return search(con, query, include_archived=include_archived, limit=limit)

    def set_company_knowledge_visibility(self, document_id: int, mode: str) -> bool:
        self.require_permission('company:manage')
        from desktop.knowledge_access import set_mode
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return set_mode(con, document_id, mode)

    def grant_company_knowledge_read(self, document_id: int, employee_id: int) -> bool:
        self.require_permission('company:manage')
        from desktop.knowledge_access import grant
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return grant(con, document_id, employee_id)

    def revoke_company_knowledge_read(self, document_id: int, employee_id: int) -> bool:
        self.require_permission('company:manage')
        from desktop.knowledge_access import revoke
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return revoke(con, document_id, employee_id)

    def read_company_knowledge_access(self, document_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.knowledge_access import access_info
        with self._connect() as con:
            return access_info(con, document_id)

    def add_company_knowledge_source(self, document_id: int, source_type: str, reference: str) -> int:
        self.require_permission('company:manage')
        from desktop.knowledge_access import add_source
        with self._connect() as con:
            return add_source(con, document_id, source_type, reference)

    def list_company_knowledge_sources(self, document_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.knowledge_access import list_sources
        with self._connect() as con:
            return list_sources(con, document_id)

    def preview_employee_knowledge_search(self, employee_id: int, query: str = '', *,
                                          limit: int = 200) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.knowledge_access import search, _positive_int
        _positive_int(employee_id, '직원 ID')  # Never fall back to unrestricted owner search.
        with self._connect() as con:
            return search(con, query, employee_id=employee_id, limit=limit)

    def preview_employee_knowledge_read(self, employee_id: int, document_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.knowledge_access import preview_read
        with self._connect() as con:
            return preview_read(con, document_id, employee_id)

    # Stage47: owner-only, employee-scoped local memory. No AI retrieval automation.
    def save_employee_memory(self, employee_id: int, kind: str, title: str,
                             content: str, source: str, confidence: int = 70,
                             expires_on: str | None = None) -> int:
        self.require_permission('agents:manage')
        from desktop.employee_memory import save
        with self._connect() as con:
            return int(save(con, employee_id, kind, title, content, source, confidence, expires_on))

    def list_employee_memories(self, employee_id: int, *, query: str = '',
                               include_archived: bool = False, include_expired: bool = False,
                               limit: int = 200) -> list[dict]:
        self.require_permission('agents:manage')
        from desktop.employee_memory import list_memories
        with self._connect() as con:
            return list_memories(con, employee_id, query=query, include_archived=include_archived,
                                 include_expired=include_expired, limit=limit)

    def read_employee_memory(self, employee_id: int, memory_id: int) -> dict:
        self.require_permission('agents:manage')
        from desktop.employee_memory import read
        with self._connect() as con:
            return read(con, employee_id, memory_id)

    def archive_employee_memory(self, employee_id: int, memory_id: int) -> bool:
        self.require_permission('agents:manage')
        from desktop.employee_memory import archive
        with self._connect() as con:
            return archive(con, employee_id, memory_id)

    # Stage50: evidence-linked manual evaluations and non-executing improvement proposals.
    def task_performance_summary(self) -> dict:
        self.require_permission('company:manage')
        from desktop.performance_reviews import task_summary
        with self._connect() as con:
            return task_summary(con)

    def review_task_performance(self, task_id: int, rating: int, evidence: str, lesson: str) -> int:
        self.require_permission('company:manage')
        from desktop.performance_reviews import review_task
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return review_task(con, task_id, rating, evidence, lesson)

    def list_task_performance_reviews(self, limit: int = 200) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.performance_reviews import list_reviews
        with self._connect() as con:
            return list_reviews(con, limit)

    def create_task_improvement(self, review_id: int, title: str, action: str, expected_result: str) -> int:
        self.require_permission('company:manage')
        from desktop.performance_reviews import create_proposal
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create_proposal(con, review_id, title, action, expected_result)

    def list_task_improvements(self, limit: int = 200) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.performance_reviews import list_proposals
        with self._connect() as con:
            return list_proposals(con, limit)

    def decide_task_improvement(self, proposal_id: int, decision: str, reason: str) -> bool:
        self.require_permission('company:manage')
        from desktop.performance_reviews import decide_proposal
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return decide_proposal(con, proposal_id, decision, reason)

    # Stage51: administrator-only metadata registration; never loads or runs tools.
    def register_ai_tool(self, tool_key: str, name: str, category: str,
                         description: str, required_capability: str = '') -> int:
        self.require_permission('company:manage')
        from desktop.tool_registry import register
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return register(con, tool_key, name, category, description, required_capability)

    def list_registered_ai_tools(self, *, include_retired: bool = False, limit: int = 200) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.tool_registry import list_tools
        with self._connect() as con:
            return list_tools(con, include_retired=include_retired, limit=limit)

    def read_registered_ai_tool(self, tool_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.tool_registry import read
        with self._connect() as con:
            return read(con, tool_id)

    def retire_registered_ai_tool(self, tool_id: int, reason: str) -> bool:
        self.require_permission('company:manage')
        from desktop.tool_registry import retire
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return retire(con, tool_id, reason)

    def registered_ai_tool_audit(self, tool_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.tool_registry import audit
        with self._connect() as con:
            return audit(con, tool_id)

    # Stage52: owner-only request/approval/preflight. NEVER an execution entry point.
    def request_ai_tool_use(self, request_key: str, tool_id: int, employee_id: int,
                            purpose: str) -> int:
        self.require_permission('company:manage')
        from desktop.tool_approvals import request
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return request(con, request_key, tool_id, employee_id, purpose)

    def list_ai_tool_use_requests(self, limit: int = 200) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.tool_approvals import list_requests
        with self._connect() as con:
            return list_requests(con, limit)

    def decide_ai_tool_use(self, request_id: int, decision: str, reason: str) -> bool:
        self.require_permission('company:manage')
        from desktop.tool_approvals import decide
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return decide(con, request_id, decision, reason)

    def check_ai_tool_use(self, request_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.tool_approvals import preflight
        with self._connect() as con:
            return preflight(con, request_id)

    def read_ai_tool_use_request(self, request_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.tool_approvals import get_request
        with self._connect() as con:
            return get_request(con, request_id)

    def execute_approved_local_read_tool(self, request_id: int) -> dict:
        from desktop.company_approved_tool_execution import execute
        return execute(self, request_id)

    def approved_local_read_tool_history(self, limit: int = 30) -> list[dict]:
        from desktop.company_approved_tool_execution import history
        return history(self, limit)

    def execute_approved_windows_version_tool(self, request_id: int) -> dict:
        from desktop.company_native_diagnostics import execute
        return execute(self, request_id)

    def approved_windows_version_tool_history(self, limit: int = 30) -> list[dict]:
        from desktop.company_native_diagnostics import history
        return history(self, limit)

    def inspect_and_cancel_stale_windows_tool(self, request_id: int,
                                              owner_confirmed: bool, operator_note: str) -> dict:
        from desktop.company_native_diagnostics import cancel_stale_run_after_owner_inspection
        return cancel_stale_run_after_owner_inspection(self, request_id,
                                                        owner_confirmed, operator_note)

    def approved_windows_tool_recovery_history(self, limit: int = 30) -> list[dict]:
        from desktop.company_native_diagnostics import recovery_history
        return recovery_history(self, limit)

    def ai_tool_use_audit(self, request_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.tool_approvals import audit
        with self._connect() as con:
            return audit(con, request_id)

    # Stage53: owner-operated local UTF-8 files only; not AI tool execution.
    @property
    def documents_dir(self) -> Path:
        return self.path.parent / 'managed_documents'

    def create_managed_document(self, filename: str, content: str) -> int:
        self.require_permission('company:manage')
        from desktop.managed_documents import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create(con, self.documents_dir, filename, content)

    def update_managed_document(self, document_id: int, content: str, expected_version: int) -> int:
        self.require_permission('company:manage')
        from desktop.managed_documents import update
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return update(con, self.documents_dir, document_id, content, expected_version)

    def list_managed_documents(self, limit: int = 200) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.managed_documents import list_documents
        with self._connect() as con:
            return list_documents(con, limit)

    def read_managed_document(self, document_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.managed_documents import read_content
        with self._connect() as con:
            return read_content(con, self.documents_dir, document_id)

    def managed_document_revisions(self, document_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.managed_documents import revisions
        with self._connect() as con:
            return revisions(con, document_id)

    # Stage56: owner-reviewed local Python code files. Never execute generated code.
    @property
    def code_dir(self) -> Path:
        return self.path.parent / 'code_drafts'

    def save_code_draft(self, filename: str, source: str, expected_version: int, *, from_model: bool = False) -> dict:
        self.require_permission('company:manage')
        from desktop.code_authoring import save_code
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return save_code(con, self.code_dir, filename, source, expected_version, from_model=from_model)

    def list_code_drafts(self) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.code_authoring import list_code
        with self._connect() as con:
            return list_code(con)

    def read_code_draft(self, artifact_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.code_authoring import read_code
        with self._connect() as con:
            return read_code(con, self.code_dir, artifact_id)

    def code_draft_history(self, artifact_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.code_authoring import history
        with self._connect() as con:
            return history(con, artifact_id)

    # Stage57: strictly limited AST evaluator, not arbitrary Python execution or an OS sandbox.
    def run_restricted_code_tests(self, artifact_id: int, assertions: str) -> dict:
        self.require_permission('company:manage')
        from desktop.restricted_code_tests import execute_restricted_tests, record
        artifact = self.read_code_draft(artifact_id)  # checks file hash and version
        result = execute_restricted_tests(artifact['source'], assertions)
        # Recheck source immediately before recording to detect changed/updated files.
        current = self.read_code_draft(artifact_id)
        if current['version'] != artifact['version'] or current['digest'] != artifact['digest']:
            raise ValueError('검사 중 파일 버전이 변경되었습니다.')
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT version,digest FROM local_code_artifacts WHERE id=?', (artifact_id,)).fetchone()
            if not row or row[0] != artifact['version'] or row[1] != artifact['digest']:
                raise ValueError('검사 중 DB 버전이 변경되었습니다.')
            result['run_id'] = record(con, artifact, result)
        return result

    def list_restricted_code_tests(self, artifact_id: int) -> list[dict]:
        self.require_permission('company:manage')
        if type(artifact_id) is not int or artifact_id < 1:
            raise ValueError('유효한 코드 ID가 필요합니다.')
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute("""SELECT id,version,source_digest,tests_digest,
                passed,total,status,created_at FROM restricted_code_test_runs
                WHERE artifact_id=? ORDER BY id DESC LIMIT 50""", (artifact_id,))]

    # Stage58: fixed local image/video/document adapter boundary; no renderer or executor.
    def list_media_adapters(self) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.media_tool_adapters import available_adapters
        return available_adapters()

    def inspect_media_file(self, path: str, adapter_key: str) -> dict:
        self.require_permission('company:manage')
        from desktop.media_tool_adapters import inspect_local, record
        from desktop.tool_use_audit import record as audit_record
        try:
            result = inspect_local(path, adapter_key)
            with self._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                result['id'] = record(con, result)
                audit_record(con, 'media_inspect', 'success', reference_id=result['id'])
            return result
        except (ValueError, OSError) as exc:
            self._record_tool_failure('media_inspect', exc)
            raise

    def media_inspection_history(self, limit: int = 50) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.media_tool_adapters import history
        with self._connect() as con:
            return history(con, limit)

    # Stage59: non-transmitting local integration plans and immutable owner reviews.
    def list_service_contracts(self) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.offline_service_integrations import available_contracts
        return available_contracts()

    def prepare_service_draft(self, kind: str, target: str, title: str, body: str) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_service_integrations import prepare
        from desktop.tool_use_audit import record as audit_record
        try:
            with self._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                result = prepare(con, kind, target, title, body)
                audit_record(con, 'service_draft_prepare', 'success', reference_id=result['id'])
                return result
        except (ValueError, OSError) as exc:
            self._record_tool_failure('service_draft_prepare', exc)
            raise

    def review_service_draft(self, draft_id: int, accept: bool, note: str = '') -> dict:
        self.require_permission('company:manage')
        from desktop.offline_service_integrations import review
        from desktop.tool_use_audit import record as audit_record
        try:
            with self._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                result = review(con, draft_id, accept, note)
                audit_record(con, 'service_draft_review', 'success', reference_id=draft_id)
                return result
        except (ValueError, OSError) as exc:
            self._record_tool_failure('service_draft_review', exc)
            raise

    def service_draft_detail(self, draft_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_service_integrations import detail
        with self._connect() as con:
            return detail(con, draft_id)

    def service_draft_history(self, limit: int = 50) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.offline_service_integrations import history
        with self._connect() as con:
            return history(con, limit)

    # Stage60: local-only tool audit; no automatic retry or external dispatch.
    def tool_use_history(self, limit: int = 50) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.tool_use_audit import history
        with self._connect() as con:
            return history(con, limit)

    def review_tool_failure(self, event_id: int, action: str, note: str = '') -> dict:
        self.require_permission('company:manage')
        from desktop.tool_use_audit import failure_action
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return failure_action(con, event_id, action, note)

    def _record_tool_failure(self, operation: str, exc: Exception) -> None:
        from desktop.tool_use_audit import classify, record
        try:
            with self._connect() as con:
                con.execute('BEGIN IMMEDIATE')
                record(con, operation, 'failure', classify(exc))
        except sqlite3.Error:
            # Do not replace the original failure if the audit database is unavailable.
            pass

    # Stage61: owner-only local generic business portfolio (no external operation).
    def business_types(self, include_disabled: bool = True) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.business_portfolio import types
        with self._connect() as con:
            return types(con, include_disabled)

    def add_business_type(self, key: str, title: str, description: str = '') -> int:
        self.require_permission('company:manage')
        from desktop.business_portfolio import add_type
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return add_type(con, key, title, description)

    def disable_business_type(self, type_id: int) -> None:
        self.require_permission('company:manage')
        from desktop.business_portfolio import disable_type
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            disable_type(con, type_id)

    def create_business(self, type_id: int, name: str, goal: str, budget_krw: int = 0,
                        owner_employee_id: int | None = None) -> int:
        self.require_permission('company:manage')
        from desktop.business_portfolio import add_business
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return add_business(con, type_id, name, goal, budget_krw, owner_employee_id)

    def list_businesses(self, limit: int = 200) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.business_portfolio import businesses
        with self._connect() as con:
            return businesses(con, limit)

    def set_business_state(self, business_id: int, state: str) -> dict:
        self.require_permission('company:manage')
        from desktop.business_portfolio import change_state
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return change_state(con, business_id, state)

    def set_business_participant(self, business_id: int, employee_id: int, add: bool) -> None:
        self.require_permission('company:manage')
        from desktop.business_portfolio import participant
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            participant(con, business_id, employee_id, add)

    def business_participants(self, business_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.business_portfolio import participants
        with self._connect() as con:
            return participants(con, business_id)

    def business_events(self, business_id: int | None = None, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.business_portfolio import events
        with self._connect() as con:
            return events(con, business_id, limit)

    # Actual chief-GGUF business hypotheses are separate from rule templates.
    # No business, sale, external request, or owner approval is automatic.
    def propose_chief_business_idea(self, audience: str, problem: str, *, cancel=None) -> dict:
        self.require_permission('company:manage')
        self.require_permission('agents:manage')
        from desktop.company_business_ideas_model import propose
        return propose(self,audience,problem,cancel=cancel)

    def list_chief_business_ideas(self, *, limit: int=50) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.company_business_ideas_model import list_ideas
        return list_ideas(self,limit=limit)

    def review_chief_business_idea(self, idea_id: int, decision: str,
                                   reason: str) -> dict:
        self.require_permission('company:manage')
        from desktop.company_business_ideas_model import decide
        return decide(self,idea_id,decision,reason)

    def create_chief_business_draft(self, idea_id: int, name: str) -> dict:
        self.require_permission('company:manage')
        from desktop.company_business_ideas_model import create_owner_approved_business_draft
        return create_owner_approved_business_draft(self,idea_id,name)

    def list_chief_business_draft_links(self, *, limit: int=100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.company_business_ideas_model import list_business_draft_links
        return list_business_draft_links(self,limit=limit)

    def create_chief_idea_project_draft(self, idea_id: int, title: str,
                                       owner_note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.company_business_idea_pipeline import create_project_draft
        return create_project_draft(self,idea_id,title,owner_note)

    def create_chief_idea_first_product_draft(self, idea_id: int, kind: str,
                                             product_name: str,
                                             delivery_note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.company_business_idea_pipeline import create_product_draft
        return create_product_draft(self,idea_id,kind,product_name,delivery_note)

    def chief_idea_pipeline_history(self, *, limit: int=100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.company_business_idea_pipeline import history
        return history(self,limit=limit)

    def create_chief_idea_delivery_tasks(self, idea_id: int, research_title: str,
                                         product_title: str, owner_note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.company_business_idea_delivery import create_owner_work_tasks
        return create_owner_work_tasks(self, idea_id, research_title, product_title, owner_note)

    def review_chief_idea_local_product(self, idea_id: int,
                                        research_artifact_id: int,
                                        product_artifact_id: int,
                                        owner_note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.company_business_idea_delivery import review_local_product
        return review_local_product(self, idea_id, research_artifact_id,
                                    product_artifact_id, owner_note)

    def chief_idea_delivery_history(self, *, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.company_business_idea_delivery import history
        return history(self, limit=limit)

    def export_chief_idea_local_product(self, idea_id: int) -> dict:
        """관리자 승인형 실제 직원 조사·제작 결과 로컬 파일만 생성."""
        self.require_permission('company:manage')
        from desktop.company_business_idea_artifact_export import export
        return export(self, idea_id)

    def read_chief_idea_local_product(self, export_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.company_business_idea_artifact_export import read
        return read(self, export_id)

    def inspect_chief_idea_local_products(self, limit: int=100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.company_business_idea_artifact_export import inspect
        return inspect(self, limit=limit)

    # Stage63: actual owner-confirmed public HTTPS evidence for chief model ideas.
    def fetch_chief_business_market_source(self, idea_id: int, url: str,
                                            hostname: str, title: str,
                                            *, owner_confirmed: bool=False,
                                            cancel=None) -> dict:
        self.require_permission('company:manage')
        from desktop.company_business_market_research import capture_source
        return capture_source(self,idea_id,url,hostname,title,
                              owner_confirmed=owner_confirmed,cancel=cancel)

    def list_chief_business_market_sources(self, idea_id: int, *, limit: int=100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.company_business_market_research import history
        return history(self,idea_id,limit)

    # Stage63: genuine local chief GGUF analysis of the actual owner-captured URLs.
    def analyze_chief_business_market(self, idea_id: int, *, cancel=None) -> dict:
        self.require_permission('company:manage')
        self.require_permission('agents:manage')
        from desktop.company_business_market_ai import analyze
        return analyze(self,idea_id,cancel=cancel)

    def chief_business_market_analysis_history(self, idea_id: int, *, limit: int=50) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.company_business_market_ai import history
        return history(self,idea_id,limit)

    # Stage65: real local GGUF over owner-authored Stage64 financial scenarios.
    def analyze_real_chief_financial_brief(self, brief_id: int, *, cancel=None) -> dict:
        self.require_permission('company:manage')
        self.require_permission('agents:manage')
        from desktop.company_real_chief_financial_brief import analyze
        return analyze(self,brief_id,cancel=cancel)

    def real_chief_financial_brief_history(self, *, limit: int=100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.company_real_chief_financial_brief import history
        return history(self,limit=limit)

    # Stage62: offline candidate hypotheses from administrator-provided assumptions.
    def generate_business_candidates(self, audience: str, problem: str,
                                     max_candidates: int = 8) -> dict:
        self.require_permission('company:manage')
        from desktop.business_discovery import generate
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return generate(con, audience, problem, max_candidates)

    def business_candidates(self, state: str | None = None, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.business_discovery import candidates
        with self._connect() as con:
            return candidates(con, state, limit)

    def set_business_candidate_state(self, candidate_id: int, state: str) -> dict:
        self.require_permission('company:manage')
        from desktop.business_discovery import change_state
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return change_state(con, candidate_id, state)

    def business_candidate_events(self, candidate_id: int, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.business_discovery import events
        with self._connect() as con:
            return events(con, candidate_id, limit)

    def business_candidate_runs(self, limit: int = 50) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.business_discovery import runs
        with self._connect() as con:
            return runs(con, limit)

    # Stage63: administrator-curated local source excerpts for market research review.
    def link_market_evidence(self, candidate_id: int, capture_id: int, kind: str,
                             stance: str, excerpt: str, note: str) -> int:
        self.require_permission('company:manage')
        from desktop.market_evidence import link
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return link(con, candidate_id, capture_id, kind, stance, excerpt, note)

    def market_evidence(self, candidate_id: int, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.market_evidence import evidence
        with self._connect() as con:
            return evidence(con, candidate_id, limit)

    def review_market_evidence(self, link_id: int, state: str) -> dict:
        self.require_permission('company:manage')
        from desktop.market_evidence import review
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return review(con, link_id, state)

    def market_evidence_events(self, link_id: int, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.market_evidence import events
        with self._connect() as con:
            return events(con, link_id, limit)

    def market_evidence_summary(self, candidate_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.market_evidence import summary
        with self._connect() as con:
            return summary(con, candidate_id)

    # Stage64: owner-entered offline financial assumptions only; no real revenue.
    def evaluate_financial_scenario(self, subject_kind: str, subject_id: int,
                                    assumptions: dict, owner_note: str) -> int:
        self.require_permission('company:manage')
        from desktop.financial_feasibility import evaluate
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return evaluate(con, subject_kind, subject_id, assumptions, owner_note)

    def financial_scenario_report(self, evaluation_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.financial_feasibility import report
        with self._connect() as con:
            return report(con, evaluation_id)

    def financial_scenario_history(self, subject_kind: str, subject_id: int,
                                   limit: int = 30) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.financial_feasibility import history
        with self._connect() as con:
            return history(con, subject_kind, subject_id, limit)

    # Stage65: owner-only offline comparison briefs; NEVER executes a business.
    def create_chief_business_brief(self, evaluation_ids: list[int], owner_note: str) -> int:
        self.require_permission('company:manage')
        from desktop.chief_business_decisions import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create(con, evaluation_ids, owner_note)

    def chief_business_brief(self, brief_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.chief_business_decisions import get
        with self._connect() as con:
            return get(con, brief_id)

    def review_chief_business_brief(self, brief_id: int, action: str) -> dict:
        self.require_permission('company:manage')
        from desktop.chief_business_decisions import review
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return review(con, brief_id, action)

    def chief_business_brief_history(self, limit: int = 30) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.chief_business_decisions import history
        with self._connect() as con:
            return history(con, limit)

    # Stage66: owner-only local multi-business project planning and task links.
    def create_business_project(self, business_id: int, title: str, objective: str,
                                planned_budget_krw: int = 0,
                                responsible_employee_id: int | None = None) -> int:
        self.require_permission('company:manage')
        from desktop.business_projects import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create(con, business_id, title, objective, planned_budget_krw, responsible_employee_id)

    def business_project(self, project_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.business_projects import get
        with self._connect() as con:
            return get(con, project_id)

    def business_projects(self, business_id: int | None = None, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.business_projects import list_projects
        with self._connect() as con:
            return list_projects(con, business_id, limit)

    def set_business_project_state(self, project_id: int, new_state: str) -> dict:
        self.require_permission('company:manage')
        from desktop.business_projects import change_state
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return change_state(con, project_id, new_state)

    def set_business_project_task(self, project_id: int, task_id: int, add: bool) -> dict:
        self.require_permission('company:manage')
        from desktop.business_projects import set_task_link
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return set_task_link(con, project_id, task_id, add)

    def business_project_events(self, project_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.business_projects import events
        with self._connect() as con:
            return events(con, project_id)

    # Stage67: owner-only offline product/service information, never publication or sale.
    def create_catalog_item(self, business_id: int, kind: str, name: str,
                            description: str, assumed_price_krw: int,
                            delivery_note: str, project_id: int | None = None) -> int:
        self.require_permission('company:manage')
        from desktop.product_catalog import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create(con, business_id, kind, name, description,
                          assumed_price_krw, delivery_note, project_id)

    def catalog_item(self, item_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.product_catalog import get
        with self._connect() as con:
            return get(con, item_id)

    def catalog_items(self, business_id: int | None = None, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.product_catalog import list_items
        with self._connect() as con:
            return list_items(con, business_id, limit)

    def revise_catalog_item(self, item_id: int, description: str,
                            assumed_price_krw: int, delivery_note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.product_catalog import revise
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return revise(con, item_id, description, assumed_price_krw, delivery_note)

    def set_catalog_item_state(self, item_id: int, new_state: str) -> dict:
        self.require_permission('company:manage')
        from desktop.product_catalog import change_state
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return change_state(con, item_id, new_state)

    def catalog_item_events(self, item_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.product_catalog import events
        with self._connect() as con:
            return events(con, item_id)

    # Stage68: owner-triggered static HTML prototype only; no AI creation or release.
    def create_product_prototype(self, catalog_item_id: int) -> int:
        self.require_permission('company:manage')
        from desktop.product_production import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create(con, self.path, catalog_item_id)

    def product_prototype(self, prototype_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.product_production import get
        with self._connect() as con:
            return get(con, self.path, prototype_id)

    def product_prototypes(self, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.product_production import list_prototypes
        with self._connect() as con:
            return list_prototypes(con, self.path, limit)

    def set_product_prototype_state(self, prototype_id: int, state: str) -> dict:
        self.require_permission('company:manage')
        from desktop.product_production import change_state
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return change_state(con, self.path, prototype_id, state)

    def product_prototype_events(self, prototype_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.product_production import events
        with self._connect() as con:
            return events(con, self.path, prototype_id)

    # Stage69: owner-reported checklist only. No actual release approval.
    def record_product_release_review(self, prototype_id: int, checklist: dict,
                                      note: str, decision: str = 'HOLD_NO_RELEASE') -> dict:
        self.require_permission('company:manage')
        from desktop.product_release_review import record
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return record(con, self.path, prototype_id, checklist, note, decision)

    def product_release_review_history(self, prototype_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.product_release_review import history
        with self._connect() as con:
            return history(con, self.path, prototype_id)

    def product_release_review_summary(self, prototype_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.product_release_review import summary
        with self._connect() as con:
            return summary(con, self.path, prototype_id)

    # Stage71: offline, disconnected sales-channel contract drafts only.
    def create_sales_channel_contract(self, operations_plan_id: int, channel_kind: str,
                                      display_name: str, region: str, integration_mode: str,
                                      planned_scopes, mapping_note: str, compliance_note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.sales_channel_contracts import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create(con, self.path, operations_plan_id, channel_kind, display_name,
                          region, integration_mode, planned_scopes, mapping_note, compliance_note)

    def sales_channel_contract(self, contract_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.sales_channel_contracts import get
        with self._connect() as con:
            return get(con, self.path, contract_id)

    def sales_channel_contracts(self, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.sales_channel_contracts import list_contracts
        with self._connect() as con:
            return list_contracts(con, self.path, limit)

    def sales_channel_contract_events(self, contract_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.sales_channel_contracts import history
        with self._connect() as con:
            return history(con, self.path, contract_id)

    def review_sales_channel_contract(self, contract_id: int, checklist: dict, note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.sales_channel_contracts import review
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return review(con, self.path, contract_id, checklist, note)

    def retire_sales_channel_contract(self, contract_id: int, note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.sales_channel_contracts import retire
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return retire(con, self.path, contract_id, note)

    # Stage72: inert unpublished listing/price drafts, no channel communication.
    def create_unpublished_listing(self, contract_id: int, catalog_item_id: int,
                                   title: str, description: str, currency: str,
                                   price_minor: int, price_note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_listing_prices import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create(con, self.path, contract_id, catalog_item_id, title,
                          description, currency, price_minor, price_note)

    def unpublished_listing(self, listing_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_listing_prices import get
        with self._connect() as con:
            return get(con, self.path, listing_id)

    def unpublished_listings(self, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.offline_listing_prices import list_drafts
        with self._connect() as con:
            return list_drafts(con, self.path, limit)

    def unpublished_listing_history(self, listing_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.offline_listing_prices import history
        with self._connect() as con:
            return history(con, self.path, listing_id)

    def revise_unpublished_listing(self, listing_id: int, title: str,
                                   description: str, currency: str,
                                   price_minor: int, price_note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_listing_prices import revise
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return revise(con, self.path, listing_id, title, description,
                          currency, price_minor, price_note)

    def review_unpublished_listing(self, listing_id: int, note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_listing_prices import review
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return review(con, self.path, listing_id, note)

    def retire_unpublished_listing(self, listing_id: int, note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_listing_prices import retire
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return retire(con, self.path, listing_id, note)

    # Stage73: local simulation ONLY. Never create real orders or payment records.
    def create_simulated_order(self, listing_id: int, client_token: str, quantity: int) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_order_simulations import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create(con, self.path, listing_id, client_token, quantity)

    def simulated_order(self, order_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_order_simulations import get
        with self._connect() as con:
            return get(con, self.path, order_id)

    def simulated_orders(self, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.offline_order_simulations import list_orders
        with self._connect() as con:
            return list_orders(con, self.path, limit)

    def simulated_order_history(self, order_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.offline_order_simulations import history
        with self._connect() as con:
            return history(con, self.path, order_id)

    def transition_simulated_order(self, order_id: int, action: str, note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_order_simulations import transition
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return transition(con, self.path, order_id, action, note)

    # Stage70: future service operations planning; never a deploy/release operation.
    def create_service_operations_plan(self, prototype_id: int, environment: str,
                                       operations_note: str, backup_plan: str,
                                       rollback_plan: str, monitoring_plan: str) -> dict:
        self.require_permission('company:manage')
        from desktop.service_operations_plan import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create(con, self.path, prototype_id, environment, operations_note,
                          backup_plan, rollback_plan, monitoring_plan)

    def service_operations_plan(self, plan_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.service_operations_plan import get
        with self._connect() as con:
            return get(con, self.path, plan_id)

    def service_operations_plans(self, limit: int = 100) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.service_operations_plan import list_plans
        with self._connect() as con:
            return list_plans(con, self.path, limit)

    def service_operations_events(self, plan_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.service_operations_plan import history
        with self._connect() as con:
            return history(con, self.path, plan_id)

    def record_service_readiness(self, plan_id: int, checklist: dict, note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.service_operations_plan import record_readiness
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return record_readiness(con, self.path, plan_id, checklist, note)

    def retire_service_operations_plan(self, plan_id: int, note: str) -> dict:
        self.require_permission('company:manage')
        from desktop.service_operations_plan import retire
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return retire(con, self.path, plan_id, note)

    # Stage54: manual offline research evidence; no HTTP request or model invocation.
    def add_offline_research(self, source_url: str, title: str, content: str,
                             capture_kind: str = 'manual_text') -> int:
        self.require_permission('company:manage')
        from desktop.research_captures import add
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return add(con, source_url, title, content, capture_kind)

    def fetch_public_research(self, url: str, confirmed_hostname: str,
                              title: str, *, consent: bool = False) -> dict:
        """One explicit public HTTPS GET; no credentials, redirects, or posting.

        Never interpret a successful read as source truth or real market demand.
        """
        self.require_permission('company:manage')
        from desktop.public_web_research import read_public_https, save_success
        result = read_public_https(url, confirmed_hostname, consent=consent)
        self.require_permission('company:manage')  # Recheck after blocking I/O / logout.
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return save_success(con, result, title)

    def crawl_public_site(self, url: str, confirmed_hostname: str, *, consent: bool = False,
                          max_pages: int = 3, max_depth: int = 1) -> dict:
        """Administrator-triggered bounded public HTTPS crawl; no scheduled requests."""
        self.require_permission('company:manage')
        from desktop.public_site_crawler import crawl_site, save_crawl
        crawl = crawl_site(url, confirmed_hostname, consent=consent,
                           max_pages=max_pages, max_depth=max_depth)
        self.require_permission('company:manage')  # May have logged out during crawling.
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return save_crawl(con, crawl)

    def crawl_public_site_robots_checked(self, url: str, confirmed_hostname: str, *,
                                        consent: bool = False, max_pages: int = 3,
                                        max_depth: int = 1) -> dict:
        """Production public site crawl; fail closed if robots.txt cannot be verified.

        This path checks URL rules and crawl delay on the same pinned HTTPS transport.
        """
        self.require_permission('company:manage')
        from desktop.public_site_crawler import crawl_site_with_robots, save_crawl
        crawl = crawl_site_with_robots(url, confirmed_hostname, consent=consent,
                                       max_pages=max_pages, max_depth=max_depth)
        self.require_permission('company:manage')
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return save_crawl(con, crawl)

    def import_web_plugin_export(self, raw: bytes) -> dict:
        """Import a local JSON export from TinyFish/Firecrawl/Tavily; no network."""
        self.require_permission('company:manage')
        from desktop.public_site_crawler import load_plugin_export, import_plugin_records
        provider, records = load_plugin_export(raw)
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return import_plugin_records(con, provider, records)

    def import_offline_research_file(self, source_url: str, title: str, path: str) -> int:
        """Owner-chosen local file only; this method never makes network requests."""
        self.require_permission('company:manage')
        from desktop.research_captures import add_local_file
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return add_local_file(con, source_url, title, path)

    def create_offline_research_bundle_manifest(self, entries, destination) -> dict:
        """Make a user-requested local JSON list; do not modify SQLite."""
        self.require_permission('company:manage')
        from desktop.research_bundle_manifest import create_local_bundle_manifest
        return create_local_bundle_manifest(entries, destination)

    def create_offline_research_bundle_receipt(self, manifest_path, destination) -> dict:
        """Owner-only local fingerprint checkpoint; never writes to SQLite."""
        self.require_permission('company:manage')
        from desktop.research_bundle_manifest import create_local_bundle_receipt
        return create_local_bundle_receipt(manifest_path, destination)

    def verify_offline_research_bundle_receipt(self, receipt_path) -> dict:
        """Owner-only file and manifest recheck, independent of import status."""
        self.require_permission('company:manage')
        from desktop.research_bundle_manifest import verify_local_bundle_receipt
        return verify_local_bundle_receipt(receipt_path)

    def preview_offline_research_bundle(self, manifest_path: str) -> dict:
        """No database mutation; inspect local import bytes and duplicate keys."""
        self.require_permission('company:manage')
        from desktop.research_captures import preview_local_bundle
        with self._connect() as con:
            # Consistent snapshot: warnings and approval marker see the same DB.
            con.execute('BEGIN')
            return preview_local_bundle(con, manifest_path)

    def verify_imported_offline_research_bundle(self, manifest_path: str) -> dict:
        """Read-only owner-directed batch custody check; never contacts URLs."""
        self.require_permission('company:manage')
        from desktop.research_captures import verify_imported_local_bundle
        with self._connect() as con:
            con.execute('BEGIN')  # snapshot immutable capture and batch records
            return verify_imported_local_bundle(con, manifest_path)

    def import_offline_research_bundle(self, manifest_path: str, *,
                                       expected_preview_token: str | None = None) -> dict:
        """Import up to 20 pre-downloaded files; all inserts commit or roll back."""
        self.require_permission('company:manage')
        from desktop.research_captures import add_local_bundle
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return add_local_bundle(con, manifest_path, expected_preview_token=expected_preview_token)

    def search_offline_research(self, query: str = '', *, include_archived: bool = False,
                                limit: int = 200) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.research_captures import search
        with self._connect() as con:
            return search(con, query, include_archived=include_archived, limit=limit)

    def read_offline_research(self, capture_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.research_captures import get
        with self._connect() as con:
            return get(con, capture_id)

    def audit_offline_research(self) -> dict:
        """Recheck local SQLite text hashes and bundle links (not source truth)."""
        self.require_permission('company:manage')
        from desktop.research_captures import audit_local_evidence
        with self._connect() as con:
            return audit_local_evidence(con)

    def compare_offline_research(self, first_id: int, second_id: int) -> dict:
        """Exact content/source comparison; never fetch the URLs."""
        self.require_permission('company:manage')
        from desktop.research_captures import compare_local_evidence
        with self._connect() as con:
            return compare_local_evidence(con, first_id, second_id)

    def list_offline_research_links(self, capture_id: int) -> list[dict]:
        """Read passive HTML links. URLs are never visited or verified."""
        self.require_permission('company:manage')
        from desktop.research_captures import list_offline_links
        with self._connect() as con:
            return list_offline_links(con, capture_id)

    def trace_offline_research_references(self, capture_id: int, max_depth: int = 2) -> dict:
        """Read bounded local reference graph; never open or verify URLs."""
        self.require_permission('company:manage')
        from desktop.research_captures import trace_offline_references
        with self._connect() as con:
            return trace_offline_references(con, capture_id, max_depth)

    def offline_research_source_overlap(self, *, include_archived: bool = False,
                                        limit: int = 25) -> dict:
        """Owner-only read-only evidence overlap hints, never web verification."""
        self.require_permission('company:manage')
        from desktop.research_source_overlap import build_source_overlap_report
        with self._connect() as con:
            return build_source_overlap_report(
                con, include_archived=include_archived, limit=limit)

    def recheck_offline_research_import_file(self, capture_id: int,
                                             selected_path: str | Path) -> dict:
        """Compare an explicitly selected local copy with recorded import bytes."""
        self.require_permission('company:manage')
        from desktop.research_file_custody import recheck_import_file
        with self._connect() as con:
            return recheck_import_file(con, capture_id, selected_path)

    def offline_research_followup_queue(self, *, include_archived: bool = False,
                                        limit: int = 40, review_filter: str = 'all',
                                        page: int = 1) -> dict:
        """Owner-only read-only manual review queue for stored URL strings."""
        self.require_permission('company:manage')
        from desktop.research_followups import build_followup_queue
        with self._connect() as con:
            return build_followup_queue(con, include_archived=include_archived, limit=limit,
                                        review_filter=review_filter, page=page)

    def offline_research_followup_domains(self, *, include_archived: bool = False,
                                          review_filter: str = 'all',
                                          limit: int = 25) -> dict:
        """Owner-only offline hostname grouping; never resolve or fetch URLs."""
        self.require_permission('company:manage')
        from desktop.research_followup_domains import build_followup_domain_summary
        with self._connect() as con:
            return build_followup_domain_summary(
                con, include_archived=include_archived,
                review_filter=review_filter, limit=limit)

    def offline_research_url_preflight(self, *, include_archived: bool = False,
                                       review_filter: str = 'all',
                                       limit: int = 40) -> dict:
        """Owner-only passive URL warning inventory; never authorizes fetching."""
        self.require_permission('company:manage')
        from desktop.research_url_preflight import build_followup_url_preflight
        with self._connect() as con:
            return build_followup_url_preflight(
                con, include_archived=include_archived,
                review_filter=review_filter, limit=limit)

    def export_offline_research_url_preflight(self, destination: str | Path, *,
                                               include_archived: bool = False,
                                               review_filter: str = 'all') -> Path:
        """Owner-only, complete bounded URL warning report; no web requests."""
        self.require_permission('company:manage')
        from desktop.research_preflight_exports import (
            build_preflight_export_report, save_preflight_export,
        )
        with self._connect() as con:
            report = build_preflight_export_report(
                con, include_archived=include_archived, review_filter=review_filter)
        return save_preflight_export(report, destination)

    def inspect_offline_research_url_preflight_export(self, filename: str | Path) -> dict:
        """Owner-only checksum and current local warning inventory comparison."""
        self.require_permission('company:manage')
        from desktop.research_preflight_exports import inspect_preflight_export_file
        return inspect_preflight_export_file(self, filename)

    def export_offline_research_followups(self, destination: str | Path, *,
                                          include_archived: bool = False,
                                          review_filter: str = 'all') -> Path:
        """Owner-approved complete bounded local queue handoff, not web research."""
        self.require_permission('company:manage')
        from desktop.research_followup_exports import build_full_queue_report, save_followup_export
        with self._connect() as con:
            report = build_full_queue_report(con, include_archived=include_archived,
                                             review_filter=review_filter)
        return save_followup_export(report, destination)

    def inspect_offline_research_followup_export(self, filename: str | Path) -> dict:
        """Owner-only comparison of an exported queue to today's local DB."""
        self.require_permission('company:manage')
        from desktop.research_followup_verification import inspect_followup_export_file
        return inspect_followup_export_file(self, filename)

    def record_offline_research_followup_note(self, linked_url: str, action: str,
                                               note: str) -> int:
        """Append owner-only manual triage, not a claim of website verification."""
        self.require_permission('company:manage')
        from desktop.research_followup_notes import record_note
        with self._connect() as con:
            return record_note(con, linked_url, action, note)

    def offline_research_followup_history(self, linked_url: str,
                                          limit: int = 20) -> dict:
        """Read bounded, append-only local triage history."""
        self.require_permission('company:manage')
        from desktop.research_followup_notes import history
        with self._connect() as con:
            return history(con, linked_url, limit)

    def local_research_evidence_report(self, query: str, *,
                                       include_archived: bool = False, limit: int = 20) -> dict:
        """Owner-only quoted evidence preview; read-only, offline, unverified URLs."""
        self.require_permission('company:manage')
        from desktop.research_captures import build_local_evidence_report
        with self._connect() as con:
            return build_local_evidence_report(con, query, include_archived=include_archived,
                                               limit=limit)

    def export_local_research_evidence(self, query: str, destination: str | Path, *,
                                       include_archived: bool = False) -> Path:
        """Owner-approved local JSON export; never overwrites an existing file."""
        self.require_permission('company:manage')
        from desktop.research_exports import save_evidence_export
        report = self.local_research_evidence_report(query, include_archived=include_archived)
        return save_evidence_export(report, destination)

    def inspect_local_research_evidence_export(self, filename: str | Path) -> dict:
        """Check selected JSON checksum and current local DB snapshot; read-only."""
        from desktop.research_verification import inspect_export_file
        return inspect_export_file(self, filename)

    def archive_offline_research(self, capture_id: int) -> bool:
        self.require_permission('company:manage')
        from desktop.research_captures import archive
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return archive(con, capture_id)

    # Stage74: local synthetic fixture only, never a real provider verification.
    def check_offline_payment_fixture(self, order_id: int, reference: str, fixture: dict) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_payment_verification import check
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return check(con,order_id,reference,fixture)

    def record_synthetic_payment_event(self, order_id: int, fixture_audit_id: int, event_key: str, payload: dict) -> dict:
        """Admin-only, offline. Never changes payment_received or sales records."""
        self.require_permission('company:manage')
        from desktop.offline_payment_event_dedup import record
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return record(con, order_id, fixture_audit_id, event_key, payload)

    # Stage76: purely local, simulated delivery planning; never fulfills customer orders.
    def record_mock_delivery(self, order_id: int, delivery_key: str, state: str, note: str = '') -> dict:
        self.require_permission('company:manage')
        from desktop.offline_delivery_simulations import record
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return record(con, order_id, delivery_key, state, note)

    def mock_delivery_history(self, order_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.offline_delivery_simulations import history
        with self._connect() as con:
            return history(con, order_id)

    # Stage77: non-transactional mock subscriptions, cancellation, refund requests.
    def create_mock_subscription(self, order_id: int, plan_key: str,
                                 mode: str, periods: int) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_subscription_refund import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            # Stage73 source verification: no stale listing may enter a new plan.
            order = self._stage77_verify_order_source(con, order_id)
            if order['stale_source']:
                raise ValueError('미게시 상품 원본이 변경되어 모의 계획 생성 불가')
            return create(con, order_id, plan_key, mode, periods)

    def _stage77_verify_order_source(self, con, order_id: int) -> dict:
        from desktop.offline_order_simulations import get
        return get(con, self.path, order_id)

    def mock_subscription(self, subscription_id: int) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_subscription_refund import get
        with self._connect() as con:
            return get(con, subscription_id)

    def mock_subscription_history(self, subscription_id: int) -> list[dict]:
        self.require_permission('company:manage')
        from desktop.offline_subscription_refund import history
        with self._connect() as con:
            return history(con, subscription_id)

    def transition_mock_subscription(self, subscription_id: int, event_key: str,
                                     action: str, note: str = '', amount_minor: int = 0) -> dict:
        self.require_permission('company:manage')
        from desktop.offline_subscription_refund import transition, _base
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            base = _base(con, subscription_id)
            # Invalidate if upstream order/listing provenance changed.
            order = self._stage77_verify_order_source(con, base['simulated_order_id'])
            if order['stale_source']:
                raise ValueError('원본 상품 변경으로 모의 요청 기록 차단')
            return transition(con, subscription_id, event_key, action, note, amount_minor)

    # Stage78-80: local synthetic records; no real customers/payments/revenue.
    def create_synthetic_support_ticket(self, order_id, ticket_key, alias, category, summary):
        self.require_permission('company:manage')
        from desktop.local_synthetic_support import create
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return create(con,order_id,ticket_key,alias,category,summary)

    def transition_synthetic_support_ticket(self, ticket_id, event_key, action, comment):
        self.require_permission('company:manage')
        from desktop.local_synthetic_support import transition
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return transition(con,ticket_id,event_key,action,comment)

    def synthetic_support_ticket_history(self,ticket_id):
        self.require_permission('company:manage')
        from desktop.local_synthetic_support import history
        with self._connect() as con:
            return history(con,ticket_id)

    def ingest_signed_payment_evidence(self, raw: bytes, signature: str, shared_secret: str):
        from desktop.company_payment_reconciliation import ingest
        return ingest(self, raw, signature, shared_secret)

    def review_signed_payment_evidence(self, event_id: int, decision: str, note: str):
        from desktop.company_payment_reconciliation import review
        return review(self, event_id, decision, note)

    def signed_payment_reconciliation_summary(self, business_id: int | None = None):
        from desktop.company_payment_reconciliation import summary
        return summary(self, business_id)

    def reconcile_owner_bank_csv(self, file_path):
        """대사만 실행; 외부 은행 API·실제 PG 결제 실행하지 않음."""
        from desktop.company_bank_reconciliation import import_owner_csv
        return import_owner_csv(self, file_path)

    def read_bank_reconciliation(self, batch_id: int):
        from desktop.company_bank_reconciliation import read
        return read(self, batch_id)

    def preview_business_financial_close(self, business_id: int):
        from desktop.company_financial_close import preview
        return preview(self, business_id)

    def create_business_financial_close(self, business_id: int, note: str):
        from desktop.company_financial_close import create
        return create(self, business_id, note)

    def read_business_financial_close(self, close_id: int):
        from desktop.company_financial_close import read
        return read(self, close_id)

    def list_business_financial_closes(self, business_id: int):
        """과거 결산 기간·중복 없는 누적 합계 확인(실제 송금 아님)."""
        from desktop.company_financial_close import history
        return history(self, business_id)

    def export_campaign_call_evidence(self, campaign_id: int):
        from desktop.company_campaign_evidence import export
        return export(self, campaign_id)

    def read_campaign_call_evidence(self, export_id: int):
        from desktop.company_campaign_evidence import read
        return read(self, export_id)

    def inspect_campaign_step_evidence(self, campaign_id: int):
        from desktop.company_campaign_evidence import inspect
        return inspect(self, campaign_id)

    def inspect_campaign_evidence_disk_consistency(self, limit: int = 100) -> dict:
        """호출 감사 파일/SQLite의 누락·손상·미등록 원본을 읽기 전용 점검."""
        from desktop.company_campaign_evidence import inspect_disk_consistency
        return inspect_disk_consistency(self, limit)


    def inspect_campaign_evidence_disk_consistency_full(self, max_records: int = 10000) -> dict:
        """기존 100건 조회를 유지하며 전체 등록/디스크 원본을 별도 점검."""
        from desktop.company_campaign_evidence import inspect_disk_consistency_full
        return inspect_disk_consistency_full(self, max_records)

    def find_campaign_final_report(self, campaign_id: int):
        from desktop.company_campaign_final_report import find_by_campaign
        return find_by_campaign(self, campaign_id)

    def propose_campaign_final_report(self, campaign_id: int, *, cancel=None):
        from desktop.company_campaign_final_report import propose
        return propose(self, campaign_id, cancel=cancel)

    def read_campaign_final_report(self, report_id: int):
        from desktop.company_campaign_final_report import read
        return read(self, report_id)

    def inspect_campaign_final_model_attempt_chain(self, campaign_id: int) -> dict:
        """총괄 실제 모델 재시도/최종보고 불변 연결의 읽기 전용 검사."""
        from desktop.company_campaign_final_report import inspect_final_model_attempt_chain
        return inspect_final_model_attempt_chain(self, campaign_id)

    def decide_campaign_final_report(self, report_id: int, decision: str, reason: str):
        from desktop.company_campaign_final_report import decide
        return decide(self, report_id, decision, reason)

    def list_signed_payment_events(self, limit: int = 30):
        from desktop.company_payment_reconciliation import pending_events
        return pending_events(self, limit)

    def scan_failed_employee_work(self, limit: int = 31):
        from desktop.company_failure_followups import scan
        return scan(self, limit)

    def decide_failed_employee_followup(self, proposal_id: int, decision: str, note: str):
        from desktop.company_failure_followups import decide
        return decide(self, proposal_id, decision, note)

    def failed_employee_followups(self, limit: int = 40):
        from desktop.company_failure_followups import pending
        return pending(self, limit)

    def propose_staff_department_transfer(self, employee_id: int, to_department_id: int,
                                          failed_run_id: int, reason: str):
        from desktop.company_staff_reallocation import propose
        return propose(self, employee_id, to_department_id, failed_run_id, reason)

    def decide_staff_department_transfer(self, proposal_id: int, decision: str, reason: str):
        from desktop.company_staff_reallocation import decide
        return decide(self, proposal_id, decision, reason)

    def staff_department_transfer_audit(self, limit: int = 30):
        from desktop.company_staff_reallocation import history
        return history(self, limit)

    def propose_full_company_campaign(self, source_task_id: int, *, cancel=None) -> dict:
        from desktop.company_wide_campaign import propose
        return propose(self,source_task_id,cancel=cancel)

    def staged_full_company_progress(self, source_task_id: int) -> dict:
        from desktop.company_wide_campaign import staged_plan_progress
        return staged_plan_progress(self,source_task_id)

    def approve_full_company_campaign(self, campaign_id: int) -> dict:
        from desktop.company_wide_campaign import approve
        return approve(self,campaign_id)

    def verified_full_company_progress(self, campaign_id: int) -> dict:
        from desktop.company_wide_campaign import verified_progress
        return verified_progress(self,campaign_id)

    def read_full_company_campaign(self, campaign_id: int) -> dict:
        from desktop.company_wide_campaign import read
        return read(self,campaign_id)

    def inspect_full_company_resume_gate(self, campaign_id: int) -> dict:
        """실제 승인·모델 실행 원본의 다음 단계 사전 점검(읽기 전용)."""
        from desktop.company_campaign_resume_gate import snapshot
        return snapshot(self, campaign_id)

    def run_full_company_next(self, campaign_id: int, *, cancel=None) -> dict:
        from desktop.company_wide_campaign import run_next
        return run_next(self,campaign_id,cancel=cancel,
                        require_genuine_provenance=True)

    def export_owner_approved_final_dossier(self, report_id: int) -> dict:
        """명시적 관리자 승인에 한한 로컬 인계, 외부 게시/전송 없음."""
        from desktop.company_campaign_owner_dossier import export
        return export(self, report_id)

    def create_local_order_intake(self, order_ref, customer_alias, payment_event_id, document_id):
        from desktop.company_local_order_fulfillment import create
        return create(self, order_ref, customer_alias, payment_event_id, document_id)

    def approve_local_order_package(self, order_id, note):
        from desktop.company_local_order_fulfillment import approve_local_package
        return approve_local_package(self, order_id, note)

    def request_local_order_cancel(self, order_id, note):
        from desktop.company_local_order_fulfillment import request_cancel
        return request_cancel(self, order_id, note)

    def link_local_order_refund(self, order_id, refund_event_id, note):
        from desktop.company_local_order_fulfillment import link_refund
        return link_refund(self, order_id, refund_event_id, note)

    def read_local_order(self, order_id):
        from desktop.company_local_order_fulfillment import read
        return read(self, order_id)

    def list_local_orders(self, limit=50):
        from desktop.company_local_order_fulfillment import list_orders
        return list_orders(self, limit)

    def link_local_order_customer_case(self, order_id, case_id):
        from desktop.company_order_support import link_case
        return link_case(self, order_id, case_id)

    def read_local_order_customer_cases(self, order_id):
        from desktop.company_order_support import read
        return read(self, order_id)

    def prepare_local_order_delivery_packet(self, order_id, note):
        from desktop.company_local_delivery_packets import prepare
        return prepare(self, order_id, note)

    def read_local_order_delivery_packet(self, packet_id):
        from desktop.company_local_delivery_packets import read
        return read(self, packet_id)

    def list_local_order_delivery_packets(self, limit=50):
        from desktop.company_local_delivery_packets import list_packets
        return list_packets(self, limit)

    def local_order_finance_snapshot(self, business_id=None, limit=100):
        from desktop.company_local_order_finance import snapshot
        return snapshot(self, business_id, limit)

    def read_owner_approved_final_dossier(self, dossier_id: int) -> dict:
        from desktop.company_campaign_owner_dossier import read
        return read(self, dossier_id)

    def list_owner_approved_final_dossiers(self, limit: int = 30) -> list[dict]:
        from desktop.company_campaign_owner_dossier import list_exports
        return list_exports(self, limit)

    def inspect_owner_final_dossier_history(self, limit: int = 30) -> list[dict]:
        from desktop.company_campaign_owner_dossier import inspect_export_history
        return inspect_export_history(self, limit)

    def inspect_owner_dossier_disk_consistency(self, limit: int = 100) -> dict:
        from desktop.company_campaign_owner_dossier import inspect_disk_consistency
        return inspect_disk_consistency(self, limit)


    def inspect_owner_dossier_disk_consistency_full(self, max_records: int = 10000) -> dict:
        """관리자 최종 승인 인계 전체 파일/SQLite 읽기 전용 감사."""
        from desktop.company_campaign_owner_dossier import inspect_disk_consistency_full
        return inspect_disk_consistency_full(self, max_records)

    def verified_campaign_owner_chain(self, campaign_id: int) -> dict:
        from desktop.company_campaign_chain_integrity import snapshot
        return snapshot(self, campaign_id)

    def verify_campaign_owner_chain_receipt(self, campaign_id: int, receipt: dict) -> dict:
        """현재 원본과 과거 최종 인계 지문 재대조(읽기 전용)."""
        from desktop.company_campaign_chain_integrity import verify_receipt
        return verify_receipt(self, campaign_id, receipt)

    def find_owner_approved_final_dossier_by_campaign(self, campaign_id: int) -> dict | None:
        from desktop.company_campaign_owner_dossier import find_by_campaign
        return find_by_campaign(self, campaign_id)

    def inspect_company_owner_operations(self, campaign_id: int, business_id: int | None = None) -> dict:
        from desktop.company_owner_operational_summary import snapshot
        return snapshot(self, campaign_id, business_id)

    def list_approved_product_documents(self, limit: int = 100) -> list[dict]:
        from desktop.company_product_documents import list_documents
        return list_documents(self, limit)

    def list_customer_cases(self, limit: int = 100) -> list[dict]:
        from desktop.company_customer_cases import list_cases
        return list_cases(self, limit)

    def list_bank_reconciliation_batches(self, limit: int = 100) -> list[dict]:
        from desktop.company_bank_reconciliation import list_batches
        return list_batches(self, limit)

    def export_approved_product_document(self, campaign_id: int, ordinal: int,
                                          catalog_item_id: int) -> dict:
        from desktop.company_product_documents import export
        return export(self,campaign_id,ordinal,catalog_item_id)

    def read_approved_product_document(self, document_id: int) -> dict:
        from desktop.company_product_documents import read
        return read(self,document_id)

    def create_customer_case(self, case_ref: str, customer_alias: str,
                             question: str, *, catalog_item_id: int | None = None) -> dict:
        from desktop.company_customer_cases import create
        return create(self,case_ref,customer_alias,question,catalog_item_id=catalog_item_id)

    def approve_customer_reply(self, case_id: int, artifact_id: int) -> dict:
        from desktop.company_customer_cases import attach_approved_reply
        return attach_approved_reply(self,case_id,artifact_id)

    def close_customer_case(self, case_id: int) -> dict:
        from desktop.company_customer_cases import close
        return close(self,case_id)

    def read_customer_case(self, case_id: int) -> dict:
        from desktop.company_customer_cases import read
        return read(self,case_id)

    def export_approved_customer_reply(self, case_id: int) -> dict:
        from desktop.company_customer_cases import export_approved_reply
        return export_approved_reply(self,case_id)

    def read_exported_customer_reply(self, export_id: int) -> dict:
        from desktop.company_customer_cases import read_export
        return read_export(self,export_id)

    def record_hypothetical_finance(self,business_id,entry_key,kind,currency,amount_minor,note,order_id=None):
        self.require_permission('company:manage')
        from desktop.local_hypothetical_finance import record
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return record(con,business_id,entry_key,kind,currency,amount_minor,note,order_id)

    def hypothetical_finance_history(self):
        self.require_permission('company:manage')
        from desktop.local_hypothetical_finance import history
        with self._connect() as con:
            return history(con)

    def hypothetical_budget_report(self):
        self.require_permission('company:manage')
        from desktop.local_budget_scenarios import calculate
        with self._connect() as con:
            return calculate(con)

    def save_hypothetical_budget_snapshot(self,snapshot_key):
        self.require_permission('company:manage')
        from desktop.local_budget_scenarios import save
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return save(con,snapshot_key)

    def hypothetical_budget_snapshots(self):
        self.require_permission('company:manage')
        from desktop.local_budget_scenarios import snapshots
        with self._connect() as con:
            return snapshots(con)

    # Stages 81-83: read-only descriptive stats, mock-only detection, inactive recommendations.
    def local_company_performance_report(self):
        self.require_permission('company:manage')
        from desktop.local_company_diagnostics import performance
        with self._connect() as con:return performance(con)

    def local_company_diagnostics(self):
        self.require_permission('company:manage')
        from desktop.local_company_diagnostics import diagnostics
        with self._connect() as con:return diagnostics(con)

    def propose_local_improvement_draft(self, diagnostic_key, proposal_key, owner_note):
        self.require_permission('company:manage')
        from desktop.local_company_diagnostics import propose
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return propose(con,diagnostic_key,proposal_key,owner_note)

    def local_improvement_draft_history(self):
        self.require_permission('company:manage')
        from desktop.local_company_diagnostics import history
        with self._connect() as con:return history(con)

    # Stage84-86: owner-only nonexecuting planning & refresh-on-demand snapshot UI.
    def create_local_staffing_draft(self,plan_key,kind,department_id,note,employee_id=None):
        self.require_permission('company:manage')
        from desktop.local_staff_model_dashboard import staffing_draft
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return staffing_draft(con,plan_key,kind,department_id,note,employee_id)

    def local_staffing_drafts(self):
        self.require_permission('company:manage')
        from desktop.local_staff_model_dashboard import staffing_history
        with self._connect() as con:return staffing_history(con)

    def local_model_config_comparison(self):
        self.require_permission('company:manage')
        from desktop.local_staff_model_dashboard import model_registry
        with self._connect() as con:return model_registry(con)

    def create_local_model_switch_draft(self,switch_key,model_id,intended_use,note):
        self.require_permission('company:manage')
        from desktop.local_staff_model_dashboard import switch_draft
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return switch_draft(con,switch_key,model_id,intended_use,note)

    def local_model_switch_drafts(self):
        self.require_permission('company:manage')
        from desktop.local_staff_model_dashboard import switch_history
        with self._connect() as con:return switch_history(con)

    def offline_company_dashboard_snapshot(self):
        self.require_permission('company:manage')
        from desktop.local_staff_model_dashboard import dashboard
        with self._connect() as con:return dashboard(con)

    # Stage87-90 management views are owner-only; no external side effects.
    def offline_management_view(self,section):
        self.require_permission('company:manage')
        from desktop import stage87_90_management as m
        views={'organization':m.organization,'communications':m.communications,
               'commerce':m.commerce,'approvals':m.approvals}
        if section not in views:raise ValueError('unknown local management view')
        with self._connect() as con:return views[section](con)

    def emergency_stop_local(self,stopped,reason):
        self.require_permission('company:manage')
        from desktop.stage87_90_management import set_stop
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return set_stop(con,stopped,reason)

    # 91-93: permission-restricted spend reviews (never a real approval or payment).
    def local_spend_review(self,review_key,business_id,amount_krw,rationale):
        self.require_permission('expenses:approve')
        from desktop.stage91_93_security import review_spending
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            return review_spending(con,review_key,business_id,amount_krw,rationale)

    def local_spend_review_history(self):
        self.require_permission('expenses:approve')
        from desktop.stage91_93_security import spend_history
        with self._connect() as con:return spend_history(con)

    # Stages94-100: restricted, non-overwriting on-disk backup and synthetic probes.
    def backup_to_new_path(self,destination):
        from desktop.stage94_100_validation import create_backup
        return create_backup(self,destination)

    def restore_backup_as_new_database(self,backup,destination):
        from desktop.stage94_100_validation import copy_backup_to_new_file
        return copy_backup_to_new_file(backup,destination,self)

    def offline_integration_evidence(self):
        self.require_permission('company:manage')
        from desktop.stage94_100_validation import local_validation_snapshot
        with self._connect() as con:return local_validation_snapshot(con)

    # 주문 예외 → 고객지원부 실제 업무 연결/감사 (외부 고객 발송 없음).
    def scan_local_order_exceptions(self, limit=100):
        from desktop.company_order_exception_queue import scan
        return scan(self, limit)

    def escalate_local_order_exception(self, order_id, kind, case_ref, owner_note):
        from desktop.company_order_exception_queue import escalate
        return escalate(self, order_id, kind, case_ref, owner_note)

    def read_local_order_exception(self, escalation_id):
        from desktop.company_order_exception_queue import read
        return read(self, escalation_id)

    def review_local_order_exception(self, escalation_id, decision, owner_note):
        from desktop.company_order_exception_queue import review
        return review(self, escalation_id, decision, owner_note)

    def local_order_exception_history(self, limit=50):
        from desktop.company_order_exception_queue import history
        return history(self, limit)

    # 로컬 정산/환불/상품/고객지원 증빙의 관리자 불변 재무 검토.
    def capture_local_finance_evidence(self, order_id, kind, owner_note):
        from desktop.company_order_finance_receipts import capture
        return capture(self, order_id, kind, owner_note)

    def read_local_finance_evidence(self, review_id):
        from desktop.company_order_finance_receipts import read
        return read(self, review_id)

    def local_finance_evidence_history(self, limit=50):
        from desktop.company_order_finance_receipts import history
        return history(self, limit)

    # 실제 SQLite 운영 이상 탐지·관리자 후속 업무 (모델 재시도/외부 조치 없음).
    def scan_operational_incidents(self, running_age=1800, review_age=86400, limit=100):
        from desktop.company_operational_incidents import scan
        return scan(self, running_age=running_age, review_age=review_age, limit=limit)

    def operational_incident_history(self, limit=50):
        from desktop.company_operational_incidents import history
        return history(self, limit)

    def decide_operational_incident(self, incident_id, decision, note):
        from desktop.company_operational_incidents import decide
        return decide(self, incident_id, decision, note)

    # 실제 15부서/31직원 등록 현황에 따른 부서별 업무량·개선 업무.
    def department_workload_snapshot(self):
        from desktop.company_department_workload import snapshot
        return snapshot(self)

    def propose_department_workload_review(self, department_id, note):
        from desktop.company_department_workload import propose
        return propose(self, department_id, note)

    def decide_department_workload_review(self, proposal_id, decision, note):
        from desktop.company_department_workload import decide
        return decide(self, proposal_id, decision, note)

    def department_workload_review_history(self, limit=50):
        from desktop.company_department_workload import history
        return history(self, limit)
 
    # 실제 총괄 GGUF 운영·재무 근거 분석 및 소유자 개별 후속업무 승인.
    def chief_evidence_snapshot(self, domain):
        from desktop.company_chief_evidence_sources import snapshot
        return snapshot(self, domain)

    def propose_chief_evidence_review(self, domain, *, cancel=None):
        from desktop.company_chief_evidence_decisions import propose
        return propose(self, domain, cancel=cancel)

    def read_chief_evidence_review(self, review_id):
        from desktop.company_chief_evidence_decisions import read
        return read(self, review_id)

    def chief_evidence_review_history(self, limit=30):
        from desktop.company_chief_evidence_decisions import history
        return history(self, limit)

    def decide_chief_evidence_review(self, review_id, decision, note):
        from desktop.company_chief_evidence_decisions import decide
        return decide(self, review_id, decision, note)

    # 소유자 확인이 끝난 중단 실행의 복구 전 내부 검토 업무(자동 재시도 없음).
    def eligible_recovery_work_orders(self, limit=50):
        from desktop.company_recovery_work_orders import eligible
        return eligible(self, limit)

    def capture_recovery_work_order(self, audit_id, note):
        from desktop.company_recovery_work_orders import capture
        return capture(self, audit_id, note)

    def decide_recovery_work_order(self, work_order_id, decision, note):
        from desktop.company_recovery_work_orders import decide
        return decide(self, work_order_id, decision, note)

    def recovery_work_order_history(self, limit=50):
        from desktop.company_recovery_work_orders import history
        return history(self, limit)

    # 실제 직원 실행·모델 호출·승인 결과물에 기반한 불변 평가.
    def employee_evidence_snapshot(self, employee_id):
        from desktop.company_employee_evidence_reviews import snapshot
        return snapshot(self, employee_id)

    def capture_employee_evidence_review(self, employee_id, note):
        from desktop.company_employee_evidence_reviews import capture
        return capture(self, employee_id, note)

    def decide_employee_evidence_review(self, review_id, decision, note):
        from desktop.company_employee_evidence_reviews import decide
        return decide(self, review_id, decision, note)

    def employee_evidence_review_history(self, limit=50):
        from desktop.company_employee_evidence_reviews import history
        return history(self, limit)

    # 기존 고객지원부 실제 GGUF 승인 업무.
    def customer_ai_readiness(self,case_id):
        from desktop.company_customer_case_ai import readiness
        return readiness(self,case_id)

    def assign_customer_ai(self,case_id):
        from desktop.company_customer_case_ai import assign
        return assign(self,case_id)

    def approve_customer_ai_order(self,case_id,instruction):
        from desktop.company_customer_case_ai import approve
        return approve(self,case_id,instruction)

    def run_customer_ai(self,case_id,*,cancel=None):
        from desktop.company_customer_case_ai import execute
        return execute(self,case_id,cancel=cancel)

    # 관리자 승인된 GGUF 업무의 재시도 없는 영속 대기열/Windows 소유 프로세스 감사.
    def enqueue_owner_model_task(self, task_id, note):
        from desktop.company_owner_model_queue import enqueue
        return enqueue(self,task_id,note)

    def list_owner_model_queue(self, limit=50):
        from desktop.company_owner_model_queue import list_entries
        return list_entries(self,limit)

    def cancel_owner_model_queue(self, queue_id, note):
        from desktop.company_owner_model_queue import cancel_pending
        return cancel_pending(self,queue_id,note)

    def native_model_exit_history(self, limit=30):
        from desktop.company_native_model_watch import history
        return history(self,limit)

    def release_owner_confirmed_model_lease(self, run_id, note):
        from desktop.company_native_model_watch import release_after_owner_inspection
        return release_after_owner_inspection(self,run_id,note,owner_confirmed=True)

    # 기존 15부서·30업무 원본 검수→관리자 개별 승인→영속 GGUF 대기열 연결.
    def inspect_owner_model_queue(self, limit=100):
        from desktop.company_model_queue_readiness import inspect
        return inspect(self,limit)

    def preview_campaign_model_queue(self, campaign_id):
        from desktop.company_campaign_queue_bridge import preview
        return preview(self,campaign_id)

    def enqueue_campaign_model_step(self, campaign_id, note):
        from desktop.company_campaign_queue_bridge import enqueue_next
        return enqueue_next(self,campaign_id,note)

    # 실제 로컬 서명 거래·은행 CSV 증빙만 조회한다.
    def finance_evidence_board(self, business_id=None, limit=100):
        from desktop.company_finance_evidence_board import snapshot
        return snapshot(self,business_id,limit)

    # 실제 GGUF 대기열·호출·관리자 검수 감사 교차 대조.
    def model_queue_evidence_audit(self, limit=100):
        from desktop.company_model_queue_evidence_audit import snapshot
        return snapshot(self,limit)


    # 원본 15부서·30업무 승인 GGUF 협업의 전사 관리자 관측·보존.
    def campaign_owner_board(self, limit=20):
        from desktop.company_campaign_owner_board import board
        return board(self,limit)

    def capture_campaign_owner_checkpoint(self, campaign_id, note):
        from desktop.company_campaign_owner_board import capture
        return capture(self,campaign_id,note)

    def campaign_owner_checkpoint_history(self, campaign_id, limit=30):
        from desktop.company_campaign_owner_board import history
        return history(self,campaign_id,limit)

    # Windows 로그인 이후 외부 감시 EXE 실행 정책: 명시적 관리자 클릭 전용.
    def native_supervisor_startup_status(self):
        from desktop.company_native_startup_policy import status
        return status(self)

    def enable_native_supervisor_startup(self):
        from desktop.company_native_startup_policy import enable
        return enable(self)

    def disable_native_supervisor_startup(self):
        from desktop.company_native_startup_policy import disable
        return disable(self)

    def native_supervisor_audit(self, limit=80):
        from desktop.company_native_supervisor_audit import history
        return history(self,limit)


    # 개별 승인된 GGUF 대기열의 연속 실행 및 중단 감사.
    def run_owner_model_batch(self, max_jobs, note, *, cancel=None, session_token=None):
        from desktop.company_approved_queue_batch import run_batch
        return run_batch(self, max_jobs=max_jobs, owner_note=note,
                         cancel=cancel, session_token=session_token)

    def owner_model_batch_history(self, limit=30):
        from desktop.company_approved_queue_batch import history
        return history(self, limit)

    def close_owner_model_batch_after_inspection(self, batch_id, note):
        from desktop.company_approved_queue_batch import close_after_owner_inspection
        return close_after_owner_inspection(self, batch_id, note, owner_confirmed=True)


    # 총괄 실제 GGUF의 현재 회사 원본 기반 부서별 신규 업무 발견·배정.
    def discover_chief_department_tasks(self, *, cancel=None):
        from desktop.company_chief_department_discovery import discover
        return discover(self, cancel=cancel)

    def chief_department_discovery_proposals(self, limit=50):
        from desktop.company_chief_department_discovery import list_proposals
        return list_proposals(self, limit=limit)

    def chief_department_discovery_attempts(self, limit=30):
        from desktop.company_chief_department_discovery import list_attempts
        return list_attempts(self, limit=limit)

    def decide_chief_department_proposal(self, proposal_id, decision, note):
        from desktop.company_chief_department_dispatch import decide
        return decide(self, proposal_id, decision, note)

    def chief_department_handoffs(self, department_id=None, limit=100):
        from desktop.company_chief_department_dispatch import pending_by_department
        return pending_by_department(self, department_id, limit)


    # 기존 Windows 자율 운영과 별도 동의를 요구하는 총괄 GGUF 주기적 신규업무 발견.
    def configure_chief_autodiscovery(self, enabled, interval_minutes=60):
        from desktop.company_chief_autodiscovery import configure
        return configure(self, enabled, interval_minutes=interval_minutes)

    def chief_autodiscovery_status(self):
        from desktop.company_chief_autodiscovery import status
        return status(self)

    def chief_autodiscovery_history(self, limit=50):
        from desktop.company_chief_autodiscovery import history
        return history(self, limit=limit)

    def close_interrupted_chief_autodiscovery(self, run_id, note):
        from desktop.company_chief_autodiscovery import close_interrupted
        return close_interrupted(self, run_id, note, owner_confirmed=True)


    # 원본 실제 직원 업무 실행 전의 타부서 GGUF 협업 검토 및 소유자 개별 승인.
    def run_peer_consultation(self,task_id,consultant_employee_id,owner_note,*,cancel=None):
        from desktop.company_peer_consultations import run
        return run(self,task_id,consultant_employee_id,owner_note,cancel=cancel)

    def decide_peer_consultation(self,consultation_id,decision,owner_note):
        from desktop.company_peer_consultations import decide
        return decide(self,consultation_id,decision,owner_note)

    def peer_consultation_history(self,task_id=None,limit=50):
        from desktop.company_peer_consultations import list_consultations
        return list_consultations(self,task_id,limit)


    # 승인된 총괄 신규 부서 업무의 실제 부서장 GGUF 검토/인계.
    def run_department_head_review(self, artifact_id, *, cancel=None):
        from desktop.company_department_head_review import run
        return run(self, artifact_id, cancel=cancel)

    def decide_department_head_review(self, review_id, decision, note):
        from desktop.company_department_head_review import decide
        return decide(self, review_id, decision, note)

    def department_head_review_history(self, limit=50):
        from desktop.company_department_head_review import history
        return history(self, limit)


    # 부서장 실 GGUF 승인 후 사용자 별도 클릭으로만 총괄 실제 보고서 회수.
    def preview_head_chief_handoffs(self, limit=30):
        from desktop.company_head_chief_handoff_queue import preview
        return preview(self,limit)

    def run_head_chief_handoff_batch(self,max_items,note,*,cancel=None):
        from desktop.company_head_chief_handoff_queue import run
        return run(self,max_items,note,cancel=cancel)

    def head_chief_handoff_history(self,limit=30):
        from desktop.company_head_chief_handoff_queue import history
        return history(self,limit)

    def close_head_chief_handoff_after_inspection(self,batch_id,note):
        from desktop.company_head_chief_handoff_queue import close_after_owner_inspection
        return close_after_owner_inspection(
            self,batch_id,note,owner_confirmed=True)

    def head_chief_department_coverage(self,limit=100):
        from desktop.company_head_chief_coverage import report
        return report(self,limit=limit)


    # 실제 직원/총괄 GGUF 양측 최종 승인 원본의 로컬 코드·문서 제품화.
    def export_approved_real_product(self, artifact_id, kind, note):
        from desktop.company_approved_real_products import export
        return export(self,artifact_id,kind,note)

    def approved_real_product_history(self,limit=30):
        from desktop.company_approved_real_products import history
        return history(self,limit)

    # 실패 직원 원본을 총괄 실제 GGUF로 평가하고 관리자 제안만 전달.
    def propose_chief_staff_strategy(self, *, cancel=None):
        from desktop.company_chief_staff_strategy import propose_with_real_chief
        return propose_with_real_chief(self,cancel=cancel)

    def decide_chief_staff_strategy(self,strategy_id,decision,note):
        from desktop.company_chief_staff_strategy import decide
        return decide(self,strategy_id,decision,note)

    def chief_staff_strategy_history(self,limit=30):
        from desktop.company_chief_staff_strategy import history
        return history(self,limit)

    # 승인 직원→부서장 전달 승인→총괄 실제 모델 호출을 소유자 1회 실행.
    def preview_operating_round(self):
        from desktop.company_owner_operating_rounds import preview
        return preview(self)

    def run_owner_operating_round(self,employee_limit,chief_limit,note,*,cancel=None):
        from desktop.company_owner_operating_rounds import run
        return run(self,max_employee_jobs=employee_limit,
                   max_chief_reviews=chief_limit,owner_note=note,cancel=cancel)

    def operating_round_history(self,limit=30):
        from desktop.company_owner_operating_rounds import history
        return history(self,limit)

    def close_operating_round_after_inspection(self,round_id,note):
        from desktop.company_owner_operating_rounds import close_after_owner_inspection
        return close_after_owner_inspection(self,round_id,note,owner_confirmed=True)


    # 원격 재기동 시 Windows PID+생성시각과 GGUF 회차 원본 결합.
    def inspect_native_round_owners(self,minimum_age_seconds=180,limit=50):
        from desktop.company_native_round_guard import inspect
        return inspect(self,min_age_seconds=minimum_age_seconds,limit=limit)

    def record_dead_native_round(self,kind,round_id):
        from desktop.company_native_round_guard import record_dead_process
        return record_dead_process(self,kind,round_id)

    def close_native_round_after_inspection(self,interruption_id,note):
        from desktop.company_native_round_guard import close_after_owner_verification
        return close_after_owner_verification(
            self,interruption_id,note,owner_confirmed=True)


    # 직원·총괄 GGUF 실제 승인 원본 여러 개의 로컬 다중 코드/문서 ZIP 제작.
    def create_actual_model_release(self,title,artifact_specs,note):
        from desktop.company_actual_release_bundles import create
        return create(self,title,artifact_specs,note)

    def actual_model_release_history(self,limit=30):
        from desktop.company_actual_release_bundles import history
        return history(self,limit)


    # 실제 승인된 상품 ZIP을 로컬 주문/준비 문서와 감사형 연결.
    def create_real_release_order_handoff(self,order_id,release_id,packet_id,note):
        from desktop.company_real_release_order_handoff import create
        return create(self,order_id,release_id,packet_id,note)

    def real_release_order_handoff_history(self,limit=40):
        from desktop.company_real_release_order_handoff import history
        return history(self,limit)


    # 로그인된 Windows GUI 자동 tick에서 사용자 별도 동의된 승인 GGUF 연속 배치.
    def configure_long_company_batch(self,enabled,interval_minutes=60,
                                     max_staff=5,max_chief=5,note=""):
        from desktop.company_long_running_batch import configure
        return configure(self,enabled,interval_minutes=interval_minutes,
                         max_staff=max_staff,max_chief=max_chief,note=note)

    def long_company_batch_status(self):
        from desktop.company_long_running_batch import status
        return status(self)

    def long_company_batch_history(self,limit=50):
        from desktop.company_long_running_batch import history
        return history(self,limit)

    def close_long_company_batch_after_inspection(self,attempt_id,note):
        from desktop.company_long_running_batch import close_after_owner_inspection
        return close_after_owner_inspection(self,attempt_id,note,owner_confirmed=True)


    # Windows 장기 승인 GGUF 배치의 원래 커널 PID/프로세스 생성시각 감사.
    def inspect_long_native_processes(self,limit=50):
        from desktop.company_long_native_process import inspect
        return inspect(self,limit=limit)

    def record_dead_long_native_process(self,attempt_id):
        from desktop.company_long_native_process import record_verified_crash
        return record_verified_crash(self,attempt_id)

    def close_dead_long_native_process(self,crash_id,note):
        from desktop.company_long_native_process import close_after_owner_inspection
        return close_after_owner_inspection(self,crash_id,note,owner_confirmed=True)


    # 부서간 실제 직원·총괄 GGUF 선행 업무 완료 및 사용자 승인 불변 인계.
    def seal_dependency_handoff(self,task_id,note):
        from desktop.company_dependency_evidence_seal import seal
        return seal(self,task_id,note)

    def inspect_dependency_handoff(self,task_id):
        from desktop.company_dependency_evidence_seal import inspect
        return inspect(self,task_id)

    def dependency_handoff_history(self,limit=50):
        from desktop.company_dependency_evidence_seal import history
        return history(self,limit)


    # 실제 SQLite 원본 기반 승인 대기·선행 인계·중단 감사 통합 조회.
    def company_approval_inbox(self,limit=100):
        from desktop.company_owner_approval_inbox import snapshot
        return snapshot(self,limit)


    # 기존 총괄/관리자 승인 15부서 30역할 또는 2~5부서 계획 전체 1회 영속 등록.
    def preview_bulk_campaign_queue(self,scope,plan_id):
        from desktop.company_bulk_campaign_queue import preview
        return preview(self,scope,plan_id)

    def enqueue_bulk_campaign_queue(self,scope,plan_id,owner_note):
        from desktop.company_bulk_campaign_queue import enqueue_all
        return enqueue_all(self,scope,plan_id,owner_note)

    def bulk_campaign_queue_history(self,limit=30):
        from desktop.company_bulk_campaign_queue import history
        return history(self,limit)


    # 관리자 1회 명시 승인·메모리 일회 인증만으로 승인 ZIP 실제 SMTP 발송.
    def send_approved_model_customer_email(self,handoff_id,host,port,sender,
                                          recipient,username,password,note):
        from desktop.company_owner_smtp_delivery import deliver
        return deliver(self,handoff_id,host,port,sender,recipient,
                       username,password,note)

    def approved_model_customer_email_history(self,limit=30):
        from desktop.company_owner_smtp_delivery import history
        return history(self,limit)
