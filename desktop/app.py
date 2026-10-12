"""AIWACK standalone native window with single-owner local login.

No HTTP server is started. This is a runnable prototype shell, not an AI company.
"""
from __future__ import annotations

import csv
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, messagebox

from desktop.storage import LocalStore
from desktop.admin_sections import SECTIONS, section_for

APP_TITLE = "AIWACK | AI Autonomous Company"
CURRENT_STAGE = 11
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
        self.account_password.set("")
        self.password_confirm.set("")
        self.auth_frame.destroy()
        self.note.set(self.store.read_note())
        self._layout()
        self.refresh()

    def sign_out(self) -> None:
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
        style.configure("Progress.Horizontal.TProgressbar", troughcolor="#23334b", background="#6a9dff", thickness=11)
        style.configure("Treeview", background="#f8fbff", foreground="#26334a", fieldbackground="#f8fbff", rowheight=27, font=("Malgun Gothic", 9))
        style.configure("Treeview.Heading", font=("Malgun Gothic", 9, "bold"))

    def _label(self, parent: tk.Widget, text: str, *, size: int = 11, weight: str = "normal", fg: str = "#eaf0ff", bg: str = "#1c2a40", **kwargs) -> tk.Label:
        return tk.Label(parent, text=text, font=("Malgun Gothic", size, weight), fg=fg, bg=bg, **kwargs)

    def _panel(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg="#1c2a40", padx=22, pady=18, highlightthickness=1, highlightbackground="#30435f")

    def _layout(self) -> None:
        outer = tk.Frame(self.root, bg="#121c2d", padx=25, pady=20)
        self.main_frame = outer
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="AIWACK", font=("Malgun Gothic", 26, "bold"), fg="#ffffff", bg="#121c2d").pack(anchor="w")
        tk.Label(outer, text="AI Autonomous Company  ·  Windows 데스크톱 초기 개발판", font=("Malgun Gothic", 11), fg="#abc2df", bg="#121c2d").pack(anchor="w", pady=(2, 15))
        tk.Button(outer, text="로그아웃", command=self.sign_out, bg="#304561", fg="#f4f7ff", padx=12, pady=5).pack(anchor="e")
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        dashboard = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        persistence = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        roadmap = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        administration = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        company = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)
        self.tabs.add(dashboard, text="개발 현황")
        self.tabs.add(persistence, text="로컬 저장 실사")
        self.tabs.add(roadmap, text="100단계 계획")
        self.tabs.add(administration, text="관리자 센터")
        self.tabs.add(company, text="회사·목표 관리")
        self._dashboard(dashboard)
        self._persistence(persistence)
        self._roadmap(roadmap)
        self._administration(administration)
        self._company(company)
        tk.Label(outer, text="실행 중인 웹 서버 없음  ·  사용자 PC의 로컬 SQLite 파일만 사용  ·  외부 전송 없음", bg="#121c2d", fg="#91aacd", font=("Malgun Gothic", 9)).pack(anchor="w", pady=(13, 0))

    def _dashboard(self, parent: tk.Frame) -> None:
        section = self._panel(parent)
        section.pack(fill="x", pady=(0, 16))
        self._label(section, "프로그램 실행 상태", size=17, weight="bold").pack(anchor="w")
        self._label(section, "데스크톱 창이 실제 실행되고 있으며 외부 서버가 필요하지 않습니다.", fg="#bfcfe5").pack(anchor="w", pady=(8, 5))
        self._label(section, "SQLite 상태 및 저장 파일", weight="bold").pack(anchor="w", pady=(10, 4))
        self._label(section, "", fg="#8ee4b7", textvariable=self.status_text, wraplength=850, justify="left").pack(anchor="w")
        summary = self._panel(parent)
        summary.pack(fill="x", pady=(0, 16))
        self._label(summary, f"{CURRENT_STAGE} / {TOTAL_STAGES}단계 — 초기 프로토타입", size=17, weight="bold").pack(anchor="w")
        ttk.Progressbar(summary, style="Progress.Horizontal.TProgressbar", maximum=TOTAL_STAGES, value=CURRENT_STAGE).pack(fill="x", pady=(15, 9))
        self._label(summary, "다음 개발 단계: 12단계 · 부서 생성·수정·삭제 기능", fg="#bfcfe5").pack(anchor="w")
        missing = self._panel(parent)
        missing.pack(fill="both", expand=True)
        self._label(missing, "아직 없는 기능", size=16, weight="bold").pack(anchor="w")
        self._label(missing, "총괄 AI / 부서별 직원 AI / 자율 업무 실행 / 사업 및 매출 시스템", fg="#f7cb92", wraplength=850, justify="left").pack(anchor="w", pady=(10, 5))
        self._label(missing, "현재 확인 가능한 기능: 관리자 로그인, 회사 정보·목표 관리, 로컬 저장 및 재시작 후 유지.", fg="#bfcfe5", wraplength=850, justify="left").pack(anchor="w")

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
            status = "완료" if item["status"] == "DONE" else "미완료"
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


def run() -> None:
    root = tk.Tk()
    try:
        AIWACKWindow(root)
        root.mainloop()
    finally:
        if root.winfo_exists():
            root.destroy()
