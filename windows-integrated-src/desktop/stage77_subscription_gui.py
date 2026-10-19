"""Stage77 isolated Tkinter owner console for OFFLINE simulated subscription requests.

Start with ``python -m desktop.stage77_subscription_gui``. It does not contact
or integrate with any external billing provider and never collects customer data.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from desktop.storage import LocalStore
from desktop.offline_subscription_refund import MODES


class SubscriptionRefundPanel(ttk.Frame):
    def __init__(self, master, store: LocalStore, *, dialogs=True):
        super().__init__(master, padding=12)
        self.store = store
        self.dialogs = dialogs
        self.message = tk.StringVar(value='관리자 로그인 필요 — 실제 구독/취소/환불이 아님')
        self.order_id = tk.StringVar()
        self.subscription_id = tk.StringVar()
        self.plan_key = tk.StringVar()
        self.mode = tk.StringVar(value=MODES[0])
        self.periods = tk.StringVar(value='1')
        self.event_key = tk.StringVar()
        self.action = tk.StringVar(value='cancel_requested')
        self.assumed_amount = tk.StringVar(value='0')
        self.note = tk.StringVar()
        ttk.Label(self, text='77단계 | 로컬 구독·취소·환불 *모의 기록* (실제 거래 없음)',
                  font=('TkDefaultFont', 11, 'bold')).grid(row=0, column=0, columnspan=4, sticky='w', pady=(0,10))
        inputs = [
            ('모의 주문 ID', self.order_id), ('모의 계획 키 (8~48자)', self.plan_key),
            ('기간 (1~12)', self.periods), ('모의 구독 ID', self.subscription_id),
            ('모의 이벤트 키 (8~48자)', self.event_key), ('가정 환불 금액(최소 화폐단위)', self.assumed_amount),
            ('메모(고객 개인정보 금지)', self.note),
        ]
        for i,(label,var) in enumerate(inputs,1):
            ttk.Label(self,text=label).grid(row=i,column=0,sticky='w',padx=4,pady=2)
            ttk.Entry(self,textvariable=var,width=36).grid(row=i,column=1,columnspan=2,sticky='ew',padx=4,pady=2)
        ttk.Label(self,text='모의 계획 유형').grid(row=8,column=0,sticky='w')
        ttk.Combobox(self,textvariable=self.mode,values=MODES,state='readonly',width=33).grid(row=8,column=1,columnspan=2,sticky='ew')
        ttk.Label(self,text='모의 요청').grid(row=9,column=0,sticky='w')
        ttk.Combobox(self,textvariable=self.action,values=('cancel_requested','cancel_acknowledged',
                            'refund_requested','refund_declined'),state='readonly',width=33).grid(row=9,column=1,columnspan=2,sticky='ew')
        ttk.Button(self,text='모의 구독 계획 생성',command=self.create_plan).grid(row=10,column=0,sticky='ew',pady=8)
        ttk.Button(self,text='모의 취소·환불 이력 추가',command=self.transition).grid(row=10,column=1,sticky='ew',pady=8)
        ttk.Button(self,text='감사 이력 읽기',command=self.refresh).grid(row=10,column=2,sticky='ew',pady=8)
        ttk.Label(self,textvariable=self.message,foreground='#8a4e0e',wraplength=650).grid(row=11,column=0,columnspan=3,sticky='w')
        self.output=tk.Text(self,height=10,width=86,wrap='word',state='disabled')
        self.output.grid(row=12,column=0,columnspan=3,sticky='nsew',pady=8)
        self.columnconfigure(2,weight=1)
        self.rowconfigure(12,weight=1)

    def _run(self, work):
        try:
            self.store.require_permission('company:manage')
            result=work()
            self.message.set('로컬 모의 기록 처리 성공 — 실제 결제·구독·환불 없음')
            return result
        except (ValueError,TypeError,PermissionError) as exc:
            self.message.set(f'보류/오류: {exc}')
            if self.dialogs:
                messagebox.showerror('모의 기록 검사',str(exc),parent=self.winfo_toplevel())
            return None

    def create_plan(self):
        result=self._run(lambda: self.store.create_mock_subscription(
            int(self.order_id.get()), self.plan_key.get(), self.mode.get(), int(self.periods.get())))
        if result is not None:
            self.subscription_id.set(str(result['id']))
            self.refresh()
        return result

    def transition(self):
        result=self._run(lambda: self.store.transition_mock_subscription(
            int(self.subscription_id.get()),self.event_key.get(),self.action.get(),
            self.note.get(),int(self.assumed_amount.get())))
        if result is not None:
            self.refresh()
        return result

    def refresh(self):
        import json
        result=self._run(lambda: self.store.mock_subscription_history(int(self.subscription_id.get())))
        if result is not None:
            visible=[dict(revision=e['revision'],state=e['state'],
                          assumed_amount_minor=e['assumed_amount_minor'],
                          audit_digest=e['digest'][:16]) for e in result]
            self.output.configure(state='normal')
            self.output.delete('1.0','end')
            self.output.insert('1.0',json.dumps(visible,ensure_ascii=False,indent=2))
            self.output.configure(state='disabled')
        return result


class Stage77OwnerWindow:
    def __init__(self, root=None, store=None):
        self.root=root if root is not None else tk.Tk()
        self.root.title('AIWACK 77단계 로컬 모의 구독·환불 — 실제 금융 기능 아님')
        self.store=store if store is not None else LocalStore()
        bar=ttk.Frame(self.root,padding=8)
        bar.pack(fill='x')
        self.username=tk.StringVar()
        self.password=tk.StringVar()
        ttk.Label(bar,text='로컬 관리자').pack(side='left')
        ttk.Entry(bar,textvariable=self.username,width=15).pack(side='left',padx=4)
        ttk.Label(bar,text='비밀번호').pack(side='left')
        ttk.Entry(bar,textvariable=self.password,show='*',width=18).pack(side='left',padx=4)
        ttk.Button(bar,text='로그인',command=self.login).pack(side='left',padx=4)
        ttk.Button(bar,text='로그아웃',command=self.logout).pack(side='left')
        self.panel=SubscriptionRefundPanel(self.root,self.store)
        self.panel.pack(fill='both',expand=True)

    def login(self):
        try:
            self.store.login(self.username.get(),self.password.get())
            self.panel.message.set('로컬 관리자 로그인 완료 — 실제 금융 서비스 미연결')
        except (ValueError,PermissionError) as exc:
            self.panel.message.set('로그인 실패: '+str(exc))
        finally:
            self.password.set('')

    def logout(self):
        self.store.logout()
        self.password.set('')
        self.panel.output.configure(state='normal')
        self.panel.output.delete('1.0','end')
        self.panel.output.configure(state='disabled')
        self.panel.message.set('로그아웃 완료. 모의 기록 접근 차단')


def main():
    app=Stage77OwnerWindow()
    app.root.mainloop()


if __name__=='__main__':
    main()
