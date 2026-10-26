"""AIWACK original Korean Tk interface: approved commerce/customer/product records.

This is a window inside the existing EXE. It does not contact PG/banks, publish
products, send customer messages or synthesize model calls. Each write requires
an authenticated owner's deliberate click and the existing LocalStore guards.
"""
from __future__ import annotations

import json
import hashlib
import os
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


class CompanyOwnerWorkflows:
    def __init__(self, parent, store):
        store.require_permission('company:manage')
        self.store = store
        self.window = tk.Toplevel(parent)
        self.window.title('AIWACK | 30업무·직원 검수·고객·상품·은행 대사')
        self.window.geometry('950x730')
        self.window.minsize(750, 590)
        self.values = {}
        self._campaign_running = False
        self._close_requested = False
        self._campaign_cancel = threading.Event()
        self._campaign_results = queue.Queue()
        self.window.protocol('WM_DELETE_WINDOW', self._close)
        self.notice = tk.StringVar(value='외부 결제·송금·게시·고객 발송은 실행하지 않습니다.')
        ttk.Label(self.window, textvariable=self.notice, wraplength=900).pack(fill='x', padx=12, pady=8)
        tabs = ttk.Notebook(self.window)
        tabs.pack(fill='both', expand=True, padx=12)
        bank = ttk.Frame(tabs)
        customer = ttk.Frame(tabs)
        product = ttk.Frame(tabs)
        payment = ttk.Frame(tabs)
        tabs.add(payment, text='결제·취소·환불 서명 증빙')
        orders = ttk.Frame(tabs)
        tabs.add(orders, text='주문·환불·고객지원 로컬 연결')
        exceptions = ttk.Frame(tabs)
        tabs.add(exceptions, text='주문 예외·고객지원·재무 감사')
        tabs.add(bank, text='은행 CSV · 사업 결산')
        tabs.add(customer, text='고객 문의 · 승인 답변')
        tabs.add(product, text='30업무 · 상품 결과물')
        business = ttk.Frame(tabs)
        tabs.add(business, text='실제 AI 신규 사업 가설')
        delivery = ttk.Frame(tabs)
        tabs.add(delivery, text='사업 조사·제작 업무')
        continuity = ttk.Frame(tabs)
        tabs.add(continuity, text='운영 기록 · 중단 복구')
        operational = ttk.Frame(tabs)
        tabs.add(operational, text='운영 이상 · 부서 업무량')
        chief_evidence = ttk.Frame(tabs)
        tabs.add(chief_evidence, text='총괄 GGUF 운영·재무 판단')
        failure_ai = ttk.Frame(tabs)
        tabs.add(failure_ai, text='실패 업무 총괄 AI 원인 분석')
        staff = ttk.Frame(tabs)
        tools = ttk.Frame(tabs)
        tabs.add(staff, text='실제 직원 평가 · 조직 개편')
        tabs.add(tools, text='승인된 실제 로컬 도구')
        self._payment(payment)
        self._local_orders(orders)
        self._order_exceptions(exceptions)
        self._bank(bank)
        self._customer(customer)
        self._product(product)
        self._business_ideas(business)
        self._business_delivery(delivery)
        self._continuity(continuity)
        self._operational_management(operational)
        self._chief_evidence_management(chief_evidence)
        self._failure_model_review(failure_ai)
        summary = ttk.Frame(tabs)
        tabs.add(summary, text='전체 운영 원본 통합 조회')
        self._operations_summary(summary)
        self._staff_management(staff)
        self._tool_management(tools)
        from desktop.company_owner_evidence_tabs import attach as attach_owner_evidence_tabs
        attach_owner_evidence_tabs(self, tabs)
        from desktop.company_owner_completion_tabs import attach as attach_completion
        attach_completion(self, tabs)
        from desktop.company_owner_head_review_tabs import attach as attach_head_reviews
        attach_head_reviews(self, tabs)
        from desktop.company_owner_peer_consultation_tabs import attach as attach_peer_consultations
        attach_peer_consultations(self, tabs)
        from desktop.company_owner_chief_discovery_tabs import attach as attach_chief_discovery
        attach_chief_discovery(self, tabs)
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

    def _close(self):
        """Do not destroy the Tk window while a real model worker still runs."""
        self._campaign_cancel.set()
        if self._campaign_running:
            self._close_requested = True
            self.notice.set('실제 모델 취소 요청됨 — 실행이 끝난 뒤 창을 닫습니다. 승인·재호출 없음.')
            return
        self.window.destroy()

    def _start_real_model_action(self, title, action, approval):
        """Run one approved existing SQLite/GGUF action without freezing Tk.

        The worker never touches Tk. Only the main thread reads its result.
        """
        try:
            self.store.require_permission('company:manage')
            if self._campaign_running:
                raise ValueError('이미 실제 모델 업무가 진행 중입니다. 중복 실행을 차단합니다.')
            if action == 'business':
                self.store.require_permission('agents:manage')
                audience = self._get('model_business_audience')
                problem = self._get('model_business_problem')
                if not audience or not problem:
                    raise ValueError('사업 고객 범위와 해결할 문제를 입력하세요.')
                campaign_id = None
                source_id = None
            elif action == 'customer_case':
                self.store.require_permission('agents:manage')
                customer_case_id=self._id('case')
                from desktop.company_customer_case_ai import readiness
                if not readiness(self.store,customer_case_id)['ready']:
                    raise ValueError('고객지원 승인·직원 모델·미실행 상태를 확인하세요.')
                campaign_id=None
                source_id=None
            elif action == 'failure_analysis':
                self.store.require_permission('agents:manage')
                failure_proposal_id = self._id('failure_model_followup_id')
                campaign_id = None
                source_id = None
            elif action in ('operations_evidence_ai', 'commerce_evidence_ai'):
                self.store.require_permission('agents:manage')
                evidence_domain = 'operations' if action == 'operations_evidence_ai' else 'commerce'
                campaign_id = None
                source_id = None
            elif action == 'chief_staff_strategy':
                self.store.require_permission('agents:manage')
                campaign_id=None
                source_id=None
            elif action == 'operating_round':
                self.store.require_permission('agents:manage')
                operating_round_staff=self._id('operating_round_staff')
                operating_round_chief=self._id('operating_round_chief')
                operating_round_note=self._get('operating_round_note')
                from desktop.company_owner_operating_rounds import _positive, _note
                _positive(operating_round_staff,30,'직원')
                _positive(operating_round_chief,10,'총괄')
                _note(operating_round_note)
                campaign_id=None
                source_id=None
            elif action == 'head_to_chief_batch':
                self.store.require_permission('agents:manage')
                head_chief_limit=self._id('head_to_chief_limit')
                if not 1<=head_chief_limit<=10:
                    raise ValueError('총괄 회수는 한 회차 1~10건입니다.')
                head_chief_note=self._get('head_to_chief_note')
                from desktop.company_head_chief_handoff_queue import _note
                _note(head_chief_note)
                campaign_id=None
                source_id=None
            elif action == 'manager_review':
                self.store.require_permission('agents:manage')
                manager_artifact_id=self._id('manager_review_artifact')
                campaign_id=None
                source_id=None
            elif action == 'peer_consultation':
                self.store.require_permission('agents:manage')
                peer_task_id=self._id('peer_task_id')
                peer_consultant_id=self._id('peer_consultant_id')
                peer_note=self._get('peer_owner_note')
                from desktop.company_peer_consultations import _note
                _note(peer_note)
                campaign_id=None
                source_id=None
            elif action == 'department_discovery':
                self.store.require_permission('agents:manage')
                campaign_id = None
                source_id = None
            elif action == 'approved_queue_batch':
                self.store.require_permission('agents:manage')
                batch_limit = self._id('owner_queue_batch_limit')
                if not 1 <= batch_limit <= 30:
                    raise ValueError('한 번에 승인된 업무는 최대 30건만 실행합니다.')
                batch_note = self._get('owner_queue_batch_note')
                from desktop.company_approved_queue_batch import _reason
                _reason(batch_note)
                campaign_id = None
                source_id = None
            elif action == 'financial_brief_ai':
                self.store.require_permission('agents:manage')
                financial_brief_id=self._id('model_financial_brief_id')
                source_id=None
                campaign_id=None
            elif action == 'market_ai':
                self.store.require_permission('agents:manage')
                idea_id=self._id('model_business_idea_id')
                campaign_id=None
                source_id=None
            elif action == 'market_source':
                # User selected one literal HTTPS URL and an exact public host.
                # Do not read Tk variables in the background worker.
                idea_id=self._id('model_business_idea_id')
                source_url=self._get('model_market_url')
                source_host=self._get('model_market_hostname')
                source_title=self._get('model_market_title')
                campaign_id=None
                source_id=None
            elif action == 'plan':
                # New campaign planning still uses the ORIGINAL real GGUF path.
                # This action only creates a draft; owner review is separate.
                self.store.require_permission('agents:manage')
                source_id = self._id('summary_source_task')
                campaign_id = None
            elif action in ('next', 'final', 'recover'):
                campaign_id = self._id('summary_campaign')
                source_id = None
                if action == 'recover':
                    packet = self._campaign_review_packet()
                    if packet['chief_report'] is not None:
                        raise ValueError('이미 총괄 모델 검토가 저장된 결과물입니다.')
                    if (packet['artifact']['review_status'] != 'pending'
                            or packet['step']['task_status'] != 'in_progress'):
                        raise ValueError('미검수 중단 직원 결과물만 총괄 검토를 복구할 수 있습니다.')
                    recovery_task_id = packet['step']['task_id']
                    recovery_artifact_id = packet['artifact']['id']
                    self.store.chief_task_report_context(recovery_artifact_id)
                else:
                    gate = self.store.inspect_full_company_resume_gate(campaign_id)
                    if action == 'next':
                        if gate.get('state') != 'ready':
                            raise ValueError('30업무 재개 원본 검사 거부: ' + str(gate.get('reason')))
                    else:
                        if gate.get('state') != 'completed':
                            raise ValueError('30업무 완료 증빙 확인 전 최종 보고 생성 금지: ' +
                                             str(gate.get('reason')))
                        if self.store.find_campaign_final_report(campaign_id) is not None:
                            raise ValueError('이미 존재하는 최종 보고를 중복 생성하지 않습니다.')
            else:
                raise ValueError('지원하지 않는 실제 모델 실행 요청')
            if not messagebox.askyesno('AIWACK | 관리자 직접 실행', approval, parent=self.window):
                return
            self._campaign_cancel.clear()
            self._campaign_running = True
            self.notice.set(title + (' — 선택한 공개 HTTPS 자료 단일 수집 중' if action=='market_source'
                                      else ' — 실제 GGUF 모델 실행 중 (자동 승인 없음)'))
            def work():
                try:
                    if self._campaign_cancel.is_set():
                        raise InterruptedError('관리자가 실행을 취소했습니다.')
                    if action == 'business':
                        result = self.store.propose_chief_business_idea(
                            audience, problem, cancel=self._campaign_cancel)
                    elif action == 'customer_case':
                        from desktop.company_customer_case_ai import execute
                        result=execute(self.store,customer_case_id,
                                       cancel=self._campaign_cancel)
                    elif action == 'failure_analysis':
                        from desktop.company_failure_ai_analysis import analyze
                        result = analyze(self.store,failure_proposal_id,
                                         cancel=self._campaign_cancel)
                    elif action in ('operations_evidence_ai', 'commerce_evidence_ai'):
                        result = self.store.propose_chief_evidence_review(
                            evidence_domain, cancel=self._campaign_cancel)
                    elif action == 'chief_staff_strategy':
                        result=self.store.propose_chief_staff_strategy(
                            cancel=self._campaign_cancel)
                    elif action == 'operating_round':
                        result=self.store.run_owner_operating_round(
                            operating_round_staff,operating_round_chief,
                            operating_round_note,cancel=self._campaign_cancel)
                    elif action == 'head_to_chief_batch':
                        result=self.store.run_head_chief_handoff_batch(
                            head_chief_limit,head_chief_note,
                            cancel=self._campaign_cancel)
                    elif action == 'manager_review':
                        result=self.store.run_department_head_review(
                            manager_artifact_id,cancel=self._campaign_cancel)
                    elif action == 'peer_consultation':
                        result=self.store.run_peer_consultation(
                            peer_task_id,peer_consultant_id,peer_note,
                            cancel=self._campaign_cancel)
                    elif action == 'department_discovery':
                        result = self.store.discover_chief_department_tasks(
                            cancel=self._campaign_cancel)
                    elif action == 'approved_queue_batch':
                        from desktop.company_approved_queue_batch import run_batch
                        result = run_batch(self.store, max_jobs=batch_limit,
                                           owner_note=batch_note,
                                           cancel=self._campaign_cancel)
                    elif action == 'financial_brief_ai':
                        result=self.store.analyze_real_chief_financial_brief(
                            financial_brief_id,cancel=self._campaign_cancel)
                    elif action == 'market_ai':
                        result=self.store.analyze_chief_business_market(
                            idea_id,cancel=self._campaign_cancel)
                    elif action == 'market_source':
                        result=self.store.fetch_chief_business_market_source(
                            idea_id,source_url,source_host,source_title,
                            owner_confirmed=True,cancel=self._campaign_cancel)
                    elif action == 'plan':
                        self.store.require_permission('company:manage')
                        self.store.require_permission('agents:manage')
                        result = self.store.propose_full_company_campaign(
                            source_id, cancel=self._campaign_cancel)
                    elif action == 'recover':
                        packet = self._campaign_review_packet_worker(
                            campaign_id, recovery_task_id, recovery_artifact_id)
                        from desktop.company_operations import recover_interrupted_chief_review
                        result = recover_interrupted_chief_review(
                            self.store, packet['step']['task_id'],
                            cancel=self._campaign_cancel)
                    else:
                        # Recheck the source after confirmation, before execution.
                        fresh = self.store.inspect_full_company_resume_gate(campaign_id)
                        required = 'ready' if action == 'next' else 'completed'
                        if fresh.get('state') != required:
                            raise ValueError('실행 직전 30업무 원본이 변경됐습니다: ' +
                                             str(fresh.get('reason')))
                        if self._campaign_cancel.is_set():
                            raise InterruptedError('관리자가 실행을 취소했습니다.')
                        if action == 'next':
                            result = self.store.run_full_company_next(
                                campaign_id, cancel=self._campaign_cancel)
                        else:
                            result = self.store.propose_campaign_final_report(
                                campaign_id, cancel=self._campaign_cancel)
                    self._campaign_results.put(('ok', title, result))
                except Exception as exc:
                    self._campaign_results.put(('error', title, str(exc)))
            threading.Thread(target=work, daemon=True,
                             name='AIWACK-Owner-Real-GGUF').start()
            self.window.after(150, self._poll_real_model_action)
        except (ValueError, PermissionError, RuntimeError, OSError) as exc:
            self.notice.set(title + ' 거부: ' + str(exc))
            messagebox.showerror('AIWACK | 실행 거부', str(exc), parent=self.window)

    def _poll_real_model_action(self):
        try:
            status, title, payload = self._campaign_results.get_nowait()
        except queue.Empty:
            if self._campaign_running:
                self.window.after(150, self._poll_real_model_action)
            return
        self._campaign_running = False
        if self._close_requested:
            # Keep the persisted audit intact; do not show modal dialogs on
            # a window the owner asked to close.
            self.window.destroy()
            return
        if status == 'ok':
            if isinstance(payload, dict):
                if title == '총괄 실제 GGUF 30업무 초안 생성':
                    if type(payload.get('id')) is int and payload['id'] > 0:
                        self.values['summary_campaign'].set(str(payload['id']))
                if title in ('30업무 다음 한 단계 실제 실행',
                             '중단 직원 결과물 총괄 실제 GGUF 검토 복구'):
                    work = payload.get('work', payload)
                    if isinstance(work, dict):
                        for field, key in (('summary_artifact', 'artifact_id'),
                                           ('summary_report', 'report_id')):
                            if type(work.get(key)) is int and work[key] > 0:
                                self.values[field].set(str(work[key]))
                if title == '총괄 실제 GGUF 최종보고 생성':
                    if type(payload.get('id')) is int and payload['id'] > 0:
                        self.values['summary_final_report'].set(str(payload['id']))
                if title in ('총괄 실제 GGUF 운영 근거 분석', '총괄 실제 GGUF 재무 근거 분석'):
                    if type(payload.get('id')) is int and payload['id'] > 0:
                        self.values['chief_evidence_review_id'].set(str(payload['id']))
                if title == '실제 총괄 GGUF 사업 가설 생성':
                    if type(payload.get('id')) is int and payload['id'] > 0:
                        self.values['model_business_idea_id'].set(str(payload['id']))
            self._display(title + ' — SQLite 결과 (실기 전체 검증과 별개)', payload)
        else:
            self.notice.set(title + ' 실패: ' + payload)
            messagebox.showerror('AIWACK | 실제 모델 실행 실패', payload, parent=self.window)

    def _cancel_real_model_action(self):
        if self._campaign_running:
            self._campaign_cancel.set()
            self.notice.set('실제 GGUF 작업 취소 요청됨 — 실행 기록은 삭제하지 않습니다.')

    def _approve_full_campaign(self):
        """Owner-only explicit review of a REAL chief-produced 30-task draft."""
        def work():
            self.store.require_permission('agents:manage')
            return self.store.approve_full_company_campaign(
                self._id('summary_campaign'))
        self._perform(
            '관리자 15부서 30업무 초안 승인', work,
            '실제 총괄 GGUF 생성 원본 5그룹·15부서·31AI 배정과 감사 기록을 검토했습니까? '
            '승인 시 기존 로컬 SQLite에 선행 순서가 있는 30업무가 등록되며 '
            '실제 모델 실행이나 외부 결제·게시·전송은 시작하지 않습니다. 승인합니까?')

    def _campaign_review_packet_worker(self, campaign_id, task_id,
                                       expected_artifact_id):
        """Worker-safe provenance check: NO Tk variable access from a thread."""
        self.store.require_permission('company:manage')
        plan = self.store.read_full_company_campaign(campaign_id)
        if plan['state'] != 'approved':
            raise ValueError('총괄 검토 복구 시 승인 계획이 변경됐습니다.')
        steps = [s for s in plan['steps'] if s['task_id'] == task_id]
        if len(steps) != 1 or steps[0]['task_status'] != 'in_progress':
            raise ValueError('총괄 검토 복구 대상 업무 원본이 변경됐습니다.')
        artifacts = self.store.list_task_artifacts(task_id)
        if (len(artifacts) != 1
                or artifacts[0]['review_status'] != 'pending'
                or artifacts[0]['id'] != expected_artifact_id):
            raise ValueError('단일 미검수 직원 결과물 원본이 변경됐습니다.')
        if self.store.find_chief_task_report(artifacts[0]['id']) is not None:
            raise ValueError('이미 총괄 모델 검토 보고서가 저장됐습니다.')
        self.store.chief_task_report_context(artifacts[0]['id'])
        return {'step': steps[0], 'artifact_id': artifacts[0]['id']}

    def _campaign_review_packet(self):
        """Read ONLY the exact approved 30-task member and immutable model evidence.

        An arbitrary artifact ID from another company task/campaign is never
        accepted by these owner controls. No automatic acceptance or execution.
        """
        campaign_id = self._id('summary_campaign')
        artifact_id = self._id('summary_artifact')
        plan = self.store.read_full_company_campaign(campaign_id)
        if plan['state'] != 'approved':
            raise ValueError('관리자가 승인한 30업무 계획만 검수할 수 있습니다.')
        artifact = self.store.read_task_artifact(artifact_id)
        matching = [step for step in plan['steps']
                    if type(step['task_id']) is int
                    and step['task_id'] == artifact['task_id']]
        if len(matching) != 1:
            raise ValueError('선택한 결과물이 현재 30업무 협업에 속하지 않습니다.')
        step = matching[0]
        body = artifact.get('body')
        digest = artifact.get('sha256')
        if (not isinstance(body, str) or not isinstance(digest, str)
                or hashlib.sha256(body.encode('utf-8')).hexdigest() != digest):
            raise ValueError('직원 결과물 원문 SHA256 무결성 검사 실패')
        report = self.store.find_chief_task_report(artifact_id)
        if report is not None:
            report_body = report.get('body')
            if (report.get('artifact_id') != artifact_id
                    or report.get('chief_employee_id') != plan['chief_employee_id']
                    or not isinstance(report_body, str)
                    or hashlib.sha256(report_body.encode('utf-8')).hexdigest()
                    != report.get('sha256')):
                raise ValueError('총괄 실제 검토 보고서 원본·SHA256 연결 불일치')
        return {'campaign_id': campaign_id, 'step': step,
                'artifact': artifact, 'chief_report': report,
                'requires_owner_approval': True, 'automatic_approval': False}

    def _review_campaign_artifact(self, decision):
        if decision not in ('approved', 'changes_requested', 'rejected'):
            raise ValueError('직원 검수 상태 오류')
        def work():
            packet = self._campaign_review_packet()
            artifact = packet['artifact']
            if artifact['review_status'] != 'pending':
                raise ValueError('이미 검수된 직원 결과물은 다시 승인할 수 없습니다.')
            note = self._get('summary_review_note')
            if decision != 'approved' and not note:
                raise ValueError('수정 요청·반려 사유를 입력하세요.')
            self.store.review_task_artifact(artifact['id'], decision, note)
            return self._campaign_review_packet()
        label = {'approved': '승인', 'changes_requested': '수정 요청',
                 'rejected': '반려'}[decision]
        self._perform('30업무 직원 결과물 관리자 ' + label, work,
            '현재 선택한 30업무 직원 원문과 SHA256을 직접 확인했습니까? '
            '관리자 검수만 저장하며 다음 업무 실행이나 총괄 보고 수락은 하지 않습니다. '
            + label + '을(를) 기록합니까?')

    def _review_campaign_chief(self, decision):
        if decision not in ('accepted', 'rejected'):
            raise ValueError('총괄 검토 상태 오류')
        def work():
            packet = self._campaign_review_packet()
            report = packet['chief_report']
            if report is None:
                raise ValueError('직원 결과물에 연결된 실제 총괄 검토 보고서가 없습니다.')
            if report['owner_decision'] != 'pending':
                raise ValueError('총괄 보고서는 이미 검수되었습니다.')
            self.store.review_chief_task_report(
                report['id'], decision, self._get('summary_review_note'))
            return self._campaign_review_packet()
        label = '수락' if decision == 'accepted' else '반려'
        self._perform('30업무 총괄 모델 보고 관리자 ' + label, work,
            '실제 총괄 모델 보고 원문과 SHA256 및 선택한 직원 결과물의 연결을 '
            '확인했습니까? 총괄 보고 검수만 기록하며 업무를 자동 완료하지 않습니다. '
            + label + '합니까?')

    def _finalize_campaign_artifact(self):
        def work():
            packet = self._campaign_review_packet()
            artifact, report, step = (packet['artifact'],
                                       packet['chief_report'], packet['step'])
            if artifact['review_status'] != 'approved' or report is None:
                raise ValueError('직원 결과물 승인과 실제 총괄 검토 보고서가 모두 필요합니다.')
            if report['owner_decision'] != 'accepted':
                raise ValueError('총괄 실제 모델 검토 보고서를 관리자가 수락해야 합니다.')
            progress = self.store.verified_full_company_progress(
                packet['campaign_id'])
            if (progress['verified_completed_tasks'] != step['ordinal'] - 1
                    or progress['verified_genuine_prefix_tasks'] != step['ordinal'] - 1
                    or progress['next_task_id'] != step['task_id']):
                raise ValueError('30업무 순서 또는 이전 총괄 모델·승인 증빙 불일치')
            from desktop.company_wide_campaign import finalize_campaign_owner_artifact
            task_id = finalize_campaign_owner_artifact(self.store, artifact['id'])
            return {'completed_task_id': task_id,
                    'completed_ordinal': step['ordinal'],
                    'campaign_id': packet['campaign_id'],
                    'next_execution_automatic': False,
                    'external_payment_or_posting': False}
        self._perform('관리자 직접 30업무 1단계 완료 확정', work,
            '직원 결과물 승인, 실제 총괄 모델 검토 수락, 이전 단계의 승인·호출 원본을 '
            '확인했습니까? 현재 한 업무만 완료로 확정하며 다음 단계 모델 실행·'
            '외부 거래는 자동으로 진행하지 않습니다. 확정합니까?')

    def _decide_final_report(self, decision):
        def work():
            return self.store.decide_campaign_final_report(
                self._id('summary_final_report'), decision,
                self._get('summary_final_reason'))
        self._perform('관리자 최종 보고 ' + ('승인' if decision == 'accepted' else '거절'),
                      work, '기존 실제 GGUF 최종 보고와 30업무 승인 원본을 다시 검사한 뒤 '
                      '관리자 결정을 불변 기록합니다. 외부 거래·게시 없음. 진행합니까?')

    def _choose_csv(self):
        path = filedialog.askopenfilename(parent=self.window,
            title='소유자가 직접 준비한 은행 CSV',
            filetypes=[('CSV', '*.csv'), ('전체 파일', '*.*')])
        if path:
            self.values['csv'].set(path)

    def _summary_buttons(self, panel, pairs):
        """Use two bounded columns instead of clipping long Korean Tk labels."""
        row = ttk.Frame(panel)
        row.pack(fill='x', padx=12, pady=5)
        row.columnconfigure(0, weight=1, uniform='owner_actions')
        row.columnconfigure(1, weight=1, uniform='owner_actions')
        for index, (label, handler) in enumerate(pairs):
            ttk.Button(row, text=label, command=handler).grid(
                row=index // 2, column=index % 2, sticky='ew', padx=3, pady=3)

    def _operations_summary(self,panel):
        """Native scrollable 30-task workflow; other original tabs unchanged."""
        canvas = tk.Canvas(panel, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(panel, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        content = ttk.Frame(canvas)
        item = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda event:
            canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event:
            canvas.itemconfigure(item, width=event.width))
        panel = content
        self._field(panel,'summary_source_task','원본 기준 업무 번호 (초안 생성)')
        self._field(panel,'summary_campaign','30업무 협업 번호')
        self._field(panel,'summary_artifact','직원 실제 결과물 번호')
        self._field(panel,'summary_report','총괄 검토 보고 번호 (자동 표시)')
        self._field(panel,'summary_review_note','직원·총괄 검수 의견 (최대 1000자)')
        self._field(panel,'summary_business','사업 번호 (선택)')
        self._field(panel,'summary_final_report','총괄 최종보고 번호')
        self._field(panel,'summary_final_reason','관리자 최종 검토 사유 (5~200자)')
        self.values['chief_plan_process_checked'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel,
            text='총괄 5그룹 계획 중단 잠금 해제 전 다른 Windows 창·실제 모델 프로세스 종료를 직접 확인했습니다.',
            variable=self.values['chief_plan_process_checked']).pack(anchor='w',padx=12,pady=5)
        self.values['final_model_process_checked'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel,
            text='총괄 최종보고 중단 잠금 해제 전 다른 Windows 창·모델 프로세스 종료를 직접 확인했습니다.',
            variable=self.values['final_model_process_checked']).pack(anchor='w',padx=12,pady=5)
        self._summary_buttons(panel,[
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
            ('최종보고 GGUF 재시도 남은 횟수 확인',lambda:self._perform(
                '중단·재시작을 포함한 실제 총괄 모델 형식 오류 누적 재시도 (읽기 전용)',
                self._final_model_attempt_budget)),
            ('최종보고 GGUF 동시 실행 잠금 조회',lambda:self._perform(
                '다른 Windows 창 최종보고 실행/중단 잠금 (읽기 전용)',
                self._final_report_leases)),
            ('중단 최종보고 GGUF 잠금 관리자 확인 후 해제',self._clear_final_report_lease),
            ('5그룹 총괄 호출 불변 출처',lambda:self._perform(
                '실제 총괄 5그룹 호출 원본·SHA256',self._read_plan_provenance))])
        self._summary_buttons(panel,[
            ('총괄 실제 GGUF 5그룹·30업무 초안 생성',lambda:self._start_real_model_action(
                '총괄 실제 GGUF 30업무 초안 생성', 'plan',
                '총괄 AI가 실제 로컬 GGUF를 호출해 15부서 31AI의 30업무 초안을 구성합니다. '
                '성공한 실제 모델 호출 감사가 없으면 계획을 만들지 않으며 '
                '실행·자동 승인·외부 거래는 하지 않습니다. 진행합니까?')),
            ('5그룹 총괄 모델 초안 생성·재개 현황',lambda:self._perform(
                '원본 업무별 실제 총괄 호출·실패 감사·중단 재개',
                lambda:self.store.staged_full_company_progress(
                    self._id('summary_source_task')))),
            ('5그룹·15부서 GGUF 누적 재시도 잔여 횟수',lambda:self._perform(
                'Windows 중단·재시작 포함 실제 총괄 모델 형식 오류 감사 (읽기 전용)',
                self._read_chief_plan_retry_budget)),
            ('총괄 5그룹 GGUF 동시 실행 잠금 조회',lambda:self._perform(
                '총괄 계획 생성 중단 잠금과 관리자 복구 감사 (읽기 전용)',
                self._chief_plan_leases)),
            ('중단 총괄 5그룹 GGUF 잠금 관리자 확인 후 해제',
                self._clear_chief_plan_lease),
            ('실제 총괄 30업무 초안 원본 조회',lambda:self._perform(
                '승인 전 15부서 30업무 배정·원본',
                lambda:self.store.read_full_company_campaign(
                    self._id('summary_campaign')))),
            ('관리자 30업무 전체 초안 승인',self._approve_full_campaign)])
        self._summary_buttons(panel,[
            ('실제 30업무 승인·진행 현황',lambda:self._perform(
                '15부서 30업무 직원·총괄·관리자 승인 진행 원본',
                lambda:self.store.verified_full_company_progress(
                    self._id('summary_campaign')))),
            ('관리자 승인 다음 1업무 실제 GGUF 실행',lambda:self._start_real_model_action(
                '30업무 다음 한 단계 실제 실행', 'next',
                '30업무 원본·관리자 승인·실제 모델 호출을 검사한 뒤 다음 한 업무만 실행합니다. '
                '실제 GGUF 모델을 호출하며 외부 결제·게시를 수행하지 않습니다. 진행합니까?')),
            ('30업무 완료 후 총괄 실제 GGUF 최종보고 생성',lambda:self._start_real_model_action(
                '총괄 실제 GGUF 최종보고 생성', 'final',
                '30업무 전부의 실제 호출·승인 원본을 재검사하고 총괄 모델 보고를 생성합니다. '
                '자동 최종 승인은 하지 않습니다. 진행합니까?'))])
        self._summary_buttons(panel,[
            ('30업무 직원 결과물·총괄 원문 검토',lambda:self._perform(
                '실제 직원 산출물과 총괄 모델 원문 SHA256 연결 (읽기 전용)',
                self._campaign_review_packet)),
            ('직원 결과물 승인',lambda:self._review_campaign_artifact('approved')),
            ('직원 결과물 수정 요청',lambda:self._review_campaign_artifact('changes_requested')),
            ('직원 결과물 반려',lambda:self._review_campaign_artifact('rejected'))])
        self._summary_buttons(panel,[
            ('총괄 실제 GGUF 보고 수락',lambda:self._review_campaign_chief('accepted')),
            ('총괄 실제 GGUF 보고 반려',lambda:self._review_campaign_chief('rejected')),
            ('승인된 한 업무 완료 확정',self._finalize_campaign_artifact),
            ('중단된 총괄 실제 GGUF 검토만 복구',lambda:self._start_real_model_action(
                '중단 직원 결과물 총괄 실제 GGUF 검토 복구', 'recover',
                '기존 성공 직원 결과물을 다시 실행하지 않고, 실제 총괄 모델 검토가 '
                '누락된 한 업무만 복구합니다. 자동 승인·업무 완료·외부 거래는 없습니다. '
                '진행합니까?'))])
        self._summary_buttons(panel,[
            ('진행 중 GGUF 작업 취소 요청',self._cancel_real_model_action),
            ('총괄 최종보고 원본 조회',lambda:self._perform(
                '총괄 최종보고 및 모델 호출 증빙',
                lambda:self.store.read_campaign_final_report(
                    self._id('summary_final_report')))),
            ('관리자 최종보고 승인',lambda:self._decide_final_report('accepted')),
            ('관리자 최종보고 거절',lambda:self._decide_final_report('rejected'))])
        self._summary_buttons(panel,[
            ('관리자 승인 30업무 최종 인계 지문 저장',lambda:self._perform(
                'SQLite 실제 모델 호출·30업무·최종 승인 인계 로컬 저장',
                self._export_chain_receipt)),
            ('저장된 최종 인계 지문 원본 재검증',lambda:self._perform(
                '기존 JSON 지문과 현재 SQLite·최종 인계 파일 일치 검사',
                self._verify_saved_chain_receipt))])
        ttk.Label(panel,text=('현재 SQLite와 로컬 승인 파일의 원본만 조회합니다. '
            '실제 Windows10/11·24시간·GGUF 바이너리·PG 실거래·T01~T20 최종 합격은 '
            '조회만으로 주장하지 않습니다.'),wraplength=850).pack(
                anchor='w',padx=12,pady=12)

    def _read_chief_plan_retry_budget(self):
        from desktop.company_wide_campaign import genuine_chief_retry_progress
        return genuine_chief_retry_progress(
            self.store, self._id('summary_source_task'))

    def _chief_plan_leases(self):
        from desktop import company_campaign_plan_leases as leases
        return {'active_or_interrupted':leases.snapshot(self.store,100),
                'manual_recoveries':leases.recovery_history(self.store,30),
                'live_process_state_verified':False,
                'automatic_model_reinvocation':False}

    def _clear_chief_plan_lease(self):
        from desktop import company_campaign_plan_leases as leases
        def action():
            if self._campaign_running:
                raise PermissionError('이 창의 실제 총괄 모델 작업이 종료되기 전에는 잠금을 해제할 수 없습니다.')
            if self.values['chief_plan_process_checked'].get() is not True:
                raise PermissionError('다른 Windows 창과 모델 프로세스 종료를 직접 확인해야 합니다.')
            result=leases.clear_after_owner_inspection(
                self.store,self._id('summary_source_task'),owner_confirmed=True)
            self.values['chief_plan_process_checked'].set(False)
            return result
        self._perform('총괄 5그룹 모델 중단 잠금 수동 복구',action,
            '3분 이상 지난 잠금만 해제합니다. 다른 Windows 창과 실제 GGUF 모델 프로세스가 '
            '종료됐음을 직접 확인했으며 기존 모델을 재실행하거나 업무를 승인하지 않습니다. '
            '계속합니까?')

    def _final_model_attempt_budget(self):
        from desktop.company_campaign_final_report import (
            remaining_final_report_model_attempts)
        return remaining_final_report_model_attempts(
            self.store, self._id('summary_campaign'))

    def _final_report_leases(self):
        from desktop import company_campaign_final_leases as leases
        return {'active_or_interrupted':leases.snapshot(self.store,100),
                'manual_recoveries':leases.recovery_history(self.store,30),
                'live_process_state_verified':False,
                'automatic_model_reinvocation':False}

    def _clear_final_report_lease(self):
        from desktop import company_campaign_final_leases as leases
        def action():
            if self._campaign_running:
                raise PermissionError('이 창의 실제 모델 작업이 종료되기 전에는 잠금을 해제할 수 없습니다.')
            if self.values['final_model_process_checked'].get() is not True:
                raise PermissionError('관리자가 다른 창과 모델 프로세스를 직접 확인해야 합니다.')
            result=leases.clear_after_owner_inspection(
                self.store,self._id('summary_campaign'),owner_confirmed=True)
            self.values['final_model_process_checked'].set(False)
            return result
        self._perform('총괄 최종보고 모델 잠금 수동 복구',action,
            '3분 이상 지난 잠금만 해제합니다. 다른 Windows 창과 실제 GGUF 모델 프로세스가 '
            '종료됐음을 직접 확인했으며 기존 모델을 재실행하거나 보고서를 승인하지 않습니다. '
            '계속합니까?')

    def _export_chain_receipt(self):
        """Owner-selected local chain proof; never replace files or call GGUF."""
        self.store.require_permission('company:manage')
        campaign_id = self._id('summary_campaign')
        from desktop.company_campaign_chain_integrity import (
            export_receipt_json, verify_receipt_json)
        original = export_receipt_json(self.store, campaign_id)
        # Verify immediately against live SQLite and already saved owner dossier.
        proof = verify_receipt_json(self.store, campaign_id, original)
        if proof.get('verified') is not True:
            raise ValueError('최종 인계 원본 무결성 연결이 확인되지 않았습니다.')
        dest = filedialog.asksaveasfilename(
            parent=self.window, title='실제 승인된 30업무 인계 지문 저장',
            defaultextension='.json', filetypes=[('JSON', '*.json')])
        if not dest:
            return {'cancelled': True, 'file_written': False}
        path = Path(dest)
        if path.is_symlink() or path.exists():
            raise FileExistsError('기존 파일은 덮어쓰지 않습니다. 새 파일명을 선택하세요.')
        data = original.encode('utf-8')
        if not 0 < len(data) <= 32768:
            raise ValueError('승인된 최종 인계 증빙 파일 크기 오류')
        # Exclusive create protects owner files on a concurrent filesystem.
        with path.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != data:
            raise ValueError('인계 파일을 저장한 뒤 원본이 달라졌습니다. 원본 재확인이 필요합니다.')
        verified = verify_receipt_json(
            self.store, campaign_id, path.read_text(encoding='utf-8'))
        return {'saved_path': str(path), 'bytes': len(data),
                'receipt_sha256': verified['receipt_sha256'],
                'source_reverified': True, 'external_transmission': False}

    def _verify_saved_chain_receipt(self):
        """Inspect existing user-selected receipt without changing it."""
        self.store.require_permission('company:manage')
        campaign_id = self._id('summary_campaign')
        source = filedialog.askopenfilename(
            parent=self.window, title='저장된 30업무 최종 인계 지문 검증',
            filetypes=[('JSON', '*.json')])
        if not source:
            return {'cancelled': True, 'read_only': True}
        path = Path(source)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
            raise ValueError('검증 파일이 없거나 링크/파일 크기가 올바르지 않습니다.')
        from desktop.company_campaign_chain_integrity import verify_receipt_json
        result = verify_receipt_json(
            self.store, campaign_id, path.read_text(encoding='utf-8'))
        return {**result, 'selected_file': str(path),
                'file_modified': False, 'external_actions_executed': False}

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


    def _operational_management(self, panel):
        """SQLite 운영 이상과 부서 업무량을 소유자가 직접 검토하는 스크롤 탭."""
        canvas = tk.Canvas(panel, highlightthickness=0)
        scrollbar = ttk.Scrollbar(panel, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        body = ttk.Frame(canvas)
        body_window = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _e: canvas.configure(
            scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(
            body_window, width=e.width))
        self._field(body, 'incident_id', '운영 이상 감사 번호')
        self._field(body, 'incident_note', '운영 이상 판단 사유 (5~200자)')
        self._buttons(body, [
            ('실제 운영 이상 탐지', lambda: self._perform(
                'SQLite 운영 중단·검수 지연 근거', self.store.scan_operational_incidents)),
            ('운영 이상 원본·결정 조회', lambda: self._perform(
                '운영 이상 변경 불가 감사', lambda: self.store.operational_incident_history(50)))])
        self._buttons(body, [
            ('관리자 확인 기록', lambda: self._review_incident('acknowledged')),
            ('관리자 후속 업무 생성', lambda: self._review_incident('followup')),
            ('관리자 반려 기록', lambda: self._review_incident('dismissed'))])
        self._field(body, 'workload_department', '기존 부서 번호')
        self._field(body, 'workload_proposal', '부서 업무량 제안 번호')
        self._field(body, 'workload_note', '부서 검토 사유 (5~200자)')
        self._buttons(body, [
            ('15부서 실제 업무량 조회', lambda: self._perform(
                'SQLite 부서·직원·업무 현황', self.store.department_workload_snapshot)),
            ('관리자 부서 검토 제안', self._propose_workload),
            ('기존 업무량 제안 이력', lambda: self._perform(
                '업무량 불변 감사', lambda: self.store.department_workload_review_history(50)))])
        self._buttons(body, [
            ('관리자 내부 검토 업무 생성', lambda: self._decide_workload('review_task')),
            ('관리자 부서 제안 반려', lambda: self._decide_workload('rejected'))])
        ttk.Label(body, text=(
            '오래된 실행 기록은 프로세스 종료 증거가 아닙니다. '
            '직원 이동·AI 재호출·외부 고객 발송·결제·게시를 자동 실행하지 않습니다. '
            '실제 Windows 24시간 연속 운영 합격도 주장하지 않습니다.'),
            wraplength=780).pack(anchor='w', padx=12, pady=10)

    def _chief_evidence_management(self, panel):
        """실제 총괄 GGUF 판단과 소유자 후속 업무 승인(기존 Tk 창)."""
        self._field(panel, 'chief_evidence_review_id', '실제 총괄 분석 번호')
        self._field(panel, 'chief_evidence_note', '관리자 판단 사유 (5~200자)')
        self._buttons(panel, [
            ('운영·부서 원본 조회', lambda: self._perform(
                '운영 원본 SHA256', lambda: self.store.chief_evidence_snapshot('operations'))),
            ('주문·재무 원본 조회', lambda: self._perform(
                '재무 원본 SHA256 (실매출 아님)',
                lambda: self.store.chief_evidence_snapshot('commerce')))])
        self._buttons(panel, [
            ('실제 총괄 GGUF 운영 분석', lambda: self._start_real_model_action(
                '총괄 실제 GGUF 운영 근거 분석', 'operations_evidence_ai',
                '현재 SQLite 운영 이상·부서 업무량을 실제 로컬 총괄 GGUF에 전달해 '
                '분석 초안만 생성합니다. 결과는 미승인 상태이며 외부 작업은 없습니다. 진행합니까?')),
            ('실제 총괄 GGUF 재무 분석', lambda: self._start_real_model_action(
                '총괄 실제 GGUF 재무 근거 분석', 'commerce_evidence_ai',
                '현재 주문·환불·은행 대사 관련 로컬 증빙을 실제 로컬 총괄 GGUF에 전달해 '
                '분석 초안만 생성합니다. 실제 매출/결제 확정은 아닙니다. 진행합니까?'))])
        self._buttons(panel, [
            ('총괄 모델·근거 감사 조회', lambda: self._perform(
                '실제 GGUF 호출·SHA256 원본',
                lambda: self.store.read_chief_evidence_review(
                    self._id('chief_evidence_review_id')))),
            ('총괄 분석 최근 30건', lambda: self._perform(
                '총괄 운영·재무 분석 원본 이력',
                lambda: self.store.chief_evidence_review_history(30)))])
        self._buttons(panel, [
            ('관리자 후속 내부 업무 생성', lambda: self._decide_chief_evidence('followup_task')),
            ('관리자 분석 반려', lambda: self._decide_chief_evidence('rejected')),
            ('진행 중 실제 GGUF 취소', self._cancel_real_model_action)])
        ttk.Label(panel, text=(
            '모델 판단은 검증되지 않은 의견입니다. 원본 SHA256·실제 모델 호출 감사와 '
            '관리자 개별 승인 전에는 후속 업무를 생성하지 않습니다. '
            '승인 이후에도 외부 결제·환불·발송·게시 및 AI 자동 실행은 없습니다.'),
            wraplength=800).pack(anchor='w', padx=12, pady=12)

    def _decide_chief_evidence(self, decision):
        label = '후속 내부 검토 업무 생성' if decision == 'followup_task' else '분석 반려'
        self._perform('총괄 모델 분석 관리자 ' + label,
            lambda: self.store.decide_chief_evidence_review(
                self._id('chief_evidence_review_id'), decision,
                self._get('chief_evidence_note')),
            '실제 총괄 GGUF 출력과 원본 증빙을 직접 확인했습니까? '
            '모델 의견을 확정 매출이나 실행 성공으로 간주하지 않으며 '
            '내부 검토 업무만 기록합니다. ' + label + '합니까?')

    def _review_incident(self, decision):
        label = {'acknowledged': '확인', 'followup': '후속 업무 생성',
                 'dismissed': '반려'}[decision]
        self._perform('운영 이상 관리자 ' + label,
            lambda: self.store.decide_operational_incident(
                self._id('incident_id'), decision, self._get('incident_note')),
            '실제 프로세스 상태는 자동 판정하지 않습니다. 기존 원본은 그대로 보존하고 '
            '관리자 ' + label + '을 기록합니다. 계속합니까?')

    def _propose_workload(self):
        def action():
            result = self.store.propose_department_workload_review(
                self._id('workload_department'), self._get('workload_note'))
            self.values['workload_proposal'].set(str(result['id']))
            return result
        self._perform('실제 부서 업무량 검토 제안', action,
            '현재 SQLite 배정·직원·검수 기록을 근거로 제안만 저장합니다. '
            '실제 직원 이동이나 AI 호출은 하지 않습니다. 계속합니까?')

    def _decide_workload(self, decision):
        label = '내부 검토 업무 생성' if decision == 'review_task' else '반려'
        self._perform('부서 업무량 관리자 ' + label,
            lambda: self.store.decide_department_workload_review(
                self._id('workload_proposal'), decision, self._get('workload_note')),
            '기존 직원 소속과 모델 설정을 변경하지 않고 관리자 ' +
            label + '만 기록합니다. 계속합니까?')

    def _local_orders(self, panel):
        """기존 정산·은행 CSV·승인 상품·고객지원의 로컬 연결만 관리."""
        for key,label in [
            ('local_order_ref','로컬 주문 고유 번호'),
            ('local_order_alias','고객 별칭 (고객 문의와 동일)'),
            ('local_order_payment','관리자 승인 정산 이벤트 ID'),
            ('local_order_document','승인 상품 문서 ID'),
            ('local_order_id','기존 로컬 주문 ID'),
            ('local_order_note','관리자 사유 5~200자'),
            ('local_order_refund','관리자 승인 환불 이벤트 ID'),
            ('local_order_case','기존 고객 문의 ID')]:
            self._field(panel,key,label)
        self._buttons(panel,[
            ('정산·은행·상품 연결 주문 기록',self._create_local_order),
            ('기존 주문·원본 파일 감사',lambda:self._perform(
                '주문·상품·정산 원본 감사',
                lambda:self.store.read_local_order(self._id('local_order_id')))),
            ('로컬 주문 최근 50건',lambda:self._perform(
                '주문 원본 목록',lambda:self.store.list_local_orders(50)))])
        self._buttons(panel,[
            ('로컬 상품 제공 준비 승인',lambda:self._perform(
                '관리자 로컬 상품 준비 승인',
                lambda:self.store.approve_local_order_package(
                    self._id('local_order_id'),self._get('local_order_note')),
                '실제 고객에게 전송하지 않고 로컬 상품 제공 준비만 승인합니까?')),
            ('취소 요청 기록',lambda:self._perform(
                '로컬 취소 요청 감사',
                lambda:self.store.request_local_order_cancel(
                    self._id('local_order_id'),self._get('local_order_note')),
                '외부 PG 취소 요청 없이 내부 취소 요청 기록만 남깁니까?')),
            ('환불 증빙 연결',lambda:self._perform(
                '승인·은행 대사 환불 증빙 연결',
                lambda:self.store.link_local_order_refund(
                    self._id('local_order_id'),self._id('local_order_refund'),
                    self._get('local_order_note')),
                '기존 환불 서명·CSV 대사만 연결합니다. 실제 환불은 실행하지 않습니다. 계속합니까?'))])
        self._buttons(panel,[
            ('기존 고객지원 문의 연결',lambda:self._perform(
                '주문과 고객지원 업무 연결',
                lambda:self.store.link_local_order_customer_case(
                    self._id('local_order_id'),self._id('local_order_case')),
                '동일 고객 별칭·상품의 기존 문의만 연결하고 고객에게 발송하지 않습니다. 계속합니까?')),
            ('주문별 고객지원 감사',lambda:self._perform(
                '주문별 고객지원 원본',
                lambda:self.store.read_local_order_customer_cases(self._id('local_order_id'))))])
        self._field(panel,'local_packet_id','로컬 상품 준비 파일 ID')
        self._field(panel,'local_finance_business','사업 ID (비우면 전체)')
        self._buttons(panel,[
            ('실제 승인 상품 파일 로컬 준비',lambda:self._perform(
                '주문별 로컬 상품 준비 파일',
                lambda:self.store.prepare_local_order_delivery_packet(
                    self._id('local_order_id'),self._get('local_order_note')),
                '승인된 원본 상품 문서를 로컬에 1회 복사합니다. 고객 발송이나 결제 확인은 하지 않습니다. 진행합니까?')),
            ('로컬 상품 준비 원본 재검사',lambda:self._perform(
                '로컬 준비 파일 SHA256 감사',
                lambda:self.store.read_local_order_delivery_packet(self._id('local_packet_id')))),
            ('로컬 준비 파일 목록',lambda:self._perform(
                '기존 상품 준비 원본 목록',
                lambda:self.store.list_local_order_delivery_packets(50)))])
        self._buttons(panel,[
            ('주문·환불·고객지원 재무 대조',lambda:self._perform(
                '서명 거래와 로컬 주문 재무 대조',
                lambda:self.store.local_order_finance_snapshot(
                    self._id('local_finance_business') if self._get('local_finance_business') else None,
                    100)))])
        ttk.Label(panel,text=('이 탭은 기존 HMAC 서명·소유자 CSV·실제 승인 직원 문서의 로컬 감사 연결입니다. '
            '외부 PG/은행 독립 확인, 실제 주문 접수·결제·환불·고객 배송·매출 확정이 아닙니다.'),
            wraplength=850).pack(padx=12,pady=12)

    def _order_exceptions(self, panel):
        """주문 예외 고객지원 실제 업무 및 재무 감사 (기존 로컬 데이터)."""
        self._field(panel,'exception_order_id','기존 주문 ID')
        self._field(panel,'exception_note','관리자 사유 5~200자')
        self._field(panel,'order_exception_kind','예외 유형 (unlinked_refund 등)')
        self._field(panel,'order_exception_case_ref','신규 고객지원 고유번호')
        self._field(panel,'order_exception_id','주문 예외 연결 ID')
        self._field(panel,'order_finance_review_id','재무 증빙 검토 ID')
        self._buttons(panel,[
            ('주문·환불·배송 예외 실자료 조회',lambda:self._perform(
                '주문 예외 및 고객지원 업무 연결 필요 현황',
                lambda:self.store.scan_local_order_exceptions(100))),
            ('예외 → 실제 고객지원 업무 등록',lambda:self._perform(
                '기존 고객지원부 업무 생성 및 주문 연결',
                lambda:self.store.escalate_local_order_exception(
                    self._id('exception_order_id'),self._get('order_exception_kind'),
                    self._get('order_exception_case_ref'),self._get('exception_note')),
                '실제 주문 예외를 기존 고객지원부의 미실행 업무로 등록하고 원본 감사에 연결합니까? '
                'AI 모델 실행·고객 발송·실제 환불은 하지 않습니다.')),
            ('주문 예외 원본·고객지원 조회',lambda:self._perform(
                '주문 예외와 실제 고객지원 업무 감사',
                lambda:self.store.read_local_order_exception(self._id('order_exception_id'))))])
        self._buttons(panel,[
            ('후속 조사 필요 기록',lambda:self._perform(
                '주문 예외 후속 조사 관리자 기록',
                lambda:self.store.review_local_order_exception(
                    self._id('order_exception_id'),'followup_required',
                    self._get('exception_note')),
                '원본 주문 예외에 관리자 후속 조사 결정을 기록합니까?')),
            ('고객지원 내부 종료 확인',lambda:self._perform(
                '고객지원 내부 종료 관리자 감사',
                lambda:self.store.review_local_order_exception(
                    self._id('order_exception_id'),'internal_case_closed',
                    self._get('exception_note')),
                '기존 승인된 고객지원 답변의 내부 종료만 기록합니다. '
                '실제 고객 발송·외부 환불 완료를 의미하지 않습니다. 진행합니까?')),
            ('주문 예외 연결 전체 이력',lambda:self._perform(
                '주문 예외·고객지원 업무 연결 이력',
                lambda:self.store.local_order_exception_history(50)))])
        self._buttons(panel,[
            ('로컬 재무 증빙 검토 기록',lambda:self._perform(
                '서명 정산·은행 CSV·환불·상품·고객지원 로컬 증빙 검토',
                lambda:self.store.capture_local_finance_evidence(
                    self._id('exception_order_id'),'local_documents_reviewed',
                    self._get('exception_note')),
                '현재 로컬 증빙의 관리자 검토 영수증만 기록합니다. '
                '독립 은행·PG 확인이나 매출 확정이 아닙니다.')),
            ('재무 증빙 후속 조사 기록',lambda:self._perform(
                '로컬 재무 증빙 후속 조사 기록',
                lambda:self.store.capture_local_finance_evidence(
                    self._id('exception_order_id'),'needs_followup',
                    self._get('exception_note')),
                '현재 원본을 조사 필요로 불변 기록합니다. 외부 결제·환불 실행은 없습니다.'))])
        self._buttons(panel,[
            ('재무 검토 원본/변경 감사',lambda:self._perform(
                '재무 증빙 검토 원본 SHA 및 현재 변경 여부',
                lambda:self.store.read_local_finance_evidence(
                    self._id('order_finance_review_id')))),
            ('재무 증빙 검토 이력',lambda:self._perform(
                '관리자 로컬 재무 검토 이력',
                lambda:self.store.local_finance_evidence_history(50)))])

    def _create_local_order(self):
        def work():
            result=self.store.create_local_order_intake(
                self._get('local_order_ref'),self._get('local_order_alias'),
                self._id('local_order_payment'),self._id('local_order_document'))
            self.values['local_order_id'].set(str(result['id']))
            return result
        self._perform('기존 거래·상품 문서 로컬 주문 연결',work,
            '실제 주문·결제·배송을 실행하지 않고 관리자 선택 원본을 연결합니까?')

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
        self._field(panel,'case_chief_instruction','총괄 지시 (5~600자)')
        self._buttons(panel,[
            ('고객지원 실제 AI 준비 조회',lambda:self._perform(
                '고객지원 모델·업무 승인 준비',
                lambda:self.store.customer_ai_readiness(self._id('case')))),
            ('고객지원부 직원 배정',lambda:self._perform(
                '고객지원 기존 직원 배정',
                lambda:self.store.assign_customer_ai(self._id('case')),
                '고객지원부 기존 직원에게 업무를 배정합니다. 모델 호출은 없습니다.')),
            ('관리자 총괄 지시 승인',lambda:self._perform(
                '고객지원 실제 총괄 지시 승인',
                lambda:self.store.approve_customer_ai_order(
                    self._id('case'),self._get('case_chief_instruction')),
                '실제 고객 문의에 대한 총괄 지시를 확정합니다. 모델 호출은 없습니다.')),
            ('고객지원 실제 GGUF 실행',lambda:self._start_real_model_action(
                '고객지원 실제 직원·총괄 GGUF 실행','customer_case',
                '기존 승인 고객지원 업무의 실제 직원·총괄 GGUF를 1회 호출합니다. '
                '관리자 결과 검수 전 고객 발송·결제·자동 완료는 없습니다.')),
        ])
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

    def _failure_model_review(self, panel):
        ttk.Label(panel,text='실제 직원 GGUF 실패 감사가 있는 대기 제안을 총괄 로컬 GGUF로 '
            '딱 1회 분석합니다. 결과는 관리자 검토용이며 모델 자동 재시도·업무 승인·결제·외부 전송이 없습니다.',
            wraplength=870).pack(anchor='w',padx=12,pady=8)
        self._field(panel,'failure_model_followup_id','실제 실패 후속 제안 번호')
        self._buttons(panel,[
            ('기존 실패 후속 제안 목록',lambda:self._perform(
                '실제 직원 실행 실패 후속 제안',
                lambda:__import__('desktop.company_failure_followups',
                    fromlist=['pending']).pending(self.store,limit=80))),
            ('실제 총괄 GGUF 원인 1회 분석',lambda:self._start_real_model_action(
                '실제 총괄 GGUF 실패 원인 분석','failure_analysis',
                '실제 실패 직원 업무 1건을 총괄 로컬 GGUF로 1회 분석합니다. '
                '같은 실패 원본의 중복·자동 재실행은 허용하지 않습니다. 실행합니까?')),
            ('실제 모델 분석·중단 원본 감사',lambda:self._perform(
                '총괄 모델 실패 분석 원본',
                lambda:__import__('desktop.company_failure_ai_analysis',
                    fromlist=['history']).history(self.store,limit=100)))])

    def _business_ideas(self, panel):
        ttk.Label(panel,text='실제 연결된 로컬 총괄 GGUF 모델의 미검증 사업 가설 1건을 만듭니다. '
            '사업 등록·실제 조사·판매·결제·고객 발송·최종 승인 기능은 실행하지 않습니다.',
            wraplength=870).pack(anchor='w',padx=12,pady=8)
        for key,label in [
            ('model_business_audience','사업 대상 고객 (1~120자)'),
            ('model_business_problem','고객 문제 (1~240자)'),
            ('model_business_idea_id','검토할 사업 가설 번호'),
            ('model_business_reason','관리자 검토 사유 (5~200자)'),
            ('model_business_name','관리자 등록 사업 초안 이름'),
            ('model_market_url','조사할 공개 HTTPS 원문 URL'),
            ('model_market_hostname','승인할 공개 호스트명(소문자)'),
            ('model_market_title','실제 조사 출처 제목'),
            ('model_financial_brief_id','관리자 미검증 손익 비교 보고 번호'),
            ('model_project_title','관리자 프로젝트 초안 이름'),
            ('model_project_note','프로젝트 검토 사유 (5~300자)'),
            ('model_product_kind','상품 유형 (product/service)'),
            ('model_product_title','관리자 첫 상품 초안 이름'),
            ('model_product_delivery','첫 상품 제공 계획')]:
            self._field(panel,key,label)
        self._buttons(panel,[
            ('실제 총괄 GGUF 사업 가설 1건 생성',lambda:self._start_real_model_action(
                '실제 총괄 GGUF 사업 가설 생성','business',
                '현재 등록된 실제 총괄 로컬 GGUF를 1회 호출하여 미검증 신규 사업 가설을 '
                '생성합니다. 결과는 SQLite에 출처 SHA와 함께 저장되며 '
                '실제 시장 조사·사업/매출 생성·결제·게시와 무관합니다. 실행하시겠습니까?')),
            ('GGUF 사업 가설·출처 기록',lambda:self._perform(
                '실제 총괄 모델 사업 가설의 SQLite 원본',
                lambda:self.store.list_chief_business_ideas(limit=100)))])
        self._buttons(panel,[
            ('관리자가 사업 후보로 선정',lambda:self._review_business_idea('shortlisted')),
            ('관리자가 사업 가설 기각',lambda:self._review_business_idea('rejected'))])
        self._buttons(panel,[
            ('관리자 선정 후보 → 사업 초안 등록',self._create_business_draft),
            ('실제 모델·사업 초안 출처 확인',lambda:self._perform(
                '총괄 GGUF 실제 호출 및 사업 초안 연결 불변 감사',
                lambda:self.store.list_chief_business_draft_links(limit=100)))])
        self._buttons(panel,[
            ('사업 가설 공개자료 실제 HTTPS 수집 1건',lambda:self._start_real_model_action(
                '실제 공개 HTTPS 시장 조사 출처 수집','market_source',
                '입력한 정확한 공개 HTTPS 주소에서 단 1회 자료를 가져옵니다. '
                '소유자 확인된 호스트만 허용하고 외부 게시/판매/결제는 없습니다. '
                '자료는 출처 원본과 SHA256으로 저장되지만 사실 검증이나 수요 증명은 아닙니다. 진행합니까?')),
            ('사업 가설 실제 출처·원본 SHA 조회',lambda:self._perform(
                '실제 사업 가설 시장 조사 자료 수집 원본',
                lambda:self.store.list_chief_business_market_sources(
                    self._id('model_business_idea_id'),limit=100)))])
        self._buttons(panel,[
            ('실제 공개자료 1~3건 → 총괄 GGUF 시장 관찰 분석',lambda:self._start_real_model_action(
                '실제 총괄 GGUF 시장 자료 원문 분석','market_ai',
                '선택한 실제 사업 가설에 이미 직접 수집된 공개 HTTPS 원문 최대 3건을 '
                '기존 총괄 GGUF 모델에 전달해 미검증 관찰·경쟁 언급·불확실성을 분석합니다. '
                '허위 시장 수요·매출 판단이나 외부 게시·결제는 하지 않습니다. 진행합니까?')),
            ('총괄 실제 출처 분석·호출 감사 조회',lambda:self._perform(
                '실제 총괄 GGUF 시장 원문 분석 기록',
                lambda:self.store.chief_business_market_analysis_history(
                    self._id('model_business_idea_id'),limit=100)))])
        self._buttons(panel,[
            ('기존 비교 보고 → 실제 총괄 GGUF 가정 판단',lambda:self._start_real_model_action(
                '실제 총괄 GGUF 손익 가정 판단','financial_brief_ai',
                '관리자가 이미 작성한 미검증 손익 가정 보고를 실제 총괄 로컬 GGUF로 1회 분석합니다. '
                '자동 사업 결정·투자·결제·판매·실제 매출 검증은 하지 않습니다. 실행할까요?')),
            ('총괄 GGUF 금융 판단·호출 원본 감사',lambda:self._perform(
                '실제 총괄 손익 분석 원본',
                lambda:self.store.real_chief_financial_brief_history(limit=100)))])
        self._buttons(panel,[
            ('관리자 프로젝트 초안 연결',self._create_model_project_draft),
            ('관리자 첫 상품 초안 연결',self._create_model_product_draft)])
        self._buttons(panel,[
            ('모델 → 사업 → 프로젝트 → 상품 원본 감사',lambda:self._perform(
                '실제 GGUF 모델 출처·관리자 선택·사업/프로젝트/상품 원본 감사',
                lambda:self.store.chief_idea_pipeline_history(limit=100)))])

    def _create_model_project_draft(self):
        self._perform('실제 모델 가설 → 예산 0원 프로젝트 계획 초안',
            lambda:self.store.create_chief_idea_project_draft(
                self._id('model_business_idea_id'),
                self._get('model_project_title'),
                self._get('model_project_note')),
            '관리자가 검토 후보 선정과 사업 초안 등록을 마친 실제 GGUF 가설만 '
            '기존 사업의 예산 0원 계획 프로젝트로 연결합니다. '
            '모델 자동 실행·실제 지출·판매·게시 없이 계획만 기록합니다. 진행합니까?')

    def _create_model_product_draft(self):
        self._perform('실제 모델 가설 → 기존 상품 카탈로그 첫 초안',
            lambda:self.store.create_chief_idea_first_product_draft(
                self._id('model_business_idea_id'),
                self._get('model_product_kind'),
                self._get('model_product_title'),
                self._get('model_product_delivery')),
            '관리자가 별도로 검토한 실제 GGUF 사업 가설과 계획 프로젝트에 '
            '가정 가격 0원의 첫 상품·서비스 초안만 연결합니다. '
            '실제 상품 완성·게시·결제·매출은 발생하지 않습니다. 진행합니까?')

    def _business_delivery(self, panel):
        ttk.Label(panel,
            text='실제 총괄 GGUF 가설→사업/프로젝트/상품 초안이 연결된 경우에만 '
                 '관리자 클릭으로 조사·제작 업무 2개를 등록합니다. '
                 '모델 호출·외부 판매·결제·발송은 별도이며 자동 실행하지 않습니다.',
            wraplength=870).pack(anchor='w', padx=12, pady=8)
        for key, label in [
            ('delivery_idea_id', '실제 모델 사업 가설 번호'),
            ('delivery_research_title', '시장 조사 업무명'),
            ('delivery_product_title', '첫 상품 제작 업무명'),
            ('delivery_owner_note', '업무 인계 관리자 사유'),
            ('delivery_research_artifact', '승인된 조사 결과물 번호'),
            ('delivery_product_artifact', '승인된 제작 결과물 번호'),
            ('delivery_review_note', '상품 내부 검토 관리자 사유'),
            ('delivery_export_id', '승인 로컬 상품 파일 번호')]:
            self._field(panel, key, label)
        self._buttons(panel, [
            ('조사 → 제작 업무 2건 등록', self._create_business_delivery_tasks),
            ('기존 실제 모델·2업무·결과물 감사', lambda: self._perform(
                '총괄 모델 사업·프로젝트·상품·직원 업무 원본 감사',
                lambda: self.store.chief_idea_delivery_history(limit=100)))])
        self._buttons(panel, [
            ('승인된 직원 결과 2건 → 상품 내부 검토', self._review_business_delivery)])
        self._buttons(panel, [
            ('관리자 승인 로컬 상품 파일 생성', self._export_business_delivery),
            ('상품 파일 원본·SHA 검증', lambda: self._perform(
                '실제 직원 승인 상품 파일 무결성',
                lambda: self.store.read_chief_idea_local_product(
                    self._id('delivery_export_id'))))])
        self._buttons(panel, [
            ('상품 로컬 파일 전체 감사', lambda: self._perform(
                '실제 GGUF 상품 파일 누락·변조 감사',
                lambda: self.store.inspect_chief_idea_local_products(limit=100)))])
        ttk.Label(panel,
            text='업무 실행은 기존 담당 직원 배정/실제 모델 호출/관리자 결과물 승인 '
                 '화면에서 수행합니다. 내부 검토는 출시 승인·매출 검증이 아닙니다.',
            wraplength=870).pack(anchor='w', padx=12, pady=8)

    def _create_business_delivery_tasks(self):
        self._perform('실제 GGUF 사업 가설의 조사·제작 업무 원본 연결',
            lambda: self.store.create_chief_idea_delivery_tasks(
                self._id('delivery_idea_id'),
                self._get('delivery_research_title'),
                self._get('delivery_product_title'),
                self._get('delivery_owner_note')),
            '이미 관리자가 승인한 실제 GGUF 가설·사업·프로젝트·0원 상품 초안에 '
            '기존 미배정 업무 2건을 연결합니다. 조사 완료를 제작의 선행 조건으로 '
            '설정하며 실제 모델 실행·외부 발송·결제는 하지 않습니다. 진행합니까?')

    def _review_business_delivery(self):
        self._perform('실제 직원 승인 결과 2건의 로컬 상품 내부 검토',
            lambda: self.store.review_chief_idea_local_product(
                self._id('delivery_idea_id'),
                self._id('delivery_research_artifact'),
                self._id('delivery_product_artifact'),
                self._get('delivery_review_note')),
            '조사·제작 업무가 각각 실제 로컬 직원 모델 실행 성공, '
            '관리자 결과물 승인 및 업무 완료된 경우에만 상품을 내부 검토중으로 '
            '전환합니다. 상품 출시·판매·외부 게시·실제 매출은 아닙니다. 진행합니까?')

    def _export_business_delivery(self):
        def work():
            result = self.store.export_chief_idea_local_product(
                self._id('delivery_idea_id'))
            self.values['delivery_export_id'].set(str(result['id']))
            return result
        self._perform('실제 직원 조사·제작 결과 로컬 상품 파일',
            work,
            '실제 직원 모델 실행·관리자 결과물 승인·2개 업무 완료·상품 내부 검토 '
            '감사 원본이 일치할 때만 로컬 파일 1개를 생성합니다. '
            '실제 시장 검증·상품 출시·외부 게시·결제·판매는 하지 않습니다. 진행합니까?')

    def _create_business_draft(self):
        self._perform('실제 GGUF 사업 후보 → 예산 0원 로컬 사업 초안',
            lambda:self.store.create_chief_business_draft(
                self._id('model_business_idea_id'),
                self._get('model_business_name')),
            '관리자가 실제 모델 출처와 위험을 검토해 이미 후보로 선정한 가설만 '
            '기존 로컬 사업 포트폴리오에 예산 0원의 초안으로 연결합니다. '
            '실제 거래·자금 사용·판매·자동 실행은 하지 않습니다. 진행합니까?')

    def _review_business_idea(self, decision):
        idea_id=self._id('model_business_idea_id')
        reason=self._get('model_business_reason')
        action='검토 후보로 선정' if decision=='shortlisted' else '기각'
        self._perform('실제 모델 사업 가설 관리자 '+action,
            lambda:self.store.review_chief_business_idea(idea_id,decision,reason),
            '실제 GGUF 사업 가설의 원본·위험을 직접 확인하고 '+action+'합니다. '
            '실제 사업 시작·계좌·외부 실행·판매는 하지 않습니다. 기록합니까?')

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
