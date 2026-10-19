"""Stage 10: honest, read-only administration navigation schema.

Declared sections are GUI structure, NOT implemented business engines. Unknown
sections and unimplemented actions must never be silently executed.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AdminSection:
    key: str
    title: str
    summary: str
    status: str
    planned_features: tuple[str, ...]
    implemented: bool = False


SECTIONS: tuple[AdminSection, ...] = (
    AdminSection("overview", "회사 현황", "로컬 회사 정보와 운영 목표를 별도 탭에서 관리합니다.", "회사 정보·목표 관리 구현, AI 운영 지표 미구현", ("회사 프로필 및 목표 CRUD (회사·목표 관리 탭)", "실제 AI 회사 운영 지표는 아직 없음"), True),
    AdminSection("departments", "조직·직원", "등록한 부서를 관리하며 AI 직원 기능은 후속 개발 예정입니다.", "부서·직급·직무·역할 및 AI 직원 프로필 관리 구현 · AI 실행 미구현", ("부서 관리 탭에서 실제 부서 CRUD", "직급·직무·역할 탭에서 명칭 관리", "직원 프로필 등록·수정·비활성화(15단계), 모델 실행 미구현", "총괄 AI → 부서장 → 직원 보고 체계(16단계), 직원별 권한·도구 허가(17단계), 실행 미구현"), True),
    AdminSection("tasks", "업무·프로젝트", "회사 목표·업무 계획과 수동 업무 생성·상태 기록을 로컬에 저장합니다.", "업무 우선순위·의존성 및 관리자 승인 로컬 AI 텍스트 실행 구현 · 자동 운영 미구현", ("업무 계획 탭에서 목표별 계획·순서 CRUD (22단계)", "업무 관리 탭에서 작업 생성·수정·상태 변경과 기록 (23단계)", "담당 직원 지정·우선순위·선행 업무 관리 (24~26단계), 수동 로컬 AI 텍스트 실행 (27단계), 결과물 수동 저장·검수 (28단계), 독립 업무 최대 2개 병렬 실행 (29단계)"), True),
    AdminSection("business", "사업·상품", "사업 탐색과 상품 관리 기능이 들어올 영역입니다.", "미구현 · 61~70단계", ("사업 후보와 프로젝트", "상품·서비스 관리", "판매 채널 준비")),
    AdminSection("finance", "재무·매출", "실제 승인된 거래 기록의 관리 영역입니다.", "미구현 · 71~80단계", ("실제 매출과 비용 구분", "정산·손익", "예산 및 비용 한도")),
    AdminSection("permissions", "승인·권한", "관리자 권한의 현재 상태와 향후 승인 기능입니다.", "로그인·기본 권한 적용, 승인 UI 미구현", ("현재 관리자 권한 확인", "AI 직원별 권한과 도구 설정(17단계)", "지출 승인 및 감사 기록은 이후 개발"), True),
    AdminSection("settings", "운영·설정", "로컬 AI 모델 설정은 '로컬 AI 모델' 탭에서 관리합니다.", "로컬 모델 등록 및 직원별 모델 배정·호출 기록 구현 · 백업 미구현", ("GGUF·llama.cpp·llamafile 로컬 실행 설정(18단계)", "직원별 모델 배정·수동 시험과 호출 기록(19단계)", "백업 및 비상 정지(후속)"), True),
)
SECTION_BY_KEY = {section.key: section for section in SECTIONS}


def section_for(key: str) -> AdminSection:
    try:
        return SECTION_BY_KEY[key]
    except KeyError as exc:
        raise ValueError("알 수 없는 관리자 화면입니다.") from exc
