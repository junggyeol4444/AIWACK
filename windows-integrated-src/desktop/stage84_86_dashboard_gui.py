"""Stage84-86 local owner GUI: planning-only, no background polls/external calls."""
import json
import tkinter as tk
from tkinter import ttk
from desktop.storage import LocalStore

class StaffModelDashboardPanel(ttk.Frame):
    def __init__(self,master,store):
        super().__init__(master,padding=10)
        self.store=store
        self.message=tk.StringVar(value='로컬 관리자 인증 필요 — 인력/모델의 실제 자동 운영 아님')
        self.vars={}
        ttk.Label(self,text='84~86 | 미실행 인력 배치·모델 변경 초안 / 수동 새로고침 대시보드',font=('TkDefaultFont',11,'bold')).pack(anchor='w',pady=5)
        for key,label,default in [('department','대상 부서 ID','1'),('employee','직원 ID(재배치 선택시)',''),
                                  ('staff_key','인력 계획 키','staffplan_local01'),('staff_kind','인력 계획 유형','CREATE_PROFILE_DRAFT'),
                                  ('model_id','등록 모델 ID','1'),('model_key','모델 계획 키','modelplan_local01'),
                                  ('model_kind','모델 검토 방식','OFFLINE_REVIEW_ONLY'),('note','관리자 메모','Offline review only')]:
            f=ttk.Frame(self);f.pack(fill='x',pady=2)
            ttk.Label(f,text=label,width=25).pack(side='left')
            var=tk.StringVar(value=default);self.vars[key]=var
            ttk.Entry(f,textvariable=var).pack(side='left',expand=True,fill='x')
        buttons=ttk.Frame(self);buttons.pack(fill='x',pady=6)
        for label,fn in [('인력 변경 초안',self.staff_draft),('모델 설정 비교',self.models),
                         ('모델 선택 초안',self.model_draft),('현황 새로고침',self.refresh),
                         ('초안 감사 이력',self.histories)]:
            ttk.Button(buttons,text=label,command=fn).pack(side='left')
        ttk.Label(self,textvariable=self.message,foreground='#9b5400',wraplength=750).pack(anchor='w')
        self.output=tk.Text(self,width=95,height=16,state='disabled');self.output.pack(fill='both',expand=True)
    def v(self,key):return self.vars[key].get()
    def _run(self,action):
        try:
            self.store.require_permission('company:manage')
            result=action()
            self.message.set('로컬 처리 완료. 실제 직원 생성/모델 실행/실시간 외부 모니터링 없음')
            self.output.configure(state='normal');self.output.delete('1.0','end')
            self.output.insert('end',json.dumps(result,ensure_ascii=False,indent=2,default=str)[:20000]);self.output.configure(state='disabled')
            return result
        except (PermissionError,TypeError,ValueError) as exc:
            self.message.set('접근 거부/유효성 검사: '+str(exc));return None
    def staff_draft(self):
        return self._run(lambda:self.store.create_local_staffing_draft(self.v('staff_key'),self.v('staff_kind'),int(self.v('department')),self.v('note'),int(self.v('employee')) if self.v('employee') else None))
    def models(self):return self._run(self.store.local_model_config_comparison)
    def model_draft(self):return self._run(lambda:self.store.create_local_model_switch_draft(self.v('model_key'),int(self.v('model_id')),self.v('model_kind'),self.v('note')))
    def refresh(self):return self._run(self.store.offline_company_dashboard_snapshot)
    def histories(self):return self._run(lambda:{'staffing':self.store.local_staffing_drafts(),'model':self.store.local_model_switch_drafts()})
    def clear(self):
        self.output.configure(state='normal');self.output.delete('1.0','end');self.output.configure(state='disabled')
        self.message.set('로그아웃: 소유자 전용 기록 차단')

class Stage84_86OwnerWindow:
    def __init__(self,root=None,store=None):
        self.root=root if root is not None else tk.Tk()
        self.root.title('AIWACK 84-86 로컬 관리자 개발용 대시보드 (실시간 성과 아님)')
        self.store=store if store is not None else LocalStore()
        bar=ttk.Frame(self.root,padding=7);bar.pack(fill='x')
        self.user=tk.StringVar();self.password=tk.StringVar()
        ttk.Entry(bar,textvariable=self.user,width=18).pack(side='left')
        ttk.Entry(bar,textvariable=self.password,show='*',width=18).pack(side='left')
        ttk.Button(bar,text='관리자 로그인',command=self.login).pack(side='left')
        ttk.Button(bar,text='로그아웃',command=self.logout).pack(side='left')
        self.panel=StaffModelDashboardPanel(self.root,self.store);self.panel.pack(fill='both',expand=True)
    def login(self):
        try:
            self.store.login(self.user.get(),self.password.get())
            self.panel.message.set('로컬 관리자 인증 완료')
        except (ValueError,PermissionError) as exc:
            self.panel.message.set('인증 실패: '+str(exc))
        finally:self.password.set('')
    def logout(self):
        self.store.logout();self.password.set('');self.panel.clear()
def main():Stage84_86OwnerWindow().root.mainloop()
if __name__=='__main__':main()
