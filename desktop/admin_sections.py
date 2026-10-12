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
    AdminSection("departments", "조직·직원", "등록한 부서를 관리하며 AI 직원 기능은 후속 개발 예정입니다.", "부서 생성·수정·삭제 구현 · AI 직원 미구현", ("부서 관리 탭에서 실제 부서 CRUD", "AI 직원·직무 및 모델은 후속 단계", "조직도는 미구현"), True),
    AdminSection("tasks", "업무·프로젝트", "작업 생성과 상태 관리 기능이 들어올 영역입니다.", "미구현 · 23~40단계", ("작업 생성과 위임", "업무 실행 및 검수", "자율 업무 계획")),
    AdminSection("business", "사업·상품", "사업 탐색과 상품 관리 기능이 들어올 영역입니다.", "미구현 · 61~70단계", ("사업 후보와 프로젝트", "상품·서비스 관리", "판매 채널 준비")),
    AdminSection("finance", "재무·매출", "실제 승인된 거래 기록의 관리 영역입니다.", "미구현 · 71~80단계", ("실제 매출과 비용 구분", "정산·손익", "예산 및 비용 한도")),
    AdminSection("permissions", "승인·권한", "관리자 권한의 현재 상태와 향후 승인 기능입니다.", "로그인·기본 권한 적용, 승인 UI 미구현", ("현재 관리자 권한 확인", "지출 승인 및 감사 기록은 이후 개발"), True),
    AdminSection("settings", "운영·설정", "프로그램 설정·연동·복구 기능이 들어올 영역입니다.", "미구현 · 후속 단계", ("모델·도구·계정 설정", "자동 작업 정책", "백업 및 비상 정지")),
)
SECTION_BY_KEY = {section.key: section for section in SECTIONS}


def section_for(key: str) -> AdminSection:
    try:
        return SECTION_BY_KEY[key]
    except KeyError as exc:
        raise ValueError("알 수 없는 관리자 화면입니다.") from exc
