"""Native Korean Tk controls for the EXISTING source 3-way preservation tool.

Explicitly owner-clicked; no Git checkout, branch, database or source changes.
Only produces a new candidate directory outside the original checkout.
"""
from __future__ import annotations

from tkinter import filedialog,ttk


def _browse(owner,key,kind):
    if kind=="zip":
        path=filedialog.askopenfilename(parent=owner.window,
            title="역사 원본 ZIP 선택",filetypes=[("ZIP 파일","*.zip")])
    elif kind=="folder":
        path=filedialog.askdirectory(parent=owner.window,
            title="현재 main Git 체크아웃 폴더 선택")
    else:
        path=filedialog.askdirectory(parent=owner.window,
            title="새 후보 폴더의 상위 경로 선택")
        if path:
            from pathlib import Path
            from uuid import uuid4
            path=str(Path(path)/("AIWACK_보존형_병합후보_"+uuid4().hex[:12]))
    if path:
        owner.values[key].set(path)


def _values(owner):
    return (owner._get("preserve_original_zip"),
            owner._get("preserve_cumulative_zip"),
            owner._get("preserve_main_checkout"),
            owner._get("preserve_stage"))


def attach(owner,tabs):
    panel=ttk.Frame(tabs)
    tabs.add(panel,text="원본 1099·1171 보존형 병합")
    specs=(
        ("preserve_original_zip","역사 원본 ZIP A (1,099 파일)","zip"),
        ("preserve_cumulative_zip","누적 원본 ZIP B (1,171 파일)","zip"),
        ("preserve_main_checkout","현재 main 로컬 Git 체크아웃","folder"),
        ("preserve_stage","새 별도 후보 폴더 (미존재)","stage"),
    )
    for key,label,kind in specs:
        owner._field(panel,key,label)
        owner._buttons(panel,[("파일/폴더 선택",lambda k=key,t=kind:_browse(owner,k,t))])
    owner._field(panel,"preserve_note","원본 보존 후보 생성 사유 (5~200자)")
    owner._buttons(panel,[
        ("원본 ZIP A/B 항목·SHA256·출력 위치 사전 조회",lambda:owner._perform(
            "역사 1,099/1,171 원본 ZIP 파일 항목·지문 조회",
            lambda:owner.store.preview_source_preservation(*_values(owner)))),
        ("3-way 병합 후보만 별도 새 폴더 생성",lambda:owner._perform(
            "기존 원본 도구로 별도 병합 후보·충돌 3사본 생성",
            lambda:owner.store.stage_source_preservation_candidates(
                *_values(owner),owner._get("preserve_note")),
            "기존 보존형 3-way 도구를 이용해 원본 ZIP A/B와 "
            "현재 로컬 main 체크아웃을 비교합니다. 기존 main/DB/"
            "ZIP은 수정하지 않으며 별도의 새로운 출력 폴더에만 "
            "병합 후보와 충돌 시 3개 원본 사본을 작성합니다. "
            "자동 main 적용·충돌 임의 해결은 하지 않습니다. "
            "원본 병합 후보 생성만 승인합니까?")),
    ])
    owner._buttons(panel,[
        ("역사 ZIP 후보 생성 SQLite 불변 감사 이력",lambda:owner._perform(
            "원본 1,099/1,171 후보 생성 감사·SHA256",
            lambda:owner.store.source_preservation_history(50))),
    ])
    ttk.Label(panel,wraplength=850,text=(
        "실제 과거 ZIP A/B가 있어야 누락 28개 및 충돌 52개를 "
        "직접 대조할 수 있습니다. 이 화면은 기존 preservation/"
        "safe_three_way_source_merge.py 원본 코드를 그대로 사용합니다. "
        "동일 ZIP이나 원본 소스/DB/모델·브랜치를 덮어쓰지 않습니다. "
        "병합 후보 생성은 개발 단계이며 main 통합 완료를 뜻하지 않습니다. "
        "충돌 3개 원본 사본은 사람이 따로 검토해야 합니다."
    )).pack(anchor="w",padx=12,pady=12)
