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

APP_TITLE = "AIWACK | AI Autonomous Company"
CURRENT_STAGE = 9
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
        self.tabs.add(dashboard, text="개발 현황")
        self.tabs.add(persistence, text="로컬 저장 실사")
        self.tabs.add(roadmap, text="100단계 계획")
        self._dashboard(dashboard)
        self._persistence(persistence)
        self._roadmap(roadmap)
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
        self._label(summary, "다음 개발 단계: 10단계 · 관리자 화면 기본 틀 구축", fg="#bfcfe5").pack(anchor="w")
        missing = self._panel(parent)
        missing.pack(fill="both", expand=True)
        self._label(missing, "아직 없는 기능", size=16, weight="bold").pack(anchor="w")
        self._label(missing, "총괄 AI / 부서별 직원 AI / 자율 업무 실행 / 사업 및 매출 시스템", fg="#f7cb92", wraplength=850, justify="left").pack(anchor="w", pady=(10, 5))
        self._label(missing, "현재 확인 가능한 기능은 관리자 로그인·권한 검사, 데스크톱 실행, 로컬 데이터 저장 및 재시작 후 유지입니다.", fg="#bfcfe5", wraplength=850, justify="left").pack(anchor="w")

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
