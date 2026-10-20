"""AIWACK company cockpit. Real SQLite organization, tasks and model runs.

This is a GUI for the owner, never a simulation of active AI employees or sales.
All run buttons delegate to the existing authenticated local-model runtime.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from desktop import company_operations as ops

BG = '#0b1220'
CARD = '#151f30'
CARD2 = '#1b2a40'
EDGE = '#293954'
INK = '#f5f8ff'
MUTED = '#9caec7'
BLUE = '#468bfa'
TEAL = '#6addc4'
AMBER = '#ffce82'
RED = '#ff8194'
FONT = 'Malgun Gothic'


class CompanyOffice:
    def __init__(self, app, parent):
        self.app, self.root, self.store = app, app.root, app.store
        self.parent = parent
        self.pending = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.generation = app._session_generation
        self.status = tk.StringVar(value='회사 운영 데이터 연결 중')
        self.title = tk.StringVar()
        self.goal_title = tk.StringVar()
        self.latest_output = '아직 실제 AI 모델 실행 기록이 없습니다.'
        self.cards = {}
        self.nav_buttons = {}
        self.views = {}
        self.chief_label = tk.StringVar(value='총괄 AI 확인 중')
        self.chief_state = tk.StringVar(value='설정 확인 중')
        self.live_badge = tk.StringVar(value='운영 상태 조회 중')
        self.team_summary = tk.StringVar(value='직원 모델을 확인하고 있습니다.')
        self.review_summary = tk.StringVar(value='저장된 결과물 없음')
        self.proposal_summary = tk.StringVar(value='총괄 AI 제안 없음')
        self.after_action = 'results'
        self.view_name = 'overview'
        self._draw()
        self.refresh()

    def _label(self, parent, text='', *, size=10, bold=False, color=INK, bg=CARD, **kwargs):
        return tk.Label(parent, text=text, bg=bg, fg=color,
                        font=(FONT, size, 'bold' if bold else 'normal'),
                        anchor='w', **kwargs)

    def _action(self, parent, label, command, *, strong=False, danger=False, compact=False):
        color = '#903c53' if danger else BLUE if strong else '#293d58'
        b = tk.Button(parent, text=label, command=command, relief='flat',
                      borderwidth=0, bg=color, fg=INK,
                      activebackground='#5d92e8' if strong else '#3a5373',
                      activeforeground='white', cursor='hand2',
                      padx=10 if compact else 13, pady=6 if compact else 8,
                      font=(FONT, 9 if compact else 10, 'bold'))
        b.pack(side='left', padx=(0, 6), pady=2)
        return b

    def _card(self, parent, *, padx=12, pady=10):
        return tk.Frame(parent, bg=CARD, highlightthickness=1,
                        highlightbackground=EDGE, padx=padx, pady=pady)

    def _divider(self, parent):
        tk.Frame(parent, bg=EDGE, height=1).pack(fill='x', pady=8)

    def _configure_tables(self):
        style = ttk.Style(self.root)
        style.configure('Office.Treeview', background=CARD, foreground=INK,
                        fieldbackground=CARD, borderwidth=0, rowheight=29,
                        font=(FONT, 9))
        style.configure('Office.Treeview.Heading', background='#26364e',
                        foreground=INK, font=(FONT, 9, 'bold'), relief='flat', padding=(7, 6))
        style.map('Office.Treeview', background=[('selected', '#2e60a5')],
                  foreground=[('selected', '#ffffff')])
        style.map('Office.Treeview.Heading', background=[('active', '#324661')])

    def _table(self, parent, specs, *, height=5):
        keys = [key for key, *_ in specs]
        wrap = tk.Frame(parent, bg=CARD)
        wrap.pack(fill='both', expand=True)
        tree = ttk.Treeview(wrap, columns=keys, show='headings', height=height,
                            style='Office.Treeview', selectmode='browse')
        for key, title, width in specs:
            tree.heading(key, text=title)
            tree.column(key, width=width, stretch=True, anchor='w')
        scroll = ttk.Scrollbar(wrap, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        tree.tag_configure('warn', foreground=AMBER)
        tree.tag_configure('ready', foreground=TEAL)
        return tree

    def _draw(self):
        self.parent.configure(bg=BG)
        self._configure_tables()
        top = tk.Frame(self.parent, bg=BG)
        top.pack(fill='x', padx=12, pady=(6, 9))
        name = tk.Frame(top, bg=BG)
        name.pack(side='left', fill='x', expand=True)
        self._label(name, 'AIWACK   /   COMPANY CONTROL', size=9, bold=True,
                    color=TEAL, bg=BG).pack(anchor='w')
        self._label(name, 'AI 회사 운영센터', size=19, bold=True,
                    bg=BG).pack(anchor='w')
        right = tk.Frame(top, bg=BG)
        right.pack(side='right', anchor='e')
        self._label(right, '', size=9, color=AMBER, bg=BG,
                    textvariable=self.live_badge).pack(anchor='e', pady=(2, 4))
        self._action(right, '↻  새로고침', self.refresh, compact=True)
        self._action(right, '회사 DB 백업', self.backup_company, compact=True)
        self._action(right, '백업 무결성 확인', self.verify_company_backup, compact=True)

        navigation = tk.Frame(self.parent, bg=BG)
        navigation.pack(fill='x', padx=12, pady=(0, 8))
        for key, label in [('overview', '◈  회사 현황'), ('organization', '♧  AI 조직'),
                           ('planning', '◇  AI 기획'), ('work', '☷  업무 실행'), ('results', '▤  결과 · 승인')]:
            button = tk.Button(navigation, text=label, command=lambda v=key: self.set_view(v),
                               relief='flat', borderwidth=0, padx=15, pady=7,
                               font=(FONT, 10, 'bold'), cursor='hand2')
            button.pack(side='left', padx=(0, 6))
            self.nav_buttons[key] = button

        kpis = tk.Frame(self.parent, bg=BG)
        kpis.pack(fill='x', padx=9, pady=(0, 8))
        for col, (key, label) in enumerate([('departments', 'DEPARTMENTS  /  부서'),
                                             ('employees', 'AI EMPLOYEES  /  직원'),
                                             ('tasks', 'OPEN TASKS  /  진행 업무'),
                                             ('pending', 'REVIEW  /  검수 대기')]):
            kpis.columnconfigure(col, weight=1, uniform='metrics')
            card = self._card(kpis, padx=12, pady=7)
            card.grid(row=0, column=col, sticky='nsew', padx=3)
            self._label(card, label, size=8, color=MUTED).pack(anchor='w')
            number = tk.StringVar(value='—')
            self._label(card, '', size=21, bold=True, textvariable=number).pack(anchor='w')
            self.cards[key] = number
        # Kept for backward-compatible smoke tests, not shown in the KPI row.
        self.cards['completed'] = tk.StringVar(value='0')

        self.content = tk.Frame(self.parent, bg=BG)
        self.content.pack(fill='both', expand=True, padx=12, pady=(0, 7))
        for key in ('overview', 'organization', 'planning', 'work', 'results'):
            self.views[key] = tk.Frame(self.content, bg=BG)
        self._draw_overview(self.views['overview'])
        self._draw_organization(self.views['organization'])
        self._draw_planning(self.views['planning'])
        self._draw_work(self.views['work'])
        self._draw_results(self.views['results'])

        foot = tk.Frame(self.parent, bg=BG)
        foot.pack(fill='x', padx=12, pady=(2, 5))
        self._label(foot, '', color=TEAL, size=9, bg=BG,
                    textvariable=self.status, wraplength=970).pack(fill='x')
        self.set_view('overview')

    def _draw_overview(self, frame):
        frame.columnconfigure(0, weight=2, uniform='center')
        frame.columnconfigure(1, weight=3, uniform='center')
        frame.rowconfigure(0, weight=1)
        left = self._card(frame)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        self._label(left, '총괄 AI  /  EXECUTIVE', size=12, bold=True).pack(anchor='w')
        self._divider(left)
        self._label(left, '', size=12, bold=True, textvariable=self.chief_label,
                    wraplength=285).pack(anchor='w', pady=(0, 3))
        self._label(left, '', color=AMBER, size=9, textvariable=self.chief_state,
                    wraplength=285).pack(anchor='w', pady=(0, 10))
        self._label(left, '모델 준비 및 실행 현황', size=10, bold=True).pack(anchor='w')
        self._label(left, '', size=9, color=MUTED, textvariable=self.team_summary,
                    wraplength=285, justify='left').pack(anchor='w', pady=(4, 10))
        shortcut = tk.Frame(left, bg=CARD)
        shortcut.pack(anchor='w')
        self._action(shortcut, '총괄 AI 진단', self.ask_chief, strong=True, compact=True)
        self._action(shortcut, '15개 부서 구성', self.seed_blueprint, compact=True)
        self._label(left, '모델 미배정 상태에서는 직원이 실제 일하지 않습니다.',
                    size=8, color=MUTED, wraplength=270).pack(anchor='w', pady=(7, 0))

        right = self._card(frame)
        right.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        header = tk.Frame(right, bg=CARD)
        header.pack(fill='x', pady=(0, 7))
        self._label(header, '최근 회사 업무', size=12, bold=True).pack(side='left')
        self._action(header, '전체 업무 보기 →', lambda: self.set_view('work'), compact=True)
        self.jobs = self._table(right, [('job', '업무', 220), ('owner', '담당 직원', 125),
                                        ('state', '상태', 82)], height=5)
        self.jobs.bind('<Double-1>', lambda _event: self.set_view('work'))
        self._label(right, '업무 실행은 사람의 명시적 시작 명령 후 진행됩니다.',
                    size=8, color=MUTED).pack(anchor='w', pady=(7, 0))

    def _draw_organization(self, frame):
        card = self._card(frame)
        card.pack(fill='both', expand=True)
        top = tk.Frame(card, bg=CARD)
        top.pack(fill='x', pady=(0, 7))
        self._label(top, 'AI 조직도  /  직급 · 부서 · 모델', size=12, bold=True).pack(side='left')
        self._action(top, '15개 부서 초기 구성', self.seed_blueprint, strong=True, compact=True)
        self._action(top, '로컬 모델 연결', self.connect_model, strong=True, compact=True)
        self._action(top, '모델 배정 화면 ↗', lambda: self._goto_native('직원별 모델'), compact=True)
        self.staff = self._table(card, [('name', '직원 AI', 195), ('department', '부서', 145),
                                        ('tier', '직급', 75), ('model', '로컬 모델', 170),
                                        ('state', '상태', 90)], height=8)
        self._label(card, '총괄 AI → 부서장 AI → 직원 AI.  초안 직원은 모델 실행 인스턴스가 아닙니다.',
                    color=MUTED, size=9).pack(anchor='w', pady=(6, 0))

    def _draw_planning(self, frame):
        card = self._card(frame)
        card.pack(fill='both', expand=True)
        goalbar=tk.Frame(card,bg=CARD)
        goalbar.pack(fill='x',pady=(0,7))
        self._label(goalbar,'새 회사 목표',size=9,color=MUTED).pack(side='left',padx=(0,7))
        self.goal_entry=tk.Entry(goalbar,textvariable=self.goal_title,font=(FONT,10),
                                 bg='#f6f8fc',fg='#152134',relief='flat')
        self.goal_entry.pack(side='left',fill='x',expand=True,ipady=7,padx=(0,8))
        self.goal_entry.bind('<Return>',lambda _event:self.create_goal())
        self._action(goalbar,'목표 등록·활성화',self.create_goal,strong=True,compact=True)
        head = tk.Frame(card, bg=CARD)
        head.pack(fill='x', pady=(0, 6))
        self._label(head, '회사 업무 제안  /  PLANNING PIPELINE', size=12, bold=True).pack(side='left')
        self._action(head, '목표·차단 업무 검색', self.scan_proposals, compact=True)
        self._action(head, '총괄 AI 구체화', self.refine_proposal, compact=True)
        self.proposal_list = self._table(card, [('id','번호',54),('title','제안 제목',300),
                                                 ('origin','작성 출처',100),('state','승인 상태',105)],height=5)
        self.proposal_list.bind('<Double-1>',lambda _event:self.open_proposal())
        controls=tk.Frame(card,bg=CARD)
        controls.pack(fill='x',pady=(7,0))
        self._action(controls,'제안 상세',self.open_proposal,compact=True)
        self._action(controls,'업무로 승인',self.approve_proposal,strong=True,compact=True)
        self._action(controls,'제안 기각',self.reject_proposal,danger=True,compact=True)
        self._label(card,'',size=9,color=AMBER,textvariable=self.proposal_summary).pack(anchor='w',pady=(6,0))
        self._label(card,'규칙 검색은 AI 모델을 호출하지 않습니다. 총괄 AI 모델이 없으면 구체화 불가 · 승인 전엔 업무 미생성',
                    size=8,color=MUTED,wraplength=870).pack(anchor='w',pady=(4,0))

    def _draw_work(self, frame):
        main = self._card(frame)
        main.pack(fill='both', expand=True)
        head = tk.Frame(main, bg=CARD)
        head.pack(fill='x', pady=(0, 5))
        self._label(head, '업무 지휘실  /  TASK BOARD', size=12, bold=True).pack(side='left')
        self._action(head, '담당 AI 자동 배정', self.assign, compact=True)
        self._action(head, '선택 업무 실행', self.run_selected, strong=True, compact=True)
        self._action(head, '승인 AI 2명 병렬', self.run_approved_parallel, compact=True)
        self._action(head, '31명 승인 연속 운영', self.run_campaign, compact=True)
        self._action(head, '운영 기록 확인', self.campaign_report, compact=True)
        self.work_jobs = self._table(main, [('job', '업무', 290), ('owner', '담당 AI', 150),
                                            ('state', '진행', 95)], height=4)
        self.work_jobs.bind('<<TreeviewSelect>>', self._sync_work_selection)
        editor = tk.Frame(main, bg=CARD)
        editor.pack(fill='x', pady=(8, 0))
        self.task_entry = tk.Entry(editor, textvariable=self.title, font=(FONT, 10),
                                   bg='#f6f8fc', fg='#152134', relief='flat')
        self.task_entry.pack(side='left', fill='x', expand=True, ipady=7, padx=(0, 8))
        self.task_entry.bind('<Return>', lambda _event: self.create())
        self._action(editor, '+  업무 등록', self.create, strong=True, compact=True)
        controls = tk.Frame(main, bg=CARD)
        controls.pack(fill='x', pady=(6, 0))
        self._action(controls, '총괄 AI 지시 초안', self.ask_chief_order, compact=True)
        self._action(controls, '최대 3개 실행', self.run_batch, compact=True)
        self._action(controls, '승인 업무 자동 회수 ≤3', self.run_approved_queue, compact=True)
        self._action(controls, '실행 결과', lambda: self.set_view('results'), compact=True)
        self._action(controls, '비상 정지', self.stop, danger=True, compact=True)
        self._label(main, '업무를 선택 → 담당 AI 배정 → 모델 실행.  모델이 없으면 실패 사유를 표시합니다.',
                    size=8, color=MUTED).pack(anchor='w', pady=(7, 0))

    def _draw_results(self, frame):
        card = self._card(frame)
        card.pack(fill='both', expand=True)
        head = tk.Frame(card, bg=CARD)
        head.pack(fill='x', pady=(0, 6))
        self._label(head, 'AI 결과물  /  REVIEW QUEUE', size=12, bold=True).pack(side='left')
        self._action(head, '결과 열기', self.open_result, compact=True)
        self._action(head, '승인', self.approve_selected, strong=True, compact=True)
        self._action(head, '수정 요청', self.request_changes, compact=True)
        self._action(head, '반려', self.reject_selected, danger=True, compact=True)
        self.artifact_list = self._table(card, [('name', '실제 AI 생성 결과', 300),
                                               ('task', '업무 #', 72),
                                               ('review', '검수 상태', 112)], height=5)
        self.artifact_list.bind('<Double-1>', lambda _event: self.open_result())
        actionbar=tk.Frame(card,bg=CARD)
        actionbar.pack(fill='x',pady=(5,0))
        self._action(actionbar,'승인 결과로 업무 완료',self.finish_reviewed,strong=True,compact=True)
        self._action(actionbar,'총괄 AI 회수 검토',self.request_chief_report,compact=True)
        self._action(actionbar,'총괄 보고서 보기',self.open_chief_report,compact=True)
        self._action(actionbar,'중단된 검토 재개',self.recover_interrupted_review,compact=True)
        recoverybar = tk.Frame(card, bg=CARD)
        recoverybar.pack(fill='x', pady=(4, 0))
        self._action(recoverybar, '복구 대기 총괄 검토 최대 3건',
                     self.recover_interrupted_queue, compact=True)
        self._action(recoverybar, '미완료 직원 실행 확인 ↗',
                     lambda: self._goto_native('AI 업무 실행'), compact=True)
        self._action(recoverybar, '결과물 품질 검사', self.quality_check_result, compact=True)
        self._action(recoverybar, '승인 결과 파일 저장', self.export_result, compact=True)
        self._label(card, '', size=9, color=AMBER, textvariable=self.review_summary).pack(anchor='w', pady=(5, 0))
        self._label(card, '실제 생성 결과가 없으면 표시하지 않습니다. 승인해도 업무가 자동 완료되지 않습니다.',
                    size=8, color=MUTED).pack(anchor='w', pady=(3, 0))

    def set_view(self, name):
        if name not in self.views:
            raise ValueError('존재하지 않는 회사 화면입니다.')
        for frame in self.views.values():
            frame.pack_forget()
        self.views[name].pack(fill='both', expand=True)
        self.view_name = name
        for key, button in self.nav_buttons.items():
            selected = key == name
            button.configure(bg=BLUE if selected else CARD2,
                             fg='#ffffff' if selected else MUTED,
                             activebackground=BLUE)

    def connect_model(self):
        from desktop.company_model_connect_ui import ConnectLocalModelDialog
        return ConnectLocalModelDialog(self)

    def _goto_native(self, label_fragment):
        choices = list(self.app.quick_navigation['values'])
        found = next((i for i, name in enumerate(choices) if label_fragment in name), None)
        if found is None:
            self._say('모델 설정 화면을 찾을 수 없습니다.')
            return
        self.app.tabs.select(found)
        self.app.quick_navigation.current(found)

    def _say(self, text):
        self.status.set(str(text)[:350])

    def _show_output(self, text):
        self.latest_output = str(text)[:20000]

    def backup_company(self):
        from desktop import company_backup
        try:
            if not messagebox.askyesno('회사 SQLite 안전 백업',
                    '현재 회사 데이터를 별도의 검증 가능한 SQLite 백업으로 생성합니다. '
                    '기존 프로그램 DB는 변경하거나 복원하지 않습니다. 진행하시겠습니까?',
                    parent=self.root):
                return
            info=company_backup.create_snapshot(self.store)
            self._say('회사 DB 안전 백업 완료: '+info['path'])
        except (ValueError,PermissionError,RuntimeError,OSError) as exc:
            self._say('회사 백업 실패: '+str(exc))

    def verify_company_backup(self):
        from desktop import company_backup
        from desktop.storage import user_data_dir
        from pathlib import Path
        try:
            folder=user_data_dir()/'verified_backups'
            backups=sorted(folder.glob('aiwack_backup_*.sqlite3'),
                           key=lambda p:p.stat().st_mtime,reverse=True) if folder.is_dir() else []
            if not backups:
                self._say('검증할 AIWACK 회사 백업이 없습니다.')
                return
            verified=company_backup.verify_snapshot(self.store,backups[0])
            self._say('가장 최근 회사 SQLite 백업의 무결성 확인 완료: '+verified['path'])
        except (ValueError,PermissionError,RuntimeError,OSError) as exc:
            self._say('회사 백업 검증 실패: '+str(exc))

    def refresh(self):
        try:
            data = ops.company_snapshot(self.store)
            self.cards['departments'].set(str(len(data['departments'])))
            self.cards['employees'].set(str(len(data['team'])))
            self.cards['tasks'].set(str(data['open_tasks']))
            self.cards['completed'].set(str(data['completed']))
            self.cards['pending'].set(str(data['pending_reviews']))
            chief = data['chief']
            self.chief_label.set(str(chief['display_name']) if chief else '총괄 AI 미지정')
            ready = bool(data['live_model_ready'])
            self.chief_state.set('총괄 모델 지정됨 · 실제 실행은 미검증' if ready else '실제 모델 미배정 · 총괄 AI 준비 필요')
            self.live_badge.set('●  비상 정지 활성' if data['emergency'] else
                                '●  총괄 모델 지정됨 (실행 미검증)' if ready else '●  AI 모델 설정 필요')
            self.team_summary.set(f"총 {len(data['team'])}명 중 모델 배정 {data['model_ready_count']}명\n"
                                  f"실행 중 업무 {data['running']}건 · 완료 {data['completed']}건\n"
                                  f"실제 매출·판매는 아직 검증되지 않았습니다.")
            proposals = ops.planning_proposals(self.store)
            for tree in (self.staff, self.jobs, self.work_jobs, self.artifact_list, self.proposal_list):
                selected = tree.selection()
                tree.delete(*tree.get_children())
                if tree is self.staff:
                    for e in data['team']:
                        self.staff.insert('', 'end', iid='employee-'+str(e['id']),
                            values=(e['name'], e['department'], e['tier'], e['model'], e['lifecycle']),
                            tags=('ready',) if e['model'] != '모델 미배정' else ('warn',))
                elif tree in (self.jobs, self.work_jobs):
                    for item in data['tasks']:
                        tree.insert('', 'end', iid=str(item['id']),
                            values=(item['title'], item['assignee'], item['status']),
                            tags=('warn',) if item['assignee']=='담당자 미배정' else ())
                elif tree is self.proposal_list:
                    for proposal in proposals:
                        tree.insert('', 'end', iid=str(proposal['id']),
                                    values=(proposal['id'],proposal['title'],proposal['origin'],proposal['status']),
                                    tags=('warn',) if proposal['status']=='pending' else ())
                else:
                    for art in data['recent_artifacts']:
                        tree.insert('', 'end', iid=str(art['id']),
                            values=(art['title'], art['task_id'], art['review_status']),
                            tags=('warn',) if art['review_status']=='pending' else ())
                if selected and tree.exists(selected[0]):
                    tree.selection_set(selected[0])
            recover_state=ops.inspect_recovery_state(self.store)
            self.review_summary.set(
                f"총 결과물 {data['artifacts']}건 · 검수 대기 {data['pending_reviews']}건"
                f" · 총괄 검토 복구 {len(recover_state['pending_chief_reviews'])}건"
                f" · 실행 중 직원 {len(recover_state['running_worker_runs'])}건"
                f"{' 이상 (조회 200건 초과)' if recover_state['running_worker_runs_truncated'] else ''}"
                f" · 미종료 모델 호출 {len(recover_state['running_model_calls'])}건"
                f"{' 이상 (조회 200건 초과)' if recover_state['running_model_calls_truncated'] else ''}"
                " · 직원 자동 재실행 없음")
            self.proposal_summary.set(f"업무 제안 {len(proposals)}건 중 승인 대기 {data['pending_proposals']}건 · 소유자 승인 필수")
            self._say('실제 회사 데이터 연결됨 · 허위 AI 활동이나 매출을 표시하지 않습니다.')
        except (ValueError, PermissionError, RuntimeError) as exc:
            self._say('회사 조회 실패: '+str(exc))

    def _sync_work_selection(self, _event=None):
        selected = self.work_jobs.selection()
        if selected and self.jobs.exists(selected[0]):
            self.jobs.selection_set(selected[0])

    def selected_task(self):
        selected = self.work_jobs.selection() if self.view_name == 'work' else self.jobs.selection()
        if not selected:
            raise ValueError('목록에서 실제 업무 한 건을 선택하세요.')
        return int(selected[0])

    def create(self):
        try:
            task_id = ops.create_task(self.store, self.title.get())
            self.title.set('')
            self.refresh()
            self.set_view('work')
            self.work_jobs.selection_set(str(task_id))
            self.work_jobs.see(str(task_id))
            self._say(f'업무 #{task_id} 등록됨 · 직원 AI 실행 전 단계')
        except (ValueError, PermissionError) as exc:
            self._say(str(exc))

    def seed_blueprint(self):
        if not messagebox.askyesno('AI 조직 첫 설정',
                '15개 부서 및 31개 AI 직원 초안을 만듭니다.\n'
                '실제 모델을 배정하지 않는 한 AI는 실행되지 않습니다.\n'
                '현재 빈 조직에서만 생성합니다. 계속할까요?', parent=self.root):
            return
        try:
            info = ops.initialize_company_blueprint(self.store)
            self.refresh()
            self.set_view('organization')
            self._say(f"부서 {info['departments']}개 · AI 직원 초안 {info['draft_ai_profiles']}명 생성됨")
        except (ValueError, PermissionError) as exc:
            self._say(str(exc))

    def assign(self):
        try:
            info = ops.assign_task(self.store, self.selected_task())
            self.refresh()
            self._say('담당 직원 AI: '+str(info['employee_name'])+' · 실제 실행은 별도 명령이 필요합니다.')
        except (ValueError, PermissionError) as exc:
            self._say(str(exc))

    def _start(self, task, *, after='results'):
        if self.worker and self.worker.is_alive():
            self._say('이미 AI가 실행 중입니다. 새 실행을 시작하지 않습니다.')
            return
        self.cancel.clear()
        self.after_action = after
        self._say('실제 로컬 AI 실행 중 · 감사 기록과 결과물을 저장합니다.')
        def work():
            try:
                self.pending.put(('result', task()))
            except Exception as exc:
                self.pending.put(('error', type(exc).__name__+': '+str(exc)))
        self.worker = threading.Thread(target=work, daemon=True, name='AIWACK-company-office')
        self.worker.start()
        self.root.after(200, self._poll)

    def _poll(self):
        if self.generation != self.app._session_generation or self.app.main_frame is None:
            self.cancel.set()
            return
        try:
            kind, result = self.pending.get_nowait()
        except queue.Empty:
            if self.worker and self.worker.is_alive():
                self.root.after(200, self._poll)
            return
        self._show_output(result)
        self.refresh()
        if kind == 'error':
            if self.after_action == 'model_probe':
                dialog = getattr(self, 'model_dialog', None)
                if dialog is not None and dialog.window.winfo_exists():
                    dialog.feedback.set('실제 모델 호출 실패: '+str(result)[:250])
            self._say('실제 AI 실행 실패: '+str(result))
        else:
            if self.after_action == 'model_probe':
                dialog = getattr(self, 'model_dialog', None)
                if dialog is not None and dialog.window.winfo_exists():
                    dialog.feedback.set('실제 모델 응답 수신 및 호출 감사 기록 저장 완료 · 결과는 관리자 검수 전입니다.')
                self._say('로컬 직원 모델이 실제 응답했습니다. 진단 감사 기록만 저장했습니다.')
                self._text_dialog('로컬 AI 직원 모델 호출 진단', str(result))
            elif self.after_action == 'chief_queue':
                self.set_view('results')
                n=int(result['completed_cycles'])
                self._say(f'승인 업무 {n}건 직원 실행·총괄 회수 완료 · 모두 소유자 검수 대기')
                if result['reports']:
                    self.open_chief_report(int(result['reports'][-1]['artifact_id']))
            elif self.after_action == 'chief_parallel':
                self.set_view('results')
                self._say('실제 직원 AI 2명 병렬 업무·총괄 AI 검토 완료 · 모두 관리자 승인 대기')
                if result['reports']:
                    self.open_chief_report(int(result['reports'][-1]['artifact_id']))
            elif self.after_action == 'company_campaign':
                self.set_view('results')
                self._say(f"승인된 AI 공동업무 #{result['id']}: 검토 대기 {result['review_pending']}건 · 자동 최종 승인 없음")
            elif self.after_action == 'chief_recovery_queue':
                self.set_view('results')
                count=int(result['recovered_reviews'])
                self._say(f'저장된 직원 결과물의 총괄 AI 검토 {count}건 복구 · 직원 중복 실행 없음 · 관리자 검수 대기')
                if result['reports']:
                    self.open_chief_report(int(result['reports'][-1]['artifact_id']))
            elif self.after_action == 'chief_report':
                self.set_view('results')
                self._say('총괄 AI 회수 보고서 저장됨 · 관리자 수락/반려 전에는 업무 상태 변경 없음')
                self.open_chief_report(int(result['artifact_id']))
            elif self.after_action == 'chief_order':
                self.review_chief_order(result)
                self._say('총괄 AI 초안 수신 · 소유자가 지시를 승인해야만 직원이 수행할 수 있습니다.')
            elif self.after_action == 'planning':
                self.set_view('planning')
                self._say('실제 총괄 모델 제안 초안 저장 · 관리자 승인 전에는 실행되지 않습니다.')
            elif self.after_action == 'chief':
                self._say('실제 총괄 AI 모델 응답 수신 · 답변 창에서 확인하세요.')
                self._text_dialog('총괄 AI 회사 진단',str(result))
            else:
                self._say('로컬 AI 실행 결과 수신 · 결과물은 승인 대기이며 매출이 아닙니다.')
                self.set_view('results')

    def run_selected(self):
        try:
            task_id = self.selected_task()
        except ValueError as exc:
            self._say(str(exc))
            return
        self._start(lambda: ops.execute_task(self.store, task_id, cancel=self.cancel))

    def run_batch(self):
        self._start(lambda: ops.execute_batch(self.store, max_tasks=3, cancel=self.cancel))

    def campaign_report(self):
        from desktop import company_campaign as campaigns
        try:
            all_campaigns=campaigns.list_campaigns(self.store,limit=5)
            if not all_campaigns:
                self._say('아직 생성된 사내 AI 연속 운영 기록이 없습니다.')
                return
            lines=[]
            for row in all_campaigns:
                lines.append(f"#{row['id']} {row['state']} | 전체 {row['total']} / "
                             f"검토 대기 {row['review_pending']} / 확인 필요 {row['needs_review']} / "
                             f"실행 대기 {row['pending']} | {row['last_error'][:120]}")
            self._text_dialog('기존 AI 공동업무 실행 기록', '\n'.join(lines))
        except (PermissionError,ValueError) as exc:
            self._say('운영 기록 조회 오류: '+str(exc))

    def run_campaign(self):
        """One owner-confirmed manifest can run 31 existing approved AI tasks."""
        from desktop import company_campaign as campaigns
        if self.worker and self.worker.is_alive():
            self._say('이미 실행 중인 AI 작업이 있습니다.')
            return
        try:
            existing=campaigns.list_campaigns(self.store,limit=1)
            if existing and existing[0]['state'] in ('running','paused','draft'):
                item=existing[0]
                if item['state']=='running':
                    if not messagebox.askyesno('중단 운영 기록 확인',
                            '이전 운영이 여전히 진행 중일 수 있습니다. '
                            '임의 재실행 없이 중단 기록만 확인하시겠습니까?',parent=self.root):
                        return
                    item=campaigns.inspect_interrupted_campaign(self.store,item['id'])
                if item['state']=='paused' and item['needs_review']:
                    if messagebox.askyesno('저장된 총괄 보고서 연결 확인',
                            '기존 SQLite에 이미 저장된 총괄 보고서만 운영 기록에 연결합니다. '
                            '직원/총괄 모델 재실행은 하지 않습니다. 확인하시겠습니까?',
                            parent=self.root):
                        item=campaigns.reconcile_manually_recovered_chief_reviews(
                            self.store,item['id'])
                if item['needs_review'] or item['running']:
                    self._say(f"운영 작업 #{item['id']}에 중단·실행 중 기록이 있습니다. "
                              '운영 기록을 확인하고 기존 결과를 먼저 검토하세요. 자동 재실행하지 않습니다.')
                    self.campaign_report()
                    return
                cid=item['id']
                if not messagebox.askyesno('승인된 사내 AI 연속 운영 재개',
                        f'기존 운영 작업 #{cid}의 승인된 나머지 {item["pending"]}건만 처리합니다. '
                        '자동 재승인·재실행 없이 진행할까요?',parent=self.root):
                    return
            else:
                choices=campaigns.candidate_tasks(self.store,limit=31)
                if not choices:
                    self._say('승인된 총괄 AI 지시·담당 직원 모델이 모두 연결된 업무가 없습니다.')
                    return
                ids=tuple(x['task_id'] for x in choices)
                preview='\n'.join(
                    f"#{x['task_id']} / 직원 #{x['employee_id']} / {x['title'][:35]}"
                    for x in choices)
                if not messagebox.askyesno('31명 승인 업무 공동 운영',
                        f'다음 {len(ids)}건을 한 번 확인하고 2명씩 실제 모델을 실행합니다.\n'
                        + preview + '\n총괄 AI 검토 뒤에도 모든 결과는 소유자 승인 대기입니다. '
                        '개별 업무 자동 재실행·자동 결제·자동 외부 게시 없음. 시작할까요?',
                        parent=self.root):
                    return
                cid=campaigns.create_campaign(self.store,expected_task_ids=ids)
            self._start(lambda:campaigns.execute_campaign(
                self.store,cid,cancel=self.cancel,max_parallel=2),after='company_campaign')
        except (PermissionError,ValueError,RuntimeError) as exc:
            self._say('AI 연속 운영 시작 오류: '+str(exc))

    def run_approved_parallel(self):
        """Physical owner confirmation and exact pinned two-task preview."""
        if self.worker and self.worker.is_alive():
            self._say('이미 실행 중인 AI 작업이 있어 병렬 실행을 시작하지 않습니다.')
            return
        try:
            preview = ops.list_approved_parallel_candidates(self.store)
            if len(preview) != 2:
                self._say('서로 다른 직원 AI와 승인 지시·모델이 연결된 업무 2건이 필요합니다.')
                return
            ids = tuple(int(x['task_id']) for x in preview)
            employees = tuple(int(x['employee_id']) for x in preview)
            details = '\n'.join(f"#{x['task_id']} · 담당 AI #{x['employee_id']} · {str(x['title'])[:45]}"
                                for x in preview)
            if not messagebox.askyesno(
                    '승인 직원 AI 병렬 실행',
                    '다음 두 승인 업무를 각기 다른 AI 직원이 동시에 실행합니다.\n'
                    + details + '\n'
                    '직원 결과는 저장되고 총괄 AI가 순서대로 검토하지만 '
                    '결과물 승인·업무 완료는 관리자가 직접 합니다.\n'
                    '하나라도 실패하면 다른 직원 실행도 취소 요청합니다. 시작할까요?',
                    parent=self.root):
                return
            self._start(lambda: ops.execute_approved_parallel_cycle(
                self.store, expected_task_ids=ids, expected_employee_ids=employees,
                cancel=self.cancel),
                after='chief_parallel')
        except (ValueError, PermissionError) as exc:
            self._say('병렬 직원 실행 준비 실패: ' + str(exc))

    def run_approved_queue(self):
        """Show exact owner-confirmed IDs before bounded subprocess execution."""
        if self.worker and self.worker.is_alive():
            self._say('진행 중인 AI 실행이 있어 자동 대기열을 시작하지 않습니다.')
            return
        try:
            candidates = ops.list_approved_chief_queue_candidates(self.store, limit=3)
            if not candidates:
                self._say('실행 가능한 소유자 승인·직원 모델 연결 업무가 없습니다.')
                return
            ids = tuple(int(row['task_id']) for row in candidates)
            listing = '\n'.join(f"#{row['task_id']} {str(row['title'])[:65]}"
                                  for row in candidates)
            if not messagebox.askyesno(
                '승인 업무 자동 회수',
                f'다음 {len(candidates)}개 승인 업무만 실행합니다.\n{listing}\n'
                '직원 실행과 총괄 AI 검토를 진행하지만 보고서 수락·결과 승인·업무 완료는 하지 않습니다.\n'
                '대상이 변경되면 새 업무 실행을 중단합니다. 시작할까요?',
                parent=self.root):
                return
            self._start(lambda: ops.execute_approved_chief_queue(
                self.store, limit=3, cancel=self.cancel,
                expected_task_ids=ids), after='chief_queue')
        except (ValueError, PermissionError) as exc:
            self._say('승인 업무 대기열 시작 실패: ' + str(exc))

    def ask_chief_order(self):
        """Request a real chief-model draft, NEVER dispatch or approve it automatically."""
        try:
            task_id=self.selected_task()
            if self.store.read_chief_task_order(task_id) is not None:
                raise ValueError('이미 승인된 총괄 AI 지시가 저장되어 있습니다.')
            objective=simpledialog.askstring(
                '총괄 AI → 직원 업무 지휘',
                '총괄 AI에게 지시할 업무 목표를 입력하세요.\n'
                '실제 AI 모델의 초안은 관리자가 확인 후 승인해야 전송됩니다.',
                parent=self.root)
            if objective is None:
                return
            if not objective.strip():
                raise ValueError('총괄 AI 목표를 입력하세요.')
            self._start(lambda:ops.draft_chief_order(
                self.store,task_id,objective,cancel=self.cancel),after='chief_order')
        except (ValueError, PermissionError) as exc:
            self._say('총괄 AI 지시 요청 실패: '+str(exc))

    def review_chief_order(self, result):
        """Human review dialog; no worker execution until explicit later click."""
        task_id=int(result['task_id'])
        instruction=str(result['instruction'])
        dialog=tk.Toplevel(self.parent)
        dialog.title('AIWACK | 총괄 AI 지시 초안 · 소유자 승인')
        dialog.geometry('780x470')
        dialog.configure(bg=BG)
        self._label(dialog,f'업무 #{task_id} · 실제 총괄 AI 답변 · 아직 업무 실행 아님',
                    bg=BG,size=12,bold=True).pack(fill='x',padx=15,pady=(13,8))
        actions=tk.Frame(dialog,bg=BG)
        actions.pack(side='bottom',fill='x',padx=15,pady=12)
        text=tk.Text(dialog,wrap='word',font=(FONT,11),bg='#f6f8fc',fg='#152134',
                     relief='flat',padx=12,pady=12)
        text.pack(fill='both',expand=True,padx=15,pady=4)
        text.insert('1.0',instruction)
        text.configure(state='disabled')
        def approve():
            try:
                order_id=ops.approve_chief_order(self.store,task_id,instruction)
                dialog.destroy()
                self.refresh()
                self._say(f'총괄 AI 지시 #{order_id} 승인됨 · 직원 실행은 별도 클릭이 필요합니다.')
            except (ValueError,PermissionError) as exc:
                self._say('총괄 AI 지시 승인 실패: '+str(exc))
        self._action(actions,'확인 후 지시 승인',approve,strong=True,compact=True)
        def approve_and_automate():
            """One owner click authorizes bounded staff -> chief review.

            Human review remains mandatory for both report and artifact.
            """
            if self.worker and self.worker.is_alive():
                self._say('다른 AI 실행이 끝난 후 지시 승인과 자동 실행을 요청하세요.')
                return
            try:
                order_id=ops.approve_chief_order(self.store,task_id,instruction)
                dialog.destroy()
                self.refresh()
                self._say(f'총괄 지시 #{order_id} 승인 · 직원 실행→총괄 회수 자동 진행 중')
                self._start(lambda:ops.execute_approved_chief_cycle(
                    self.store,task_id,cancel=self.cancel),after='chief_report')
            except (ValueError,PermissionError) as exc:
                self._say('자동 진행 승인 실패: '+str(exc))
        self._action(actions,'승인 후 직원·총괄 자동 회수',
                     approve_and_automate,strong=True,compact=True)
        self._action(actions,'기각하고 닫기',dialog.destroy,danger=True,compact=True)
        return dialog

    def ask_chief(self):
        self._start(lambda: ops.chief_brief(self.store, cancel=self.cancel),after='chief')

    def _proposal_id(self):
        pick=self.proposal_list.selection()
        if not pick:
            raise ValueError('제안 한 건을 먼저 선택하세요.')
        return int(pick[0])

    def _proposal_row(self):
        proposal_id=self._proposal_id()
        row=next((p for p in ops.planning_proposals(self.store) if p['id']==proposal_id),None)
        if row is None:
            raise ValueError('제안이 변경됐습니다. 새로고침하세요.')
        return row

    def open_proposal(self):
        try:
            row=self._proposal_row()
            a=row['analysis'] or {}
            detail=(f"업무 제안 #{row['id']}\n원본: {row['source_kind']} #{row['source_id']}\n"
                    f"작성 출처: {row['origin']} · 검수 상태: {row['status']}\n"
                    f"적합도: {a.get('feasibility','평가 없음')} · 점수: {a.get('score','—')}\n"
                    f"\n{row['title']}\n\n{row['description']}\n\n"
                    '실제 AI 직원의 작업은 제안 승인 후에도 별도로 시작해야 합니다.')
            self._text_dialog('업무 기획 초안 · 실행 아님',detail)
        except (ValueError,PermissionError) as exc:
            self._say(str(exc))

    def create_goal(self):
        try:
            goal_id=ops.create_active_company_goal(self.store,self.goal_title.get())
            self.goal_title.set('')
            self.refresh()
            self.set_view('planning')
            self._say(f'회사 목표 #{goal_id} 활성화됨 · 제안 검색으로 실제 업무 초안을 생성할 수 있습니다.')
        except (ValueError,PermissionError) as exc:
            self._say('회사 목표 등록 실패: '+str(exc))

    def scan_proposals(self):
        try:
            result=ops.scan_planning_proposals(self.store)
            self.refresh()
            self.set_view('planning')
            self._say(f"로컬 자료 기반 제안 {len(result['created_ids'])}개 생성 · AI 호출 없음 · 승인 대기 {result['pending_count']}개")
        except (ValueError,PermissionError) as exc:
            self._say('제안 스캔 실패: '+str(exc))

    def refine_proposal(self):
        try:
            proposal_id=self._proposal_id()
        except ValueError as exc:
            self._say(str(exc))
            return
        self._start(lambda:ops.refine_planning_proposal(self.store,proposal_id,cancel=self.cancel),
                    after='planning')

    def approve_proposal(self):
        try:
            row=self._proposal_row()
            if row['status']!='pending':
                raise ValueError('승인 대기 제안만 선택할 수 있습니다.')
            if not messagebox.askyesno('업무 생성 승인',
                    '제안을 실제 업무로 등록합니까?\n모델 자동 실행은 하지 않습니다.\n\n'+row['title'],parent=self.root):
                return
            task_id=ops.approve_planning_proposal(self.store,int(row['id']))
            self.refresh()
            if task_id is None:
                self._say('원본 자료가 변경되어 제안 승인되지 않았습니다.')
            else:
                self.set_view('work')
                self.work_jobs.selection_set(str(task_id))
                self._say(f'소유자 승인 · 실제 업무 #{task_id} 생성 · 모델 실행은 아직 아닙니다.')
        except (ValueError,PermissionError) as exc:
            self._say('제안 승인 실패: '+str(exc))

    def reject_proposal(self):
        try:
            row=self._proposal_row()
            if not messagebox.askyesno('제안 기각','선택한 업무 제안을 기각합니까?',parent=self.root):
                return
            ops.reject_planning_proposal(self.store,int(row['id']))
            self.refresh()
            self._say('제안이 기각됐습니다. 실제 업무는 생성되지 않았습니다.')
        except (ValueError,PermissionError) as exc:
            self._say('제안 기각 실패: '+str(exc))

    def request_chief_report(self):
        """Real chief subprocess is launched only on explicit owner click."""
        try:
            artifact_id=self._selected_artifact()
            existing=self.store.find_chief_task_report(artifact_id)
            if existing is not None:
                self.open_chief_report(artifact_id)
                return
            if not messagebox.askyesno('총괄 AI 회수 검토',
                    '선택 결과물을 총괄 AI 로컬 모델에 보내 검토 보고서를 생성합니까?\n'
                    '모델 실행 후에도 관리자 승인 없이 완료되거나 판매되지 않습니다.', parent=self.root):
                return
            self._start(lambda:ops.collect_chief_review(self.store,artifact_id,cancel=self.cancel),
                        after='chief_report')
        except (ValueError,PermissionError) as exc:
            self._say('총괄 회수 검토 시작 실패: '+str(exc))

    def recover_interrupted_queue(self):
        """Only an explicit owner click may launch bounded chief-only recovery."""
        if self.worker and self.worker.is_alive():
            self._say('실행 중인 AI가 있으므로 중단 검토 대기열을 시작하지 않습니다.')
            return
        try:
            candidates=ops.list_interrupted_chief_reviews(self.store,limit=3)
            if not candidates:
                self._say('복구 가능한 미검수 직원 결과물이 없습니다.')
                return
            listing='\n'.join(
                f"#{item['task_id']} {str(item['title'])[:70]}"
                for item in candidates)
            if not messagebox.askyesno('중단된 총괄 검토 일괄 복구',
                    f'기존 직원 결과물 {len(candidates)}건에 총괄 AI 검토만 실행합니다.\n'
                    + listing + '\n직원 중복 실행·자동 승인·업무 완료는 하지 않습니다.\n'
                    + '실패 시 다음 업무는 시작하지 않습니다. 진행합니까?',
                    parent=self.root):
                return
            # Pass exactly the IDs the owner confirmed on the GUI.
            approved_ids=tuple(int(item['task_id']) for item in candidates)
            self._start(lambda:ops.recover_interrupted_chief_review_queue(
                self.store,limit=3,cancel=self.cancel,
                expected_task_ids=approved_ids),after='chief_recovery_queue')
        except (ValueError,PermissionError) as exc:
            self._say('총괄 검토 일괄 복구 실패: '+str(exc))

    def recover_interrupted_review(self):
        """Physical owner request; only recover chief review for persisted staff art."""
        try:
            artifact_id = self._selected_artifact()
            artifact = self.store.read_task_artifact(artifact_id)
            task_id = int(artifact['task_id'])
            if not messagebox.askyesno('중단된 총괄 검토 복구',
                    '저장된 직원 결과물로 총괄 AI 검토만 재개합니까?\n'
                    '직원 AI는 재실행하지 않으며 결과물 승인·업무 완료·외부 작업은 하지 않습니다.',
                    parent=self.root):
                return
            # Existing worker/owner session lock disallows concurrent requests.
            self._start(lambda: ops.recover_interrupted_chief_review(
                self.store, task_id, cancel=self.cancel), after='chief_report')
        except (ValueError, PermissionError) as exc:
            self._say('중단 검토 복구 실패: ' + str(exc))

    def open_chief_report(self, artifact_id=None):
        """Display a persisted chief report and require a physical owner decision."""
        try:
            if artifact_id is None:
                artifact_id=self._selected_artifact()
            report=self.store.find_chief_task_report(int(artifact_id))
            if report is None:
                raise ValueError('실제 총괄 AI 회수 보고서가 없습니다. 먼저 회수 검토를 실행하세요.')
            dialog=tk.Toplevel(self.root)
            dialog.title('AIWACK | 총괄 AI 회수 보고서 · 소유자 검토')
            # Place the actual owner decision controls in the center of the
            # application instead of unexpectedly opening at desktop (0, 0).
            self.root.update_idletasks()
            x=max(0,min(self.root.winfo_screenwidth()-790,
                        self.root.winfo_rootx()+(self.root.winfo_width()-790)//2))
            y=max(0,min(self.root.winfo_screenheight()-490,
                        self.root.winfo_rooty()+(self.root.winfo_height()-490)//2))
            dialog.geometry(f'790x490+{x}+{y}')
            dialog.configure(bg=BG)
            dialog.transient(self.root)
            dialog.lift()
            self._label(dialog,
                f"결과물 #{artifact_id} · 총괄 보고서 #{report['id']} · 상태: {report['owner_decision']}",
                bg=BG,size=11,bold=True).pack(fill='x',padx=15,pady=(10,6))
            # Reserve room for actual visible user approval buttons BEFORE
            # the expandable text area claims all Tk packer height.
            controls=tk.Frame(dialog,bg=BG)
            controls.pack(side='bottom',fill='x',padx=15,pady=(2,12))
            area=tk.Text(dialog,wrap='word',font=(FONT,10),bg='#f6f8fc',fg='#152134',
                         relief='flat',padx=12,pady=12)
            area.pack(fill='both',expand=True,padx=15,pady=5)
            area.insert('1.0',report['body'])
            area.configure(state='disabled')
            if report['owner_decision']=='pending':
                def decide(decision):
                    title='수락' if decision=='accepted' else '반려'
                    if not messagebox.askyesno('총괄 보고서 관리자 검토',
                         f'실제 총괄 AI 검토 보고서를 {title}하겠습니까?\n업무 완료는 자동으로 되지 않습니다.',
                         parent=dialog):
                        return
                    try:
                        ops.review_chief_feedback(self.store,int(report['id']),decision)
                        dialog.destroy()
                        self.refresh()
                        self._say(f"총괄 AI 보고서 #{report['id']} {title}됨 · 결과물 승인/완료는 별도 단계")
                    except (ValueError,PermissionError) as exc:
                        self._say('총괄 보고서 검토 실패: '+str(exc))
                self._action(controls,'총괄 보고서 수락',lambda:decide('accepted'),
                             strong=True,compact=True)
                self._action(controls,'총괄 보고서 반려',lambda:decide('rejected'),
                             danger=True,compact=True)
            self._action(controls,'닫기',dialog.destroy,compact=True)
            return dialog
        except (ValueError,PermissionError) as exc:
            self._say('총괄 보고서 조회 실패: '+str(exc))
            return None

    def _selected_artifact(self):
        picked = self.artifact_list.selection()
        if not picked:
            raise ValueError('결과 목록에서 검수할 결과물 한 건을 선택하세요.')
        return int(picked[0])

    def _text_dialog(self, title, body):
        dialog = tk.Toplevel(self.root)
        dialog.title('AIWACK | '+title)
        dialog.geometry('790x510')
        area = tk.Text(dialog, wrap='word', font=(FONT, 10), bg=CARD, fg=INK,
                       relief='flat', padx=14, pady=14)
        area.pack(fill='both', expand=True, padx=10, pady=10)
        area.insert('1.0', body)
        area.configure(state='disabled')

    def open_result(self):
        try:
            artifact_id = self._selected_artifact()
            artifact = self.store.read_task_artifact(artifact_id)
            text = f"결과물 #{artifact_id}  /  {artifact['title']}\n" + '-'*52 + '\n' + artifact['body']
        except ValueError:
            text = self.latest_output
        self._text_dialog('실제 AI 결과 및 검수',text)

    def quality_check_result(self):
        from desktop import company_deliverables as deliver
        try:
            aid=self._selected_artifact()
            report=deliver.check_quality(self.store,aid)
            issues=('\n'.join(report['warnings']) if report['warnings'] else '기계적 무결성 검사 경고 없음')
            self._text_dialog('결과물 기계적 품질 검사',
                f"#{aid} / SHA256 일치: {report['integrity_ok']} / "
                f"본문 길이 {report['body_chars']}자\n"
                + issues + '\n내용 사실성·법적 적합성·상업적 품질은 관리자 직접 검토가 필요합니다.')
        except (ValueError,PermissionError) as exc:
            self._say('기계적 품질 검사 실패: '+str(exc))

    def export_result(self):
        from desktop import company_deliverables as deliver
        try:
            aid=self._selected_artifact()
            if not messagebox.askyesno('승인 결과 파일로 저장',
                    f'관리자가 검수 승인한 결과물 #{aid}만 컴퓨터 AIWACK 데이터 폴더에 '
                    'Markdown 파일로 저장합니다.\n외부 게시·판매·덮어쓰기는 하지 않습니다. 진행할까요?',
                    parent=self.root):
                return
            report=deliver.export_approved(self.store,aid)
            self._say(f"승인 결과 #{aid} 저장 완료: {report['path']}")
        except (ValueError,PermissionError,FileExistsError,OSError,RuntimeError) as exc:
            self._say('파일 내보내기 오류: '+str(exc))

    def _review(self, decision):
        try:
            artifact_id = self._selected_artifact()
            if not messagebox.askyesno('결과물 검수', f'결과물 #{artifact_id}을(를) {decision} 처리합니까?\n업무 완료는 자동 처리하지 않습니다.', parent=self.root):
                return
            comment = ''
            if decision != 'approved':
                comment = simpledialog.askstring('검수 의견', '수정하거나 반려할 이유를 적으세요.', parent=self.root)
                if comment is None:
                    return
            self.store.review_task_artifact(artifact_id, decision, comment)
            self.refresh()
            self._say(f'결과물 #{artifact_id} 검수 기록: {decision}')
        except (ValueError, PermissionError) as exc:
            self._say('검수 실패: '+str(exc))

    def finish_reviewed(self):
        try:
            artifact_id=self._selected_artifact()
            artifact=self.store.read_task_artifact(artifact_id)
            if artifact['review_status'] != 'approved':
                raise ValueError('먼저 결과물을 검토하고 승인해야 완료할 수 있습니다.')
            if not messagebox.askyesno('업무 완료 확인',
                    f'승인된 결과물 #{artifact_id}을 근거로 업무를 완료 처리할까요?\n'
                    '완료 기록은 감사 이력에 저장됩니다.',parent=self.root):
                return
            tid=ops.finalize_approved_artifact(self.store,artifact_id)
            self.refresh()
            self._say(f'소유자 최종 승인 · 업무 #{tid} 완료 · 매출·판매는 발생하지 않았습니다.')
        except (ValueError,PermissionError) as exc:
            self._say('업무 완료 처리 실패: '+str(exc))

    def approve_selected(self):
        self._review('approved')

    def request_changes(self):
        self._review('changes_requested')

    def reject_selected(self):
        self._review('rejected')

    def stop(self):
        if not messagebox.askyesno('회사 비상 정지',
                '회사 AI 작업의 신규 실행을 차단하고 현재 운영센터 작업에 취소를 요청합니다. 계속하시겠습니까?',parent=self.root):
            return
        self.cancel.set()
        try:
            self.store.emergency_stop_local(True, '운영센터에서 관리자가 비상 중지')
            self.refresh()
            self._say('비상 정지 활성 · 해제는 관리자 안전 화면에서 명시적으로 수행하세요.')
        except (ValueError, PermissionError) as exc:
            self._say('비상 정지 실패: '+str(exc))


def mount(app, parent):
    app.company_office = CompanyOffice(app, parent)
    return app.company_office
