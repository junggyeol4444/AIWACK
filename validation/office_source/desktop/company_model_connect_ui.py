"""Explicit user-facing LOCAL model registration; never auto-download or auto-start.

The only supported paths are validated absolute local paths. A registered model
is *not* proof that real LLM inference succeeded; probing calls the real adapter.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from desktop import company_operations as ops

BG = '#10192b'
FG = '#ecf3ff'
SECONDARY = '#a7bbd5'
EDIT_BG = '#f7f9fc'


class ConnectLocalModelDialog:
    def __init__(self, office):
        self.office = office
        self.window = tk.Toplevel(office.parent)
        self.window.title('AIWACK | 로컬 AI 모델 연결')
        office.model_dialog = self
        self.window.geometry('760x594')
        self.window.minsize(680, 570)
        self.window.configure(bg=BG)
        self.window.transient(office.root)
        self.window.protocol('WM_DELETE_WINDOW', self.window.destroy)
        self.employee = tk.StringVar()
        self.model_name = tk.StringVar(value='내 로컬 AI 모델')
        self.backend = tk.StringVar(value='llama_cpp')
        self.executable = tk.StringVar()
        self.gguf = tk.StringVar()
        self.tokens = tk.StringVar(value='128')
        self.feedback = tk.StringVar(value='실제 로컬 모델 경로를 입력하세요. 미설치 파일은 연결할 수 없습니다.')
        people = ops.eligible_model_employees(office.store)
        self.employee_ids = {f"{p['name']}  /  #{p['id']}": p['id'] for p in people}
        self._build()
        chosen = office.staff.selection()
        selected_id = int(chosen[0].split('-')[1]) if chosen else None
        for label, employee_id in self.employee_ids.items():
            if employee_id == selected_id:
                self.employee.set(label)
                break
        if not self.employee.get() and self.employee_ids:
            self.employee.set(next(iter(self.employee_ids)))
        self.window.lift()
        self.window.focus_force()

    def _build(self):
        wrapper = tk.Frame(self.window, bg=BG, padx=22, pady=10)
        wrapper.pack(fill='both', expand=True)
        tk.Label(wrapper, text='AI 직원에게 실제 로컬 모델 연결', bg=BG, fg=FG,
                 font=('Malgun Gothic', 17, 'bold')).pack(anchor='w')
        tk.Label(wrapper, text='GGUF는 PC에 존재해야 합니다. 연결만으로 AI가 실행되거나 업무를 완료하지 않습니다.',
                 bg=BG, fg=SECONDARY, font=('Malgun Gothic', 9)).pack(anchor='w', pady=(3, 8))
        self.employee_select = ttk.Combobox(wrapper, textvariable=self.employee,
                                            values=list(self.employee_ids), state='readonly', width=52)
        self._row(wrapper, '연결할 AI 직원', self.employee_select)
        self.name_entry = tk.Entry(wrapper, textvariable=self.model_name, bg=EDIT_BG, fg='#152134')
        self._row(wrapper, '모델 표시 이름', self.name_entry)
        self.backend_select = ttk.Combobox(wrapper, textvariable=self.backend,
                                           values=('llama_cpp', 'llamafile'), state='readonly')
        self._row(wrapper, '실행 방식', self.backend_select)
        executable = tk.Frame(wrapper, bg=BG)
        self.program_entry = tk.Entry(executable, textvariable=self.executable, bg=EDIT_BG, fg='#152134')
        self.program_entry.pack(side='left', fill='x', expand=True)
        tk.Button(executable, text='파일 선택', command=self.browse_executable).pack(side='right', padx=(8, 0))
        self._row(wrapper, '로컬 실행 파일 (.exe)', executable)
        model = tk.Frame(wrapper, bg=BG)
        self.gguf_entry = tk.Entry(model, textvariable=self.gguf, bg=EDIT_BG, fg='#152134')
        self.gguf_entry.pack(side='left', fill='x', expand=True)
        tk.Button(model, text='파일 선택', command=self.browse_model).pack(side='right', padx=(8, 0))
        self._row(wrapper, 'GGUF 경로 (llamafile은 선택)', model)
        self.tokens_entry = tk.Entry(wrapper, textvariable=self.tokens, bg=EDIT_BG, fg='#152134')
        self._row(wrapper, '최대 생성 토큰 (1~512)', self.tokens_entry)
        buttons = tk.Frame(wrapper, bg=BG)
        buttons.pack(fill='x', pady=(9, 6))
        self.bind_button = tk.Button(buttons, text='경로 검증 후 직원에게 배정',
                                    command=self.connect, bg='#477ded', fg='white',
                                    font=('Malgun Gothic', 10, 'bold'), padx=12, pady=8)
        self.bind_button.pack(side='left')
        self.probe_button = tk.Button(buttons, text='실제 모델 1회 호출 테스트',
                                     command=self.probe, padx=12, pady=8)
        self.probe_button.pack(side='left', padx=(8, 0))
        tk.Label(wrapper, textvariable=self.feedback, bg=BG, fg='#f9ca85',
                 wraplength=690, justify='left', anchor='w').pack(fill='x', pady=(5, 0))
        tk.Label(wrapper, text='테스트는 로컬 모델 실행파일을 실제로 호출하며, 응답이 없으면 실패입니다. '
                              '테스트 응답은 승인된 결과물이 아닙니다.',
                 bg=BG, fg=SECONDARY, wraplength=690, justify='left').pack(fill='x', pady=(4, 0))

    def _row(self, parent, label, widget):
        tk.Label(parent, text=label, bg=BG, fg=SECONDARY,
                 anchor='w').pack(fill='x', pady=(4, 1))
        widget.pack(fill='x', ipady=4 if isinstance(widget, tk.Entry) else 0)

    def browse_executable(self):
        chosen = filedialog.askopenfilename(parent=self.window, title='신뢰하는 로컬 모델 실행파일 선택',
                                           filetypes=[('Windows 실행 파일', '*.exe'), ('모든 파일', '*')])
        if chosen:
            self.executable.set(chosen)

    def browse_model(self):
        chosen = filedialog.askopenfilename(parent=self.window, title='내 PC의 GGUF 파일 선택',
                                           filetypes=[('GGUF 모델', '*.gguf'), ('모든 파일', '*')])
        if chosen:
            self.gguf.set(chosen)

    def _employee_id(self):
        if self.employee.get() not in self.employee_ids:
            raise ValueError('연결할 직원을 선택하세요.')
        return self.employee_ids[self.employee.get()]

    def connect(self):
        try:
            from desktop.model_runtime import ModelConfig
            config = ModelConfig(self.model_name.get().strip(), self.backend.get(),
                                 self.executable.get().strip(), self.gguf.get().strip(),
                                 int(self.tokens.get()))
            eid, mid = self._employee_id(), ops.connect_employee_model(self.office.store,
                                                                        self._employee_id(), config)
            self.feedback.set(f'실제 모델 경로 검증됨 · 직원 #{eid} 연결 · 모델 #{mid}. '
                              '추론 성공 여부는 아래 호출 테스트로 별도 확인하세요.')
            self.office.refresh()
        except (ValueError, PermissionError, RuntimeError, OSError) as exc:
            self.feedback.set('모델 연결 실패: ' + str(exc)[:300])

    def probe(self):
        try:
            eid = self._employee_id()
            if self.office.worker and self.office.worker.is_alive():
                self.feedback.set('다른 AI 모델이 실행 중입니다. 완료 후 다시 시도하세요.')
                return
            self.feedback.set('실제 로컬 모델을 별도 작업으로 실행 중입니다. 종료 시 감사 기록을 남깁니다.')
            self.office._start(lambda: ops.probe_employee_model(self.office.store, eid,
                                                                 cancel=self.office.cancel),
                               after='model_probe')
        except (ValueError, PermissionError) as exc:
            self.feedback.set('실제 모델 테스트 실패: ' + str(exc)[:250])
