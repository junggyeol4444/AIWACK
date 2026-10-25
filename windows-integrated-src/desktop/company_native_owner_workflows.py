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
        continuity = ttk.Frame(tabs)
        tabs.add(continuity, text='운영 기록 · 중단 복구')
        staff = ttk.Frame(tabs)
        tools = ttk.Frame(tabs)
        tabs.add(staff, text='실제 직원 평가 · 조직 개편')
        tabs.add(tools, text='승인된 실제 로컬 도구')
        self._payment(payment)
        self._bank(bank)
        self._customer(customer)
        self._product(product)
        self._continuity(continuity)
        summary = ttk.Frame(tabs)
        tabs.add(summary, text='전체 운영 원본 통합 조회')
        self._operations_summary(summary)
        self._staff_management(staff)
        self._tool_management(tools)
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

    def _operations_summary(self,panel):
        """기존 실제 총괄/직원/관리자/금융 원본의 읽기 전용 연결."""
        self._field(panel,'summary_campaign','30업무 협업 번호')
        self._field(panel,'summary_business','사업 번호 (선택)')
        self._buttons(panel,[
            ('전체 실제 운영 원본 재조회',lambda:self._perform(
                '총괄 5그룹·30업무·최종 승인·결제/은행/조직 원본',
                self._read_operations_summary)),
            ('30업무 최종 승인 원본 연결 검증',lambda:self._perform(
                '총괄 5그룹·30업무·최종 보고·관리자 인계 동일 원본',
                lambda:self.store.verified_campaign_owner_chain(
                    self._id('summary_campaign')))),
            ('인계 디스크·SQLite 중단 복구 감사',lambda:self._perform(
                '승인 인계 파일 누락·손상·미등록 원본 확인 (삭제/복구 없음)',
                lambda:self.store.inspect_owner_dossier_disk_consistency(100))),
            ('30업무 호출 감사 디스크·SQLite 점검',lambda:self._perform(
                '직원·총괄 호출 감사 파일 누락·손상·미등록 원본 (읽기 전용)',
                lambda:self.store.inspect_campaign_evidence_disk_consistency(100))),
            ('호출 감사 전체 원본·디스크 검사 (최대 1만)',lambda:self._perform(
                '30업무 직원·총괄 호출 감사 전체 등록/디스크 검사 (읽기 전용)',
                lambda:self.store.inspect_campaign_evidence_disk_consistency_full(10000))),
            ('최종 인계 전체 원본·디스크 검사 (최대 1만)',lambda:self._perform(
                '최종 관리자 승인 인계 전체 등록/디스크 검사 (읽기 전용)',
                lambda:self.store.inspect_owner_dossier_disk_consistency_full(10000))),
            ('30업무 중단·재개 사전 점검',lambda:self._perform(
                '실제 승인·모델 실행 이력 및 중복 실행 방지',
                lambda:self.store.inspect_full_company_resume_gate(
                    self._id('summary_campaign')))),
            ('총괄 최종보고 실제 모델 재시도 감사',lambda:self._perform(
                '30업무 승인 증빙과 실제 총괄 GGUF 호출·실패·최종 보고 연결 (읽기 전용)',
                lambda:self.store.inspect_campaign_final_model_attempt_chain(
                    self._id('summary_campaign')))),
            ('5그룹 총괄 호출 불변 출처',lambda:self._perform(
                '실제 총괄 5그룹 호출 원본·SHA256',self._read_plan_provenance))])
        ttk.Label(panel,text=('현재 SQLite와 로컬 승인 파일의 원본만 조회합니다. '
            '실제 Windows10/11·24시간·GGUF 바이너리·PG 실거래·T01~T20 최종 합격은 '
            '조회만으로 주장하지 않습니다.'),wraplength=850).pack(
                anchor='w',padx=12,pady=12)

    def _read_operations_summary(self):
        from desktop.company_owner_operational_summary import snapshot
        business=self._get('summary_business')
        return snapshot(self.store,self._id('summary_campaign'),
                        self._id('summary_business') if business else None)

    def _read_plan_provenance(self):
        from desktop.company_campaign_plan_provenance import snapshot
        return snapshot(self.store,self._id('summary_campaign'))

    def _staff_management(self,panel):
        """Only observed real employee work, explicit owner reviews and transfers."""
        self._field(panel,'staff_employee','기존 직원 AI 번호')
        self._field(panel,'staff_department','이동 대상 부서 번호')
        self._field(panel,'staff_failed_run','동일 직원 실패 실행 번호')
        self._field(panel,'staff_proposal','직원 이동 제안 번호')
        self._field(panel,'staff_note','관리자 판단 사유 (5~200자)')
        self._buttons(panel,[
            ('31명 실제 모델 호출·성과 기록',lambda:self._perform(
                'SQLite 실제 모델·직원 성과',self._staff_metrics)),
            ('실패 직원 업무 제안 조회',lambda:self._perform(
                '실제 실패 직원 후속 제안',lambda:self.store.failed_employee_followups(40))),
            ('실제 실패 기반 후속 제안 생성',lambda:self._perform(
                '실패 실행 기반 후속 업무 제안',lambda:self.store.scan_failed_employee_work(31),
                '실제 실패 감사만 스캔합니다. 모델을 재호출하지 않고 로컬 제안을 생성합니까?'))])
        self._field(panel,'followup_id','실패 개선 제안 번호')
        self._field(panel,'followup_note','개선 업무 승인 사유')
        self._buttons(panel,[
            ('개선 업무 관리자 승인',lambda:self._review_followup('approved')),
            ('개선 업무 관리자 반려',lambda:self._review_followup('rejected'))])
        self._buttons(panel,[
            ('실패 증빙 기반 직원 이동 제안',self._propose_staff_transfer),
            ('직원 이동 감사 이력',lambda:self._perform('실제 조직 변경 감사',
                lambda:self.store.staff_department_transfer_audit(30)))])
        self._buttons(panel,[
            ('관리자 직원 이동 승인',lambda:self._review_staff_transfer('accepted')),
            ('관리자 직원 이동 반려',lambda:self._review_staff_transfer('rejected'))])
        ttk.Label(panel,text=('직원 성과는 SQLite 실제 업무·모델 호출 건수입니다. '
            '실제 GGUF 바이너리·외부 매출 검증과는 별개이며, 부서 이동은 기존 실행중 보호를 거칩니다.'),
            wraplength=850).pack(anchor='w',padx=12,pady=10)

    def _staff_metrics(self):
        from desktop.company_staff_metrics import snapshot
        return snapshot(self.store)

    def _review_followup(self,decision):
        label='승인' if decision=='approved' else '반려'
        self._perform('실패 직원 후속 업무 '+label,
            lambda:self.store.decide_failed_employee_followup(
                self._id('followup_id'),decision,self._get('followup_note')),
            '관리자 '+label+' 결과만 기록합니다. 승인 시 로컬 개선 업무를 만들되 '
            '모델 실행·외부 행동은 시작하지 않습니다. 진행합니까?')

    def _propose_staff_transfer(self):
        def action():
            result=self.store.propose_staff_department_transfer(
                self._id('staff_employee'),self._id('staff_department'),
                self._id('staff_failed_run'),self._get('staff_note'))
            self.values['staff_proposal'].set(str(result['id']))
            return result
        self._perform('실제 실패 증빙 기반 직원 이동 제안',action,
            '실제 실패 실행을 근거로 제안만 생성합니다. 소속을 변경하지 않습니다. 진행합니까?')

    def _review_staff_transfer(self,decision):
        label='승인' if decision=='accepted' else '반려'
        self._perform('직원 조직 개편 '+label,
            lambda:self.store.decide_staff_department_transfer(
                self._id('staff_proposal'),decision,self._get('staff_note')),
            '기존 부서장 보고 관계·실행 중 업무·배정 보호를 재확인한 뒤 관리자 '
            +label+'을 기록합니다. 승인하면 기존 배정이 해제될 수 있습니다. 진행합니까?')

    def _tool_management(self,panel):
        """Use existing LocalStore preflight/owner approval for real local tools."""
        self._field(panel,'tool_request','기존 로컬 도구 요청 번호')
        self._field(panel,'tool_reason','관리자 도구 승인 사유')
        self._buttons(panel,[
            ('등록된 도구 목록',lambda:self._perform('로컬 도구 목록',
                lambda:self.store.list_registered_ai_tools(limit=100))),
            ('직원별 도구 요청 조회',lambda:self._perform('기존 도구 요청',
                lambda:self.store.list_ai_tool_use_requests(100))),
            ('도구 요청 원본 확인',lambda:self._perform('도구 요청 원본',
                lambda:self.store.read_ai_tool_use_request(self._id('tool_request'))))])
        self._buttons(panel,[
            ('도구 요청 사전 권한 확인',lambda:self._perform('도구 사전 권한 검사',
                lambda:self.store.check_ai_tool_use(self._id('tool_request')))),
            ('도구 요청 관리자 승인',lambda:self._review_tool('approved')),
            ('도구 요청 관리자 반려',lambda:self._review_tool('denied'))])
        self._buttons(panel,[
            ('승인된 로컬 읽기 도구 실행',lambda:self._execute_tool('local')),
            ('승인된 Windows 버전 도구 실행',lambda:self._execute_tool('windows'))])
        self._buttons(panel,[
            ('로컬 읽기 실행 이력',lambda:self._perform('실제 로컬 읽기 감사',
                lambda:self.store.approved_local_read_tool_history(30))),
            ('Windows 버전 실행 이력',lambda:self._perform('실제 Windows 도구 감사',
                lambda:self.store.approved_windows_version_tool_history(30))),
            ('도구 요청 감사 조회',lambda:self._perform('도구 승인 원문',
                lambda:self.store.ai_tool_use_audit(self._id('tool_request'))))])
        ttk.Label(panel,text=('도구는 기존 요청/권한 사전 확인 및 관리자 승인에 따라 실행합니다. '
            '결제·환불·게시·고객 전송 도구를 자동 실행하지 않습니다.'),
            wraplength=850).pack(anchor='w',padx=12,pady=12)

    def _review_tool(self,decision):
        label='승인' if decision=='approved' else '반려'
        self._perform('도구 사용 요청 '+label,
            lambda:self.store.decide_ai_tool_use(
                self._id('tool_request'),decision,self._get('tool_reason')),
            '기존 도구 요청의 관리자 '+label+'만 기록합니다. 실행은 별도 명시적 클릭이 필요합니다. 진행합니까?')

    def _execute_tool(self,kind):
        if kind=='local':
            action=self.store.execute_approved_local_read_tool
            label='승인된 로컬 읽기 도구'
        elif kind=='windows':
            action=self.store.execute_approved_windows_version_tool
            label='승인된 Windows 버전 도구'
        else:
            raise ValueError('허용되지 않은 도구 유형')
        self._perform(label+' 실제 실행',
            lambda:action(self._id('tool_request')),
            '기존 승인·권한·비상정지·요청 검사를 통과한 '+label+'만 로컬에서 실행합니다. 진행합니까?')

    def _continuity(self,panel):
        """Native read-only uptime evidence plus deliberately reviewed recovery."""
        self._field(panel,'stale_kind','중단된 실행 종류 (tick/model)')
        self._field(panel,'stale_id','중단된 실행 번호')
        self._field(panel,'stale_note','관리자 복구 판단 사유 (5~200자)')
        self.values['process_checked']=tk.BooleanVar(value=False)
        ttk.Checkbutton(panel,text='다른 Windows 창과 실행 중인 실제 모델 프로세스를 직접 확인했습니다.',
                        variable=self.values['process_checked']).pack(anchor='w',padx=14,pady=10)
        self._buttons(panel,[
            ('실제 로그인 GUI 지속 기록',lambda:self._perform('관측된 GUI 세션 기록',
                 self._observed_continuity)),
            ('180초 이상 중단된 업무 목록',lambda:self._perform('수동 검토가 필요한 실행',
                 self._stale_claims))])
        self._buttons(panel,[
            ('관리자 직접 중단 판정',self._owner_mark_stale),
            ('과거 복구 감사 조회',lambda:self._perform('변경 불가능한 로컬 복구 감사',
                 self._recovery_audit))])
        ttk.Label(panel,text=('이 기록은 GUI 실행·로그인 중 실제 관측한 SQLite 기록입니다. '
            'Windows 10/11에서 24시간 실제 검증을 수행했다는 인증이 아닙니다. '
            '실행 중인 외부 프로세스를 종료하거나 AI를 자동 재호출하지 않습니다.'),
            wraplength=860).pack(anchor='w',padx=12,pady=12)

    def _observed_continuity(self):
        from desktop.company_continuity import observed_gui_continuity
        return observed_gui_continuity(self.store)

    def _stale_claims(self):
        from desktop.company_continuity import recent_stale_claims
        return recent_stale_claims(self.store,min_age_seconds=180)

    def _recovery_audit(self):
        from desktop.company_continuity import read_recovery_audit
        return read_recovery_audit(self.store,limit=30)

    def _owner_mark_stale(self):
        from desktop.company_continuity import inspect_and_close_stale
        def action():
            if not self.values['process_checked'].get():
                raise PermissionError('다른 프로세스를 직접 확인한 관리자의 체크가 필요합니다.')
            kind=self._get('stale_kind')
            if kind not in ('tick','model'):
                raise ValueError('실행 종류는 tick 또는 model이어야 합니다.')
            result=inspect_and_close_stale(self.store,kind,self._id('stale_id'),
                  self._get('stale_note'),owner_confirmed=True)
            self.values['process_checked'].set(False)
            return result
        self._perform('관리자 확인 후 중단된 실행 감사 처리',action,
            ('실제 다른 Windows 창과 모델 프로세스가 실행 중이지 않은지 직접 확인한 경우에만 '
             '기존 running 기록을 failed로 표시합니다. 실제 프로세스 종료·모델 재호출은 하지 않습니다. 계속합니까?'))

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
                          ('evidence_export','모델 호출 감사 번호'),
                          ('owner_final_report','관리자 승인된 총괄 최종보고 ID'),
                          ('owner_dossier','최종 결과 인계 파일 번호')]:
            self._field(panel,key,label)
        self._buttons(panel,[
            ('총괄 5그룹 실제 GGUF 계획 감사',lambda:self._perform(
                '15부서 총괄 계획·실제 호출 원본',self._read_plan_provenance)),
            ('실제 30업무 증빙 조회',lambda:self._perform('직원/총괄 승인 증빙',
                lambda:self.store.inspect_campaign_step_evidence(self._id('campaign')))),
            ('승인 상품 로컬 문서 생성',self._export_product)])
        self._buttons(panel,[
            ('상품 문서 원문·SHA 조회',lambda:self._perform('승인된 상품 문서',
                lambda:self.store.read_approved_product_document(self._id('product_doc')))),
            ('실제 모델 감사 로컬 내보내기',self._export_campaign)])
        self._buttons(panel,[('호출 감사 파일 조회',lambda:self._perform('30업무 호출 감사',
            lambda:self.store.read_campaign_call_evidence(self._id('evidence_export'))))])
        self._buttons(panel,[
            ('관리자 최종 승인 30업무 결과 패키지 생성',self._export_final_dossier),
            ('최종 인계 파일·원본 SHA 확인',lambda:self._perform('30업무 최종 인계 감사',
                lambda:self.store.read_owner_approved_final_dossier(self._id('owner_dossier')))),
            ('손상 기록 포함 최종 인계 감사',lambda:self._perform(
                '원본 인계별 정상·손상 기록',
                lambda:self.store.inspect_owner_final_dossier_history(50))),
            ('최종 승인 인계 이력·무결성',lambda:self._perform('실제 승인 인계 목록',
                lambda:self.store.list_owner_approved_final_dossiers(30))),
            ('현재 협업 최종 인계 재확인',lambda:self._perform('30업무 최종 승인 원본 재검토',
                lambda:self.store.find_owner_approved_final_dossier_by_campaign(self._id('campaign'))))])
        ttk.Label(panel,text='직원·총괄 실제 호출 및 관리자 승인 결과물만 사용합니다. 상품을 외부 게시/판매하지 않습니다.',
            wraplength=860).pack(padx=12,pady=12)

    def _export_final_dossier(self):
        def work():
            result=self.store.export_owner_approved_final_dossier(
                self._id('owner_final_report'))
            self.values['owner_dossier'].set(str(result['id']))
            return result
        self._perform('관리자 승인 완료 30업무 최종 인계 패키지',work,
            '30업무 전부와 실제 총괄 최종 보고의 관리자 승인·원본 무결성을 확인한 뒤 '
            '로컬 파일만 생성합니다. 외부 게시·결제·전송은 하지 않습니다. 진행합니까?')

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
