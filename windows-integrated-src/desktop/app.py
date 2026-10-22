"""AIWACK standalone native window with single-owner local login.

No HTTP server is started. This is a runnable prototype shell, not an AI company.
"""
from __future__ import annotations

import csv
import sqlite3
import threading
import queue
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from desktop.storage import LocalStore, MAX_PARALLEL_TASK_RUNS
from desktop.admin_sections import SECTIONS, section_for
from desktop.access_policy import CAPABILITIES, TOOLS
from desktop.model_runtime import BACKENDS, ModelConfig, validate_config, run_local_model
from desktop.employee_model_runtime import invoke_employee_model
from desktop.chief_runtime import invoke_chief_model
from desktop.chief_task_runtime import propose_chief_task_order, collect_chief_task_result
from desktop.task_runtime import invoke_task_execution
from desktop.company_status import read_chief_status_text

APP_TITLE = "AIWACK | AI Autonomous Company"
CURRENT_STAGE = 54  # Count of DONE stages; not highest roadmap step
TOTAL_STAGES = 100


def package_root() -> Path:
    """Locate bundled read-only project assets in source and frozen builds."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def steps() -> list[dict[str, str]]:
    with (package_root() / "docs" / "roadmap_100.csv").open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


class AIWACKWindow:
    def __init__(self, root: tk.Tk, store: LocalStore | None = None) -> None:
        self.root = root
        self.store = store or LocalStore()
        self.root.title(APP_TITLE)
        self.root.geometry("1040x720")
        self.root.minsize(820, 600)
        self.root.configure(bg="#121c2d")
        self.status_text = tk.StringVar(value="로컬 데이터 확인 중")
        self.note = tk.StringVar(value="")
        self.feedback = tk.StringVar(value="메모를 저장하고 프로그램을 다시 켜도 남는지 확인해 주세요.")
        self._style()
        self.main_frame = None
        self.account_name = tk.StringVar(value="")
        self.account_password = tk.StringVar(value="")
        self.password_confirm = tk.StringVar(value="")
        self.auth_feedback = tk.StringVar(value="")
        self._session_generation = 0
        self._health_timer_id = None
        self._model_cancel: threading.Event | None = None
        self._model_thread: threading.Thread | None = None
        self._auto_proposal_ai_enabled = False  # explicit opt-in, session only
        self._auto_proposal_ai_cancel = threading.Event()
        self._auto_proposal_ai_thread: threading.Thread | None = None
        self._auto_proposal_ai_queue: queue.Queue = queue.Queue()
        self._show_auth()

    def _show_auth(self) -> None:
        """Never render protected tabs until an owner is authenticated."""
        if self.main_frame is not None:
            self.main_frame.destroy()
            self.main_frame = None
        if hasattr(self, "auth_frame"):
            self.auth_frame.destroy()
        self.auth_frame = self._panel(self.root)
        self.auth_frame.pack(expand=True, padx=65, pady=50, fill="x")
        setup = not self.store.has_owner()
        self._label(self.auth_frame, "AIWACK · " + ("관리자 첫 설정" if setup else "관리자 로그인"), size=20, weight="bold").pack(anchor="w", pady=(0, 18))
        self._label(self.auth_frame, "로컬 PC 전용 관리자 계정입니다. 비밀번호를 분실하면 복구 기능은 아직 없습니다.", fg="#bfcfe5").pack(anchor="w", pady=(0, 15))
        self._label(self.auth_frame, "관리자 ID").pack(anchor="w")
        self.username_entry = tk.Entry(self.auth_frame, textvariable=self.account_name, font=("Malgun Gothic", 12), width=42)
        self.username_entry.pack(anchor="w", fill="x", pady=(4, 13), ipady=7)
        self._label(self.auth_frame, "비밀번호 (12자 이상)" if setup else "비밀번호").pack(anchor="w")
        self.password_entry = tk.Entry(self.auth_frame, textvariable=self.account_password, show="*", font=("Malgun Gothic", 12))
        self.password_entry.pack(anchor="w", fill="x", pady=(4, 13), ipady=7)
        if setup:
            self._label(self.auth_frame, "비밀번호 확인").pack(anchor="w")
            self.confirm_entry = tk.Entry(self.auth_frame, textvariable=self.password_confirm, show="*", font=("Malgun Gothic", 12))
            self.confirm_entry.pack(anchor="w", fill="x", pady=(4, 13), ipady=7)
        self.auth_button = tk.Button(self.auth_frame, text="관리자 계정 만들기" if setup else "로그인", command=self.submit_setup if setup else self.submit_login,
                                     bg="#4c83e6", fg="white", padx=24, pady=11, font=("Malgun Gothic", 11, "bold"))
        self.auth_button.pack(anchor="w", pady=(4, 10))
        self._label(self.auth_frame, "", fg="#ffd3a9", textvariable=self.auth_feedback, wraplength=830).pack(anchor="w")
        self.username_entry.focus_set()

    def submit_setup(self) -> None:
        if self.account_password.get() != self.password_confirm.get():
            self.auth_feedback.set("비밀번호 확인이 일치하지 않습니다.")
            return
        try:
            self.store.setup_owner(self.account_name.get(), self.account_password.get())
        except (ValueError, PermissionError) as exc:
            self.auth_feedback.set(str(exc))
            return
        self._enter_dashboard()

    def submit_login(self) -> None:
        try:
            self.store.login(self.account_name.get(), self.account_password.get())
        except PermissionError as exc:
            self.auth_feedback.set(str(exc))
            self.account_password.set("")
            return
        self._enter_dashboard()

    def _enter_dashboard(self) -> None:
        self._session_generation += 1
        self.account_password.set("")
        self.password_confirm.set("")
        self.auth_frame.destroy()
        self.note.set(self.store.read_note())
        self._layout()
        self.refresh()
        self._health_timer_tick(self._session_generation)

    def sign_out(self) -> None:
        if self._health_timer_id is not None:
            self.root.after_cancel(self._health_timer_id)
            self._health_timer_id = None
        self.cancel_local_model(wait=True)
        self._auto_proposal_ai_enabled = False
        self._auto_proposal_ai_cancel.set()
        self._session_generation += 1
        self.store.logout()
        self.note.set("")
        self.account_name.set("")
        self.account_password.set("")
        self._show_auth()

    def _style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TNotebook", background="#121c2d", borderwidth=0)
        style.configure("TNotebook.Tab", background="#26364f", foreground="#f3f6fe", padding=(18, 11), font=("Malgun Gothic", 11))
        style.map("TNotebook.Tab", background=[("selected", "#3659ab")])
        style.layout("AIWACK.TNotebook.Tab", [])
        style.configure("Progress.Horizontal.TProgressbar", troughcolor="#23334b", background="#6a9dff", thickness=11)
        style.configure("Treeview", background="#f8fbff", foreground="#26334a", fieldbackground="#f8fbff", rowheight=27, font=("Malgun Gothic", 9))
        style.configure("Treeview.Heading", font=("Malgun Gothic", 9, "bold"))

    def _label(self, parent: tk.Widget, text: str, *, size: int = 11, weight: str = "normal", fg: str = "#eaf0ff", bg: str = "#1c2a40", **kwargs) -> tk.Label:
        return tk.Label(parent, text=text, font=("Malgun Gothic", size, weight), fg=fg, bg=bg, **kwargs)

    def _panel(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg="#1c2a40", padx=22, pady=18, highlightthickness=1, highlightbackground="#30435f")

    def _layout(self) -> None:
        outer = tk.Frame(self.root, bg="#121c2d", padx=17, pady=11)
        self.main_frame = outer
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="AIWACK", font=("Malgun Gothic", 22, "bold"), fg="#ffffff", bg="#121c2d").pack(anchor="w")
        tk.Label(outer, text="AI Autonomous Company  ·  AI 조직·업무·실제 모델 실행 현황", font=("Malgun Gothic", 11), fg="#abc2df", bg="#121c2d").pack(anchor="w", pady=(1, 7))
        header_actions = tk.Frame(outer, bg="#121c2d")
        header_actions.pack(anchor="e", fill="x")
        tk.Label(header_actions, text="관리 화면 바로가기", bg="#121c2d", fg="#abc2df").pack(side="left", padx=(0, 7))
        self.quick_navigation = ttk.Combobox(header_actions, width=26, state="readonly")
        self.quick_navigation.pack(side="left")
        self.quick_navigation.bind("<<ComboboxSelected>>", self._jump_to_tab)
        tk.Button(header_actions, text="메모 실사", command=self._open_persistence,
                  bg="#3659ab", fg="white", padx=12, pady=4).pack(side="left", padx=(9, 0))
        tk.Button(header_actions, text="로그아웃", command=self.sign_out,
                  bg="#304561", fg="#f4f7ff", padx=12, pady=5).pack(side="right")
        self.tabs = ttk.Notebook(outer, style="AIWACK.TNotebook")
        self.tabs.pack(fill="both", expand=True)
        dashboard = tk.Frame(self.tabs, bg="#121c2d", padx=5, pady=6)
        persistence = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        roadmap = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        administration = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        company = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        departments = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        designations = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        employees = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        hierarchy = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        access = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        models = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        employee_models = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        chief_chat = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        work_plans = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        tasks = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        task_routing = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        task_dependencies = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        task_execution = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        task_artifacts = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        chief_tasks = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        health_monitor = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        detection = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        auto_proposals = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        breakdowns = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(dashboard, text="AI 회사 운영센터")
        self.tabs.add(persistence, text="로컬 저장 실사")
        self.tabs.add(roadmap, text="100단계 계획")
        self.tabs.add(administration, text="관리자 센터")
        self.tabs.add(company, text="회사·목표 관리")
        self.tabs.add(departments, text="부서 관리")
        self.tabs.add(designations, text="직급·직무·역할")
        self.tabs.add(employees, text="AI 직원 관리")
        self.tabs.add(hierarchy, text="조직 지휘 체계")
        self.tabs.add(access, text="직원 권한·도구")
        self.tabs.add(models, text="로컬 AI 모델")
        self.tabs.add(employee_models, text="직원별 모델·호출")
        self.tabs.add(chief_chat, text="총괄 AI 대화")
        self.tabs.add(work_plans, text="업무 계획")
        self.tabs.add(tasks, text="업무 관리")
        self.tabs.add(task_routing, text="업무 자동 배정")
        self.tabs.add(task_dependencies, text="업무 의존성")
        self.tabs.add(task_execution, text="AI 업무 실행")
        self.tabs.add(task_artifacts, text="업무 결과물·검수")
        self.tabs.add(chief_tasks, text="총괄 AI 지시·회수")
        self.tabs.add(health_monitor, text="회사 자동 점검")
        self.tabs.add(detection, text="문제·사업 기회 감지")
        self.tabs.add(auto_proposals, text="자동 업무 제안")
        self.tabs.add(breakdowns, text="복합 업무 세부 계획")
        recurring = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(recurring, text="정기 업무 스케줄러")
        event_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(event_tab, text="로컬 이벤트 업무")
        queue_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(queue_tab, text="작업 대기열")
        messages_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(messages_tab, text="직원 개인 메시지")
        department_chat_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(department_chat_tab, text="부서별 협업 대화")
        project_chat_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(project_chat_tab, text="프로젝트 협업 대화")
        meetings_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(meetings_tab, text="AI 회의 안건·참석자")
        opinions_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(opinions_tab, text="AI 회의 의견 수집·비교")
        decisions_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(decisions_tab, text="AI 회의 결정·후속 업무")
        memories_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(memories_tab, text="직원별 장기 기억")
        knowledge_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(knowledge_tab, text="회사 공동 지식 저장소")
        performance_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(performance_tab, text="성과 평가·업무 개선")
        registry_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(registry_tab, text="AI 작업 도구 등록")
        approvals_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(approvals_tab, text="도구 사용 승인 검사")
        documents_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(documents_tab, text="로컬 문서·파일 작업")
        research_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(research_tab, text="오프라인 조사 자료 수집")
        browser_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(browser_tab, text="허용된 로컬 브라우저 작업")
        coding_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(coding_tab, text="로컬 AI 코드 초안")
        restricted_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(restricted_tab, text="제한형 코드 테스트")
        media_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(media_tab, text="이미지·영상·문서 어댑터")
        service_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(service_tab, text="외부 연동 초안 (오프라인)")
        tool_audit_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(tool_audit_tab, text="도구 사용·실패 기록")
        evidence_business_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(evidence_business_tab, text="거래 증빙·실패 업무 개선")
        staff_reorg_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(staff_reorg_tab, text="실제 직원 성과 기반 조직 개편")
        full_company_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(full_company_tab, text="15부서·31명 실제 회사 협업")
        business_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(business_tab, text="범용 사업 유형·사업 관리")
        discovery_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(discovery_tab, text="수익 사업 후보 가설")
        market_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(market_tab, text="시장 수요·경쟁 근거 검토")
        finance_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(finance_tab, text="비용·수익 가정 평가")
        chief_business_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(chief_business_tab, text="총괄 사업 판단 검토")
        projects_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(projects_tab, text="다중 사업·프로젝트 관리")
        catalog_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(catalog_tab, text="상품·서비스 정보 관리")
        production_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(production_tab, text="로컬 상품 시제품 준비")
        release_review_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(release_review_tab, text="상품 검수·출시 보류 기록")
        service_operations_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(service_operations_tab, text="서비스 배포·운영 계획 (미배포)")
        sales_channels_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(sales_channels_tab, text="판매 채널 연결 계획 (미연결)")
        listing_prices_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(listing_prices_tab, text="상품 등록·가격 초안 (미게시)")
        simulated_orders_tab = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(simulated_orders_tab, text="주문 접수·상태 모의실험 (비실거래)")
        self.quick_navigation["values"] = [self.tabs.tab(i, "text") for i in range(self.tabs.index("end"))]
        self.quick_navigation.set("AI 회사 운영센터")
        from desktop.company_office_gui import mount as mount_company_office
        mount_company_office(self, dashboard)
        self._persistence(persistence)
        self._roadmap(roadmap)
        self._administration(administration)
        self._company(company)
        self._departments(departments)
        self._designations(designations)
        self._employees(employees)
        self._hierarchy(hierarchy)
        self._employee_access(access)
        self._local_models(models)
        self._employee_models(employee_models)
        self._chief_chat(chief_chat)
        self._work_plans(work_plans)
        self._tasks(tasks)
        self._task_routing(task_routing)
        self._task_dependencies(task_dependencies)
        self._task_execution(task_execution)
        self._task_artifacts(task_artifacts)
        self._chief_tasks(chief_tasks)
        self._health_monitor(health_monitor)
        self._company_detection(detection)
        self._autonomous_task_proposals(auto_proposals)
        self._task_breakdowns(breakdowns)
        self._recurring_scheduler(recurring)
        self._event_task_panel(event_tab)
        self._task_queue_panel(queue_tab)
        self._direct_messages_panel(messages_tab)
        self._department_chat_panel(department_chat_tab)
        self._project_chat_panel(project_chat_tab)
        self._meetings_panel(meetings_tab)
        self._meeting_opinions_panel(opinions_tab)
        self._meeting_decisions_panel(decisions_tab)
        self._employee_memories_panel(memories_tab)
        self._company_knowledge_panel(knowledge_tab)
        self._performance_panel(performance_tab)
        self._managed_documents_panel(documents_tab)
        self._offline_research_panel(research_tab)
        self._offline_browser_panel(browser_tab)
        self._code_authoring_panel(coding_tab)
        self._restricted_code_panel(restricted_tab)
        self._media_adapter_panel(media_tab)
        self._service_drafts_panel(service_tab)
        self._tool_audit_panel(tool_audit_tab)
        self._evidence_business_panel(evidence_business_tab)
        self._staff_reorg_panel(staff_reorg_tab)
        self._full_company_panel(full_company_tab)
        self._business_portfolio_panel(business_tab)
        self._business_discovery_panel(discovery_tab)
        self._market_evidence_panel(market_tab)
        self._financial_feasibility_panel(finance_tab)
        self._chief_business_decisions_panel(chief_business_tab)
        self._business_projects_panel(projects_tab)
        self._product_catalog_panel(catalog_tab)
        self._product_production_panel(production_tab)
        self._product_release_review_panel(release_review_tab)
        self._service_operations_panel(service_operations_tab)
        self._sales_channels_panel(sales_channels_tab)
        self._unpublished_listing_panel(listing_prices_tab)
        self._simulated_orders_panel(simulated_orders_tab)
        self._tool_registry_panel(registry_tab)
        self._tool_approval_panel(approvals_tab)
        self.tabs.bind("<<NotebookTabChanged>>", self._tab_changed)
        tk.Label(outer, text="실행 상태는 실제 SQLite·로컬 모델 기준  ·  대외 판매·결제는 별도 연동 검증 필요", bg="#121c2d", fg="#91aacd", font=("Malgun Gothic", 9)).pack(anchor="w", pady=(5, 0))

    def _jump_to_tab(self, event=None) -> None:
        self.store.require_permission("agents:manage")
        choice = self.quick_navigation.get()
        if choice in self.quick_navigation["values"]:
            self.tabs.select(list(self.quick_navigation["values"]).index(choice))

    def _open_persistence(self, event=None) -> None:
        """One-click real GUI navigation to note persistence."""
        self.store.require_permission("notes:read")
        self.tabs.select(1)
        self.quick_navigation.current(1)
        self.root.after_idle(self.note_entry.focus_set)

    def _dashboard(self, parent: tk.Frame) -> None:
        section = self._panel(parent)
        section.pack(fill="x", pady=(0, 16))
        self._label(section, "프로그램 실행 상태", size=17, weight="bold").pack(anchor="w")
        self._label(section, "데스크톱 창이 실제 실행되고 있으며 외부 서버가 필요하지 않습니다.", fg="#bfcfe5").pack(anchor="w", pady=(8, 5))
        self._label(section, "SQLite 상태 및 저장 파일", weight="bold").pack(anchor="w", pady=(10, 4))
        self._label(section, "", fg="#8ee4b7", textvariable=self.status_text, wraplength=850, justify="left").pack(anchor="w")
        summary = self._panel(parent)
        summary.pack(fill="x", pady=(0, 16))
        self._label(summary, f"검증 완료 {CURRENT_STAGE} / {TOTAL_STAGES}개 · 개발 순번 100/100 · 실제 인수 미완료", size=17, weight="bold").pack(anchor="w")
        ttk.Progressbar(summary, style="Progress.Horizontal.TProgressbar", maximum=TOTAL_STAGES, value=CURRENT_STAGE).pack(fill="x", pady=(15, 9))
        self._label(summary, "54·56~66단계 일부 미검증/보류 · 완료 개수와 진행 순번은 별도", fg="#bfcfe5").pack(anchor="w")
        missing = self._panel(parent)
        missing.pack(fill="both", expand=True)
        self._label(missing, "아직 없는 기능", size=16, weight="bold").pack(anchor="w")
        self._label(missing, "장기 자율 업무 운영 / 자동 사업 기회 분석 / 사업 및 매출 시스템", fg="#f7cb92", wraplength=850, justify="left").pack(anchor="w", pady=(10, 5))
        self._label(missing, "현재 기능: 회사·직원·업무·로컬 모델 실행·검수·총괄 지시·회사 상태 자동 집계.", fg="#bfcfe5", wraplength=850, justify="left").pack(anchor="w")

    def _persistence(self, parent: tk.Frame) -> None:
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "PC 실사용 검사", size=18, weight="bold").pack(anchor="w")
        self._label(panel, "메모를 저장한 뒤 EXE를 종료하고 다시 실행하여 같은 메모가 남아 있는지 확인하세요.", fg="#bfcfe5", wraplength=800, justify="left").pack(anchor="w", pady=(12, 18))
        self._label(panel, "검사용 메모 (최대 120자, 비밀번호 입력 금지)", weight="bold").pack(anchor="w", pady=(0, 8))
        self.note_entry = tk.Entry(panel, textvariable=self.note, width=90, font=("Malgun Gothic", 12), bg="#f8fbff", fg="#162037", relief="flat", highlightthickness=1, highlightbackground="#8ab0e9")
        self.note_entry.pack(fill="x", ipady=12)
        buttons = tk.Frame(panel, bg="#1c2a40")
        buttons.pack(anchor="w", pady=(16, 10))
        self.save_button = tk.Button(buttons, text="메모 저장", command=self.save_note, bg="#4c83e6", fg="white", activebackground="#689bef", padx=20, pady=9, relief="flat", font=("Malgun Gothic", 11, "bold"))
        self.save_button.pack(side="left", padx=(0, 10))
        tk.Button(buttons, text="저장 내용 다시 읽기", command=self.reload_note, bg="#304561", fg="#f4f7ff", activebackground="#526b8f", padx=20, pady=9, relief="flat", font=("Malgun Gothic", 11)).pack(side="left")
        self._label(panel, "", textvariable=self.feedback, fg="#9cdbbb", wraplength=800, justify="left").pack(anchor="w", pady=(10, 14))
        self._label(panel, "데이터는 사용자 계정의 로컬 저장 폴더에 기록되며 GitHub로 전송되지 않습니다.", fg="#bfcfe5", wraplength=790).pack(anchor="w")

    def _roadmap(self, parent: tk.Frame) -> None:
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "개발 단계 목록", size=18, weight="bold").pack(anchor="w", pady=(0, 12))
        frame = tk.Frame(panel)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=("stage", "name", "state"), show="headings")
        tree.heading("stage", text="단계")
        tree.heading("name", text="개발 작업")
        tree.heading("state", text="상태")
        tree.column("stage", width=70, anchor="center", stretch=False)
        tree.column("name", width=600, anchor="w")
        tree.column("state", width=100, anchor="center", stretch=False)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for item in steps():
            status = "완료" if item["status"] == "DONE" else ("보류" if item["status"] == "BLOCKED" else "미완료")
            tree.insert("", "end", values=(item["step"], item["name"], status))
        self.roadmap_tree = tree

    def _administration(self, parent: tk.Frame) -> None:
        """Owner-only navigation shell. Future actions are intentionally absent."""
        self.store.require_permission("company:manage")
        header = self._panel(parent)
        header.pack(fill="x", pady=(0, 12))
        self._label(header, "회사 관리자 센터", size=18, weight="bold").pack(anchor="w")
        self._label(header, "관리자 인증 완료 · 실제 기능과 미구현 기능을 구분합니다.", fg="#bfcfe5").pack(anchor="w", pady=(7, 0))
        content = tk.Frame(parent, bg="#121c2d")
        content.pack(fill="both", expand=True)
        sidebar = self._panel(content)
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        self._label(sidebar, "관리 영역", weight="bold").pack(anchor="w", pady=(0, 9))
        self.admin_navigation: dict[str, tk.Button] = {}
        for section in SECTIONS:
            button = tk.Button(
                sidebar, text=section.title, width=17, anchor="w", bg="#304561", fg="#f4f7ff",
                relief="flat", pady=10, padx=12, font=("Malgun Gothic", 10),
                command=lambda key=section.key: self.show_admin_section(key),
            )
            button.pack(fill="x", pady=3)
            self.admin_navigation[section.key] = button
        details = self._panel(content)
        details.pack(side="left", fill="both", expand=True)
        self.admin_title = tk.StringVar(value="")
        self.admin_state = tk.StringVar(value="")
        self.admin_description = tk.StringVar(value="")
        self.admin_features = tk.StringVar(value="")
        self.admin_realtime = tk.StringVar(value="")
        self._label(details, "", textvariable=self.admin_title, size=18, weight="bold").pack(anchor="w", pady=(0, 12))
        self._label(details, "", textvariable=self.admin_state, fg="#8ee4b7").pack(anchor="w", pady=(0, 12))
        self._label(details, "", textvariable=self.admin_description, fg="#d8e3f3", wraplength=530, justify="left").pack(anchor="w", pady=(0, 12))
        self._label(details, "", textvariable=self.admin_features, fg="#bed0e8", wraplength=530, justify="left").pack(anchor="w", pady=(0, 15))
        self._label(details, "", textvariable=self.admin_realtime, fg="#93dcb5", wraplength=530, justify="left").pack(anchor="w", pady=(0, 12))
        self._label(details, "이 화면에서 미구현 기능은 실행할 수 없습니다. 실제 외부 거래·연동도 없습니다.",
                    fg="#f7cb92", wraplength=530, justify="left").pack(anchor="w")
        self.current_admin_section = ""
        self.show_admin_section("overview")

    def show_admin_section(self, key: str) -> None:
        """Switch a real widget's content only after owner permission is checked."""
        self.store.require_permission("company:manage")
        section = section_for(key)
        self.current_admin_section = section.key
        self.admin_title.set(section.title)
        self.admin_state.set(section.status)
        self.admin_description.set(section.summary)
        self.admin_features.set("준비 기능 / 확인 항목:\n" + "\n".join("· " + item for item in section.planned_features))
        if section.key == "overview":
            status = self.store.health()
            self.admin_realtime.set("SQLite 정상 · " + status["database"])
        elif section.key == "departments":
            self.admin_realtime.set(f"등록 부서 {len(self.store.list_departments())}개 · 직급·직무·역할 {len(self.store.list_designations())}개 · AI 직원 정보 {len(self.store.list_employee_records())}건 (AI 실행 미구현)")
        elif section.key == "tasks":
            records=self.store.list_tasks()
            self.admin_realtime.set(f"로컬 업무 {len(records)}건 · 완료 {sum(item['status']=='done' for item in records)}건 (AI 실행 미구현)")
        elif section.key == "permissions":
            self.admin_realtime.set("현재 로그인 역할: " + str(self.store.role()) + " (기본 권한 확인 완료)")
        else:
            self.admin_realtime.set("실제 데이터 및 실행 기능은 아직 없습니다.")
        for button_key, button in self.admin_navigation.items():
            button.configure(bg="#3659ab" if button_key == key else "#304561")

    def _company(self, parent: tk.Frame) -> None:
        """Owner-only native profile form and goal CRUD; no external API."""
        self.store.require_permission("company:manage")
        self.company_feedback = tk.StringVar(value="회사 설정과 목표는 이 PC의 SQLite에만 저장됩니다.")
        profile = self.store.read_company()
        self.company_name = tk.StringVar(value=profile["name"])
        self.company_description = tk.StringVar(value=profile["description"])
        self.company_mission = tk.StringVar(value=profile["mission"])
        upper = self._panel(parent)
        upper.pack(fill="x", pady=(0, 10))
        self._label(upper, "회사 정보", size=16, weight="bold").grid(row=0, column=0, sticky="w", columnspan=2, pady=(0, 9))
        for i, (caption, value) in enumerate((("회사명", self.company_name), ("회사 소개", self.company_description), ("운영 방향", self.company_mission)), start=1):
            self._label(upper, caption).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 12))
            tk.Entry(upper, textvariable=value, font=("Malgun Gothic", 10), width=63).grid(row=i, column=1, sticky="ew", pady=4, ipady=3)
        upper.grid_columnconfigure(1, weight=1)
        self.company_save_button = tk.Button(upper, text="회사 정보 저장", command=self.save_company, bg="#4c83e6", fg="white", padx=15, pady=6)
        self.company_save_button.grid(row=4, column=1, sticky="w", pady=(9, 0))
        lower = self._panel(parent)
        lower.pack(fill="both", expand=True)
        self._label(lower, "운영 목표", size=16, weight="bold").pack(anchor="w", pady=(0, 5))
        row = tk.Frame(lower, bg="#1c2a40")
        row.pack(fill="x")
        self.goal_title = tk.StringVar(value="")
        self.goal_detail = tk.StringVar(value="")
        self.goal_status = tk.StringVar(value="planned")
        self._label(row, "목표명").grid(row=0, column=0, padx=(0, 5), sticky="w")
        tk.Entry(row, textvariable=self.goal_title, width=35).grid(row=0, column=1, sticky="ew", padx=(0, 9), ipady=4)
        self._label(row, "설명").grid(row=0, column=2, padx=(0, 5), sticky="w")
        tk.Entry(row, textvariable=self.goal_detail, width=32).grid(row=0, column=3, sticky="ew", ipady=4)
        row.grid_columnconfigure(1, weight=2)
        row.grid_columnconfigure(3, weight=3)
        controls = tk.Frame(lower, bg="#1c2a40")
        controls.pack(fill="x", pady=(7, 7))
        self._label(controls, "상태").pack(side="left")
        self.goal_status_selector = ttk.Combobox(controls, textvariable=self.goal_status,
                                                 values=["planned", "active", "paused", "done"],
                                                 state="readonly", width=12)
        self.goal_status_selector.pack(side="left", padx=(6, 12))
        self.goal_add_button = tk.Button(controls, text="목표 추가", command=self.add_goal, bg="#4c83e6", fg="white")
        self.goal_add_button.pack(side="left", padx=(0, 8))
        self.goal_update_button = tk.Button(controls, text="선택 목표 수정", command=self.update_goal)
        self.goal_update_button.pack(side="left", padx=(0, 8))
        self.goal_delete_button = tk.Button(controls, text="선택 목표 삭제", command=self.delete_goal)
        self.goal_delete_button.pack(side="left")
        listing = tk.Frame(lower)
        listing.pack(fill="both", expand=True)
        self.goal_tree = ttk.Treeview(listing, columns=("id", "title", "status", "detail"), show="headings", height=5)
        for key, title, width in (("id", "번호", 58), ("title", "목표명", 220), ("status", "상태", 90), ("detail", "설명", 320)):
            self.goal_tree.heading(key, text=title)
            self.goal_tree.column(key, width=width, stretch=(key != "id"))
        self.goal_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.goal_tree.yview)
        scroll.pack(side="right", fill="y")
        self.goal_tree.configure(yscrollcommand=scroll.set)
        self.goal_tree.bind("<<TreeviewSelect>>", self._load_goal_selection)
        self._label(lower, "", textvariable=self.company_feedback, fg="#9cdbbb", wraplength=740).pack(anchor="w", pady=(5, 0))
        self._reload_goals()

    def _reload_goals(self, selected_id: int | None = None) -> None:
        self.store.require_permission("company:manage")
        for row in self.goal_tree.get_children():
            self.goal_tree.delete(row)
        for item in self.store.list_goals():
            self.goal_tree.insert("", "end", iid=str(item["id"]),
                                  values=(item["id"], item["title"], item["status"], item["detail"]))
        if selected_id is not None and self.goal_tree.exists(str(selected_id)):
            self.goal_tree.selection_set(str(selected_id))

    def _load_goal_selection(self, event=None) -> None:
        self.store.require_permission("company:manage")
        selection = self.goal_tree.selection()
        if not selection:
            return
        for item in self.store.list_goals():
            if str(item["id"]) == selection[0]:
                self.goal_title.set(str(item["title"]))
                self.goal_detail.set(str(item["detail"]))
                self.goal_status.set(str(item["status"]))
                return

    def _selected_goal_id(self) -> int:
        self.store.require_permission("company:manage")
        selection = self.goal_tree.selection()
        if not selection:
            raise ValueError("목표 목록에서 수정·삭제할 대상을 먼저 선택하세요.")
        return int(selection[0])

    def save_company(self) -> None:
        try:
            self.store.save_company(self.company_name.get(), self.company_description.get(), self.company_mission.get())
            self.company_feedback.set("회사 정보가 로컬 DB에 저장됐습니다.")
        except (ValueError, PermissionError) as exc:
            self.company_feedback.set(f"저장 실패: {exc}")

    def add_goal(self) -> None:
        try:
            goal_id = self.store.add_goal(self.goal_title.get(), self.goal_detail.get())
            self.goal_status.set("planned")
            self._reload_goals(goal_id)
            self.company_feedback.set("새 목표가 저장됐습니다.")
        except (ValueError, PermissionError) as exc:
            self.company_feedback.set(f"목표 추가 실패: {exc}")

    def update_goal(self) -> None:
        try:
            goal_id = self._selected_goal_id()
            self.store.update_goal(goal_id, self.goal_title.get(), self.goal_detail.get(), self.goal_status.get())
            self._reload_goals(goal_id)
            self.company_feedback.set("선택한 목표가 수정됐습니다.")
        except (ValueError, PermissionError) as exc:
            self.company_feedback.set(f"목표 수정 실패: {exc}")

    def delete_goal(self) -> None:
        try:
            goal_id = self._selected_goal_id()
            # Always require explicit confirmation for deletion in normal UI.
            if not messagebox.askyesno("목표 삭제", "선택한 목표를 정말 삭제하시겠습니까?", parent=self.root):
                self.company_feedback.set("목표 삭제가 취소됐습니다.")
                return
            self.store.delete_goal(goal_id)
            self.goal_title.set("")
            self.goal_detail.set("")
            self.goal_status.set("planned")
            self._reload_goals()
            self.company_feedback.set("선택한 목표가 삭제됐습니다.")
        except (ValueError, PermissionError) as exc:
            self.company_feedback.set(f"목표 삭제 실패: {exc}")

    def _departments(self, parent: tk.Frame) -> None:
        """A functioning native CRUD screen, protected by the owner session."""
        self.store.require_permission("company:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "부서 관리", size=18, weight="bold").pack(anchor="w")
        self._label(panel, "부서를 추가·수정·삭제합니다. AI 직원 연결과 부서 자동 운영은 후속 개발입니다.",
                    fg="#bfcfe5", wraplength=780).pack(anchor="w", pady=(6, 14))
        self.department_name = tk.StringVar(value="")
        self.department_description = tk.StringVar(value="")
        self.department_feedback = tk.StringVar(value="관리자 로그인 후 변경할 수 있습니다.")
        form = tk.Frame(panel, bg="#1c2a40")
        form.pack(fill="x", pady=(0, 10))
        self._label(form, "부서명").grid(row=0, column=0, sticky="w", padx=(0, 8))
        tk.Entry(form, textvariable=self.department_name, width=44, font=("Malgun Gothic", 10)).grid(
            row=0, column=1, sticky="ew", ipady=7)
        self._label(form, "설명·담당 영역").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(9, 0))
        tk.Entry(form, textvariable=self.department_description, width=65, font=("Malgun Gothic", 10)).grid(
            row=1, column=1, sticky="ew", ipady=7, pady=(9, 0))
        form.columnconfigure(1, weight=1)
        controls = tk.Frame(panel, bg="#1c2a40")
        controls.pack(fill="x", pady=(5, 10))
        self.department_add_button = tk.Button(controls, text="부서 추가", command=self.add_department,
                                               bg="#4c83e6", fg="white", padx=12, pady=7)
        self.department_add_button.pack(side="left", padx=(0, 8))
        self.department_update_button = tk.Button(controls, text="선택 부서 수정", command=self.update_department,
                                                  padx=12, pady=7)
        self.department_update_button.pack(side="left", padx=(0, 8))
        self.department_delete_button = tk.Button(controls, text="선택 부서 삭제", command=self.delete_department,
                                                  padx=12, pady=7)
        self.department_delete_button.pack(side="left", padx=(0, 8))
        self.department_clear_button = tk.Button(controls, text="입력 초기화", command=self.clear_department,
                                                 padx=12, pady=7)
        self.department_clear_button.pack(side="left")
        listing = tk.Frame(panel)
        listing.pack(fill="both", expand=True)
        self.department_tree = ttk.Treeview(listing, columns=("id", "name", "description"),
                                            show="headings", height=9)
        for key, label, width in (("id", "번호", 65), ("name", "부서명", 215),
                                  ("description", "설명·담당 영역", 440)):
            self.department_tree.heading(key, text=label)
            self.department_tree.column(key, width=width, stretch=key != "id")
        self.department_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self.department_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.department_tree.configure(yscrollcommand=scrollbar.set)
        self.department_tree.bind("<<TreeviewSelect>>", self._load_department_selection)
        self._label(panel, "", textvariable=self.department_feedback, fg="#9cdbbb", wraplength=760).pack(
            anchor="w", pady=(12, 0))
        self.reload_departments()

    def reload_departments(self, selected_id: int | None = None) -> None:
        self.store.require_permission("company:manage")
        for item in self.department_tree.get_children():
            self.department_tree.delete(item)
        for department in self.store.list_departments():
            self.department_tree.insert("", "end", iid=str(department["id"]),
                                        values=(department["id"], department["name"], department["description"]))
        if selected_id is not None and self.department_tree.exists(str(selected_id)):
            self.department_tree.selection_set(str(selected_id))

    def _load_department_selection(self, event=None) -> None:
        self.store.require_permission("company:manage")
        selected = self.department_tree.selection()
        if selected:
            for department in self.store.list_departments():
                if str(department["id"]) == selected[0]:
                    self.department_name.set(str(department["name"]))
                    self.department_description.set(str(department["description"]))
                    break

    def _selected_department_id(self) -> int:
        self.store.require_permission("company:manage")
        selected = self.department_tree.selection()
        if not selected:
            raise ValueError("목록에서 부서를 먼저 선택하세요.")
        return int(selected[0])

    def clear_department(self) -> None:
        self.store.require_permission("company:manage")
        self.department_tree.selection_remove(self.department_tree.selection())
        self.department_name.set("")
        self.department_description.set("")
        self.department_feedback.set("입력값을 초기화했습니다.")

    def add_department(self) -> None:
        try:
            identifier = self.store.add_department(self.department_name.get(), self.department_description.get())
            self.reload_departments(identifier)
            self.department_feedback.set("부서가 추가됐습니다.")
        except (ValueError, PermissionError) as error:
            self.department_feedback.set(f"추가 실패: {error}")

    def update_department(self) -> None:
        try:
            identifier = self._selected_department_id()
            self.store.update_department(identifier, self.department_name.get(), self.department_description.get())
            self.reload_departments(identifier)
            self.department_feedback.set("부서가 수정됐습니다.")
        except (ValueError, PermissionError) as error:
            self.department_feedback.set(f"수정 실패: {error}")

    def delete_department(self) -> None:
        try:
            identifier = self._selected_department_id()
            if not messagebox.askyesno("부서 삭제", "선택한 부서를 삭제하시겠습니까?\n삭제한 부서는 복원할 수 없습니다.",
                                       parent=self.root):
                self.department_feedback.set("부서 삭제를 취소했습니다.")
                return
            self.store.delete_department(identifier)
            self.department_name.set("")
            self.department_description.set("")
            self.reload_departments()
            self.department_feedback.set("선택한 부서를 삭제했습니다.")
        except (ValueError, PermissionError) as error:
            self.department_feedback.set(f"삭제 실패: {error}")

    def _designations(self, parent: tk.Frame) -> None:
        """Authenticated native rank/job/role catalog. No AI employee or permission grants."""
        self.store.require_permission("company:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "직급·직무·역할 관리", size=18, weight="bold").pack(anchor="w")
        self._label(panel, "직급(서열), 직무(담당 업무), 역할(책임)을 등록합니다. 실제 AI 직원 배치는 14~17단계에 구현합니다.",
                    fg="#bfcfe5", wraplength=750).pack(anchor="w", pady=(6, 12))
        self.designation_kind = tk.StringVar(value="rank")
        self.designation_name = tk.StringVar(value="")
        self.designation_description = tk.StringVar(value="")
        self.designation_feedback = tk.StringVar(value="관리자 로그인 후 변경할 수 있습니다.")
        form = tk.Frame(panel, bg="#1c2a40")
        form.pack(fill="x", pady=(0, 9))
        self._label(form, "구분").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.designation_kind_selector = ttk.Combobox(
            form, textvariable=self.designation_kind, values=("rank", "job", "role"),
            state="readonly", width=13)
        self.designation_kind_selector.grid(row=0, column=1, sticky="w", pady=5)
        self._label(form, "rank=직급 · job=직무 · role=책임 역할 (관리자 권한 부여와 무관)",
                    fg="#bfcfe5").grid(row=0, column=2, sticky="w", padx=8)
        self._label(form, "명칭").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
        tk.Entry(form, textvariable=self.designation_name, width=42).grid(
            row=1, column=1, columnspan=2, sticky="ew", ipady=5, pady=5)
        self._label(form, "설명·책임").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=5)
        tk.Entry(form, textvariable=self.designation_description, width=64).grid(
            row=2, column=1, columnspan=2, sticky="ew", ipady=5, pady=5)
        form.grid_columnconfigure(2, weight=1)
        controls = tk.Frame(panel, bg="#1c2a40")
        controls.pack(anchor="w", pady=(5, 9))
        self.designation_add_button = tk.Button(
            controls, text="새 항목 추가", command=self.add_designation,
            bg="#4c83e6", fg="white", padx=12, pady=7)
        self.designation_add_button.pack(side="left", padx=(0, 8))
        self.designation_update_button = tk.Button(
            controls, text="선택 항목 수정", command=self.update_designation, padx=12, pady=7)
        self.designation_update_button.pack(side="left", padx=(0, 8))
        self.designation_delete_button = tk.Button(
            controls, text="선택 항목 삭제", command=self.delete_designation, padx=12, pady=7)
        self.designation_delete_button.pack(side="left", padx=(0, 8))
        self.designation_clear_button = tk.Button(
            controls, text="입력 초기화", command=self.clear_designation, padx=12, pady=7)
        self.designation_clear_button.pack(side="left")
        listing = tk.Frame(panel)
        listing.pack(fill="both", expand=True)
        self.designation_tree = ttk.Treeview(
            listing, columns=("id", "kind", "name", "description"), show="headings", height=9)
        for key, label, width in (("id", "번호", 60), ("kind", "구분", 100),
                                  ("name", "명칭", 190), ("description", "설명", 320)):
            self.designation_tree.heading(key, text=label)
            self.designation_tree.column(key, width=width, stretch=(key != "id"))
        self.designation_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self.designation_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.designation_tree.configure(yscrollcommand=scrollbar.set)
        self.designation_tree.bind("<<TreeviewSelect>>", self._load_designation_selection)
        self._label(panel, "", textvariable=self.designation_feedback,
                    fg="#9cdbbb", wraplength=760).pack(anchor="w", pady=(12, 0))
        self.reload_designations()

    def reload_designations(self, selected_id: int | None = None) -> None:
        self.store.require_permission("company:manage")
        for row in self.designation_tree.get_children():
            self.designation_tree.delete(row)
        for item in self.store.list_designations():
            self.designation_tree.insert("", "end", iid=str(item["id"]),
                                         values=(item["id"], item["kind"], item["name"], item["description"]))
        if selected_id is not None and self.designation_tree.exists(str(selected_id)):
            self.designation_tree.selection_set(str(selected_id))

    def _load_designation_selection(self, event=None) -> None:
        self.store.require_permission("company:manage")
        selected = self.designation_tree.selection()
        if selected:
            for item in self.store.list_designations():
                if str(item["id"]) == selected[0]:
                    self.designation_kind.set(str(item["kind"]))
                    self.designation_name.set(str(item["name"]))
                    self.designation_description.set(str(item["description"]))
                    return

    def _selected_designation_id(self) -> int:
        self.store.require_permission("company:manage")
        selected = self.designation_tree.selection()
        if not selected:
            raise ValueError("목록에서 직급·직무·역할 항목을 선택하세요.")
        return int(selected[0])

    def clear_designation(self) -> None:
        self.store.require_permission("company:manage")
        self.designation_tree.selection_remove(self.designation_tree.selection())
        self.designation_kind.set("rank")
        self.designation_name.set("")
        self.designation_description.set("")
        self.designation_feedback.set("입력을 초기화했습니다.")

    def add_designation(self) -> None:
        try:
            identifier = self.store.add_designation(
                self.designation_kind.get(), self.designation_name.get(),
                self.designation_description.get())
            self.reload_designations(identifier)
            self.designation_feedback.set("항목이 추가됐습니다.")
        except (ValueError, PermissionError) as error:
            self.designation_feedback.set(f"추가 실패: {error}")

    def update_designation(self) -> None:
        try:
            identifier = self._selected_designation_id()
            self.store.update_designation(
                identifier, self.designation_kind.get(), self.designation_name.get(),
                self.designation_description.get())
            self.reload_designations(identifier)
            self.designation_feedback.set("항목이 수정됐습니다.")
        except (ValueError, PermissionError) as error:
            self.designation_feedback.set(f"수정 실패: {error}")

    def delete_designation(self) -> None:
        try:
            identifier = self._selected_designation_id()
            if not messagebox.askyesno("직급·직무·역할 삭제",
                                       "선택한 항목을 삭제하시겠습니까?\n삭제한 항목은 복원할 수 없습니다.",
                                       parent=self.root):
                self.designation_feedback.set("삭제를 취소했습니다.")
                return
            self.store.delete_designation(identifier)
            self.clear_designation()
            self.reload_designations()
            self.designation_feedback.set("선택한 항목을 삭제했습니다.")
        except (ValueError, PermissionError) as error:
            self.designation_feedback.set(f"삭제 실패: {error}")


    # Stage 15: real owner-only Tk form. Records are NOT executable agents.
    def _employees(self, parent: tk.Frame) -> None:
        self.store.require_permission("agents:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "AI 직원 정보 관리", size=17, weight="bold").pack(anchor="w")
        self._label(panel, "직원 정보의 등록·수정·비활성화만 가능합니다. AI 실행/모델 연결은 미구현입니다.",
                    fg="#f7cb92", wraplength=770).pack(anchor="w", pady=(3, 7))
        self.employee_key = tk.StringVar()
        self.employee_name = tk.StringVar()
        self.employee_description = tk.StringVar()
        self.employee_feedback = tk.StringVar(value="부서·직급·직무·역할은 선택 사항입니다.")
        self.employee_links = {kind: tk.StringVar() for kind in ("department", "rank", "job", "role")}
        form = tk.Frame(panel, bg="#1c2a40")
        form.pack(fill="x", pady=(2, 5))
        for row, (label, variable) in enumerate((
            ("직원 식별자", self.employee_key), ("표시 이름", self.employee_name),
            ("설명", self.employee_description),
        )):
            self._label(form, label).grid(row=row, column=0, sticky="w", padx=(0, 7), pady=3)
            tk.Entry(form, textvariable=variable, width=58).grid(
                row=row, column=1, columnspan=3, sticky="ew", ipady=4, pady=3)
        for col, (kind, label) in enumerate((("department", "부서"), ("rank", "직급"),
                                             ("job", "직무"), ("role", "역할"))):
            self._label(form, label).grid(row=3, column=col, sticky="w", pady=(6, 1))
        self.employee_choices: dict[str, ttk.Combobox] = {}
        for col, kind in enumerate(("department", "rank", "job", "role")):
            combo = ttk.Combobox(form, textvariable=self.employee_links[kind],
                                 state="readonly", width=18)
            combo.grid(row=4, column=col, sticky="ew", padx=(0, 8), pady=3)
            self.employee_choices[kind] = combo
        for col in range(4):
            form.grid_columnconfigure(col, weight=1)
        controls = tk.Frame(panel, bg="#1c2a40")
        controls.pack(anchor="w", pady=(5, 6))
        operations = (
            ("직원 등록", self.create_employee), ("선택 직원 수정", self.update_employee),
            ("비활성화", self.deactivate_employee), ("초안으로 복귀", self.restore_employee),
            ("목록 새로고침", self.reload_employees),
        )
        self.employee_buttons = {}
        for label, callback in operations:
            btn = tk.Button(controls, text=label, command=callback, padx=8, pady=5,
                            bg="#426cba" if label == "직원 등록" else "#304561", fg="white")
            btn.pack(side="left", padx=(0, 6))
            self.employee_buttons[label] = btn
        self.employee_create_button = self.employee_buttons["직원 등록"]
        self.employee_update_button = self.employee_buttons["선택 직원 수정"]
        self.employee_inactive_button = self.employee_buttons["비활성화"]
        self.employee_restore_button = self.employee_buttons["초안으로 복귀"]
        listing = tk.Frame(panel)
        listing.pack(fill="both", expand=True)
        cols = ("id", "employee_key", "display_name", "department", "rank", "job", "role", "lifecycle")
        self.employee_tree = ttk.Treeview(listing, columns=cols, show="headings", height=6)
        headings = ("번호", "식별자", "이름", "부서", "직급", "직무", "역할", "상태")
        widths = (47, 126, 130, 95, 75, 75, 75, 85)
        for key, title, width in zip(cols, headings, widths):
            self.employee_tree.heading(key, text=title)
            self.employee_tree.column(key, width=width, stretch=key != "id")
        self.employee_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.employee_tree.yview)
        scroll.pack(side="right", fill="y")
        self.employee_tree.configure(yscrollcommand=scroll.set)
        self.employee_tree.bind("<<TreeviewSelect>>", self._load_employee_selection)
        self._label(panel, "", textvariable=self.employee_feedback,
                    fg="#9cdbbb", wraplength=770).pack(anchor="w", pady=(7, 0))
        self.refresh_employee_choices()
        self.reload_employees()

    def _tab_changed(self, event=None) -> None:
        if not self.store.is_authenticated:
            return
        selected = self.tabs.select()
        if selected == str(self.tabs.tabs()[7]):
            self.refresh_employee_choices()
            self.reload_employees()
        elif selected == str(self.tabs.tabs()[8]):
            self.reload_hierarchy()
        elif selected == str(self.tabs.tabs()[9]):
            self.refresh_access_employees()
        elif selected == str(self.tabs.tabs()[11]):
            self.refresh_employee_model_choices()
        elif selected == str(self.tabs.tabs()[12]):
            self.refresh_chief_state()
        elif selected == str(self.tabs.tabs()[13]):
            self.refresh_work_plan_goals()
            self.reload_work_plans()
        elif selected == str(self.tabs.tabs()[14]):
            self.reload_tasks()
        elif selected == str(self.tabs.tabs()[15]):
            self.refresh_task_routing_choices()
        elif selected == str(self.tabs.tabs()[17]):
            self.refresh_task_execution_choices()
        elif selected == str(self.tabs.tabs()[19]):
            self.refresh_chief_task_choices()
        elif selected == str(self.tabs.tabs()[20]):
            self.refresh_company_health_view()
        elif selected == str(self.tabs.tabs()[21]):
            self.refresh_company_detection_view()
        elif selected == str(self.tabs.tabs()[22]):
            self.refresh_autonomous_task_proposals()
        elif selected == str(self.tabs.tabs()[23]):
            self.refresh_task_breakdowns()

    def refresh_employee_choices(self) -> None:
        self.store.require_permission("agents:manage")
        catalogs = {"department": self.store.list_departments()}
        catalogs.update({kind: self.store.list_designations(kind)
                         for kind in ("rank", "job", "role")})
        self.employee_catalogs: dict[str, dict[int, str]] = {}
        for kind, rows in catalogs.items():
            existing = self.employee_links[kind].get()
            names = {int(x["id"]): str(x["name"]) for x in rows}
            self.employee_catalogs[kind] = names
            options = [""] + [f"{identifier} · {name}" for identifier, name in names.items()]
            self.employee_choices[kind]["values"] = options
            self.employee_links[kind].set(existing if existing in options else "")

    @staticmethod
    def _employee_choice_id(text: str) -> int | None:
        if not text:
            return None
        try:
            value = int(text.split(" · ", 1)[0])
        except (ValueError, IndexError) as exc:
            raise ValueError("부서·직급·직무·역할을 목록에서 선택하세요.") from exc
        if value < 1:
            raise ValueError("항목 번호가 올바르지 않습니다.")
        return value

    def _employee_values(self) -> dict[str, int | None]:
        result = {}
        for kind in ("department", "rank", "job", "role"):
            selection = self.employee_links[kind].get()
            if selection and selection not in self.employee_choices[kind]["values"]:
                raise ValueError("이전 목록의 항목입니다. 선택 목록을 새로고침하세요.")
            result[kind + "_id"] = self._employee_choice_id(selection)
        return result

    def reload_employees(self, selected_id: int | None = None) -> None:
        self.store.require_permission("agents:manage")
        for item in self.employee_tree.get_children():
            self.employee_tree.delete(item)
        for record in self.store.list_employee_records():
            names = [self.employee_catalogs[kind].get(record[kind + "_id"], "—")
                     for kind in ("department", "rank", "job", "role")]
            self.employee_tree.insert("", "end", iid=str(record["id"]),
                                      values=(record["id"], record["employee_key"],
                                              record["display_name"], *names,
                                              "비활성" if record["lifecycle"] == "inactive" else "초안"))
        if selected_id is not None and self.employee_tree.exists(str(selected_id)):
            self.employee_tree.selection_set(str(selected_id))

    def _load_employee_selection(self, event=None) -> None:
        self.store.require_permission("agents:manage")
        selection = self.employee_tree.selection()
        if not selection:
            return
        record = self.store.read_employee_record(int(selection[0]))
        self.employee_key.set(str(record["employee_key"]))
        self.employee_name.set(str(record["display_name"]))
        self.employee_description.set(str(record["description"]))
        self.refresh_employee_choices()
        for kind in ("department", "rank", "job", "role"):
            identifier = record[kind + "_id"]
            name = self.employee_catalogs[kind].get(identifier)
            self.employee_links[kind].set(f"{identifier} · {name}" if name is not None else "")
        self.employee_feedback.set(f"선택 직원 #{record['id']} · 상태: {record['lifecycle']}")

    def _selected_employee_id(self) -> int:
        selection = self.employee_tree.selection()
        if not selection:
            raise ValueError("직원 목록에서 항목을 선택하세요.")
        return int(selection[0])

    def create_employee(self) -> None:
        try:
            identifier = self.store.add_employee_draft(self.employee_key.get(),
                self.employee_name.get(), self.employee_description.get(), **self._employee_values())
            self.reload_employees(selected_id=identifier)
            self.employee_feedback.set("AI 직원 정보를 초안으로 등록했습니다. AI는 실행되지 않습니다.")
        except (ValueError, PermissionError) as exc:
            self.employee_feedback.set(f"등록 실패: {exc}")

    def update_employee(self) -> None:
        try:
            identifier = self._selected_employee_id()
            record = self.store.read_employee_record(identifier)
            if record["employee_key"] != self.employee_key.get():
                raise ValueError("식별자는 수정할 수 없습니다.")
            self.store.update_employee_record(identifier, self.employee_name.get(),
                self.employee_description.get(), **self._employee_values())
            self.reload_employees(selected_id=identifier)
            self.employee_feedback.set("AI 직원 정보 수정 완료 (AI 미실행).")
        except (ValueError, PermissionError) as exc:
            self.employee_feedback.set(f"수정 실패: {exc}")

    def deactivate_employee(self) -> None:
        try:
            identifier = self._selected_employee_id()
            if not messagebox.askyesno("직원 비활성화", "선택 직원 정보를 비활성화하시겠습니까?",
                                       parent=self.root):
                self.employee_feedback.set("비활성화를 취소했습니다.")
                return
            self.store.set_employee_inactive(identifier)
            self.reload_employees(selected_id=identifier)
            self.employee_feedback.set("직원 정보를 비활성화했습니다. 실행 중인 AI는 없습니다.")
        except (ValueError, PermissionError) as exc:
            self.employee_feedback.set(f"비활성화 실패: {exc}")

    def restore_employee(self) -> None:
        try:
            identifier = self._selected_employee_id()
            self.store.restore_employee_draft(identifier)
            self.reload_employees(selected_id=identifier)
            self.employee_feedback.set("비활성 정보를 초안으로 복귀했습니다. AI는 실행되지 않습니다.")
        except (ValueError, PermissionError) as exc:
            self.employee_feedback.set(f"복귀 실패: {exc}")

    # Stage 16: real native reporting-tree view, backed by local SQLite only.
    _TIER_LABELS = {"ceo": "총괄 AI", "department_head": "부서장", "staff": "직원"}

    def _hierarchy(self, parent: tk.Frame) -> None:
        self.store.require_permission("agents:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "AI 조직 지휘 체계", size=17, weight="bold").pack(anchor="w")
        self._label(panel, "총괄 AI → 부서장 → 직원 관계만 저장합니다. 모델 실행·권한 부여는 아직 없습니다.",
                    fg="#f7cb92", wraplength=790).pack(anchor="w", pady=(4, 12))
        form = tk.Frame(panel, bg="#1c2a40")
        form.pack(fill="x")
        self.hierarchy_tier = tk.StringVar(value="staff")
        self.hierarchy_manager = tk.StringVar()
        self.hierarchy_feedback = tk.StringVar(value="직원 목록에서 항목을 선택해 보고 관계를 등록하세요.")
        self._label(form, "계층").grid(row=0, column=0, sticky="w", pady=3)
        self.hierarchy_tier_combo = ttk.Combobox(form, textvariable=self.hierarchy_tier,
                    values=list(self._TIER_LABELS), state="readonly", width=19)
        self.hierarchy_tier_combo.grid(row=0, column=1, sticky="w", padx=9)
        self.hierarchy_tier_combo.bind("<<ComboboxSelected>>", lambda event: self.refresh_hierarchy_managers())
        self._label(form, "상급자").grid(row=0, column=2, sticky="w")
        self.hierarchy_manager_combo = ttk.Combobox(form, textvariable=self.hierarchy_manager,
                    state="readonly", width=32)
        self.hierarchy_manager_combo.grid(row=0, column=3, sticky="w", padx=9)
        buttons = tk.Frame(panel, bg="#1c2a40")
        buttons.pack(anchor="w", pady=(9, 10))
        self.hierarchy_assign_button = tk.Button(buttons, text="보고 체계 저장", command=self.assign_hierarchy,
                                                 bg="#426cba", fg="white", padx=12, pady=6)
        self.hierarchy_assign_button.pack(side="left", padx=(0, 8))
        self.hierarchy_clear_button = tk.Button(buttons, text="선택 배정 해제", command=self.unassign_hierarchy,
                                                bg="#304561", fg="white", padx=12, pady=6)
        self.hierarchy_clear_button.pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="새로고침", command=self.reload_hierarchy,
                  bg="#304561", fg="white", padx=12, pady=6).pack(side="left")
        listing = tk.Frame(panel)
        listing.pack(fill="both", expand=True)
        self.hierarchy_tree = ttk.Treeview(listing, columns=("tier", "department", "state"),
                                          show="tree headings", height=10)
        self.hierarchy_tree.heading("#0", text="직원 / 보고 조직")
        self.hierarchy_tree.column("#0", width=310, stretch=True)
        for key, title, width in (("tier", "직책", 100), ("department", "부서", 175),
                                  ("state", "프로필 상태", 100)):
            self.hierarchy_tree.heading(key, text=title)
            self.hierarchy_tree.column(key, width=width)
        self.hierarchy_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.hierarchy_tree.yview)
        scroll.pack(side="right", fill="y")
        self.hierarchy_tree.configure(yscrollcommand=scroll.set)
        self.hierarchy_tree.bind("<<TreeviewSelect>>", self._select_hierarchy_employee)
        self._label(panel, "", textvariable=self.hierarchy_feedback, fg="#9cdbbb",
                    wraplength=780).pack(anchor="w", pady=(9, 0))
        self.reload_hierarchy()

    def refresh_hierarchy_managers(self) -> None:
        self.store.require_permission("agents:manage")
        selected = self.hierarchy_manager.get()
        tier = self.hierarchy_tier.get()
        expected = "ceo" if tier == "department_head" else "department_head" if tier == "staff" else None
        assigned = self.store.list_reporting_lines()
        names = {int(x["id"]): str(x["display_name"]) for x in self.store.list_employee_records()}
        options = [f"{x['employee_id']} · {names[x['employee_id']]}" for x in assigned
                   if x['tier'] == expected] if expected else []
        self.hierarchy_manager_combo["values"] = options
        self.hierarchy_manager.set(selected if selected in options else "")
        self.hierarchy_manager_combo.configure(state="readonly" if expected else "disabled")

    def reload_hierarchy(self, selected_id: int | None = None) -> None:
        self.store.require_permission("agents:manage")
        records = self.store.list_employee_records()
        assignments = {r["employee_id"]: r for r in self.store.list_reporting_lines()}
        departments = {r["id"]: r["name"] for r in self.store.list_departments()}
        self.hierarchy_tree.delete(*self.hierarchy_tree.get_children())
        # Parents must be inserted before children (CEO, head, staff, unassigned).
        for tier in ("ceo", "department_head", "staff", "unassigned"):
            for r in records:
                a = assignments.get(r["id"])
                current = a["tier"] if a else "unassigned"
                if current != tier:
                    continue
                parent_id = a["manager_id"] if a else None
                parent = str(parent_id) if parent_id is not None and self.hierarchy_tree.exists(str(parent_id)) else ""
                self.hierarchy_tree.insert(parent, "end", iid=str(r["id"]),
                    text=f"#{r['id']}  {r['display_name']}",
                    values=(self._TIER_LABELS.get(current, "미배정"),
                            departments.get(r["department_id"], "—"),
                            "비활성" if r["lifecycle"] == "inactive" else "초안"), open=True)
        self.refresh_hierarchy_managers()
        if selected_id is not None and self.hierarchy_tree.exists(str(selected_id)):
            self.hierarchy_tree.selection_set(str(selected_id))

    def _select_hierarchy_employee(self, event=None) -> None:
        self.store.require_permission("agents:manage")
        selected = self.hierarchy_tree.selection()
        if not selected:
            return
        employee_id = int(selected[0])
        assignment = next((x for x in self.store.list_reporting_lines() if x["employee_id"] == employee_id), None)
        self.hierarchy_tier.set(assignment["tier"] if assignment else "staff")
        self.refresh_hierarchy_managers()
        if assignment and assignment["manager_id"] is not None:
            name = self.store.read_employee_record(assignment["manager_id"])["display_name"]
            self.hierarchy_manager.set(f"{assignment['manager_id']} · {name}")
        self.hierarchy_feedback.set(f"선택 직원 #{employee_id} · 관계를 편집할 수 있습니다.")

    def assign_hierarchy(self) -> None:
        try:
            selected = self.hierarchy_tree.selection()
            if not selected:
                raise ValueError("조직 목록에서 직원을 선택하세요.")
            tier = self.hierarchy_tier.get()
            raw = self.hierarchy_manager.get()
            if raw and raw not in self.hierarchy_manager_combo["values"]:
                raise ValueError("상급자를 목록에서 선택하세요.")
            manager = self._employee_choice_id(raw)
            employee_id = int(selected[0])
            self.store.assign_reporting_line(employee_id, tier, manager)
            self.reload_hierarchy(employee_id)
            self.hierarchy_feedback.set("보고 체계를 로컬 DB에 저장했습니다. AI 실행은 시작되지 않습니다.")
        except (ValueError, PermissionError) as exc:
            self.hierarchy_feedback.set(f"저장 실패: {exc}")

    def unassign_hierarchy(self) -> None:
        try:
            selected = self.hierarchy_tree.selection()
            if not selected:
                raise ValueError("해제할 직원을 선택하세요.")
            if not messagebox.askyesno("조직 배정 해제", "선택 직원의 보고 관계를 해제할까요?",
                                       parent=self.root):
                return
            employee_id = int(selected[0])
            self.store.unassign_reporting_line(employee_id)
            self.reload_hierarchy(employee_id)
            self.hierarchy_feedback.set("조직 보고 관계를 해제했습니다.")
        except (ValueError, PermissionError) as exc:
            self.hierarchy_feedback.set(f"해제 실패: {exc}")

    # Stage 17: all controls are local configuration widgets, NOT tool launchers.
    def _employee_access(self, parent: tk.Frame) -> None:
        self.store.require_permission("agents:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "AI 직원별 권한 및 도구 설정", size=17, weight="bold").pack(anchor="w")
        self._label(panel, "실행은 미구현입니다. 허가 목록을 로컬에 저장할 뿐 네트워크·도구·AI 모델을 호출하지 않습니다.",
                    fg="#f7cb92", wraplength=820).pack(anchor="w", pady=(4, 12))
        top = tk.Frame(panel, bg="#1c2a40")
        top.pack(fill="x", pady=(0, 10))
        self._label(top, "대상 직원").pack(side="left", padx=(0, 12))
        self.access_employee = tk.StringVar(value="")
        self.access_employee_combo = ttk.Combobox(top, textvariable=self.access_employee, state="readonly", width=47)
        self.access_employee_combo.pack(side="left", fill="x", expand=True)
        self.access_employee_combo.bind("<<ComboboxSelected>>", self.load_employee_access)
        tk.Button(top, text="직원 목록 새로고침", command=self.refresh_access_employees,
                  bg="#304561", fg="white", padx=10, pady=5).pack(side="left", padx=(10, 0))
        self.access_cap_vars = {k: tk.BooleanVar(value=False) for k in CAPABILITIES}
        self.access_tool_vars = {k: tk.BooleanVar(value=False) for k in TOOLS}
        columns = tk.Frame(panel, bg="#1c2a40")
        columns.pack(fill="both", expand=True)
        for title, definitions, vars_ in (
            ("작업 권한 (최초 모두 거부)", CAPABILITIES, self.access_cap_vars),
            ("허용 도구 (로컬 현황 조회만 구현)", TOOLS, self.access_tool_vars),
        ):
            section = tk.Frame(columns, bg="#1c2a40")
            section.pack(side="left", fill="both", expand=True, padx=(0, 10))
            self._label(section, title, weight="bold").pack(anchor="w", pady=(0, 8))
            for key, definition in definitions.items():
                label = definition if isinstance(definition, str) else definition[0]
                tk.Checkbutton(section, text=label, variable=vars_[key], bg="#1c2a40",
                               fg="#eaf0ff", selectcolor="#304561", activebackground="#1c2a40",
                               activeforeground="#ffffff", anchor="w", justify="left",
                               wraplength=350).pack(anchor="w", pady=5)
        buttons = tk.Frame(panel, bg="#1c2a40")
        buttons.pack(anchor="w", pady=(6, 8))
        self.access_save_button = tk.Button(buttons, text="권한·도구 저장", command=self.save_access_settings,
                                            bg="#426cba", fg="white", padx=18, pady=7)
        self.access_save_button.pack(side="left", padx=(0, 9))
        self.access_revoke_button = tk.Button(buttons, text="전체 허가 취소", command=self.revoke_access_settings,
                                              bg="#304561", fg="white", padx=18, pady=7)
        self.access_revoke_button.pack(side="left")
        self.access_feedback = tk.StringVar(value="직원을 선택하세요. 등록 시 기본 허가가 없습니다.")
        self._label(panel, "", textvariable=self.access_feedback, fg="#9cdbbb", wraplength=780).pack(anchor="w")
        self.refresh_access_employees()

    def refresh_access_employees(self) -> None:
        self.store.require_permission("agents:manage")
        original = self.access_employee.get()
        entries = [f"{row['id']} · {row['display_name']} [{row['lifecycle']}]"
                   for row in self.store.list_employee_records()]
        self.access_employee_combo["values"] = entries
        self.access_employee.set(original if original in entries else "")
        self.load_employee_access()

    def _selected_access_employee(self) -> int:
        self.store.require_permission("agents:manage")
        value = self.access_employee.get()
        if value not in self.access_employee_combo["values"]:
            raise ValueError("목록에서 직원을 선택하세요.")
        return int(value.split(" · ", 1)[0])

    def load_employee_access(self, event=None) -> None:
        self.store.require_permission("agents:manage")
        for var in (*self.access_cap_vars.values(), *self.access_tool_vars.values()):
            var.set(False)
        if not self.access_employee.get():
            self.access_feedback.set("직원을 선택하세요. 등록 시 기본 허가가 없습니다.")
            return
        record = self.store.read_employee_access(self._selected_access_employee())
        for key in record["capabilities"]:
            self.access_cap_vars[key].set(True)
        for key in record["tools"]:
            self.access_tool_vars[key].set(True)
        self.access_feedback.set("저장된 허가를 불러왔습니다. 총괄 AI 현황 조회만 실제 읽기 전용으로 구현됐습니다.")

    def save_access_settings(self) -> None:
        try:
            employee_id = self._selected_access_employee()
            caps = [k for k, v in self.access_cap_vars.items() if v.get()]
            tools = [k for k, v in self.access_tool_vars.items() if v.get()]
            self.store.save_employee_access(employee_id, caps, tools)
            self.access_feedback.set("권한·도구 설정 저장 완료. 총괄 AI 현황 조회는 수동 버튼에서만 작동합니다.")
        except (ValueError, PermissionError) as exc:
            self.access_feedback.set("저장 실패: " + str(exc))

    def revoke_access_settings(self) -> None:
        try:
            employee_id = self._selected_access_employee()
            if not messagebox.askyesno("허가 취소", "선택 직원의 모든 권한과 도구 허가를 취소할까요?", parent=self.root):
                return
            self.store.save_employee_access(employee_id, [], [])
            self.load_employee_access()
            self.access_feedback.set("모든 권한·도구 허가를 취소했습니다.")
        except (ValueError, PermissionError) as exc:
            self.access_feedback.set("허가 취소 실패: " + str(exc))

    def _local_models(self, parent: tk.Frame) -> None:
        """Local subprocess model registry; no cloud API or background startup."""
        self.store.require_permission("agents:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "오프라인 AI 모델 연결", size=17, weight="bold").pack(anchor="w")
        self._label(panel, "모델 등록·경로 검사는 추론을 실행하지 않습니다. 시험 버튼을 눌렀을 때만 선택한 PC 실행파일을 구동합니다.",
                    fg="#f7cb92", wraplength=820).pack(anchor="w", pady=(3, 9))
        upper = tk.Frame(panel, bg="#1c2a40")
        upper.pack(fill="x")
        self.model_name = tk.StringVar(value="")
        self.model_backend = tk.StringVar(value="llama_cpp")
        self.model_executable = tk.StringVar(value="")
        self.model_file = tk.StringVar(value="")
        self.model_tokens = tk.StringVar(value="128")
        for row, (title, variable) in enumerate((("모델 이름", self.model_name),
                                                  ("로컬 실행파일", self.model_executable),
                                                  ("GGUF 모델 파일", self.model_file))):
            self._label(upper, title).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            tk.Entry(upper, textvariable=variable, width=60, font=("Malgun Gothic", 10)).grid(row=row, column=1, sticky="ew", pady=4)
            if row in (1, 2):
                tk.Button(upper, text="파일 선택", command=lambda target=variable: self._choose_local_file(target),
                          bg="#304561", fg="white").grid(row=row, column=2, padx=(7, 0))
        self._label(upper, "실행 방식").grid(row=3, column=0, sticky="w", pady=4)
        self.model_backend_combo = ttk.Combobox(upper, textvariable=self.model_backend,
                                                values=list(BACKENDS), state="readonly", width=20)
        self.model_backend_combo.grid(row=3, column=1, sticky="w", pady=4)
        self._label(upper, "최대 토큰").grid(row=3, column=2, sticky="w", padx=(12, 0))
        tk.Entry(upper, textvariable=self.model_tokens, width=5).grid(row=3, column=3, sticky="w")
        upper.columnconfigure(1, weight=1)
        self._label(panel, "llama_cpp: llama-cli와 .gguf 모두 필수 / llamafile: 모델을 내장한 실행파일 가능. 모든 경로는 PC 내부 파일이어야 합니다.",
                    size=9, fg="#bfcfe5", wraplength=820).pack(anchor="w", pady=(4, 9))
        self.model_tree = ttk.Treeview(panel, columns=("id", "name", "backend"), show="headings", height=4)
        for col, label, width in (("id", "ID", 50), ("name", "모델 이름", 250), ("backend", "실행 방식", 130)):
            self.model_tree.heading(col, text=label)
            self.model_tree.column(col, width=width, stretch=col=="name")
        self.model_tree.pack(fill="x", pady=(0, 7))
        self.model_tree.bind("<<TreeviewSelect>>", self._on_model_selection)
        actions = tk.Frame(panel, bg="#1c2a40")
        actions.pack(anchor="w", pady=2)
        for title, name, action in (("모델 등록", "model_add_button", self.add_model),
                                    ("모델 수정", "model_update_button", self.update_model),
                                    ("모델 삭제", "model_delete_button", self.delete_model),
                                    ("경로 검사", "model_verify_button", self.verify_model)):
            button = tk.Button(actions, text=title, command=action, bg="#426cba", fg="white", padx=10, pady=5)
            button.pack(side="left", padx=(0, 7))
            setattr(self, name, button)
        self.model_prompt = tk.StringVar(value="안녕하세요. 자기소개를 한 문장으로 해 주세요.")
        prompt_row = tk.Frame(panel, bg="#1c2a40")
        prompt_row.pack(fill="x", pady=(7, 3))
        self._label(prompt_row, "시험 질문").pack(side="left", padx=(0, 9))
        tk.Entry(prompt_row, textvariable=self.model_prompt, font=("Malgun Gothic", 10)).pack(side="left", fill="x", expand=True)
        self.model_run_button = tk.Button(panel, text="선택 모델 추론 시험 (사용자가 직접 실행)", command=self.test_local_model,
                                          bg="#426cba", fg="white", padx=12, pady=7)
        self.model_run_button.pack(anchor="w", pady=5)
        self.model_cancel_button = tk.Button(panel, text="실행 중단", command=self.cancel_local_model,
                                            bg="#304561", fg="white", padx=12, pady=5)
        self.model_cancel_button.pack(anchor="w", pady=2)
        self.model_feedback = tk.StringVar(value="모델 실행파일은 별도 설치가 필요할 수 있습니다. 등록 자체는 어떤 프로그램도 시작하지 않습니다.")
        self._label(panel, "", textvariable=self.model_feedback, fg="#9cdbbb", wraplength=810).pack(anchor="w")
        self.model_result = tk.Text(panel, height=4, bg="#f8fbff", fg="#202b40", wrap="word")
        self.model_result.pack(fill="both", expand=True, pady=(4, 0))
        self._model_queue = queue.Queue()
        self._model_running = False
        self.reload_models()

    def _choose_local_file(self, variable: tk.StringVar) -> None:
        self.store.require_permission("agents:manage")
        path = filedialog.askopenfilename(parent=self.root, title="PC 내부 파일 선택")
        if path:
            variable.set(path)

    def _model_config(self) -> ModelConfig:
        self.store.require_permission("agents:manage")
        try:
            tokens = int(self.model_tokens.get())
        except ValueError as exc:
            raise ValueError("토큰 수는 숫자여야 합니다.") from exc
        return ModelConfig(self.model_name.get(), self.model_backend.get(), self.model_executable.get(),
                           self.model_file.get(), tokens)

    def _selected_model_id(self) -> int:
        self.store.require_permission("agents:manage")
        selection = self.model_tree.selection()
        if len(selection) != 1:
            raise ValueError("등록된 모델을 한 개 선택하세요.")
        return int(selection[0])

    def reload_models(self, selected_id: int | None = None) -> None:
        self.store.require_permission("agents:manage")
        for iid in self.model_tree.get_children():
            self.model_tree.delete(iid)
        for item in self.store.list_local_models():
            self.model_tree.insert("", "end", iid=str(item["id"]), values=(item["id"], item["name"], item["backend"]))
        if selected_id is not None and self.model_tree.exists(str(selected_id)):
            self.model_tree.selection_set(str(selected_id))

    def _on_model_selection(self, event=None) -> None:
        self.store.require_permission("agents:manage")
        try:
            model_id = self._selected_model_id()
        except ValueError:
            return
        row = self.store.read_local_model(model_id)
        self.model_name.set(str(row["name"]))
        self.model_backend.set(str(row["backend"]))
        self.model_executable.set(str(row["executable_path"]))
        self.model_file.set(str(row["model_path"]))
        self.model_tokens.set(str(row["max_tokens"]))

    def add_model(self) -> None:
        try:
            model_id = self.store.add_local_model(self._model_config())
            self.reload_models(model_id)
            self.model_feedback.set("모델 설정을 로컬에 등록했습니다. 실행하지 않았습니다.")
        except (ValueError, PermissionError, OSError) as exc:
            self.model_feedback.set("모델 등록 실패: " + str(exc))

    def update_model(self) -> None:
        try:
            model_id = self._selected_model_id()
            self.store.update_local_model(model_id, self._model_config())
            self.reload_models(model_id)
            self.model_feedback.set("모델 연결 설정을 수정했습니다. 실행하지 않았습니다.")
        except (ValueError, PermissionError, OSError) as exc:
            self.model_feedback.set("모델 수정 실패: " + str(exc))

    def delete_model(self) -> None:
        try:
            model_id = self._selected_model_id()
            if not messagebox.askyesno("모델 등록 삭제", "로컬 모델 등록 정보만 삭제할까요? 실제 GGUF 파일은 삭제하지 않습니다.", parent=self.root):
                return
            self.store.delete_local_model(model_id)
            self.reload_models()
            self.model_feedback.set("모델 연결 설정을 삭제했습니다. 실제 모델 파일은 그대로 남습니다.")
        except (ValueError, PermissionError) as exc:
            self.model_feedback.set("모델 삭제 실패: " + str(exc))

    def verify_model(self) -> None:
        try:
            validate_config(self._model_config())
            self.model_feedback.set("경로·GGUF 머리글 검사 통과. 실제 추론 가능 여부는 별도 실행 시험이 필요합니다.")
        except (ValueError, PermissionError, OSError) as exc:
            self.model_feedback.set("경로 검사 실패: " + str(exc))

    def test_local_model(self) -> None:
        """Do not run on startup: this callback is ONLY from the explicit button."""
        try:
            model_id = self._selected_model_id()
            entry = self.store.read_local_model(model_id)
            config = ModelConfig(str(entry["name"]), str(entry["backend"]),
                                 str(entry["executable_path"]), str(entry["model_path"]), int(entry["max_tokens"]))
            validate_config(config)
            prompt = self.model_prompt.get()
            if not prompt.strip() or len(prompt) > 3000:
                raise ValueError("시험 질문은 1~3000자여야 합니다.")
            if self._model_running:
                raise ValueError("이미 모델 실행 시험이 진행 중입니다.")
        except (ValueError, PermissionError, OSError) as exc:
            self.model_feedback.set("시험 시작 실패: " + str(exc))
            return
        self._model_running = True
        generation = self._session_generation
        outbound = self._model_queue
        cancel = threading.Event()
        self._model_cancel = cancel
        self.model_run_button.configure(state="disabled")
        self.employee_model_run_button.configure(state="disabled")
        self.chief_run_button.configure(state="disabled")
        self.model_feedback.set("지정한 로컬 실행파일을 실행 중입니다 (최대 60초). 앱에서 클라우드 API를 호출하지 않습니다.")
        self.model_result.delete("1.0", "end")

        def task() -> None:
            try:
                outbound.put((generation, True, run_local_model(config, prompt, timeout=60, cancel=cancel)))
            except (ValueError, TimeoutError, InterruptedError, RuntimeError, OSError) as exc:
                outbound.put((generation, False, str(exc)))

        self._model_thread = threading.Thread(target=task, daemon=True)
        self._model_thread.start()
        self.root.after(100, lambda: self._poll_model_result(generation, outbound))

    def cancel_local_model(self, *, wait: bool = False) -> None:
        """Stop local inference; wait briefly on logout or window closure."""
        if self._model_cancel is not None:
            self._model_cancel.set()
        if (wait and self._model_thread is not None
                and self._model_thread is not threading.current_thread()):
            self._model_thread.join(timeout=3)
        # Task workers have their own cancellation tokens; never lose track of
        # one of the parallel local subprocesses on logout/window closure.
        live = list(getattr(self, '_task_runs_live', {}).values())
        for token, _ in live:
            token.set()
        if wait:
            for _, worker in live:
                if worker is not threading.current_thread():
                    worker.join(timeout=3)

    def _poll_model_result(self, generation: int, outbound: queue.Queue) -> None:
        if generation != self._session_generation or not self.store.is_authenticated:
            return
        try:
            generation, success, message = outbound.get_nowait()
        except queue.Empty:
            if self._model_running and self.root.winfo_exists():
                self.root.after(100, lambda: self._poll_model_result(generation, outbound))
            return
        self._model_running = False
        self._model_cancel = None
        self._model_thread = None
        if self.root.winfo_exists() and self.store.is_authenticated and generation == self._session_generation:
            self.model_run_button.configure(state="normal")
            self.employee_model_run_button.configure(state="normal")
            self.chief_run_button.configure(state="normal")
            self.model_feedback.set("로컬 실행파일 응답 완료" if success else "로컬 실행 실패: " + message)
            if success:
                self.model_result.insert("1.0", message or "(출력 없음)")

    # Stage 19: owner-managed employee-specific model mapping and invocation history.
    def _employee_models(self, parent: tk.Frame) -> None:
        self.store.require_permission("agents:manage")
        panel=self._panel(parent)
        panel.pack(fill="both",expand=True)
        self._label(panel,"AI 직원별 로컬 모델·호출 이력",size=17,weight="bold").pack(anchor="w")
        self._label(panel,"직원에 모델을 배정해도 자동 실행되지 않습니다. 버튼으로 실행할 때만 PC의 로컬 모델을 호출합니다.",
                    fg="#f7cb92",wraplength=820,size=9).pack(anchor="w",pady=(4,7))
        line=tk.Frame(panel,bg="#1c2a40")
        line.pack(fill="x",pady=2)
        self.employee_model_employee=tk.StringVar(value="")
        self.employee_model_model=tk.StringVar(value="")
        self._label(line,"직원").pack(side="left",padx=(0,6))
        self.employee_model_employee_combo=ttk.Combobox(line,textvariable=self.employee_model_employee,
                                                         state="readonly",width=37)
        self.employee_model_employee_combo.pack(side="left",padx=(0,12))
        self.employee_model_employee_combo.bind("<<ComboboxSelected>>",self.load_employee_model)
        self._label(line,"모델").pack(side="left",padx=(0,6))
        self.employee_model_model_combo=ttk.Combobox(line,textvariable=self.employee_model_model,
                                                      state="readonly",width=32)
        self.employee_model_model_combo.pack(side="left")
        actions=tk.Frame(panel,bg="#1c2a40")
        actions.pack(anchor="w",pady=5)
        self.employee_model_save_button=tk.Button(actions,text="직원 모델 배정",command=self.save_employee_model,
                                                   bg="#426cba",fg="white",padx=13,pady=5)
        self.employee_model_save_button.pack(side="left",padx=(0,9))
        self.employee_model_clear_button=tk.Button(actions,text="배정 해제",command=self.clear_employee_model,
                                                    bg="#304561",fg="white",padx=13,pady=5)
        self.employee_model_clear_button.pack(side="left")
        self.employee_model_prompt=tk.StringVar(value="안녕하세요. 한 문장으로 소개해 주세요.")
        prompt_row=tk.Frame(panel,bg="#1c2a40")
        prompt_row.pack(fill="x",pady=(5,6))
        self._label(prompt_row,"질문 (저장하지 않음)").pack(side="left",padx=(0,10))
        tk.Entry(prompt_row,textvariable=self.employee_model_prompt,width=69).pack(side="left",fill="x",expand=True)
        buttons=tk.Frame(panel,bg="#1c2a40")
        buttons.pack(anchor="w",pady=(0,7))
        self.employee_model_run_button=tk.Button(buttons,text="선택 직원 모델 수동 실행",command=self.test_employee_model,
                                                  bg="#426cba",fg="white",padx=12,pady=5)
        self.employee_model_run_button.pack(side="left",padx=(0,9))
        self.employee_model_cancel_button=tk.Button(buttons,text="실행 중단",command=self.cancel_local_model,
                                                     bg="#304561",fg="white",padx=12,pady=5)
        self.employee_model_cancel_button.pack(side="left",padx=(0,9))
        tk.Button(buttons,text="이력 새로고침",command=self.reload_employee_model_history,
                  bg="#304561",fg="white",padx=12,pady=5).pack(side="left")
        self.employee_model_feedback=tk.StringVar(value="모든 호출은 관리자 수동 시험만 가능합니다. 질문/응답 본문은 기록하지 않습니다.")
        self._label(panel,"",textvariable=self.employee_model_feedback,fg="#9cdbbb",wraplength=820,size=9).pack(anchor="w")
        self.employee_model_result=tk.Text(panel,height=3,bg="#f8fbff",fg="#202b40",wrap="word")
        self.employee_model_result.pack(fill="x",pady=(3,7))
        columns=("id","employee","model","status","started","duration")
        self.employee_model_history=ttk.Treeview(panel,columns=columns,show="headings",height=5)
        for key,label,width in (("id","호출번호",75),("employee","직원 ID",75),("model","모델",200),
                                ("status","결과",95),("started","시작 시각",150),("duration","소요 ms",95)):
            self.employee_model_history.heading(key,text=label)
            self.employee_model_history.column(key,width=width,stretch=(key=="model"))
        self.employee_model_history.pack(fill="both",expand=True)
        self._employee_model_queue=queue.Queue()
        self.refresh_employee_model_choices()

    def _selected_employee_model_employee(self) -> int:
        self.store.require_permission("agents:manage")
        value=self.employee_model_employee.get()
        if value not in self.employee_model_employee_combo["values"]:
            raise ValueError("목록에서 직원을 선택하세요.")
        return int(value.split(" · ",1)[0])

    def refresh_employee_model_choices(self) -> None:
        self.store.require_permission("agents:manage")
        previous_employee=self.employee_model_employee.get()
        employees=self.store.list_employee_records()
        options=[f"{r['id']} · {r['display_name']} [{r['lifecycle']}]" for r in employees]
        self.employee_model_employee_combo["values"]=options
        self.employee_model_employee.set(previous_employee if previous_employee in options else "")
        previous_model=self.employee_model_model.get()
        models=self.store.list_local_models()
        model_options=[f"{r['id']} · {r['name']}" for r in models]
        self.employee_model_model_combo["values"]=model_options
        self.employee_model_model.set(previous_model if previous_model in model_options else "")
        self.load_employee_model()

    def load_employee_model(self, event=None) -> None:
        self.store.require_permission("agents:manage")
        if not self.employee_model_employee.get():
            self.employee_model_model.set("")
        else:
            assignment=self.store.read_employee_model(self._selected_employee_model_employee())
            if assignment:
                choice=next((text for text in self.employee_model_model_combo["values"]
                             if text.startswith(str(assignment["model_id"])+" · ")),"")
                self.employee_model_model.set(choice)
            else:
                self.employee_model_model.set("")
        self.reload_employee_model_history()

    def save_employee_model(self) -> None:
        try:
            employee_id=self._selected_employee_model_employee()
            text=self.employee_model_model.get()
            if text not in self.employee_model_model_combo["values"]:
                raise ValueError("등록된 모델을 선택하세요.")
            self.store.set_employee_model(employee_id,int(text.split(" · ",1)[0]))
            self.employee_model_feedback.set("로컬 모델 배정 완료. 모델은 실행하지 않았습니다.")
            self.reload_employee_model_history()
        except (ValueError,PermissionError) as exc:
            self.employee_model_feedback.set("배정 실패: "+str(exc))

    def clear_employee_model(self) -> None:
        try:
            employee_id=self._selected_employee_model_employee()
            self.store.set_employee_model(employee_id,None)
            self.employee_model_model.set("")
            self.employee_model_feedback.set("모델 배정을 해제했습니다. 기존 호출 기록은 보존됩니다.")
            self.reload_employee_model_history()
        except (ValueError,PermissionError) as exc:
            self.employee_model_feedback.set("배정 해제 실패: "+str(exc))

    def reload_employee_model_history(self) -> None:
        self.store.require_permission("agents:manage")
        for row in self.employee_model_history.get_children():
            self.employee_model_history.delete(row)
        try:
            employee_id=self._selected_employee_model_employee()
        except ValueError:
            return
        for row in self.store.list_employee_model_calls(employee_id):
            self.employee_model_history.insert("","end",iid=str(row["id"]),values=(
                row["id"],row["employee_id"],row["model_name"],row["status"],
                row["started_at"],row["duration_ms"]))

    def test_employee_model(self) -> None:
        """Only this explicit native Tk button starts an assigned local model."""
        try:
            employee_id=self._selected_employee_model_employee()
            prompt=self.employee_model_prompt.get()
            if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>3000:
                raise ValueError("질문은 1~3000자여야 합니다.")
            if not self.store.read_employee_model(employee_id):
                raise ValueError("선택한 직원에게 로컬 모델을 먼저 배정하세요.")
            if self._model_running:
                raise ValueError("이미 모델이 실행 중입니다.")
        except (ValueError,PermissionError) as exc:
            self.employee_model_feedback.set("실행 시작 실패: "+str(exc))
            return
        self._model_running=True
        generation=self._session_generation
        cancel=threading.Event()
        self._model_cancel=cancel
        self.model_run_button.configure(state="disabled")
        self.employee_model_run_button.configure(state="disabled")
        self.chief_run_button.configure(state="disabled")
        self.employee_model_feedback.set("배정된 PC 로컬 모델 수동 실행 중 (최대 60초) · 질문/응답 본문은 저장하지 않음")
        self.employee_model_result.delete("1.0","end")

        def task() -> None:
            try:
                self._employee_model_queue.put((generation,True,
                    invoke_employee_model(self.store,employee_id,prompt,timeout=60,cancel=cancel)))
            except (ValueError,PermissionError,TimeoutError,InterruptedError,RuntimeError,OSError) as exc:
                self._employee_model_queue.put((generation,False,str(exc)))

        self._model_thread=threading.Thread(target=task,daemon=True)
        self._model_thread.start()
        self.root.after(100,lambda:self._poll_employee_model_result(generation))

    def _poll_employee_model_result(self,generation:int) -> None:
        if generation!=self._session_generation or not self.store.is_authenticated:
            return
        try:
            item_generation,success,message=self._employee_model_queue.get_nowait()
        except queue.Empty:
            if self._model_running and self.root.winfo_exists():
                self.root.after(100,lambda:self._poll_employee_model_result(generation))
            return
        self._model_running=False
        self._model_cancel=None
        self._model_thread=None
        self.model_run_button.configure(state="normal")
        self.employee_model_run_button.configure(state="normal")
        self.chief_run_button.configure(state="normal")
        self.employee_model_feedback.set("직원 로컬 모델 시험 완료 · 호출 이력 저장" if success else "실행 실패 (호출 이력 확인): "+message)
        if success:
            self.employee_model_result.insert("1.0",message or "(출력 없음)")
        self.reload_employee_model_history()

    # Stage 20: owner-only, explicit one-turn conversation with the assigned local CEO.
    def _chief_chat(self, parent: tk.Frame) -> None:
        self.store.require_permission("agents:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "총괄 AI · 로컬 모델 대화", size=17, weight="bold").pack(anchor="w")
        self._label(panel, "총괄 AI를 조직 지휘 체계에 지정하고 로컬 모델을 배정하세요. 발송 버튼을 누를 때만 실행합니다.",
                    size=9, fg="#f7cb92", wraplength=800).pack(anchor="w", pady=(5, 9))
        self.chief_state = tk.StringVar(value="")
        self._label(panel, "", textvariable=self.chief_state, fg="#93dcb5", wraplength=800).pack(anchor="w", pady=(0, 8))
        self.chief_transcript = tk.Text(panel, height=14, wrap="word", bg="#f8fbff", fg="#17213b", state="disabled")
        self.chief_transcript.pack(fill="both", expand=True, pady=(0, 9))
        self._label(panel, "질문 입력 (최대 3000자 · 이 화면에서만 보관)", size=9).pack(anchor="w")
        self.chief_input = tk.Text(panel, height=3, wrap="word", bg="#f8fbff", fg="#17213b")
        self.chief_input.pack(fill="x", pady=(4, 7))
        bar = tk.Frame(panel, bg="#1c2a40")
        bar.pack(anchor="w")
        self.chief_run_button = tk.Button(bar, text="총괄 AI에게 보내기", command=self.send_chief_message,
                                          bg="#426cba", fg="white", padx=13, pady=6)
        self.chief_run_button.pack(side="left", padx=(0, 8))
        self.chief_status_button = tk.Button(bar, text="회사 현황 조회", command=self.show_chief_company_status,
                                             bg="#3659ab", fg="white", padx=12, pady=6)
        self.chief_status_button.pack(side="left", padx=(0, 8))
        self.chief_cancel_button = tk.Button(bar, text="응답 중단", command=self.cancel_local_model,
                                             bg="#304561", fg="white", padx=13, pady=6)
        self.chief_cancel_button.pack(side="left", padx=(0, 8))
        self.chief_include_status = tk.BooleanVar(value=False)
        tk.Checkbutton(panel, text="대화 질문에 회사 현황 포함 (명시적 동의 · 직원 조회 권한 필요)",
                       variable=self.chief_include_status, bg="#1c2a40", fg="#eaf0ff",
                       selectcolor="#304561", activebackground="#1c2a40").pack(anchor="w", pady=(5, 0))
        tk.Button(bar, text="대화 화면 지우기", command=self.clear_chief_conversation,
                  bg="#304561", fg="white", padx=13, pady=6).pack(side="left", padx=(0, 8))
        tk.Button(bar, text="모델 상태 새로고침", command=self.refresh_chief_state,
                  bg="#304561", fg="white", padx=13, pady=6).pack(side="left")
        self.chief_feedback = tk.StringVar(value="질문·답변 원문은 데이터베이스에 저장하지 않습니다. 재로그인하면 화면 대화도 초기화됩니다.")
        self._label(panel, "", textvariable=self.chief_feedback, size=9, fg="#93dcb5", wraplength=800).pack(anchor="w", pady=(8, 0))
        self._chief_queue = queue.Queue()
        self.refresh_chief_state()

    def show_chief_company_status(self) -> None:
        """On-demand data read; never start a model or send a network request."""
        try:
            if self._model_running:
                raise ValueError("모델 실행이 끝나면 다시 조회하세요.")
            status = read_chief_status_text(self.store)
        except (ValueError, PermissionError) as exc:
            self.chief_feedback.set("회사 현황 조회 실패: " + str(exc))
            return
        self._append_chief("현재 로컬 회사 현황 (모델 호출 없음)", status)
        self.chief_feedback.set("로컬 SQLite 현황을 읽었습니다. 목표는 별도 권한이 있을 때만 표시됩니다.")

    def refresh_chief_state(self) -> None:
        self.store.require_permission("agents:manage")
        chief = self.store.read_chief_profile()
        if chief is None:
            self.chief_state.set("총괄 AI 미지정 · 조직 지휘 체계에서 지정하세요.")
        elif chief["lifecycle"] != "draft":
            self.chief_state.set("총괄 AI가 비활성 상태입니다.")
        elif chief["model_id"] is None:
            self.chief_state.set(f"총괄 AI: {chief['display_name']} · 로컬 모델 미배정")
        else:
            self.chief_state.set(f"총괄 AI: {chief['display_name']} · 로컬 모델: {chief['model_name']}")

    def _append_chief(self, label: str, text: str) -> None:
        self.chief_transcript.configure(state="normal")
        self.chief_transcript.insert("end", f"{label}\n{text}\n\n")
        self.chief_transcript.see("end")
        self.chief_transcript.configure(state="disabled")

    def clear_chief_conversation(self) -> None:
        self.store.require_permission("agents:manage")
        if self._model_running:
            self.chief_feedback.set("모델 응답이 완료되거나 중단된 뒤 화면을 지울 수 있습니다.")
            return
        self.chief_transcript.configure(state="normal")
        self.chief_transcript.delete("1.0", "end")
        self.chief_transcript.configure(state="disabled")
        self.chief_feedback.set("대화 화면을 지웠습니다. 대화 본문은 디스크에 저장되지 않습니다.")

    def send_chief_message(self) -> None:
        try:
            self.store.require_permission("agents:manage")
            if self._model_running:
                raise ValueError("다른 로컬 모델이 실행 중입니다.")
            prompt = self.chief_input.get("1.0", "end-1c").strip()
            if not (1 <= len(prompt) <= 3000):
                raise ValueError("질문은 1~3000자여야 합니다.")
            if self.chief_include_status.get():
                from desktop.company_status import chief_query_with_status
                chief_query_with_status(self.store, prompt)  # deny before editing the chat UI
            chief = self.store.read_chief_profile()
            if chief is None or chief["lifecycle"] != "draft" or chief["model_id"] is None:
                raise ValueError("활성 총괄 AI와 로컬 모델 배정이 필요합니다.")
        except (ValueError, PermissionError) as exc:
            self.chief_feedback.set("발송 실패: " + str(exc))
            return
        self._append_chief("사용자", prompt)
        self.chief_input.delete("1.0", "end")
        self._model_running = True
        cancel = threading.Event()
        self._model_cancel = cancel
        generation = self._session_generation
        outbound = self._chief_queue
        self.chief_run_button.configure(state="disabled")
        self.model_run_button.configure(state="disabled")
        self.employee_model_run_button.configure(state="disabled")
        include_status = self.chief_include_status.get()
        self.chief_feedback.set("PC 로컬 모델 응답 중 (최대 60초). 인터넷 연결 및 자동 실행 없음.")

        def task() -> None:
            try:
                response = invoke_chief_model(self.store, prompt, timeout=60, cancel=cancel,
                                              include_company_status=include_status)
                outbound.put((generation, True, response))
            except (ValueError, PermissionError, RuntimeError, OSError, TimeoutError, InterruptedError) as exc:
                outbound.put((generation, False, str(exc)))

        self._model_thread = threading.Thread(target=task, daemon=True)
        self._model_thread.start()
        self.root.after(100, lambda: self._poll_chief_result(generation, outbound))

    def _poll_chief_result(self, generation: int, outbound: queue.Queue) -> None:
        if generation != self._session_generation or not self.store.is_authenticated:
            return
        try:
            item_generation, success, response = outbound.get_nowait()
        except queue.Empty:
            if self._model_running and self.root.winfo_exists():
                self.root.after(100, lambda: self._poll_chief_result(generation, outbound))
            return
        if item_generation != generation:
            return
        self._model_running = False
        self._model_cancel = None
        self._model_thread = None
        self.chief_run_button.configure(state="normal")
        self.model_run_button.configure(state="normal")
        self.employee_model_run_button.configure(state="normal")
        if success:
            self._append_chief("총괄 AI · 로컬 모델 응답", response or "(모델이 빈 답변을 반환했습니다)")
            self.chief_feedback.set("응답 완료 · 호출 메타데이터만 로컬에 저장됨")
        else:
            # No private prompt/output in persistent storage; UI-only error.
            self._append_chief("실행 오류", response)
            self.chief_feedback.set("응답 실패 또는 취소 · 모델 실행 이력 확인")

    def _work_plans(self, parent: tk.Frame) -> None:
        """Owner-only plan editor. Stored steps are NOT executable tasks."""
        self.store.require_permission("company:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "회사 목표별 업무 계획", size=18, weight="bold").pack(anchor="w")
        self._label(panel, "계획·실행 순서만 저장합니다. AI 업무 실행이나 지출은 시작하지 않습니다.",
                    fg="#bfcfe5").pack(anchor="w", pady=(4, 12))
        self.work_plan_goal = tk.StringVar(value="")
        self.work_plan_title = tk.StringVar(value="")
        self.work_plan_description = tk.StringVar(value="")
        self.work_plan_status = tk.StringVar(value="draft")
        self.work_plan_feedback = tk.StringVar(value="목표를 선택하고 순서를 줄마다 하나씩 작성하세요.")
        form = tk.Frame(panel, bg="#1c2a40")
        form.pack(fill="x")
        self._label(form, "연결 목표").grid(row=0, column=0, padx=(0, 12), pady=4, sticky="w")
        self.work_plan_goal_combo = ttk.Combobox(form, textvariable=self.work_plan_goal,
                                                  state="readonly", width=52)
        self.work_plan_goal_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self._label(form, "계획 제목").grid(row=1, column=0, sticky="w", pady=4)
        tk.Entry(form, textvariable=self.work_plan_title, width=62).grid(row=1, column=1, sticky="ew", pady=4, ipady=4)
        self._label(form, "계획 설명").grid(row=2, column=0, sticky="w", pady=4)
        tk.Entry(form, textvariable=self.work_plan_description, width=62).grid(row=2, column=1, sticky="ew", pady=4, ipady=4)
        self._label(form, "계획 상태").grid(row=3, column=0, sticky="w", pady=4)
        self.work_plan_status_combo = ttk.Combobox(form, textvariable=self.work_plan_status,
                                                   values=("draft", "ready", "archived"), width=14, state="readonly")
        self.work_plan_status_combo.grid(row=3, column=1, sticky="w", pady=4)
        form.columnconfigure(1, weight=1)
        self._label(panel, "실행 순서 (한 줄에 하나, 최대 30줄 · 각 200자)").pack(anchor="w", pady=(12, 5))
        self.work_plan_steps = tk.Text(panel, height=5, width=72, wrap="word", font=("Malgun Gothic", 10))
        self.work_plan_steps.pack(fill="x")
        bar = tk.Frame(panel, bg="#1c2a40")
        bar.pack(fill="x", pady=(11, 9))
        self.work_plan_add_button = tk.Button(bar, text="계획 저장", command=self.add_work_plan,
                                             bg="#4c83e6", fg="white", padx=12)
        self.work_plan_add_button.pack(side="left", padx=(0, 7))
        self.work_plan_update_button = tk.Button(bar, text="선택 계획 수정", command=self.update_work_plan)
        self.work_plan_update_button.pack(side="left", padx=(0, 7))
        self.work_plan_delete_button = tk.Button(bar, text="선택 계획 삭제", command=self.delete_work_plan)
        self.work_plan_delete_button.pack(side="left", padx=(0, 7))
        tk.Button(bar, text="새 계획 입력", command=self.clear_work_plan).pack(side="left")
        table = tk.Frame(panel)
        table.pack(fill="both", expand=True)
        self.work_plan_tree = ttk.Treeview(table, columns=("id", "goal", "title", "status", "count"),
                                           show="headings", height=5)
        for key, title, width in (("id", "번호", 53), ("goal", "연결 목표", 190),
                                  ("title", "계획명", 240), ("status", "상태", 72), ("count", "순서", 60)):
            self.work_plan_tree.heading(key, text=title)
            self.work_plan_tree.column(key, width=width, stretch=key not in {"id", "status", "count"})
        self.work_plan_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.work_plan_tree.yview)
        scroll.pack(side="right", fill="y")
        self.work_plan_tree.configure(yscrollcommand=scroll.set)
        self.work_plan_tree.bind("<<TreeviewSelect>>", self._load_work_plan_selection)
        self._label(panel, "", textvariable=self.work_plan_feedback, fg="#9cdbbb", wraplength=850).pack(anchor="w", pady=(7, 0))
        self.refresh_work_plan_goals()
        self.reload_work_plans()

    def refresh_work_plan_goals(self) -> None:
        self.store.require_permission("company:manage")
        goals = self.store.list_goals()
        current = self.work_plan_goal.get()
        self.work_plan_goal_map = {f"{g['id']} · {g['title']}": int(g["id"]) for g in goals}
        options = list(self.work_plan_goal_map)
        self.work_plan_goal_combo["values"] = options
        self.work_plan_goal.set(current if current in options else (options[0] if options else ""))

    def _work_plan_values(self) -> tuple[int, str, str, list[str], str]:
        self.store.require_permission("company:manage")
        goal_id = self.work_plan_goal_map.get(self.work_plan_goal.get())
        if goal_id is None:
            raise ValueError("회사·목표 관리에서 목표를 먼저 등록하고 선택하세요.")
        lines = self.work_plan_steps.get("1.0", "end-1c").splitlines()
        # Blank lines are not steps; prevent accidentally saving empty plan.
        steps = [line.strip() for line in lines if line.strip()]
        return goal_id, self.work_plan_title.get(), self.work_plan_description.get(), steps, self.work_plan_status.get()

    def reload_work_plans(self, selected_id: int | None = None) -> None:
        self.store.require_permission("company:manage")
        for row in self.work_plan_tree.get_children():
            self.work_plan_tree.delete(row)
        for plan in self.store.list_work_plans():
            self.work_plan_tree.insert("", "end", iid=str(plan["id"]),
                                       values=(plan["id"], plan["goal_title"], plan["title"],
                                               plan["status"], plan["steps_count"]))
        if selected_id is not None and self.work_plan_tree.exists(str(selected_id)):
            self.work_plan_tree.selection_set(str(selected_id))

    def _selected_work_plan_id(self) -> int:
        self.store.require_permission("company:manage")
        selected = self.work_plan_tree.selection()
        if not selected:
            raise ValueError("수정·삭제할 업무 계획을 목록에서 먼저 선택하세요.")
        return int(selected[0])

    def _load_work_plan_selection(self, event=None) -> None:
        self.store.require_permission("company:manage")
        selected = self.work_plan_tree.selection()
        if not selected:
            return
        plan = self.store.read_work_plan(int(selected[0]))
        self.refresh_work_plan_goals()
        for text, goal_id in self.work_plan_goal_map.items():
            if goal_id == plan["goal_id"]:
                self.work_plan_goal.set(text)
                break
        self.work_plan_title.set(str(plan["title"]))
        self.work_plan_description.set(str(plan["description"]))
        self.work_plan_status.set(str(plan["status"]))
        self.work_plan_steps.delete("1.0", "end")
        self.work_plan_steps.insert("1.0", "\n".join(plan["steps"]))

    def clear_work_plan(self) -> None:
        self.store.require_permission("company:manage")
        self.work_plan_tree.selection_remove(*self.work_plan_tree.selection())
        self.work_plan_title.set("")
        self.work_plan_description.set("")
        self.work_plan_status.set("draft")
        self.work_plan_steps.delete("1.0", "end")
        self.work_plan_feedback.set("새 업무 계획을 입력할 수 있습니다.")

    def add_work_plan(self) -> None:
        try:
            goal_id, title, description, steps, status = self._work_plan_values()
            plan_id = self.store.add_work_plan(goal_id, title, description, steps, status)
            self.reload_work_plans(plan_id)
            self.work_plan_feedback.set("업무 계획과 순서를 로컬 DB에 저장했습니다.")
        except (ValueError, PermissionError) as exc:
            self.work_plan_feedback.set(f"저장 실패: {exc}")

    def update_work_plan(self) -> None:
        try:
            plan_id = self._selected_work_plan_id()
            goal_id, title, description, steps, status = self._work_plan_values()
            self.store.update_work_plan(plan_id, goal_id, title, description, steps, status)
            self.reload_work_plans(plan_id)
            self.work_plan_feedback.set("선택한 업무 계획을 수정했습니다.")
        except (ValueError, PermissionError) as exc:
            self.work_plan_feedback.set(f"수정 실패: {exc}")

    def delete_work_plan(self) -> None:
        try:
            plan_id = self._selected_work_plan_id()
            if not messagebox.askyesno("업무 계획 삭제", "선택한 계획과 실행 순서를 삭제할까요?", parent=self.root):
                return
            self.store.delete_work_plan(plan_id)
            self.clear_work_plan()
            self.reload_work_plans()
            self.work_plan_feedback.set("선택한 업무 계획이 삭제됐습니다.")
        except (ValueError, PermissionError) as exc:
            self.work_plan_feedback.set(f"삭제 실패: {exc}")

    # Stage 23 — manual task CRUD and lifecycle in an owner-only native window.
    def _tasks(self, parent: tk.Frame) -> None:
        self.store.require_permission("company:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "업무 생성 및 상태 관리", size=18, weight="bold").pack(anchor="w")
        self._label(panel, "업무는 로컬 DB의 수동 기록입니다. 등록·상태 변경으로 AI가 실행되지 않습니다.",
                    fg="#f7cb92", size=9).pack(anchor="w", pady=(3, 9))
        self.task_title = tk.StringVar(value="")
        self.task_description = tk.StringVar(value="")
        self.task_plan = tk.StringVar(value="연결 없음")
        self.task_status = tk.StringVar(value="todo")
        self.task_priority = tk.StringVar(value="normal")
        self.task_feedback = tk.StringVar(value="새 업무를 등록하거나 목록에서 기존 업무를 선택하세요.")
        form = tk.Frame(panel, bg="#1c2a40")
        form.pack(fill="x", pady=(0, 8))
        self._label(form,"업무 제목").grid(row=0,column=0,sticky="w",padx=(0,10),pady=3)
        tk.Entry(form,textvariable=self.task_title).grid(row=0,column=1,sticky="ew",pady=3,ipady=4)
        self._label(form,"설명").grid(row=1,column=0,sticky="w",pady=3)
        tk.Entry(form,textvariable=self.task_description).grid(row=1,column=1,sticky="ew",pady=3,ipady=4)
        self._label(form,"연결 계획").grid(row=2,column=0,sticky="w",pady=3)
        self.task_plan_combo = ttk.Combobox(form,textvariable=self.task_plan,state="readonly",width=55)
        self.task_plan_combo.grid(row=2,column=1,sticky="ew",pady=3)
        self._label(form,"변경할 상태").grid(row=3,column=0,sticky="w",pady=3)
        self.task_status_combo=ttk.Combobox(form,textvariable=self.task_status,state="readonly",
                                            values=tuple(self.store.TASK_TRANSITIONS),width=18)
        self.task_status_combo.grid(row=3,column=1,sticky="w",pady=3)
        self._label(form,"업무 우선순위").grid(row=4,column=0,sticky="w",pady=3)
        self.task_priority_combo=ttk.Combobox(form,textvariable=self.task_priority,state="readonly",
                                             values=self.store.TASK_PRIORITIES,width=18)
        self.task_priority_combo.grid(row=4,column=1,sticky="w",pady=3)
        form.columnconfigure(1,weight=1)
        bar = tk.Frame(panel,bg="#1c2a40")
        bar.pack(fill="x",pady=(5,9))
        self.task_add_button=tk.Button(bar,text="새 업무 등록",command=self.add_task,bg="#4c83e6",fg="white",padx=10)
        self.task_add_button.pack(side="left",padx=(0,6))
        self.task_update_button=tk.Button(bar,text="선택 업무 수정",command=self.update_task)
        self.task_update_button.pack(side="left",padx=(0,6))
        self.task_status_button=tk.Button(bar,text="상태 변경",command=self.change_task_status)
        self.task_status_button.pack(side="left",padx=(0,6))
        self.task_priority_button=tk.Button(bar,text="우선순위 저장",command=self.change_task_priority)
        self.task_priority_button.pack(side="left",padx=(0,6))
        self.task_delete_button=tk.Button(bar,text="선택 업무 삭제",command=self.delete_task)
        self.task_delete_button.pack(side="left",padx=(0,6))
        tk.Button(bar,text="새 항목 입력",command=self.clear_task).pack(side="left")
        frame=tk.Frame(panel)
        frame.pack(fill="both",expand=True)
        self.task_tree=ttk.Treeview(frame,columns=("id","plan","title","status","priority"),show="headings",height=6)
        for key,text,width in (("id","번호",55),("plan","업무 계획",190),
                               ("title","업무 제목",270),("status","상태",120),("priority","우선순위",95)):
            self.task_tree.heading(key,text=text)
            self.task_tree.column(key,width=width,stretch=key in ("plan","title"))
        self.task_tree.pack(side="left",fill="both",expand=True)
        scrollbar=ttk.Scrollbar(frame,orient="vertical",command=self.task_tree.yview)
        scrollbar.pack(side="right",fill="y")
        self.task_tree.configure(yscrollcommand=scrollbar.set)
        self.task_tree.bind("<<TreeviewSelect>>",self._load_task_selection)
        self._label(panel,"",textvariable=self.task_feedback,fg="#9cdbbb",wraplength=830).pack(anchor="w",pady=(6,0))
        self.refresh_task_plans()
        self.reload_tasks()

    def refresh_task_plans(self) -> None:
        self.store.require_permission("company:manage")
        current=self.task_plan.get()
        self.task_plan_map={"연결 없음":None}
        for plan in self.store.list_work_plans():
            self.task_plan_map[f"{plan['id']} · {plan['title']}"]=int(plan["id"])
        options=list(self.task_plan_map)
        self.task_plan_combo["values"]=options
        self.task_plan.set(current if current in options else "연결 없음")

    def _task_form_values(self) -> tuple[str,str,int | None]:
        self.store.require_permission("company:manage")
        chosen=self.task_plan.get()
        if chosen not in self.task_plan_map:
            raise ValueError("목록에 있는 업무 계획을 선택하세요.")
        return self.task_title.get(),self.task_description.get(),self.task_plan_map[chosen]

    def reload_tasks(self, selected_id:int | None=None) -> None:
        self.store.require_permission("company:manage")
        self.refresh_task_plans()
        for row in self.task_tree.get_children():
            self.task_tree.delete(row)
        for task in self.store.list_tasks():
            self.task_tree.insert("","end",iid=str(task["id"]),
                                  values=(task["id"],task["plan_title"] or "연결 없음",
                                          task["title"],task["status"],task["priority"]))
        if selected_id is not None and self.task_tree.exists(str(selected_id)):
            self.task_tree.selection_set(str(selected_id))

    def _selected_task_id(self) -> int:
        self.store.require_permission("company:manage")
        chosen=self.task_tree.selection()
        if not chosen:
            raise ValueError("먼저 목록에서 업무를 선택하세요.")
        return int(chosen[0])

    def _load_task_selection(self,event=None) -> None:
        self.store.require_permission("company:manage")
        chosen=self.task_tree.selection()
        if not chosen:
            return
        task=self.store.read_task(int(chosen[0]))
        self.task_title.set(str(task["title"]))
        self.task_description.set(str(task["description"]))
        self.task_status.set(str(task["status"]))
        self.task_priority.set(str(task["priority"]))
        self.refresh_task_plans()
        self.task_plan.set(next((name for name, plan_id in self.task_plan_map.items()
                                  if plan_id==task["plan_id"]),"연결 없음"))
        history=self.store.list_task_status_events(int(chosen[0]))
        self.task_feedback.set(f"업무 {task['id']} 선택 · 현재 {task['status']} · 우선순위 {task['priority']} · 상태 기록 {len(history)}건")

    def clear_task(self) -> None:
        self.store.require_permission("company:manage")
        self.task_tree.selection_remove(*self.task_tree.selection())
        self.task_title.set("")
        self.task_description.set("")
        self.task_plan.set("연결 없음")
        self.task_status.set("todo")
        self.task_priority.set("normal")
        self.task_feedback.set("새 업무를 입력할 수 있습니다.")

    def add_task(self) -> None:
        try:
            title,desc,plan_id=self._task_form_values()
            task_id=self.store.add_task(title,desc,plan_id)
            self.reload_tasks(task_id)
            self.task_feedback.set("새 업무를 로컬 데이터베이스에 저장했습니다. AI를 실행하지 않았습니다.")
        except (ValueError,PermissionError) as exc:
            self.task_feedback.set(f"업무 등록 실패: {exc}")

    def update_task(self) -> None:
        try:
            task_id=self._selected_task_id()
            title,desc,plan_id=self._task_form_values()
            self.store.update_task(task_id,title,desc,plan_id)
            self.reload_tasks(task_id)
            self.task_feedback.set("선택한 업무 정보를 수정했습니다.")
        except (ValueError,PermissionError) as exc:
            self.task_feedback.set(f"수정 실패: {exc}")

    def change_task_status(self) -> None:
        try:
            task_id=self._selected_task_id()
            self.store.set_task_status(task_id,self.task_status.get())
            self.reload_tasks(task_id)
            count=len(self.store.list_task_status_events(task_id))
            self.task_feedback.set(f"상태 변경을 저장했습니다. 기록 {count}건 (AI 실행 없음)")
        except (ValueError,PermissionError) as exc:
            self.task_feedback.set(f"상태 변경 실패: {exc}")

    def change_task_priority(self) -> None:
        try:
            task_id=self._selected_task_id()
            changed=self.store.set_task_priority(task_id,self.task_priority.get())
            self.reload_tasks(task_id)
            count=len(self.store.list_task_priority_events(task_id))
            self.task_feedback.set(f"우선순위 {'변경' if changed else '유지'} · 변경 기록 {count}건 (AI 실행 없음)")
        except (ValueError,PermissionError) as exc:
            self.task_feedback.set(f"우선순위 변경 실패: {exc}")

    def delete_task(self) -> None:
        try:
            task_id=self._selected_task_id()
            if not messagebox.askyesno("업무 삭제","선택한 업무와 상태 기록을 삭제할까요?",parent=self.root):
                return
            self.store.delete_task(task_id)
            self.clear_task()
            self.reload_tasks()
            self.task_feedback.set("선택한 업무를 삭제했습니다.")
        except (ValueError,PermissionError) as exc:
            self.task_feedback.set(f"삭제 실패: {exc}")


    # Stage 26 — owner-controlled prerequisite graph in the native GUI.
    def _task_dependencies(self, parent: tk.Frame) -> None:
        self.store.require_permission("company:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "선행·후속 업무 의존성 관리", size=18, weight="bold").pack(anchor="w")
        self._label(panel, "후속 업무는 선행 업무가 모두 완료되어야 진행할 수 있습니다. "
                    "순환 관계를 차단하며 AI를 자동 실행하지 않습니다.",
                    fg="#f7cb92", size=9, wraplength=830, justify="left").pack(anchor="w", pady=(3, 12))
        self.dependency_task = tk.StringVar(value="")
        self.dependency_prerequisite = tk.StringVar(value="")
        self.dependency_summary = tk.StringVar(value="후속 업무를 선택하세요.")
        self.dependency_feedback = tk.StringVar(value="의존성은 로컬 SQLite에 저장됩니다.")
        form = tk.Frame(panel, bg="#1c2a40")
        form.pack(fill="x", pady=(0, 8))
        self._label(form, "후속 업무 (기다리는 업무)").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
        self.dependency_task_combo = ttk.Combobox(form, textvariable=self.dependency_task,
                                                   state="readonly", width=64)
        self.dependency_task_combo.grid(row=0, column=1, sticky="ew", pady=5)
        self.dependency_task_combo.bind("<<ComboboxSelected>>", self.load_task_dependencies)
        self._label(form, "선행 업무 (먼저 완료)").grid(row=1, column=0, sticky="w", pady=5)
        self.dependency_prerequisite_combo = ttk.Combobox(form, textvariable=self.dependency_prerequisite,
                                                           state="readonly", width=64)
        self.dependency_prerequisite_combo.grid(row=1, column=1, sticky="ew", pady=5)
        form.columnconfigure(1, weight=1)
        bar = tk.Frame(panel, bg="#1c2a40")
        bar.pack(fill="x", pady=(5, 10))
        self.dependency_add_button = tk.Button(bar, text="선행 업무 연결", command=self.add_task_dependency,
                                               bg="#4c83e6", fg="white", padx=10)
        self.dependency_add_button.pack(side="left", padx=(0, 7))
        self.dependency_remove_button = tk.Button(bar, text="선택한 연결 해제",
                                                  command=self.remove_task_dependency, padx=10)
        self.dependency_remove_button.pack(side="left", padx=(0, 7))
        self.dependency_refresh_button = tk.Button(bar, text="목록 새로고침",
                                                   command=self.refresh_task_dependency_choices)
        self.dependency_refresh_button.pack(side="left")
        self._label(panel, "", textvariable=self.dependency_summary, fg="#9ddac1",
                    wraplength=830).pack(anchor="w", pady=(0, 9))
        self._label(panel, "선택한 업무의 선행 업무", weight="bold").pack(anchor="w", pady=(3, 5))
        table = tk.Frame(panel)
        table.pack(fill="both", expand=True)
        self.dependency_tree = ttk.Treeview(table, columns=("id", "title", "status", "ready"),
                                             show="headings", height=5)
        for key, label, width in (("id", "업무 ID", 85), ("title", "선행 업무 제목", 400),
                                  ("status", "현재 상태", 135), ("ready", "완료 여부", 125)):
            self.dependency_tree.heading(key, text=label)
            self.dependency_tree.column(key, width=width, stretch=key=="title")
        self.dependency_tree.pack(side="left", fill="both", expand=True)
        sc = ttk.Scrollbar(table, orient="vertical", command=self.dependency_tree.yview)
        sc.pack(side="right", fill="y")
        self.dependency_tree.configure(yscrollcommand=sc.set)
        self._label(panel, "연결·해제 기록", weight="bold").pack(anchor="w", pady=(10, 5))
        self.dependency_events = ttk.Treeview(panel, columns=("id", "upstream", "action", "date"),
                                               show="headings", height=4)
        for key, label, width in (("id", "기록", 70), ("upstream", "선행 업무 ID", 135),
                                  ("action", "변경", 120), ("date", "기록 시각", 250)):
            self.dependency_events.heading(key, text=label)
            self.dependency_events.column(key, width=width, stretch=key=="date")
        self.dependency_events.pack(fill="both", expand=True)
        self._label(panel, "", textvariable=self.dependency_feedback, fg="#9cdbbb",
                    wraplength=830).pack(anchor="w", pady=(8, 0))
        self.refresh_task_dependency_choices()

    def refresh_task_dependency_choices(self) -> None:
        self.store.require_permission("company:manage")
        current_task = self.dependency_task.get()
        current_upstream = self.dependency_prerequisite.get()
        self.dependency_task_map = {f"{t['id']} · [{t['status']}] {t['title']}": int(t['id'])
                                    for t in self.store.list_tasks()}
        labels = list(self.dependency_task_map)
        self.dependency_task_combo["values"] = labels
        self.dependency_prerequisite_combo["values"] = labels
        self.dependency_task.set(current_task if current_task in labels else "")
        self.dependency_prerequisite.set(current_upstream if current_upstream in labels else "")
        self.load_task_dependencies()

    def _dependency_selected_task(self) -> int:
        selected = self.dependency_task.get()
        if selected not in self.dependency_task_map:
            raise ValueError("후속 업무를 선택하세요.")
        return self.dependency_task_map[selected]

    def load_task_dependencies(self, event=None) -> None:
        for table in (self.dependency_tree, self.dependency_events):
            for iid in table.get_children():
                table.delete(iid)
        if not self.dependency_task.get():
            self.dependency_summary.set("후속 업무를 선택하세요.")
            return
        task_id = self._dependency_selected_task()
        for dependency in self.store.list_task_dependencies(task_id):
            self.dependency_tree.insert("", "end", iid=str(dependency["prerequisite_id"]),
                                        values=(dependency["prerequisite_id"], dependency["title"],
                                                dependency["status"],
                                                "완료" if dependency["satisfied"] else "미완료"))
        for record in self.store.list_task_dependency_events(task_id):
            self.dependency_events.insert("", "end", values=(record["id"], record["prerequisite_id"],
                                                              record["action"], record["changed_at"]))
        readiness = self.store.task_dependency_readiness(task_id)
        pending = ", ".join(map(str, readiness["pending_ids"])) or "없음"
        self.dependency_summary.set(f"업무 {task_id} · 선행 업무 {readiness['total']}개 · "
                                    f"{'진행 가능' if readiness['ready'] else '대기'} · 미완료 ID: {pending}")

    def add_task_dependency(self) -> None:
        try:
            task_id = self._dependency_selected_task()
            selected = self.dependency_prerequisite.get()
            if selected not in self.dependency_task_map:
                raise ValueError("선행 업무를 선택하세요.")
            changed = self.store.add_task_dependency(task_id, self.dependency_task_map[selected])
            self.load_task_dependencies()
            self.dependency_feedback.set("선행 업무를 연결했습니다." if changed else "이미 연결된 선행 업무입니다.")
        except (ValueError, PermissionError) as exc:
            self.dependency_feedback.set(f"연결 실패: {exc}")

    def remove_task_dependency(self) -> None:
        try:
            task_id = self._dependency_selected_task()
            selected = self.dependency_tree.selection()
            if not selected:
                raise ValueError("해제할 선행 업무를 목록에서 선택하세요.")
            changed = self.store.remove_task_dependency(task_id, int(selected[0]))
            self.load_task_dependencies()
            self.dependency_feedback.set("연결을 해제하고 이력을 보관했습니다." if changed else "이미 해제된 연결입니다.")
        except (ValueError, PermissionError) as exc:
            self.dependency_feedback.set(f"연결 해제 실패: {exc}")

    # Stage 27: explicit local AI task execution (single job, no tools or network).
    def _task_execution(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        panel=self._panel(parent)
        panel.pack(fill='both',expand=True)
        self._label(panel,'독립 업무 병렬 실행 · 로컬 모델 (최대 2개)',size=18,weight='bold').pack(anchor='w')
        self._label(panel,'관리자가 직접 누를 때만 서로 다른 담당 직원의 독립 업무를 최대 2개까지 병렬 호출합니다. '
                    '모델 출력은 자동 저장되지 않습니다. 결과물 저장은 관리자가 명시적으로 선택하며, 업무 완료·외부 접속·결제는 실행하지 않습니다.',
                    fg='#f7cb92',wraplength=820,size=9).pack(anchor='w',pady=(4,11))
        self._task_execution_active=False
        self._task_runs_live: dict[int, tuple[threading.Event, threading.Thread]] = {}
        self._task_drafts: dict[int, tuple[int, str]] = {}
        self._displayed_execution_task: int | None = None
        self.task_execution_task=tk.StringVar(value='')
        self.task_execution_feedback=tk.StringVar(value='서로 다른 AI 직원의 독립 업무를 선택해 최대 2개 실행할 수 있습니다.')
        row=tk.Frame(panel,bg='#1c2a40')
        row.pack(fill='x',pady=4)
        self._label(row,'업무 선택').pack(side='left',padx=(0,8))
        self.task_execution_combo=ttk.Combobox(row,textvariable=self.task_execution_task,
                                                state='readonly',width=65)
        self.task_execution_combo.pack(side='left',fill='x',expand=True)
        self.task_execution_combo.bind('<<ComboboxSelected>>',self.load_task_execution)
        actions=tk.Frame(panel,bg='#1c2a40')
        actions.pack(fill='x',pady=(7,12))
        self.task_execution_run_button=tk.Button(actions,text='선택 업무 로컬 AI 실행',
            command=self.start_task_execution,bg='#426cba',fg='white',padx=12,pady=6)
        self.task_execution_run_button.pack(side='left',padx=(0,8))
        self.task_execution_cancel_button=tk.Button(actions,text='선택 업무 실행 취소',
            command=self.cancel_task_execution,padx=12,pady=6)
        self.task_execution_cancel_button.pack(side='left',padx=(0,8))
        self.task_execution_recover_button=tk.Button(actions,text='중단된 실행 기록 복구',
            command=self.recover_task_execution,padx=12,pady=6)
        self.task_execution_recover_button.pack(side='left',padx=(0,8))
        tk.Button(actions,text='목록 새로고침',command=self.refresh_task_execution_choices).pack(side='left')
        tk.Button(actions,text='현재 응답 결과물로 저장',command=self.save_current_task_draft).pack(side='left',padx=(0,8))
        self._label(panel,'실행 기록 (입력문·응답 본문은 저장하지 않음)',weight='bold').pack(anchor='w')
        self.task_execution_events=ttk.Treeview(panel,columns=('id','status','model','date'),
                                                  show='headings',height=5)
        for key,label,width in (('id','실행 ID',75),('status','결과',125),
                                ('model','로컬 모델',225),('date','시작 시각',220)):
            self.task_execution_events.heading(key,text=label)
            self.task_execution_events.column(key,width=width,stretch=key=='model')
        self.task_execution_events.pack(fill='both',expand=True,pady=(5,9))
        self._label(panel,'이번 실행의 임시 텍스트 (프로그램 종료 시 소멸)',weight='bold').pack(anchor='w')
        self.task_execution_output=tk.Text(panel,height=7,wrap='word')
        self.task_execution_output.pack(fill='both',expand=True,pady=(5,9))
        self._label(panel,'',textvariable=self.task_execution_feedback,fg='#9cdbbb',
                    wraplength=820).pack(anchor='w')
        self.refresh_task_execution_choices()

    def refresh_task_execution_choices(self) -> None:
        self.store.require_permission('company:manage')
        # Preserve the selected task ID across status changes (todo -> in_progress).
        selected_id = getattr(self, 'task_execution_map', {}).get(self.task_execution_task.get())
        self.task_execution_map={f"{t['id']} · [{t['status']}] {t['title']}":int(t['id'])
                                 for t in self.store.list_tasks()}
        self.task_execution_combo['values']=list(self.task_execution_map)
        self.task_execution_task.set(next((key for key, value in self.task_execution_map.items()
                                          if value == selected_id), ''))
        self.load_task_execution()

    def _selected_execution_task(self) -> int:
        selected=self.task_execution_task.get()
        if selected not in self.task_execution_map:
            raise ValueError('먼저 실행할 업무를 선택하세요.')
        return self.task_execution_map[selected]

    def load_task_execution(self,event=None) -> None:
        selected = self.task_execution_map.get(self.task_execution_task.get())
        previous = self._displayed_execution_task
        if selected != previous:
            # Keep unsaved owner edits isolated by task, even while another
            # subprocess is still running and the selection changes.
            if previous in self._task_drafts:
                run_id, _ = self._task_drafts[previous]
                self._task_drafts[previous] = (run_id, self.task_execution_output.get('1.0','end-1c'))
            self.task_execution_output.delete('1.0','end')
            if selected in self._task_drafts:
                self.task_execution_output.insert('1.0', self._task_drafts[selected][1])
            self._displayed_execution_task = selected
        for item in self.task_execution_events.get_children():
            self.task_execution_events.delete(item)
        if selected is None:
            return
        for run in self.store.list_task_runs(selected):
            self.task_execution_events.insert('','end',iid=str(run['id']),
                values=(run['id'],run['status'],run['model_name'],run['started_at']))

    def start_task_execution(self) -> None:
        try:
            task_id=self._selected_execution_task()
            if self._model_running and not self._task_execution_active:
                raise ValueError('다른 종류의 로컬 모델 실행이 진행 중입니다.')
            if task_id in self._task_runs_live:
                raise ValueError('선택한 업무가 이미 실행 중입니다.')
            if len(self._task_runs_live) >= MAX_PARALLEL_TASK_RUNS:
                raise ValueError('병렬 실행은 최대 2개까지 허용합니다.')
            # DB transaction repeats all preflight checks, including employee
            # uniqueness and dependency readiness, to prevent race conditions.
            task=self.store.read_task(task_id)
            if task['status']!='todo':
                raise ValueError('할 일 상태의 업무만 실행할 수 있습니다.')
            if not messagebox.askyesno('로컬 AI 업무 실행',
                '선택한 로컬 실행파일을 이 PC에서 시작합니다. 신뢰할 수 있는 프로그램인지 확인했나요?\n'
                '최대 2개 병렬 실행은 PC 메모리·GPU 자원을 함께 사용합니다.\n'
                '업무는 완료 처리되지 않으며 모델 출력은 자동 저장하지 않습니다.',parent=self.root):
                self.task_execution_feedback.set('관리자가 실행을 취소했습니다.')
                return
        except (ValueError,PermissionError) as exc:
            self.task_execution_feedback.set(f'실행 시작 실패: {exc}')
            return
        generation=self._session_generation
        cancel=threading.Event()
        outbound=queue.Queue()
        if self._displayed_execution_task == task_id:
            self.task_execution_output.delete('1.0','end')
        self._task_drafts.pop(task_id,None)
        self.task_execution_feedback.set('독립 업무 로컬 모델 실행 중 (최대 60초/업무). 완료는 관리자가 수동 처리합니다.')
        def worker() -> None:
            try:
                result=invoke_task_execution(self.store,task_id,timeout=60,cancel=cancel)
                outbound.put((True,task_id,result))
            except Exception as exc:
                outbound.put((False,task_id,str(exc)))
        thread=threading.Thread(target=worker,daemon=True)
        self._task_runs_live[task_id]=(cancel,thread)
        self._model_running=True
        self._task_execution_active=True
        thread.start()
        self.root.after(100,lambda:self._poll_task_execution(generation,outbound))

    def _poll_task_execution(self,generation:int,outbound:queue.Queue) -> None:
        if generation!=self._session_generation or not self.store.is_authenticated:
            return
        try:
            success,executed_task_id,result=outbound.get_nowait()
        except queue.Empty:
            if self.root.winfo_exists():
                self.root.after(100,lambda:self._poll_task_execution(generation,outbound))
            return
        self._task_runs_live.pop(executed_task_id,None)
        self._task_execution_active=bool(self._task_runs_live)
        self._model_running=self._task_execution_active
        self.refresh_task_execution_choices()
        self.task_execution_feedback.set(
            f'업무 #{executed_task_id} 응답 완료 · 관리자 검토 필요 (남은 실행 {len(self._task_runs_live)}개)' if success
            else f'업무 #{executed_task_id} 실패/취소: {result} (남은 실행 {len(self._task_runs_live)}개)')
        if success:
            recent=self.store.list_task_runs(executed_task_id)
            if recent and recent[0]['status']=='success':
                self._task_drafts[executed_task_id]=(recent[0]['id'],result)
                if self._displayed_execution_task == executed_task_id:
                    self.task_execution_output.delete('1.0','end')
                    self.task_execution_output.insert('1.0',result or '(빈 응답)')

    def save_current_task_draft(self) -> None:
        try:
            task_id=self._selected_execution_task()
            if task_id in self._task_runs_live:
                raise ValueError('선택한 업무 실행이 종료된 뒤 저장하세요.')
            if task_id not in self._task_drafts:
                raise ValueError('이 업무의 성공한 실행 응답이 현재 화면에 없습니다.')
            run_id, _ = self._task_drafts[task_id]
            body=self.task_execution_output.get('1.0','end-1c')
            title=str(self.store.read_task(task_id)['title'])+' · 실행 초안'
            if not messagebox.askyesno('결과물 로컬 저장',
                '현재 화면의 텍스트를 로컬 SQLite에 평문으로 저장합니다. 비밀정보가 포함되지 않았는지 확인했나요?\n'
                '저장 후 본문은 수정할 수 없으며 업무는 자동 완료되지 않습니다.',parent=self.root):
                return
            artifact_id=self.store.save_task_artifact(task_id,run_id,title,body)
            self._task_drafts.pop(task_id,None)
            self.task_execution_feedback.set(f'결과물 #{artifact_id} 저장 완료. 업무 결과물·검수 탭에서 검토하세요.')
            self.refresh_task_artifacts()
        except (ValueError,PermissionError) as exc:
            self.task_execution_feedback.set('저장 실패: '+str(exc))

    def _task_artifacts(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        panel=self._panel(parent)
        panel.pack(fill='both',expand=True)
        self._label(panel,'업무 결과물 저장 및 관리자 검수',size=18,weight='bold').pack(anchor='w')
        self._label(panel,'실행 화면에서 관리자가 명시적으로 저장한 텍스트만 표시됩니다. '
                    '본문은 로컬 SQLite에 평문 저장되며 검수는 업무를 자동 완료하지 않습니다.',
                    fg='#f7cb92',wraplength=820).pack(anchor='w',pady=(5,9))
        self.task_artifact_list=ttk.Treeview(panel,columns=('id','task','title','review'),
                                              show='headings',height=5)
        for key,label,width in (('id','ID',60),('task','업무 ID',75),('title','제목',340),('review','검수',135)):
            self.task_artifact_list.heading(key,text=label)
            self.task_artifact_list.column(key,width=width,stretch=key=='title')
        self.task_artifact_list.pack(fill='x',pady=6)
        self.task_artifact_list.bind('<<TreeviewSelect>>',self.load_task_artifact)
        self.task_artifact_body=tk.Text(panel,height=10,wrap='word',state='disabled')
        self.task_artifact_body.pack(fill='both',expand=True,pady=(5,7))
        self.task_artifact_note=tk.StringVar(value='')
        self._label(panel,'검수 의견 (수정 요청·반려는 필수, 최대 1000자)').pack(anchor='w')
        tk.Entry(panel,textvariable=self.task_artifact_note).pack(fill='x',pady=(3,7))
        buttons=tk.Frame(panel,bg='#1c2a40')
        buttons.pack(fill='x',pady=(0,8))
        for text,decision in (('승인','approved'),('수정 요청','changes_requested'),('반려','rejected')):
            tk.Button(buttons,text=text,command=lambda d=decision:self.review_selected_task_artifact(d),
                      padx=12).pack(side='left',padx=(0,7))
        tk.Button(buttons,text='목록 새로고침',command=self.refresh_task_artifacts).pack(side='left')
        self.task_artifact_feedback=tk.StringVar(value='결과물을 선택하여 검수하세요.')
        self._label(panel,'',textvariable=self.task_artifact_feedback,fg='#9cdbbb',wraplength=820).pack(anchor='w')
        self.refresh_task_artifacts()

    def refresh_task_artifacts(self) -> None:
        self.store.require_permission('company:manage')
        if not hasattr(self,'task_artifact_list'):
            return
        for row in self.task_artifact_list.get_children():
            self.task_artifact_list.delete(row)
        for artifact in self.store.list_task_artifacts():
            self.task_artifact_list.insert('','end',iid=str(artifact['id']),values=(
                artifact['id'],artifact['task_id'],artifact['title'],artifact['review_status']))
        self.task_artifact_body.configure(state='normal')
        self.task_artifact_body.delete('1.0','end')
        self.task_artifact_body.configure(state='disabled')

    def load_task_artifact(self,event=None) -> None:
        selection=self.task_artifact_list.selection()
        if not selection:
            return
        try:
            artifact=self.store.read_task_artifact(int(selection[0]))
            self.task_artifact_body.configure(state='normal')
            self.task_artifact_body.delete('1.0','end')
            self.task_artifact_body.insert('1.0',str(artifact['body']))
            self.task_artifact_body.configure(state='disabled')
            self.task_artifact_feedback.set(f"결과물 #{artifact['id']} · {artifact['review_status']} · SHA256 {artifact['sha256']}")
        except (ValueError,PermissionError) as exc:
            self.task_artifact_feedback.set('읽기 실패: '+str(exc))

    def review_selected_task_artifact(self, decision: str) -> None:
        try:
            selected=self.task_artifact_list.selection()
            if not selected:
                raise ValueError('검수할 결과물을 선택하세요.')
            if not messagebox.askyesno('결과물 검수 확인',
                '검수 결정은 변경할 수 없고 이력이 보존됩니다. 계속할까요?',parent=self.root):
                return
            artifact_id=int(selected[0])
            self.store.review_task_artifact(artifact_id,decision,self.task_artifact_note.get())
            self.task_artifact_note.set('')
            self.refresh_task_artifacts()
            self.task_artifact_feedback.set(f'결과물 #{artifact_id} 검수 완료: {decision}. 업무 상태는 변경하지 않았습니다.')
        except (ValueError,PermissionError) as exc:
            self.task_artifact_feedback.set('검수 실패: '+str(exc))

    def cancel_task_execution(self) -> None:
        task_id = self.task_execution_map.get(self.task_execution_task.get())
        if task_id in self._task_runs_live:
            self._task_runs_live[task_id][0].set()
            self.task_execution_feedback.set(f'업무 #{task_id} 취소 요청 · 다른 실행은 계속 진행합니다.')
        else:
            self.task_execution_feedback.set('선택한 업무는 현재 실행 중이지 않습니다.')

    def recover_task_execution(self) -> None:
        try:
            if self._selected_execution_task() in self._task_runs_live:
                raise ValueError('현재 실행 중인 업무는 복구할 수 없습니다.')
            selected=self.task_execution_events.selection()
            if not selected:
                raise ValueError('복구할 실행 기록을 먼저 선택하세요.')
            run_id=int(selected[0])
            row=next((r for r in self.store.list_task_runs(self._selected_execution_task())
                      if r['id']==run_id),None)
            if row is None or row['status']!='running':
                raise ValueError('running 상태의 실행 기록만 복구할 수 있습니다.')
            if not messagebox.askyesno('중단된 실행 기록 복구',
                '이전 로컬 모델 프로세스가 완전히 종료된 것을 확인했나요?\n'
                '확인하면 해당 기록을 interrupted로 종료하고 업무를 차단 상태로 변경합니다.',
                parent=self.root):
                return
            self.store.recover_interrupted_task_run(run_id)
            self.load_task_execution()
            self.task_execution_feedback.set('중단된 실행 기록을 복구했습니다. 재시도하려면 업무 상태를 할 일로 바꾸세요.')
        except (ValueError,PermissionError) as exc:
            self.task_execution_feedback.set('복구 실패: '+str(exc))

    # Stage 30: chief -> worker text handoff and saved artifact -> chief review.
    # Stage 31: read-only aggregate checks run once on login and every five
    # minutes while this authenticated Tk window remains open. No OS service.
    def _health_monitor(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '회사 상황 자동 점검', size=18, weight='bold').pack(anchor='w')
        self._label(panel, '로그인 직후 및 창이 열린 동안 5분마다 로컬 SQLite 통계만 점검합니다. '
                    '업무 생성·변경, 모델 호출, 외부 전송은 하지 않습니다.',
                    fg='#bfcfe5', wraplength=840, justify='left').pack(anchor='w', pady=(7, 12))
        self.health_summary = tk.StringVar(value='점검 전')
        self.health_feedback = tk.StringVar(value='')
        self._label(panel, '', textvariable=self.health_summary, fg='#9ddac1',
                    wraplength=840, justify='left', weight='bold').pack(anchor='w', pady=(5, 12))
        tk.Button(panel, text='지금 점검 · 이력 저장', command=self.manual_company_health_check,
                  padx=13, pady=7).pack(anchor='w', pady=(0, 10))
        self._label(panel, '', textvariable=self.health_feedback, fg='#f7cb92',
                    wraplength=840, justify='left').pack(anchor='w', pady=(0, 10))
        self._label(panel, '최근 점검 기록 (내용·직원명·모델 출력은 저장하지 않음)',
                    weight='bold').pack(anchor='w', pady=(0, 6))
        frame = tk.Frame(panel)
        frame.pack(fill='both', expand=True)
        columns = ('id', 'time', 'severity', 'issues')
        self.health_history = ttk.Treeview(frame, columns=columns, show='headings', height=9)
        for key, title, width in [('id', '번호', 65), ('time', '점검 시각 (SQLite UTC)', 170),
                                  ('severity', '판정', 95), ('issues', '문제 요약', 470)]:
            self.health_history.heading(key, text=title)
            self.health_history.column(key, width=width, stretch=key == 'issues')
        self.health_history.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=self.health_history.yview)
        scrollbar.pack(side='right', fill='y')
        self.health_history.configure(yscrollcommand=scrollbar.set)

    # Stage 32: deterministic problem/opportunity detection; no market research
    # or autonomous task creation. Current goal/plan IDs are never stored in
    # history, and no user-authored title or body is read by the detector.
    def _company_detection(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '문제 및 내부 사업 기회 후보 감지', size=18, weight='bold').pack(anchor='w')
        self._label(panel, '로그인 직후 및 앱 실행 중 5분마다 로컬 DB를 검사합니다. '
                    '사업 기회는 등록된 활성 목표·준비 완료 계획에서 찾은 내부 후보일 뿐, '
                    '시장 수요·수익성·실행 가능성을 검증한 결과가 아닙니다. '
                    '업무 생성·모델 실행·외부 전송은 하지 않습니다.',
                    fg='#bfcfe5', wraplength=840, justify='left').pack(anchor='w', pady=(7, 9))
        self.detection_summary = tk.StringVar(value='감지 전')
        self.detection_feedback = tk.StringVar(value='')
        self._label(panel, '', textvariable=self.detection_summary, fg='#9ddac1',
                    wraplength=840, justify='left', weight='bold').pack(anchor='w', pady=(3, 7))
        tk.Button(panel, text='지금 감지 · 이력 저장', command=self.manual_company_detection,
                  padx=13, pady=6).pack(anchor='w', pady=(0, 7))
        self._label(panel, '', textvariable=self.detection_feedback, fg='#f7cb92',
                    wraplength=840, justify='left').pack(anchor='w', pady=(0, 7))
        self._label(panel, '현재 신호 (번호는 로컬 목표·계획 ID, 최대 20개 표시)',
                    weight='bold').pack(anchor='w')
        signal_frame = tk.Frame(panel)
        signal_frame.pack(fill='both', expand=True, pady=(3, 9))
        cols = ('kind', 'severity', 'label', 'count', 'ids')
        self.detection_signals = ttk.Treeview(signal_frame, columns=cols, show='headings', height=6)
        for key, title, width in [('kind', '분류', 90), ('severity', '수준', 85),
                                  ('label', '감지 근거', 330), ('count', '건수', 55),
                                  ('ids', '대상 ID 일부', 170)]:
            self.detection_signals.heading(key, text=title)
            self.detection_signals.column(key, width=width, stretch=key in ('label', 'ids'))
        self.detection_signals.pack(fill='both', expand=True)
        self._label(panel, '최근 감지 이력 (고정 코드·건수만 저장, 목표명·본문·ID 미보관)',
                    weight='bold').pack(anchor='w')
        history_frame = tk.Frame(panel)
        history_frame.pack(fill='both', expand=True, pady=(3, 0))
        cols = ('id', 'time', 'severity', 'summary')
        self.detection_history = ttk.Treeview(history_frame, columns=cols, show='headings', height=5)
        for key, title, width in [('id', '번호', 60), ('time', '시각 (SQLite UTC)', 160),
                                  ('severity', '문제 수준', 85), ('summary', '신호 코드 및 건수', 450)]:
            self.detection_history.heading(key, text=title)
            self.detection_history.column(key, width=width, stretch=key == 'summary')
        self.detection_history.pack(fill='both', expand=True)

    # Stage 33: autonomous *rule-based* draft creation from local signals.
    # No actual AI inference, real task creation or execution until approval.
    def _task_breakdowns(self, parent: tk.Frame) -> None:
        """Owner review screen: draft first, explicit confirmation to add tasks."""
        self.store.require_permission('company:manage')
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '복합 업무 세부 계획 (규칙 기반)', size=18, weight='bold').pack(anchor='w')
        self._label(panel, '활성 목표의 준비 완료 계획 중 6~30단계를 미배정 업무 초안으로 분할합니다. '
                    '단계 순서대로 선행 관계를 제안하며, 관리자 승인 전에는 실제 업무가 생기지 않습니다. '
                    '실제 AI 추론·업무 자동 실행이 아닙니다.',
                    fg='#f7cb92', wraplength=850, size=9).pack(anchor='w', pady=(5, 10))
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self.breakdown_plan_choice = tk.StringVar(value='')
        self._label(row, '원본 계획').pack(side='left', padx=(0, 7))
        self.breakdown_plan_combo = ttk.Combobox(row, state='readonly',
            textvariable=self.breakdown_plan_choice, width=55)
        self.breakdown_plan_combo.pack(side='left', fill='x', expand=True)
        tk.Button(row, text='계획 목록 갱신', command=self.refresh_task_breakdowns).pack(side='left', padx=5)
        tk.Button(row, text='세부 초안 생성', command=self.generate_task_breakdown).pack(side='left', padx=5)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=(3, 8))
        tk.Button(row, text='선택 초안 승인 · 업무/선행 관계 생성',
                  command=self.apply_task_breakdown).pack(side='left', padx=(0, 8))
        tk.Button(row, text='선택 초안 거절', command=self.reject_task_breakdown).pack(side='left')
        self.breakdown_feedback = tk.StringVar(value='먼저 원본 계획을 선택해 초안을 생성하세요.')
        self._label(panel, '', textvariable=self.breakdown_feedback,
                    fg='#9cdbbb', wraplength=850).pack(anchor='w', pady=(0, 8))
        listing = tk.Frame(panel); listing.pack(fill='both', expand=True)
        self.breakdown_tree = ttk.Treeview(listing, columns=('id','plan','count','status'), show='headings', height=6)
        for col, label, width in [('id','초안 ID',80),('plan','원본 계획',400),
                                  ('count','단계 수',90),('status','상태',100)]:
            self.breakdown_tree.heading(col, text=label)
            self.breakdown_tree.column(col, width=width, stretch=col=='plan')
        self.breakdown_tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(listing, orient='vertical', command=self.breakdown_tree.yview)
        scroll.pack(side='right', fill='y')
        self.breakdown_tree.configure(yscrollcommand=scroll.set)
        self.breakdown_tree.bind('<<TreeviewSelect>>', self.show_task_breakdown)
        self._label(panel, '선택 초안의 단계 / 선행 관계 / 완료 기준 (읽기 전용)').pack(anchor='w', pady=(9, 3))
        self.breakdown_details = tk.Text(panel, height=9, wrap='word', state='disabled')
        self.breakdown_details.pack(fill='both', expand=True)
        self.refresh_task_breakdowns()

    def refresh_task_breakdowns(self) -> None:
        try:
            plans = self.store.list_work_plans()
            self.breakdown_plan_map = {
                f"#{p['id']} · {p['title']} ({p['steps_count']}단계, {p['status']})": p['id']
                for p in plans}
            self.breakdown_plan_combo['values'] = list(self.breakdown_plan_map)
            if self.breakdown_plan_choice.get() not in self.breakdown_plan_map:
                self.breakdown_plan_choice.set('')
            selected = self.breakdown_tree.selection()
            previous = selected[0] if selected else None
            for item in self.breakdown_tree.get_children():
                self.breakdown_tree.delete(item)
            statuses = {'draft':'승인 대기', 'applied':'승인 적용',
                        'stale':'원본 변경', 'rejected':'거절'}
            for draft in self.store.list_task_breakdowns():
                self.breakdown_tree.insert('', 'end', iid=str(draft['id']), values=(
                    draft['id'], f"#{draft['plan_id']} · {draft['plan_title']}",
                    draft['item_count'], statuses[draft['status']]))
            if previous and self.breakdown_tree.exists(previous):
                self.breakdown_tree.selection_set(previous)
            self.show_task_breakdown()
        except (ValueError, PermissionError, OSError) as exc:
            self.breakdown_feedback.set('목록 조회 실패: ' + str(exc))

    def show_task_breakdown(self, event=None) -> None:
        selected = self.breakdown_tree.selection()
        self.breakdown_details.configure(state='normal')
        self.breakdown_details.delete('1.0', 'end')
        if selected:
            try:
                draft = self.store.read_task_breakdown(int(selected[0]))
                for item in draft['items']:
                    prerequisite = item['prerequisite_position']
                    self.breakdown_details.insert('end',
                        f"{item['position']}. {item['title']}\n"
                        f"   선행: {str(prerequisite) + '단계' if prerequisite else '없음'}"
                        f" · 등록 업무: {item['task_id'] or '미등록'}\n"
                        f"   {item['detail']}\n\n")
            except (ValueError, PermissionError) as exc:
                self.breakdown_feedback.set('초안 조회 실패: ' + str(exc))
        self.breakdown_details.configure(state='disabled')

    def _selected_task_breakdown_id(self) -> int:
        selected = self.breakdown_tree.selection()
        if not selected:
            raise ValueError('세부 계획 초안을 먼저 선택하세요.')
        return int(selected[0])

    def generate_task_breakdown(self) -> None:
        try:
            plan_id = self.breakdown_plan_map.get(self.breakdown_plan_choice.get())
            if plan_id is None:
                raise ValueError('원본 계획을 선택하세요.')
            draft_id = self.store.generate_task_breakdown(plan_id)
            self.refresh_task_breakdowns()
            self.breakdown_tree.selection_set(str(draft_id))
            self.show_task_breakdown()
            self.breakdown_feedback.set(f'세부 계획 초안 #{draft_id} 저장. 실제 업무는 아직 생성되지 않았습니다.')
        except (ValueError, PermissionError, OSError) as exc:
            self.breakdown_feedback.set('초안 생성 실패: ' + str(exc))

    def apply_task_breakdown(self) -> None:
        try:
            draft_id = self._selected_task_breakdown_id()
            draft = self.store.read_task_breakdown(draft_id)
            if draft['status'] != 'draft':
                raise ValueError('승인 대기 중인 초안만 적용할 수 있습니다.')
            if not messagebox.askyesno('세부 계획 적용 승인',
                f"초안 #{draft_id}의 {len(draft['items'])}개 업무를 실제 todo로 등록하고 "
                '순차 선행 관계를 생성하시겠습니까? AI 실행은 시작되지 않습니다.', parent=self.root):
                return
            ids = self.store.apply_task_breakdown(draft_id)
            self.refresh_task_breakdowns()
            self.breakdown_feedback.set(
                f'초안 #{draft_id}의 원본 조건이 변경되어 적용을 취소했습니다.' if ids is None
                else f'초안 #{draft_id} 승인: 미배정 todo 업무 {len(ids)}개와 선행 관계 생성 완료. 실행 없음.')
        except (ValueError, PermissionError, OSError) as exc:
            self.breakdown_feedback.set('초안 적용 실패: ' + str(exc))

    def reject_task_breakdown(self) -> None:
        try:
            draft_id = self._selected_task_breakdown_id()
            if not messagebox.askyesno('세부 계획 거절', f'초안 #{draft_id}을 거절하시겠습니까?', parent=self.root):
                return
            self.store.reject_task_breakdown(draft_id)
            self.refresh_task_breakdowns()
            self.breakdown_feedback.set(f'초안 #{draft_id} 거절 완료. 업무 생성 없음.')
        except (ValueError, PermissionError, OSError) as exc:
            self.breakdown_feedback.set('초안 거절 실패: ' + str(exc))

    def _autonomous_task_proposals(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '자동 업무 제안 · 관리자 승인', size=18, weight='bold').pack(anchor='w')
        self._label(panel, '로그인 직후와 앱 실행 중 5분마다 로컬 규칙으로 제안 초안을 만듭니다. '
                    '현재는 실제 언어 모델이 아니라 고정 규칙을 사용합니다. '
                    '제안만으로 실제 업무는 만들어지거나 실행되지 않습니다. '
                    '관리자가 선택 후 승인해야 할 일(todo)로 등록됩니다. '
                    '외부 서비스·자동 실행·자동 결제 없음.',
                    fg='#bfcfe5', wraplength=850, justify='left').pack(anchor='w', pady=(7, 10))
        buttons = tk.Frame(panel, bg='#1c2a40')
        buttons.pack(anchor='w', pady=(0, 9))
        tk.Button(buttons, text='새 후보 스캔', command=self.scan_autonomous_task_proposals,
                  padx=12, pady=6).pack(side='left', padx=(0, 8))
        tk.Button(buttons, text='선택 제안 승인 · 업무 등록',
                  command=self.approve_autonomous_task_proposal,
                  padx=12, pady=6).pack(side='left', padx=(0, 8))
        tk.Button(buttons, text='선택 제안 거절', command=self.reject_autonomous_task_proposal,
                  padx=12, pady=6).pack(side='left', padx=(0, 8))
        tk.Button(buttons, text='실행 가능성·우선순위 재분석',
                  command=self.analyze_autonomous_task_proposals,
                  padx=12, pady=6).pack(side='left', padx=(0, 8))
        tk.Button(buttons, text='목록 새로고침', command=self.refresh_autonomous_task_proposals,
                  padx=12, pady=6).pack(side='left', padx=(0, 8))
        self.auto_proposal_ai_button = tk.Button(
            buttons, text='로컬 총괄 AI 자동 초안 켜기 (선택)',
            command=self.toggle_auto_proposal_ai, padx=12, pady=6)
        self.auto_proposal_ai_button.pack(side='left')
        self._label(panel, '선택 기능: 총괄 AI와 로컬 모델이 설정된 경우에만, 관리자 동의 후 '
                    '5분 주기마다 최대 1개 초안을 로컬 모델로 구체화합니다. '
                    '로그아웃하면 중지합니다. 모델 출력은 검토 전까지 실행하지 않습니다. '
                    '지정한 실행파일의 OS 수준 네트워크 격리는 제공하지 않습니다.',
                    fg='#bfcfe5', wraplength=850, justify='left').pack(anchor='w', pady=(0, 6))
        self.autonomous_proposals_feedback = tk.StringVar(value='')
        self._label(panel, '', textvariable=self.autonomous_proposals_feedback,
                    fg='#f7cb92', wraplength=850, justify='left').pack(anchor='w', pady=(0, 8))
        frame = tk.Frame(panel)
        frame.pack(fill='both', expand=True)
        columns = ('id', 'status', 'source', 'origin', 'score', 'feasibility', 'priority', 'title', 'task_id', 'created_at')
        self.autonomous_proposals_tree = ttk.Treeview(
            frame, columns=columns, show='headings', height=12)
        for key, label, width in (
            ('id', '제안 ID', 65), ('status', '상태', 75),
            ('source', '출처', 115), ('origin', '초안 생성', 80),
            ('score', '검토 점수', 80), ('feasibility', '준비 상태', 125),
            ('priority', '추천 우선순위', 105), ('title', '업무 초안 제목', 270),
            ('task_id', '등록 업무', 80), ('created_at', '생성 시각 (UTC)', 150),
        ):
            self.autonomous_proposals_tree.heading(key, text=label)
            self.autonomous_proposals_tree.column(key, width=width, stretch=key == 'title')
        self.autonomous_proposals_tree.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(frame, orient='vertical',
                                  command=self.autonomous_proposals_tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.autonomous_proposals_tree.configure(yscrollcommand=scrollbar.set)
        self.autonomous_proposals_tree.bind('<<TreeviewSelect>>', self._show_task_proposal_analysis)
        self.autonomous_analysis_detail = tk.StringVar(value='제안을 선택하면 규칙 기반 분석 근거를 표시합니다.')
        self._label(panel, '', textvariable=self.autonomous_analysis_detail,
                    fg='#bfcfe5', wraplength=880, justify='left').pack(anchor='w', pady=(7, 0))
        self._label(panel, '점수는 규칙 기반 검토 순서일 뿐 실행 가능 판정이 아닙니다. '
                    '추천 우선순위는 실제 업무에 자동 적용되지 않으며, 승인 후에도 담당자·모델 지정과 수동 실행이 필요합니다.',
                    fg='#bfcfe5', wraplength=880, justify='left').pack(anchor='w', pady=(4, 0))

    def _show_task_proposal_analysis(self, event=None) -> None:
        selected = self.autonomous_proposals_tree.selection()
        if not selected:
            self.autonomous_analysis_detail.set('제안을 선택하면 규칙 기반 분석 근거를 표시합니다.')
            return
        row = self._proposal_assessment_map.get(int(selected[0]))
        if row is None:
            self.autonomous_analysis_detail.set('분석 기록이 없습니다. 재분석을 눌러주세요.')
            return
        if row['proposal_status'] != 'pending':
            self.autonomous_analysis_detail.set(
                f"제안 #{row['proposal_id']}은 현재 {row['proposal_status']} 상태입니다. "
                '아래 분석은 과거 기록이며 현재 실행 판단에 사용할 수 없습니다. ' + row['reason'])
            return
        self.autonomous_analysis_detail.set(
            f"제안 #{row['proposal_id']} · 검토 점수 {row['score']}/100 · "
            f"추천 우선순위 {row['recommended_priority']} · {row['reason']} "
            '실행 가능 판정 아님 · 관리자가 별도 승인해야 합니다.')

    def analyze_autonomous_task_proposals(self) -> None:
        try:
            report = self.store.analyze_task_proposals()
            self.refresh_autonomous_task_proposals()
            self.autonomous_proposals_feedback.set(
                f"분석 갱신 {report['evaluated']}건 · 기존 분석 유지 {report['unchanged']}건 · "
                f"출처 조건 변경 {report['stale']}건. 실제 업무 생성·실행 없음.")
        except (ValueError, PermissionError, OSError) as exc:
            self.autonomous_proposals_feedback.set('분석 실패: ' + str(exc))

    def refresh_autonomous_task_proposals(self) -> None:
        try:
            proposals = self.store.list_autonomous_task_proposals()
            self._proposal_assessment_map = {
                int(a['proposal_id']): a for a in self.store.list_task_proposal_assessments()}
            proposals.sort(key=lambda p: (
                0 if p['status'] == 'pending' else 1,
                -int(self._proposal_assessment_map.get(p['id'], {}).get('score', -1)),
                p['id']))
            tree = self.autonomous_proposals_tree
            for item in tree.get_children():
                tree.delete(item)
            labels = {'pending': '승인 대기', 'approved': '승인',
                      'rejected': '거절', 'stale': '조건 변경'}
            sources = {'active_goal': '활성 목표', 'ready_plan': '준비 계획',
                       'blocked_task': '차단 업무'}
            for p in proposals:
                assessment = self._proposal_assessment_map.get(p['id'], {})
                feasibility_labels = {
                    'needs_plan': '계획 필요', 'needs_assignment': '배정 검토 필요',
                    'needs_breakdown': '세분화 검토', 'needs_unblocking': '차단 해소 필요'}
                priority_labels = {'low': '낮음', 'normal': '보통',
                                   'high': '높음', 'urgent': '긴급'}
                tree.insert('', 'end', iid=str(p['id']), values=(
                    p['id'], labels[p['status']],
                    f"{sources[p['source_kind']]} #{p['source_id']}",
                    '로컬 AI' if p['origin'] == 'local_ai' else '고정 규칙',
                    assessment.get('score', '-') if p['status'] == 'pending' else '-',
                    feasibility_labels.get(assessment.get('feasibility'), '-') if p['status'] == 'pending' else '-',
                    priority_labels.get(assessment.get('recommended_priority'), '-') if p['status'] == 'pending' else '-', 
                    p['title'], p['approved_task_id'] or '-', p['created_at']))
            self._show_task_proposal_analysis()
        except (ValueError, PermissionError, OSError) as exc:
            self.autonomous_proposals_feedback.set('제안 조회 실패: ' + str(exc))

    def scan_autonomous_task_proposals(self) -> None:
        try:
            result = self.store.scan_autonomous_task_proposals()
            self.refresh_autonomous_task_proposals()
            self.autonomous_proposals_feedback.set(
                f"새 제안 {len(result['created_ids'])}건, 조건 변경 {result['stale_count']}건, "
                f"승인 대기 {result['pending_count']}건. 실제 업무 자동 등록 없음.")
        except (ValueError, PermissionError, OSError) as exc:
            self.autonomous_proposals_feedback.set('제안 생성 실패: ' + str(exc))

    def toggle_auto_proposal_ai(self) -> None:
        """Explicit per-login consent for optional offline chief model drafting."""
        if self._auto_proposal_ai_enabled:
            self._auto_proposal_ai_enabled = False
            self._auto_proposal_ai_cancel.set()
            self.auto_proposal_ai_button.configure(text='로컬 총괄 AI 자동 초안 켜기 (선택)')
            self.autonomous_proposals_feedback.set('로컬 AI 자동 초안을 중지했습니다.')
            return
        try:
            if (self._auto_proposal_ai_thread is not None
                    and self._auto_proposal_ai_thread.is_alive()):
                raise ValueError('이전 로컬 모델 작업이 종료된 후 다시 켜세요.')
            chief = self.store.read_chief_profile()
            if chief is None or chief['lifecycle'] != 'draft' or chief['model_id'] is None:
                raise ValueError('활성 총괄 AI와 로컬 모델 배정이 필요합니다.')
            self._auto_proposal_ai_enabled = True
            self._auto_proposal_ai_cancel = threading.Event()
            while not self._auto_proposal_ai_queue.empty():
                try:
                    self._auto_proposal_ai_queue.get_nowait()
                except queue.Empty:
                    break
            self.auto_proposal_ai_button.configure(text='로컬 총괄 AI 자동 초안 끄기')
            self.autonomous_proposals_feedback.set('로컬 AI 자동 초안 동의: 실행 대기 중')
            self._kick_auto_proposal_ai()
        except (ValueError, PermissionError, OSError) as exc:
            self.autonomous_proposals_feedback.set('AI 자동 초안 활성화 실패: ' + str(exc))

    def _kick_auto_proposal_ai(self) -> None:
        if not self._auto_proposal_ai_enabled or not self.store.is_authenticated:
            return
        if self._auto_proposal_ai_thread is not None and self._auto_proposal_ai_thread.is_alive():
            return
        pending = next((p for p in self.store.list_autonomous_task_proposals(limit=200)
                        if p['status'] == 'pending' and p['origin'] == 'rule'), None)
        if pending is None:
            return
        generation = self._session_generation
        cancel = self._auto_proposal_ai_cancel
        def worker() -> None:
            try:
                from desktop.autonomous_task_ai import generate_local_ai_proposal
                title, description = generate_local_ai_proposal(
                    self.store, pending, timeout=60, cancel=cancel)
                if cancel.is_set():
                    raise InterruptedError('로컬 AI 초안 생성을 취소했습니다.')
                saved = self.store.save_local_ai_task_proposal(
                    int(pending['id']), title, description)
                self._auto_proposal_ai_queue.put((generation, None,
                    f"제안 #{pending['id']} 로컬 AI 초안 저장 완료." if saved else
                    f"제안 #{pending['id']} 출처가 바뀌어 저장하지 않았습니다."))
            except (ValueError, PermissionError, OSError, RuntimeError,
                    InterruptedError, TimeoutError) as exc:
                self._auto_proposal_ai_queue.put((generation, str(exc), ''))
        self._auto_proposal_ai_thread = threading.Thread(target=worker, daemon=True)
        self._auto_proposal_ai_thread.start()
        self.root.after(100, lambda: self._poll_auto_proposal_ai(generation))

    def _poll_auto_proposal_ai(self, generation: int) -> None:
        if generation != self._session_generation or not self.store.is_authenticated:
            return
        while True:
            try:
                item_generation, error, message = self._auto_proposal_ai_queue.get_nowait()
                if item_generation == generation:
                    break  # discard completed messages from a previous login
            except queue.Empty:
                if self._auto_proposal_ai_thread is not None and self._auto_proposal_ai_thread.is_alive():
                    self.root.after(100, lambda: self._poll_auto_proposal_ai(generation))
                return
        if error:
            self._auto_proposal_ai_enabled = False
            self._auto_proposal_ai_cancel.set()
            self.auto_proposal_ai_button.configure(text='로컬 총괄 AI 자동 초안 켜기 (선택)')
            self.autonomous_proposals_feedback.set('로컬 AI 초안 실패 (자동 중지): ' + error)
        else:
            self.refresh_autonomous_task_proposals()
            self.autonomous_proposals_feedback.set(message)

    def _selected_autonomous_proposal_id(self) -> int:
        selection = self.autonomous_proposals_tree.selection()
        if not selection:
            raise ValueError('업무 제안을 먼저 선택하세요.')
        return int(selection[0])

    def approve_autonomous_task_proposal(self) -> None:
        try:
            proposal_id = self._selected_autonomous_proposal_id()
            if not messagebox.askyesno('업무 생성 승인',
                    f'제안 #{proposal_id}를 실제 할 일(todo)로 등록하시겠습니까?\n'
                    '등록만 하며 AI 실행은 시작하지 않습니다.', parent=self.root):
                return
            task_id = self.store.approve_autonomous_task_proposal(proposal_id)
            self.refresh_autonomous_task_proposals()
            self.autonomous_proposals_feedback.set(
                f'업무 #{task_id} 등록 완료 (실행 없음).' if task_id is not None
                else '제안의 출처 조건이 바뀌어 등록하지 않았습니다.')
        except (ValueError, PermissionError, OSError) as exc:
            self.autonomous_proposals_feedback.set('업무 등록 실패: ' + str(exc))

    def reject_autonomous_task_proposal(self) -> None:
        try:
            proposal_id = self._selected_autonomous_proposal_id()
            if not messagebox.askyesno('제안 거절',
                    f'제안 #{proposal_id}를 거절하시겠습니까? 같은 출처는 자동 재제안하지 않습니다.',
                    parent=self.root):
                return
            self.store.reject_autonomous_task_proposal(proposal_id)
            self.refresh_autonomous_task_proposals()
            self.autonomous_proposals_feedback.set(f'제안 #{proposal_id} 거절 완료.')
        except (ValueError, PermissionError, OSError) as exc:
            self.autonomous_proposals_feedback.set('제안 거절 실패: ' + str(exc))

    def _update_company_detection_view(self, report: dict[str, object]) -> None:
        severity_labels = {'ok': '정상', 'attention': '확인 필요', 'critical': '긴급 확인',
                           'candidate': '검토 후보'}
        self.detection_summary.set(
            f"문제 신호 {report['problem_types']}종 · 내부 기회 후보 {report['opportunity_types']}종 "
            f"· 문제 수준: {severity_labels[report['severity']]} (자동 조치 없음)")
        for item in self.detection_signals.get_children():
            self.detection_signals.delete(item)
        for signal in report['signals']:
            self.detection_signals.insert('', 'end', values=(
                '문제' if signal['kind'] == 'problem' else '내부 기회',
                severity_labels[signal['severity']], signal['label'], signal['count'],
                ', '.join(str(x) for x in signal['sample_ids']) or '-'))
        for item in self.detection_history.get_children():
            self.detection_history.delete(item)
        for row in self.store.list_company_detection_checks():
            summary = ', '.join(f"{x['code']} {x['count']}" for x in row['signals']) or '신호 없음'
            self.detection_history.insert('', 'end', values=(
                row['id'], row['checked_at'], severity_labels[row['severity']], summary))

    def refresh_company_detection_view(self) -> None:
        try:
            self._update_company_detection_view(self.store.read_company_signals())
        except (ValueError, PermissionError, OSError) as exc:
            self.detection_feedback.set('감지 조회 실패: ' + str(exc))

    def manual_company_detection(self) -> None:
        try:
            report = self.store.check_company_signals(force=True)
            self._update_company_detection_view(report)
            self.detection_feedback.set(
                f"수동 감지 #{report['check_id']} 저장 완료. 후보를 실제 사업 기회로 확정하지 않습니다.")
        except (ValueError, PermissionError, OSError) as exc:
            self.detection_feedback.set('감지 실패: ' + str(exc))

    def _event_task_panel(self, parent: tk.Frame) -> None:
        self.event_summary = tk.StringVar()
        self.event_feedback = tk.StringVar(value='로컬 이벤트만 등록합니다. AI 자동 실행 없음.')
        tk.Label(parent, text='로컬 이벤트 제목', bg='#121c2d', fg='white').pack(anchor='w')
        tk.Entry(parent, textvariable=self.event_summary).pack(fill='x', pady=5)
        tk.Button(parent, text='수동 알림 이벤트 등록', command=self._submit_event_task).pack(anchor='w')
        tk.Button(parent, text='대기 이벤트를 업무로 변환', command=self._dispatch_event_tasks).pack(anchor='w')
        self.event_tree = ttk.Treeview(parent, columns=('id','kind','summary','status','task'), show='headings', height=8)
        for key in ('id','kind','summary','status','task'):
            self.event_tree.heading(key, text=key)
        self.event_tree.pack(fill='both', expand=True)
        tk.Label(parent, textvariable=self.event_feedback, bg='#121c2d', fg='white').pack(anchor='w')
        self.refresh_local_events()

    def refresh_local_events(self) -> None:
        if not hasattr(self, 'event_tree') or not self.store.is_authenticated:
            return
        for item in self.event_tree.get_children():
            self.event_tree.delete(item)
        for item in self.store.list_local_events():
            self.event_tree.insert('', 'end', values=(item['id'],item['event_type'],item['summary'],item['status'],item['task_id'] or ''))

    def _submit_event_task(self) -> None:
        try:
            import uuid
            self.store.submit_local_event(uuid.uuid4().hex, 'manual_alert', self.event_summary.get())
            self.event_feedback.set('로컬 이벤트 등록 완료')
            self.refresh_local_events()
        except (ValueError, PermissionError) as exc:
            self.event_feedback.set(str(exc))

    def _dispatch_event_tasks(self) -> None:
        try:
            created = self.store.dispatch_local_events()
            self.event_feedback.set(f'업무 {len(created)}개 생성. AI 실행 없음.')
            self.refresh_local_events()
        except (ValueError, PermissionError) as exc:
            self.event_feedback.set(str(exc))

    def _recurring_scheduler(self, parent: tk.Frame) -> None:
        self._label(parent, '정기 업무 스케줄러 · 로컬 업무 등록만 수행하며 AI 실행은 하지 않습니다.').pack(anchor='w')
        self.recurring_title = tk.StringVar()
        self.recurring_minutes = tk.StringVar(value='1440')
        self.recurring_feedback = tk.StringVar(value='기본값: 비활성. 관리자가 활성화해야 작동합니다.')
        tk.Entry(parent, textvariable=self.recurring_title).pack(fill='x', pady=5)
        self._label(parent, '반복 간격(분, 5~10080)').pack(anchor='w')
        tk.Entry(parent, textvariable=self.recurring_minutes).pack(fill='x', pady=5)
        tk.Button(parent, text='비활성 일정 추가', command=self._add_recurring).pack(anchor='w')
        self.recurring_tree = ttk.Treeview(parent, columns=('id','title','minutes','enabled','due'), show='headings', height=8)
        for key, label in [('id','번호'),('title','업무 제목'),('minutes','간격(분)'),('enabled','활성'),('due','다음 실행(Unix 초)')]:
            self.recurring_tree.heading(key, text=label)
            self.recurring_tree.column(key, width=120)
        self.recurring_tree.pack(fill='both', expand=True, pady=8)
        controls = tk.Frame(parent, bg='#121c2d')
        controls.pack(anchor='w')
        tk.Button(controls, text='선택 일정 활성화', command=lambda: self._toggle_recurring(True)).pack(side='left')
        tk.Button(controls, text='선택 일정 비활성화', command=lambda: self._toggle_recurring(False)).pack(side='left')
        tk.Button(controls, text='지금 기한 검사', command=self._run_recurring).pack(side='left')
        self._label(parent, '', textvariable=self.recurring_feedback).pack(anchor='w')
        self.refresh_recurring_schedules()

    def refresh_recurring_schedules(self) -> None:
        if not hasattr(self, 'recurring_tree') or not self.store.is_authenticated:
            return
        for item in self.recurring_tree.get_children():
            self.recurring_tree.delete(item)
        for item in self.store.list_recurring_schedules():
            self.recurring_tree.insert('', 'end', values=(item['id'],item['title'],item['interval_minutes'], '예' if item['enabled'] else '아니오',item['next_due']))

    def _add_recurring(self) -> None:
        try:
            self.store.add_recurring_schedule(self.recurring_title.get(), interval_minutes=int(self.recurring_minutes.get()))
            self.recurring_feedback.set('비활성 일정이 저장되었습니다.')
            self.refresh_recurring_schedules()
        except (ValueError, PermissionError) as exc:
            self.recurring_feedback.set(str(exc))

    def _toggle_recurring(self, enabled: bool) -> None:
        selection = self.recurring_tree.selection()
        if not selection:
            self.recurring_feedback.set('일정을 선택하세요.')
            return
        try:
            self.store.set_recurring_schedule_enabled(int(self.recurring_tree.item(selection[0], 'values')[0]), enabled)
            self.refresh_recurring_schedules()
        except (ValueError, PermissionError) as exc:
            self.recurring_feedback.set(str(exc))

    def _run_recurring(self) -> None:
        try:
            created = self.store.run_due_recurring_schedules()
            self.recurring_feedback.set(f'새 업무 {len(created)}개 등록 (AI 실행 없음)')
            self.refresh_recurring_schedules()
        except (ValueError, PermissionError) as exc:
            self.recurring_feedback.set(str(exc))

    def _health_timer_tick(self, generation: int) -> None:
        self._health_timer_id = None
        if generation != self._session_generation or not self.store.is_authenticated:
            return
        try:
            report = self.store.check_company_health()
            self._update_company_health_view(report)
        except (ValueError, PermissionError, OSError) as exc:
            self.health_feedback.set('자동 점검 실패: ' + str(exc))
        # Detection has an independent failure boundary: a failed health
        # summary must not prevent a detection check, and vice versa.
        try:
            report = self.store.check_company_signals()
            self._update_company_detection_view(report)
        except (ValueError, PermissionError, OSError) as exc:
            self.detection_feedback.set('자동 감지 실패: ' + str(exc))
        # Draft generation is local, bounded, idempotent and never executes AI
        # or creates real tasks. The owner must approve each draft separately.
        try:
            self.store.scan_autonomous_task_proposals()
            self.refresh_autonomous_task_proposals()
            self._kick_auto_proposal_ai()
        except (ValueError, PermissionError, OSError) as exc:
            self.autonomous_proposals_feedback.set('자동 제안 실패: ' + str(exc))
        try:
            self.store.run_due_recurring_schedules()
            self.refresh_recurring_schedules()
        except (ValueError, PermissionError, OSError) as exc:
            self.recurring_feedback.set('정기 업무 확인 실패: ' + str(exc))
        if generation == self._session_generation and self.store.is_authenticated:
            self._health_timer_id = self.root.after(
                300_000, lambda: self._health_timer_tick(generation))

    def _update_company_health_view(self, report: dict[str, object]) -> None:
        labels = {'ok': '정상', 'attention': '확인 필요', 'critical': '긴급 확인'}
        metrics = report['metrics']
        issues = report['issues']
        self.health_summary.set(
            f"판정: {labels[report['severity']]} · 전체 업무 {metrics['tasks_total']}개 · "
            f"진행 중 {metrics['in_progress']}개 · 완료 {metrics['done']}개\n" +
            ('문제 없음' if not issues else ' / '.join(
                f"{issue['label']} {issue['count']}건" for issue in issues)))
        for item in self.health_history.get_children():
            self.health_history.delete(item)
        for item in self.store.list_company_health_checks():
            self.health_history.insert('', 'end', values=(
                item['id'], item['checked_at'], labels[item['severity']],
                ', '.join(f"{x['label']} {x['count']}" for x in item['issues']) or '문제 없음'))

    def refresh_company_health_view(self) -> None:
        try:
            self._update_company_health_view(self.store.read_company_health())
        except (ValueError, PermissionError, OSError) as exc:
            self.health_feedback.set('조회 실패: ' + str(exc))

    def manual_company_health_check(self) -> None:
        try:
            report = self.store.check_company_health(force=True)
            self._update_company_health_view(report)
            self.health_feedback.set(f"수동 점검 #{report['check_id']} 저장 완료. "
                                     '문제의 조치와 AI 실행은 자동으로 수행하지 않습니다.')
        except (ValueError, PermissionError, OSError) as exc:
            self.health_feedback.set('점검 실패: ' + str(exc))

    def _chief_tasks(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        panel=self._panel(parent)
        panel.pack(fill='both',expand=True)
        self._label(panel,'총괄 AI 지시 · 업무 결과 회수',size=18,weight='bold').pack(anchor='w')
        self._label(panel,'총괄 AI가 로컬 모델로 지시 초안을 작성해도 관리자 승인 전에는 직원에게 전달되지 않습니다. '
                    '실제 업무 실행·결과물 저장은 기존 탭에서 관리자가 직접 수행합니다. '
                    '검토 보고서 승인도 업무 완료를 뜻하지 않습니다.',
                    fg='#f7cb92',wraplength=840,size=9).pack(anchor='w',pady=(5,9))
        self.chief_task_choice=tk.StringVar(value='')
        self.chief_task_objective=tk.StringVar(value='')
        self.chief_task_artifact_choice=tk.StringVar(value='')
        self.chief_task_feedback=tk.StringVar(value='업무를 선택하고 지시 초안을 요청하세요.')
        self.chief_task_order_id=None
        self.chief_task_report_id=None
        self._chief_task_queue=queue.Queue()
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=3)
        self._label(row,'업무').pack(side='left',padx=(0,6))
        self.chief_task_combo=ttk.Combobox(row,textvariable=self.chief_task_choice,state='readonly',width=65)
        self.chief_task_combo.pack(side='left',fill='x',expand=True)
        self.chief_task_combo.bind('<<ComboboxSelected>>',self.load_chief_task)
        tk.Button(row,text='새로고침',command=self.refresh_chief_task_choices).pack(side='left',padx=5)
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=3)
        self._label(row,'관리자 목표').pack(side='left',padx=(0,6))
        tk.Entry(row,textvariable=self.chief_task_objective).pack(side='left',fill='x',expand=True)
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=(5,3))
        self.chief_task_propose_button=tk.Button(row,text='총괄 AI 지시 초안 요청',command=self.propose_chief_task)
        self.chief_task_propose_button.pack(side='left',padx=(0,7))
        self.chief_task_approve_button=tk.Button(row,text='지시 승인·저장',command=self.approve_chief_task)
        self.chief_task_approve_button.pack(side='left',padx=(0,7))
        tk.Button(row,text='모델 응답 중단',command=self.cancel_local_model).pack(side='left')
        self._label(panel,'승인할 지시 (최대 600자, 승인 후 변경 불가)').pack(anchor='w',pady=(5,2))
        self.chief_task_instruction=tk.Text(panel,height=4,wrap='word')
        self.chief_task_instruction.pack(fill='x',pady=(0,8))
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=3)
        self._label(row,'저장된 업무 결과물').pack(side='left',padx=(0,6))
        self.chief_task_artifact_combo=ttk.Combobox(row,textvariable=self.chief_task_artifact_choice,
                                                    state='readonly',width=55)
        self.chief_task_artifact_combo.pack(side='left',fill='x',expand=True)
        self.chief_task_artifact_combo.bind('<<ComboboxSelected>>',self.load_chief_task_report)
        self.chief_task_collect_button=tk.Button(row,text='총괄 AI에게 결과 회수·검토 요청',
                                                 command=self.collect_chief_task)
        self.chief_task_collect_button.pack(side='left',padx=5)
        self._label(panel,'총괄 AI 회수 검토 의견 (명시적으로 저장·검토)').pack(anchor='w',pady=(5,2))
        self.chief_task_report=tk.Text(panel,height=5,wrap='word')
        self.chief_task_report.pack(fill='both',expand=True,pady=(0,5))
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=(2,7))
        self.chief_task_save_report_button=tk.Button(row,text='회수 보고서 저장',command=self.save_chief_task_report)
        self.chief_task_save_report_button.pack(side='left',padx=(0,7))
        tk.Button(row,text='보고서 승인',command=lambda:self.review_chief_task_report('accepted')).pack(side='left',padx=(0,7))
        tk.Button(row,text='보고서 반려',command=lambda:self.review_chief_task_report('rejected')).pack(side='left')
        self._label(panel,'',textvariable=self.chief_task_feedback,fg='#9cdbbb',wraplength=840).pack(anchor='w')
        self.refresh_chief_task_choices()

    def refresh_chief_task_choices(self) -> None:
        previous=getattr(self,'chief_task_map',{}).get(self.chief_task_choice.get())
        self.chief_task_map={f"{t['id']} · [{t['status']}] {t['title']}":int(t['id'])
                             for t in self.store.list_tasks()}
        self.chief_task_combo['values']=list(self.chief_task_map)
        self.chief_task_choice.set(next((k for k,v in self.chief_task_map.items() if v==previous),'') )
        self.load_chief_task()

    def _chief_selected_task(self) -> int:
        if self.chief_task_choice.get() not in self.chief_task_map:
            raise ValueError('먼저 업무를 선택하세요.')
        return self.chief_task_map[self.chief_task_choice.get()]

    def load_chief_task(self,event=None) -> None:
        self.chief_task_order_id=None
        self.chief_task_report_id=None
        self.chief_task_instruction.configure(state='normal')
        self.chief_task_instruction.delete('1.0','end')
        self.chief_task_report.configure(state='normal')
        self.chief_task_report.delete('1.0','end')
        self.chief_task_artifact_map={}
        self.chief_task_artifact_choice.set('')
        self.chief_task_artifact_combo['values']=[]
        if not self.chief_task_choice.get():
            return
        task_id=self._chief_selected_task()
        order=self.store.read_chief_task_order(task_id)
        if order:
            self.chief_task_order_id=order['id']
            self.chief_task_instruction.insert('1.0',order['instruction'])
            self.chief_task_instruction.configure(state='disabled')
            self.chief_task_feedback.set(f"승인된 지시 #{order['id']} · 실제 실행은 'AI 업무 실행' 탭에서 직접 시작하세요.")
        else:
            self.chief_task_instruction.configure(state='normal')
            self.chief_task_feedback.set('총괄 AI 지시 초안을 요청하고 관리자가 직접 승인하세요.')
        for a in self.store.list_task_artifacts(task_id):
            try:
                ctx=self.store.chief_task_report_context(int(a['id']))
            except ValueError:
                continue
            if ctx['task_id']==task_id:
                self.chief_task_artifact_map[f"{a['id']} · {a['title']}"]=int(a['id'])
        self.chief_task_artifact_combo['values']=list(self.chief_task_artifact_map)

    def _chief_selected_artifact(self) -> int:
        selected=self.chief_task_artifact_choice.get()
        if selected not in self.chief_task_artifact_map:
            raise ValueError('지시 실행에서 저장된 결과물을 선택하세요.')
        return self.chief_task_artifact_map[selected]

    def _chief_task_async(self, mode: str, identifier: int, objective: str = '') -> None:
        if self._model_running or getattr(self,'_task_runs_live',{}):
            raise ValueError('다른 로컬 모델이 실행 중입니다. 완료 후 요청하세요.')
        generation=self._session_generation
        cancel=threading.Event()
        self._model_running=True
        self._model_cancel=cancel
        self.chief_task_propose_button.configure(state='disabled')
        self.chief_task_collect_button.configure(state='disabled')
        outbound=self._chief_task_queue
        def worker():
            try:
                if mode=='propose':
                    result=propose_chief_task_order(self.store,identifier,objective,timeout=60,cancel=cancel)
                else:
                    result=collect_chief_task_result(self.store,identifier,timeout=60,cancel=cancel)
                outbound.put((generation,mode,identifier,True,result))
            except (ValueError,PermissionError,RuntimeError,OSError,TimeoutError,InterruptedError) as exc:
                outbound.put((generation,mode,identifier,False,str(exc)))
        self._model_thread=threading.Thread(target=worker,daemon=True)
        self._model_thread.start()
        self.root.after(100,lambda:self._poll_chief_task(generation,outbound))

    def _poll_chief_task(self,generation:int,outbound:queue.Queue) -> None:
        if generation!=self._session_generation or not self.store.is_authenticated:
            return
        try:
            _,mode,identifier,ok,result=outbound.get_nowait()
        except queue.Empty:
            if self.root.winfo_exists():
                self.root.after(100,lambda:self._poll_chief_task(generation,outbound))
            return
        self._model_running=False
        self._model_cancel=None
        self._model_thread=None
        self.chief_task_propose_button.configure(state='normal')
        self.chief_task_collect_button.configure(state='normal')
        # Do not show a previous task's response after user switches selection.
        still_selected=(self.chief_task_map.get(self.chief_task_choice.get())==identifier
                        if mode=='propose' else self.chief_task_artifact_map.get(
                            self.chief_task_artifact_choice.get())==identifier)
        if ok and still_selected:
            target=self.chief_task_instruction if mode=='propose' else self.chief_task_report
            target.configure(state='normal')
            target.delete('1.0','end')
            target.insert('1.0',result)
            self.chief_task_feedback.set('로컬 총괄 AI 응답 완료. 내용을 검토한 후 관리자 버튼으로 승인·저장하세요.')
        else:
            self.chief_task_feedback.set('응답을 표시하지 않았습니다.' if ok else '모델 호출 실패·취소: '+result)

    def propose_chief_task(self) -> None:
        try:
            task_id=self._chief_selected_task()
            if self.chief_task_order_id is not None:
                raise ValueError('이미 승인된 지시가 있습니다.')
            self._chief_task_async('propose',task_id,self.chief_task_objective.get())
            self.chief_task_feedback.set('총괄 AI가 오프라인 지시 초안을 작성 중입니다.')
        except (ValueError,PermissionError) as exc:
            self.chief_task_feedback.set('초안 요청 실패: '+str(exc))

    def approve_chief_task(self) -> None:
        try:
            if self._model_running:
                raise ValueError('모델 응답이 끝난 뒤 승인하세요.')
            task_id=self._chief_selected_task()
            instruction=self.chief_task_instruction.get('1.0','end-1c')
            if not messagebox.askyesno('총괄 AI 지시 승인',
                '이 지시를 로컬 SQLite에 저장하고, 관리자가 해당 업무를 실행할 때 직원 모델에 전달합니다. '
                '승인 후 지시는 변경할 수 없습니다. 승인하시겠습니까?',parent=self.root):
                return
            order_id=self.store.approve_chief_task_order(task_id,instruction)
            self.load_chief_task()
            self.chief_task_feedback.set(f'지시 #{order_id} 승인 완료. 업무 실행은 별도 탭에서 수동으로 시작하세요.')
        except (ValueError,PermissionError) as exc:
            self.chief_task_feedback.set('승인 실패: '+str(exc))

    def collect_chief_task(self) -> None:
        try:
            artifact_id=self._chief_selected_artifact()
            self._chief_task_async('collect',artifact_id)
            self.chief_task_feedback.set('총괄 AI가 저장된 결과물을 오프라인 검토 중입니다.')
        except (ValueError,PermissionError) as exc:
            self.chief_task_feedback.set('회수 실패: '+str(exc))

    def load_chief_task_report(self,event=None) -> None:
        self.chief_task_report_id=None
        self.chief_task_report.configure(state='normal')
        self.chief_task_report.delete('1.0','end')
        try:
            artifact_id=self._chief_selected_artifact()
        except ValueError:
            return
        report=self.store.find_chief_task_report(artifact_id)
        if report:
            self.chief_task_report_id=report['id']
            self.chief_task_report.insert('1.0',report['body'])
            self.chief_task_report.configure(state='disabled')
            self.chief_task_feedback.set(f"회수 보고서 #{report['id']} · 관리자 검토 {report['owner_decision']}")

    def save_chief_task_report(self) -> None:
        try:
            if self._model_running:
                raise ValueError('모델 실행이 끝난 뒤 저장하세요.')
            artifact_id=self._chief_selected_artifact()
            body=self.chief_task_report.get('1.0','end-1c')
            if not messagebox.askyesno('총괄 AI 보고서 저장','회수 의견을 영구 저장하시겠습니까? '
                    '로컬 SQLite에 평문으로 보관됩니다.',parent=self.root):
                return
            report_id=self.store.save_chief_task_report(artifact_id,body)
            self.load_chief_task_report()
            self.chief_task_feedback.set(f'회수 보고서 #{report_id} 저장 완료. 검토 승인과 업무 완료는 별개입니다.')
        except (ValueError,PermissionError) as exc:
            self.chief_task_feedback.set('보고서 저장 실패: '+str(exc))

    def review_chief_task_report(self,decision:str) -> None:
        try:
            if self.chief_task_report_id is None:
                raise ValueError('먼저 회수 보고서를 저장하세요.')
            if not messagebox.askyesno('회수 보고서 검토','보고서를 '+('승인' if decision=='accepted' else '반려')+
                    '하시겠습니까? 업무 상태는 변경되지 않습니다.',parent=self.root):
                return
            self.store.review_chief_task_report(self.chief_task_report_id,decision)
            self.load_chief_task_report()
            self.chief_task_feedback.set('관리자 검토 기록을 저장했습니다. 업무는 자동 완료되지 않습니다.')
        except (ValueError,PermissionError) as exc:
            self.chief_task_feedback.set('검토 실패: '+str(exc))

    # Stage 24: deterministic matching of local AI employee *profiles* to tasks.
    def _task_routing(self, parent: tk.Frame) -> None:
        self.store.require_permission("company:manage")
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True)
        self._label(panel, "업무 담당 AI 자동 지정", size=18, weight="bold").pack(anchor="w")
        self._label(panel, "할 일 상태의 업무만 배정합니다. 활성 직원 초안의 부서·직무와 업무량만 비교하며 AI 모델을 실행하지 않습니다.",
                    fg="#f7cb92", size=9, wraplength=830, justify="left").pack(anchor="w", pady=(4, 12))
        self.task_route_task = tk.StringVar(value="")
        self.task_route_department = tk.StringVar(value="")
        self.task_route_job = tk.StringVar(value="")
        self.task_route_feedback = tk.StringVar(value="목록에서 업무를 선택하세요.")
        self.task_route_current = tk.StringVar(value="현재 담당자: 미배정")
        form = tk.Frame(panel, bg="#1c2a40")
        form.pack(fill="x", pady=(0, 7))
        for idx,(title,variable) in enumerate((("배정할 업무",self.task_route_task),
                                                 ("필요 부서 (선택)",self.task_route_department),
                                                 ("필요 직무 (선택)",self.task_route_job))):
            self._label(form,title).grid(row=idx,column=0,sticky="w",pady=5,padx=(0,10))
            combo = ttk.Combobox(form,textvariable=variable,width=62,state="readonly")
            combo.grid(row=idx,column=1,sticky="ew",pady=5)
            if idx == 0:
                self.task_route_task_combo = combo
                combo.bind("<<ComboboxSelected>>",self.load_task_routing)
            elif idx == 1:
                self.task_route_department_combo = combo
            else:
                self.task_route_job_combo = combo
        form.columnconfigure(1,weight=1)
        bar = tk.Frame(panel,bg="#1c2a40")
        bar.pack(fill="x",pady=(6,12))
        self.task_route_save_button=tk.Button(bar,text="배정 조건 저장",command=self.save_task_routing,
                                               bg="#4c83e6",fg="white",padx=9)
        self.task_route_save_button.pack(side="left",padx=(0,7))
        self.task_route_assign_button=tk.Button(bar,text="담당 AI 자동 지정",command=self.assign_task_auto,padx=9)
        self.task_route_assign_button.pack(side="left",padx=(0,7))
        self.task_route_clear_button=tk.Button(bar,text="담당자 배정 해제",command=self.clear_task_routing_assignment,padx=9)
        self.task_route_clear_button.pack(side="left",padx=(0,7))
        tk.Button(bar,text="목록 다시 읽기",command=self.refresh_task_routing_choices).pack(side="left")
        self._label(panel,"",textvariable=self.task_route_current,fg="#9ddac1",
                    wraplength=820,justify="left").pack(anchor="w",pady=(4,8))
        self._label(panel,"담당자 배정 변경 이력",weight="bold").pack(anchor="w",pady=(3,7))
        frame=tk.Frame(panel)
        frame.pack(fill="both",expand=True)
        self.task_route_events=ttk.Treeview(frame,columns=("id","action","employee","detail"),show="headings",height=7)
        for key,title,width in (("id","기록",60),("action","변경",155),
                                ("employee","직원 ID",95),("detail","선정 근거 및 변경 이유",455)):
            self.task_route_events.heading(key,text=title)
            self.task_route_events.column(key,width=width,stretch=key=="detail")
        self.task_route_events.pack(side="left",fill="both",expand=True)
        sc=ttk.Scrollbar(frame,orient="vertical",command=self.task_route_events.yview)
        sc.pack(side="right",fill="y")
        self.task_route_events.configure(yscrollcommand=sc.set)
        self._label(panel,"",textvariable=self.task_route_feedback,fg="#9cdbbb",wraplength=820).pack(anchor="w",pady=(9,0))
        self.refresh_task_routing_choices()

    def refresh_task_routing_choices(self) -> None:
        self.store.require_permission("company:manage")
        old_task=self.task_route_task.get()
        self.task_route_task_map={f"{task['id']} · [{task['status']}] {task['title']}":int(task['id'])
                                  for task in self.store.list_tasks()}
        self.task_route_task_combo["values"]=list(self.task_route_task_map)
        self.task_route_task.set(old_task if old_task in self.task_route_task_map else "")
        self.task_route_dept_map={"":None}
        for dept in self.store.list_departments():
            self.task_route_dept_map[f"{dept['id']} · {dept['name']}"]=int(dept['id'])
        self.task_route_department_combo["values"]=list(self.task_route_dept_map)
        self.task_route_job_map={"":None}
        for job in self.store.list_designations("job"):
            self.task_route_job_map[f"{job['id']} · {job['name']}"]=int(job['id'])
        self.task_route_job_combo["values"]=list(self.task_route_job_map)
        if self.task_route_task.get():
            self.load_task_routing()
        else:
            self.task_route_department.set("")
            self.task_route_job.set("")
            self.task_route_current.set("현재 담당자: 미배정")
            for row in self.task_route_events.get_children():
                self.task_route_events.delete(row)

    def _selected_route_task(self) -> int:
        self.store.require_permission("company:manage")
        key=self.task_route_task.get()
        if key not in self.task_route_task_map:
            raise ValueError("먼저 업무를 선택하세요.")
        return self.task_route_task_map[key]

    def load_task_routing(self,event=None) -> None:
        task_id=self._selected_route_task()
        routing=self.store.read_task_routing(task_id)
        self.task_route_department.set(next((label for label,value in self.task_route_dept_map.items()
                                             if value==routing["department_id"]),""))
        self.task_route_job.set(next((label for label,value in self.task_route_job_map.items()
                                      if value==routing["job_id"]),""))
        self.task_route_current.set("현재 담당자: " +
            (f"{routing['employee_name']} (직원 #{routing['employee_id']}) · {routing['reason']}"
             if routing['employee_id'] else "미배정"))
        for row in self.task_route_events.get_children():
            self.task_route_events.delete(row)
        for record in self.store.list_task_assignment_events(task_id):
            self.task_route_events.insert("","end",values=(record["id"],record["action"],
                                          record["employee_id"] or "",record["detail"]))

    def save_task_routing(self) -> None:
        try:
            task_id=self._selected_route_task()
            dept_key=self.task_route_department.get()
            job_key=self.task_route_job.get()
            if dept_key not in self.task_route_dept_map or job_key not in self.task_route_job_map:
                raise ValueError("등록된 부서와 직무만 선택하세요.")
            self.store.save_task_requirements(task_id,self.task_route_dept_map[dept_key],
                                               self.task_route_job_map[job_key])
            self.load_task_routing()
            self.task_route_feedback.set("업무 배정 조건을 저장했습니다. 조건 변경 시 이전 담당자를 해제합니다.")
        except (ValueError,PermissionError) as exc:
            self.task_route_feedback.set(f"조건 저장 실패: {exc}")

    def assign_task_auto(self) -> None:
        try:
            task_id=self._selected_route_task()
            assigned=self.store.auto_assign_task(task_id)
            self.load_task_routing()
            self.task_route_feedback.set(f"{assigned['employee_name']} 배정 {'완료' if assigned['changed'] else '유지'}. "
                                         "실제 AI 실행·권한 부여는 하지 않았습니다.")
        except (ValueError,PermissionError) as exc:
            self.task_route_feedback.set(f"자동 배정 실패: {exc}")

    def clear_task_routing_assignment(self) -> None:
        try:
            task_id=self._selected_route_task()
            self.store.clear_task_assignment(task_id)
            self.load_task_routing()
            self.task_route_feedback.set("담당자 배정을 해제하고 이력을 저장했습니다.")
        except (ValueError,PermissionError) as exc:
            self.task_route_feedback.set(f"배정 해제 실패: {exc}")

    def refresh(self) -> None:
        try:
            result = self.store.health()
            self.status_text.set(f"정상 · {result['storage']}   |   {result['database']}")
        except Exception as error:
            self.status_text.set(f"데이터베이스 오류: {error}")
            messagebox.showerror("AIWACK 저장 오류", str(error), parent=self.root)

    def save_note(self) -> None:
        try:
            self.store.save_note(self.note.get())
            self.feedback.set("저장 완료. 프로그램을 종료했다가 다시 실행해도 메모가 남아야 합니다.")
        except Exception as error:
            self.feedback.set(f"저장 실패: {error}")
            messagebox.showerror("저장 실패", str(error), parent=self.root)

    def reload_note(self) -> None:
        try:
            self.note.set(self.store.read_note())
            self.feedback.set("로컬 저장 파일에서 메모를 다시 읽었습니다.")
        except Exception as error:
            self.feedback.set(f"읽기 실패: {error}")
            messagebox.showerror("읽기 실패", str(error), parent=self.root)


    def _task_queue_panel(self, parent: tk.Frame) -> None:
        self.queue_task_id = tk.StringVar()
        self.queue_feedback = tk.StringVar(value='수동 처리 대기열 · AI 자동 실행 없음')
        tk.Label(parent, text='등록할 업무 ID', bg='#121c2d', fg='white').pack(anchor='w')
        tk.Entry(parent, textvariable=self.queue_task_id).pack(fill='x')
        tk.Button(parent, text='업무 대기열 등록', command=self._enqueue_selected_task).pack(anchor='w')
        tk.Button(parent, text='다음 실행 가능 업무 수동 선택', command=self._claim_queue_task).pack(anchor='w')
        self.queue_tree=ttk.Treeview(parent, columns=('id','task','title','state','attempts','due'),show='headings',height=8)
        for key in ('id','task','title','state','attempts','due'):
            self.queue_tree.heading(key,text=key)
        self.queue_tree.pack(fill='both',expand=True)
        controls=tk.Frame(parent,bg='#121c2d')
        controls.pack(anchor='w')
        tk.Button(controls,text='선택 항목 성공 처리',command=lambda:self._resolve_queue(True)).pack(side='left')
        tk.Button(controls,text='선택 항목 실패·재시도',command=lambda:self._resolve_queue(False)).pack(side='left')
        tk.Button(controls,text='중단 항목 수동 복구',command=self._recover_queue).pack(side='left')
        tk.Button(controls,text='새로고침',command=self.refresh_task_queue).pack(side='left')
        tk.Label(parent,textvariable=self.queue_feedback,bg='#121c2d',fg='white').pack(anchor='w')
        self.refresh_task_queue()

    def refresh_task_queue(self) -> None:
        if not hasattr(self,'queue_tree') or not self.store.is_authenticated:
            return
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        for item in self.store.list_queued_tasks():
            self.queue_tree.insert('', 'end',values=(item['id'],item['task_id'],item['title'],item['state'],item['attempts'],item['next_attempt_at']))

    def _enqueue_selected_task(self) -> None:
        try:
            result=self.store.enqueue_task(int(self.queue_task_id.get()))
            self.queue_feedback.set(f'대기열 #{result} 등록 또는 기존 항목 확인')
            self.refresh_task_queue()
        except (ValueError,PermissionError) as exc:
            self.queue_feedback.set(str(exc))

    def _claim_queue_task(self) -> None:
        try:
            item=self.store.claim_queued_task()
            self.queue_feedback.set(f'수동 선택: {item}' if item else '실행 가능한 업무 없음')
            self.refresh_task_queue()
        except (ValueError,PermissionError) as exc:
            self.queue_feedback.set(str(exc))

    def _recover_queue(self) -> None:
        from tkinter import messagebox
        selection = self.queue_tree.selection()
        if not selection:
            self.queue_feedback.set('복구할 항목을 선택하세요.')
            return
        if not messagebox.askyesno('중단 업무 복구', '이전 작업 프로세스가 완전히 종료되었고 외부 부작용을 확인했습니까?\n중복 실행 위험이 있습니다.'):
            return
        try:
            queue_id = int(self.queue_tree.item(selection[0], 'values')[0])
            state = self.store.recover_queued_task(queue_id)
            self.queue_feedback.set(f'복구 기록 #{queue_id}: {state}')
            self.refresh_task_queue()
        except (ValueError, PermissionError) as exc:
            self.queue_feedback.set(str(exc))

    def _resolve_queue(self, success: bool) -> None:
        try:
            selection=self.queue_tree.selection()
            if not selection:
                raise ValueError('항목을 선택하세요.')
            queue_id=int(self.queue_tree.item(selection[0],'values')[0])
            state=self.store.resolve_queued_task(queue_id,success,'' if success else '관리자 수동 실패 기록')
            self.queue_feedback.set(f'대기열 #{queue_id}: {state}')
            self.refresh_task_queue()
        except (ValueError,PermissionError) as exc:
            self.queue_feedback.set(str(exc))

    def _direct_messages_panel(self, parent: tk.Frame) -> None:
        self._label(parent, "직원 개인 메시지 (관리자 수동 등록 · 로컬 저장)", size=16).pack(anchor="w")
        form = tk.Frame(parent, bg="#121c2d")
        form.pack(fill="x", pady=10)
        self.dm_sender = tk.StringVar()
        self.dm_recipient = tk.StringVar()
        self.dm_subject = tk.StringVar()
        self.dm_feedback = tk.StringVar()
        for label, variable in (("발신 직원 ID",self.dm_sender),("수신 직원 ID",self.dm_recipient),("제목",self.dm_subject)):
            tk.Label(form,text=label,bg="#121c2d",fg="white").pack(anchor="w")
            tk.Entry(form,textvariable=variable).pack(fill="x")
        tk.Label(form,text="내용",bg="#121c2d",fg="white").pack(anchor="w")
        self.dm_body=tk.Text(form,height=3)
        self.dm_body.pack(fill="x")
        buttons=tk.Frame(parent,bg="#121c2d")
        buttons.pack(fill="x")
        tk.Button(buttons,text="메시지 기록",command=self._send_direct_message).pack(side="left")
        tk.Button(buttons,text="목록 새로고침",command=self._refresh_direct_messages).pack(side="left")
        tk.Button(buttons,text="선택 읽음 처리",command=self._read_direct_message).pack(side="left")
        tk.Label(parent,textvariable=self.dm_feedback,bg="#121c2d",fg="white").pack(anchor="w")
        self.dm_tree=ttk.Treeview(parent,columns=("id","from","to","subject","read"),show="headings",height=9)
        for col in ("id","from","to","subject","read"):
            self.dm_tree.heading(col,text=col)
        self.dm_tree.pack(fill="both",expand=True)
        self._refresh_direct_messages()

    def _send_direct_message(self) -> None:
        try:
            msg_id=self.store.send_direct_message(int(self.dm_sender.get()),int(self.dm_recipient.get()),self.dm_subject.get(),self.dm_body.get("1.0","end-1c"))
            self.dm_feedback.set(f"로컬 메시지 #{msg_id} 저장")
            self._refresh_direct_messages()
        except (ValueError,PermissionError) as exc:
            self.dm_feedback.set(str(exc))

    def _refresh_direct_messages(self) -> None:
        for item in self.dm_tree.get_children():
            self.dm_tree.delete(item)
        for m in self.store.list_direct_messages():
            self.dm_tree.insert("","end",values=(m["id"],m["sender_id"],m["recipient_id"],m["subject"],"읽음" if m["read_at"] else "안 읽음"))

    def _read_direct_message(self) -> None:
        selected=self.dm_tree.selection()
        if not selected:
            self.dm_feedback.set("메시지를 선택하세요.")
            return
        message_id=int(self.dm_tree.item(selected[0],"values")[0])
        self.store.mark_direct_message_read(message_id)
        self._refresh_direct_messages()

    def _department_chat_panel(self, parent: tk.Frame) -> None:
        self._label(parent, "부서별 협업 대화 (관리자 수동 등록 · 부서별 로컬 기록)", size=16).pack(anchor="w")
        self._label(parent, "발신 직원은 해당 부서에 소속된 활성 직원이어야 합니다. 자동 AI 대화는 아직 지원하지 않습니다.", fg="#bfcfe5", bg="#121c2d").pack(anchor="w", pady=5)
        form = tk.Frame(parent, bg="#121c2d")
        form.pack(fill="x", pady=6)
        self.department_chat_department = tk.StringVar()
        self.department_chat_sender = tk.StringVar()
        self.department_chat_feedback = tk.StringVar()
        for title, variable in (("부서 ID", self.department_chat_department), ("발신 직원 ID", self.department_chat_sender)):
            tk.Label(form, text=title, bg="#121c2d", fg="white").pack(anchor="w")
            tk.Entry(form, textvariable=variable).pack(fill="x")
        tk.Label(form, text="내용 (최대 4000자)", bg="#121c2d", fg="white").pack(anchor="w")
        self.department_chat_body = tk.Text(form, height=3)
        self.department_chat_body.pack(fill="x")
        buttons = tk.Frame(parent, bg="#121c2d")
        buttons.pack(fill="x")
        self.department_chat_send_button = tk.Button(buttons, text="부서 대화 기록", command=self._send_department_chat)
        self.department_chat_send_button.pack(side="left")
        self.department_chat_refresh_button = tk.Button(buttons, text="선택 부서 대화 조회", command=self._refresh_department_chat)
        self.department_chat_refresh_button.pack(side="left")
        tk.Label(parent, textvariable=self.department_chat_feedback, bg="#121c2d", fg="white").pack(anchor="w")
        self.department_chat_tree = ttk.Treeview(parent, columns=("id", "employee", "message", "when"), show="headings", height=10)
        for column, text, width in (("id", "번호", 70), ("employee", "발신 직원", 130), ("message", "본문", 520), ("when", "등록 시각", 165)):
            self.department_chat_tree.heading(column, text=text)
            self.department_chat_tree.column(column, width=width, stretch=(column=="message"))
        self.department_chat_tree.pack(fill="both", expand=True, pady=8)

    def _send_department_chat(self) -> None:
        try:
            department_id = int(self.department_chat_department.get())
            employee_id = int(self.department_chat_sender.get())
            message_id = self.store.send_department_message(
                department_id, employee_id, self.department_chat_body.get("1.0", "end-1c"))
            self.department_chat_feedback.set(f"부서 #{department_id} 대화 #{message_id} 저장")
            self.department_chat_body.delete("1.0", "end")
            self._refresh_department_chat()
        except (ValueError, PermissionError) as exc:
            self.department_chat_feedback.set(str(exc))

    def _refresh_department_chat(self) -> None:
        # Clear previous room immediately, including on invalid/unknown room IDs.
        for item in self.department_chat_tree.get_children():
            self.department_chat_tree.delete(item)
        try:
            department_id = int(self.department_chat_department.get())
            messages = self.store.list_department_messages(department_id)
        except (ValueError, PermissionError) as exc:
            self.department_chat_feedback.set(str(exc))
            return
        for msg in messages:
            excerpt = msg["body"].replace("\r", " ").replace("\n", " ")
            self.department_chat_tree.insert("", "end", values=(msg["id"], msg["sender_name"], excerpt, msg["created_at"]))
        self.department_chat_feedback.set(f"부서 #{department_id} 대화 {len(messages)}건 표시 (최근 최대 200건)")


    # Stage43: local owner-mediated project collaboration workspace.
    def _project_chat_panel(self, parent: tk.Frame) -> None:
        self._label(parent, "프로젝트별 협업 대화 (관리자가 기록하는 로컬 대화방)", size=16).pack(anchor="w")
        self._label(parent, "프로젝트 공간과 참여 직원은 로컬 기록입니다. AI 자율 소통·실제 프로젝트 실행은 지원하지 않습니다.", fg="#bfcfe5").pack(anchor="w", pady=5)
        self.project_chat_name = tk.StringVar()
        self.project_chat_description = tk.StringVar()
        self.project_chat_project = tk.StringVar()
        self.project_chat_employee = tk.StringVar()
        self.project_chat_feedback = tk.StringVar()
        form = tk.Frame(parent, bg="#121c2d")
        form.pack(fill="x", pady=4)
        for title, field in (("새 프로젝트명", self.project_chat_name), ("설명", self.project_chat_description),
                             ("프로젝트 ID", self.project_chat_project), ("직원 ID (참여/발신)", self.project_chat_employee)):
            col = tk.Frame(form, bg="#121c2d")
            col.pack(side="left", fill="x", expand=True, padx=3)
            tk.Label(col, text=title, bg="#121c2d", fg="white").pack(anchor="w")
            tk.Entry(col, textvariable=field).pack(fill="x")
        toolbar = tk.Frame(parent, bg="#121c2d")
        toolbar.pack(fill="x", pady=3)
        self.project_chat_create_button = tk.Button(toolbar, text="대화방 생성", command=self._create_project_chat_room)
        self.project_chat_create_button.pack(side="left", padx=3)
        self.project_chat_add_button = tk.Button(toolbar, text="직원 참여", command=self._add_project_chat_participant)
        self.project_chat_add_button.pack(side="left", padx=3)
        self.project_chat_remove_button = tk.Button(toolbar, text="직원 제외", command=self._remove_project_chat_participant)
        self.project_chat_remove_button.pack(side="left", padx=3)
        self.project_chat_refresh_button = tk.Button(toolbar, text="대화방 조회", command=self._refresh_project_chat)
        self.project_chat_refresh_button.pack(side="left", padx=3)
        self.project_chat_rooms_button = tk.Button(toolbar, text="프로젝트 목록", command=self._refresh_project_chat_rooms)
        self.project_chat_rooms_button.pack(side="left", padx=3)
        self.project_chat_rooms = ttk.Treeview(parent, columns=("id","name","people","messages"),show="headings",height=3)
        for key, label, width in (("id","ID",65),("name","프로젝트명",300),("people","참여 인원",95),("messages","메시지 수",95)):
            self.project_chat_rooms.heading(key,text=label)
            self.project_chat_rooms.column(key,width=width,stretch=(key=="name"))
        self.project_chat_rooms.pack(fill="x", pady=3)
        self.project_chat_rooms.bind("<<TreeviewSelect>>", self._select_project_chat_room)
        self._label(parent, "대화 본문 (최대 4000자)").pack(anchor="w")
        self.project_chat_body = tk.Text(parent, height=3)
        self.project_chat_body.pack(fill="x", pady=3)
        self.project_chat_send_button = tk.Button(parent, text="참여 직원 메시지 기록", command=self._send_project_chat)
        self.project_chat_send_button.pack(anchor="w")
        tk.Label(parent, textvariable=self.project_chat_feedback, bg="#121c2d", fg="white").pack(anchor="w", pady=3)
        self.project_chat_tree = ttk.Treeview(parent, columns=("id","sender","message","when"),show="headings",height=8)
        for key,label,width in (("id","ID",65),("sender","발신 직원",110),("message","메시지",460),("when","등록 시각",165)):
            self.project_chat_tree.heading(key,text=label)
            self.project_chat_tree.column(key,width=width,stretch=(key=="message"))
        self.project_chat_tree.pack(fill="both",expand=True)
        self._refresh_project_chat_rooms()

    def _project_room_id(self) -> int:
        return int(self.project_chat_project.get())

    def _project_employee_id(self) -> int:
        return int(self.project_chat_employee.get())

    def _refresh_project_chat_rooms(self) -> None:
        for item in self.project_chat_rooms.get_children():
            self.project_chat_rooms.delete(item)
        try:
            for room in self.store.list_project_rooms():
                self.project_chat_rooms.insert("", "end", values=(room['id'],room['name'],room['participant_count'],room['message_count']))
        except (ValueError,PermissionError) as exc:
            self.project_chat_feedback.set(str(exc))

    def _select_project_chat_room(self, event=None) -> None:
        selected = self.project_chat_rooms.selection()
        if selected:
            self.project_chat_project.set(str(self.project_chat_rooms.item(selected[0],'values')[0]))
            self._refresh_project_chat()

    def _create_project_chat_room(self) -> None:
        try:
            room_id = self.store.create_project_room(self.project_chat_name.get(),self.project_chat_description.get())
            self.project_chat_project.set(str(room_id))
            self.project_chat_feedback.set(f"프로젝트 대화방 #{room_id} 생성")
            self._refresh_project_chat_rooms()
            self._refresh_project_chat()
        except (ValueError,PermissionError) as exc:
            self.project_chat_feedback.set(str(exc))

    def _add_project_chat_participant(self) -> None:
        try:
            self.store.add_project_participant(self._project_room_id(),self._project_employee_id())
            self._refresh_project_chat_rooms()
            self._refresh_project_chat()
        except (ValueError,PermissionError) as exc:
            self.project_chat_feedback.set(str(exc))

    def _remove_project_chat_participant(self) -> None:
        try:
            self.store.remove_project_participant(self._project_room_id(),self._project_employee_id())
            self._refresh_project_chat_rooms()
            self._refresh_project_chat()
        except (ValueError,PermissionError) as exc:
            self.project_chat_feedback.set(str(exc))

    def _send_project_chat(self) -> None:
        try:
            message_id = self.store.send_project_message(self._project_room_id(),self._project_employee_id(),self.project_chat_body.get('1.0','end-1c'))
            self.project_chat_body.delete('1.0','end')
            self._refresh_project_chat_rooms()
            self._refresh_project_chat()
            self.project_chat_feedback.set(f"프로젝트 메시지 #{message_id} 저장")
        except (ValueError,PermissionError) as exc:
            self.project_chat_feedback.set(str(exc))

    def _refresh_project_chat(self) -> None:
        # Never keep old-room messages visible after an invalid room selection.
        for item in self.project_chat_tree.get_children():
            self.project_chat_tree.delete(item)
        try:
            room_id = self._project_room_id()
            messages = self.store.list_project_messages(room_id)
            people = self.store.list_project_participants(room_id)
        except (ValueError,PermissionError) as exc:
            self.project_chat_feedback.set(str(exc))
            return
        for message in messages:
            self.project_chat_tree.insert("", "end", values=(message['id'],message['sender_name'],message['body'].replace('\n',' ').replace('\r',' '),message['created_at']))
        self.project_chat_feedback.set(f"대화방 #{room_id}: 참여 직원 {len(people)}명 / 최근 메시지 {len(messages)}건")

    # Stage44: local meeting agenda and attendance, no AI generated opinions.
    def _meetings_panel(self, parent: tk.Frame) -> None:
        self._label(parent, "AI 회의 안건·참석자 (관리자 로컬 기록)", size=16).pack(anchor="w")
        self._label(parent, "회의 개최/모델 호출/실제 의견 교환은 하지 않습니다. 예정 상태는 기록일 뿐 자동 실행되지 않습니다.", fg="#bfcfe5").pack(anchor="w")
        self.meeting_title = tk.StringVar()
        self.meeting_purpose = tk.StringVar()
        self.meeting_id = tk.StringVar()
        self.meeting_employee = tk.StringVar()
        self.meeting_topic = tk.StringVar()
        self.meeting_feedback = tk.StringVar()
        form = tk.Frame(parent, bg="#121c2d")
        form.pack(fill="x", pady=6)
        for text, var in (("새 회의명", self.meeting_title), ("회의 목적", self.meeting_purpose),
                          ("회의 ID", self.meeting_id), ("직원 ID", self.meeting_employee)):
            cell = tk.Frame(form, bg="#121c2d")
            cell.pack(side="left", fill="x", expand=True, padx=3)
            tk.Label(cell, text=text, bg="#121c2d", fg="white").pack(anchor="w")
            tk.Entry(cell, textvariable=var).pack(fill="x")
        toolbar = tk.Frame(parent, bg="#121c2d")
        toolbar.pack(fill="x", pady=3)
        for caption, method, name in (("회의 초안 생성",self._create_meeting,"meeting_create_button"),
                                      ("참석자 추가",self._add_meeting_attendee,"meeting_add_button"),
                                      ("참석자 제외",self._remove_meeting_attendee,"meeting_remove_button"),
                                      ("예정 확정",self._schedule_meeting,"meeting_schedule_button"),
                                      ("회의 취소",self._cancel_meeting,"meeting_cancel_button"),
                                      ("새로고침",self._refresh_meetings,"meeting_refresh_button")):
            button = tk.Button(toolbar, text=caption, command=method)
            button.pack(side="left", padx=3)
            setattr(self,name,button)
        self.meeting_tree = ttk.Treeview(parent,columns=("id","title","status","agenda","people"),show="headings",height=4)
        for key,label,width in (("id","ID",45),("title","회의명",300),("status","상태",90),
                                ("agenda","안건 수",85),("people","참석자 수",85)):
            self.meeting_tree.heading(key,text=label)
            self.meeting_tree.column(key,width=width,stretch=(key=="title"))
        self.meeting_tree.pack(fill="x",pady=5)
        self.meeting_tree.bind("<<TreeviewSelect>>", self._select_meeting)
        topic_row = tk.Frame(parent,bg="#121c2d")
        topic_row.pack(fill="x", pady=4)
        tk.Entry(topic_row,textvariable=self.meeting_topic).pack(side="left",fill="x",expand=True)
        self.meeting_topic_button = tk.Button(topic_row,text="안건 추가 (최대 20개)",command=self._add_meeting_agenda)
        self.meeting_topic_button.pack(side="left")
        tk.Label(parent,textvariable=self.meeting_feedback,bg="#121c2d",fg="white").pack(anchor="w")
        self.meeting_detail_tree = ttk.Treeview(parent,columns=("kind","id","content"),show="headings",height=8)
        for key,label,width in (("kind","구분",80),("id","ID/순서",80),("content","안건 / 참석자",440)):
            self.meeting_detail_tree.heading(key,text=label)
            self.meeting_detail_tree.column(key,width=width,stretch=(key=="content"))
        self.meeting_detail_tree.pack(fill="both",expand=True,pady=5)
        self._refresh_meetings()

    def _meeting_selected_id(self) -> int:
        return int(self.meeting_id.get())

    def _refresh_meetings(self) -> None:
        for item in self.meeting_tree.get_children():
            self.meeting_tree.delete(item)
        try:
            for row in self.store.list_meetings():
                self.meeting_tree.insert("","end",values=(row['id'],row['title'],row['status'],row['agenda_count'],row['attendee_count']))
        except (ValueError, PermissionError) as exc:
            self.meeting_feedback.set(str(exc))

    def _select_meeting(self, event=None) -> None:
        selected=self.meeting_tree.selection()
        if selected:
            self.meeting_id.set(str(self.meeting_tree.item(selected[0],'values')[0]))
            self._refresh_meeting_detail()

    def _refresh_meeting_detail(self) -> None:
        for item in self.meeting_detail_tree.get_children():
            self.meeting_detail_tree.delete(item)
        try:
            meeting=self.store.read_meeting(self._meeting_selected_id())
        except (ValueError,PermissionError) as exc:
            self.meeting_feedback.set(str(exc))
            return
        for item in meeting['agenda']:
            self.meeting_detail_tree.insert("","end",values=('안건',item['position'],item['topic']))
        for person in meeting['attendees']:
            self.meeting_detail_tree.insert("","end",values=('참석자',person['employee_id'],person['display_name']+' ('+person['lifecycle']+')'))
        self.meeting_feedback.set(f"회의 #{meeting['id']} {meeting['status']} / 안건 {len(meeting['agenda'])} / 참석자 {len(meeting['attendees'])}")

    def _meeting_action(self, callback) -> None:
        try:
            callback()
            self._refresh_meetings()
            self._refresh_meeting_detail()
        except (ValueError,PermissionError) as exc:
            self.meeting_feedback.set(str(exc))

    def _create_meeting(self) -> None:
        def action():
            ident=self.store.create_meeting(self.meeting_title.get(),self.meeting_purpose.get())
            self.meeting_id.set(str(ident))
        self._meeting_action(action)

    def _add_meeting_agenda(self) -> None:
        def action():
            self.store.add_meeting_agenda(self._meeting_selected_id(),self.meeting_topic.get())
            self.meeting_topic.set('')
        self._meeting_action(action)

    def _add_meeting_attendee(self) -> None:
        self._meeting_action(lambda: self.store.add_meeting_attendee(self._meeting_selected_id(),int(self.meeting_employee.get())))

    def _remove_meeting_attendee(self) -> None:
        self._meeting_action(lambda: self.store.remove_meeting_attendee(self._meeting_selected_id(),int(self.meeting_employee.get())))

    def _schedule_meeting(self) -> None:
        self._meeting_action(lambda: self.store.set_meeting_status(self._meeting_selected_id(),'scheduled'))

    def _cancel_meeting(self) -> None:
        self._meeting_action(lambda: self.store.set_meeting_status(self._meeting_selected_id(),'cancelled'))

    # Stage45: owner-entered opinions and neutral per-agenda comparison, not AI discussion.
    def _meeting_opinions_panel(self, parent: tk.Frame) -> None:
        self._label(parent, "회의 의견 수집·비교 (관리자 기록)", size=16).pack(anchor="w")
        self._label(parent, "예정 상태 회의의 초대된 활성 직원만 등록 가능. 의견은 1인·안건당 1개로 수정 불가. 다수 의견은 결정이 아닙니다.", fg="#bfcfe5").pack(anchor="w")
        self.opinion_meeting_id = tk.StringVar()
        self.opinion_agenda_id = tk.StringVar()
        self.opinion_employee_id = tk.StringVar()
        self.opinion_stance = tk.StringVar(value="보류")
        self.opinion_reason = tk.StringVar()
        self.opinion_evidence = tk.StringVar()
        self.opinion_alternative = tk.StringVar()
        self.opinion_feedback = tk.StringVar(value="44단계 회의 관리 화면에서 회의·안건 ID와 참석자 ID를 확인하세요.")
        row = tk.Frame(parent,bg="#121c2d")
        row.pack(fill="x",pady=7)
        for caption,var,width in (("회의 ID",self.opinion_meeting_id,10),("안건 ID",self.opinion_agenda_id,10),
                                  ("참석 직원 ID",self.opinion_employee_id,13)):
            item=tk.Frame(row,bg="#121c2d")
            item.pack(side="left",padx=3)
            tk.Label(item,text=caption,bg="#121c2d",fg="white").pack(anchor="w")
            tk.Entry(item,textvariable=var,width=width).pack()
        choice=tk.Frame(row,bg="#121c2d")
        choice.pack(side="left",padx=4)
        tk.Label(choice,text="입장",bg="#121c2d",fg="white").pack(anchor="w")
        self.opinion_stance_select = ttk.Combobox(choice, textvariable=self.opinion_stance,
                                                 values=("찬성","보류","반대"),state="readonly",width=9)
        self.opinion_stance_select.pack()
        for caption,var in (("의견 근거 (필수, 2000자 이내)",self.opinion_reason),
                            ("참고 출처 (선택, 500자 이내)",self.opinion_evidence),
                            ("제안 대안 (선택, 1000자 이내)",self.opinion_alternative)):
            line=tk.Frame(parent,bg="#121c2d")
            line.pack(fill="x",pady=3)
            tk.Label(line,text=caption,bg="#121c2d",fg="white",width=29,anchor="w").pack(side="left")
            tk.Entry(line,textvariable=var).pack(side="left",fill="x",expand=True)
        buttons=tk.Frame(parent,bg="#121c2d")
        buttons.pack(fill="x",pady=6)
        self.opinion_submit_button=tk.Button(buttons,text="의견 저장 (변경 불가)",command=self._submit_meeting_opinion)
        self.opinion_submit_button.pack(side="left",padx=4)
        self.real_meeting_ai_button=tk.Button(buttons,text="선택 직원 실제 로컬 AI 의견 생성",
                        command=self._run_real_meeting_ai_opinion)
        self.real_meeting_ai_button.pack(side="left",padx=4)
        self.real_meeting_attendees_button=tk.Button(buttons,
            text="참석 직원 전체 로컬 AI 의견 수집 (최대 30명)",
            command=self._run_real_meeting_attendees)
        self.real_meeting_attendees_button.pack(side="left",padx=4)
        self.opinion_refresh_button=tk.Button(buttons,text="안건별 의견 비교·새로고침",command=self._refresh_meeting_opinions)
        self.opinion_refresh_button.pack(side="left",padx=4)
        tk.Label(parent,textvariable=self.opinion_feedback,bg="#121c2d",fg="white",wraplength=900,justify="left").pack(anchor="w",pady=3)
        self.opinion_comparison_tree=ttk.Treeview(parent,columns=("agenda","topic","yes","hold","no","pending","difference"),show="headings",height=5)
        for key,caption,width in (("agenda","안건 ID",70),("topic","안건",230),("yes","찬성",55),
                                  ("hold","보류",55),("no","반대",55),("pending","미등록",75),("difference","의견 차이",90)):
            self.opinion_comparison_tree.heading(key,text=caption)
            self.opinion_comparison_tree.column(key,width=width,stretch=(key=="topic"))
        self.opinion_comparison_tree.pack(fill="x",pady=4)
        self.opinion_comparison_tree.bind("<<TreeviewSelect>>",self._select_opinion_agenda)
        self.opinion_detail_tree=ttk.Treeview(parent,columns=("agenda","employee","stance","reason","source","alternative"),show="headings",height=7)
        for key,caption,width in (("agenda","안건",55),("employee","직원",100),("stance","입장/출처",95),
                                  ("reason","의견 근거",225),("source","출처",125),("alternative","대안",125)):
            self.opinion_detail_tree.heading(key,text=caption)
            self.opinion_detail_tree.column(key,width=width,stretch=(key=="reason"))
        self.opinion_detail_tree.pack(fill="both",expand=True,pady=5)

    def _select_opinion_agenda(self,event=None) -> None:
        selection=self.opinion_comparison_tree.selection()
        if selection:
            self.opinion_agenda_id.set(str(self.opinion_comparison_tree.item(selection[0],"values")[0]))

    def _submit_meeting_opinion(self) -> None:
        try:
            identifier=self.store.add_meeting_opinion(int(self.opinion_meeting_id.get()),
                int(self.opinion_agenda_id.get()),int(self.opinion_employee_id.get()),
                self.opinion_stance.get(),self.opinion_reason.get(),self.opinion_evidence.get(),
                self.opinion_alternative.get())
        except (ValueError,PermissionError) as exc:
            self.opinion_feedback.set(str(exc))
            return
        self.opinion_reason.set("")
        self.opinion_evidence.set("")
        self.opinion_alternative.set("")
        self._refresh_meeting_opinions()
        self.opinion_feedback.set(f"의견 #{identifier} 저장. 수정·삭제 불가 / 의견 비교는 결정이나 승인이 아닙니다.")

    def _run_real_meeting_attendees(self) -> None:
        """One consented batch of actual assigned local GGUF/CLI workers."""
        try:
            if self._model_running:
                raise ValueError('이미 다른 로컬 모델을 호출 중입니다.')
            meeting_id=int(self.opinion_meeting_id.get())
            agenda_id=int(self.opinion_agenda_id.get())
            self.store.require_permission('company:manage')
            self.store.require_permission('agents:manage')
            with self.store._connect() as con:
                from desktop.meetings import read as meeting_read
                meeting=meeting_read(con,meeting_id)
            if not messagebox.askyesno('참석 직원 실제 로컬 모델 협업',
                f'회의 #{meeting_id} 안건 #{agenda_id}의 활성 참석자 '
                f'{len(meeting["attendees"])}명에 대해 각각 로컬 모델을 실행할까요?\n'
                '직원별 결과가 저장되며 취소·실패는 성공으로 계산되지 않습니다. '
                '관리자 의사결정/외부 결제·도구 실행은 하지 않습니다.'):
                return
        except (ValueError,PermissionError) as exc:
            self.opinion_feedback.set('전체 참석자 호출 거부: '+str(exc))
            return
        self._model_running=True
        generation=self._session_generation
        cancel=threading.Event()
        self._model_cancel=cancel
        responses=queue.Queue()
        self.real_meeting_attendees_button.configure(state='disabled')
        self.real_meeting_ai_button.configure(state='disabled')
        self.opinion_feedback.set('참석자 전체 로컬 모델 실행 중: 직원별 감사와 SQLite 의견을 기록합니다.')
        def worker():
            try:
                responses.put((True,self.store.run_real_meeting_attendees(
                    meeting_id,agenda_id,cancel=cancel)))
            except (ValueError,PermissionError,TimeoutError,InterruptedError,
                    RuntimeError,OSError,sqlite3.Error) as exc:
                responses.put((False,str(exc)))
        self._model_thread=threading.Thread(target=worker,daemon=True)
        self._model_thread.start()
        def poll():
            if generation!=self._session_generation or not self.store.is_authenticated:
                return
            try:
                ok,result=responses.get_nowait()
            except queue.Empty:
                if self.root.winfo_exists(): self.root.after(100,poll)
                return
            self._model_running=False
            self._model_cancel=None
            self._model_thread=None
            self.real_meeting_attendees_button.configure(state='normal')
            self.real_meeting_ai_button.configure(state='normal')
            if ok:
                self._refresh_meeting_opinions()
                self.opinion_feedback.set(
                    f'실제 직원 모델 성공 {len(result["succeeded"])}명, '
                    f'실패 {len(result["failed"])}명, '
                    f'기존 의견 건너뜀 {len(result["skipped_previously_recorded"])}명, '
                    f'취소 {result["cancelled"]}. 관리자 최종 승인/외부 활동 없음.')
            else:
                self.opinion_feedback.set('전체 로컬 AI 회의 호출 실패: '+str(result))
        self.root.after(100,poll)

    def _run_real_meeting_ai_opinion(self) -> None:
        """Owner click, local model subprocess, audited SQLite and GUI-thread result."""
        try:
            if self._model_running:
                raise ValueError('이미 로컬 AI 모델이 실행 중입니다.')
            meeting_id=int(self.opinion_meeting_id.get())
            agenda_id=int(self.opinion_agenda_id.get())
            employee_id=int(self.opinion_employee_id.get())
            if not messagebox.askyesno('실제 로컬 직원 AI 회의 의견',
                    f'직원 #{employee_id}의 로컬 모델로 회의 #{meeting_id}, 안건 #{agenda_id} '
                    '의견을 1회 생성·불변 감사할까요?\n'
                    'AI 의견은 관리자 결정, 외부 사실 검증이나 실행 승인이 아닙니다.'):
                return
            self.store.require_permission('company:manage')
        except (ValueError,PermissionError) as exc:
            self.opinion_feedback.set('실제 회의 모델 호출 거부: '+str(exc))
            return
        self._model_running=True
        generation=self._session_generation
        cancel=threading.Event()
        self._model_cancel=cancel
        replies=queue.Queue()
        self.real_meeting_ai_button.configure(state='disabled')
        self.real_meeting_attendees_button.configure(state='disabled')
        self.opinion_feedback.set('실제 직원 로컬 AI를 실행 중입니다. 호출과 결과가 SQLite 감사에 기록됩니다.')
        def worker():
            try:
                result=self.store.run_real_meeting_employee_opinion(
                    meeting_id,agenda_id,employee_id,cancel=cancel)
                replies.put((True,result))
            except (ValueError,PermissionError,TimeoutError,InterruptedError,RuntimeError,OSError) as exc:
                replies.put((False,str(exc)))
        self._model_thread=threading.Thread(target=worker,daemon=True)
        self._model_thread.start()
        def poll():
            if generation != self._session_generation or not self.store.is_authenticated:
                return
            try:
                success,result=replies.get_nowait()
            except queue.Empty:
                if self.root.winfo_exists():
                    self.root.after(100,poll)
                return
            self._model_running=False
            self._model_cancel=None
            self._model_thread=None
            self.real_meeting_ai_button.configure(state='normal')
            self.real_meeting_attendees_button.configure(state='normal')
            if success:
                self._refresh_meeting_opinions()
                self.opinion_feedback.set(
                    f'실제 AI 의견 #{result["opinion_id"]} · 모델 감사 #{result["model_call_id"]} 저장. '
                    '관리자 승인과 사실 검증은 별도입니다.')
            else:
                self.opinion_feedback.set('실제 직원 AI 회의 의견 실패: '+str(result))
        self.root.after(100,poll)

    def _refresh_meeting_opinions(self) -> None:
        # Blank existing meeting data first, so invalid selections cannot leak stale results.
        for tree in (self.opinion_comparison_tree,self.opinion_detail_tree):
            for item in tree.get_children():
                tree.delete(item)
        try:
            summary=self.store.compare_meeting_opinions(int(self.opinion_meeting_id.get()))
        except (ValueError,PermissionError) as exc:
            self.opinion_feedback.set(str(exc))
            return
        for agenda in summary['agenda']:
            counts=agenda['counts']
            self.opinion_comparison_tree.insert('', 'end', values=(agenda['agenda_id'],agenda['topic'],
                counts['찬성'],counts['보류'],counts['반대'],len(agenda['missing_attendees']),
                '있음' if agenda['has_differing_opinions'] else '없음'))
            for opinion in agenda['opinions']:
                self.opinion_detail_tree.insert('','end',values=(agenda['position'],opinion['display_name'],
                    opinion['stance']+('·AI' if opinion['origin']=='real_local_model' else '·수기'),
                    opinion['reasoning'].replace('\n',' '),opinion['evidence'],opinion['alternative']))
        count=sum(len(a['opinions']) for a in summary['agenda'])
        missing=sum(len(a['missing_attendees']) for a in summary['agenda'])
        self.opinion_feedback.set(f"회의 #{summary['meeting_id']} ({summary['status']}) | 의견 {count}건 / 미등록 {missing}건. {summary['note']}")



    # Stage46: explicit administrator decision and local follow-up TODO, never AI vote.
    def _meeting_decisions_panel(self, parent: tk.Frame) -> None:
        self._label(parent, '회의 의사결정 및 후속 업무 (관리자 승인)', size=16).pack(anchor='w')
        self._label(parent, '의견은 참고용이며, 채택은 관리자 명시적 결정입니다. 외부 실행·지출 승인과 무관합니다.', fg='#bfcfe5').pack(anchor='w')
        self.decision_meeting_id=tk.StringVar()
        self.decision_agenda_id=tk.StringVar()
        self.decision_outcome=tk.StringVar(value='deferred')
        self.decision_rationale=tk.StringVar()
        self.decision_acknowledge=tk.BooleanVar(value=False)
        self.decision_id=tk.StringVar()
        self.decision_employee=tk.StringVar()
        self.decision_task_title=tk.StringVar()
        self.decision_task_description=tk.StringVar()
        self.decision_feedback=tk.StringVar(value='회의·안건 ID를 입력하고 의견 검토 후 관리자 결정부터 저장하세요.')
        line=tk.Frame(parent,bg='#121c2d');line.pack(fill='x',pady=8)
        for label,var,width in (('회의 ID',self.decision_meeting_id,10),('안건 ID',self.decision_agenda_id,10)):
            box=tk.Frame(line,bg='#121c2d');box.pack(side='left',padx=5)
            tk.Label(box,text=label,bg='#121c2d',fg='white').pack(anchor='w')
            tk.Entry(box,textvariable=var,width=width).pack()
        box=tk.Frame(line,bg='#121c2d');box.pack(side='left',padx=5)
        tk.Label(box,text='관리자 결정',bg='#121c2d',fg='white').pack(anchor='w')
        self.decision_outcome_select=ttk.Combobox(box,textvariable=self.decision_outcome,
            values=('approved','deferred','rejected'),state='readonly',width=13)
        self.decision_outcome_select.pack()
        line=tk.Frame(parent,bg='#121c2d');line.pack(fill='x',pady=5)
        tk.Label(line,text='결정 근거 (필수)',bg='#121c2d',fg='white').pack(side='left',padx=5)
        tk.Entry(line,textvariable=self.decision_rationale).pack(side='left',expand=True,fill='x')
        tk.Checkbutton(parent,text='반대·보류 의견 및 미제출 참석자를 확인했습니다',variable=self.decision_acknowledge,
            bg='#121c2d',fg='white',selectcolor='#26364f',activebackground='#121c2d').pack(anchor='w')
        buttons=tk.Frame(parent,bg='#121c2d');buttons.pack(fill='x',pady=5)
        self.decision_save_button=tk.Button(buttons,text='관리자 결정 확정 (변경 불가)',command=self._save_meeting_decision)
        self.decision_save_button.pack(side='left',padx=4)
        self.decision_refresh_button=tk.Button(buttons,text='결정 목록 새로고침',command=self._refresh_meeting_decisions)
        self.decision_refresh_button.pack(side='left',padx=4)
        self.decision_tree=ttk.Treeview(parent,columns=('id','agenda','topic','outcome','submitted','missing','task'),show='headings',height=7)
        for key,label,width in (('id','결정 ID',65),('agenda','안건 ID',65),('topic','안건',200),('outcome','결정',80),
                                ('submitted','제출',65),('missing','미제출',65),('task','후속 업무 ID',100)):
            self.decision_tree.heading(key,text=label)
            self.decision_tree.column(key,width=width,stretch=(key=='topic'))
        self.decision_tree.pack(fill='both',expand=True,pady=6)
        self.decision_tree.bind('<<TreeviewSelect>>',self._select_meeting_decision)
        self._label(parent,'채택된 결정의 후속 업무: 참석 중인 활성 실무 직원에게 명시적으로 배정 (AI 실행·외부 전송 없음)',fg='#bfcfe5').pack(anchor='w')
        line=tk.Frame(parent,bg='#121c2d');line.pack(fill='x',pady=5)
        for label,var,width in (('결정 ID',self.decision_id,9),('담당 직원 ID',self.decision_employee,11),('업무 제목',self.decision_task_title,30)):
            box=tk.Frame(line,bg='#121c2d');box.pack(side='left',padx=5)
            tk.Label(box,text=label,bg='#121c2d',fg='white').pack(anchor='w')
            tk.Entry(box,textvariable=var,width=width).pack()
        line=tk.Frame(parent,bg='#121c2d');line.pack(fill='x',pady=5)
        tk.Label(line,text='업무 설명',bg='#121c2d',fg='white').pack(side='left',padx=5)
        tk.Entry(line,textvariable=self.decision_task_description).pack(side='left',fill='x',expand=True)
        self.decision_followup_button=tk.Button(parent,text='후속 업무 생성·담당자 배정 (1회)',command=self._create_meeting_followup)
        self.decision_followup_button.pack(anchor='w',pady=7)
        tk.Label(parent,textvariable=self.decision_feedback,bg='#121c2d',fg='white',wraplength=870,justify='left').pack(anchor='w')

    def _save_meeting_decision(self) -> None:
        try:
            ident=self.store.decide_meeting_agenda(int(self.decision_meeting_id.get()),
                int(self.decision_agenda_id.get()),self.decision_outcome.get(),
                self.decision_rationale.get(),self.decision_acknowledge.get())
        except (ValueError,PermissionError) as exc:
            self.decision_feedback.set(str(exc));return
        self.decision_acknowledge.set(False)
        self._refresh_meeting_decisions()
        self.decision_id.set(str(ident))
        self.decision_feedback.set(f'결정 #{ident} 저장 완료. 수정·삭제 불가. 후속 업무는 별도 관리자 조작 필요.')

    def _refresh_meeting_decisions(self) -> None:
        for item in self.decision_tree.get_children():
            self.decision_tree.delete(item)
        self.decision_id.set('')  # no stale selection on invalid meeting
        try:
            rows=self.store.list_meeting_decisions(int(self.decision_meeting_id.get()))
        except (ValueError,PermissionError) as exc:
            self.decision_feedback.set(str(exc));return
        for record in rows:
            self.decision_tree.insert('','end',values=(record['id'],record['agenda_id'],record['topic'],
                record['outcome'],record['opinions_count'],record['missing_count'],record['task_id'] or ''))
        self.decision_feedback.set(f'회의 #{self.decision_meeting_id.get()} 결정 {len(rows)}건. 선택한 결정은 변경할 수 없습니다.')

    def _select_meeting_decision(self,event=None) -> None:
        selection=self.decision_tree.selection()
        if selection:
            self.decision_id.set(str(self.decision_tree.item(selection[0],'values')[0]))

    def _create_meeting_followup(self) -> None:
        try:
            task_id=self.store.create_meeting_followup(int(self.decision_id.get()),
                int(self.decision_employee.get()),self.decision_task_title.get(),
                self.decision_task_description.get())
        except (ValueError,PermissionError) as exc:
            self.decision_feedback.set(str(exc));return
        self._refresh_meeting_decisions()
        self.decision_feedback.set(f'업무 #{task_id} 저장, 지정 직원에게 할 일(todo) 배정. 모델·도구는 호출하지 않았습니다.')


    def _employee_memories_panel(self, parent: tk.Frame) -> None:
        self._label(parent, '직원별 장기 기억 (관리자 수동 기록 · 로컬 SQLite)', size=16).pack(anchor='w')
        self._label(parent, '직원 ID별로 분리 · AI 자동 회상/학습 아님 · DB 암호화 안 됨',
                    fg='#bfcfe5', bg='#121c2d').pack(anchor='w', pady=5)
        form=tk.Frame(parent,bg='#121c2d');form.pack(fill='x')
        self.memory_employee=tk.StringVar()
        self.memory_kind=tk.StringVar(value='fact')
        self.memory_title=tk.StringVar()
        self.memory_source=tk.StringVar()
        self.memory_confidence=tk.StringVar(value='70')
        self.memory_expiry=tk.StringVar()
        self.memory_query=tk.StringVar()
        self.memory_feedback=tk.StringVar()
        fields=tk.Frame(form,bg='#121c2d');fields.pack(fill='x')
        fields.columnconfigure(0,weight=1);fields.columnconfigure(1,weight=1)
        for n,(label,variable) in enumerate((('직원 ID (저장·조회 범위)',self.memory_employee),
                               ('제목',self.memory_title),('출처/근거',self.memory_source),
                               ('신뢰도 0~100',self.memory_confidence),
                               ('유효기간 YYYY-MM-DD (선택)',self.memory_expiry),
                               ('검색어 (선택)',self.memory_query))):
            col=n%2;row=(n//2)*2
            tk.Label(fields,text=label,bg='#121c2d',fg='white').grid(row=row,column=col,sticky='w')
            tk.Entry(fields,textvariable=variable).grid(row=row+1,column=col,sticky='ew',padx=(0,10),pady=(0,3))
        tk.Label(form,text='분류',bg='#121c2d',fg='white').pack(anchor='w')
        ttk.Combobox(form,textvariable=self.memory_kind,
                     values=('fact','lesson','procedure','decision'),state='readonly').pack(fill='x')
        tk.Label(form,text='기억 내용',bg='#121c2d',fg='white').pack(anchor='w')
        self.memory_content=tk.Text(form,height=3);self.memory_content.pack(fill='x')
        buttons=tk.Frame(parent,bg='#121c2d');buttons.pack(fill='x',pady=5)
        self.memory_save_button=tk.Button(buttons,text='직원 기억 저장',command=self._save_employee_memory)
        self.memory_save_button.pack(side='left')
        self.memory_refresh_button=tk.Button(buttons,text='기억 조회',command=self._refresh_employee_memories)
        self.memory_refresh_button.pack(side='left')
        self.memory_archive_button=tk.Button(buttons,text='선택 기억 보관',command=self._archive_employee_memory)
        self.memory_archive_button.pack(side='left')
        tk.Label(parent,textvariable=self.memory_feedback,bg='#121c2d',fg='white').pack(anchor='w')
        self.memory_tree=ttk.Treeview(parent,columns=('id','kind','title','confidence','expires','archived'),show='headings',height=7)
        for col,label in (('id','ID'),('kind','분류'),('title','제목'),('confidence','신뢰도'),
                          ('expires','유효기간'),('archived','보관 시각')):
            self.memory_tree.heading(col,text=label)
        self.memory_tree.pack(fill='both',expand=True)
        self.memory_tree.bind('<<TreeviewSelect>>',self._view_employee_memory)
        self.memory_details=tk.Text(parent,height=4,state='disabled')
        self.memory_details.pack(fill='x')

    def _save_employee_memory(self) -> None:
        try:
            mid=self.store.save_employee_memory(
                int(self.memory_employee.get()),self.memory_kind.get(),self.memory_title.get(),
                self.memory_content.get('1.0','end-1c'),self.memory_source.get(),
                int(self.memory_confidence.get()),self.memory_expiry.get().strip() or None)
            self.memory_feedback.set(f'직원 기억 #{mid} 로컬 저장 완료')
            self._refresh_employee_memories()
        except (ValueError,PermissionError) as exc:self.memory_feedback.set(str(exc))

    def _refresh_employee_memories(self) -> None:
        try:
            employee=int(self.memory_employee.get())
            memories=self.store.list_employee_memories(employee,query=self.memory_query.get())
            for item in self.memory_tree.get_children():self.memory_tree.delete(item)
            for m in memories:
                self.memory_tree.insert('','end',values=(m['id'],m['kind'],m['title'],m['confidence'],
                    m['expires_on'] or '',m['archived_at'] or ''))
            self.memory_feedback.set(f'직원 #{employee}: {len(memories)}개 표시 (보관·만료 제외)')
        except (ValueError,PermissionError) as exc:self.memory_feedback.set(str(exc))

    def _view_employee_memory(self,event=None) -> None:
        selected=self.memory_tree.selection()
        if not selected:return
        try:
            employee=int(self.memory_employee.get())
            mid=int(self.memory_tree.item(selected[0],'values')[0])
            m=self.store.read_employee_memory(employee,mid)
            self.memory_details.configure(state='normal')
            self.memory_details.delete('1.0','end')
            self.memory_details.insert('1.0',f"출처: {m['source']}\n내용: {m['content']}")
            self.memory_details.configure(state='disabled')
        except (ValueError,PermissionError) as exc:self.memory_feedback.set(str(exc))

    def _archive_employee_memory(self) -> None:
        selected=self.memory_tree.selection()
        if not selected:
            self.memory_feedback.set('보관할 기억을 선택하세요.');return
        try:
            employee=int(self.memory_employee.get())
            mid=int(self.memory_tree.item(selected[0],'values')[0])
            self.store.archive_employee_memory(employee,mid)
            self._refresh_employee_memories()
            self.memory_feedback.set(f'기억 #{mid} 보관 완료 (기록 유지)')
        except (ValueError,PermissionError) as exc:self.memory_feedback.set(str(exc))

    def _company_knowledge_panel(self, parent: tk.Frame) -> None:
        self._label(parent, '회사 공동 지식 저장소 (관리자 수동 기록 · 로컬 SQLite)', size=16).pack(anchor='w')
        self._label(parent, '문자 검색·관리자 전용 직원별 접근 미리보기 / 출처 미검증 / AI 자동 검색·DB 암호화 없음',
                    fg='#bfcfe5', bg='#121c2d').pack(anchor='w', pady=5)
        self.knowledge_kind = tk.StringVar(value='policy')
        self.knowledge_title = tk.StringVar()
        self.knowledge_source = tk.StringVar()
        self.knowledge_feedback = tk.StringVar()
        fields = tk.Frame(parent, bg='#121c2d'); fields.pack(fill='x')
        self._label(fields, '문서 분류', bg='#121c2d').pack(anchor='w')
        ttk.Combobox(fields, textvariable=self.knowledge_kind, state='readonly',
                     values=('policy','procedure','research','business_plan','development',
                             'product','case_study','meeting','other')).pack(fill='x')
        for name, var in (('제목',self.knowledge_title),('출처',self.knowledge_source)):
            self._label(fields, name, bg='#121c2d').pack(anchor='w')
            tk.Entry(fields, textvariable=var).pack(fill='x')
        self._label(fields,'지식 내용',bg='#121c2d').pack(anchor='w')
        self.knowledge_content = tk.Text(fields,height=3); self.knowledge_content.pack(fill='x')
        search_box = tk.Frame(parent,bg='#121c2d');search_box.pack(fill='x',pady=4)
        self.knowledge_query = tk.StringVar()
        self._label(search_box,'문자 검색 (제목·본문·출처)',bg='#121c2d').pack(side='left')
        tk.Entry(search_box,textvariable=self.knowledge_query,width=38).pack(side='left',padx=6)
        self.knowledge_search_button = tk.Button(search_box,text='검색',command=self._refresh_company_knowledge)
        self.knowledge_search_button.pack(side='left')
        actions = tk.Frame(parent,bg='#121c2d'); actions.pack(fill='x',pady=5)
        self.knowledge_save_button = tk.Button(actions,text='지식 문서 저장',command=self._save_company_knowledge)
        self.knowledge_save_button.pack(side='left')
        self.knowledge_refresh_button = tk.Button(actions,text='목록 새로고침',command=self._refresh_company_knowledge)
        self.knowledge_refresh_button.pack(side='left')
        self.knowledge_archive_button = tk.Button(actions,text='선택 문서 보관',command=self._archive_company_knowledge)
        self.knowledge_archive_button.pack(side='left')
        policy = tk.Frame(parent,bg='#121c2d');policy.pack(fill='x',pady=4)
        self.knowledge_mode = tk.StringVar(value='owner_only')
        self.knowledge_employee = tk.StringVar()
        self.knowledge_source_type = tk.StringVar(value='manual')
        self.knowledge_reference = tk.StringVar()
        self._label(policy,'선택 문서 공개 범위',bg='#121c2d').pack(side='left')
        ttk.Combobox(policy,textvariable=self.knowledge_mode,state='readonly',width=15,
                     values=('owner_only','restricted','company')).pack(side='left',padx=3)
        self.knowledge_mode_button=tk.Button(policy,text='공개 범위 적용',command=self._set_company_knowledge_mode)
        self.knowledge_mode_button.pack(side='left',padx=3)
        self._label(policy,'직원 ID',bg='#121c2d').pack(side='left')
        tk.Entry(policy,textvariable=self.knowledge_employee,width=7).pack(side='left',padx=3)
        self.knowledge_grant_button=tk.Button(policy,text='읽기 허용',command=self._grant_company_knowledge)
        self.knowledge_grant_button.pack(side='left',padx=2)
        self.knowledge_revoke_button=tk.Button(policy,text='허용 해제',command=self._revoke_company_knowledge)
        self.knowledge_revoke_button.pack(side='left',padx=2)
        source_bar=tk.Frame(parent,bg='#121c2d');source_bar.pack(fill='x',pady=4)
        ttk.Combobox(source_bar,textvariable=self.knowledge_source_type,state='readonly',width=19,
                     values=('manual','local_file','internal_record','website_reference')).pack(side='left')
        tk.Entry(source_bar,textvariable=self.knowledge_reference,width=45).pack(side='left',padx=4)
        self.knowledge_source_button=tk.Button(source_bar,text='출처 참조 추가 (미검증)',command=self._add_company_knowledge_source)
        self.knowledge_source_button.pack(side='left')
        self.knowledge_preview_button=tk.Button(source_bar,text='직원 조회 미리보기',command=self._preview_company_knowledge)
        self.knowledge_preview_button.pack(side='left',padx=4)
        self._label(parent, '', textvariable=self.knowledge_feedback, bg='#121c2d').pack(anchor='w')
        self.knowledge_tree = ttk.Treeview(parent,columns=('id','kind','title','source','created'),show='headings',height=7)
        for col,label in (('id','ID'),('kind','분류'),('title','제목'),('source','출처'),('created','등록 시각')):
            self.knowledge_tree.heading(col,text=label)
        self.knowledge_tree.pack(fill='both',expand=True)
        self.knowledge_tree.bind('<<TreeviewSelect>>',self._view_company_knowledge)
        self.knowledge_details = tk.Text(parent,height=4,state='disabled')
        self.knowledge_details.pack(fill='x')
        self._refresh_company_knowledge()

    def _save_company_knowledge(self) -> None:
        try:
            document = self.store.create_company_knowledge(self.knowledge_kind.get(),
                self.knowledge_title.get(),self.knowledge_content.get('1.0','end-1c'),
                self.knowledge_source.get())
            self._refresh_company_knowledge()
            self.knowledge_feedback.set(f'지식 문서 #{document} 저장 완료 (자동 AI 호출 없음)')
        except (ValueError,PermissionError) as exc:
            self.knowledge_feedback.set(str(exc))

    def _refresh_company_knowledge(self) -> None:
        try:
            docs = self.store.search_company_knowledge(self.knowledge_query.get())
            for row in self.knowledge_tree.get_children(): self.knowledge_tree.delete(row)
            for doc in docs:
                self.knowledge_tree.insert('','end',values=(doc['id'],doc['kind'],doc['title'],
                    doc['source'],doc['created_at']))
            self.knowledge_feedback.set(f'현재 문서 {len(docs)}개 (보관 문서 제외)')
        except (ValueError,PermissionError) as exc:
            self.knowledge_feedback.set(str(exc))

    def _view_company_knowledge(self,event=None) -> None:
        selected=self.knowledge_tree.selection()
        if not selected:return
        try:
            doc_id=int(self.knowledge_tree.item(selected[0],'values')[0])
            doc=self.store.read_company_knowledge(doc_id)
            self.knowledge_details.configure(state='normal')
            self.knowledge_details.delete('1.0','end')
            access=self.store.read_company_knowledge_access(doc_id)
            sources=self.store.list_company_knowledge_sources(doc_id)
            source_summary='; '.join(f"{r['source_type']}:{r['reference']} [{r['validation_status']}]" for r in sources)
            self.knowledge_mode.set(access['mode'])
            self.knowledge_details.insert('1.0',f"출처(사용자 기입·미검증): {doc['source']}\n"
                f"권한: {access['mode']} / 읽기 허용 직원: {access['employees']}\n"
                f"추가 출처(미검증): {source_summary or '없음'}\n내용: {doc['content']}")
            self.knowledge_details.configure(state='disabled')
        except (ValueError,PermissionError) as exc:
            self.knowledge_feedback.set(str(exc))

    def _archive_company_knowledge(self) -> None:
        selected=self.knowledge_tree.selection()
        if not selected:
            self.knowledge_feedback.set('보관할 문서를 선택하세요.');return
        try:
            doc_id=int(self.knowledge_tree.item(selected[0],'values')[0])
            self.store.archive_company_knowledge(doc_id)
            self._refresh_company_knowledge()
            self.knowledge_feedback.set(f'문서 #{doc_id} 보관 완료 (원본 유지)')
        except (ValueError,PermissionError) as exc:
            self.knowledge_feedback.set(str(exc))

    def _selected_knowledge_id(self) -> int:
        selected=self.knowledge_tree.selection()
        if not selected:
            raise ValueError('먼저 지식 문서를 선택하세요.')
        return int(self.knowledge_tree.item(selected[0],'values')[0])

    def _set_company_knowledge_mode(self) -> None:
        try:
            did=self._selected_knowledge_id()
            self.store.set_company_knowledge_visibility(did,self.knowledge_mode.get())
            self._view_company_knowledge()
            self.knowledge_feedback.set(f'문서 #{did} 접근 범위 적용: {self.knowledge_mode.get()}')
        except (ValueError,PermissionError) as exc:self.knowledge_feedback.set(str(exc))

    def _grant_company_knowledge(self) -> None:
        try:
            did=self._selected_knowledge_id()
            emp=int(self.knowledge_employee.get())
            granted=self.store.grant_company_knowledge_read(did,emp)
            self._view_company_knowledge()
            self.knowledge_feedback.set(f'직원 #{emp} 문서 읽기 허용: {granted}')
        except (ValueError,PermissionError) as exc:self.knowledge_feedback.set(str(exc))

    def _revoke_company_knowledge(self) -> None:
        try:
            did=self._selected_knowledge_id()
            emp=int(self.knowledge_employee.get())
            revoked=self.store.revoke_company_knowledge_read(did,emp)
            self._view_company_knowledge()
            self.knowledge_feedback.set(f'직원 #{emp} 문서 읽기 권한 해제: {revoked}')
        except (ValueError,PermissionError) as exc:self.knowledge_feedback.set(str(exc))

    def _add_company_knowledge_source(self) -> None:
        try:
            did=self._selected_knowledge_id()
            sid=self.store.add_company_knowledge_source(did,self.knowledge_source_type.get(),
                                                       self.knowledge_reference.get())
            self._view_company_knowledge()
            self.knowledge_feedback.set(f'출처 #{sid} 메타데이터 추가 (실제 확인된 출처 아님)')
        except (ValueError,PermissionError) as exc:self.knowledge_feedback.set(str(exc))

    def _preview_company_knowledge(self) -> None:
        try:
            did=self._selected_knowledge_id()
            emp=int(self.knowledge_employee.get())
            doc=self.store.preview_employee_knowledge_read(emp,did)
            self.knowledge_feedback.set(f'관리자 미리보기: 직원 #{emp}은 문서 #{doc["id"]} 읽기 가능')
        except (ValueError,PermissionError) as exc:self.knowledge_feedback.set(f'관리자 미리보기 거부: {exc}')

    # Stage50: owner-administered evidence-based review. No autonomous LLM evaluation.
    def _performance_panel(self, parent: tk.Frame) -> None:
        self.performance_task_id = tk.StringVar()
        self.performance_rating = tk.StringVar(value='3')
        self.performance_evidence = tk.StringVar()
        self.performance_lesson = tk.StringVar()
        self.performance_review_id = tk.StringVar()
        self.improvement_title = tk.StringVar()
        self.improvement_action = tk.StringVar()
        self.improvement_expected = tk.StringVar()
        self.improvement_reason = tk.StringVar()
        self.performance_feedback = tk.StringVar()
        self.performance_summary = tk.StringVar()
        self._label(parent, '업무 기록 기반 평가 (관리자 수동 입력 · AI 품질 자동 측정 아님)',
                    bg='#121c2d',size=12,weight='bold').pack(anchor='w')
        self._label(parent, '', textvariable=self.performance_summary, bg='#121c2d',wraplength=900).pack(anchor='w',pady=3)
        review_row = tk.Frame(parent, bg='#121c2d');review_row.pack(fill='x',pady=(5,2))
        for title,var,width in (('완료/차단 업무 ID',self.performance_task_id,9),
                                ('점수 1~5',self.performance_rating,4),
                                ('근거',self.performance_evidence,35)):
            tk.Label(review_row,text=title,bg='#121c2d',fg='#dce7ff').pack(side='left',padx=3)
            tk.Entry(review_row,textvariable=var,width=width).pack(side='left',padx=3)
        lesson_row=tk.Frame(parent,bg='#121c2d');lesson_row.pack(fill='x')
        tk.Label(lesson_row,text='회고/교훈',bg='#121c2d',fg='#dce7ff').pack(side='left',padx=3)
        tk.Entry(lesson_row,textvariable=self.performance_lesson,width=63).pack(side='left',padx=3)
        self.performance_review_button=tk.Button(lesson_row,text='수동 평가 저장',command=self._save_performance_review)
        self.performance_review_button.pack(side='left',padx=5)
        self.performance_reviews_tree=ttk.Treeview(parent,columns=('id','task','status','score','evidence'),show='headings',height=4)
        for key,title,width in (('id','평가 ID',75),('task','업무 ID',75),('status','평가 당시 상태',100),
                                ('score','수동 점수',80),('evidence','검증 근거',350)):
            self.performance_reviews_tree.heading(key,text=title)
            self.performance_reviews_tree.column(key,width=width,stretch=(key=='evidence'))
        self.performance_reviews_tree.pack(fill='x',pady=4)
        self.performance_reviews_tree.bind('<<TreeviewSelect>>',self._select_performance_review)
        propose_row=tk.Frame(parent,bg='#121c2d');propose_row.pack(fill='x',pady=(4,2))
        for title,var,width in (('평가 ID',self.performance_review_id,7),('개선 제목',self.improvement_title,30),
                                ('개선 행동',self.improvement_action,45)):
            tk.Label(propose_row,text=title,bg='#121c2d',fg='#dce7ff').pack(side='left',padx=3)
            tk.Entry(propose_row,textvariable=var,width=width).pack(side='left',padx=3)
        expected_row=tk.Frame(parent,bg='#121c2d');expected_row.pack(fill='x')
        tk.Label(expected_row,text='기대 효과(추정)',bg='#121c2d',fg='#dce7ff').pack(side='left',padx=3)
        tk.Entry(expected_row,textvariable=self.improvement_expected,width=53).pack(side='left',padx=3)
        self.improvement_create_button=tk.Button(expected_row,text='개선안 제안 (실행하지 않음)',command=self._create_task_improvement)
        self.improvement_create_button.pack(side='left',padx=5)
        self.performance_proposals_tree=ttk.Treeview(parent,columns=('id','review','title','status'),show='headings',height=4)
        for key,title,width in (('id','제안 ID',75),('review','평가 ID',75),('title','개선 내용',440),('status','결정 상태',90)):
            self.performance_proposals_tree.heading(key,text=title)
            self.performance_proposals_tree.column(key,width=width,stretch=(key=='title'))
        self.performance_proposals_tree.pack(fill='x',pady=4)
        decide_row=tk.Frame(parent,bg='#121c2d');decide_row.pack(fill='x',pady=4)
        tk.Label(decide_row,text='결정 근거',bg='#121c2d',fg='#dce7ff').pack(side='left')
        tk.Entry(decide_row,textvariable=self.improvement_reason,width=56).pack(side='left',padx=5)
        self.improvement_accept_button=tk.Button(decide_row,text='선택 개선안 채택',command=lambda:self._decide_task_improvement('accepted'))
        self.improvement_accept_button.pack(side='left',padx=3)
        self.improvement_reject_button=tk.Button(decide_row,text='선택 개선안 반려',command=lambda:self._decide_task_improvement('rejected'))
        self.improvement_reject_button.pack(side='left',padx=3)
        self.performance_refresh_button=tk.Button(decide_row,text='조회 갱신',command=self._refresh_performance)
        self.performance_refresh_button.pack(side='left',padx=3)
        self._label(parent,'',textvariable=self.performance_feedback,bg='#121c2d',wraplength=870).pack(anchor='w')
        self._refresh_performance()

    def _refresh_performance(self) -> None:
        try:
            summary=self.store.task_performance_summary()
            value=' · '.join(f'{key}: {summary[key]}' for key in ('todo','in_progress','blocked','done','cancelled'))
            ratio = '자료 없음' if summary['completion_percent'] is None else f"{summary['completion_percent']}%"
            self.performance_summary.set(f'내부 업무 상태: {value} · 취소 제외 완료 비율 {ratio} · 수동 평가 {summary["manual_reviews"]}건 · 미결 개선안 {summary["pending_proposals"]}건')
            for tree in (self.performance_reviews_tree,self.performance_proposals_tree):
                for item in tree.get_children():tree.delete(item)
            for r in self.store.list_task_performance_reviews():
                self.performance_reviews_tree.insert('','end',values=(r['id'],r['task_id'],r['task_status'],r['rating'],r['evidence']))
            for p in self.store.list_task_improvements():
                self.performance_proposals_tree.insert('','end',values=(p['id'],p['review_id'],p['title'],p['state']))
        except (ValueError,PermissionError) as exc:
            self.performance_feedback.set(str(exc))

    def _save_performance_review(self) -> None:
        try:
            rid=self.store.review_task_performance(int(self.performance_task_id.get()),
                int(self.performance_rating.get()),self.performance_evidence.get(),self.performance_lesson.get())
            self.performance_review_id.set(str(rid))
            self._refresh_performance()
            self.performance_feedback.set(f'수동 평가 #{rid} 저장 (AI 자동 평가 아님)')
        except (ValueError,PermissionError) as exc:
            self.performance_feedback.set(str(exc))

    def _select_performance_review(self,event=None) -> None:
        chosen=self.performance_reviews_tree.selection()
        if chosen:
            self.performance_review_id.set(str(self.performance_reviews_tree.item(chosen[0],'values')[0]))

    def _create_task_improvement(self) -> None:
        try:
            pid=self.store.create_task_improvement(int(self.performance_review_id.get()),
                self.improvement_title.get(),self.improvement_action.get(),self.improvement_expected.get())
            self._refresh_performance()
            self.performance_feedback.set(f'개선안 #{pid} 등록 (승인 전·후 모두 자동 실행 없음)')
        except (ValueError,PermissionError) as exc:
            self.performance_feedback.set(str(exc))

    def _decide_task_improvement(self, decision: str) -> None:
        chosen=self.performance_proposals_tree.selection()
        if not chosen:
            self.performance_feedback.set('결정할 개선안을 선택하세요.')
            return
        try:
            pid=int(self.performance_proposals_tree.item(chosen[0],'values')[0])
            self.store.decide_task_improvement(pid,decision,self.improvement_reason.get())
            self._refresh_performance()
            self.performance_feedback.set(f'개선안 #{pid} {"채택" if decision=="accepted" else "반려"}됨 (업무 자동 변경 없음)')
        except (ValueError,PermissionError) as exc:
            self.performance_feedback.set(str(exc))


    def _tool_registry_panel(self, parent: tk.Frame) -> None:
        from desktop.tool_registry import CATEGORIES
        from desktop.access_policy import CAPABILITIES
        self.registry_key = tk.StringVar()
        self.registry_name = tk.StringVar()
        self.registry_category = tk.StringVar(value='file')
        self.registry_capability = tk.StringVar(value='')
        self.registry_description = tk.StringVar()
        self.registry_retire_reason = tk.StringVar()
        self.registry_feedback = tk.StringVar()
        self._label(parent, '51단계: 도구 정보만 등록합니다. 실행·네트워크 연결·직원 권한 변경 없음.',
                    bg='#121c2d',wraplength=900).pack(anchor='w',pady=5)
        line = tk.Frame(parent,bg='#121c2d');line.pack(anchor='w',fill='x',pady=3)
        for label,var,width in (('도구 식별자',self.registry_key,24),('표시 이름',self.registry_name,29)):
            self._label(line,label,bg='#121c2d').pack(side='left',padx=3)
            tk.Entry(line,textvariable=var,width=width).pack(side='left',padx=4)
        line = tk.Frame(parent,bg='#121c2d');line.pack(anchor='w',fill='x',pady=3)
        self._label(line,'분류',bg='#121c2d').pack(side='left')
        ttk.Combobox(line,textvariable=self.registry_category,values=CATEGORIES,width=17,state='readonly').pack(side='left',padx=5)
        self._label(line,'요구 권한 (선택)',bg='#121c2d').pack(side='left')
        ttk.Combobox(line,textvariable=self.registry_capability,values=['']+list(CAPABILITIES),width=22,state='readonly').pack(side='left',padx=5)
        line = tk.Frame(parent,bg='#121c2d');line.pack(anchor='w',fill='x',pady=3)
        self._label(line,'설명',bg='#121c2d').pack(side='left')
        tk.Entry(line,textvariable=self.registry_description,width=78).pack(side='left',padx=5)
        self.registry_create_button=tk.Button(line,text='도구 정보 등록',command=self._register_ai_tool)
        self.registry_create_button.pack(side='left',padx=5)
        self.registry_tree=ttk.Treeview(parent,columns=('id','key','name','category','capability','state'),show='headings',height=9)
        for key,label,width in (('id','ID',55),('key','식별자',145),('name','이름',155),('category','분류',112),
                                ('capability','요구 권한',145),('state','상태',90)):
            self.registry_tree.heading(key,text=label)
            self.registry_tree.column(key,width=width,stretch=(key=='name'))
        self.registry_tree.pack(fill='both',expand=True,pady=6)
        line = tk.Frame(parent,bg='#121c2d');line.pack(anchor='w',fill='x',pady=3)
        self._label(line,'보관 사유',bg='#121c2d').pack(side='left')
        tk.Entry(line,textvariable=self.registry_retire_reason,width=48).pack(side='left',padx=5)
        self.registry_retire_button=tk.Button(line,text='선택 도구 보관',command=self._retire_ai_tool)
        self.registry_retire_button.pack(side='left',padx=5)
        self.registry_refresh_button=tk.Button(line,text='목록 새로고침',command=self._refresh_ai_tools)
        self.registry_refresh_button.pack(side='left',padx=5)
        self._label(parent,'',textvariable=self.registry_feedback,bg='#121c2d',wraplength=800).pack(anchor='w')
        self._refresh_ai_tools()

    def _refresh_ai_tools(self) -> None:
        try:
            for child in self.registry_tree.get_children():self.registry_tree.delete(child)
            for tool in self.store.list_registered_ai_tools(include_retired=True):
                self.registry_tree.insert('','end',values=(tool['id'],tool['tool_key'],tool['name'],
                    tool['category'],tool['required_capability'] or '없음',tool['state']))
        except (ValueError,PermissionError) as exc:
            self.registry_feedback.set(str(exc))

    def _register_ai_tool(self) -> None:
        try:
            tid=self.store.register_ai_tool(self.registry_key.get(),self.registry_name.get(),
                self.registry_category.get(),self.registry_description.get(),self.registry_capability.get())
            self._refresh_ai_tools()
            self.registry_feedback.set(f'도구 정보 #{tid} 등록됨 — 실행·권한 부여되지 않음')
        except (ValueError,PermissionError) as exc:
            self.registry_feedback.set(str(exc))

    def _retire_ai_tool(self) -> None:
        selection=self.registry_tree.selection()
        if not selection:
            self.registry_feedback.set('보관할 도구를 선택하세요.')
            return
        try:
            tid=int(self.registry_tree.item(selection[0],'values')[0])
            self.store.retire_registered_ai_tool(tid,self.registry_retire_reason.get())
            self._refresh_ai_tools()
            self.registry_feedback.set(f'도구 정보 #{tid} 보관됨 — 실행 기능 없음')
        except (ValueError,PermissionError) as exc:
            self.registry_feedback.set(str(exc))

    def _tool_approval_panel(self, parent: tk.Frame) -> None:
        self.tool_use_key = tk.StringVar()
        self.tool_use_tool = tk.StringVar()
        self.tool_use_employee = tk.StringVar()
        self.tool_use_purpose = tk.StringVar()
        self.tool_use_reason = tk.StringVar()
        self.tool_use_feedback = tk.StringVar()
        self._label(parent,'도구 요청·승인과 별도 실행: 관리자 명시 클릭 시 내장 회사/목표 SQLite 읽기만 실제 수행합니다.',
                    bg='#121c2d',wraplength=930).pack(anchor='w',pady=5)
        line = tk.Frame(parent,bg='#121c2d');line.pack(anchor='w',fill='x',pady=4)
        for name, var, width in (('요청 키',self.tool_use_key,23),('도구 ID',self.tool_use_tool,7),
                                  ('직원 ID',self.tool_use_employee,7)):
            self._label(line,name,bg='#121c2d').pack(side='left',padx=4)
            tk.Entry(line,textvariable=var,width=width).pack(side='left',padx=4)
        self._label(line,'목적',bg='#121c2d').pack(side='left',padx=4)
        tk.Entry(line,textvariable=self.tool_use_purpose,width=40).pack(side='left',padx=4)
        self.tool_use_request_button = tk.Button(line,text='승인 요청 기록',command=self._create_tool_use_request)
        self.tool_use_request_button.pack(side='left',padx=5)
        self.tool_use_tree=ttk.Treeview(parent,columns=('id','key','tool','employee','purpose','status'),
                                        show='headings',height=10)
        for key,label,width in (('id','ID',50),('key','요청 키',130),('tool','도구',170),
                                ('employee','직원',110),('purpose','목적',260),('status','상태',90)):
            self.tool_use_tree.heading(key,text=label)
            self.tool_use_tree.column(key,width=width,stretch=(key=='purpose'))
        self.tool_use_tree.pack(fill='both',expand=True,pady=6)
        line=tk.Frame(parent,bg='#121c2d');line.pack(anchor='w',fill='x',pady=3)
        self._label(line,'결정 사유',bg='#121c2d').pack(side='left',padx=3)
        tk.Entry(line,textvariable=self.tool_use_reason,width=50).pack(side='left',padx=3)
        self.tool_use_approve_button=tk.Button(line,text='선택 요청 승인',command=lambda:self._decide_tool_use('approved'))
        self.tool_use_approve_button.pack(side='left',padx=3)
        self.tool_use_deny_button=tk.Button(line,text='선택 요청 반려',command=lambda:self._decide_tool_use('denied'))
        self.tool_use_deny_button.pack(side='left',padx=3)
        self.tool_use_check_button=tk.Button(line,text='사전 권한 재검사',command=self._check_tool_use)
        self.tool_use_check_button.pack(side='left',padx=3)
        tk.Button(line,text='목록 새로고침',command=self._refresh_tool_use).pack(side='left',padx=3)
        readbar=tk.Frame(parent,bg='#121c2d');readbar.pack(anchor='w',fill='x',pady=3)
        self.tool_use_execute_button=tk.Button(readbar,text='승인된 로컬 읽기 도구 실제 실행',
            command=self._execute_approved_read_tool)
        self.tool_use_execute_button.pack(side='left',padx=3)
        tk.Button(readbar,text='실제 실행·무결성 감사 조회',
            command=self._show_approved_read_tool_history).pack(side='left',padx=3)
        self.tool_windows_version_button=tk.Button(readbar,text='승인된 Windows 버전 명령 실제 실행',
            command=self._execute_approved_windows_version_tool)
        self.tool_windows_version_button.pack(side='left',padx=3)
        tk.Button(readbar,text='Windows 명령 실행 감사',
            command=self._show_approved_windows_version_history).pack(side='left',padx=3)
        recoverybar=tk.Frame(parent,bg='#121c2d');recoverybar.pack(anchor='w',fill='x',pady=3)
        self.tool_windows_stale_button=tk.Button(recoverybar,
            text='중단된 Windows 명령 실행 감사 복구',command=self._inspect_stale_windows_tool)
        self.tool_windows_stale_button.pack(side='left',padx=3)
        tk.Button(recoverybar,text='명령 복구 감사 기록',
            command=self._show_windows_tool_recoveries).pack(side='left',padx=3)
        self._label(parent,'',textvariable=self.tool_use_feedback,bg='#121c2d',wraplength=940).pack(anchor='w')
        self._refresh_tool_use()

    def _refresh_tool_use(self) -> None:
        try:
            for item in self.tool_use_tree.get_children():self.tool_use_tree.delete(item)
            for item in self.store.list_ai_tool_use_requests():
                self.tool_use_tree.insert('','end',values=(item['id'],item['request_key'],
                    item['tool_name'],item['employee_name'],item['purpose'],item['status']))
        except (ValueError,PermissionError) as exc:
            self.tool_use_feedback.set(str(exc))

    def _create_tool_use_request(self) -> None:
        try:
            rid=self.store.request_ai_tool_use(self.tool_use_key.get(),
                int(self.tool_use_tool.get()),int(self.tool_use_employee.get()),self.tool_use_purpose.get())
            self._refresh_tool_use()
            self.tool_use_feedback.set(f'요청 #{rid} 저장. 현재 승인·실행 없음')
        except (ValueError,PermissionError) as exc:
            self.tool_use_feedback.set(str(exc))

    def _selected_tool_use(self) -> int:
        selection=self.tool_use_tree.selection()
        if not selection:
            raise ValueError('먼저 요청을 선택하세요.')
        return int(self.tool_use_tree.item(selection[0],'values')[0])

    def _decide_tool_use(self, decision: str) -> None:
        try:
            rid=self._selected_tool_use()
            self.store.decide_ai_tool_use(rid,decision,self.tool_use_reason.get())
            self._refresh_tool_use()
            self.tool_use_feedback.set(f'요청 #{rid} {decision} — 실제 도구 실행 없음')
        except (ValueError,PermissionError) as exc:
            self.tool_use_feedback.set(str(exc))

    def _check_tool_use(self) -> None:
        try:
            rid=self._selected_tool_use()
            result=self.store.check_ai_tool_use(rid)
            self.tool_use_feedback.set(f'요청 #{rid} 사전 검사: {"조건 충족" if result["allowed"] else "거부"}. '
                f'{result["reason"]} · 실제 도구 실행 없음')
        except (ValueError,PermissionError) as exc:
            self.tool_use_feedback.set(str(exc))

    def _execute_approved_read_tool(self) -> None:
        try:
            rid=self._selected_tool_use()
            if not messagebox.askyesno('로컬 도구 실제 실행 승인',
                    f'요청 #{rid}의 현재 승인·직원 권한·비상정지를 재검사하고\n'
                    '회사 또는 목표 SQLite 데이터를 실제로 조회합니다.\n'
                    '외부 프로그램·파일·네트워크·결제 실행은 없습니다. 진행할까요?'):
                return
            result=self.store.execute_approved_local_read_tool(rid)
            self.tool_use_feedback.set(
                f'요청 #{rid} 로컬 SQLite 실제 조회 완료 · 실행 #{result["execution_id"]} '
                f'· 중복={result["already_executed"]} · SHA256 {result["sha256"][:16]}…')
        except (ValueError,PermissionError,RuntimeError) as exc:
            self.tool_use_feedback.set('승인된 로컬 읽기 실행 실패: '+str(exc))

    def _show_approved_read_tool_history(self) -> None:
        try:
            import json
            rows=self.store.approved_local_read_tool_history(limit=20)
            content='\n'.join(f'#{r["execution_id"]} 요청 {r["request_id"]} '
                f'직원 {r["employee_id"]} / {r["tool_key"]} / SHA256 {r["sha256"][:16]}…'
                for r in rows) or '아직 실제 읽기 실행 증빙이 없습니다.'
            messagebox.showinfo('승인된 로컬 읽기 도구 실행 감사',content)
        except (ValueError,PermissionError,RuntimeError) as exc:
            self.tool_use_feedback.set('도구 실행 감사 조회 실패: '+str(exc))

    def _execute_approved_windows_version_tool(self) -> None:
        try:
            rid=self._selected_tool_use()
            if not messagebox.askyesno('Windows 기본 명령 실행 확인',
                    f'요청 #{rid}의 관리자 승인과 직원 권한을 재검사한 후\n'
                    'Windows 자체 cmd.exe /d /c ver 명령을 1회 실행합니다.\n'
                    '임의 명령·네트워크·파일 수정·결제는 실행하지 않습니다. 계속할까요?'):
                return
            result=self.store.execute_approved_windows_version_tool(rid)
            self.tool_use_feedback.set(
                f'요청 #{rid} Windows 실제 명령 실행 완료 · #{result["execution_id"]} '
                f'· 중복={result["already_executed"]} · SHA256 {result["sha256"][:16]}…')
        except (ValueError,PermissionError,RuntimeError,OSError) as exc:
            self.tool_use_feedback.set('Windows 명령 실행 실패: '+str(exc))

    def _show_approved_windows_version_history(self) -> None:
        try:
            rows=self.store.approved_windows_version_tool_history(limit=20)
            content='\n'.join(f'#{r["execution_id"]} 요청 {r["request_id"]} '
                f'직원 {r["employee_id"]} / {r["state"]} / '
                f'SHA256 {r["sha256"][:16]}… / {r["error_code"]}'
                for r in rows) or 'Windows 명령 실행 기록이 없습니다.'
            messagebox.showinfo('Windows 명령 실제 실행 감사',content)
        except (ValueError,PermissionError,RuntimeError) as exc:
            self.tool_use_feedback.set('Windows 명령 감사 조회 실패: '+str(exc))

    def _inspect_stale_windows_tool(self) -> None:
        try:
            rid=self._selected_tool_use()
            if not messagebox.askyesno('중단된 Windows 명령 복구',
                    f'요청 #{rid}의 중단된 명령 실행 감사만 취소 상태로 확정합니다.\\n'
                    '180초 이내의 다른 창 실행은 보호하며 명령은 다시 실행되지 않습니다.\\n'
                    'OS 프로세스 종료를 보장하는 기능이 아닙니다. 직접 확인하셨습니까?'):
                return
            reason=simpledialog.askstring('관리자 복구 사유',
                '실제 실행 상태와 다른 Windows 창을 확인한 내용을 5자 이상 입력하세요.')
            if reason is None:
                return
            result=self.store.inspect_and_cancel_stale_windows_tool(rid,True,reason)
            self.tool_use_feedback.set(f'요청 #{rid} 감사 복구: {result["state"]}, 재실행 없음')
        except (ValueError,PermissionError,RuntimeError) as exc:
            self.tool_use_feedback.set('Windows 중단 기록 복구 실패: '+str(exc))

    def _show_windows_tool_recoveries(self) -> None:
        try:
            rows=self.store.approved_windows_tool_recovery_history(limit=20)
            messagebox.showinfo('Windows 명령 수동 복구 감사',
                '\\n'.join(f'#{r["id"]}: 요청 {r["request_id"]} / '
                          f'감사 #{r["execution_id"]} / 경과 {r["elapsed_seconds"]}초 '
                          f'/ 사유 {r["operator_note"]}' for r in rows)
                or '수동 복구 감사 기록 없음')
        except (ValueError,PermissionError,RuntimeError) as exc:
            self.tool_use_feedback.set('Windows 복구 기록 조회 실패: '+str(exc))

    def _managed_documents_panel(self, parent: tk.Frame) -> None:
        self.document_name = tk.StringVar()
        self.document_feedback = tk.StringVar()
        self.document_selected_id = None
        self.document_loaded_version = None
        self._label(parent, '53단계: 관리자 수동 UTF-8 텍스트 파일 생성·수정 (txt/md/csv/json, 최대 128KiB)',
                    bg='#121c2d',wraplength=900).pack(anchor='w',pady=4)
        self._label(parent, '저장 위치: 데이터 폴더/managed_documents · 외부 경로·파일 실행·AI 자동 수정 불가',
                    bg='#121c2d',fg='#bfcfe5',wraplength=920).pack(anchor='w',pady=3)
        line=tk.Frame(parent,bg='#121c2d');line.pack(anchor='w',fill='x',pady=5)
        self._label(line,'파일명',bg='#121c2d').pack(side='left',padx=4)
        tk.Entry(line,textvariable=self.document_name,width=32).pack(side='left',padx=4)
        self.document_create_button=tk.Button(line,text='새 파일 생성',command=self._create_managed_document)
        self.document_create_button.pack(side='left',padx=5)
        self.document_update_button=tk.Button(line,text='선택 파일 수정 저장',command=self._update_managed_document)
        self.document_update_button.pack(side='left',padx=5)
        tk.Button(line,text='목록 새로고침',command=self._refresh_managed_documents).pack(side='left',padx=5)
        self.document_tree=ttk.Treeview(parent,columns=('id','filename','version','updated'),show='headings',height=6)
        for key,title,width in (('id','ID',58),('filename','파일명',300),('version','버전',70),('updated','갱신 시각',190)):
            self.document_tree.heading(key,text=title)
            self.document_tree.column(key,width=width,stretch=(key=='filename'))
        self.document_tree.pack(fill='x',pady=5)
        self.document_tree.bind('<<TreeviewSelect>>',self._load_managed_document)
        self._label(parent,'파일 내용 (선택한 파일을 불러온 후 수정 저장)',bg='#121c2d').pack(anchor='w')
        self.document_content=tk.Text(parent,height=8,undo=True,wrap='word',font=('Consolas',10))
        self.document_content.pack(fill='both',expand=True,pady=5)
        self._label(parent,'',textvariable=self.document_feedback,bg='#121c2d',wraplength=930).pack(anchor='w')
        self._refresh_managed_documents()

    def _refresh_managed_documents(self) -> None:
        try:
            for item in self.document_tree.get_children():self.document_tree.delete(item)
            for doc in self.store.list_managed_documents():
                self.document_tree.insert('','end',values=(doc['id'],doc['filename'],doc['version'],doc['updated_at']))
        except (ValueError,PermissionError,OSError) as exc:
            self.document_feedback.set(str(exc))

    def _load_managed_document(self, _event=None) -> None:
        chosen=self.document_tree.selection()
        if not chosen:
            return
        try:
            doc_id=int(self.document_tree.item(chosen[0],'values')[0])
            doc=self.store.read_managed_document(doc_id)
            self.document_selected_id=doc_id
            self.document_loaded_version=doc['version']
            self.document_name.set(doc['filename'])
            self.document_content.delete('1.0','end')
            self.document_content.insert('1.0',doc['content'])
            self.document_feedback.set(f'파일 #{doc_id} / 버전 {doc["version"]} 불러옴. 수정 시 충돌 검사 적용')
        except (ValueError,PermissionError,OSError,UnicodeError) as exc:
            self.document_selected_id=None
            self.document_loaded_version=None
            self.document_feedback.set(str(exc))

    def _create_managed_document(self) -> None:
        try:
            doc_id=self.store.create_managed_document(self.document_name.get(),
                self.document_content.get('1.0','end-1c'))
            self.document_selected_id=doc_id
            self.document_loaded_version=1
            self._refresh_managed_documents()
            self.document_feedback.set(f'로컬 파일 #{doc_id} 생성 완료 (AI 자동 실행 없음)')
        except (ValueError,PermissionError,OSError,UnicodeError) as exc:
            self.document_feedback.set(str(exc))

    def _update_managed_document(self) -> None:
        if self.document_selected_id is None or self.document_loaded_version is None:
            self.document_feedback.set('수정 전에 목록에서 파일을 선택하고 불러오세요.')
            return
        try:
            version=self.store.update_managed_document(self.document_selected_id,
                self.document_content.get('1.0','end-1c'),self.document_loaded_version)
            self.document_loaded_version=version
            self._refresh_managed_documents()
            self.document_feedback.set(f'파일 #{self.document_selected_id} 버전 {version} 저장 (이전 내용은 SQLite에 보존)')
        except (ValueError,PermissionError,OSError,UnicodeError) as exc:
            self.document_feedback.set(str(exc))


    def _offline_browser_panel(self, parent: tk.Frame) -> None:
        self.store.require_permission('agents:manage')
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '55단계 · 허용된 로컬 브라우저 작업', size=16).pack(anchor='w')
        self._label(panel, '선택한 HTML을 평문으로 정리해 로컬 Chromium으로 읽고 검색합니다. '
                    'JavaScript/외부 리소스/원격 URL은 열지 않습니다. 브라우저·Playwright는 사전 설치 필요.',
                    fg='#bfcfe5', wraplength=780, justify='left').pack(anchor='w', pady=8)
        self.browser_html_path = tk.StringVar(value='')
        self.browser_find_text = tk.StringVar(value='')
        self.browser_feedback = tk.StringVar(value='HTML 파일을 선택하고 명시적으로 실행하세요.')
        self._label(panel, '로컬 HTML 파일').pack(anchor='w')
        tk.Entry(panel, textvariable=self.browser_html_path, width=87, state='readonly').pack(fill='x', pady=4)
        self.browser_choose_button = tk.Button(panel, text='로컬 HTML 선택', command=self._choose_offline_browser_html)
        self.browser_choose_button.pack(anchor='w', pady=4)
        self._label(panel, '문자열 찾기 (선택, 120자 이하)').pack(anchor='w', pady=(8, 0))
        tk.Entry(panel, textvariable=self.browser_find_text, width=55).pack(anchor='w', pady=4)
        self.browser_run_button = tk.Button(panel, text='허용된 로컬 브라우저 작업 실행',
                                            command=self._run_offline_browser_task)
        self.browser_run_button.pack(anchor='w', pady=8)
        self._label(panel, '', textvariable=self.browser_feedback, wraplength=780,
                    justify='left', fg='#8ee4b7').pack(anchor='w', pady=6)
        self._label(panel, '외부 접속이 차단된 브라우저 문서 작업만 지원합니다. '
                    '사용 중인 브라우저 자체의 OS 수준 통신 차단은 보장하지 않습니다.',
                    fg='#f7cb92', wraplength=780).pack(anchor='w')

    def _choose_offline_browser_html(self) -> None:
        self.store.require_permission('agents:manage')
        path = filedialog.askopenfilename(title='로컬 HTML 선택',
                    filetypes=[('HTML', '*.html *.htm')])
        if path:
            self.browser_html_path.set(path)

    def _run_offline_browser_task(self) -> None:
        from desktop.offline_browser import inspect_in_browser
        try:
            self.store.require_permission('agents:manage')
            result = inspect_in_browser(Path(self.browser_html_path.get()),
                                        find_text=self.browser_find_text.get())
            self.browser_feedback.set(
                f"로컬 브라우저 성공 · 제목: {result['title']} · 글자: {result['characters']} · "
                f"검색 일치: {result['matches']}회 · 발췌: {result['preview']}")
        except (ValueError, RuntimeError, PermissionError) as exc:
            self.browser_feedback.set(f'로컬 브라우저 작업 거부/실패: {exc}')

    def _code_authoring_panel(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        self.code_filename = tk.StringVar(value='sample.py')
        self.code_model_id = tk.StringVar(value='')
        self.code_request = tk.StringVar(value='')
        self.code_feedback = tk.StringVar(value='로컬 모델 초안은 실행되지 않습니다. 관리자 사전 검토 후에만 저장합니다.')
        self.code_artifact_id = None
        self.code_expected_version = 0
        self.code_generated_source = None
        self.code_preview_token = None
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '56단계 · 로컬 AI 코드 작성·수정 (실모델 생성 결과 검증 대기)',size=16).pack(anchor='w')
        self._label(panel, '선택한 로컬 모델 CLI로 Python 초안을 생성하거나 직접 입력할 수 있습니다. '
                    '실행/설치/프로젝트 소스 수정 없음. 승인된 .py만 개인 code_drafts 폴더에 저장됩니다.',
                    fg='#bfcfe5', wraplength=820).pack(anchor='w',pady=5)
        row = tk.Frame(panel, bg='#1c2a40');row.pack(fill='x',pady=3)
        self._label(row,'파일명 (.py)').pack(side='left')
        tk.Entry(row,textvariable=self.code_filename,width=24).pack(side='left',padx=5)
        self._label(row,'모델 ID').pack(side='left')
        tk.Entry(row,textvariable=self.code_model_id,width=7).pack(side='left',padx=5)
        self._label(row,'요청').pack(side='left')
        tk.Entry(row,textvariable=self.code_request,width=42).pack(side='left',padx=5)
        buttons = tk.Frame(panel,bg='#1c2a40'); buttons.pack(fill='x',pady=6)
        self.code_load_button = tk.Button(buttons,text='기존 코드 불러오기',command=self._load_code_authoring)
        self.code_load_button.pack(side='left',padx=3)
        self.code_generate_button = tk.Button(buttons,text='로컬 모델로 초안 생성 (수동 실행)',command=self._generate_code_authoring)
        self.code_generate_button.pack(side='left',padx=3)
        self.code_preview_button = tk.Button(buttons,text='구문·차이 미리보기',command=self._preview_code_authoring)
        self.code_preview_button.pack(side='left',padx=3)
        self.code_save_button = tk.Button(buttons,text='검토한 코드 승인 저장',command=self._save_code_authoring)
        self.code_save_button.pack(side='left',padx=3)
        self.code_editor = tk.Text(panel,height=11,width=95,wrap='none')
        self.code_editor.pack(fill='both',expand=True,pady=4)
        self.code_diff = tk.Text(panel,height=6,width=95,wrap='none',state='disabled')
        self.code_diff.pack(fill='both',expand=True,pady=4)
        self._label(panel,'코드를 실행하지 않습니다. 정적 Python 구문 검사만 수행하며 안전한 코드인지 보증하지 않습니다.',
                    fg='#f7cb92',wraplength=820).pack(anchor='w',pady=2)
        self._label(panel,'',textvariable=self.code_feedback,wraplength=820,fg='#8ee4b7').pack(anchor='w')

    def _load_code_authoring(self) -> None:
        try:
            self.store.require_permission('company:manage')
            from desktop.code_authoring import _filename
            name = _filename(self.code_filename.get())
            matches=[x for x in self.store.list_code_drafts() if x['filename'].casefold()==name.casefold()]
            if matches:
                current=self.store.read_code_draft(matches[0]['id'])
                self.code_artifact_id=current['id']
                self.code_expected_version=current['version']
                self.code_editor.delete('1.0','end'); self.code_editor.insert('1.0',current['source'])
                self.code_feedback.set(f"불러옴: 버전 {current['version']} · 읽기 전용 검증 후 변경 가능")
            else:
                self.code_artifact_id=None; self.code_expected_version=0
                self.code_editor.delete('1.0','end')
                self.code_feedback.set('새 Python 파일: 작성 후 구문·차이 미리보기를 누르세요.')
            self.code_generated_source=None
            self.code_preview_token=None
        except (ValueError,PermissionError) as exc:
            self.code_feedback.set(f'코드 불러오기 거부: {exc}')

    def _generate_code_authoring(self) -> None:
        try:
            self.store.require_permission('company:manage')
            from desktop.code_authoring import generate_local_draft
            existing=self.code_editor.get('1.0','end-1c')
            code=generate_local_draft(self.store,int(self.code_model_id.get()),self.code_request.get(),existing)
            self.code_editor.delete('1.0','end');self.code_editor.insert('1.0',code)
            self.code_generated_source=code
            self.code_preview_token=None
            self.code_feedback.set('로컬 모델 응답 초안만 표시했습니다. 반드시 차이 미리보기 후 직접 승인하세요.')
        except (ValueError,PermissionError,RuntimeError,TimeoutError,InterruptedError) as exc:
            self.code_feedback.set(f'모델 초안 생성 실패/거부: {exc}')

    def _preview_code_authoring(self) -> None:
        try:
            self.store.require_permission('company:manage')
            from desktop.code_authoring import _filename, diff_preview
            import hashlib
            filename=_filename(self.code_filename.get())
            code=self.code_editor.get('1.0','end-1c')
            original=''
            if self.code_expected_version:
                current=self.store.read_code_draft(self.code_artifact_id)
                if current['version']!=self.code_expected_version or current['filename']!=filename:
                    raise ValueError('원본 버전이 변경됐습니다. 다시 불러오세요.')
                original=current['source']
            elif any(row['filename'].casefold()==filename.casefold() for row in self.store.list_code_drafts()):
                raise ValueError('동일 파일명이 있습니다. 기존 코드를 불러오세요.')
            diff=diff_preview(original,code,filename)
            self.code_diff.configure(state='normal')
            self.code_diff.delete('1.0','end');self.code_diff.insert('1.0',diff or '(변경 내용 없음)')
            self.code_diff.configure(state='disabled')
            self.code_preview_token=(filename,self.code_expected_version,hashlib.sha256(code.encode('utf-8')).hexdigest())
            self.code_feedback.set('구문·차이 미리보기 완료. 코드의 안전성은 검증되지 않았습니다. 저장을 별도 승인해야 합니다.')
        except (ValueError,PermissionError,UnicodeError) as exc:
            self.code_preview_token=None
            self.code_feedback.set(f'미리보기 실패/거부: {exc}')

    def _save_code_authoring(self) -> None:
        try:
            self.store.require_permission('company:manage')
            from desktop.code_authoring import _filename
            import hashlib
            filename=_filename(self.code_filename.get())
            code=self.code_editor.get('1.0','end-1c')
            token=(filename,self.code_expected_version,hashlib.sha256(code.encode('utf-8')).hexdigest())
            if self.code_preview_token is None or self.code_preview_token!=token:
                raise ValueError('수정된 내용을 다시 미리보기한 후 승인하세요.')
            if not messagebox.askyesno('코드 저장 승인',
                       f'{filename}을(를) 개인 코드 작업 공간에 저장하시겠습니까?\n생성된 코드는 실행되지 않습니다.'):
                self.code_feedback.set('관리자가 저장을 취소했습니다.');return
            result=self.store.save_code_draft(filename,code,self.code_expected_version,
                                              from_model=(self.code_generated_source==code))
            self.code_expected_version=result['version'];self.code_artifact_id=result['id']
            self.code_preview_token=None
            self.code_feedback.set(f"승인 저장 완료 · 버전 {result['version']} · SHA-256 {result['digest'][:16]}... (실행 없음)")
        except (ValueError,PermissionError,UnicodeError,OSError) as exc:
            self.code_feedback.set(f'코드 저장 거부: {exc}')

    def _restricted_code_panel(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        self.restricted_id = tk.StringVar(value='')
        self.restricted_feedback = tk.StringVar(value='코드 저장 후 ID를 입력하세요. 아무 코드나 실행하는 Python 샌드박스가 아닙니다.')
        panel=self._panel(parent);panel.pack(fill='both',expand=True)
        self._label(panel,'57단계 · 제한형 Python 코드 테스트 (OS 격리 미검증)',size=16).pack(anchor='w')
        self._label(panel, '관리자가 저장·승인한 .py의 단순 함수·산술·if와 assert만 해석합니다. '
                    'import, exec, eval, 파일/네트워크, 반복문 및 임의 Python 구문은 거부합니다.',
                    wraplength=850,fg='#f7cb92').pack(anchor='w',pady=5)
        line=tk.Frame(panel,bg='#1c2a40');line.pack(fill='x',pady=5)
        self._label(line,'저장된 코드 ID').pack(side='left')
        tk.Entry(line,textvariable=self.restricted_id,width=8).pack(side='left',padx=8)
        self.restricted_run_button=tk.Button(line,text='검사 범위 확인 후 수동 실행',command=self._run_restricted_code)
        self.restricted_run_button.pack(side='left',padx=3)
        self.restricted_history_button=tk.Button(line,text='실행 기록 조회',command=self._history_restricted_code)
        self.restricted_history_button.pack(side='left',padx=3)
        self._label(panel,'테스트용 assert 예: assert answer() == 7').pack(anchor='w')
        self.restricted_assertions=tk.Text(panel,height=6,width=90)
        self.restricted_assertions.pack(fill='both',expand=True,pady=4)
        self.restricted_assertions.insert('1.0','assert answer() == 7\n')
        self._label(panel,'',textvariable=self.restricted_feedback,fg='#8ee4b7',wraplength=850).pack(anchor='w')

    def _run_restricted_code(self) -> None:
        try:
            self.store.require_permission('company:manage')
            artifact_id=int(self.restricted_id.get())
            assertions=self.restricted_assertions.get('1.0','end-1c')
            if not messagebox.askyesno('제한형 코드 검사 승인',
                        '허용된 Python AST 일부만 계산하고 결과를 SQLite에 기록합니다.\n'
                        'OS 수준 샌드박스나 임의 Python 안전 실행 기능은 아닙니다. 실행하시겠습니까?'):
                self.restricted_feedback.set('관리자가 검사 실행을 취소했습니다.');return
            result=self.store.run_restricted_code_tests(artifact_id,assertions)
            self.restricted_feedback.set(
                f"제한형 검사 #{result['run_id']}: {result['passed']}/{result['total']} 통과 · " +
                ', '.join(f"{r['case']}번:{r['detail']}" for r in result['results'][:8]))
        except (ValueError,PermissionError,OverflowError) as exc:
            self.restricted_feedback.set(f'제한형 검사 거부/실패: {exc}')

    def _history_restricted_code(self) -> None:
        try:
            rows=self.store.list_restricted_code_tests(int(self.restricted_id.get()))
            self.restricted_feedback.set('검사 기록: '+(
                ' / '.join(f"#{r['id']} v{r['version']} {r['passed']}/{r['total']}" for r in rows[:6])
                if rows else '없음'))
        except (ValueError,PermissionError) as exc:
            self.restricted_feedback.set(f'검사 기록 조회 거부: {exc}')

    def _media_adapter_panel(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        adapters=self.store.list_media_adapters()
        self.media_file=tk.StringVar(value='')
        self.media_adapter=tk.StringVar(value=adapters[0]['key'])
        self.media_feedback=tk.StringVar(value='로컬 파일을 직접 선택하고 승인해야 헤더/구조 검사 및 SHA-256 기록을 수행합니다.')
        panel=self._panel(parent);panel.pack(fill='both',expand=True)
        self._label(panel,'58단계 · 로컬 이미지·영상·문서 어댑터 (읽기 전용)',size=16).pack(anchor='w')
        self._label(panel,'7개 내장 어댑터 · 20MiB 상한 · 외부 프로그램/서버 호출 없음. '
                    '이미지 생성·영상 편집·PDF 렌더링 또는 실제 AI 도구 연동은 아직 지원하지 않습니다.',
                    fg='#f7cb92',wraplength=850).pack(anchor='w',pady=6)
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=5)
        self._label(row,'어댑터').pack(side='left')
        self.media_adapter_select=ttk.Combobox(row,textvariable=self.media_adapter,
                            values=[a['key'] for a in adapters],state='readonly',width=22)
        self.media_adapter_select.pack(side='left',padx=8)
        tk.Button(row,text='로컬 파일 선택',command=self._media_choose_file).pack(side='left',padx=5)
        self._label(panel,'',textvariable=self.media_file,fg='#bfcfe5',wraplength=850).pack(anchor='w')
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=10)
        self.media_inspect_button=tk.Button(row,text='관리자 승인 후 검사',command=self._media_inspect_file)
        self.media_inspect_button.pack(side='left',padx=4)
        tk.Button(row,text='검사 이력',command=self._media_show_history).pack(side='left',padx=4)
        self._label(panel,'',textvariable=self.media_feedback,fg='#8ee4b7',wraplength=850).pack(anchor='w')

    def _media_choose_file(self) -> None:
        try:
            self.store.require_permission('company:manage')
            filename=filedialog.askopenfilename(title='검사할 로컬 미디어/문서 파일 선택')
            if filename:
                self.media_file.set(filename)
                self.media_feedback.set('파일을 선택했습니다. 검사/기록은 아직 실행되지 않았습니다.')
        except PermissionError as exc:
            self.media_feedback.set(f'권한 거부: {exc}')

    def _media_inspect_file(self) -> None:
        try:
            self.store.require_permission('company:manage')
            filename=self.media_file.get()
            adapter=self.media_adapter.get()
            if not filename:
                raise ValueError('검사할 로컬 파일을 선택하세요.')
            if not messagebox.askyesno('로컬 파일 검사 승인',
                 f'어댑터: {adapter}\n파일: {filename}\n읽기 전용 검사 결과(파일명/해시)를 SQLite에 기록합니다. 진행합니까?'):
                self.media_feedback.set('검사를 취소했습니다.');return
            result=self.store.inspect_media_file(filename,adapter)
            self.media_feedback.set(f"검사 #{result['id']} · {result['category']} · "
                  f"{result['byte_size']}바이트 · SHA-256 {result['sha256'][:16]}... · {result['details']}")
        except (ValueError,PermissionError,OSError) as exc:
            self.media_feedback.set(f'검사 거부/실패: {exc}')

    def _media_show_history(self) -> None:
        try:
            rows=self.store.media_inspection_history(6)
            self.media_feedback.set('최근 검사: '+(' / '.join(
                f"#{r['id']} {r['adapter_key']} {r['filename']}" for r in rows) if rows else '없음'))
        except (ValueError,PermissionError) as exc:
            self.media_feedback.set(f'이력 조회 거부: {exc}')

    def _service_drafts_panel(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        contracts = self.store.list_service_contracts()
        self.service_kind = tk.StringVar(value='email')
        self.service_target = tk.StringVar(value='')
        self.service_title = tk.StringVar(value='')
        self.service_draft_id = tk.StringVar(value='')
        self.service_feedback = tk.StringVar(value='전송·게시·로그인·계정 연결은 구현하지 않았습니다.')
        panel = self._panel(parent);panel.pack(fill='both',expand=True)
        self._label(panel,'59단계 · 외부 서비스 연동 초안 (전송 불가)',size=16).pack(anchor='w')
        self._label(panel,'이메일·게시·외부 서비스 연결 규약만 정의합니다. 모든 연결은 비활성화되어 있습니다. '
                    '초안과 검토 기록은 암호화되지 않은 로컬 SQLite에 저장되므로 비밀번호·토큰·개인정보를 넣지 마세요.',
                    fg='#f7cb92',wraplength=850).pack(anchor='w',pady=5)
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=4)
        self._label(row,'유형').pack(side='left')
        ttk.Combobox(row,textvariable=self.service_kind,values=[c['key'] for c in contracts],
                     state='readonly',width=13).pack(side='left',padx=6)
        self._label(row,'대상(이메일 주소 또는 로컬 식별자)').pack(side='left',padx=4)
        tk.Entry(row,textvariable=self.service_target,width=34).pack(side='left',padx=4)
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=4)
        self._label(row,'제목').pack(side='left')
        tk.Entry(row,textvariable=self.service_title,width=72).pack(side='left',padx=6)
        self._label(panel,'본문(최대 5,000자, 로컬 보관 전용)').pack(anchor='w')
        self.service_body=tk.Text(panel,height=5,width=80,wrap='word')
        self.service_body.pack(fill='x',pady=4)
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=4)
        self.service_prepare_button=tk.Button(row,text='관리자 승인 후 로컬 초안 저장',command=self._service_prepare)
        self.service_prepare_button.pack(side='left',padx=4)
        self._label(row,'초안 ID').pack(side='left',padx=3)
        tk.Entry(row,textvariable=self.service_draft_id,width=8).pack(side='left')
        tk.Button(row,text='초안 미리보기',command=self._service_preview).pack(side='left',padx=4)
        self.service_review_button=tk.Button(row,text='로컬 검토 완료(전송 아님)',command=self._service_review)
        self.service_review_button.pack(side='left',padx=4)
        tk.Button(row,text='검토 거부',command=self._service_reject).pack(side='left',padx=4)
        tk.Button(row,text='이력',command=self._service_history).pack(side='left',padx=4)
        self._label(panel,'',textvariable=self.service_feedback,fg='#8ee4b7',wraplength=850,
                    justify='left').pack(anchor='w',pady=7)

    def _service_prepare(self) -> None:
        try:
            self.store.require_permission('company:manage')
            kind=self.service_kind.get();target=self.service_target.get();title=self.service_title.get()
            body=self.service_body.get('1.0','end-1c')
            from desktop.offline_service_integrations import validate_draft
            validate_draft(kind,target,title,body)
            if not messagebox.askyesno('오프라인 초안 저장 승인',
                    f'{kind} · {target}\n제목: {title}\n\nSQLite에 로컬 초안만 저장합니다. '
                    '이메일 전송·게시·서비스 요청은 절대 실행하지 않습니다. 저장합니까?'):
                self.service_feedback.set('초안 저장을 취소했습니다.');return
            result=self.store.prepare_service_draft(kind,target,title,body)
            self.service_draft_id.set(str(result['id']))
            self.service_feedback.set(f"초안 #{result['id']} 저장 · SHA-256 {result['sha256'][:16]}... "
                                      '· 전송/게시 불가')
        except (ValueError,PermissionError) as exc:
            self.service_feedback.set(f'초안 저장 거부: {exc}')

    def _service_preview(self) -> None:
        try:
            draft=self.store.service_draft_detail(int(self.service_draft_id.get()))
            self.service_feedback.set(f"초안 #{draft['id']} [{draft['state']}] "
                f"{draft['kind']} → {draft['target']} / {draft['title']} / 본문: "
                f"{draft['body'][:250]}" + ('…' if len(draft['body'])>250 else '') +
                ' (로컬 저장, 외부 전송 없음)')
        except (ValueError,PermissionError) as exc:
            self.service_feedback.set(f'초안 조회 거부: {exc}')

    def _service_review(self) -> None:
        self._service_finalize(True)

    def _service_reject(self) -> None:
        self._service_finalize(False)

    def _service_finalize(self, accept: bool) -> None:
        try:
            self.store.require_permission('company:manage')
            draft_id=int(self.service_draft_id.get())
            draft=self.store.service_draft_detail(draft_id)
            if not messagebox.askyesno('로컬 초안 검토',
                  f"초안 #{draft_id} · {draft['title']}\n" +
                  ('로컬 검토 완료로 표시할까요?' if accept else '로컬 초안을 거부할까요?') +
                  '\n이 동작은 외부 서비스에 아무것도 전송하지 않습니다.'):
                self.service_feedback.set('검토를 취소했습니다.');return
            result=self.store.review_service_draft(draft_id,accept)
            self.service_feedback.set(f"초안 #{result['id']} → {result['state']} · "
                                      '외부 연결/전송 없음')
        except (ValueError,PermissionError) as exc:
            self.service_feedback.set(f'검토 거부: {exc}')

    def _service_history(self) -> None:
        try:
            rows=self.store.service_draft_history(6)
            self.service_feedback.set('최근 로컬 초안: '+(' / '.join(
                f"#{r['id']} {r['kind']} {r['state']} {r['title'][:30]}" for r in rows)
                if rows else '없음'))
        except (ValueError,PermissionError) as exc:
            self.service_feedback.set(f'조회 거부: {exc}')

    def _tool_audit_panel(self, parent: tk.Frame) -> None:
        self.store.require_permission('company:manage')
        self.tool_audit_id = tk.StringVar(value='')
        self.tool_audit_feedback = tk.StringVar(value='도구 호출을 실행하지 않습니다. 선택된 로컬 도구의 성공/실패 기록만 조회합니다.')
        panel = self._panel(parent); panel.pack(fill='both', expand=True)
        self._label(panel, '60단계 · 도구 사용·실패 처리 기록', size=16).pack(anchor='w')
        self._label(panel, '로컬 미디어 검사 및 외부 연동 초안 작업만 자동 기록합니다. '
                    '실패 사유는 분류 코드만 보관하며 경로·토큰·오류 원문은 저장하지 않습니다. '
                    '실패 확인·해결 표시가 도구 재실행을 뜻하지는 않습니다.',
                    fg='#f7cb92', wraplength=850).pack(anchor='w', pady=6)
        row=tk.Frame(panel,bg='#1c2a40');row.pack(fill='x',pady=5)
        self.tool_audit_refresh_button=tk.Button(row,text='최근 도구 사용 이력',command=self._tool_audit_refresh)
        self.tool_audit_refresh_button.pack(side='left',padx=4)
        self._label(row,'실패 기록 ID').pack(side='left',padx=5)
        tk.Entry(row,textvariable=self.tool_audit_id,width=10).pack(side='left',padx=3)
        self.tool_audit_ack_button=tk.Button(row,text='실패 확인',command=self._tool_audit_ack)
        self.tool_audit_ack_button.pack(side='left',padx=4)
        self.tool_audit_resolve_button=tk.Button(row,text='수동 해결 표시',command=self._tool_audit_resolve)
        self.tool_audit_resolve_button.pack(side='left',padx=4)
        self._label(panel,'',textvariable=self.tool_audit_feedback,fg='#8ee4b7',wraplength=850,
                    justify='left').pack(anchor='w',pady=7)

    def _tool_audit_refresh(self) -> None:
        try:
            rows=self.store.tool_use_history(10)
            self.tool_audit_feedback.set('최근 기록: '+(' / '.join(
                f"#{r['id']} {r['operation']} {r['outcome']} {r['error_code']} [{r['review_state']}]"
                for r in rows) if rows else '없음'))
        except (ValueError, PermissionError) as exc:
            self.tool_audit_feedback.set(f'기록 조회 거부: {exc}')

    def _tool_audit_ack(self) -> None:
        self._tool_audit_finalize('acknowledged')

    def _tool_audit_resolve(self) -> None:
        self._tool_audit_finalize('resolved')

    def _tool_audit_finalize(self, action: str) -> None:
        try:
            self.store.require_permission('company:manage')
            event_id=int(self.tool_audit_id.get())
            rows=self.store.tool_use_history(200)
            event=next((row for row in rows if row['id']==event_id),None)
            if event is None or event['outcome']!='failure':
                raise ValueError('최근 실패 기록 ID를 입력하세요.')
            if not messagebox.askyesno('로컬 실패 기록 확인',
                f"#{event_id} · {event['operation']} · {event['error_code']}\n"
                f"'{action}' 상태만 기록합니다. 도구를 재실행하지 않습니다. 진행합니까?"):
                self.tool_audit_feedback.set('실패 처리 취소');return
            result=self.store.review_tool_failure(event_id,action)
            self.tool_audit_feedback.set(f"기록 #{result['event_id']} → {result['action']} · 재실행 없음")
        except (ValueError, PermissionError) as exc:
            self.tool_audit_feedback.set(f'실패 처리 거부: {exc}')

    def _evidence_business_panel(self, parent: tk.Frame) -> None:
        """Provider-signature format readiness and actual failed staff follow-ups; no fake sales."""
        self.store.require_permission('company:manage')
        self.ev_payment_file=tk.StringVar()
        self.ev_signature=tk.StringVar()
        self.ev_secret=tk.StringVar()
        self.ev_event_id=tk.StringVar()
        self.ev_followup_id=tk.StringVar()
        self.ev_review_note=tk.StringVar()
        self.ev_message=tk.StringVar(value='실제 공급자 계정·결제 API 미연동. 수기 서명 확인과 입금 확인은 구별합니다.')
        frame=self._panel(parent);frame.pack(fill='both',expand=True)
        self._label(frame,'외부 거래 서명 증빙 검토 · 직원 실패 후속 개선',size=16,weight='bold').pack(anchor='w')
        self._label(frame,'서명 검증된 JSON 파일을 SQLite로 가져옵니다. 은행 입금, 결제, 주문, 실매출을 자동으로 인정하지 않습니다.',
                    fg='#f7cb92',wraplength=900).pack(anchor='w',pady=(6,9))
        row=tk.Frame(frame,bg='#1c2a40');row.pack(fill='x',pady=4)
        self._label(row,'JSON 증빙 파일').pack(side='left')
        tk.Entry(row,textvariable=self.ev_payment_file,width=53).pack(side='left',padx=4)
        tk.Button(row,text='파일 선택',command=lambda:self.ev_payment_file.set(
            filedialog.askopenfilename(title='서명된 JSON 외부 거래 증빙',filetypes=[('JSON','*.json')]))).pack(side='left')
        row=tk.Frame(frame,bg='#1c2a40');row.pack(fill='x',pady=3)
        self._label(row,'SHA256 HMAC 서명').pack(side='left')
        tk.Entry(row,textvariable=self.ev_signature,width=68).pack(side='left',padx=4)
        row=tk.Frame(frame,bg='#1c2a40');row.pack(fill='x',pady=3)
        self._label(row,'제공자 서명키(메모리 전용)').pack(side='left')
        tk.Entry(row,textvariable=self.ev_secret,width=34,show='●').pack(side='left',padx=4)
        tk.Button(row,text='서명 검증·증빙 수신',command=self._payment_evidence_import).pack(side='left')
        row=tk.Frame(frame,bg='#1c2a40');row.pack(fill='x',pady=6)
        self._label(row,'증빙 ID').pack(side='left')
        tk.Entry(row,textvariable=self.ev_event_id,width=8).pack(side='left',padx=3)
        self._label(row,'검수 사유').pack(side='left')
        tk.Entry(row,textvariable=self.ev_review_note,width=41).pack(side='left',padx=4)
        tk.Button(row,text='증빙 수락',command=lambda:self._payment_evidence_review('accepted')).pack(side='left')
        tk.Button(row,text='증빙 반려',command=lambda:self._payment_evidence_review('rejected')).pack(side='left')
        tk.Button(frame,text='서명 수신·환불 대사 현황',command=self._payment_evidence_summary).pack(anchor='w',pady=4)
        row=tk.Frame(frame,bg='#1c2a40');row.pack(fill='x',pady=6)
        tk.Button(row,text='실제 실패 업무 개선 후보 검색',command=self._failed_work_scan).pack(side='left')
        self._label(row,'개선 제안 ID').pack(side='left',padx=4)
        tk.Entry(row,textvariable=self.ev_followup_id,width=8).pack(side='left')
        tk.Button(row,text='후속 업무 생성 승인',command=lambda:self._failed_work_review('approved')).pack(side='left',padx=4)
        tk.Button(row,text='개선 제안 반려',command=lambda:self._failed_work_review('rejected')).pack(side='left')
        tk.Button(frame,text='실제 실패·후속 업무 감사 조회',command=self._failed_work_audit).pack(anchor='w',pady=4)
        self._label(frame,'자동 개선 후보 생성은 실제 모델 실패 기록 기준. 소유자 승인 전 실행·재배정 없음.',
                    fg='#f7cb92',wraplength=890).pack(anchor='w',pady=4)
        self._label(frame,'',textvariable=self.ev_message,fg='#8ee4b7',wraplength=900).pack(anchor='w',pady=5)

    def _payment_evidence_import(self) -> None:
        try:
            if not messagebox.askyesno('서명된 거래 증빙','제공자가 발행한 서명/원문을 수신할까요? 실제 결제·입금은 확인되지 않습니다.'):return
            path=Path(self.ev_payment_file.get())
            if not path.is_file() or path.stat().st_size>8192:raise ValueError('거래 증빙 파일 크기·경로 오류')
            result=self.store.ingest_signed_payment_evidence(
                path.read_bytes(),self.ev_signature.get(),self.ev_secret.get())
            self.ev_message.set('서명된 증빙 수신: #'+str(result['id'])+' / 중복: '+str(result['duplicate'])+' (실제 입금 미검증)')
        except (ValueError,OSError,PermissionError) as exc:self.ev_message.set('거래 증빙 수신 실패: '+str(exc))
        finally:self.ev_secret.set('')

    def _payment_evidence_review(self, decision: str) -> None:
        try:
            if not messagebox.askyesno('외부 거래 증빙 검수','수락해도 실제 입금 완료를 뜻하지 않습니다. 진행할까요?'):return
            r=self.store.review_signed_payment_evidence(int(self.ev_event_id.get()),decision,self.ev_review_note.get())
            self.ev_message.set('거래 증빙 '+r['decision']+' (독립 제공자 확인·실제 매출 미검증)')
        except (ValueError,PermissionError) as exc:self.ev_message.set('거래 검수 실패: '+str(exc))

    def _payment_evidence_summary(self) -> None:
        try:
            r=self.store.signed_payment_reconciliation_summary()
            self.ev_message.set('서명 수신 '+str(r['events'])+'건 / 검수 대기 '+str(r['pending'])+
                 '건 / 수락된 서명 정산 '+str(r['accepted_signed_settlements_minor'])+'원, 환불 '+
                 str(r['accepted_signed_refunds_minor'])+'원 / 실제 은행 정산 미검증')
        except (ValueError,PermissionError) as exc:self.ev_message.set('대사 조회 실패: '+str(exc))

    def _failed_work_scan(self) -> None:
        try:
            result=self.store.scan_failed_employee_work()
            self.ev_message.set('실제 실패 기록 개선 후보 '+str(len(result['created']))+
                                '건 생성. 업무 실행·재시작은 소유자 승인 전 차단.')
        except (ValueError,PermissionError) as exc:self.ev_message.set('실패 감사 조회 실패: '+str(exc))

    def _failed_work_review(self,decision: str) -> None:
        try:
            if not messagebox.askyesno('실패 업무 개선 검수','기존 실패 업무는 자동 재실행하지 않습니다. 진행할까요?'):return
            value=self.store.decide_failed_employee_followup(
                int(self.ev_followup_id.get()),decision,self.ev_review_note.get())
            self.ev_message.set('실패 업무 개선 '+value['decision']+' / 새 후속 업무 '+
                                str(value['new_task_id'])+' (모델 자동 실행 없음)')
        except (ValueError,PermissionError) as exc:self.ev_message.set('실패 개선 결정 실패: '+str(exc))

    def _failed_work_audit(self) -> None:
        try:
            data=self.store.failed_employee_followups()
            self.ev_message.set('실패 후속 기록 '+str(len(data))+'건 / 최근 '+
                   ', '.join('#'+str(v['id'])+':'+v['state'] for v in data[:9]))
        except (ValueError,PermissionError) as exc:self.ev_message.set('실패 감사 조회 실패: '+str(exc))

    def _staff_reorg_panel(self,parent: tk.Frame) -> None:
        """소유자 확인 후 실제 실패 모델 기록을 근거로 SQLite 직원을 재배치."""
        self.store.require_permission('company:manage')
        self.reorg_staff=tk.StringVar()
        self.reorg_target=tk.StringVar()
        self.reorg_run=tk.StringVar()
        self.reorg_proposal=tk.StringVar()
        self.reorg_reason=tk.StringVar()
        self.reorg_feedback=tk.StringVar(value='실제 실패 근거와 기존 부서장 보고 관계를 먼저 확인하세요.')
        card=self._panel(parent);card.pack(fill='both',expand=True)
        self._label(card,'실제 직원 실패 증거 기반 부서 이동·업무 재배정',size=16,weight='bold').pack(anchor='w')
        self._label(card,'직원·대상 부서·실패 모델 실행을 지정한 뒤 제안하고, 관리자 승인으로 직원 부서와 기존 배정을 변경합니다.',
                    fg='#f7cb92',wraplength=880).pack(anchor='w',pady=8)
        row=tk.Frame(card,bg='#1c2a40');row.pack(fill='x',pady=5)
        for label,var in [('직원 ID',self.reorg_staff),('대상 부서 ID',self.reorg_target),
                          ('실패 실행 ID',self.reorg_run)]:
            self._label(row,label).pack(side='left',padx=(4,2))
            tk.Entry(row,textvariable=var,width=8).pack(side='left',padx=(0,10))
        tk.Button(row,text='근거 기반 이동 제안',command=self._reorg_propose).pack(side='left',padx=4)
        row=tk.Frame(card,bg='#1c2a40');row.pack(fill='x',pady=5)
        self._label(row,'제안 번호').pack(side='left')
        tk.Entry(row,textvariable=self.reorg_proposal,width=9).pack(side='left',padx=4)
        self._label(row,'소유자 사유').pack(side='left')
        tk.Entry(row,textvariable=self.reorg_reason,width=46).pack(side='left',padx=4)
        tk.Button(row,text='조직 이동 승인',command=lambda:self._reorg_decide('accepted')).pack(side='left',padx=2)
        tk.Button(row,text='제안 반려',command=lambda:self._reorg_decide('rejected')).pack(side='left')
        tk.Button(card,text='직원 조직 개편 감사 조회',command=self._reorg_history).pack(anchor='w',pady=5)
        self._label(card,'실행 중인 직원 모델·부서장 보고 충돌 시 이동 금지. 기존 업무 배정은 취소 감사 후 수동 재배정하며 자동 권한 확대는 없습니다.',
                    fg='#f7cb92',wraplength=900).pack(anchor='w',pady=4)
        self._label(card,'',textvariable=self.reorg_feedback,fg='#8ee4b7',wraplength=900).pack(anchor='w',pady=5)

    def _reorg_propose(self) -> None:
        try:
            result=self.store.propose_staff_department_transfer(int(self.reorg_staff.get()),
                int(self.reorg_target.get()),int(self.reorg_run.get()),self.reorg_reason.get())
            self.reorg_feedback.set('직원 부서 이동 제안 #'+str(result['id'])+
                ' 저장. 실제 변경은 별도 관리자 수락 전까지 보류.')
        except (ValueError,PermissionError,RuntimeError) as exc:
            self.reorg_feedback.set('조직 이동 제안 실패: '+str(exc))

    def _reorg_decide(self,decision:str) -> None:
        try:
            if not messagebox.askyesno('직원 조직 변경 관리자 검수',
                 '실제 직원 부서가 변경되고 기존 배정은 감사 후 해제됩니다. 실행 중 모델과 관리자 보고 관계는 보호합니다. 진행할까요?'):
                return
            result=self.store.decide_staff_department_transfer(
                int(self.reorg_proposal.get()),decision,self.reorg_reason.get())
            self.reorg_feedback.set('조직 개편 '+result['decision']+
                ' / 해제된 기존 업무 배정 '+str(result['assignments_released'])+
                '건. 모델/도구 자동 실행 없음.')
        except (ValueError,PermissionError,RuntimeError) as exc:
            self.reorg_feedback.set('조직 개편 승인 실패: '+str(exc))

    def _reorg_history(self) -> None:
        try:
            data=self.store.staff_department_transfer_audit()
            self.reorg_feedback.set('실제 조직 개편 감사 '+str(len(data))+'건: '+
                ', '.join('#'+str(v['id'])+':'+v['state'] for v in data[:10]))
        except (ValueError,PermissionError) as exc:
            self.reorg_feedback.set('감사 조회 실패: '+str(exc))

    def _full_company_panel(self,parent: tk.Frame) -> None:
        """Original company 1 chief + 15 department heads + 15 staff, real work path."""
        self.wide_source=tk.StringVar()
        self.wide_plan=tk.StringVar()
        self.wide_status=tk.StringVar(value='실제 15부서 총괄 AI 5회 계획 생성 → 관리자 승인 → 직원 30개 순차 업무.')
        card=self._panel(parent);card.pack(fill='both',expand=True)
        self._label(card,'15개 부서 · 31명 AI 실제 회사 협업',size=17,weight='bold').pack(anchor='w')
        self._label(card,'총괄 AI 1명 + 각 부서장/직원 30명. 참여 인원·모델 배정이 실제로 필요합니다. '
            '결과 검수와 업무 완료는 관리자만 수행하며 자동 대외 거래는 없습니다.',
            fg='#f7cb92',wraplength=900).pack(anchor='w',pady=5)
        row=tk.Frame(card,bg='#1c2a40');row.pack(fill='x',pady=6)
        self._label(row,'기준 업무 ID').pack(side='left')
        tk.Entry(row,textvariable=self.wide_source,width=9).pack(side='left',padx=5)
        self.wide_propose_button=tk.Button(row,text='총괄 AI 15부서 실제 계획 생성',
            command=self._wide_propose)
        self.wide_propose_button.pack(side='left',padx=3)
        self.wide_staged_button=tk.Button(row,text='총괄 계획 중단·재개 상태',
            command=self._wide_staged_progress)
        self.wide_staged_button.pack(side='left',padx=3)
        self._label(row,'협업 계획 ID').pack(side='left',padx=5)
        tk.Entry(row,textvariable=self.wide_plan,width=9).pack(side='left',padx=3)
        row=tk.Frame(card,bg='#1c2a40');row.pack(fill='x',pady=5)
        tk.Button(row,text='30업무 관리자 승인·배정',command=self._wide_approve).pack(side='left',padx=3)
        self.wide_execute_button=tk.Button(row,text='다음 직원·총괄 실제 모델 실행',
            command=self._wide_execute)
        self.wide_execute_button.pack(side='left',padx=3)
        tk.Button(row,text='실제 30단계 감사·진행 상태',command=self._wide_show).pack(side='left',padx=3)
        self._label(card,'',textvariable=self.wide_status,fg='#8ee4b7',wraplength=900).pack(anchor='w',pady=6)
        self.wide_results=tk.Text(card,height=15,width=112,wrap='word')
        self.wide_results.pack(fill='both',expand=True,pady=6)
        self.wide_results.insert('end','각 단계의 직원 모델 호출·총괄 결과 검토 후 결과물과 보고서를 '
            '기존 AI 회사 운영센터에서 관리자가 별도 승인해야 다음 단계로 진행할 수 있습니다.\n')
        self.wide_results.configure(state='disabled')

    def _wide_write(self,text):
        self.wide_results.configure(state='normal')
        self.wide_results.delete('1.0','end')
        self.wide_results.insert('end',text)
        self.wide_results.configure(state='disabled')

    def _wide_background(self,action,call):
        try:
            if self._model_running:raise ValueError('다른 모델이 실행 중입니다.')
            self.store.require_permission('company:manage')
            self.store.require_permission('agents:manage')
        except (ValueError,PermissionError) as exc:
            self.wide_status.set(str(exc));return
        self._model_running=True
        self.wide_propose_button.configure(state='disabled')
        self.wide_execute_button.configure(state='disabled')
        generation=self._session_generation
        cancel=threading.Event()
        self._model_cancel=cancel
        replies=queue.Queue()
        self.wide_status.set(action+' 실행 중: 기존 승인/비상정지 검사를 유지합니다.')
        def worker():
            try:replies.put((True,call(cancel)))
            except Exception as exc:replies.put((False,type(exc).__name__+': '+str(exc)))
        self._model_thread=threading.Thread(target=worker,daemon=True)
        self._model_thread.start()
        def poll():
            if generation!=self._session_generation or not self.store.is_authenticated:return
            try:ok,result=replies.get_nowait()
            except queue.Empty:
                if self.root.winfo_exists():self.root.after(120,poll)
                return
            self._model_running=False
            self._model_cancel=None
            self._model_thread=None
            self.wide_propose_button.configure(state='normal')
            self.wide_execute_button.configure(state='normal')
            if not ok:
                self.wide_status.set(action+' 실패: '+str(result));return
            if action=='총괄 계획':
                self.wide_plan.set(str(result['id']))
                self.wide_status.set('15부서 30역할 실제 총괄 모델 초안 저장. 관리자 승인 전 실행 없음.')
                self._wide_write('\n'.join(f"#{s['ordinal']} {s['department']} {s['role']} "
                    f"직원 {s['employee_id']} / {s['title']}" for s in result['steps']))
            else:
                self.wide_status.set('한 단계 실제 직원·총괄 실행. 결과물·보고서를 별도로 검수하세요.')
                self._wide_write(str(result))
        self.root.after(120,poll)

    def _wide_staged_progress(self):
        try:
            source=int(self.wide_source.get())
            result=self.store.staged_full_company_progress(source)
            self.wide_status.set('실제 총괄 모델 단계별 계획 저장: '
                +str(result['completed_groups'])+'/5개 묶음. '
                '같은 기준 업무로 계획 생성을 다시 누르면 남은 묶음부터 재개합니다. '
                '30업무 실행에는 별도 관리자 승인이 필요합니다.')
        except (ValueError,PermissionError,RuntimeError) as exc:
            self.wide_status.set('총괄 계획 재개 상태 확인 실패: '+str(exc))

    def _wide_propose(self):
        try:
            task=int(self.wide_source.get())
            if not messagebox.askyesno('31명 실제 회사 협업',
                  '총괄 로컬 모델을 실제로 5회 실행해 15부서 계획을 작성합니다. '
                  '모든 직원 모델이 배정돼 있어야 합니다. 실행할까요?'):return
            self._wide_background('총괄 계획',lambda cancel:
                self.store.propose_full_company_campaign(task,cancel=cancel))
        except ValueError as exc:self.wide_status.set(str(exc))

    def _wide_approve(self):
        try:
            plan=int(self.wide_plan.get())
            if not messagebox.askyesno('30개 직원 업무 관리자 승인',
                    '15개 부서의 부서장·직원 업무 30개와 순서·지시를 SQLite에 실제 생성합니다. '
                    '관리자의 개별 결과물 검수 전 자동 완료되지 않습니다. 승인할까요?'):return
            result=self.store.approve_full_company_campaign(plan)
            self.wide_status.set('관리자 승인 완료: 30개 실제 업무와 선행 의존성 생성')
            self._wide_write('\n'.join(f"#{s['ordinal']} 업무 {s['task_id']} 직원 "
                f"{s['employee_id']} / {s['title']}" for s in result['steps']))
        except (ValueError,PermissionError,RuntimeError) as exc:
            self.wide_status.set('계획 승인 실패: '+str(exc))

    def _wide_execute(self):
        try:
            plan=int(self.wide_plan.get())
            if not messagebox.askyesno('실제 모델 업무 실행',
                '다음 한 직원과 총괄 AI의 실제 로컬 모델을 호출합니다. '
                '이전 업무의 직원 결과물·총괄 보고서 관리자의 승인이 필요합니다. 실행할까요?'):return
            self._wide_background('직원·총괄 실제 업무',lambda cancel:
                self.store.run_full_company_next(plan,cancel=cancel))
        except ValueError as exc:self.wide_status.set(str(exc))

    def _wide_show(self):
        try:
            result=self.store.read_full_company_campaign(int(self.wide_plan.get()))
            evidence=self.store.verified_full_company_progress(result['id'])
            self.wide_status.set('31 AI 회사 협업: '+result['state']+
                ' / 승인·무결성 검증 '+str(evidence['verified_completed_tasks'])+
                '/30 · '+str(evidence['verified_distinct_departments'])+'/15부서'
                ' / 다음 업무 '+str(evidence['next_task_id']))
            self._wide_write('\n'.join(f"#{s['ordinal']} {s['department']} "
                f"{s['role']} 직원 {s['employee_id']} 업무 {s['task_id']} "
                f"상태 {s['task_status']}" for s in result['steps']))
        except (ValueError,PermissionError) as exc:self.wide_status.set(str(exc))

    def _business_portfolio_panel(self, parent: tk.Frame) -> None:
        """Stage61 owner-only local business portfolio; no business execution."""
        self.store.require_permission('company:manage')
        self.business_type_key = tk.StringVar()
        self.business_type_title = tk.StringVar()
        self.business_type_id = tk.StringVar(value='1')
        self.business_name = tk.StringVar()
        self.business_goal = tk.StringVar()
        self.business_budget = tk.StringVar(value='0')
        self.business_owner_id = tk.StringVar()
        self.business_id = tk.StringVar()
        self.business_state = tk.StringVar(value='active')
        self.business_participant_id = tk.StringVar()
        self.business_feedback = tk.StringVar(value='오프라인 계획만 관리합니다. 판매·결제·AI 자동 실행 없음.')
        self.business_type_choices = tk.StringVar(value='')
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '61단계 · 범용 사업 유형 및 다중 사업 관리', size=16).pack(anchor='w')
        self._label(panel, '원본 사업 유형 예시 + 임의 신규 유형. 계획 예산은 실제 지출이 아닙니다. '
                    '사업 활성 표시는 운영·배포·판매 실행을 의미하지 않습니다.',
                    fg='#f7cb92', wraplength=860).pack(anchor='w', pady=5)
        self._label(panel, '', textvariable=self.business_type_choices,
                    fg='#bfcfe5', wraplength=860, justify='left').pack(anchor='w', pady=3)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '새 유형 키').pack(side='left')
        tk.Entry(row, textvariable=self.business_type_key, width=17).pack(side='left', padx=4)
        self._label(row, '유형 이름').pack(side='left')
        tk.Entry(row, textvariable=self.business_type_title, width=24).pack(side='left', padx=4)
        self.business_type_add_button = tk.Button(row, text='사업 유형 등록', command=self._business_type_add)
        self.business_type_add_button.pack(side='left', padx=4)
        self.business_type_disable_button = tk.Button(row, text='유형 비활성', command=self._business_type_disable)
        self.business_type_disable_button.pack(side='left', padx=4)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '유형 ID').pack(side='left')
        tk.Entry(row, textvariable=self.business_type_id, width=7).pack(side='left', padx=4)
        self._label(row, '사업명').pack(side='left')
        tk.Entry(row, textvariable=self.business_name, width=22).pack(side='left', padx=4)
        self._label(row, '목표').pack(side='left')
        tk.Entry(row, textvariable=self.business_goal, width=27).pack(side='left', padx=4)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '계획 예산(원)').pack(side='left')
        tk.Entry(row, textvariable=self.business_budget, width=16).pack(side='left', padx=4)
        self._label(row, '책임 직원 ID(선택)').pack(side='left')
        tk.Entry(row, textvariable=self.business_owner_id, width=10).pack(side='left', padx=4)
        self.business_create_button = tk.Button(row, text='사업 계획 등록', command=self._business_create)
        self.business_create_button.pack(side='left', padx=4)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '사업 ID').pack(side='left')
        tk.Entry(row, textvariable=self.business_id, width=8).pack(side='left', padx=4)
        self._label(row, '상태').pack(side='left')
        ttk.Combobox(row, textvariable=self.business_state,
                     values=('active', 'paused', 'closed'), state='readonly', width=11).pack(side='left', padx=4)
        self.business_state_button = tk.Button(row, text='상태 변경', command=self._business_change_state)
        self.business_state_button.pack(side='left', padx=4)
        self._label(row, '참여 직원 ID').pack(side='left')
        tk.Entry(row, textvariable=self.business_participant_id, width=8).pack(side='left', padx=4)
        self.business_join_button = tk.Button(row, text='참여 등록', command=lambda: self._business_participant(True))
        self.business_join_button.pack(side='left', padx=3)
        self.business_leave_button = tk.Button(row, text='참여 해제', command=lambda: self._business_participant(False))
        self.business_leave_button.pack(side='left', padx=3)
        self.business_refresh_button = tk.Button(panel, text='사업 유형·사업 목록 새로고침',
                                                  command=self._business_refresh)
        self.business_refresh_button.pack(anchor='w', pady=5)
        self.business_events_button = tk.Button(panel, text='선택 사업 이력·참여 직원 조회',
                                                 command=self._business_detail)
        self.business_events_button.pack(anchor='w', pady=2)
        self.business_tree = ttk.Treeview(panel, columns=('id', 'type', 'name', 'state', 'budget', 'staff'),
                                          show='headings', height=7)
        for col, title, width in [('id', 'ID', 55), ('type', '유형', 165), ('name', '사업명', 240),
                                  ('state', '상태', 85), ('budget', '계획 예산(원)', 135),
                                  ('staff', '참여 인원', 85)]:
            self.business_tree.heading(col, text=title)
            self.business_tree.column(col, width=width, anchor='w')
        self.business_tree.pack(fill='both', expand=True, pady=5)
        self.business_tree.bind('<<TreeviewSelect>>', self._business_select)
        self._label(panel, '', textvariable=self.business_feedback, fg='#8ee4b7',
                    wraplength=860, justify='left').pack(anchor='w')
        self._business_refresh()

    def _business_select(self, _event=None) -> None:
        selection = self.business_tree.selection()
        if selection:
            self.business_id.set(str(self.business_tree.item(selection[0], 'values')[0]))

    def _business_type_add(self) -> None:
        try:
            result = self.store.add_business_type(self.business_type_key.get(), self.business_type_title.get())
            self.business_type_id.set(str(result))
            self._business_refresh()
            self.business_feedback.set(f'신규 사업 유형 #{result} 등록 · 외부 실행 없음')
        except (ValueError, PermissionError) as exc:
            self.business_feedback.set(f'사업 유형 등록 거부: {exc}')

    def _business_type_disable(self) -> None:
        try:
            type_id = int(self.business_type_id.get())
            if not messagebox.askyesno('사업 유형 비활성',
                f'사업 유형 #{type_id}를 비활성화합니까?\n기존 사업 기록은 유지됩니다.'):
                self.business_feedback.set('유형 비활성 취소'); return
            self.store.disable_business_type(type_id)
            self._business_refresh()
            self.business_feedback.set(f'사업 유형 #{type_id} 비활성 · 기존 사업 보존')
        except (ValueError, PermissionError) as exc:
            self.business_feedback.set(f'유형 비활성 거부: {exc}')

    def _business_detail(self) -> None:
        try:
            business_id = int(self.business_id.get())
            events = self.store.business_events(business_id, 10)
            people = self.store.business_participants(business_id)
            self.business_feedback.set(
                f'사업 #{business_id} 최근 기록: ' +
                (', '.join(f"{e['action']}({e['id']})" for e in events) if events else '없음') +
                f" / 참여 직원: {', '.join(str(p['employee_id']) for p in people) if people else '없음'}")
        except (ValueError, PermissionError) as exc:
            self.business_feedback.set(f'상세 조회 거부: {exc}')

    def _business_create(self) -> None:
        try:
            owner = self.business_owner_id.get().strip()
            result = self.store.create_business(int(self.business_type_id.get()),
                self.business_name.get(), self.business_goal.get(), int(self.business_budget.get()),
                int(owner) if owner else None)
            self.business_id.set(str(result))
            self._business_refresh()
            self.business_feedback.set(f'사업 계획 #{result} 저장 · 실제 사업 시작/지출 없음')
        except (ValueError, PermissionError) as exc:
            self.business_feedback.set(f'사업 등록 거부: {exc}')

    def _business_change_state(self) -> None:
        try:
            business_id = int(self.business_id.get())
            state = self.business_state.get()
            if not messagebox.askyesno('로컬 사업 상태',
                f'사업 #{business_id}을 {state} 상태로 변경합니까?\n실제 운영·판매는 시작하지 않습니다.'):
                self.business_feedback.set('상태 변경 취소'); return
            result = self.store.set_business_state(business_id, state)
            self._business_refresh()
            self.business_feedback.set(f"사업 #{result['id']} 상태 {result['state']} · 외부 작업 없음")
        except (ValueError, PermissionError) as exc:
            self.business_feedback.set(f'상태 변경 거부: {exc}')

    def _business_participant(self, add: bool) -> None:
        try:
            self.store.set_business_participant(int(self.business_id.get()),
                int(self.business_participant_id.get()), add)
            self._business_refresh()
            self.business_feedback.set('참여 기록 변경 완료 · AI 직원 실행 없음')
        except (ValueError, PermissionError) as exc:
            self.business_feedback.set(f'참여 변경 거부: {exc}')

    def _business_refresh(self) -> None:
        try:
            self.store.require_permission('company:manage')
            types = self.store.business_types()
            self.business_type_choices.set('사업 유형 ID: ' + ', '.join(
                f"{t['id']}:{t['title']}" + ('(비활성)' if not t['enabled'] else '')
                for t in types[:25]) + (' …' if len(types) > 25 else ''))
            rows = self.store.list_businesses()
            for item in self.business_tree.get_children():
                self.business_tree.delete(item)
            for item in rows:
                self.business_tree.insert('', 'end', values=(item['id'], item['type_title'],
                    item['name'], item['state'], item['budget_krw'], item['participant_count']))
            self.business_feedback.set(f'등록 사업 유형 {len(types)}개 · 사업 {len(rows)}개 · '
                                       '로컬 계획·상태 기록만 제공')
        except (ValueError, PermissionError) as exc:
            self.business_feedback.set(f'조회 거부: {exc}')

    def _business_discovery_panel(self, parent: tk.Frame) -> None:
        """Stage62: draft ideas only; never autonomous market research or sales."""
        self.store.require_permission('company:manage')
        self.discovery_audience = tk.StringVar()
        self.discovery_problem = tk.StringVar()
        self.discovery_limit = tk.StringVar(value='8')
        self.discovery_candidate_id = tk.StringVar()
        self.discovery_state = tk.StringVar(value='shortlisted')
        self.discovery_feedback = tk.StringVar(value='관리자가 입력한 가정에서 미검증 사업 가설만 생성합니다.')
        panel = self._panel(parent); panel.pack(fill='both', expand=True)
        self._label(panel, '62단계 · 신규 수익 사업 후보 가설 (오프라인)', size=16).pack(anchor='w')
        self._label(panel, '시장 수요·경쟁·수익성을 조사하거나 검증하지 않습니다. '
                    '자동 실행·외부 연결·판매·결제 없음. 모든 후보는 검토 전 가설입니다.',
                    fg='#f7cb92', wraplength=860).pack(anchor='w', pady=6)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '가정한 고객').pack(side='left')
        tk.Entry(row, textvariable=self.discovery_audience, width=38).pack(side='left', padx=5)
        self._label(row, '고객 문제 가정').pack(side='left')
        tk.Entry(row, textvariable=self.discovery_problem, width=42).pack(side='left', padx=5)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '최대 후보 수').pack(side='left')
        tk.Entry(row, textvariable=self.discovery_limit, width=5).pack(side='left', padx=5)
        self.discovery_generate_button = tk.Button(row, text='미검증 후보 가설 생성', command=self._discovery_generate)
        self.discovery_generate_button.pack(side='left', padx=5)
        self.discovery_refresh_button = tk.Button(row, text='목록 갱신', command=self._discovery_refresh)
        self.discovery_refresh_button.pack(side='left', padx=5)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '후보 ID').pack(side='left')
        tk.Entry(row, textvariable=self.discovery_candidate_id, width=8).pack(side='left', padx=5)
        ttk.Combobox(row, textvariable=self.discovery_state,
                     values=('shortlisted', 'rejected', 'draft'),
                     state='readonly', width=13).pack(side='left', padx=5)
        self.discovery_state_button = tk.Button(row, text='관리자 검토 상태 변경', command=self._discovery_change_state)
        self.discovery_state_button.pack(side='left', padx=5)
        self.discovery_events_button = tk.Button(row, text='후보 감사 이력', command=self._discovery_events)
        self.discovery_events_button.pack(side='left', padx=5)
        self.discovery_tree = ttk.Treeview(panel,
            columns=('id','type','audience','problem','state'), show='headings', height=11)
        for col,title,width in [('id','ID',55),('type','사업 유형',200),('audience','가정 고객',180),
                                ('problem','고객 문제 가정',290),('state','검토 상태',120)]:
            self.discovery_tree.heading(col,text=title)
            self.discovery_tree.column(col,width=width,anchor='w')
        self.discovery_tree.pack(fill='both', expand=True, pady=5)
        self.discovery_tree.bind('<<TreeviewSelect>>', self._discovery_select)
        self._label(panel,'',textvariable=self.discovery_feedback,fg='#8ee4b7',
                    wraplength=860,justify='left').pack(anchor='w')
        self._discovery_refresh()

    def _discovery_select(self, _event=None) -> None:
        selected = self.discovery_tree.selection()
        if selected:
            self.discovery_candidate_id.set(str(self.discovery_tree.item(selected[0], 'values')[0]))

    def _discovery_generate(self) -> None:
        try:
            limit = int(self.discovery_limit.get())
            if not messagebox.askyesno('미검증 가설 생성',
                '관리자가 입력한 고객·문제 가정으로 로컬 사업 유형별 후보 초안만 생성합니까?\n'
                '시장 검증·AI 추론·외부 사업 실행은 수행하지 않습니다.'):
                self.discovery_feedback.set('후보 생성 취소'); return
            result = self.store.generate_business_candidates(
                self.discovery_audience.get(), self.discovery_problem.get(), limit)
            self._discovery_refresh()
            self.discovery_feedback.set(
                f"후보 초안 {len(result['created_ids'])}개 생성 · 중복 {result['skipped_duplicates']}개 제외 · "
                '시장 검증 없음 / 외부 작업 없음')
        except (ValueError, PermissionError) as exc:
            self.discovery_feedback.set(f'후보 생성 거부: {exc}')

    def _discovery_change_state(self) -> None:
        try:
            cid = int(self.discovery_candidate_id.get())
            state = self.discovery_state.get()
            if not messagebox.askyesno('후보 검토',
                f'후보 #{cid}를 {state} 상태로 변경합니까?\n사업 시작이나 판매를 수행하지 않습니다.'):
                self.discovery_feedback.set('후보 검토 취소'); return
            result = self.store.set_business_candidate_state(cid, state)
            self._discovery_refresh()
            self.discovery_feedback.set(f"후보 #{result['id']} 검토 상태: {result['state']} · 외부 실행 없음")
        except (ValueError, PermissionError) as exc:
            self.discovery_feedback.set(f'후보 검토 거부: {exc}')

    def _discovery_events(self) -> None:
        try:
            cid = int(self.discovery_candidate_id.get())
            events = self.store.business_candidate_events(cid, 20)
            self.discovery_feedback.set(f'후보 #{cid} 이력: ' + ', '.join(
                f"{event['action']}({event['id']})" for event in events))
        except (ValueError, PermissionError) as exc:
            self.discovery_feedback.set(f'후보 이력 조회 거부: {exc}')

    def _discovery_refresh(self) -> None:
        try:
            rows = self.store.business_candidates()
            for item in self.discovery_tree.get_children():
                self.discovery_tree.delete(item)
            for item in rows:
                self.discovery_tree.insert('', 'end', values=(item['id'],item['type_title'],
                    item['audience'],item['problem'],item['state']))
            self.discovery_feedback.set(f'로컬 미검증 사업 후보 {len(rows)}개 · 시장 자료/수익 검증 없음')
        except (ValueError, PermissionError) as exc:
            self.discovery_feedback.set(f'후보 목록 조회 거부: {exc}')

    def _financial_feasibility_panel(self, parent: tk.Frame) -> None:
        """Stage64: offline owner assumptions, not real earnings or forecasting."""
        self.store.require_permission('company:manage')
        self.finance_subject_kind = tk.StringVar(value='candidate')
        self.finance_subject_id = tk.StringVar()
        self.finance_note = tk.StringVar(value='관리자 미검증 비용·판매 가정')
        self.finance_eval_id = tk.StringVar()
        self.finance_feedback = tk.StringVar(value='관리자 입력 가정만 산술 계산합니다. 실제 매출·시장 검증 없음.')
        defaults = {
            'unit_price_krw': '10000', 'monthly_units': '10', 'unit_cost_krw': '3000',
            'monthly_fixed_krw': '20000', 'monthly_marketing_krw': '10000',
            'setup_cost_krw': '50000', 'refund_bps': '0', 'payment_fee_bps': '300', 'months': '6',
        }
        self.finance_inputs = {name: tk.StringVar(value=value) for name, value in defaults.items()}
        labels = {'unit_price_krw': '단가(원)', 'monthly_units': '월 판매량(가정)',
                  'unit_cost_krw': '단위당 변동비(원)', 'monthly_fixed_krw': '월 고정비(원)',
                  'monthly_marketing_krw': '월 마케팅비(원)', 'setup_cost_krw': '초기 비용(원)',
                  'refund_bps': '환불률(bp)', 'payment_fee_bps': '결제 수수료(bp)', 'months': '기간(월)'}
        panel = self._panel(parent); panel.pack(fill='both', expand=True)
        self._label(panel, '64단계 · 사업/후보별 비용·수익 가정 평가 (오프라인)', size=16).pack(anchor='w')
        self._label(panel, '입력값은 모두 검증되지 않은 가정입니다. 1bp=0.01%, 수수료는 총매출 기준. '
                    '±25% 판매량 민감도·초기비용 포함 손익분기점을 산술 계산합니다. '
                    '실제 판매·정산·회계·지출·자동 사업 실행 없음.',
                    fg='#f7cb92', wraplength=890).pack(anchor='w', pady=6)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '평가 대상').pack(side='left')
        ttk.Combobox(row, textvariable=self.finance_subject_kind, values=('candidate', 'business'),
                     state='readonly', width=12).pack(side='left', padx=6)
        self._label(row, '후보/사업 ID').pack(side='left')
        tk.Entry(row, textvariable=self.finance_subject_id, width=9).pack(side='left', padx=6)
        self._label(row, '가정 메모').pack(side='left')
        tk.Entry(row, textvariable=self.finance_note, width=44).pack(side='left', padx=6, fill='x', expand=True)
        keys = list(defaults)
        for start in range(0, len(keys), 3):
            row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=3)
            for name in keys[start:start+3]:
                self._label(row, labels[name]).pack(side='left', padx=(4, 2))
                tk.Entry(row, textvariable=self.finance_inputs[name], width=13).pack(side='left', padx=(0, 8))
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=5)
        self.finance_evaluate_button = tk.Button(row, text='가정 평가 저장 (확인)', command=self._finance_evaluate)
        self.finance_evaluate_button.pack(side='left', padx=4)
        self.finance_refresh_button = tk.Button(row, text='평가 이력 조회', command=self._finance_refresh)
        self.finance_refresh_button.pack(side='left', padx=4)
        self._label(row, '평가 ID').pack(side='left', padx=5)
        tk.Entry(row, textvariable=self.finance_eval_id, width=9).pack(side='left')
        self.finance_report_button = tk.Button(row, text='결과·무결성 조회', command=self._finance_report)
        self.finance_report_button.pack(side='left', padx=5)
        self.finance_tree = ttk.Treeview(panel, columns=('id', 'date', 'base', 'low', 'high'),
                                         show='headings', height=6)
        for col, title, width in (('id','평가 ID',75),('date','생성 시각',160),
                                  ('base','기준 기간 손익 가정',190),
                                  ('low','판매량 -25% 손익',190), ('high','판매량 +25% 손익',190)):
            self.finance_tree.heading(col, text=title)
            self.finance_tree.column(col, width=width, anchor='center')
        self.finance_tree.pack(fill='both', expand=True, pady=6)
        self.finance_tree.bind('<<TreeviewSelect>>', self._finance_select)
        self._label(panel, '', textvariable=self.finance_feedback, fg='#8ee4b7',
                    wraplength=900, justify='left').pack(anchor='w', pady=5)

    def _finance_select(self, event=None) -> None:
        selected = self.finance_tree.selection()
        if selected:
            self.finance_eval_id.set(str(self.finance_tree.item(selected[0], 'values')[0]))

    def _finance_evaluate(self) -> None:
        try:
            subject_id = int(self.finance_subject_id.get())
            assumptions = {name: int(value.get()) for name, value in self.finance_inputs.items()}
            if not messagebox.askyesno('가정 기반 평가 저장',
                    '미검증 가정만 저장·산술 평가합니다. 실제 매출·수익 예측이나 지출이 아닙니다. 계속합니까?'):
                self.finance_feedback.set('가정 평가 취소'); return
            ident = self.store.evaluate_financial_scenario(self.finance_subject_kind.get(),
                        subject_id, assumptions, self.finance_note.get())
            self.finance_eval_id.set(str(ident))
            self._finance_refresh()
            self._finance_report()
        except (ValueError, PermissionError) as exc:
            self.finance_feedback.set(f'가정 평가 거부: {exc}')

    def _finance_refresh(self) -> None:
        try:
            subject_id = int(self.finance_subject_id.get())
            rows = self.store.financial_scenario_history(self.finance_subject_kind.get(), subject_id)
            for item in self.finance_tree.get_children():
                self.finance_tree.delete(item)
            for item in rows:
                scenarios = item['result']['scenarios']
                self.finance_tree.insert('', 'end', values=(item['id'], item['created_at'],
                    scenarios['base_owner_assumption']['horizon_net_after_setup_assumed_krw'],
                    scenarios['downside_25pct_units']['horizon_net_after_setup_assumed_krw'],
                    scenarios['upside_25pct_units']['horizon_net_after_setup_assumed_krw']))
            self.finance_feedback.set(f'미검증 가정 평가 {len(rows)}건 조회 · 실제 매출·회계 데이터 없음')
        except (ValueError, PermissionError) as exc:
            self.finance_feedback.set(f'평가 이력 조회 거부: {exc}')

    def _finance_report(self) -> None:
        try:
            item = self.store.financial_scenario_report(int(self.finance_eval_id.get()))
            result = item['result']
            scenarios = result['scenarios']
            base = scenarios['base_owner_assumption']
            low = scenarios['downside_25pct_units']
            high = scenarios['upside_25pct_units']
            self.finance_feedback.set(
                f"평가 #{item['id']} · {result['horizon_months']}개월 가정 손익(원) "
                f"하향 {low['horizon_net_after_setup_assumed_krw']:,} / "
                f"기준 {base['horizon_net_after_setup_assumed_krw']:,} / "
                f"상향 {high['horizon_net_after_setup_assumed_krw']:,} · "
                f"월 손익분기 가정 수량 {result['break_even_monthly_units_assumed']} · "
                '입력·결과·감사 무결성 확인. 실제 매출/시장 수요 검증 없음.')
        except (ValueError, PermissionError) as exc:
            self.finance_feedback.set(f'평가 결과 조회 거부: {exc}')

    def _chief_business_decisions_panel(self, parent: tk.Frame) -> None:
        """Stage65: review only; never triggers projects, sales, or spending."""
        self.store.require_permission('company:manage')
        self.chief_business_eval_ids = tk.StringVar()
        self.chief_business_note = tk.StringVar(value='관리자 가정 비교 및 보류 사유')
        self.chief_business_brief_id = tk.StringVar()
        self.chief_business_feedback = tk.StringVar(value='실제 AI 판단/실행 없음. 검토 기록만 저장합니다.')
        panel = self._panel(parent); panel.pack(fill='both', expand=True)
        self._label(panel, '65단계 · 총괄 사업 선택·실행 판단 사전 검토 (오프라인)', size=16).pack(anchor='w')
        self._label(panel, '64단계 평가 ID를 쉼표로 구분(1~10개, 서로 다른 사업/후보·동일 평가 기간). '
                    '가정 손익 순서만 표시하며 사업 추천·실행 승인·프로젝트 생성·지출은 절대 하지 않습니다.',
                    fg='#f7cb92', wraplength=890).pack(anchor='w', pady=7)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=5)
        self._label(row, '평가 ID').pack(side='left')
        tk.Entry(row, textvariable=self.chief_business_eval_ids, width=25).pack(side='left', padx=6)
        self._label(row, '검토 메모').pack(side='left')
        tk.Entry(row, textvariable=self.chief_business_note, width=34).pack(side='left', padx=6)
        tk.Button(row, text='보류 판단 초안 저장', command=self._chief_business_create,
                  bg='#4c83e6', fg='white').pack(side='left', padx=5)
        actions = tk.Frame(panel, bg='#1c2a40'); actions.pack(fill='x', pady=6)
        self._label(actions, '검토 ID').pack(side='left')
        tk.Entry(actions, textvariable=self.chief_business_brief_id, width=10).pack(side='left', padx=5)
        self.chief_business_refresh_button = tk.Button(actions, text='이력 조회', command=self._chief_business_refresh)
        self.chief_business_refresh_button.pack(side='left', padx=5)
        tk.Button(actions, text='검토 내용', command=self._chief_business_show).pack(side='left', padx=5)
        tk.Button(actions, text='읽음 확인 (실행 아님)', command=lambda: self._chief_business_review('acknowledged')).pack(side='left', padx=5)
        tk.Button(actions, text='거부', command=lambda: self._chief_business_review('rejected')).pack(side='left', padx=5)
        self.chief_business_tree = ttk.Treeview(panel, columns=('id','count','status','base'), show='headings', height=7)
        for col, title, width in [('id','검토 ID',75),('count','비교 평가 수',110),('status','검토 상태',140),('base','첫 행 기준 가정 손익(원)',250)]:
            self.chief_business_tree.heading(col, text=title); self.chief_business_tree.column(col, width=width)
        self.chief_business_tree.pack(fill='both', expand=True, pady=8)
        self.chief_business_tree.bind('<<TreeviewSelect>>', self._chief_business_select)
        self._label(panel, '', textvariable=self.chief_business_feedback, wraplength=880,
                    justify='left', fg='#f7cb92').pack(anchor='w')
        self._chief_business_refresh()

    def _chief_business_select(self, event=None) -> None:
        selection = self.chief_business_tree.selection()
        if selection:
            self.chief_business_brief_id.set(str(self.chief_business_tree.item(selection[0], 'values')[0]))

    def _chief_business_create(self) -> None:
        try:
            ids = [int(v.strip()) for v in self.chief_business_eval_ids.get().split(',')]
            if not messagebox.askyesno('사업 판단 보류 기록',
                    '관리자 가정만 비교하여 보류 기록을 저장합니다. 사업 실행·승인이 아닙니다. 계속합니까?'):
                self.chief_business_feedback.set('저장 취소'); return
            ident = self.store.create_chief_business_brief(ids, self.chief_business_note.get())
            self.chief_business_brief_id.set(str(ident))
            self._chief_business_refresh(); self._chief_business_show()
        except (ValueError, PermissionError) as exc:
            self.chief_business_feedback.set(f'검토 저장 거부: {exc}')

    def _chief_business_refresh(self) -> None:
        try:
            rows = self.store.chief_business_brief_history()
            for item in self.chief_business_tree.get_children():
                self.chief_business_tree.delete(item)
            for item in rows:
                snap = item['snapshot']
                self.chief_business_tree.insert('', 'end', values=(item['id'], snap['comparison_count'],
                    item['review_status'], snap['items'][0]['base_assumed_krw']))
            self.chief_business_feedback.set(f'로컬 미검증 비교 {len(rows)}건 · 실행 승인/실제 AI 판단 없음')
        except (ValueError, PermissionError) as exc:
            self.chief_business_feedback.set(f'검토 이력 조회 거부: {exc}')

    def _chief_business_show(self) -> None:
        try:
            item = self.store.chief_business_brief(int(self.chief_business_brief_id.get()))
            snap = item['snapshot']
            first = snap['items'][0]
            self.chief_business_feedback.set(
                f"검토 #{item['id']} · {snap['comparison_count']}건 · 상태 {item['review_status']} · "
                f"가정상 기준 손익 최대 표시: 평가 #{first['evaluation_id']} / {first['base_assumed_krw']:,}원. "
                '근거/감사 무결성 확인. 실제 AI 판단·사업 추천·프로젝트 생성·실행 없음.')
        except (ValueError, PermissionError) as exc:
            self.chief_business_feedback.set(f'검토 조회 거부: {exc}')

    def _chief_business_review(self, action: str) -> None:
        try:
            if not messagebox.askyesno('로컬 검토 상태',
                    '검토 상태만 변경합니다. 사업 실행·외부 연결·지출 승인이 아닙니다. 계속합니까?'):
                self.chief_business_feedback.set('검토 취소'); return
            self.store.review_chief_business_brief(int(self.chief_business_brief_id.get()), action)
            self._chief_business_refresh(); self._chief_business_show()
        except (ValueError, PermissionError) as exc:
            self.chief_business_feedback.set(f'검토 상태 변경 거부: {exc}')

    def _product_catalog_panel(self, parent: tk.Frame) -> None:
        """Stage67: local catalogue plans, not product creation, release or sale."""
        self.store.require_permission('company:manage')
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '상품·서비스 정보 (오프라인 초안)', size=15, weight='bold').pack(anchor='w')
        self._label(panel, '가격은 미검증 가정입니다. 검토 대기 상태도 출시·판매·결제 승인이 아닙니다.',
                    fg='#f7cb92', wraplength=850).pack(anchor='w', pady=4)
        self.catalog_business_id = tk.StringVar()
        self.catalog_project_id = tk.StringVar()
        self.catalog_item_id = tk.StringVar()
        self.catalog_kind = tk.StringVar(value='product')
        self.catalog_name = tk.StringVar()
        self.catalog_description = tk.StringVar()
        self.catalog_price = tk.StringVar(value='0')
        self.catalog_delivery = tk.StringVar()
        self.catalog_state = tk.StringVar(value='draft')
        self.catalog_feedback = tk.StringVar()
        for label, var in (
            ('사업 ID', self.catalog_business_id),
            ('프로젝트 ID (선택)', self.catalog_project_id),
            ('상품·서비스 ID (조회/수정)', self.catalog_item_id),
            ('상품·서비스명', self.catalog_name),
            ('설명 (미검증)', self.catalog_description),
            ('가정 가격 KRW (실제 판매가 아님)', self.catalog_price),
            ('제공 계획 (실제 제공 아님)', self.catalog_delivery),
        ):
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=2)
            self._label(row, label, width=30).pack(side='left')
            tk.Entry(row, textvariable=var, width=62).pack(side='left', fill='x', expand=True)
        for label, var, choices in (
            ('종류', self.catalog_kind, ('product', 'service')),
            ('검토 상태', self.catalog_state, ('draft','review_pending','archived')),
        ):
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=2)
            self._label(row, label, width=30).pack(side='left')
            ttk.Combobox(row, textvariable=var, values=choices,
                         state='readonly', width=22).pack(side='left')
        buttons = tk.Frame(panel, bg='#17253b'); buttons.pack(fill='x', pady=5)
        tk.Button(buttons, text='로컬 초안 생성', command=self._catalog_create).pack(side='left', padx=3)
        tk.Button(buttons, text='초안 정보 수정', command=self._catalog_revise).pack(side='left', padx=3)
        tk.Button(buttons, text='검토 상태 변경 (출시 아님)', command=self._catalog_change_state).pack(side='left', padx=3)
        tk.Button(buttons, text='목록 갱신', command=self._catalog_refresh).pack(side='left', padx=3)
        self.catalog_tree = ttk.Treeview(panel, columns=('id','business','project','kind','name','state','price'),
                                         show='headings', height=6)
        for col, title, width in (
            ('id','ID',60),('business','사업',65),('project','프로젝트',75),
            ('kind','종류',90),('name','상품·서비스',210),('state','검토 상태',125),('price','가정 가격',110),
        ):
            self.catalog_tree.heading(col, text=title)
            self.catalog_tree.column(col, width=width)
        self.catalog_tree.pack(fill='both', expand=True, pady=5)
        self.catalog_tree.bind('<<TreeviewSelect>>', self._catalog_select)
        self._label(panel, '', textvariable=self.catalog_feedback, fg='#f7cb92',
                    wraplength=850, justify='left').pack(anchor='w')
        self._catalog_refresh()

    def _catalog_refresh(self) -> None:
        try:
            items = self.store.catalog_items()
            for node in self.catalog_tree.get_children():
                self.catalog_tree.delete(node)
            for item in items:
                self.catalog_tree.insert('', 'end', values=(item['id'], item['business_id'],
                    item['project_id'] or '', item['kind'], item['name'], item['state'],
                    item['assumed_price_krw']))
            self.catalog_feedback.set(f'로컬 정보 {len(items)}건 · 출시/판매/결제/외부 호출 0건')
        except (ValueError, PermissionError) as exc:
            self.catalog_feedback.set(f'조회 거부: {exc}')

    def _catalog_select(self, event=None) -> None:
        selected = self.catalog_tree.selection()
        if selected:
            self.catalog_item_id.set(str(self.catalog_tree.item(selected[0], 'values')[0]))
            self._catalog_show()

    def _catalog_show(self) -> None:
        try:
            item = self.store.catalog_item(int(self.catalog_item_id.get()))
            for var, key in ((self.catalog_business_id,'business_id'),
                             (self.catalog_kind,'kind'), (self.catalog_name,'name'),
                             (self.catalog_description,'description'),
                             (self.catalog_price,'assumed_price_krw'),
                             (self.catalog_delivery,'delivery_note'), (self.catalog_state,'state')):
                var.set(str(item[key]))
            self.catalog_project_id.set(str(item['project_id'] or ''))
            self.catalog_feedback.set(f"#{item['id']} / 버전 {item['version']} / {item['state']} · "
                                      '모든 정보는 오프라인 계획이며 실제 출시·판매 기록 아님')
        except (ValueError, PermissionError) as exc:
            self.catalog_feedback.set(f'상세 조회 거부: {exc}')

    def _catalog_create(self) -> None:
        try:
            if not messagebox.askyesno('오프라인 상품·서비스 초안',
                    '상품·서비스 정보만 저장합니다. 실제 상품 제작·출시·판매가 아닙니다. 계속합니까?'):
                self.catalog_feedback.set('생성 취소'); return
            project = self.catalog_project_id.get().strip()
            item_id = self.store.create_catalog_item(int(self.catalog_business_id.get()),
                self.catalog_kind.get(), self.catalog_name.get(), self.catalog_description.get(),
                int(self.catalog_price.get()), self.catalog_delivery.get(),
                int(project) if project else None)
            self.catalog_item_id.set(str(item_id))
            self._catalog_refresh(); self._catalog_show()
        except (ValueError, PermissionError) as exc:
            self.catalog_feedback.set(f'생성 거부: {exc}')

    def _catalog_revise(self) -> None:
        try:
            if not messagebox.askyesno('초안 정보 수정',
                    '로컬 설명·가정 가격·제공 계획만 수정합니다. 실제 가격 변경이 아닙니다. 계속합니까?'):
                self.catalog_feedback.set('수정 취소'); return
            self.store.revise_catalog_item(int(self.catalog_item_id.get()),
                self.catalog_description.get(), int(self.catalog_price.get()), self.catalog_delivery.get())
            self._catalog_refresh(); self._catalog_show()
        except (ValueError, PermissionError) as exc:
            self.catalog_feedback.set(f'수정 거부: {exc}')

    def _catalog_change_state(self) -> None:
        try:
            if not messagebox.askyesno('로컬 검토 상태 변경',
                    '검토 상태만 변경합니다. 실제 출시·판매·결제 승인이 아닙니다. 계속합니까?'):
                self.catalog_feedback.set('상태 변경 취소'); return
            self.store.set_catalog_item_state(int(self.catalog_item_id.get()), self.catalog_state.get())
            self._catalog_refresh(); self._catalog_show()
        except (ValueError, PermissionError) as exc:
            self.catalog_feedback.set(f'상태 변경 거부: {exc}')

    def _product_production_panel(self, parent: tk.Frame) -> None:
        """Stage68: deterministic static preview only, not AI creation or launch."""
        self.store.require_permission('company:manage')
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '로컬 정적 HTML 시제품 준비 (AI 제작 아님)',
                    size=15, weight='bold').pack(anchor='w')
        self._label(panel, '카탈로그 정보로 HTML 미리보기 파일만 만듭니다. 프로그램 기능/AI 제작·'
                    '품질 검수·출시·판매·외부 전송은 없습니다.',
                    fg='#f7cb92', wraplength=850).pack(anchor='w', pady=5)
        self.production_catalog_id = tk.StringVar()
        self.production_id = tk.StringVar()
        self.production_state = tk.StringVar(value='review_requested')
        self.production_feedback = tk.StringVar()
        for label, var in (('카탈로그 ID', self.production_catalog_id),
                           ('시제품 ID (조회/상태)', self.production_id)):
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=2)
            self._label(row, label, width=26).pack(side='left')
            tk.Entry(row, textvariable=var, width=25).pack(side='left')
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=2)
        self._label(row, '로컬 검토 상태', width=26).pack(side='left')
        ttk.Combobox(row, textvariable=self.production_state,
                     values=('review_requested','withdrawn'), state='readonly',
                     width=24).pack(side='left')
        buttons = tk.Frame(panel, bg='#17253b'); buttons.pack(fill='x', pady=5)
        tk.Button(buttons, text='로컬 정적 미리보기 생성',
                  command=self._production_create).pack(side='left', padx=3)
        tk.Button(buttons, text='해시 재검사·상세',
                  command=self._production_show).pack(side='left', padx=3)
        tk.Button(buttons, text='검토 요청/철회 (출시 아님)',
                  command=self._production_change_state).pack(side='left', padx=3)
        tk.Button(buttons, text='목록 갱신',
                  command=self._production_refresh).pack(side='left', padx=3)
        self.production_tree = ttk.Treeview(panel,
            columns=('id','catalog','version','state','digest','stale'),
            show='headings', height=7)
        for col, title, width in (('id','ID',65),('catalog','카탈로그',100),
                ('version','원본 버전',95),('state','검토 상태',140),
                ('digest','SHA-256 앞 12자리',175),('stale','원본 변경',110)):
            self.production_tree.heading(col, text=title)
            self.production_tree.column(col, width=width)
        self.production_tree.pack(fill='both', expand=True, pady=5)
        self.production_tree.bind('<<TreeviewSelect>>', self._production_select)
        self._label(panel, '', textvariable=self.production_feedback,
                    fg='#f7cb92', wraplength=850, justify='left').pack(anchor='w')
        self._production_refresh()

    def _production_refresh(self) -> None:
        try:
            items = self.store.product_prototypes()
            for node in self.production_tree.get_children():
                self.production_tree.delete(node)
            for item in items:
                self.production_tree.insert('', 'end', values=(item['id'],
                    item['catalog_item_id'], item['catalog_version'], item['state'],
                    item['sha256'][:12], '예' if item['catalog_changed_since_build'] else '아니오'))
            self.production_feedback.set(f'로컬 정적 시제품 {len(items)}개 / 외부 실행·출시·판매 0건')
        except (ValueError, PermissionError, OSError) as exc:
            self.production_feedback.set(f'조회 거부: {exc}')

    def _production_select(self, event=None) -> None:
        selected = self.production_tree.selection()
        if selected:
            self.production_id.set(str(self.production_tree.item(selected[0], 'values')[0]))
            self._production_show()

    def _production_show(self) -> None:
        try:
            item = self.store.product_prototype(int(self.production_id.get()))
            self.production_catalog_id.set(str(item['catalog_item_id']))
            self.production_feedback.set(
                f"#{item['id']} / {item['state']} / 파일 무결성 통과 / "
                f"원본 변경: {item['catalog_changed_since_build']} / {item['artifact_path']} / "
                'AI 생성·실제 출시·판매 아님')
        except (ValueError, PermissionError, OSError) as exc:
            self.production_feedback.set(f'무결성/조회 거부: {exc}')

    def _production_create(self) -> None:
        try:
            if not messagebox.askyesno('로컬 정적 미리보기',
                    '관리자가 입력한 카탈로그 정보를 HTML로 표현합니다. '
                    'AI 제작/실제 프로그램/출시/판매가 아닙니다. 계속합니까?'):
                self.production_feedback.set('생성 취소'); return
            prototype_id = self.store.create_product_prototype(int(self.production_catalog_id.get()))
            self.production_id.set(str(prototype_id))
            self._production_refresh(); self._production_show()
        except (ValueError, PermissionError, OSError) as exc:
            self.production_feedback.set(f'생성 거부: {exc}')

    def _production_change_state(self) -> None:
        try:
            if not messagebox.askyesno('로컬 검토 상태',
                    '로컬 검토 요청/철회만 기록합니다. 검수 합격·출시 승인이 아닙니다. 계속합니까?'):
                self.production_feedback.set('상태 변경 취소'); return
            self.store.set_product_prototype_state(int(self.production_id.get()),
                                                    self.production_state.get())
            self._production_refresh(); self._production_show()
        except (ValueError, PermissionError, OSError) as exc:
            self.production_feedback.set(f'상태 변경 거부: {exc}')

    def _product_release_review_panel(self, parent: tk.Frame) -> None:
        """Stage69: owner checklist claims; NEVER a release approval control."""
        self.store.require_permission('company:manage')
        from desktop.product_release_review import CHECKS, ANSWERS
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '상품 검수 기록 · 출시 보류 (실제 품질 검증 아님)',
                    size=15, weight='bold').pack(anchor='w')
        self._label(panel, '관리자 자체 점검 주장을 기록합니다. 실제 품질 합격·출시 승인·배포·판매 기능은 없습니다.',
                    fg='#f7cb92', wraplength=850).pack(anchor='w', pady=4)
        self.release_review_id = tk.StringVar()
        self.release_review_note = tk.StringVar()
        self.release_review_decision = tk.StringVar(value='HOLD_NO_RELEASE')
        self.release_review_feedback = tk.StringVar()
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=2)
        self._label(row, '검토 요청된 시제품 ID', width=29).pack(side='left')
        tk.Entry(row, textvariable=self.release_review_id, width=20).pack(side='left')
        self.release_review_checks = {}
        for key in CHECKS:
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=1)
            self._label(row, key, width=29).pack(side='left')
            var = tk.StringVar(value='unverified')
            self.release_review_checks[key] = var
            ttk.Combobox(row, textvariable=var, values=ANSWERS,
                         state='readonly', width=24).pack(side='left')
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=2)
        self._label(row, '검토 메모 (주장, 최대 1000자)', width=29).pack(side='left')
        tk.Entry(row, textvariable=self.release_review_note, width=65).pack(side='left')
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=2)
        self._label(row, '출시 불가 결정만 허용', width=29).pack(side='left')
        ttk.Combobox(row, textvariable=self.release_review_decision,
                     values=('HOLD_NO_RELEASE','REJECTED_NO_RELEASE'),
                     state='readonly', width=28).pack(side='left')
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=5)
        tk.Button(row, text='검수 주장 기록 (출시 불가)',
                  command=self._release_review_record).pack(side='left', padx=3)
        tk.Button(row, text='기록·해시 재검사',
                  command=self._release_review_refresh).pack(side='left', padx=3)
        self.release_review_tree = ttk.Treeview(panel,
            columns=('revision','decision','checked','digest'), show='headings', height=5)
        for col, label, width in (
            ('revision','차수',80), ('decision','출시 보류 결정',210),
            ('checked','관리자 확인 주장 수',150), ('digest','감사 해시 앞 12자리',180)):
            self.release_review_tree.heading(col, text=label)
            self.release_review_tree.column(col, width=width)
        self.release_review_tree.pack(fill='both', expand=True, pady=4)
        self._label(panel, '', textvariable=self.release_review_feedback,
                    fg='#f7cb92', wraplength=850, justify='left').pack(anchor='w')

    def _release_review_refresh(self) -> None:
        try:
            prototype_id = int(self.release_review_id.get())
            result = self.store.product_release_review_summary(prototype_id)
            rows = self.store.product_release_review_history(prototype_id)
            for node in self.release_review_tree.get_children():
                self.release_review_tree.delete(node)
            for row in rows:
                count = sum(v == 'owner_reports_checked' for v in row['checklist'].values())
                self.release_review_tree.insert('', 'end', values=(
                    row['revision'], row['decision'], count, row['digest'][:12]))
            self.release_review_feedback.set(
                f"시제품 #{prototype_id}: 파일 무결성 확인 / 검토 기록 {len(rows)}건 / "
                f"원본 변경 {result['catalog_changed_since_build']} / "
                '실제 품질 검증·출시 승인·배포·판매 0건')
        except (ValueError, PermissionError, OSError) as exc:
            self.release_review_feedback.set(f'조회·무결성 검사 거부: {exc}')

    def _release_review_record(self) -> None:
        try:
            if not messagebox.askyesno('출시 보류 검토 기록',
                    '입력 내용은 관리자의 검수 주장일 뿐입니다. 출시 승인·배포·판매는 불가능합니다. 기록합니까?'):
                self.release_review_feedback.set('기록 취소'); return
            result = self.store.record_product_release_review(
                int(self.release_review_id.get()),
                {key: var.get() for key, var in self.release_review_checks.items()},
                self.release_review_note.get(), self.release_review_decision.get())
            self._release_review_refresh()
            self.release_review_feedback.set(
                f"검토 #{result['revision']} 추가 전용 저장 / {result['decision']} / "
                '실제 품질 합격·출시 승인 없음')
        except (ValueError, PermissionError, OSError) as exc:
            self.release_review_feedback.set(f'기록 거부: {exc}')

    def _service_operations_panel(self, parent: tk.Frame) -> None:
        """Stage70: no launch/deployment controls, only offline plans and owner claims."""
        self.store.require_permission('company:manage')
        from desktop.service_operations_plan import CHECKS, ANSWERS, ENVIRONMENTS
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '서비스 배포·운영 계획 (미배포 · 오프라인)',
                    size=15, weight='bold').pack(anchor='w')
        self._label(panel, '계획/준비 상태만 기록합니다. 실제 서비스 배포, 운영, 출시 승인, 판매, 외부 호출은 없습니다.',
                    fg='#f7cb92', wraplength=850).pack(anchor='w', pady=4)
        self.service_ops_prototype_id = tk.StringVar()
        self.service_ops_plan_id = tk.StringVar()
        self.service_ops_environment = tk.StringVar(value=ENVIRONMENTS[0])
        self.service_ops_operator = tk.StringVar()
        self.service_ops_backup = tk.StringVar()
        self.service_ops_rollback = tk.StringVar()
        self.service_ops_monitor = tk.StringVar()
        self.service_ops_note = tk.StringVar()
        self.service_ops_feedback = tk.StringVar()
        for label, var in (
            ('69단계 출시 보류 검토 시제품 ID', self.service_ops_prototype_id),
            ('운영 계획 ID', self.service_ops_plan_id),
            ('운영 책임 계획 (500자 이내)', self.service_ops_operator),
            ('백업·복원 계획 (500자 이내)', self.service_ops_backup),
            ('롤백 계획 (500자 이내)', self.service_ops_rollback),
            ('모니터링 계획 (500자 이내)', self.service_ops_monitor),
            ('준비 검토 메모 / 폐기 사유', self.service_ops_note),
        ):
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=1)
            self._label(row, label, width=31).pack(side='left')
            tk.Entry(row, textvariable=var, width=60).pack(side='left', fill='x', expand=True)
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=2)
        self._label(row, '미래 운영 환경 (접속 없음)', width=31).pack(side='left')
        ttk.Combobox(row, textvariable=self.service_ops_environment,
                     values=ENVIRONMENTS, state='readonly', width=30).pack(side='left')
        self.service_ops_checks = {}
        for key in CHECKS:
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=1)
            self._label(row, key, width=31).pack(side='left')
            var = tk.StringVar(value='unverified')
            self.service_ops_checks[key] = var
            ttk.Combobox(row, textvariable=var, values=ANSWERS,
                         state='readonly', width=26).pack(side='left')
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=4)
        for label, callback in (
            ('미배포 계획 생성', self._service_ops_create),
            ('준비 자기보고 기록', self._service_ops_record),
            ('계획 폐기 (미배포)', self._service_ops_retire),
            ('감사 이력 재검사', self._service_ops_refresh),
        ):
            tk.Button(row, text=label, command=callback).pack(side='left', padx=3)
        self.service_ops_tree = ttk.Treeview(panel,
            columns=('id','prototype','environment','state','stale'), show='headings', height=4)
        for key, label, width in (
            ('id','계획 ID',75), ('prototype','시제품',80),
            ('environment','미래 환경',220), ('state','미배포 상태',210),
            ('stale','원본 변경',100)):
            self.service_ops_tree.heading(key, text=label)
            self.service_ops_tree.column(key, width=width)
        self.service_ops_tree.pack(fill='both', expand=True, pady=4)
        self.service_ops_tree.bind('<<TreeviewSelect>>', self._service_ops_select)
        self._label(panel, '', textvariable=self.service_ops_feedback,
                    fg='#f7cb92', wraplength=850, justify='left').pack(anchor='w')

    def _service_ops_select(self, event=None) -> None:
        selected = self.service_ops_tree.selection()
        if selected:
            self.service_ops_plan_id.set(str(self.service_ops_tree.item(selected[0], 'values')[0]))

    def _service_ops_refresh(self) -> None:
        try:
            rows = self.store.service_operations_plans()
            for node in self.service_ops_tree.get_children():
                self.service_ops_tree.delete(node)
            for row in rows:
                self.service_ops_tree.insert('', 'end', values=(row['id'], row['prototype_id'],
                    row['environment'], row['state'], '예' if row['stale_source'] else '아니오'))
            if self.service_ops_plan_id.get().strip():
                ident = int(self.service_ops_plan_id.get())
                current = self.store.service_operations_plan(ident)
                events = self.store.service_operations_events(ident)
                self.service_ops_feedback.set(
                    f"계획 #{ident} / {current['state']} / 감사 {len(events)}건 / "
                    f"원본 변경 {current['stale_source']} / 실제 배포·운영·매출 0건")
            else:
                self.service_ops_feedback.set(f'로컬 운영 계획 {len(rows)}건 · 실제 배포·운영 0건')
        except (ValueError, PermissionError, OSError) as exc:
            self.service_ops_feedback.set(f'조회·무결성 검사 거부: {exc}')

    def _service_ops_create(self) -> None:
        try:
            if not messagebox.askyesno('미배포 계획 생성',
                    '오프라인 계획만 저장합니다. 서비스 배포·실행·출시 승인은 불가능합니다. 진행합니까?'):
                self.service_ops_feedback.set('생성 취소'); return
            row = self.store.create_service_operations_plan(
                int(self.service_ops_prototype_id.get()), self.service_ops_environment.get(),
                self.service_ops_operator.get(), self.service_ops_backup.get(),
                self.service_ops_rollback.get(), self.service_ops_monitor.get())
            self.service_ops_plan_id.set(str(row['id']))
            self._service_ops_refresh()
        except (ValueError, PermissionError, OSError) as exc:
            self.service_ops_feedback.set(f'계획 생성 거부: {exc}')

    def _service_ops_record(self) -> None:
        try:
            if not messagebox.askyesno('운영 준비 주장',
                    '체크 상태는 관리자 주장일 뿐입니다. 실제 배포/운영 승인 아님. 기록합니까?'):
                self.service_ops_feedback.set('기록 취소'); return
            row = self.store.record_service_readiness(
                int(self.service_ops_plan_id.get()),
                {k: v.get() for k, v in self.service_ops_checks.items()},
                self.service_ops_note.get())
            self._service_ops_refresh()
            self.service_ops_feedback.set(f"운영 준비 기록 #{row['id']} · {row['state']} · 미배포")
        except (ValueError, PermissionError, OSError) as exc:
            self.service_ops_feedback.set(f'기록 거부: {exc}')

    def _service_ops_retire(self) -> None:
        try:
            if not messagebox.askyesno('운영 계획 폐기', '로컬 계획만 폐기합니다. 계속합니까?'):
                self.service_ops_feedback.set('폐기 취소'); return
            row = self.store.retire_service_operations_plan(
                int(self.service_ops_plan_id.get()), self.service_ops_note.get())
            self._service_ops_refresh()
            self.service_ops_feedback.set(f"운영 계획 #{row['id']} · {row['state']} · 미배포")
        except (ValueError, PermissionError, OSError) as exc:
            self.service_ops_feedback.set(f'폐기 거부: {exc}')

    def _sales_channels_panel(self, parent: tk.Frame) -> None:
        """Stage71: channel CONTRACT plans, never credentials or real connections."""
        self.store.require_permission('company:manage')
        from desktop.sales_channel_contracts import KINDS, REGIONS, MODES, SCOPES, CHECKS, ANSWERS
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '외부 판매 채널 연결 구조 · 미연결 오프라인 계획',
                    size=15, weight='bold').pack(anchor='w')
        self._label(panel, '계정·비밀키·URL 입력 금지. 자기보고 검토는 연결 승인 아님. '
                    '외부 접속·상품 등록·주문·판매·결제 기능 없음.',
                    fg='#f7cb92', wraplength=900).pack(anchor='w', pady=4)
        self.sales_channel_ops_id = tk.StringVar()
        self.sales_channel_id = tk.StringVar()
        self.sales_channel_kind = tk.StringVar(value=KINDS[0])
        self.sales_channel_name = tk.StringVar()
        self.sales_channel_region = tk.StringVar(value=REGIONS[0])
        self.sales_channel_mode = tk.StringVar(value=MODES[0])
        self.sales_channel_mapping = tk.StringVar()
        self.sales_channel_compliance = tk.StringVar()
        self.sales_channel_note = tk.StringVar()
        self.sales_channel_feedback = tk.StringVar()
        for label, var in (
            ('70단계 관리자 검토 운영 계획 ID', self.sales_channel_ops_id),
            ('판매 채널 계약 ID', self.sales_channel_id),
            ('채널 별칭 (URL/계정 아님)', self.sales_channel_name),
            ('데이터 매핑 계획 (500자)', self.sales_channel_mapping),
            ('규정/개인정보 검토 계획 (500자)', self.sales_channel_compliance),
            ('검토 메모 또는 폐기 사유', self.sales_channel_note),
        ):
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=1)
            self._label(row, label, width=34).pack(side='left')
            tk.Entry(row, textvariable=var, width=60).pack(side='left', fill='x', expand=True)
        for label, var, values in (
            ('미래 채널 분류', self.sales_channel_kind, KINDS),
            ('미래 대상 지역', self.sales_channel_region, REGIONS),
            ('미래 연결 방식', self.sales_channel_mode, MODES),
        ):
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=1)
            self._label(row, label, width=34).pack(side='left')
            ttk.Combobox(row, textvariable=var, values=values, state='readonly',
                         width=33).pack(side='left')
        self.sales_channel_scopes = {}
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=1)
        self._label(row, '미래 권한 범위 (실제 권한 없음)', width=34).pack(side='left')
        for scope in SCOPES:
            var = tk.BooleanVar(value=scope == SCOPES[0])
            self.sales_channel_scopes[scope] = var
            tk.Checkbutton(row, text=scope, variable=var, bg='#17253b',
                           fg='white', selectcolor='#17253b').pack(side='left')
        self.sales_channel_checks = {}
        for key in CHECKS:
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=1)
            self._label(row, key, width=34).pack(side='left')
            var = tk.StringVar(value='unverified')
            self.sales_channel_checks[key] = var
            ttk.Combobox(row, textvariable=var, values=ANSWERS, state='readonly',
                         width=26).pack(side='left')
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=3)
        for label, callback in (
            ('미연결 계획 생성', self._sales_channel_create),
            ('관리자 자기보고', self._sales_channel_review),
            ('계획 폐기', self._sales_channel_retire),
            ('감사 이력 확인', self._sales_channel_refresh),
        ):
            tk.Button(row, text=label, command=callback).pack(side='left', padx=3)
        self.sales_channel_tree = ttk.Treeview(panel,
            columns=('id','ops','kind','state','stale'), show='headings', height=4)
        for key, label, width in (
            ('id','계약 ID',75), ('ops','운영 계획',90), ('kind','미래 채널',220),
            ('state','미연결 상태',220), ('stale','원본 변경',100)):
            self.sales_channel_tree.heading(key, text=label)
            self.sales_channel_tree.column(key, width=width)
        self.sales_channel_tree.pack(fill='both', expand=True, pady=4)
        self.sales_channel_tree.bind('<<TreeviewSelect>>', self._sales_channel_select)
        self._label(panel, '', textvariable=self.sales_channel_feedback,
                    fg='#f7cb92', wraplength=900, justify='left').pack(anchor='w')

    def _sales_channel_select(self, event=None) -> None:
        selected = self.sales_channel_tree.selection()
        if selected:
            self.sales_channel_id.set(str(self.sales_channel_tree.item(selected[0], 'values')[0]))

    def _sales_channel_refresh(self) -> None:
        try:
            rows = self.store.sales_channel_contracts()
            for node in self.sales_channel_tree.get_children():
                self.sales_channel_tree.delete(node)
            for row in rows:
                self.sales_channel_tree.insert('', 'end', values=(row['id'],
                    row['operations_plan_id'], row['channel_kind'], row['state'],
                    '예' if row['stale_source'] else '아니오'))
            if self.sales_channel_id.get().strip():
                ident = int(self.sales_channel_id.get())
                current = self.store.sales_channel_contract(ident)
                events = self.store.sales_channel_contract_events(ident)
                self.sales_channel_feedback.set(
                    f"계약 #{ident} / {current['state']} / 감사 {len(events)}건 / "
                    f"원본 변경 {current['stale_source']} / 실제 연결·등록·판매·결제 0건")
            else:
                self.sales_channel_feedback.set(f'미연결 채널 계약 {len(rows)}건 · 실제 연결 0건')
        except (ValueError, PermissionError, OSError) as exc:
            self.sales_channel_feedback.set(f'조회·무결성 검사 거부: {exc}')

    def _sales_channel_create(self) -> None:
        try:
            if not messagebox.askyesno('미연결 채널 계획',
                    '계정·키·URL 없이 로컬 연결 계획만 저장합니다. 외부 접속/판매 없음. 진행합니까?'):
                self.sales_channel_feedback.set('생성 취소'); return
            row = self.store.create_sales_channel_contract(
                int(self.sales_channel_ops_id.get()), self.sales_channel_kind.get(),
                self.sales_channel_name.get(), self.sales_channel_region.get(),
                self.sales_channel_mode.get(),
                [k for k, v in self.sales_channel_scopes.items() if v.get()],
                self.sales_channel_mapping.get(), self.sales_channel_compliance.get())
            self.sales_channel_id.set(str(row['id']))
            self._sales_channel_refresh()
        except (ValueError, PermissionError, OSError) as exc:
            self.sales_channel_feedback.set(f'계획 생성 거부: {exc}')

    def _sales_channel_review(self) -> None:
        try:
            if not messagebox.askyesno('관리자 자체 검토',
                    '체크리스트는 관리자 자기보고입니다. 실제 채널 연결 승인 아님. 기록합니까?'):
                self.sales_channel_feedback.set('검토 취소'); return
            row = self.store.review_sales_channel_contract(
                int(self.sales_channel_id.get()),
                {k: v.get() for k, v in self.sales_channel_checks.items()},
                self.sales_channel_note.get())
            self._sales_channel_refresh()
            self.sales_channel_feedback.set(f"계약 #{row['id']} · {row['state']} · 미연결")
        except (ValueError, PermissionError, OSError) as exc:
            self.sales_channel_feedback.set(f'검토 거부: {exc}')

    def _sales_channel_retire(self) -> None:
        try:
            if not messagebox.askyesno('채널 계획 폐기', '로컬 미연결 계획만 폐기합니다. 진행합니까?'):
                self.sales_channel_feedback.set('폐기 취소'); return
            row = self.store.retire_sales_channel_contract(
                int(self.sales_channel_id.get()), self.sales_channel_note.get())
            self._sales_channel_refresh()
            self.sales_channel_feedback.set(f"계약 #{row['id']} · {row['state']} · 미연결")
        except (ValueError, PermissionError, OSError) as exc:
            self.sales_channel_feedback.set(f'폐기 거부: {exc}')

    def _unpublished_listing_panel(self, parent: tk.Frame) -> None:
        """Stage72: owner-only offline drafts; NEVER publish or synchronize."""
        self.store.require_permission('company:manage')
        from desktop.offline_listing_prices import CURRENCIES
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '상품 등록 및 가격 관리 · 로컬 미게시 초안',
                    size=15, weight='bold').pack(anchor='w')
        self._label(panel, 'Stage71 관리자 검토된 미연결 계획 + 동일 상품만 허용. '
                    '가격은 미검증 가정, 외부 게시/가격 동기화/주문/결제 없음. '
                    'USD/EUR은 센트, KRW/JPY는 원/엔 정수 입력.',
                    fg='#f7cb92', wraplength=900).pack(anchor='w', pady=4)
        self.listing_draft_id = tk.StringVar()
        self.listing_contract_id = tk.StringVar()
        self.listing_catalog_id = tk.StringVar()
        self.listing_title = tk.StringVar()
        self.listing_description = tk.StringVar()
        self.listing_currency = tk.StringVar(value='KRW')
        self.listing_price_minor = tk.StringVar(value='0')
        self.listing_price_note = tk.StringVar()
        self.listing_review_note = tk.StringVar()
        self.listing_feedback = tk.StringVar()
        for label, var in (
            ('미게시 초안 ID (수정·검토·폐기)', self.listing_draft_id),
            ('Stage71 관리자 검토 미연결 계약 ID', self.listing_contract_id),
            ('Stage67 상품·서비스 ID', self.listing_catalog_id),
            ('미게시 상품명 (120자)', self.listing_title),
            ('미게시 설명 (1000자)', self.listing_description),
            ('가정 가격 (통화 최소단위 정수)', self.listing_price_minor),
            ('가격 가정 근거 (500자)', self.listing_price_note),
            ('관리자 검토 메모 / 폐기 사유', self.listing_review_note),
        ):
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=1)
            self._label(row, label, width=35).pack(side='left')
            tk.Entry(row, textvariable=var, width=55).pack(side='left', fill='x', expand=True)
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=1)
        self._label(row, '통화 (환율 변환 없음)', width=35).pack(side='left')
        ttk.Combobox(row, textvariable=self.listing_currency, values=CURRENCIES,
                     state='readonly', width=15).pack(side='left')
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=3)
        for label, callback in (
            ('미게시 초안 생성', self._listing_create),
            ('가격·내용 초안 수정', self._listing_revise),
            ('관리자 자체 검토', self._listing_review),
            ('초안 폐기', self._listing_retire),
            ('이력·무결성 조회', self._listing_refresh),
        ):
            tk.Button(row, text=label, command=callback).pack(side='left', padx=3)
        self.listing_tree = ttk.Treeview(panel,
            columns=('id','contract','item','currency','price','state','stale'),
            show='headings', height=4)
        for key, label, width in (
            ('id','초안 ID',75), ('contract','채널 계획',90), ('item','상품 ID',75),
            ('currency','통화',70), ('price','가정 가격',110),
            ('state','미게시 상태',215), ('stale','원본 변경',90)):
            self.listing_tree.heading(key, text=label)
            self.listing_tree.column(key, width=width)
        self.listing_tree.pack(fill='both', expand=True, pady=4)
        self.listing_tree.bind('<<TreeviewSelect>>', self._listing_select)
        self._label(panel, '', textvariable=self.listing_feedback,
                    fg='#f7cb92', wraplength=900, justify='left').pack(anchor='w')

    def _listing_select(self, event=None) -> None:
        selected = self.listing_tree.selection()
        if selected:
            self.listing_draft_id.set(str(self.listing_tree.item(selected[0], 'values')[0]))

    def _listing_refresh(self) -> None:
        try:
            rows = self.store.unpublished_listings()
            for node in self.listing_tree.get_children():
                self.listing_tree.delete(node)
            for row in rows:
                self.listing_tree.insert('', 'end', values=(row['id'], row['contract_id'],
                    row['catalog_item_id'], row['currency'], row['price_minor'],
                    row['state'], '예' if row['stale_source'] else '아니오'))
            if self.listing_draft_id.get().strip():
                ident = int(self.listing_draft_id.get())
                current = self.store.unpublished_listing(ident)
                events = self.store.unpublished_listing_history(ident)
                self.listing_feedback.set(
                    f"초안 #{ident} / {current['state']} / 감사 {len(events)}건 / "
                    f"원본 변경 {current['stale_source']} / 외부 게시·동기화·주문·결제 0건")
            else:
                self.listing_feedback.set(f'로컬 미게시 초안 {len(rows)}건 · 외부 게시 0건')
        except (ValueError, PermissionError, OSError) as exc:
            self.listing_feedback.set(f'조회·무결성 검사 거부: {exc}')

    def _listing_fields(self):
        return (self.listing_title.get(), self.listing_description.get(),
                self.listing_currency.get(), int(self.listing_price_minor.get()),
                self.listing_price_note.get())

    def _listing_create(self) -> None:
        try:
            if not messagebox.askyesno('로컬 미게시 상품 초안',
                    '상품 등록·가격 게시가 아닌 로컬 미검증 초안만 생성합니다. 진행합니까?'):
                self.listing_feedback.set('생성 취소'); return
            row = self.store.create_unpublished_listing(
                int(self.listing_contract_id.get()), int(self.listing_catalog_id.get()),
                *self._listing_fields())
            self.listing_draft_id.set(str(row['id']))
            self._listing_refresh()
        except (ValueError, PermissionError, OSError) as exc:
            self.listing_feedback.set(f'초안 생성 거부: {exc}')

    def _listing_revise(self) -> None:
        try:
            if not messagebox.askyesno('가격 가정 변경',
                    '실제 판매 가격이 아닌 로컬 미게시 가정만 수정합니다. 진행합니까?'):
                self.listing_feedback.set('수정 취소'); return
            self.store.revise_unpublished_listing(int(self.listing_draft_id.get()),
                                                   *self._listing_fields())
            self._listing_refresh()
        except (ValueError, PermissionError, OSError) as exc:
            self.listing_feedback.set(f'수정 거부: {exc}')

    def _listing_review(self) -> None:
        try:
            if not messagebox.askyesno('관리자 자체 검토',
                    '검토는 실제 등록/게시 승인 아님. 미게시 상태로 기록합니까?'):
                self.listing_feedback.set('검토 취소'); return
            row = self.store.review_unpublished_listing(int(self.listing_draft_id.get()),
                                                         self.listing_review_note.get())
            self._listing_refresh()
            self.listing_feedback.set(f"초안 #{row['id']} · {row['state']} · 미게시")
        except (ValueError, PermissionError, OSError) as exc:
            self.listing_feedback.set(f'검토 거부: {exc}')

    def _listing_retire(self) -> None:
        try:
            if not messagebox.askyesno('미게시 초안 폐기',
                    '로컬 미게시 초안만 폐기합니다. 진행합니까?'):
                self.listing_feedback.set('폐기 취소'); return
            row = self.store.retire_unpublished_listing(int(self.listing_draft_id.get()),
                                                         self.listing_review_note.get())
            self._listing_refresh()
            self.listing_feedback.set(f"초안 #{row['id']} · {row['state']} · 미게시")
        except (ValueError, PermissionError, OSError) as exc:
            self.listing_feedback.set(f'폐기 거부: {exc}')

    def _simulated_orders_panel(self, parent: tk.Frame) -> None:
        """Stage73 owner-only LOCAL simulation, never a customer or sale."""
        self.store.require_permission('company:manage')
        panel = self._panel(parent); panel.pack(fill='both', expand=True)
        self._label(panel, '주문 접수 및 상태 관리 · 비실거래 모의실험',
                    size=15, weight='bold').pack(anchor='w')
        self._label(panel, 'Stage72 관리자 자체 검토 미게시 초안만 사용. '
                    '실제 고객/주문/결제/매출/상품 전달은 전혀 발생하지 않습니다. '
                    '중복 방지 토큰에 고객 이름·이메일·계정 정보를 넣지 마세요.',
                    fg='#f7cb92', wraplength=900).pack(anchor='w', pady=4)
        self.sim_order_id = tk.StringVar()
        self.sim_listing_id = tk.StringVar()
        self.sim_token = tk.StringVar()
        self.sim_quantity = tk.StringVar(value='1')
        self.sim_note = tk.StringVar()
        self.sim_feedback = tk.StringVar()
        for label, var in (
            ('모의 주문 ID (상태 변경/조회)', self.sim_order_id),
            ('Stage72 미게시 관리자 검토 초안 ID', self.sim_listing_id),
            ('로컬 중복 방지 토큰 (영숫자/_/- 8~48자)', self.sim_token),
            ('모의 수량 (정수 1~1000)', self.sim_quantity),
            ('관리자 모의 상태 변경 사유 (500자)', self.sim_note),
        ):
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=2)
            self._label(row, label, width=40).pack(side='left')
            tk.Entry(row, textvariable=var, width=55).pack(side='left', fill='x', expand=True)
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=4)
        for label, callback in (
            ('비실거래 모의 주문 생성', self._sim_order_create),
            ('관리자 모의 검토', lambda: self._sim_order_transition('owner_reviewed')),
            ('모의 취소', lambda: self._sim_order_transition('cancelled')),
            ('모의 종료 (배송 없음)', lambda: self._sim_order_transition('closed')),
            ('이력·무결성 조회', self._sim_order_refresh),
        ):
            tk.Button(row, text=label, command=callback).pack(side='left', padx=3)
        self.sim_order_tree = ttk.Treeview(panel,
            columns=('id','listing','quantity','currency','total','state','stale'),
            show='headings', height=5)
        for key, label, width in (
            ('id','모의 ID',80), ('listing','미게시 초안',95), ('quantity','모의 수량',85),
            ('currency','통화',75), ('total','가정 총액',120),
            ('state','비실거래 상태',220), ('stale','원본 변경',90)):
            self.sim_order_tree.heading(key, text=label)
            self.sim_order_tree.column(key, width=width)
        self.sim_order_tree.pack(fill='both', expand=True, pady=4)
        self.sim_order_tree.bind('<<TreeviewSelect>>', self._sim_order_select)
        self._label(panel, '', textvariable=self.sim_feedback,
                    fg='#f7cb92', wraplength=900, justify='left').pack(anchor='w')

    def _sim_order_select(self, event=None) -> None:
        selected = self.sim_order_tree.selection()
        if selected:
            self.sim_order_id.set(str(self.sim_order_tree.item(selected[0], 'values')[0]))

    def _sim_order_refresh(self) -> None:
        try:
            rows = self.store.simulated_orders()
            for node in self.sim_order_tree.get_children():
                self.sim_order_tree.delete(node)
            for row in rows:
                self.sim_order_tree.insert('', 'end', values=(
                    row['id'], row['listing_id'], row['quantity'], row['currency'],
                    row['total_minor'], row['state'], '예' if row['stale_source'] else '아니오'))
            if self.sim_order_id.get().strip():
                ident = int(self.sim_order_id.get())
                current = self.store.simulated_order(ident)
                events = self.store.simulated_order_history(ident)
                self.sim_feedback.set(f"모의 #{ident} / {current['state']} / 감사 {len(events)}건 / "
                                      f"원본 변경 {current['stale_source']} / 실제 주문·결제·매출 0건")
            else:
                self.sim_feedback.set(f'로컬 비실거래 모의 주문 {len(rows)}건 · 실제 주문 0건')
        except (ValueError, PermissionError, OSError) as exc:
            self.sim_feedback.set(f'모의 조회·무결성 검사 거부: {exc}')

    def _sim_order_create(self) -> None:
        try:
            if not messagebox.askyesno('비실거래 모의 주문',
                    '실제 고객/주문/결제/매출 없이 로컬 상태 모의실험만 생성합니다. 진행합니까?'):
                self.sim_feedback.set('모의 생성 취소'); return
            row = self.store.create_simulated_order(
                int(self.sim_listing_id.get()), self.sim_token.get(), int(self.sim_quantity.get()))
            self.sim_order_id.set(str(row['id']))
            self._sim_order_refresh()
        except (ValueError, PermissionError, OSError) as exc:
            self.sim_feedback.set(f'모의 생성 거부: {exc}')

    def _sim_order_transition(self, action: str) -> None:
        try:
            if not messagebox.askyesno('비실거래 상태 전환',
                    '실제 주문/결제/배송이 아닌 로컬 모의 상태만 변경합니다. 진행합니까?'):
                self.sim_feedback.set('모의 상태 변경 취소'); return
            row = self.store.transition_simulated_order(
                int(self.sim_order_id.get()), action, self.sim_note.get())
            self._sim_order_refresh()
            self.sim_feedback.set(f"모의 #{row['id']} / {row['state']} · 실거래 없음")
        except (ValueError, PermissionError, OSError) as exc:
            self.sim_feedback.set(f'모의 상태 변경 거부: {exc}')

    def _business_projects_panel(self, parent: tk.Frame) -> None:
        """Stage66: explicit owner-only planning, never an execution switch."""
        self.store.require_permission('company:manage')
        panel = self._panel(parent)
        panel.pack(fill='both', expand=True)
        self._label(panel, '사업별 프로젝트 계획·기존 업무 연결 (오프라인)', size=15,
                    weight='bold').pack(anchor='w')
        self._label(panel, '상태 active는 계획 표시만 의미합니다. AI 실행·외부 연결·지출 승인 아님.',
                    fg='#f7cb92', wraplength=850).pack(anchor='w', pady=4)
        self.business_project_business_id = tk.StringVar()
        self.business_project_id = tk.StringVar()
        self.business_project_title = tk.StringVar()
        self.business_project_objective = tk.StringVar()
        self.business_project_budget = tk.StringVar(value='0')
        self.business_project_owner = tk.StringVar()
        self.business_project_task_id = tk.StringVar()
        self.business_project_state = tk.StringVar(value='planned')
        self.business_project_feedback = tk.StringVar()
        for label, var in (
            ('사업 ID', self.business_project_business_id),
            ('프로젝트 ID (조회·변경)', self.business_project_id),
            ('프로젝트명', self.business_project_title),
            ('프로젝트 목표', self.business_project_objective),
            ('계획 예산 KRW (지출 아님)', self.business_project_budget),
            ('담당 AI 직원 ID (선택)', self.business_project_owner),
            ('기존 업무 ID (연결·해제)', self.business_project_task_id),
        ):
            row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=2)
            self._label(row, label, width=28).pack(side='left')
            tk.Entry(row, textvariable=var, width=65).pack(side='left', fill='x', expand=True)
        row = tk.Frame(panel, bg='#17253b'); row.pack(fill='x', pady=3)
        self._label(row, '계획 상태', width=28).pack(side='left')
        ttk.Combobox(row, textvariable=self.business_project_state, state='readonly',
                     values=('planned','active','paused','completed','cancelled'), width=22).pack(side='left')
        buttons = tk.Frame(panel, bg='#17253b'); buttons.pack(fill='x', pady=5)
        tk.Button(buttons, text='프로젝트 계획 생성', command=self._business_project_create).pack(side='left', padx=3)
        tk.Button(buttons, text='상태 변경 (계획만)', command=self._business_project_state_change).pack(side='left', padx=3)
        tk.Button(buttons, text='기존 업무 연결', command=lambda: self._business_project_task(True)).pack(side='left', padx=3)
        tk.Button(buttons, text='업무 연결 해제', command=lambda: self._business_project_task(False)).pack(side='left', padx=3)
        tk.Button(buttons, text='목록 갱신', command=self._business_project_refresh).pack(side='left', padx=3)
        self.business_project_tree = ttk.Treeview(panel, columns=('id','business','title','state','tasks'),
                                                  show='headings', height=6)
        for col, title, width in [('id','프로젝트',75),('business','사업 ID',85),
                                  ('title','프로젝트명',260),('state','계획 상태',110),('tasks','연결 업무',95)]:
            self.business_project_tree.heading(col, text=title)
            self.business_project_tree.column(col, width=width)
        self.business_project_tree.pack(fill='both', expand=True, pady=5)
        self.business_project_tree.bind('<<TreeviewSelect>>', self._business_project_select)
        self._label(panel, '', textvariable=self.business_project_feedback, fg='#f7cb92',
                    wraplength=880, justify='left').pack(anchor='w')
        self._business_project_refresh()

    def _business_project_select(self, event=None) -> None:
        selected = self.business_project_tree.selection()
        if selected:
            vals = self.business_project_tree.item(selected[0], 'values')
            self.business_project_id.set(str(vals[0]))
            self.business_project_business_id.set(str(vals[1]))
            self.business_project_state.set(str(vals[3]))
            self._business_project_show()

    def _business_project_create(self) -> None:
        try:
            if not messagebox.askyesno('로컬 프로젝트 계획',
                    '계획만 저장합니다. AI 업무 실행·지출·외부 서비스 실행이 아닙니다. 계속합니까?'):
                self.business_project_feedback.set('생성 취소'); return
            owner = self.business_project_owner.get().strip()
            ident = self.store.create_business_project(
                int(self.business_project_business_id.get()), self.business_project_title.get(),
                self.business_project_objective.get(), int(self.business_project_budget.get()),
                int(owner) if owner else None)
            self.business_project_id.set(str(ident))
            self._business_project_refresh(); self._business_project_show()
        except (ValueError, PermissionError) as exc:
            self.business_project_feedback.set(f'프로젝트 생성 거부: {exc}')

    def _business_project_refresh(self) -> None:
        try:
            rows = self.store.business_projects()
            for node in self.business_project_tree.get_children():
                self.business_project_tree.delete(node)
            for item in rows:
                self.business_project_tree.insert('', 'end', values=(
                    item['id'], item['business_id'], item['title'], item['state'], item['task_count']))
            self.business_project_feedback.set(f'로컬 프로젝트 {len(rows)}건 · 실제 사업 실행 없음')
        except (ValueError, PermissionError) as exc:
            self.business_project_feedback.set(f'프로젝트 조회 거부: {exc}')

    def _business_project_show(self) -> None:
        try:
            item = self.store.business_project(int(self.business_project_id.get()))
            self.business_project_feedback.set(
                f"#{item['id']} / 사업 #{item['business_id']} / {item['state']} / "
                f"계획 예산 {item['planned_budget_krw']:,}원 / 연결 업무 ID {item['task_ids']} / "
                '로컬 계획 상태만 저장됨 · AI/외부 작업/결제 미실행')
        except (ValueError, PermissionError) as exc:
            self.business_project_feedback.set(f'프로젝트 상세 조회 거부: {exc}')

    def _business_project_state_change(self) -> None:
        try:
            if not messagebox.askyesno('프로젝트 상태 변경',
                    '상태는 계획 표시만 변경합니다. 실제 프로젝트 실행·지출은 없습니다. 계속합니까?'):
                self.business_project_feedback.set('상태 변경 취소'); return
            self.store.set_business_project_state(int(self.business_project_id.get()),
                                                  self.business_project_state.get())
            self._business_project_refresh(); self._business_project_show()
        except (ValueError, PermissionError) as exc:
            self.business_project_feedback.set(f'상태 변경 거부: {exc}')

    def _business_project_task(self, add: bool) -> None:
        try:
            if not messagebox.askyesno('기존 업무 연결',
                    '업무 참조만 변경합니다. AI 업무 실행·상태 변경은 하지 않습니다. 계속합니까?'):
                self.business_project_feedback.set('업무 연결 취소'); return
            self.store.set_business_project_task(int(self.business_project_id.get()),
                                                 int(self.business_project_task_id.get()), add)
            self._business_project_refresh(); self._business_project_show()
        except (ValueError, PermissionError) as exc:
            self.business_project_feedback.set(f'업무 연결 거부: {exc}')

    def _market_evidence_panel(self, parent: tk.Frame) -> None:
        """Stage63: manual offline evidence links; no market validation claims."""
        self.store.require_permission('company:manage')
        self.market_candidate_id = tk.StringVar()
        self.market_capture_id = tk.StringVar()
        self.market_kind = tk.StringVar(value='demand')
        self.market_stance = tk.StringVar(value='context')
        self.market_excerpt = tk.StringVar()
        self.market_note = tk.StringVar()
        self.market_link_id = tk.StringVar()
        self.market_review = tk.StringVar(value='noted')
        self.market_feedback = tk.StringVar(value='로컬 수동 자료만 연결합니다. 수요·경쟁 사실 확인은 수행하지 않습니다.')
        panel = self._panel(parent); panel.pack(fill='both', expand=True)
        self._label(panel, '63단계 · 시장 수요/경쟁 근거 검토 (오프라인)', size=16).pack(anchor='w')
        self._label(panel, '62단계 후보 ID와 54단계 수동 자료 ID를 연결합니다. '
                    '출처 URL은 사용자 주장이고, 자료의 진위·시장 수요·경쟁 수준은 검증되지 않았습니다.',
                    fg='#f7cb92', wraplength=860).pack(anchor='w', pady=6)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '후보 ID').pack(side='left')
        tk.Entry(row, textvariable=self.market_candidate_id, width=8).pack(side='left', padx=5)
        self._label(row, '자료 ID').pack(side='left')
        tk.Entry(row, textvariable=self.market_capture_id, width=8).pack(side='left', padx=5)
        ttk.Combobox(row, textvariable=self.market_kind, values=('demand', 'competition'),
                     state='readonly', width=13).pack(side='left', padx=5)
        ttk.Combobox(row, textvariable=self.market_stance,
                     values=('supports', 'challenges', 'context'), state='readonly', width=13).pack(side='left', padx=5)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '로컬 원문에 있는 발췌 (8~240자)').pack(side='left')
        tk.Entry(row, textvariable=self.market_excerpt, width=75).pack(side='left', padx=5, fill='x', expand=True)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '관리자 메모').pack(side='left')
        tk.Entry(row, textvariable=self.market_note, width=60).pack(side='left', padx=5)
        self.market_link_button = tk.Button(row, text='로컬 근거 연결 (확인)', command=self._market_link)
        self.market_link_button.pack(side='left', padx=5)
        row = tk.Frame(panel, bg='#1c2a40'); row.pack(fill='x', pady=4)
        self._label(row, '연결 ID').pack(side='left')
        tk.Entry(row, textvariable=self.market_link_id, width=8).pack(side='left', padx=5)
        ttk.Combobox(row, textvariable=self.market_review,
                     values=('noted', 'excluded', 'unreviewed'), state='readonly', width=13).pack(side='left', padx=5)
        self.market_review_button = tk.Button(row, text='검토 상태 변경', command=self._market_change_review)
        self.market_review_button.pack(side='left', padx=5)
        self.market_refresh_button = tk.Button(row, text='자료·검토 현황 조회', command=self._market_refresh)
        self.market_refresh_button.pack(side='left', padx=5)
        self.market_events_button = tk.Button(row, text='연결 감사 이력', command=self._market_events)
        self.market_events_button.pack(side='left', padx=5)
        self.market_tree = ttk.Treeview(panel, columns=('id','capture','kind','stance','review','source'),
                                        show='headings', height=10)
        for col,title,width in [('id','연결 ID',70),('capture','자료 ID',70),('kind','수요/경쟁',110),
                                ('stance','방향',100),('review','검토',100),('source','출처 주장(검증 안 됨)',300)]:
            self.market_tree.heading(col, text=title)
            self.market_tree.column(col, width=width, anchor='w')
        self.market_tree.pack(fill='both', expand=True, pady=5)
        self.market_tree.bind('<<TreeviewSelect>>', self._market_select)
        self._label(panel, '', textvariable=self.market_feedback, fg='#8ee4b7',
                    wraplength=860, justify='left').pack(anchor='w')

    def _market_select(self, _event=None) -> None:
        selected = self.market_tree.selection()
        if selected:
            self.market_link_id.set(str(self.market_tree.item(selected[0], 'values')[0]))

    def _market_link(self) -> None:
        try:
            cid, rid = int(self.market_candidate_id.get()), int(self.market_capture_id.get())
            if not messagebox.askyesno('로컬 근거 연결',
                '로컬 자료에 존재하는 발췌문만 연결합니다. 시장 검증이나 인터넷 조회는 하지 않습니다. 진행합니까?'):
                self.market_feedback.set('근거 연결 취소'); return
            ident = self.store.link_market_evidence(cid, rid, self.market_kind.get(),
                self.market_stance.get(), self.market_excerpt.get(), self.market_note.get())
            self._market_refresh()
            self.market_feedback.set(f'연결 #{ident} 저장 · 로컬 발췌 일치 확인 · 출처/시장 검증 없음')
        except (ValueError, PermissionError) as exc:
            self.market_feedback.set(f'근거 연결 거부: {exc}')

    def _market_change_review(self) -> None:
        try:
            ident = int(self.market_link_id.get())
            if not messagebox.askyesno('로컬 자료 검토',
                '검토 메모 상태만 변경합니다. 실제 수요나 경쟁이 입증되는 것은 아닙니다. 진행합니까?'):
                self.market_feedback.set('검토 취소'); return
            result = self.store.review_market_evidence(ident, self.market_review.get())
            self._market_refresh()
            self.market_feedback.set(f"연결 #{ident} 검토 상태: {result['review']} · 진위 검증 없음")
        except (ValueError, PermissionError) as exc:
            self.market_feedback.set(f'검토 거부: {exc}')

    def _market_events(self) -> None:
        try:
            ident = int(self.market_link_id.get())
            events = self.store.market_evidence_events(ident, 20)
            self.market_feedback.set('로컬 이력: ' + ', '.join(
                f"{item['action']}({item['id']})" for item in events))
        except (ValueError, PermissionError) as exc:
            self.market_feedback.set(f'이력 조회 거부: {exc}')

    def _market_refresh(self) -> None:
        try:
            cid = int(self.market_candidate_id.get())
            rows = self.store.market_evidence(cid)
            for item in self.market_tree.get_children():
                self.market_tree.delete(item)
            for item in rows:
                self.market_tree.insert('', 'end', values=(item['id'],item['capture_id'],
                    item['kind'],item['stance'],item['review'],item['source_title']))
            status = self.store.market_evidence_summary(cid)
            demand, competition = status['categories']['demand'], status['categories']['competition']
            self.market_feedback.set(
                f"로컬 연결 {len(rows)}개 · 수요 검토 {demand['reviewed_links']}개 · "
                f"경쟁 검토 {competition['reviewed_links']}개 · 실제 시장/출처 진위 검증 없음")
        except (ValueError, PermissionError) as exc:
            self.market_feedback.set(f'자료 조회 거부: {exc}')

    def _offline_research_panel(self, parent: tk.Frame) -> None:
        self.research_url = tk.StringVar()
        self.research_title = tk.StringVar()
        self.research_kind = tk.StringVar(value='manual_text')
        self.research_query = tk.StringVar()
        self.research_feedback = tk.StringVar()
        self.research_include_archived = tk.BooleanVar(value=False)
        self.research_selected_id = None
        self._label(parent, '54단계 보완: 수동 연구·공개 HTTPS 읽기·동일 호스트 제한 크롤링·플러그인 자료 가져오기',
                    bg='#121c2d', wraplength=950).pack(anchor='w', pady=4)
        self._label(parent, 'URL은 출처 메타데이터이며 실제 접속·진위 검증하지 않습니다. AI 자동 조사 기능 없음.',
                    bg='#121c2d', fg='#bfcfe5', wraplength=950).pack(anchor='w', pady=3)
        row=tk.Frame(parent,bg='#121c2d');row.pack(fill='x',pady=3)
        self._label(row,'출처 URL',bg='#121c2d').pack(side='left')
        tk.Entry(row,textvariable=self.research_url,width=85).pack(side='left',fill='x',expand=True,padx=7)
        webrow=tk.Frame(parent,bg='#121c2d');webrow.pack(fill='x',pady=3)
        self.research_online_confirm_host = tk.StringVar()
        self.research_online_consent = tk.BooleanVar(value=False)
        self._label(webrow,'허용 호스트 (URL과 일치)',bg='#121c2d').pack(side='left')
        tk.Entry(webrow,textvariable=self.research_online_confirm_host,width=28).pack(side='left',padx=4)
        tk.Checkbutton(webrow,text='이번 공개 HTTPS GET 허용',variable=self.research_online_consent,
                       bg='#121c2d',fg='white',selectcolor='#304561').pack(side='left',padx=5)
        self.research_online_button=tk.Button(webrow,text='온라인 공개 자료 읽어 저장',
                                              command=self._begin_online_research)
        self.research_online_button.pack(side='left',padx=5)
        crawler_row=tk.Frame(parent,bg='#121c2d');crawler_row.pack(fill='x',pady=3)
        self.research_crawl_button=tk.Button(crawler_row,text='robots.txt 확인 후 크롤링 (최대 3쪽)',
                                            command=self._begin_site_crawl)
        self.research_crawl_button.pack(side='left',padx=5)
        self.research_plugin_import_button=tk.Button(crawler_row,text='크롤링 플러그인 JSON 가져오기',
                                                    command=self._import_web_plugin_export)
        self.research_plugin_import_button.pack(side='left',padx=5)
        self._label(crawler_row,'TinyFish/Firecrawl/Tavily 결과 파일 (실제 플러그인 계정/인증은 별도)',
                    bg='#121c2d',fg='#bfcfe5').pack(side='left',padx=7)
        self._label(parent, '사용자 클릭 1회/1 URL, HTTPS GET 전용, 응답 128KiB 제한, DNS 공개 IP 검사, 리다이렉트·로그인·게시 금지. 출처 주장/사실 검증 아님.',
                    bg='#121c2d',fg='#bfcfe5',wraplength=950).pack(anchor='w')
        row=tk.Frame(parent,bg='#121c2d');row.pack(fill='x',pady=3)
        self._label(row,'제목',bg='#121c2d').pack(side='left')
        tk.Entry(row,textvariable=self.research_title,width=35).pack(side='left',padx=7)
        ttk.Combobox(row,textvariable=self.research_kind,values=('manual_text','html_snapshot'),
                     state='readonly',width=19).pack(side='left',padx=4)
        self.research_add_button=tk.Button(row,text='자료 등록',command=self._add_offline_research)
        self.research_add_button.pack(side='left',padx=5)
        self.research_import_button=tk.Button(row,text='로컬 파일 가져오기',command=self._import_offline_research_file)
        self.research_import_button.pack(side='left',padx=5)
        self.research_bundle_button=tk.Button(row,text='자료 묶음(JSON) 가져오기',command=self._import_offline_research_bundle)
        self.research_bundle_button.pack(side='left',padx=5)
        bundle_row=tk.Frame(parent,bg='#121c2d');bundle_row.pack(fill='x',pady=2)
        self.research_bundle_manifest_button=tk.Button(
            bundle_row,text='로컬 묶음 JSON 목록 만들기',command=self._create_offline_research_bundle_manifest)
        self.research_bundle_manifest_button.pack(side='left',padx=5)
        self.research_bundle_custody_button=tk.Button(
            bundle_row,text='등록 묶음 원본 파일 일괄 재검사',
            command=self._verify_offline_research_bundle_files)
        self.research_bundle_custody_button.pack(side='left',padx=5)
        self._label(bundle_row,'파일 1~20개·직접 입력한 URL/제목으로 목록만 저장 (자료 등록은 별도 승인)',
                    bg='#121c2d').pack(side='left',padx=7)
        receipt_row=tk.Frame(parent,bg='#121c2d');receipt_row.pack(fill='x',pady=2)
        self.research_receipt_create_button=tk.Button(
            receipt_row,text='묶음 파일 지문 JSON 저장',command=self._create_offline_research_bundle_receipt)
        self.research_receipt_create_button.pack(side='left',padx=5)
        self.research_receipt_verify_button=tk.Button(
            receipt_row,text='묶음 지문 재검사',command=self._verify_offline_research_bundle_receipt)
        self.research_receipt_verify_button.pack(side='left',padx=5)
        self._label(receipt_row,'등록 전 로컬 지문 기록 · 원본 출처 인증 아님',
                    bg='#121c2d').pack(side='left',padx=7)
        self.research_file_custody_button = tk.Button(
            row, text='선택 자료 원본 파일 재검사', command=self._recheck_offline_research_import_file)
        self.research_file_custody_button.pack(side='left', padx=5)
        self.research_archive_button=tk.Button(row,text='선택 자료 보관',command=self._archive_offline_research)
        self.research_archive_button.pack(side='left',padx=5)
        self._label(parent,'내용 붙여넣기 · HTML 방식은 script/style을 제거하고 글만 저장',
                    bg='#121c2d').pack(anchor='w')
        self.research_content=tk.Text(parent,height=5,wrap='word',font=('Consolas',10))
        self.research_content.pack(fill='both',expand=True,pady=3)
        row=tk.Frame(parent,bg='#121c2d');row.pack(fill='x',pady=3)
        self._label(row,'검색',bg='#121c2d').pack(side='left')
        tk.Entry(row,textvariable=self.research_query,width=35).pack(side='left',padx=5)
        self.research_search_button=tk.Button(row,text='조회',command=self._refresh_offline_research)
        self.research_search_button.pack(side='left',padx=5)
        self.research_audit_button=tk.Button(row,text='로컬 증거 무결성 검사',command=self._audit_offline_research)
        self.research_audit_button.pack(side='left',padx=5)
        self.research_compare_id=tk.StringVar()
        self._label(row,'비교 ID',bg='#121c2d').pack(side='left',padx=(8,2))
        tk.Entry(row,textvariable=self.research_compare_id,width=8).pack(side='left')
        self.research_compare_button=tk.Button(row,text='선택 자료와 비교',command=self._compare_offline_research)
        self.research_compare_button.pack(side='left',padx=5)
        self.research_links_button=tk.Button(row,text='선택 HTML 링크 목록',command=self._show_offline_research_links)
        self.research_links_button.pack(side='left',padx=5)
        self.research_trace_button=tk.Button(row,text='로컬 참조 연결 추적',
                                             command=self._trace_offline_research_references)
        self.research_trace_button.pack(side='left',padx=5)
        tk.Checkbutton(row,text='보관 포함',variable=self.research_include_archived,
                       bg='#121c2d',fg='white',selectcolor='#304561').pack(side='left')
        report_row = tk.Frame(parent, bg='#121c2d')
        report_row.pack(fill='x', pady=3)
        self.research_evidence_button = tk.Button(report_row, text='검색어 근거 발췌 보고서',
                                                  command=self._show_local_evidence_report)
        self.research_evidence_button.pack(side='left', padx=5)
        self.research_export_button = tk.Button(report_row, text='근거 보고서 JSON 저장',
                                                command=self._export_local_evidence_report)
        self.research_export_button.pack(side='left', padx=5)
        self.research_verify_button = tk.Button(report_row, text='근거 JSON 재검사',
                                                command=self._verify_local_evidence_export)
        self.research_verify_button.pack(side='left', padx=5)
        self.research_followup_button = tk.Button(report_row, text='미확인 링크 후속 조사 목록',
                                                  command=self._show_offline_research_followups)
        self.research_followup_button.pack(side='left', padx=5)
        self.research_followup_export_button = tk.Button(
            report_row, text='후속 조사 JSON 저장',
            command=self._export_offline_research_followups)
        self.research_followup_export_button.pack(side='left', padx=5)
        self.research_followup_verify_button = tk.Button(
            report_row, text='후속 조사 JSON 재검사',
            command=self._verify_offline_research_followup_export)
        self.research_followup_verify_button.pack(side='left', padx=5)
        self.research_review_filter = tk.StringVar(value='all')
        self._label(report_row, '수동 검토 상태', bg='#121c2d').pack(side='left', padx=3)
        self.research_review_filter_combo = ttk.Combobox(
            report_row, textvariable=self.research_review_filter,
            values=('all', 'pending', 'deferred'), state='readonly', width=10)
        self.research_review_filter_combo.pack(side='left', padx=3)
        self.research_followup_page = 1
        self.research_review_filter_combo.bind('<<ComboboxSelected>>',
            self._reset_offline_research_followup_page)
        followup_paging_row = tk.Frame(parent, bg='#121c2d')
        followup_paging_row.pack(fill='x', pady=3)
        self.research_followup_prev_button = tk.Button(
            followup_paging_row, text='이전 40개', command=self._previous_offline_research_followups)
        self.research_followup_prev_button.pack(side='left', padx=3)
        self.research_followup_next_button = tk.Button(
            followup_paging_row, text='다음 40개', command=self._next_offline_research_followups)
        self.research_followup_next_button.pack(side='left', padx=3)
        self.research_source_overlap_button = tk.Button(
            followup_paging_row, text='자료 중복·버전 차이 점검',
            command=self._show_offline_research_source_overlap)
        self.research_source_overlap_button.pack(side='left', padx=3)
        self.research_followup_domains_button = tk.Button(
            followup_paging_row, text='호스트별 조사 현황',
            command=self._show_offline_research_followup_domains)
        self.research_followup_domains_button.pack(side='left', padx=3)
        self.research_url_preflight_button = tk.Button(
            followup_paging_row, text='저장 URL 위험 신호',
            command=self._show_offline_research_url_preflight)
        self.research_url_preflight_button.pack(side='left', padx=3)
        self.research_url_preflight_export_button = tk.Button(
            followup_paging_row, text='URL 경고 JSON 저장',
            command=self._export_offline_research_url_preflight)
        self.research_url_preflight_export_button.pack(side='left', padx=3)
        self.research_url_preflight_verify_button = tk.Button(
            followup_paging_row, text='URL 경고 JSON 재검사',
            command=self._verify_offline_research_url_preflight_export)
        self.research_url_preflight_verify_button.pack(side='left', padx=3)
        self._label(followup_paging_row,
                    '로컬 링크 최신 최대 2,000개 중 수동 검토 필터 적용 후 40개씩 표시',
                    bg='#121c2d').pack(side='left', padx=8)
        followup_row = tk.Frame(parent, bg='#121c2d')
        followup_row.pack(fill='x', pady=3)
        self.research_followup_url = tk.StringVar()
        self.research_followup_action = tk.StringVar(value='noted')
        self.research_followup_note = tk.StringVar()
        self._label(followup_row, '링크 URL', bg='#121c2d').pack(side='left', padx=3)
        tk.Entry(followup_row, textvariable=self.research_followup_url, width=34).pack(side='left', padx=3)
        ttk.Combobox(followup_row, textvariable=self.research_followup_action,
                     values=('noted', 'deferred', 'reopen'), state='readonly', width=10).pack(side='left', padx=3)
        self._label(followup_row, '메모', bg='#121c2d').pack(side='left', padx=3)
        tk.Entry(followup_row, textvariable=self.research_followup_note, width=20).pack(side='left', padx=3)
        self.research_followup_note_button = tk.Button(followup_row, text='수동 검토 기록',
                                                      command=self._record_offline_research_followup_note)
        self.research_followup_note_button.pack(side='left', padx=3)
        self.research_followup_history_button = tk.Button(followup_row, text='URL 검토 이력',
                                                         command=self._show_offline_research_followup_history)
        self.research_followup_history_button.pack(side='left', padx=3)
        self._label(report_row, '저장된 본문 검색어와 원문 행·자료 ID·해시 표시 / 온라인 출처 미검증',
                    bg='#121c2d', wraplength=780).pack(side='left', padx=5)
        self.research_tree=ttk.Treeview(parent,columns=('id','title','source','kind','status'),
                                        show='headings',height=5)
        for key,label,width in (('id','ID',50),('title','제목',210),('source','참조 URL',330),
                                ('kind','방식',110),('status','상태',95)):
            self.research_tree.heading(key,text=label)
            self.research_tree.column(key,width=width,stretch=(key in ('title','source')))
        self.research_tree.pack(fill='x',pady=4)
        self.research_tree.bind('<<TreeviewSelect>>', self._load_offline_research)
        self._label(parent,'선택 자료 상세 · 기록은 읽기 전용 (원문과 출처 미검증)',
                    bg='#121c2d').pack(anchor='w')
        self.research_detail=tk.Text(parent,height=5,wrap='word',state='disabled')
        self.research_detail.pack(fill='both',expand=True,pady=3)
        self._label(parent,'',textvariable=self.research_feedback,bg='#121c2d',wraplength=920).pack(anchor='w')
        self._refresh_offline_research()

    def _refresh_offline_research(self) -> None:
        try:
            for row in self.research_tree.get_children():
                self.research_tree.delete(row)
            records=self.store.search_offline_research(self.research_query.get(),
                include_archived=self.research_include_archived.get())
            for record in records:
                self.research_tree.insert('','end',values=(record['id'],record['title'],
                    record['source_url'],record['capture_kind'],
                    '보관' if record['archived_at'] else '미검증'))
            self.research_feedback.set(f'{len(records)}건 조회 (출처 진위 확인 안 됨)')
        except (ValueError,PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _load_offline_research(self, _event=None) -> None:
        selected=self.research_tree.selection()
        if not selected:
            return
        try:
            identifier=int(self.research_tree.item(selected[0],'values')[0])
            document=self.store.read_offline_research(identifier)
            self.research_selected_id=identifier
            body=(f'제목: {document["title"]}\n출처 URL (미검증): {document["source_url"]}\n'
                  f'SHA-256: {document["content_sha256"]}\n등록: {document["recorded_at"]}\n'
                  f'검증 상태: {document["source_verification"]}\n\n{document["body"]}')
            if document.get('local_import'):
                imported=document['local_import']
                body += (f'\n\n[로컬 파일 증거 - 웹 출처 진위는 미검증]'
                         f'\n파일 이름: {imported["original_filename"]}'
                         f'\n원본 바이트 SHA-256: {imported["raw_sha256"]}'
                         f'\n원본 크기: {imported["raw_size"]}바이트'
                         f'\n가져온 시각: {imported["imported_at"]}')
            if document.get('bundle_import'):
                batch=document['bundle_import']
                body += (f'\n\n[로컬 자료 묶음 - 웹 출처 진위는 미검증]'
                         f'\n묶음 #{batch["batch_id"]} / 순서 {batch["ordinal"]}/{batch["item_count"]}'
                         f'\n목록 파일: {batch["manifest_filename"]}'
                         f'\n목록 SHA-256: {batch["manifest_sha256"]}')
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0','end')
            self.research_detail.insert('1.0',body)
            self.research_detail.configure(state='disabled')
            self.research_feedback.set(f'자료 #{identifier} 내용 조회 · 출처 미검증')
        except (ValueError,PermissionError) as exc:
            self.research_selected_id=None
            self.research_feedback.set(str(exc))

    def _begin_online_research(self) -> None:
        """User-controlled public HTTPS GET; worker never calls Tk directly."""
        if not self.research_online_consent.get():
            self.research_feedback.set('온라인 공개 자료 요청은 명시적 허용 확인이 필요합니다.')
            return
        url = self.research_url.get().strip()
        hostname = self.research_online_confirm_host.get().strip()
        title = self.research_title.get().strip()
        # Validate before thread creation, without DNS or network side effects.
        try:
            from desktop.public_web_research import check_public_url
            check_public_url(url, hostname)
            if not 1 <= len(title) <= 200:
                raise ValueError('자료 제목을 먼저 입력하세요.')
            self.store.require_permission('company:manage')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(f'온라인 자료 요청 거부: {exc}')
            return
        self.research_online_consent.set(False)  # single-use consent
        self.research_online_button.configure(state='disabled')
        self.research_feedback.set('이 URL 공개 HTTPS GET 요청 중 (최대 8초/응답 크기 제한).')
        generation = self._session_generation
        result_queue = queue.Queue(maxsize=1)

        def run():
            try:
                result = self.store.fetch_public_research(url, hostname, title, consent=True)
                result_queue.put(('ok', result))
            except (ValueError, PermissionError, OSError) as exc:
                result_queue.put(('error', str(exc)))

        threading.Thread(target=run, name='aiwack-public-get', daemon=True).start()

        def poll():
            if generation != self._session_generation or not self.store.is_authenticated:
                return
            try:
                kind, message = result_queue.get_nowait()
            except queue.Empty:
                if self.root.winfo_exists():
                    self.root.after(60, poll)
                return
            self.research_online_button.configure(state='normal')
            if kind == 'ok':
                self.research_feedback.set(
                    f'공개 HTTPS 자료 등록 ID={message["capture_id"]}, {message["bytes"]} bytes; 출처 사실 미검증')
                self._refresh_offline_research()
            else:
                self.research_feedback.set(f'공개 HTTPS GET 실패/차단: {message}')

        self.root.after(60, poll)

    def _begin_site_crawl(self) -> None:
        """Run owner-approved bounded same-origin crawl outside the UI thread."""
        if not self.research_online_consent.get():
            self.research_feedback.set('크롤링 전에 이번 공개 HTTPS 요청 허용을 확인하세요.')
            return
        url = self.research_url.get().strip()
        hostname = self.research_online_confirm_host.get().strip()
        try:
            from desktop.public_web_research import check_public_url
            check_public_url(url, hostname)
            self.store.require_permission('company:manage')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(f'크롤링 거부: {exc}')
            return
        session_generation = self._session_generation
        self.research_crawl_button.configure(state='disabled')
        result_queue: queue.Queue = queue.Queue()

        def work():
            try:
                record = self.store.crawl_public_site_robots_checked(url, hostname, consent=True,
                                                      max_pages=3, max_depth=1)
                result_queue.put(('ok', record))
            except Exception as exc:
                result_queue.put(('error', str(exc)))

        threading.Thread(target=work, daemon=True).start()
        def poll():
            if session_generation != self._session_generation:
                return
            try:
                kind, result = result_queue.get_nowait()
            except queue.Empty:
                if self.root.winfo_exists():
                    self.root.after(60, poll)
                return
            self.research_crawl_button.configure(state='normal')
            if kind == 'ok':
                self._refresh_offline_research()
                self.research_feedback.set(
                    f'robots.txt 확인 후 공개 페이지 {result["pages"]}건 수집 / 오류 {result["failures"]}건; 외부 사실 미검증')
            else:
                self.research_feedback.set(f'크롤링 실패/차단: {result}')
        self.root.after(60, poll)

    def _import_web_plugin_export(self) -> None:
        """Read a deliberately selected JSON file; never call plugin APIs from EXE."""
        path = filedialog.askopenfilename(
            title='크롤링 플러그인 결과 JSON 선택',
            filetypes=[('JSON export','*.json'), ('모든 파일','*.*')])
        if not path:
            return
        try:
            import os
            if os.path.getsize(path) > 800_000:
                raise ValueError('JSON 파일이 800KB 한도를 초과합니다.')
            with open(path,'rb') as stream:
                raw = stream.read(800_001)
            result = self.store.import_web_plugin_export(raw)
            self._refresh_offline_research()
            self.research_feedback.set(
                f'{result["provider"]} 외부 자료 {len(result["capture_ids"])}건 수동 가져오기; 출처 진위 미검증')
        except (OSError, ValueError, PermissionError) as exc:
            self.research_feedback.set(f'플러그인 자료 가져오기 실패: {exc}')

    def _add_offline_research(self) -> None:
        try:
            identifier=self.store.add_offline_research(self.research_url.get(),
                self.research_title.get(),self.research_content.get('1.0','end-1c'),
                self.research_kind.get())
            self._refresh_offline_research()
            self.research_feedback.set(f'자료 #{identifier} 등록 · 실제 웹 요청 없음 / 출처 미검증')
        except (ValueError,PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _import_offline_research_file(self) -> None:
        """Import a user-selected local file only, never retrieve a remote URL."""
        path=filedialog.askopenfilename(
            title='이미 저장된 로컬 자료 파일 선택',
            filetypes=[('텍스트 및 HTML', '*.txt *.md *.html *.htm'), ('모든 파일', '*.*')])
        if not path:
            return
        try:
            ident=self.store.import_offline_research_file(
                self.research_url.get(), self.research_title.get(), path)
            self._refresh_offline_research()
            self.research_feedback.set(f'자료 #{ident} 로컬 파일 등록 · 원본 해시 저장 / 웹 출처 미검증')
        except (ValueError,PermissionError,OSError) as exc:
            self.research_feedback.set(str(exc))

    def _recheck_offline_research_import_file(self) -> None:
        """Re-select an existing local snapshot, comparing bytes without DB writes."""
        if self.research_selected_id is None:
            self.research_feedback.set('재검사할 자료를 목록에서 선택해 주세요.')
            return
        path = filedialog.askopenfilename(
            title='등록 당시 원본 파일과 비교할 로컬 파일 선택',
            filetypes=[('모든 파일', '*.*')])
        if not path:
            return
        try:
            result = self.store.recheck_offline_research_import_file(
                self.research_selected_id, path)
            lines = [
                '[선택 자료의 로컬 원본 파일 바이트 재검사 — 읽기 전용]',
                f'자료 #{result["capture_id"]} · 보관됨: {result["archived"]}',
                f'등록 당시 이름: {result["recorded_filename"]}',
                f'선택 파일 이름: {result["selected_filename"]}',
                f'파일 이름 일치: {"예" if result["filename_match"] else "아니오"}',
                f'바이트 길이: 등록 {result["recorded_size"]} / 현재 {result["selected_size"]}',
                f'파일 바이트 SHA-256 일치: {"예" if result["bytes_match"] else "아니오"}',
                f'등록 SHA-256: {result["recorded_sha256"]}',
                f'선택 SHA-256: {result["selected_sha256"]}',
                '주의: 이 결과는 선택한 파일과 등록 당시 해시의 비교일 뿐입니다.',
                '실제 웹 출처, 파일 보관 연속성, 제3자 서명은 검증하지 않습니다.',
            ]
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', '\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set(
                '선택한 로컬 파일 바이트 일치' if result['bytes_match']
                else '주의: 선택한 로컬 파일 바이트가 등록 기록과 다릅니다.')
        except (ValueError, PermissionError, OSError) as exc:
            self.research_feedback.set(f'로컬 파일 재검사 실패: {exc}')

    def _create_offline_research_bundle_manifest(self) -> None:
        """Owner selects files and supplies each unverified claimed URL."""
        try:
            self.store.require_permission('company:manage')
        except (PermissionError, ValueError) as exc:
            self.research_feedback.set(str(exc))
            return
        paths = filedialog.askopenfilenames(
            title='하나의 폴더에서 저장된 로컬 텍스트/HTML 파일 1~20개 선택',
            filetypes=[('텍스트 및 HTML','*.txt *.md *.html *.htm'),('모든 파일','*.*')])
        if not paths:
            return
        if len(paths) > 20:
            self.research_feedback.set('자료는 최대 20개까지만 선택할 수 있습니다.')
            return
        entries=[]
        for filepath in paths:
            url = simpledialog.askstring('미검증 출처 URL 수동 입력',
                f'{Path(filepath).name}의 출처 URL을 직접 입력해 주세요.\n'
                '인터넷 접속·출처 진위 확인은 하지 않습니다.',parent=self.root)
            if url is None:
                self.research_feedback.set('목록 생성 취소 · 파일/DB 변경 없음')
                return
            title = simpledialog.askstring('자료 제목 수동 입력',
                f'{Path(filepath).name}의 표시 제목을 입력해 주세요.',
                initialvalue=Path(filepath).stem[:200],parent=self.root)
            if title is None:
                self.research_feedback.set('목록 생성 취소 · 파일/DB 변경 없음')
                return
            entries.append((filepath,url,title))
        if not messagebox.askyesno('로컬 JSON 목록 생성 승인',
                f'선택한 {len(entries)}개 파일의 목록만 로컬 폴더에 저장하시겠습니까?\n'
                '자료는 등록되지 않으며 URL은 미검증 주장입니다.',parent=self.root):
            self.research_feedback.set('목록 생성 취소 · 파일/DB 변경 없음')
            return
        output=filedialog.asksaveasfilename(
            title='선택한 자료 파일과 동일한 폴더에 새 JSON 목록 저장',
            defaultextension='.json',filetypes=[('JSON 목록','*.json')])
        if not output:
            return
        try:
            report=self.store.create_offline_research_bundle_manifest(entries, output)
            self.research_feedback.set(
                f'로컬 목록 {report["manifest_filename"]} 생성: {report["item_count"]}개 · '
                '아직 SQLite 등록 없음 / 실제 웹 출처 미검증')
        except (ValueError,PermissionError,OSError) as exc:
            self.research_feedback.set(f'로컬 목록 생성 거부: {exc}')

    def _create_offline_research_bundle_receipt(self) -> None:
        """Explicit local checkpoint before import; no SQLite or web access."""
        try:
            self.store.require_permission('company:manage')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(str(exc))
            return
        manifest=filedialog.askopenfilename(title='원본 자료 묶음 JSON 목록 선택',
                    filetypes=[('JSON 파일','*.json')])
        if not manifest:
            return
        if not messagebox.askyesno('로컬 묶음 지문 기록',
                '선택한 목록과 파일의 SHA-256을 로컬 JSON으로 기록하시겠습니까?\n'
                '출처 인증/전자서명이 아니며 SQLite에는 등록되지 않습니다.', parent=self.root):
            self.research_feedback.set('지문 기록 생성 취소')
            return
        dest=filedialog.asksaveasfilename(title='원본 자료와 같은 폴더에 새 지문 기록 저장',
                   defaultextension='.json',filetypes=[('JSON 파일','*.json')])
        if not dest:
            return
        try:
            result=self.store.create_offline_research_bundle_receipt(manifest,dest)
            self.research_feedback.set(
                f'로컬 지문 기록 {result["receipt_filename"]}: {result["item_count"]}개 파일, '
                'SQLite 변경 없음 · 출처 미검증')
        except (ValueError, PermissionError, OSError) as exc:
            self.research_feedback.set(f'지문 기록 생성 거부: {exc}')

    def _verify_offline_research_bundle_receipt(self) -> None:
        try:
            self.store.require_permission('company:manage')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(str(exc))
            return
        path=filedialog.askopenfilename(title='재검사할 로컬 지문 기록 JSON 선택',
                   filetypes=[('JSON 파일','*.json')])
        if not path:
            return
        try:
            result=self.store.verify_offline_research_bundle_receipt(path)
            lines=['[오프라인 묶음 지문 재검사 — 읽기 전용]',
                   f'목록 상태: {result["manifest_status"]}',
                   f'파일 일치 {result["counts"]["match"]} · 변경 {result["counts"]["changed"]} · '
                   f'검사 불가 {result["counts"]["unavailable"]}']
            for item in result['items']:
                lines.append(f'  {item["file"]}: {item["status"]}')
            if result['changed_during_check']:
                lines.append('주의: 검사 도중 목록 또는 파일 상태가 변경되었습니다. 다시 검사하세요.')
            lines.append('SHA-256 자체 기록만 검사; 웹 출처 진위/전자서명 미검증, SQLite 변경 없음')
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0','end')
            self.research_detail.insert('1.0','\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('지문 재검사 일치' if result['passed'] else '주의: 지문/목록 재검사 불일치')
        except (ValueError, PermissionError, OSError) as exc:
            self.research_feedback.set(f'지문 재검사 실패: {exc}')

    def _import_offline_research_bundle(self) -> None:
        """Preview local bytes and conflicts, then import only after owner consent."""
        path = filedialog.askopenfilename(
            title='로컬 자료 묶음 목록(JSON) 선택',
            filetypes=[('JSON 목록', '*.json'), ('모든 파일', '*.*')])
        if not path:
            return
        try:
            preview = self.store.preview_offline_research_bundle(path)
            lines = ['[로컬 JSON 자료 묶음 가져오기 전 점검 — 읽기 전용]',
                     f'목록: {preview["manifest_filename"]} · {preview["item_count"]}건',
                     f'완전 중복(등록 차단): {preview["duplicate_count"]}건',
                     f'출처/버전 차이 경고: {preview["warning_item_count"]}개 항목',
                     f'URL 문자열 위험 신호: {preview["url_warning_item_count"]}개 항목',
                     (f'HTML 참조 링크(오프라인): {preview["html_link_count"]}건 · '
                      f'묶음 내 {preview["html_link_status_counts"]["in_bundle"]} · '
                      f'기존 활성 {preview["html_link_status_counts"]["registered_active"]} · '
                      f'보관 {preview["html_link_status_counts"]["registered_archived"]} · '
                      f'미등록 {preview["html_link_status_counts"]["unregistered"]}'),
                     (f'HTML 자기 출처 표기(미검증): {preview["source_hint_count"]}건 · '
                      f'입력 URL과 일치 {preview["source_hint_status_counts"]["match"]} · '
                      f'불일치 {preview["source_hint_status_counts"]["mismatch"]} · '
                      f'형식 오류 {preview["source_hint_status_counts"]["invalid"]}'),
                     (f'HTML 이동 지시(실행 안 함): {preview["navigation_directive_count"]}건 · '
                      f'동일 출처 {preview["navigation_directive_status_counts"]["same_origin"]} · '
                      f'다른 출처 {preview["navigation_directive_status_counts"]["other_origin"]} · '
                      f'형식 오류 {preview["navigation_directive_status_counts"]["invalid"]}'),
                     (f'HTML 폼·삽입·스크립트 대상(실행 안 함): {preview["active_target_count"]}건 · '
                      f'폼 {preview["active_target_kind_counts"]["form"]} · '
                      f'iframe {preview["active_target_kind_counts"]["iframe"]} · '
                      f'script {preview["active_target_kind_counts"]["script"]} · '
                      f'다른 출처 {preview["active_target_status_counts"]["other_origin"]} · '
                      f'형식 오류 {preview["active_target_status_counts"]["invalid"]}'),
                     (f'HTML 폼의 입력 유형(값 수집 안 함): {preview["form_control_count"]}건 · '
                      f'암호 {preview["form_control_kind_counts"]["password"]} · '
                      f'파일 {preview["form_control_kind_counts"]["file"]} · '
                      f'숨김 {preview["form_control_kind_counts"]["hidden"]} · '
                      f'GET 방식 암호 입력 {preview["form_password_get_count"]}'),
                     (f'HTML 반응형 이미지 srcset(요청 안 함): {preview["responsive_image_count"]}건 · '
                      f'img {preview["responsive_image_element_counts"]["img"]} · '
                      f'source {preview["responsive_image_element_counts"]["source"]} · '
                      f'다른 출처 {preview["responsive_image_status_counts"]["other_origin"]} · '
                      f'형식 오류 {preview["responsive_image_status_counts"]["invalid"]}'),
                     (f'HTML 수동 리소스 참조(접속 안 함): {preview["passive_resource_count"]}건 · '
                      f'이미지 {preview["passive_resource_kind_counts"]["image"]} · '
                      f'스타일 {preview["passive_resource_kind_counts"]["stylesheet"]} · '
                      f'미디어 {preview["passive_resource_kind_counts"]["media"]} · '
                      f'다른 출처 {preview["passive_resource_status_counts"]["other_origin"]} · '
                      f'형식 오류 {preview["passive_resource_status_counts"]["invalid"]}'),
                     (f'HTML 내부 CSS 참조(실행 안 함): {preview["css_reference_count"]}건 · '
                      f'다른 출처 {preview["css_reference_status_counts"]["other_origin"]} · '
                      f'형식 오류 {preview["css_reference_status_counts"]["invalid"]}'),
                     (f'HTML 이용·색인 자체 표기(미검증): {preview["usage_hint_count"]}건 · '
                      f'robots {preview["usage_hint_kind_counts"]["robots"]} · '
                      f'라이선스 링크 {preview["usage_hint_kind_counts"]["license"]} · '
                      f'제한 표기 {preview["usage_hint_status_counts"]["restricted"]}'),
                     f'목록 SHA-256: {preview["manifest_sha256"]}']
            warning_labels = {
                'existing_url_other_body': '기존 등록 자료와 동일 URL·다른 본문',
                'existing_body_other_url': '기존 등록 자료와 동일 본문·다른 URL',
                'bundle_url_other_body': '묶음 안 동일 URL·다른 본문',
                'bundle_body_other_url': '묶음 안 동일 본문·다른 URL',
            }
            url_labels = {
                'invalid_url': 'URL 형식 주의',
                'embedded_credentials': 'URL에 사용자명/비밀번호 포함 가능',
                'nonstandard_port': '비표준 포트 지정',
                'trailing_dot_hostname': '호스트명 끝에 점 포함',
                'encoded_or_scoped_hostname': '특수/영역 지정 호스트명',
                'internationalized_hostname': '국제화 호스트명',
                'ip_literal': 'IP 주소 직접 사용',
                'non_global_ip_literal': '비공개/로컬 등 전역 라우팅 불가 IP',
                'ambiguous_numeric_hostname': '숫자형 IP 별칭 후보',
                'local_name': '로컬 네트워크 호스트명',
                'single_label_hostname': '단일 라벨 호스트명',
            }
            for item in preview['items']:
                label = {'new': '신규 후보', 'already_registered': '기존 자료 중복',
                         'duplicate_in_bundle': '묶음 내부 중복'}[item['status']]
                lines.append(f'{item["ordinal"]}. {item["filename"]} · {label} · '
                             f'{item["raw_size"]}바이트 · {item["claimed_source_url"]}')
                for code in item['warnings']:
                    examples = item['warning_examples'][code]
                    label_type = '기존 자료 ID' if code.startswith('existing_') else '묶음 순번'
                    lines.append(f'  ⚠ {warning_labels[code]} ({label_type} 예: '
                                 + ', '.join(map(str, examples)) + ')')
                for code in item['url_warning_codes']:
                    lines.append(f'  ⚠ URL 사전 점검: {url_labels[code]} ({code})')
                if item['source_hint_count']:
                    hints = item['source_hint_status_counts']
                    lines.append(f'  HTML 출처 자체 표기 {item["source_hint_count"]}건: '
                                 f'일치 {hints["match"]}, 불일치 {hints["mismatch"]}, '
                                 f'형식 오류 {hints["invalid"]}')
                    for hint in item['source_hint_examples']:
                        status = {'match': '입력 URL과 일치', 'mismatch': '⚠ 입력 URL과 다름',
                                  'invalid': '⚠ 형식 오류'}[hint['status']]
                        lines.append(f'    ↳ {hint["kind"]}: {status} · '
                                     f'{hint["claimed_url"] or hint["raw_value"]}')
                    if item['source_hint_count'] > len(item['source_hint_examples']):
                        lines.append('    ↳ 추가 HTML 출처 표기는 생략됨 (개수에는 포함)')
                if item['navigation_directive_count']:
                    counts = item['navigation_directive_status_counts']
                    lines.append(f'  ⚠ HTML 이동 지시 {item["navigation_directive_count"]}건: '
                                 f'동일 출처 {counts["same_origin"]}, '
                                 f'다른 출처 {counts["other_origin"]}, '
                                 f'형식 오류 {counts["invalid"]}')
                    for directive in item['navigation_directive_examples']:
                        label = {'same_origin': '같은 출처', 'other_origin': '다른 출처',
                                 'invalid': '유효하지 않은 URL'}[directive['status']]
                        lines.append(f'    ↳ {directive["kind"]}: {label} · '
                                     f'{directive["target_url"] or directive["raw_value"]}')
                    if item['navigation_directive_count'] > len(item['navigation_directive_examples']):
                        lines.append('    ↳ 다른 이동 지시 예시는 생략됨 (개수에는 포함)')
                if item['active_target_count']:
                    counts = item['active_target_status_counts']
                    lines.append(f'  ⚠ HTML 폼/삽입/스크립트 대상 {item["active_target_count"]}건: '
                                 f'동일 출처 {counts["same_origin"]}, '
                                 f'다른 출처 {counts["other_origin"]}, '
                                 f'형식 오류 {counts["invalid"]}')
                    for target in item['active_target_examples']:
                        label = {'same_origin': '동일 출처 후보', 'other_origin': '⚠ 다른 출처',
                                 'invalid': '⚠ 잘못된 URL'}[target['status']]
                        kind = ('form ' + (target['method'] or '?') if target['kind'] == 'form'
                                else target['kind'])
                        lines.append(f'    ↳ {kind}: {label} · '
                                     f'{target["target_url"] or target["raw_value"]}')
                    if item['active_target_count'] > len(item['active_target_examples']):
                        lines.append('    ↳ 추가 폼/삽입/스크립트 대상 예시는 생략됨')
                if item['form_control_count']:
                    counts = item['form_control_kind_counts']
                    lines.append(f'  ⚠ HTML 폼 입력 유형 {item["form_control_count"]}건: '
                                 f'암호 {counts["password"]}, 파일 {counts["file"]}, '
                                 f'숨김 {counts["hidden"]} (입력값 읽지 않음)')
                    for control in item['form_control_examples']:
                        label = {'password': '암호 입력', 'file': '파일 선택',
                                 'hidden': '숨김 입력'}[control['kind']]
                        extra = ' ⚠ GET 방식 암호 입력' if control['password_in_get'] else ''
                        lines.append(f'    ↳ 폼 {control["form_ordinal"]}: {label} '
                                     f'(방식 {control["method"]}){extra}')
                    if item['form_control_count'] > len(item['form_control_examples']):
                        lines.append('    ↳ 추가 입력 유형 예시는 생략됨')
                if item['passive_resource_count']:
                    counts = item['passive_resource_status_counts']
                    lines.append(f'  ⚠ 이미지/스타일/미디어 참조 {item["passive_resource_count"]}건: '
                                 f'동일 출처 {counts["same_origin"]}, '
                                 f'다른 출처 {counts["other_origin"]}, '
                                 f'형식 오류 {counts["invalid"]}')
                    for ref in item['passive_resource_examples']:
                        label = {'same_origin': '동일 출처', 'other_origin': '⚠ 다른 출처',
                                 'invalid': '⚠ 형식 오류'}[ref['status']]
                        lines.append(f'    ↳ {ref["kind"]}: {label} · '
                                     f'호스트 {ref["target_host"] or "표시 불가"} '
                                     '(URL 경로·쿼리는 표시하지 않음)')
                    if item['passive_resource_count'] > len(item['passive_resource_examples']):
                        lines.append('    ↳ 추가 리소스 예시는 생략됨')
                if item['responsive_image_count']:
                    counts = item['responsive_image_status_counts']
                    lines.append(f'  ⚠ 반응형 이미지 srcset {item["responsive_image_count"]}건: '
                                 f'동일 출처 {counts["same_origin"]}, '
                                 f'다른 출처 {counts["other_origin"]}, '
                                 f'형식 오류 {counts["invalid"]}')
                    for candidate in item['responsive_image_examples']:
                        label = {'same_origin': '동일 출처', 'other_origin': '⚠ 다른 출처',
                                 'invalid': '⚠ 형식 오류'}[candidate['status']]
                        lines.append(f'    ↳ {candidate["element"]} srcset: {label} · '
                                     f'호스트 {candidate["target_host"] or "표시 불가"} '
                                     '(URL 경로·쿼리 표시 안 함)')
                    if item['responsive_image_count'] > len(item['responsive_image_examples']):
                        lines.append('    ↳ 추가 srcset 후보는 생략됨')
                if item['css_reference_count']:
                    counts = item['css_reference_status_counts']
                    lines.append(f'  ⚠ HTML 내부 CSS 참조 {item["css_reference_count"]}건: '
                                 f'다른 출처 {counts["other_origin"]}, 형식 오류 {counts["invalid"]}')
                    for cue in item['css_reference_examples']:
                        label = {'same_origin':'동일 출처', 'other_origin':'⚠ 다른 출처',
                                 'invalid':'⚠ 형식 오류'}[cue['status']]
                        lines.append(f'    ↳ CSS {cue["kind"]}: {label} · '
                                     f'호스트 {cue["target_host"] or "표시 불가"} '
                                     '(URL 경로·쿼리 표시 안 함)')
                    if item['css_reference_count'] > len(item['css_reference_examples']):
                        lines.append('    ↳ 추가 CSS 후보는 생략됨')
                if item['usage_hint_count']:
                    lines.append(f'  ⚠ HTML 이용/색인 자기 표기 {item["usage_hint_count"]}건 '
                                 '(법적 사용 허가 또는 실제 색인 정책 인증 아님)')
                    for hint in item['usage_hint_examples']:
                        if hint['kind'] == 'robots':
                            labels = ', '.join(hint['flags']) if hint['flags'] else '인식한 제한 없음'
                            lines.append(f'    ↳ robots meta: {labels} (HTML 자체 표기)')
                        else:
                            labels = {'same_origin': '동일 출처', 'other_origin': '다른 출처',
                                      'invalid': 'URL 형식 오류'}
                            lines.append(f'    ↳ rel=license: {labels[hint["status"]]} · '
                                         f'호스트 {hint["target_host"] or "표시 불가"} '
                                         '(경로·쿼리 표시 안 함)')
                    if item['usage_hint_count'] > len(item['usage_hint_examples']):
                        lines.append('    ↳ 나머지 이용/색인 표기는 생략됨')
                if item['html_link_count']:
                    counts = item['html_link_status_counts']
                    lines.append(f'  HTML 참조 {item["html_link_count"]}건: 묶음 내 {counts["in_bundle"]}, '
                                 f'기존 활성 {counts["registered_active"]}, '
                                 f'보관 {counts["registered_archived"]}, 미등록 {counts["unregistered"]}')
                    status_labels = {'in_bundle': '묶음 내 등록 후보', 'registered_active': '로컬 활성 자료',
                                     'registered_archived': '로컬 보관 자료', 'unregistered': '로컬 미등록'}
                    for reference in item['html_link_examples']:
                        lines.append(f'    ↳ {status_labels[reference["status"]]}: '
                                     f'{reference["linked_url"]} '
                                     f'(후보 ID/묶음 순번: {reference["candidate_ids_or_ordinals"]})')
                    if item['html_link_count'] > len(item['html_link_examples']):
                        lines.append('    ↳ 나머지 링크 예시는 생략됨 (개수에는 포함)')
            lines.extend(['URL은 사용자가 입력한 미검증 주장입니다. 외부 사이트를 조회하지 않습니다.',
                          'URL 경고가 없어도 해당 호스트의 실제 IP나 안전성은 검증되지 않습니다.',
                          '확인 뒤 파일·목록 또는 관련 SQLite 조사 자료가 바뀌면 등록이 거부됩니다.'])
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', '\n'.join(lines))
            self.research_detail.configure(state='disabled')
            if not preview['importable']:
                self.research_feedback.set(f'가져오기 차단: {preview["duplicate_count"]}건 이미 등록 또는 묶음 내 중복')
                return
            warning_notice = (
                f'\n주의: {preview["warning_item_count"]}개 항목에서 URL/본문 중복 또는 '
                '버전 차이 후보가 발견됐습니다. 위 상세 내용을 확인해 주세요.\n'
                if preview['warning_item_count'] else '')
            if preview['url_warning_item_count']:
                warning_notice += (
                    f'\nURL 위험 신호: {preview["url_warning_item_count"]}개 항목. '
                    'URL 문자열에 사설 IP·로컬 호스트명·자격증명 등의 경고가 있습니다. '
                    '상세 내용을 확인해 주세요. DNS 조회나 실제 안전성 검증은 수행하지 않았습니다.\n')
            differing = (preview['source_hint_status_counts']['mismatch'] +
                         preview['source_hint_status_counts']['invalid'])
            if differing:
                warning_notice += (f'\nHTML 내부 출처 자체 표기 {differing}건이 입력 URL과 다르거나 '
                                   '형식 오류입니다. 상세 내용을 확인해 주세요. '
                                   'HTML 메타데이터의 진위도 검증하지 않았습니다.\n')
            if preview['navigation_directive_count']:
                warning_notice += (
                    f'\nHTML 내 base/자동 이동 지시 {preview["navigation_directive_count"]}건이 '
                    '발견됐습니다. 로컬 파일을 브라우저로 열면 이동 동작에 영향을 줄 수 있습니다. '
                    '검토기에서는 지시를 실행하지 않았습니다.\n')
            if preview['active_target_count']:
                warning_notice += (
                    f'\nHTML 폼·iframe·외부 script 대상 {preview["active_target_count"]}건이 '
                    '표시됐습니다. 실제 브라우저에서 제출·로딩할 수 있는 문자열입니다. '
                    '검토기에서는 어떤 요청도 실행하지 않았습니다. 상세 내용을 확인해 주세요.\n')
            if preview['form_control_count']:
                warning_notice += (
                    f'\nHTML 폼의 암호/파일/숨김 입력 유형 {preview["form_control_count"]}건이 '
                    f'발견됐습니다 (GET 암호 입력 {preview["form_password_get_count"]}건). '
                    '입력값은 수집하지 않았고 폼을 제출하지 않았습니다. 상세 내용을 확인해 주세요.\n')
            if preview['passive_resource_count']:
                warning_notice += (
                    f'\nHTML 이미지/스타일/미디어 참조 {preview["passive_resource_count"]}건 '
                    f'(다른 출처 {preview["passive_resource_status_counts"]["other_origin"]}건)이 '
                    '발견됐습니다. 로컬 검토기는 파일을 열거나 네트워크 요청을 하지 않습니다. '
                    '상세 화면에 URL의 호스트만 표시했습니다.\n')
            if preview['responsive_image_count']:
                warning_notice += (
                    f'\nHTML 반응형 이미지 srcset {preview["responsive_image_count"]}건 '
                    f'(다른 출처 {preview["responsive_image_status_counts"]["other_origin"]}건)이 '
                    '발견됐습니다. 이미지를 열거나 요청하지 않았으며 후보 URL 전체는 표시하지 않습니다.\n')
            if preview['css_reference_count']:
                warning_notice += (
                    f'\nHTML 내부 CSS 참조 {preview["css_reference_count"]}건이 발견됐습니다. '
                    'CSS/이미지를 실행하거나 다운로드하지 않았으며 호스트만 표시합니다. '
                    '지원하지 않는 CSS 구문은 누락될 수 있습니다.\n')
            if preview['usage_hint_count']:
                warning_notice += (
                    f'\nHTML 이용·색인 자기 표기 {preview["usage_hint_count"]}건을 확인했습니다. '
                    'robots meta 및 라이선스 링크는 자체 표기이며 허가·정책의 사실 여부를 증명하지 않습니다.\n')
            if preview['html_link_status_counts']['unregistered']:
                warning_notice += (
                    f'\nHTML 참조 링크 {preview["html_link_status_counts"]["unregistered"]}건에 '
                    '대응하는 로컬 등록 자료가 없습니다. 외부 웹 조회는 수행하지 않았습니다.\n')
            if not messagebox.askyesno('로컬 자료 묶음 등록 승인',
                                        f'{preview["item_count"]}개 파일의 로컬 텍스트를 '
                                        'SQLite에 등록하시겠습니까?\n' + warning_notice +
                                        '외부 출처 진위는 확인되지 않았습니다.'):
                self.research_feedback.set('자료 묶음 사전 검토 완료 · 등록 취소 (DB 변경 없음)')
                return
            imported = self.store.import_offline_research_bundle(
                path, expected_preview_token=preview['preview_token'])
            self._refresh_offline_research()
            self.research_feedback.set(
                f'로컬 묶음 #{imported["batch_id"]}: {len(imported["capture_ids"])}건 등록 · 출처 미검증')
        except (ValueError, PermissionError, OSError) as exc:
            self.research_feedback.set(str(exc))

    def _verify_offline_research_bundle_files(self) -> None:
        """Explicit manifest path only; no external URL request or SQLite write."""
        path=filedialog.askopenfilename(
            title='등록된 로컬 자료 묶음 JSON 목록 선택',
            filetypes=[('JSON 목록','*.json')])
        if not path:
            return
        try:
            result=self.store.verify_imported_offline_research_bundle(path)
            statuses={'match': '원본 바이트 일치', 'changed': '파일 변경됨',
                      'unavailable': '파일 누락/읽기 불가',
                      'record_mismatch': '등록 이력 불일치'}
            lines=[f'[로컬 등록 묶음 원본 파일 일괄 재검사 — 읽기 전용]',
                   f'등록 묶음 #{result["batch_id"]}: {result["item_count"]}개 파일',
                   f'등록 이력 일치: {result["records_consistent"]}',
                   f'원본 바이트 일치 {result["counts"]["match"]} · '
                   f'변경 {result["counts"]["changed"]} · '
                   f'누락/불가 {result["counts"]["unavailable"]} · '
                   f'기록 불일치 {result["counts"]["record_mismatch"]}']
            for row in result['items']:
                lines.append(f'{row["ordinal"]}. {row["filename"]} · 자료 #{row["capture_id"]} · '
                             f'{statuses[row["status"]]}')
                if row['status'] != 'match':
                    lines.append('  ' + row['details'])
            lines.append('입력 URL·선택 폴더의 실제 원산지/웹 출처 진위는 검증되지 않습니다.')
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0','end')
            self.research_detail.insert('1.0','\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('묶음 파일 일괄 검사 통과' if result['passed']
                else '주의: 묶음 파일 변경/누락/기록 불일치 발견')
        except (ValueError, PermissionError, OSError) as exc:
            self.research_feedback.set(str(exc))

    def _audit_offline_research(self) -> None:
        try:
            result=self.store.audit_offline_research()
            lines=[f'로컬 기록 검사: 자료 {result["checked_captures"]}건, 묶음 {result["checked_batches"]}개',
                   f'내부 기록 불일치: {len(result["issues"])}건',
                   '주의: 출처 웹사이트 진위 및 원본 파일 바이트는 검증하지 않았습니다.']
            lines.extend(f'• {issue["issue"]} (자료 ID: {issue["capture_id"]})'
                         for issue in result['issues'][:30])
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0','end')
            self.research_detail.insert('1.0','\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('로컬 무결성 검사 완료' if result['passed']
                else f'주의: 불일치 {len(result["issues"])}건 발견')
        except (ValueError,PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _compare_offline_research(self) -> None:
        if self.research_selected_id is None:
            self.research_feedback.set('먼저 목록에서 첫 번째 자료를 선택해 주세요.')
            return
        try:
            other=int(self.research_compare_id.get())
            result=self.store.compare_offline_research(self.research_selected_id,other)
            lines=[f'로컬 자료 비교: #{result["first_id"]} / #{result["second_id"]}',
                   f'{result["first_title"]} / {result["second_title"]}',
                   f'본문 일치: {"예" if result["same_body"] else "아니오"}',
                   f'기재된 출처 URL 일치: {"예" if result["same_claimed_source"] else "아니오"}',
                   f'로컬 원본 파일 해시 일치: {"예" if result["same_local_raw_file"] else "아니오/확인 불가"}',
                   f'첫 번째 본문 SHA-256: {result["first_sha256"]}',
                   f'두 번째 본문 SHA-256: {result["second_sha256"]}',
                   '서로 같은 내용이어도 사실이거나 해당 웹사이트가 제공했다는 증거는 아닙니다.']
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0','end')
            self.research_detail.insert('1.0','\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('로컬 자료 내용 비교 완료 · 온라인 출처 미검증')
        except (ValueError,PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _show_offline_research_links(self) -> None:
        if self.research_selected_id is None:
            self.research_feedback.set('먼저 HTML 자료를 선택해 주세요.')
            return
        try:
            links=self.store.list_offline_research_links(self.research_selected_id)
            lines=['[저장 당시 HTML에 있던 링크 — 실제 웹 요청 없음 / 출처 미검증]',
                   '로컬 사본 있음은 URL 문자열과 일치하는 등록 자료가 있다는 뜻만 가집니다.']
            if not links:
                lines.append('추출된 링크가 없습니다 (이전 버전 HTML 자료는 소급 추출하지 않음).')
            for item in links:
                present='로컬 사본 있음 (진위 미검증)' if item['has_local_copy'] else '로컬 사본 없음'
                lines.append(f"{item['position']}. {item['linked_url']} — {present}")
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0','end')
            self.research_detail.insert('1.0','\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set(f'선택 자료의 HTML 링크 {len(links)}건 표시 · 인터넷 접속 없음')
        except (ValueError,PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _trace_offline_research_references(self) -> None:
        if self.research_selected_id is None:
            self.research_feedback.set('먼저 목록에서 출발 자료를 선택해 주세요.')
            return
        try:
            result=self.store.trace_offline_research_references(self.research_selected_id)
            node_index={item['id']:item for item in result['nodes']}
            lines=['[로컬 참조 연결 — 출처·링크 진위 미검증, 인터넷 접속 없음]',
                   f'출발 #{result["start_id"]} · 깊이 {result["max_depth"]}단계',
                   f'로컬 자료 {len(result["nodes"])}개 · 링크 {len(result["links"])}개',
                   '같은 URL을 가진 자료는 모두 후보이며, 진위나 동일 사이트 소유를 증명하지 않습니다.']
            for edge in result['links']:
                ids=edge['candidate_ids']
                if not ids:
                    info='로컬 사본 없음'
                else:
                    parts=[]
                    for ident in ids:
                        node=node_index.get(ident)
                        label=' (보관)' if node and node['archived'] else ''
                        parts.append(f'#{ident}{label}')
                    info='로컬 후보 '+', '.join(parts)
                    if edge['status']=='multiple':
                        info += ' (다중 후보: 미검증)'
                lines.append(f'#{edge["from_id"]} → {edge["linked_url"]} — {info}')
            if result['truncated']:
                lines.append('주의: 조회 상한에 도달해 일부 연결은 표시되지 않았습니다.')
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0','end')
            self.research_detail.insert('1.0','\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set(f'로컬 참조 연결 {len(result["links"])}개 확인 · 출처 미검증')
        except (ValueError,PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _export_offline_research_followups(self) -> None:
        """Export all filtered pages, never just the visible 40 URL strings."""
        try:
            self.store.require_permission('company:manage')
            path = filedialog.asksaveasfilename(
                parent=self.root, title='오프라인 후속 조사 전체 JSON 저장 (덮어쓰기 금지)',
                defaultextension='.json', filetypes=[('JSON 파일', '*.json')])
            if not path:
                self.research_feedback.set('후속 조사 JSON 저장 취소 · 변경 없음')
                return
            saved = self.store.export_offline_research_followups(
                path, include_archived=self.research_include_archived.get(),
                review_filter=self.research_review_filter.get())
            self.research_feedback.set(
                f'후속 조사 JSON 저장: {saved.name} · 모든 필터 결과 포함 / 출처 진위 미검증')
        except (ValueError, PermissionError, OSError, UnicodeError) as exc:
            self.research_feedback.set(f'후속 조사 JSON 저장 실패: {exc}')

    def _verify_offline_research_followup_export(self) -> None:
        """Read-only comparison against current local follow-up state."""
        try:
            self.store.require_permission('company:manage')
            path = filedialog.askopenfilename(
                parent=self.root, title='오프라인 후속 조사 JSON 재검사',
                filetypes=[('JSON 파일', '*.json')])
            if not path:
                self.research_feedback.set('후속 조사 JSON 재검사 취소 · 변경 없음')
                return
            result = self.store.inspect_offline_research_followup_export(path)
            lines = [
                '[오프라인 후속 조사 JSON 재검사 — 읽기 전용]',
                '자체 체크섬 일치 (전자서명·웹 출처 진위 인증 아님)',
                f'내보낸 URL {result["exported_url_count"]}개 / 현재 {result["current_url_count"]}개',
                '동일 범위의 현재 로컬 DB 목록 일치: ' +
                ('예' if result['local_report_matches'] else '아니오'),
                f'현재 DB에만 있는 URL ({result["added_url_count"]}): {result["added_urls_preview"]}',
                f'내보낸 JSON에만 있는 URL ({result["missing_url_count"]}): {result["missing_urls_preview"]}',
                f'동일 URL의 기록·상태 변경 ({result["changed_url_count"]}): '
                f'{result["changed_urls_preview"]}',
                f'동일 URL 항목 {result["unchanged_url_count"]}개',
                'URL 미리보기는 각 종류별 최대 20개입니다.',
                '기타 집계·순서 차이: ' +
                ('있음' if result['metadata_or_order_differs'] else '없음'),
                'DB 변경·보관·수동 검토 변경·다른 DB 등 원인은 확정할 수 없습니다.',
                '웹 접속 없음 / 실제 웹 출처·내용 진위 미검증 / 가져오기 없음',
            ]
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', '\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('후속 조사 JSON 자체 무결성 확인 · ' +
                ('로컬 DB 일치' if result['local_report_matches'] else '로컬 DB 불일치'))
        except (ValueError, PermissionError, OSError, UnicodeError) as exc:
            self.research_feedback.set(f'후속 조사 JSON 재검사 실패: {exc}')

    def _reset_offline_research_followup_page(self, event=None) -> None:
        self.research_followup_page = 1
        self._show_offline_research_followups()

    def _previous_offline_research_followups(self) -> None:
        self.research_followup_page = max(1, self.research_followup_page - 1)
        self._show_offline_research_followups()

    def _next_offline_research_followups(self) -> None:
        # Read the current bounded result first; never blindly increment past the end.
        try:
            current = self.store.offline_research_followup_queue(
                include_archived=self.research_include_archived.get(),
                review_filter=self.research_review_filter.get(),
                page=self.research_followup_page)
            if current['has_next_page']:
                self.research_followup_page += 1
            self._show_offline_research_followups()
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _show_offline_research_followups(self) -> None:
        """Display one page of local URL candidates; never request URLs."""
        try:
            result = self.store.offline_research_followup_queue(
                include_archived=self.research_include_archived.get(),
                review_filter=self.research_review_filter.get(),
                page=self.research_followup_page)
            # Manual actions may shrink the filtered list. Rewind to its last
            # available page rather than showing an unexplained empty screen.
            if result['page_out_of_range']:
                self.research_followup_page = result['page_count']
                result = self.store.offline_research_followup_queue(
                    include_archived=self.research_include_archived.get(),
                    review_filter=self.research_review_filter.get(),
                    page=self.research_followup_page)
            counts = result['status_counts']
            lines = [
                '[저장된 HTML 링크의 수동 후속 조사 목록 — 웹 접속 없음]',
                'URL 문자열과 로컬 사본의 일치 후보만 표시합니다. 출처 진위 미검증.',
                f'스캔 링크: {result["scanned_link_count"]}개 / 서로 다른 URL: {result["unique_url_count"]}개',
                f'미등록 {counts["unregistered"]} · 보관본만 {counts["archived_only"]} · '
                f'활성 후보 여러 개 {counts["multiple_active"]} · 활성 후보 1개 {counts["one_active"]}',
                '표시 순서: 미등록 → 보관본만 → 활성 후보 여러 개 → 활성 후보 1개',
                f'페이지 {result["page"]}/{result["page_count"]} · 필터 결과 {result["filtered_url_count"]}개',
                f'수동 상태 필터: {result["review_filter"]} · 보류 {result["review_counts"]["deferred"]}건'
                f' / 보류 아님 {result["review_counts"]["pending"]}건 (웹 검증 아님)',
            ]
            if result['scan_truncated']:
                lines.append('주의: 최신 링크 2,000개까지만 스캔했습니다. 더 오래된 링크는 포함되지 않습니다.')
            if result['has_next_page']:
                lines.append('다음 페이지에 추가 URL이 있습니다 (다음 40개 버튼).')
            if not result['items']:
                lines.append('선택한 조건에 해당하는 로컬 링크 없음. 실제 웹 상태는 알 수 없습니다.')
            labels = {'unregistered': '로컬 미등록', 'archived_only': '보관본만 있음',
                      'multiple_active': '활성 후보 여러 개', 'one_active': '활성 후보 1개'}
            for item in result['items']:
                lines.append(f'[{labels[item["status"]]}] {item["linked_url"]}')
                lines.append(f'  참조 자료 {item["referrer_count"]}건 (ID 일부: '
                             f'{item["referrer_ids"]}) / 활성 후보 {item["active_candidate_count"]}건 '
                             f'/ 보관 후보 {item["archived_candidate_count"]}건')
                if item['manual_review']:
                    review = item['manual_review']
                    lines.append(f'  수동 기록: {review["action"]} · {review["recorded_at"]} '
                                 '(출처 검증 아님)')
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', '\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set(
                f'로컬 후속 조사 {result["page"]}/{result["page_count"]}페이지 표시 · 실제 인터넷 접속 없음')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _show_offline_research_source_overlap(self) -> None:
        """Show local hash/source overlaps, without claiming independent evidence."""
        try:
            report = self.store.offline_research_source_overlap(
                include_archived=self.research_include_archived.get())
            counts = report['category_counts']
            labels = {
                'same_body_different_claimed_urls': '동일 본문·서로 다른 주장 URL',
                'different_bodies_same_claimed_url': '동일 주장 URL·서로 다른 본문',
                'same_imported_bytes_different_claimed_urls': '동일 가져온 파일 바이트·서로 다른 주장 URL',
            }
            lines = [
                '[저장된 오프라인 조사 자료 중복·버전 차이 점검 — 읽기 전용]',
                '저장된 본문/가져오기 당시의 SHA-256과 주장 URL 문자열만 비교합니다.',
                '동일 해시는 독립 출처·원본 파일 보존·웹 출처 진위의 증거가 아닙니다.',
                f'최신 자료 {report["scanned_capture_count"]}개 분석 · '
                f'보관 포함 {report["include_archived"]}',
                f'동일 본문·서로 다른 URL {counts["same_body_different_claimed_urls"]}그룹 · '
                f'동일 URL·본문 차이 {counts["different_bodies_same_claimed_url"]}그룹 · '
                f'동일 원본 바이트 해시·서로 다른 URL '
                f'{counts["same_imported_bytes_different_claimed_urls"]}그룹',
                f'전체 {report["group_count"]}그룹 중 '
                f'{report["displayed_group_count"]}그룹 표시',
            ]
            if report['scan_truncated']:
                lines.append('주의: 최신 2,000개 자료만 분석했습니다. 전체 DB 검사 아님.')
            if report['groups_truncated']:
                lines.append('주의: 상위 25개 그룹만 표시했습니다.')
            if not report['items']:
                lines.append('선택 범위에서 일치/차이 후보 없음 (실제 출처 신뢰성 미검증).')
            for item in report['items']:
                lines.append(f'[{labels[item["category"]]}] {item["capture_count"]}건 · '
                             f'서로 다른 값 {item["distinct_value_count"]}개')
                lines.append(f'  비교 키: {item["key"]} / 자료 ID 일부: {item["capture_ids"]}')
                for url in item['claimed_urls']:
                    lines.append(f'  주장 URL 예시: {url}')
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', '\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('로컬 자료 중복·버전 차이 표시 · 외부 접속/진위 검증 없음')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(f'자료 중복 점검 실패: {exc}')

    def _show_offline_research_followup_domains(self) -> None:
        """Summarize claimed URL hostnames without DNS or website access."""
        try:
            report = self.store.offline_research_followup_domains(
                include_archived=self.research_include_archived.get(),
                review_filter=self.research_review_filter.get())
            lines = [
                '[로컬 HTML 링크의 호스트별 수동 조사 현황 — 웹 접속 없음]',
                '호스트는 저장된 URL 문자열에서만 추출합니다. 도메인 소유·출처 진위 미검증.',
                f'링크 스캔 {report["scanned_link_count"]}개 중 필터 결과 '
                f'{report["filtered_url_count"]}개 · 호스트 {report["domain_count"]}개',
                f'필터 {report["review_filter"]} · 보관 자료 포함 '
                f'{report["include_archived_referrers"]}',
                '우선순위: 로컬 미등록/보관본만 있는 URL 수가 많은 호스트부터',
            ]
            if report['scan_truncated']:
                lines.append('주의: 최신 2,000개 링크만 분석했습니다 (전체 DB 아님).')
            if report['domains_truncated']:
                lines.append('상위 25개 호스트만 표시합니다 (전체 집계 수는 유지).')
            if not report['items']:
                lines.append('선택한 필터에 해당하는 저장된 URL이 없습니다.')
            for row in report['items']:
                counts = row['status_counts']
                lines.append(
                    f'[{row["hostname"]}] URL {row["url_count"]} · 참조 {row["referrer_count_total"]}건 '
                    f'· 미등록 {counts["unregistered"]} · 보관본만 {counts["archived_only"]} '
                    f'· 활성 복수 {counts["multiple_active"]} · 활성 1개 {counts["one_active"]} '
                    f'· 수동 보류 {row["deferred_url_count"]}')
                for url in row['sample_urls']:
                    lines.append(f'  예시: {url}')
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', '\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('호스트별 로컬 조사 현황 표시 · 웹 접속/출처 검증 없음')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(f'호스트별 조사 현황 조회 실패: {exc}')

    def _export_offline_research_url_preflight(self) -> None:
        """Owner-selected JSON of ALL sampled warnings, not just visible 40."""
        try:
            self.store.require_permission('company:manage')
            path = filedialog.asksaveasfilename(
                parent=self.root, title='저장 URL 경고 전체 JSON 저장 (덮어쓰기 금지)',
                defaultextension='.json', filetypes=[('JSON 파일', '*.json')])
            if not path:
                self.research_feedback.set('URL 경고 JSON 저장 취소 · 변경 없음')
                return
            saved = self.store.export_offline_research_url_preflight(
                path, include_archived=self.research_include_archived.get(),
                review_filter=self.research_review_filter.get())
            self.research_feedback.set(
                f'URL 경고 JSON 저장: {saved.name} · 전체 경고 포함 / 접속 안전·출처 진위 미검증')
        except (ValueError, PermissionError, OSError, UnicodeError) as exc:
            self.research_feedback.set(f'URL 경고 JSON 저장 실패: {exc}')

    def _verify_offline_research_url_preflight_export(self) -> None:
        """Read-only self-checksum and current local warning comparison."""
        try:
            self.store.require_permission('company:manage')
            path = filedialog.askopenfilename(
                parent=self.root, title='저장 URL 경고 JSON 재검사',
                filetypes=[('JSON 파일', '*.json')])
            if not path:
                self.research_feedback.set('URL 경고 JSON 재검사 취소 · 변경 없음')
                return
            result = self.store.inspect_offline_research_url_preflight_export(path)
            lines = [
                '[저장 URL 경고 JSON 재검사 — 오프라인/읽기 전용]',
                'SHA-256 자체 체크섬 일치 (전자서명·출처 진위 인증 아님)',
                f'저장 당시 경고 URL {result["exported_warning_url_count"]}개 / '
                f'현재 경고 URL {result["current_warning_url_count"]}개',
                '현재 로컬 DB 경고 목록 일치: ' +
                ('예' if result['local_report_matches'] else '아니오'),
                f'현재 DB에만 있는 경고 URL ({result["added_warning_url_count"]}): '
                f'{result["added_urls_preview"]}',
                f'내보낸 JSON에만 있는 경고 URL ({result["missing_warning_url_count"]}): '
                f'{result["missing_urls_preview"]}',
                f'동일 URL의 경고·로컬 상태 차이 ({result["changed_warning_url_count"]}): '
                f'{result["changed_urls_preview"]}',
                '기타 집계·순서 차이: ' +
                ('있음' if result['metadata_or_order_differs'] else '없음'),
                'URL 예시는 종류별 최대 20개입니다. 변화 원인은 확정할 수 없습니다.',
                '웹 접속·DNS 조회 없음 / 접속 안전·출처 진위 미검증 / DB 변경 없음',
            ]
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', '\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('URL 경고 JSON 자체 무결성 확인 · ' +
                ('로컬 DB 일치' if result['local_report_matches'] else '로컬 DB 불일치'))
        except (ValueError, PermissionError, OSError, UnicodeError) as exc:
            self.research_feedback.set(f'URL 경고 JSON 재검사 실패: {exc}')

    def _show_offline_research_url_preflight(self) -> None:
        """Display passive URL string warnings; never permit remote access."""
        try:
            report = self.store.offline_research_url_preflight(
                include_archived=self.research_include_archived.get(),
                review_filter=self.research_review_filter.get())
            lines = [
                '[저장 URL 위험 신호 — 오프라인 문자열 검사만 수행]',
                '주의: 경고가 없어도 안전한 웹 주소라는 뜻이 아닙니다.',
                'DNS/접속/출처 검증/접속 허가를 수행하지 않습니다.',
                f'최신 링크 {report["scanned_link_count"]}개 스캔 · 필터 결과 '
                f'{report["filtered_url_count"]}개 · 경고 URL {report["warning_url_count"]}개',
                f'필터 {report["review_filter"]} · 보관 자료 포함 '
                f'{report["include_archived_referrers"]}',
            ]
            if report['scan_truncated']:
                lines.append('주의: 최신 2,000개 링크만 검사했습니다 (전체 DB 아님).')
            if report['warnings_truncated']:
                lines.append('경고 URL 중 상위 40개만 표시합니다 (집계는 전체 필터 결과).')
            for code, count in report['warning_counts'].items():
                lines.append(f'경고 유형 {code}: {count}건')
            if not report['items']:
                lines.append('문자열 규칙에 걸린 URL 없음 — 접속 안전성은 여전히 미검증.')
            for item in report['items']:
                lines.append(f'[{", ".join(item["warning_codes"])}] '
                             f'{item["linked_url"]} · {item["status"]}')
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', '\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('저장 URL 위험 신호 표시 · DNS/웹 접속 없음')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(f'저장 URL 검사 실패: {exc}')

    def _record_offline_research_followup_note(self) -> None:
        try:
            ident = self.store.record_offline_research_followup_note(
                self.research_followup_url.get(), self.research_followup_action.get(),
                self.research_followup_note.get())
            self.research_feedback.set(f'수동 검토 메모 #{ident} 저장 · 웹 접속/출처 검증 없음')
            self._show_offline_research_followups()
            self.research_feedback.set(f'수동 검토 메모 #{ident} 저장 · 웹 접속/출처 검증 없음')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _show_offline_research_followup_history(self) -> None:
        try:
            report = self.store.offline_research_followup_history(
                self.research_followup_url.get())
            lines = ['[수동 링크 검토 이력 — 온라인 출처 미검증]', report['linked_url']]
            if not report['items']:
                lines.append('저장된 검토 메모 없음')
            for item in report['items']:
                lines.append(f'#{item["id"]} · {item["recorded_at"]} · {item["action"]}')
                lines.append(item['note'])
            if report['truncated']:
                lines.append('이전 이력 일부 생략 (최근 20건 표시)')
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', '\n'.join(lines))
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('로컬 수동 검토 이력 표시 · 실제 웹 접속 없음')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _show_local_evidence_report(self) -> None:
        try:
            report = self.store.local_research_evidence_report(
                self.research_query.get(),
                include_archived=self.research_include_archived.get())
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', report['report_text'])
            self.research_detail.configure(state='disabled')
            self.research_feedback.set(
                f'로컬 본문 근거 {len(report["hits"])}건 표시 · 온라인 출처 미검증 · 외부 접속 없음')
        except (ValueError, PermissionError) as exc:
            self.research_feedback.set(str(exc))

    def _export_local_evidence_report(self) -> None:
        """Only save after the owner explicitly chooses a local destination."""
        try:
            # Validate the search before showing a save dialog.
            self.store.local_research_evidence_report(
                self.research_query.get(),
                include_archived=self.research_include_archived.get())
            path = filedialog.asksaveasfilename(
                parent=self.root, title='오프라인 근거 보고서 저장 (기존 파일 덮어쓰기 금지)',
                defaultextension='.json', filetypes=[('JSON 파일', '*.json')])
            if not path:
                self.research_feedback.set('근거 보고서 저장 취소 · 파일 변경 없음')
                return
            saved = self.store.export_local_research_evidence(
                self.research_query.get(), path,
                include_archived=self.research_include_archived.get())
            self.research_feedback.set(
                f'오프라인 근거 JSON 저장: {saved.name} · 체크섬은 출처 진위 인증이 아님')
        except (ValueError, PermissionError, OSError, UnicodeError) as exc:
            self.research_feedback.set(f'근거 보고서 저장 실패: {exc}')

    def _verify_local_evidence_export(self) -> None:
        """Check a selected JSON without importing or modifying any evidence."""
        try:
            self.store.require_permission('company:manage')
            path = filedialog.askopenfilename(
                parent=self.root, title='오프라인 근거 JSON 재검사',
                filetypes=[('JSON 파일', '*.json')])
            if not path:
                self.research_feedback.set('근거 JSON 재검사 취소 · 변경 없음')
                return
            result = self.store.inspect_local_research_evidence_export(path)
            summary = (
                '오프라인 근거 JSON 검사 (읽기 전용)\n'
                'JSON 자체 체크섬: 일치 (전자서명/출처 인증 아님)\n'
                f'내보낸 근거 수: {result["exported_hit_count"]}건\n'
                '현재 로컬 DB 보고서와 정확히 일치: ' +
                ('예' if result['local_report_matches'] else '아니오') + '\n'
                '불일치 시 DB 변경·자료 추가·보관·다른 DB 가능성 있음.\n'
                '웹 출처·내용 진위 미검증 / 외부 접속 없음 / 자료 가져오기 없음'
            )
            difference = result.get('candidate_difference')
            if difference is not None:
                summary += ('\n로컬 DB 비교 후보 범위: ' +
                            ('보관 자료 포함' if difference['compared_scope'] == 'including_archived'
                             else '활성 자료만') +
                            ' (원래 내보내기 범위로 확정되지 않음)\n'
                            f'현재 DB에만 보이는 자료 ID: {difference["added_capture_ids"]}\n'
                            f'내보낸 JSON에만 보이는 자료 ID: {difference["missing_capture_ids"]}\n'
                            f'동일 ID이지만 내용이 다른 항목: {difference["changed_capture_ids"]}\n'
                            f'동일 항목 수: {difference["unchanged_hit_count"]}\n'
                            '위 차이는 원인 진단이나 웹 출처 검증이 아닙니다.')
            self.research_detail.configure(state='normal')
            self.research_detail.delete('1.0', 'end')
            self.research_detail.insert('1.0', summary)
            self.research_detail.configure(state='disabled')
            self.research_feedback.set('근거 JSON 자체 무결성 확인 · ' +
                                       ('로컬 DB 일치' if result['local_report_matches'] else '로컬 DB 불일치'))
        except (ValueError, PermissionError, OSError, UnicodeError) as exc:
            self.research_feedback.set(f'근거 JSON 재검사 실패: {exc}')

    def _archive_offline_research(self) -> None:
        if self.research_selected_id is None:
            self.research_feedback.set('먼저 목록에서 보관할 자료를 선택해 주세요.')
            return
        try:
            self.store.archive_offline_research(self.research_selected_id)
            self._refresh_offline_research()
            self.research_selected_id=None
            self.research_feedback.set('자료 보관 완료. 삭제하지 않고 기록을 유지했습니다.')
        except (ValueError,PermissionError) as exc:
            self.research_feedback.set(str(exc))

def run() -> None:
    root = tk.Tk()
    try:
        app = AIWACKWindow(root)
        def on_close() -> None:
            app.cancel_local_model(wait=True)
            root.destroy()
        root.protocol("WM_DELETE_WINDOW", on_close)
        root.mainloop()
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass

