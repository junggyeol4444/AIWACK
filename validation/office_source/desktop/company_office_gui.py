"""A functional first-screen AI company operations center, not an empty demo dashboard."""
from __future__ import annotations
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from desktop import company_operations as ops

BG='#101d30'; PANEL='#1d3048'; SUB='#aec5de'; WHITE='#f6f9ff'; ACCENT='#377ee5'


class CompanyOffice:
    def __init__(self, app, parent):
        self.app=app
        self.root=app.root
        self.store=app.store
        self.parent=parent
        self.pending=queue.Queue()
        self.cancel=threading.Event()
        self.worker=None
        self.generation=app._session_generation
        self.status=tk.StringVar(value='회사 업무를 불러오는 중')
        self.title=tk.StringVar()
        self.cards={}
        self._draw()
        self.refresh()

    def label(self,parent,text,*,size=10,bold=False,fg=WHITE,bg=PANEL):
        return tk.Label(parent,text=text,font=('Malgun Gothic',size,'bold' if bold else 'normal'),
                        bg=bg,fg=fg,anchor='w')

    def button(self,parent,text,action,*,strong=False):
        b=tk.Button(parent,text=text,command=action,fg=WHITE,bg=ACCENT if strong else '#2e4b70',
                    activebackground='#4b83c6',padx=11,pady=7,relief='flat',font=('Malgun Gothic',10,'bold'))
        b.pack(side='left',padx=(0,8),pady=4)
        return b

    def _draw(self):
        self.parent.configure(bg=BG)
        header=tk.Frame(self.parent,bg=BG)
        header.pack(fill='x',padx=8,pady=(0,10))
        self.label(header,'AI 회사 운영센터',size=22,bold=True,bg=BG).pack(anchor='w')
        self.label(header,'총괄 AI · 부서 · 직원 AI · 실제 업무 · 실행 기록   |   미배정 모델은 실행하지 않습니다',
                   fg=SUB,bg=BG).pack(anchor='w',pady=(3,0))
        kpis=tk.Frame(self.parent,bg=BG)
        kpis.pack(fill='x',padx=8,pady=(0,9))
        for col,key,title in ((0,'departments','부서'),(1,'employees','AI 직원'),
                              (2,'tasks','업무'),(3,'completed','완료')):
            frame=tk.Frame(kpis,bg=PANEL,padx=16,pady=11,highlightbackground='#38577b',highlightthickness=1)
            frame.grid(row=0,column=col,sticky='nsew',padx=4)
            kpis.grid_columnconfigure(col,weight=1)
            self.label(frame,title,fg=SUB).pack(anchor='w')
            var=tk.StringVar(value='—')
            self.label(frame,'',size=23,bold=True).config(textvariable=var)
            self.label(frame,'',size=23,bold=True).pack_forget() if False else None
            tk.Label(frame,textvariable=var,font=('Malgun Gothic',22,'bold'),fg=WHITE,bg=PANEL).pack(anchor='w')
            self.cards[key]=var
        middle=tk.PanedWindow(self.parent,orient='horizontal',bg=BG,sashwidth=7,sashrelief='flat')
        middle.pack(fill='both',expand=True,padx=8,pady=(0,7))
        left=tk.Frame(middle,bg=PANEL,padx=12,pady=10)
        right=tk.Frame(middle,bg=PANEL,padx=12,pady=10)
        middle.add(left,stretch='always',minsize=285)
        middle.add(right,stretch='always',minsize=365)
        self.label(left,'조직 / AI 직원',size=14,bold=True).pack(anchor='w',pady=(0,8))
        self.chief_label=tk.StringVar(value='총괄 AI 확인 중')
        tk.Label(left,textvariable=self.chief_label,bg='#284464',fg='#e4f1ff',
                 anchor='w',wraplength=380,justify='left',padx=10,pady=8).pack(fill='x',pady=(0,8))
        self.staff=ttk.Treeview(left,columns=('team','model','state'),show='headings',height=8)
        for key,label,width in [('team','직원 / 부서',190),('model','모델',145),('state','상태',95)]:
            self.staff.heading(key,text=label)
            self.staff.column(key,width=width,stretch=key!='state')
        self.staff.pack(fill='both',expand=True)
        self.label(right,'현재 회사 업무',size=14,bold=True).pack(anchor='w',pady=(0,8))
        self.jobs=ttk.Treeview(right,columns=('job','owner','state'),show='headings',height=8)
        for key,label,width in [('job','업무',205),('owner','담당 AI',140),('state','상태',100)]:
            self.jobs.heading(key,text=label)
            self.jobs.column(key,width=width,stretch=key!='state')
        self.jobs.pack(fill='both',expand=True)
        editor=tk.Frame(right,bg=PANEL)
        editor.pack(fill='x',pady=(7,0))
        self.task_entry=tk.Entry(editor,textvariable=self.title,font=('Malgun Gothic',11))
        self.task_entry.pack(side='left',fill='x',expand=True,padx=(0,7),ipady=6)
        self.button(editor,'업무 등록',self.create, strong=True)
        controls=tk.Frame(self.parent,bg=BG)
        controls.pack(fill='x',padx=10,pady=4)
        self.button(controls,'새로고침',self.refresh)
        self.button(controls,'담당 AI 배정',self.assign)
        self.button(controls,'선택 업무 실행',self.run_selected,strong=True)
        self.button(controls,'최대 3개 실행',self.run_batch)
        self.button(controls,'총괄 AI 진단',self.ask_chief)
        self.button(controls,'비상 중지',self.stop)
        self.label(self.parent,'실제 GGUF 실행은 직원에게 모델을 배정해야 합니다. 결과는 검수 대기이며 자동 완료·실매출이 아닙니다.',
                   bg=BG,fg='#eebd83').pack(fill='x',padx=13)
        feedback=tk.Frame(self.parent,bg=BG)
        feedback.pack(fill='both',expand=False,padx=10,pady=(4,0))
        self.label(feedback,'',bg=BG,fg='#88dbaf').config(textvariable=self.status)
        tk.Label(feedback,textvariable=self.status,bg=BG,fg='#88dbaf',anchor='w',wraplength=925).pack(fill='x')
        self.report=tk.Text(feedback,height=3,bg='#182940',fg=WHITE,wrap='word',font=('Malgun Gothic',10))
        self.report.pack(fill='x',pady=(3,0))
        self.report.insert('1.0','총괄 AI 및 직원 AI의 실제 실행 결과가 여기에 표시됩니다. 가상 직원 응답을 만들지 않습니다.')
        self.report.configure(state='disabled')

    def _say(self, message):
        self.status.set(str(message)[:350])

    def _show_output(self,message):
        self.report.configure(state='normal')
        self.report.delete('1.0','end')
        self.report.insert('1.0',str(message)[:5000])
        self.report.configure(state='disabled')

    def refresh(self):
        try:
            data=ops.company_snapshot(self.store)
            self.cards['departments'].set(str(len(data['departments'])))
            self.cards['employees'].set(str(len(data['team'])))
            self.cards['tasks'].set(str(data['total_tasks']))
            self.cards['completed'].set(str(data['completed']))
            chief=data['chief']
            self.chief_label.set('총괄 AI: '+(chief['display_name'] if chief else '미지정')+
                                 ('  | 모델: '+str(chief.get('model_name') or '미배정') if chief else '')+
                                 ('  | 비상 정지 적용 중' if data['emergency'] else ''))
            self.staff.delete(*self.staff.get_children())
            for row in data['team']:
                self.staff.insert('','end',iid='employee-'+str(row['id']),
                    values=(row['name']+' / '+row['department'],row['model'],row['lifecycle']))
            selection=self.jobs.selection()
            self.jobs.delete(*self.jobs.get_children())
            for row in data['tasks']:
                self.jobs.insert('','end',iid=str(row['id']),
                    values=(row['title'],row['assignee'],row['status']))
            if selection and self.jobs.exists(selection[0]):self.jobs.selection_set(selection[0])
            self._say('회사 실데이터 새로고침 완료 · 미배정 모델은 자동으로 실행하지 않습니다.')
        except (ValueError,PermissionError,RuntimeError) as exc:
            self._say('조회 실패: '+str(exc))

    def selected_task(self):
        picked=self.jobs.selection()
        if not picked:
            raise ValueError('먼저 업무 목록에서 한 건을 클릭하세요.')
        return int(picked[0])

    def create(self):
        try:
            task_id=ops.create_task(self.store,self.title.get())
            self.title.set('')
            self.refresh()
            self.jobs.selection_set(str(task_id))
            self.jobs.see(str(task_id))
            self._say(f'실제 SQLite 업무 #{task_id} 등록 완료 · 아직 AI가 수행한 것은 아닙니다.')
        except (ValueError,PermissionError) as exc:self._say(str(exc))

    def assign(self):
        try:
            info=ops.assign_task(self.store,self.selected_task())
            self.refresh()
            self._say('담당 직원 AI 배정: '+str(info['employee_name'])+' · 아직 모델 미실행')
        except (ValueError,PermissionError) as exc:self._say(str(exc))

    def _start(self,job):
        if self.worker and self.worker.is_alive():
            self._say('AI 작업이 실행 중입니다. 중복 실행하지 않습니다.')
            return
        self.cancel.clear()
        self._say('실제 로컬 AI 실행 중… 완료 후 결과물 감사 기록을 남깁니다.')
        def work():
            try: self.pending.put(('result',job()))
            except Exception as exc: self.pending.put(('error',type(exc).__name__+': '+str(exc)))
        self.worker=threading.Thread(target=work,daemon=True,name='AIWACK-office-user-request')
        self.worker.start()
        self.root.after(200,self._poll)

    def _poll(self):
        if self.generation!=self.app._session_generation or self.app.main_frame is None:
            self.cancel.set();return
        try: kind,result=self.pending.get_nowait()
        except queue.Empty:
            if self.worker and self.worker.is_alive():self.root.after(200,self._poll)
            return
        if kind=='error':
            self._say('실제 작업 실패: '+str(result))
            self._show_output(str(result))
        else:
            self._show_output(result)
            self._say('실제 실행 결과 수신 · 승인 전 초안/검수 대기')
        self.refresh()
        self._say('AI 실행 완료(초안). 저장된 결과물은 기존 업무 결과물·검수 화면에서 확인하세요.'
                  if kind=='result' else '실제 작업 실패: '+str(result))

    def run_selected(self):
        try: task=self.selected_task()
        except ValueError as exc:self._say(str(exc));return
        self._start(lambda:ops.execute_task(self.store,task,cancel=self.cancel))

    def run_batch(self):
        self._start(lambda:ops.execute_batch(self.store,max_tasks=3,cancel=self.cancel))

    def ask_chief(self):
        self._start(lambda:ops.chief_brief(self.store,cancel=self.cancel))

    def stop(self):
        self.cancel.set()
        try:
            state=self.store.emergency_stop_local(True,'관리자가 회사 운영센터에서 비상 중지')
            self._say('비상 중지 저장됨 · 로컬 실행 중단 요청 · 외부 도구까지 강제 차단하는 것은 아닙니다.')
            self.refresh()
            self._say('비상 정지 활성화. 해제는 기존 안전·관리 화면에서 명시적으로 진행하십시오.')
        except (PermissionError,ValueError) as exc:self._say('비상 중지 실패: '+str(exc))


def mount(app,parent):
    app.company_office=CompanyOffice(app,parent)
    return app.company_office
