"""Stages81-83 owner-only offline descriptive diagnostics & improvement DRAFTS."""
import json
import tkinter as tk
from tkinter import ttk
from desktop.storage import LocalStore

class DiagnosticPanel(ttk.Frame):
    def __init__(self,master,store):
        super().__init__(master,padding=10)
        self.store=store
        self.diagnostic=tk.StringVar(value='VERIFIED_REVENUE_MISSING:0')
        self.proposal=tk.StringVar(value='improvement_mock001')
        self.note=tk.StringVar(value='Local administrator review only')
        self.message=tk.StringVar(value='관리자 인증 필요 — 로컬 진단; 실제 매출·고객 분석 아님')
        ttk.Label(self,text='81~83 | 로컬 데이터 현황 · 가정 경고 · 비실행 개선 초안',font=('TkDefaultFont',11,'bold')).pack(anchor='w',pady=5)
        row=ttk.Frame(self);row.pack(fill='x')
        ttk.Button(row,text='직원·부서·사업 기록 현황',command=self.performance).pack(side='left')
        ttk.Button(row,text='로컬 위험 징후',command=self.diagnostics).pack(side='left')
        ttk.Button(row,text='개선 초안 이력',command=self.history).pack(side='left')
        for label,var in [('진단 키',self.diagnostic),('초안 키',self.proposal),('소유자 메모',self.note)]:
            r=ttk.Frame(self);r.pack(fill='x',pady=2)
            ttk.Label(r,text=label,width=14).pack(side='left')
            ttk.Entry(r,textvariable=var).pack(side='left',fill='x',expand=True)
        ttk.Button(self,text='개선 업무 초안 저장 (실제 업무 생성·실행 안 함)',command=self.create_draft).pack(anchor='w',pady=4)
        ttk.Label(self,textvariable=self.message,foreground='#9b5400').pack(anchor='w')
        self.output=tk.Text(self,width=90,height=18,state='disabled');self.output.pack(fill='both',expand=True)
    def _run(self,fn):
        try:
            self.store.require_permission('company:manage')
            result=fn()
            self.message.set('로컬 조회/초안 성공; 검증된 실제 성과 데이터 없음')
            self.output.configure(state='normal');self.output.delete('1.0','end')
            self.output.insert('end',json.dumps(result,ensure_ascii=False,indent=2,default=str)[:15000]);self.output.configure(state='disabled')
            return result
        except (PermissionError,ValueError,TypeError) as exc:
            self.message.set('접근 거부/검사 실패: '+str(exc))
            return None
    def performance(self):return self._run(self.store.local_company_performance_report)
    def diagnostics(self):return self._run(self.store.local_company_diagnostics)
    def create_draft(self):return self._run(lambda:self.store.propose_local_improvement_draft(self.diagnostic.get(),self.proposal.get(),self.note.get()))
    def history(self):return self._run(self.store.local_improvement_draft_history)
    def clear(self):
        self.output.configure(state='normal');self.output.delete('1.0','end');self.output.configure(state='disabled')
        self.message.set('관리자 로그아웃 — 로컬 진단 접근 차단')

class Stage81_83OwnerWindow:
    def __init__(self,root=None,store=None):
        self.root=root if root is not None else tk.Tk()
        self.root.title('AIWACK 81~83 로컬 현황·가정 진단 — 실제 성과/매출 검증 아님')
        self.store=store if store is not None else LocalStore()
        bar=ttk.Frame(self.root,padding=7);bar.pack(fill='x')
        self.username=tk.StringVar();self.password=tk.StringVar()
        ttk.Label(bar,text='로컬 관리자').pack(side='left')
        ttk.Entry(bar,textvariable=self.username,width=18).pack(side='left')
        ttk.Entry(bar,textvariable=self.password,show='*',width=18).pack(side='left')
        ttk.Button(bar,text='로그인',command=self.login).pack(side='left')
        ttk.Button(bar,text='로그아웃',command=self.logout).pack(side='left')
        self.panel=DiagnosticPanel(self.root,self.store);self.panel.pack(fill='both',expand=True)
    def login(self):
        try:
            self.store.login(self.username.get(),self.password.get())
            self.panel.message.set('로컬 관리자 인증 성공')
        except (PermissionError,ValueError) as exc:
            self.panel.message.set('로그인 실패: '+str(exc))
        finally:self.password.set('')
    def logout(self):
        self.store.logout();self.password.set('');self.panel.clear()

def main():Stage81_83OwnerWindow().root.mainloop()
if __name__=='__main__':main()
