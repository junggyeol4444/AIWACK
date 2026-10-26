"""Korean Windows Tk screen for owner-selected original bank camt.053 XML.

No bank login, no web UI, no arbitrary model action. Local bank statement
is owner-supplied evidence, not bank-issuer-authenticated settlement.
"""
from __future__ import annotations
from tkinter import filedialog, ttk


def attach(owner,tabs):
    frame=ttk.Frame(tabs)
    tabs.add(frame,text="은행 XML 원본 거래 대사")
    owner._field(frame,"camt_statement_path","선택한 은행 ISO20022 camt.053 XML 로컬 경로")
    owner._field(frame,"camt_provider_name","기존 HMAC 승인 공급자 이름")
    owner._field(frame,"camt_business_id","기존 사업 번호")
    owner._buttons(frame,[
        ("은행 실제 XML 파일 선택",lambda:owner.values["camt_statement_path"].set(
            filedialog.askopenfilename(
                parent=owner.window,title="AIWACK | 은행 camt.053 원본 파일 선택",
                filetypes=[("ISO 20022 camt.053","*.xml *.camt"),
                           ("모든 파일","*.*")]) or
            owner._get("camt_statement_path"))),
        ("실제 은행 거래 XML/PG 승인 이벤트 사전 대조",lambda:owner._perform(
            "실제 은행 XML 원본·PG 승인 거래번호/금액/방향 대조 미리보기",
            lambda:owner.store.preview_bank_camt_statement(
                owner._get("camt_statement_path"),
                owner._get("camt_provider_name"),
                owner._id("camt_business_id")))),
    ])
    owner._buttons(frame,[
        ("선택한 은행 XML 전체 원자적 대사 기록",lambda:owner._perform(
            "기존 HMAC 관리자 승인 거래와 은행 camt.053 원본 파일 1회 대사",
            lambda:owner.store.import_bank_camt_statement(
                owner._get("camt_statement_path"),
                owner._get("camt_provider_name"),
                owner._id("camt_business_id")),
            "선택한 로컬 은행 XML의 모든 확정 거래를 기존 공급자 HMAC "
            "증빙 및 관리자 수락 이벤트와 정확한 TxId/금액/입출금 상태로 "
            "연결합니다. 한 행이라도 불일치하면 전체 거부합니다. "
            "기존 CSV 또는 다른 XML에서 대사된 거래는 중복 등록하지 않습니다. "
            "계좌에 접속하거나 결제·환불·송금하지 않습니다. "
            "로컬 파일은 독립적 은행 발급 증거가 아닙니다. 실제로 등록합니까?")),
        ("은행 camt 원본 SHA256 및 대사 기록",lambda:owner._perform(
            "실제 로컬 은행 XML·승인 공급자 증빙·중복 검수 원장",
            lambda:owner.store.bank_camt_statement_history(50))),
    ])
    ttk.Label(frame,wraplength=820,text=(
        "한국 은행이 ISO 20022 camt.053 규격으로 내려받게 해 준 파일만 "
        "사용할 수 있습니다. 일반 거래내역 CSV는 기존 은행 CSV 대사 화면을 "
        "사용하세요. 이 기능은 은행 원본의 NtryRef·TxId와 확정 거래만 "
        "연결하며, 은행 API·은행 서명·실제 입출금은 독립 확인하지 않습니다. "
        "모델을 실행하거나 고객 계정·금융 계좌를 조작하지 않습니다."
    )).pack(anchor="w",padx=12,pady=12)
