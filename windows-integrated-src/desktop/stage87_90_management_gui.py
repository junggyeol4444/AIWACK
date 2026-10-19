"""87-90 local owner cockpit. Explicit emergency stop affects local queue/schedulers only."""
import json
import tkinter as tk
from tkinter import ttk
from desktop.storage import LocalStore

class ManagementPanel(ttk.Frame):
    def __init__(self,master,store):
        super().__init__(master,padding=8)
        self.store=store
        self.feedback=tk.StringVar(value='관리자 인증 필요. 모든 표는 로컬 기록입니다.')
        ttk.Label(self,text='87~90 | 로컬 조직·대화 건수·가정 회계·관리자 안전 정지',font=('TkDefaultFont',11,'bold')).pack(anchor='w')
        controls=ttk.Frame(self);controls.pack(fill='x')
        for text,action in [('조직·업무',lambda:self.view('organization')),('채팅·회의 기록 건수',lambda:self.view('communications')),
                            ('가정 사업·매출',lambda:self.view('commerce')),('승인·설정 상태',lambda:self.view('approvals')),
                            ('로컬 업무 긴급 정지',lambda:self.change_stop(True)),('정지 해제',lambda:self.change_stop(False))]:
            ttk.Button(controls,text=text,command=action).pack(side='left')
        self.reason=tk.StringVar(value='Owner reviewed local queue state')
        ttk.Entry(self,textvariable=self.reason,width=65).pack(anchor='w')
        ttk.Label(self,textvariable=self.feedback,foreground='#894800').pack(anchor='w')
        self.output=tk.Text(self,width=96,height=22,state='disabled');self.output.pack(fill='both',expand=True)
    def action(self,fn):
        try:
            result=fn()
            self.output.configure(state='normal');self.output.delete('1.0','end')
            self.output.insert('1.0',json.dumps(result,ensure_ascii=False,indent=2,default=str)[:26000]);self.output.configure(state='disabled')
            self.feedback.set('완료: 외부 작업/매출/실제 AI 실행·모니터링 없음')
            return result
        except (PermissionError,ValueError,TypeError) as exc:
            self.feedback.set('거부: '+str(exc));return None
    def view(self,section):return self.action(lambda:self.store.offline_management_view(section))
    def change_stop(self,value):return self.action(lambda:self.store.emergency_stop_local(value,self.reason.get()))
    def clear(self):
        self.output.configure(state='normal');self.output.delete('1.0','end');self.output.configure(state='disabled')
        self.feedback.set('로그아웃 — 관리자 확인 필수')
class Stage87_90Window:
    def __init__(self,root=None,store=None):
        self.root=root if root is not None else tk.Tk()
        self.root.title('AIWACK 관리 콘솔 — 실제 외부 회사 운영 아님')
        self.store=store if store is not None else LocalStore()
        bar=ttk.Frame(self.root);bar.pack()
        self.user=tk.StringVar();self.pw=tk.StringVar()
        ttk.Entry(bar,textvariable=self.user,width=20).pack(side='left')
        ttk.Entry(bar,textvariable=self.pw,width=20,show='*').pack(side='left')
        ttk.Button(bar,text='로그인',command=self.login).pack(side='left')
        ttk.Button(bar,text='로그아웃',command=self.logout).pack(side='left')
        self.panel=ManagementPanel(self.root,self.store);self.panel.pack(fill='both',expand=True)
    def login(self):
        try:self.store.login(self.user.get(),self.pw.get());self.panel.feedback.set('관리자 인증 완료')
        except (ValueError,PermissionError) as exc:self.panel.feedback.set(str(exc))
        finally:self.pw.set('')
    def logout(self):self.store.logout();self.pw.set('');self.panel.clear()
if __name__=='__main__':Stage87_90Window().root.mainloop()
