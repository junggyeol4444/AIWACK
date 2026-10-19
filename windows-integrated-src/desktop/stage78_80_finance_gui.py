"""Stage78-80 local-only Tkinter owner console (NO real customers or transactions)."""
import json
import tkinter as tk
from tkinter import ttk
from desktop.storage import LocalStore


class OfflineCommercePanel(ttk.Frame):
    def __init__(self, master, store, *, dialogs=False):
        super().__init__(master, padding=8)
        self.store=store
        self.dialogs=dialogs
        self.status=tk.StringVar(value='OFFLINE / SYNTHETIC ONLY — 관리자 인증 필요')
        ttk.Label(self,text='78~80 | 가상 고객지원 · 미검증 금액 · 가정 예산 (실거래 0)',font=('TkDefaultFont',11,'bold')).pack(anchor='w')
        self.tabs=ttk.Notebook(self)
        self.tabs.pack(fill='both',expand=True)
        self.fields={}
        self._tab('가상 고객지원',[
            ('order_id','모의 주문 ID','1'),('ticket_key','티켓 키','ticket_local_001'),
            ('alias','합성 고객 별칭','SIMCUST_local01'),('category','분류','QUESTION_SIMULATED'),
            ('summary','합성 문의','Local example question'),('ticket_id','티켓 ID','1'),
            ('event_key','티켓 이벤트 키','review_local_001'),('action','상태 전환','reviewed'),
            ('comment','합성 처리 메모','Locally reviewed')],
            [('티켓 생성',self.create_ticket),('상태 변경',self.transition_ticket),('티켓 감사 이력',self.ticket_history)])
        self._tab('가정 금액',[
            ('business_id','사업 ID','1'),('entry_key','금액 입력 키','expense_local_01'),
            ('kind','가정 구분','ASSUMED_EXPENSE'),('currency','통화','KRW'),
            ('amount_minor','최소 화폐단위 정수','100'),('money_note','가정 메모','Local assumed expense'),
            ('finance_order_id','모의 주문 ID(선택)','')],
            [('가정 금액 기록',self.record_finance),('가정 기록 검사',self.finance_history)])
        self._tab('가정 예산', [('snapshot_key','예산 스냅샷 키','budget_local_001')],
                  [('가정 손익 보기',self.budget_report),('스냅샷 기록',self.budget_snapshot),('기록 재검사',self.budget_history)])
        ttk.Label(self,textvariable=self.status,foreground='#9b5400',wraplength=680).pack(anchor='w',pady=5)
        self.output=tk.Text(self,height=11,width=92,state='disabled')
        self.output.pack(fill='both',expand=True)

    def _tab(self,name,items,actions):
        container=ttk.Frame(self.tabs,padding=7)
        self.tabs.add(container,text=name)
        for n,(key,title,default) in enumerate(items):
            ttk.Label(container,text=title).grid(row=n,column=0,sticky='w',padx=4,pady=2)
            field=tk.StringVar(value=default)
            self.fields[key]=field
            ttk.Entry(container,textvariable=field,width=50).grid(row=n,column=1,sticky='ew',pady=2)
        for col,(title,action) in enumerate(actions):
            ttk.Button(container,text=title,command=action).grid(row=len(items),column=col,sticky='ew',pady=6)
        container.columnconfigure(1,weight=1)

    def val(self,name):return self.fields[name].get()
    def _run(self,fn):
        try:
            self.store.require_permission('company:manage')
            result=fn()
            self.status.set('로컬 처리 성공 — 외부 연락/결제/정산 없음')
            self.output.configure(state='normal')
            self.output.delete('1.0','end')
            self.output.insert('end',json.dumps(result,ensure_ascii=False,indent=2,default=str)[:12000])
            self.output.configure(state='disabled')
            return result
        except (ValueError,TypeError,PermissionError) as exc:
            self.status.set('차단/확인 필요: '+str(exc))
            return None

    def create_ticket(self):
        out=self._run(lambda:self.store.create_synthetic_support_ticket(
            int(self.val('order_id')),self.val('ticket_key'),self.val('alias'),self.val('category'),self.val('summary')))
        if out:self.fields['ticket_id'].set(str(out['id']))
        return out
    def transition_ticket(self):
        return self._run(lambda:self.store.transition_synthetic_support_ticket(
            int(self.val('ticket_id')),self.val('event_key'),self.val('action'),self.val('comment')))
    def ticket_history(self):return self._run(lambda:self.store.synthetic_support_ticket_history(int(self.val('ticket_id'))))
    def record_finance(self):
        return self._run(lambda:self.store.record_hypothetical_finance(
            int(self.val('business_id')),self.val('entry_key'),self.val('kind'),self.val('currency'),
            int(self.val('amount_minor')),self.val('money_note'),int(self.val('finance_order_id')) if self.val('finance_order_id') else None))
    def finance_history(self):return self._run(self.store.hypothetical_finance_history)
    def budget_report(self):return self._run(self.store.hypothetical_budget_report)
    def budget_snapshot(self):return self._run(lambda:self.store.save_hypothetical_budget_snapshot(self.val('snapshot_key')))
    def budget_history(self):return self._run(self.store.hypothetical_budget_snapshots)
    def clear(self):
        self.output.configure(state='normal')
        self.output.delete('1.0','end')
        self.output.configure(state='disabled')
        self.status.set('관리자 로그아웃 — 합성 기록 조회/변경 차단')


class Stage78_80OwnerWindow:
    def __init__(self,root=None,store=None):
        self.root=root if root is not None else tk.Tk()
        self.root.title('AIWACK 78-80 — 오프라인 모의 고객지원·가정 재무')
        self.store=store if store is not None else LocalStore()
        login=ttk.Frame(self.root,padding=6);login.pack(fill='x')
        self.username=tk.StringVar();self.password=tk.StringVar()
        ttk.Label(login,text='로컬 관리자').pack(side='left')
        ttk.Entry(login,textvariable=self.username,width=20).pack(side='left')
        ttk.Label(login,text='비밀번호').pack(side='left')
        ttk.Entry(login,textvariable=self.password,width=20,show='*').pack(side='left')
        ttk.Button(login,text='로그인',command=self.login).pack(side='left')
        ttk.Button(login,text='로그아웃',command=self.logout).pack(side='left')
        self.panel=OfflineCommercePanel(self.root,self.store)
        self.panel.pack(fill='both',expand=True)
    def login(self):
        try:
            self.store.login(self.username.get(),self.password.get())
            self.panel.status.set('로컬 관리자 로그인 확인 — 실제 거래 불가')
        except (ValueError,PermissionError) as exc:
            self.panel.status.set('로그인 실패: '+str(exc))
        finally:self.password.set('')
    def logout(self):
        self.store.logout();self.password.set('');self.panel.clear()


def main():Stage78_80OwnerWindow().root.mainloop()
if __name__=='__main__':main()
