"""AIWACK original Korean Tk interface: approved commerce/customer/product records.

This is a window inside the existing EXE. It does not contact PG/banks, publish
products, send customer messages or synthesize model calls. Each write requires
an authenticated owner's deliberate click and the existing LocalStore guards.
"""
from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


class CompanyOwnerWorkflows:
    def __init__(self, parent, store):
        store.require_permission('company:manage')
        self.store = store
        self.window = tk.Toplevel(parent)
        self.window.title('AIWACK | 고객·상품·은행 대사·기간 결산')
        self.window.geometry('950x730')
        self.window.minsize(750, 590)
        self.values = {}
        self.notice = tk.StringVar(value='외부 결제·송금·게시·고객 발송은 실행하지 않습니다.')
        ttk.Label(self.window, textvariable=self.notice, wraplength=900).pack(fill='x', padx=12, pady=8)
        tabs = ttk.Notebook(self.window)
        tabs.pack(fill='both', expand=True, padx=12)
        bank = ttk.Frame(tabs)
        customer = ttk.Frame(tabs)
        product = ttk.Frame(tabs)
        payment = ttk.Frame(tabs)
        tabs.add(payment, text='결제·취소·환불 서명 증빙')
        tabs.add(bank, text='은행 CSV · 사업 결산')
        tabs.add(customer, text='고객 문의 · 승인 답변')
        tabs.add(product, text='30업무 · 상품 결과물')
        self._payment(payment)
        self._bank(bank)
        self._customer(customer)
        self._product(product)
        self.output = tk.Text(self.window, height=12, wrap='word')
        self.output.pack(fill='both', expand=True, padx=12, pady=10)
        self.output.insert('end','기존 SQLite 원본 결과와 관리자 승인 기록만 조회·연결합니다.')
        self.output.configure(state='disabled')

    def _field(self, parent, key, label, width=64):
        row = ttk.Frame(parent)
        row.pack(fill='x', padx=12, pady=5)
        ttk.Label(row, text=label, width=22).pack(side='left')
        value = tk.StringVar()
        self.values[key] = value
        ttk.Entry(row, textvariable=value, width=width).pack(side='left', fill='x', expand=True)
        return row

    def _buttons(self, parent, pairs):
        row = ttk.Frame(parent)
        row.pack(fill='x', padx=12, pady=7)
        for label, handler in pairs:
            ttk.Button(row, text=label, command=handler).pack(side='left', padx=3)

    def _get(self, key):
        return self.values[key].get().strip()

    def _id(self, key):
        value = self._get(key)
        if not value.isdecimal() or int(value)<=0:
            raise ValueError(key+' 번호는 양의 정수여야 합니다.')
        return int(value)

    def _display(self, title, data):
        self.notice.set(title)
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('end', json.dumps(data, ensure_ascii=False, indent=2, default=str))
        self.output.configure(state='disabled')

    def _perform(self, title, fn, approval=None):
        try:
            self.store.require_permission('company:manage')
            if approval and not messagebox.askyesno('AIWACK | 관리자 직접 승인', approval, parent=self.window):
                return
            self._display(title, fn())
        except (ValueError, PermissionError, RuntimeError, OSError) as exc:
            self.notice.set(title+' 거부: '+str(exc))
            messagebox.showerror('AIWACK | 실행 거부', str(exc), parent=self.window)

    def _choose_csv(self):
        path = filedialog.askopenfilename(parent=self.window,
            title='소유자가 직접 준비한 은행 CSV',
            filetypes=[('CSV', '*.csv'), ('전체 파일', '*.*')])
        if path:
            self.values['csv'].set(path)

    def _payment(self, panel):
        """Only ingest pre-existing signed evidence; never initiate a payment."""
        line=self._field(panel,'pg_file','기존 PG 서명 JSON 파일')
        ttk.Button(line,text='JSON 원본 선택',command=self._choose_pg).pack(side='left',padx=4)
        self._field(panel,'pg_signature','제공자 HMAC-SHA256 서명')
        secret_line=ttk.Frame(panel)
        secret_line.pack(fill='x',padx=12,pady=5)
        ttk.Label(secret_line,text='제공자가 발급한 서명 검증키',width=22).pack(side='left')
        self.values['pg_secret']=tk.StringVar()
        ttk.Entry(secret_line,textvariable=self.values['pg_secret'],show='*',
                  width=64).pack(side='left',fill='x',expand=True)
        self._buttons(panel,[
            ('공급자 서명 JSON 로컬 감사 등록',self._ingest_pg),
            ('서명 이벤트 현황 30건',lambda:self._perform('기존 거래 감사 기록',
                 lambda:self.store.list_signed_payment_events(30)))])
        self._field(panel,'pg_event','검수할 기존 이벤트 ID')
        self._field(panel,'pg_note','관리자 검수 사유 (5~200자)')
        self._buttons(panel,[
            ('기존 거래 증빙 승인',lambda:self._review_pg('accepted')),
            ('기존 거래 증빙 반려',lambda:self._review_pg('rejected')),
            ('서명 이벤트 원화 요약',lambda:self._perform('공급자 서명 거래 요약',
                 lambda:self.store.signed_payment_reconciliation_summary(
                    self._id('business') if self._get('business') else None)))])
        ttk.Label(panel,text=('거래 유형: settlement, refund, expense. 원본 HMAC과 관리자 검토 결과를 '
               '보존할 뿐 외부 PG API 접속·결제 취소·환불 승인 요청·송금은 실행하지 않습니다.'),
                  wraplength=850).pack(padx=12,pady=12)

    def _choose_pg(self):
        path=filedialog.askopenfilename(parent=self.window,title='기존 서명 거래 JSON 원본',
             filetypes=[('JSON 거래 이벤트','*.json'),('전체 파일','*.*')])
        if path:self.values['pg_file'].set(path)

    def _ingest_pg(self):
        def work():
            path=Path(self._get('pg_file'))
            if not path.is_file() or path.suffix.lower()!='.json':
                raise ValueError('관리자가 선택한 기존 JSON 파일이 없습니다.')
            if path.stat().st_size>8192:
                raise ValueError('기존 거래 증빙 파일 크기 제한 초과')
            try:
                result=self.store.ingest_signed_payment_evidence(
                    path.read_bytes(),self._get('pg_signature'),self._get('pg_secret'))
                self.values['pg_event'].set(str(result['id']))
                return result
            finally:
                # Verification secret is used only for this owner click; never
                # written to SQLite, exported or left in the Tk input widget.
                self.values['pg_secret'].set('')
        self._perform('공급자 서명 거래의 로컬 원본 감사',work,
             '실제 결제·취소·환불을 실행하지 않고 기존 HMAC 서명 JSON만 로컬에 등록합니까?')

    def _review_pg(self,decision):
        label='승인' if decision=='accepted' else '반려'
        self._perform('기존 거래 증빙 관리자 '+label,
            lambda:self.store.review_signed_payment_evidence(
                self._id('pg_event'),decision,self._get('pg_note')),
            '서명 이벤트의 관리자 '+label+' 감사만 남깁니다. 외부 PG·은행 실거래를 실행하지 않습니다. 계속합니까?')

    def _bank(self, panel):
        line = self._field(panel,'csv','관리자 선택 은행 CSV')
        ttk.Button(line, text='CSV 선택', command=self._choose_csv).pack(side='left', padx=4)
        self._field(panel,'batch','기존 대사 번호')
        self._buttons(panel, [
            ('소유자 CSV 로컬 대사',self._import_csv),
            ('대사 원문 조회',lambda:self._perform('은행 CSV 대사 원문',
                lambda:self.store.read_bank_reconciliation(self._id('batch'))))])
        ttk.Separator(panel).pack(fill='x', pady=9)
        self._field(panel,'business','사업 번호')
        self._field(panel,'close_note','관리자 결산 사유 (5~200자)')
        self._field(panel,'close','기존 기간 결산 번호')
        self._buttons(panel, [
            ('결산 전 미승인·미대사 확인',lambda:self._perform('기간 결산 사전 상태',
                lambda:self.store.preview_business_financial_close(self._id('business')))),
            ('관리자 로컬 기간 결산 확정',self._close_period)])
        self._buttons(panel, [
            ('사업별 이전 결산 이력',lambda:self._perform('기존 기간별 누적 결산',
                lambda:self.store.list_business_financial_closes(self._id('business')))),
            ('결산 감사 기록 조회',lambda:self._perform('로컬 결산 원문',
                lambda:self.store.read_business_financial_close(self._id('close'))))])
        ttk.Label(panel,text='은행 CSV와 공급자 서명 거래의 로컬 비교일 뿐 독립 은행·PG 입금 확증은 아닙니다.',
            wraplength=860).pack(padx=12,pady=12)

    def _import_csv(self):
        def work():
            path=Path(self._get('csv'))
            if not path.is_file() or path.suffix.lower()!='.csv':
                raise ValueError('관리자 선택 CSV 파일이 없습니다.')
            result=self.store.reconcile_owner_bank_csv(path)
            self.values['batch'].set(str(result['batch_id']))
            return result
        self._perform('은행 CSV 로컬 대사 저장',work,
            '은행 CSV 원본과 승인된 거래 이벤트를 대사합니다. 실거래·송금·PG 결제/환불은 수행하지 않습니다. 진행합니까?')

    def _close_period(self):
        def work():
            result=self.store.create_business_financial_close(
                self._id('business'),self._get('close_note'))
            if 'close_id' in result:
                self.values['close'].set(str(result['close_id']))
            return result
        self._perform('관리자 승인 로컬 기간 결산',work,
            '미승인·미대사 거래가 있으면 거부됩니다. 실제 은행 정산/송금 없이 로컬 결산 기록만 확정합니까?')

    def _customer(self, panel):
        for key,label in [('reference','고객 문의 고유키'),('alias','고객 별칭'),
                          ('question','문의 원문'),('case_catalog','상품 번호(선택)'),
                          ('case','문의 번호'),('artifact','승인된 답변 결과물 번호'),
                          ('reply_export','답변 파일 내보내기 번호')]:
            self._field(panel,key,label)
        self._buttons(panel,[
            ('문의 접수·직원 업무 생성',self._create_case),
            ('기존 문의 확인',lambda:self._perform('고객 문의 현황',
                lambda:self.store.read_customer_case(self._id('case'))))])
        self._buttons(panel,[
            ('실제 승인 답변 연결',lambda:self._perform('직원·총괄 승인 답변 연결',
                lambda:self.store.approve_customer_reply(self._id('case'),self._id('artifact')),
                '이미 승인된 실제 직원·총괄 결과만 연결하고 외부 발송하지 않습니다. 진행합니까?')),
            ('관리자 문의 종료',lambda:self._perform('로컬 문의 종료',
                lambda:self.store.close_customer_case(self._id('case')),
                '실제 고객에게 전송했다고 주장하지 않고 로컬 문의만 종료합니까?')),
            ('승인 답변 로컬 파일',self._export_reply)])
        self._buttons(panel,[('답변 파일 감사 조회',lambda:self._perform('답변 파일 감사',
            lambda:self.store.read_exported_customer_reply(self._id('reply_export'))))])

    def _create_case(self):
        def work():
            catalog=self._get('case_catalog')
            kw={'catalog_item_id':self._id('case_catalog')} if catalog else {}
            result=self.store.create_customer_case(self._get('reference'),
                self._get('alias'),self._get('question'),**kw)
            self.values['case'].set(str(result['id']))
            return result
        self._perform('관리자 직접 고객 문의 접수',work,
            '고객 문의를 기존 직원 업무로 등록하며 실제 발송·주문·결제하지 않습니다. 진행합니까?')

    def _export_reply(self):
        def work():
            result=self.store.export_approved_customer_reply(self._id('case'))
            if 'id' in result:self.values['reply_export'].set(str(result['id']))
            return result
        self._perform('승인 답변 로컬 파일 저장',work,
            '승인된 결과만 로컬 파일로 생성하고 고객에게 자동 발송하지 않습니다. 진행합니까?')

    def _product(self, panel):
        for key,label in [('campaign','전체 협업 계획 번호'),('ordinal','업무 단계 번호 (1~30)'),
                          ('catalog','상품 카탈로그 번호'),('product_doc','상품 문서 번호'),
                          ('evidence_export','모델 호출 감사 번호')]:
            self._field(panel,key,label)
        self._buttons(panel,[
            ('실제 30업무 증빙 조회',lambda:self._perform('직원/총괄 승인 증빙',
                lambda:self.store.inspect_campaign_step_evidence(self._id('campaign')))),
            ('승인 상품 로컬 문서 생성',self._export_product)])
        self._buttons(panel,[
            ('상품 문서 원문·SHA 조회',lambda:self._perform('승인된 상품 문서',
                lambda:self.store.read_approved_product_document(self._id('product_doc')))),
            ('실제 모델 감사 로컬 내보내기',self._export_campaign)])
        self._buttons(panel,[('호출 감사 파일 조회',lambda:self._perform('30업무 호출 감사',
            lambda:self.store.read_campaign_call_evidence(self._id('evidence_export'))))])
        ttk.Label(panel,text='직원·총괄 실제 호출 및 관리자 승인 결과물만 사용합니다. 상품을 외부 게시/판매하지 않습니다.',
            wraplength=860).pack(padx=12,pady=12)

    def _export_product(self):
        def work():
            result=self.store.export_approved_product_document(
                self._id('campaign'),self._id('ordinal'),self._id('catalog'))
            if 'id' in result:self.values['product_doc'].set(str(result['id']))
            return result
        self._perform('실제 승인 결과 기반 상품 문서 생성',work,
            '30업무 실제 승인 결과를 로컬 상품 문서로 생성합니다. 외부 판매·게시·결제하지 않습니다. 진행합니까?')

    def _export_campaign(self):
        def work():
            result=self.store.export_campaign_call_evidence(self._id('campaign'))
            if 'id' in result:self.values['evidence_export'].set(str(result['id']))
            return result
        self._perform('실제 30업무 호출 감사 내보내기',work,
            '현재의 실제 모델 감사·관리자 승인 원본만 로컬 파일로 내보냅니다. 진행합니까?')


def open_native_company_workflows(parent,store):
    return CompanyOwnerWorkflows(parent,store)
