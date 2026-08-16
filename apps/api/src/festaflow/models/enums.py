"""도메인 열거형.

packages/shared/src/enums.ts 와 값이 1:1로 일치해야 합니다.
한쪽만 고치면 프런트와 백엔드가 다른 말을 하게 됩니다.
"""

from __future__ import annotations

import enum


class FestivalStatus(str, enum.Enum):
    DRAFT = "draft"
    PLANNING = "planning"
    READY = "ready"
    LIVE = "live"
    CLOSED = "closed"


class PlanStage(str, enum.Enum):
    """진행 표시일 뿐 다음 단계를 잠그지 않는다."""

    DRAFT = "draft"
    LAYOUT = "layout"
    OPERATIONS = "operations"
    PROPOSAL = "proposal"


class PlanTier(str, enum.Enum):
    PER_FESTIVAL = "per_festival"
    ANNUAL = "annual"
    ENTERPRISE = "enterprise"


class StaffRole(str, enum.Enum):
    PLANNER = "planner"
    OPERATOR = "operator"
    BOOTH_MANAGER = "booth_manager"


class BoothType(str, enum.Enum):
    """자유 텍스트가 아니다 — 진단의 '유형 수' 점수가 표기 흔들림으로 부풀지 않게."""

    FOOD = "food"
    EXPERIENCE = "experience"
    PERFORMANCE = "performance"
    INFORMATION = "information"
    LOCAL_SHOP = "local_shop"
    ETC = "etc"


class BoothVerifyMode(str, enum.Enum):
    STAFF_SCAN = "staff_scan"
    PARTICIPANT_SCAN = "participant_scan"


class BoothQrMode(str, enum.Enum):
    """인쇄가 기본. 장비를 강요하면 그 기능은 안 쓰인다."""

    PRINTED = "printed"
    ROTATING = "rotating"


class ParticipationStatus(str, enum.Enum):
    ISSUED = "issued"
    COMPLETED = "completed"


class ExperienceType(str, enum.Enum):
    STAMP = "stamp"
    QUIZ = "quiz"
    PHOTO = "photo"
    SURVEY = "survey"
    INFO = "info"


class RevealMode(str, enum.Enum):
    RANDOM = "random"
    BOOTH_ASSIGNED = "booth_assigned"


class GrantUnit(str, enum.Enum):
    BOOTH = "booth"
    MISSION = "mission"


class DiagnosisStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DiagnosisCategory(str, enum.Enum):
    TOURISM_DEMAND = "tourism_demand"
    CROWD_SAFETY = "crowd_safety"
    PROGRAM_BALANCE = "program_balance"
    LOCAL_LINKAGE = "local_linkage"
    OPS_READINESS = "ops_readiness"


class RiskLevel(str, enum.Enum):
    STABLE = "stable"
    CAUTION = "caution"
    RISK = "risk"


class RiskGrade(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TourismProvider(str, enum.Enum):
    KTO_LIVE = "kto_live"
    DEMO = "demo"


class VisitorSource(str, enum.Enum):
    BEACON = "beacon"
    MANUAL_COUNTER = "manual_counter"
    KTO_BIGDATA = "kto_bigdata"
    PARTNER = "partner"
    ESTIMATE = "estimate"


#: 낮을수록 우선. 리포트는 이 순서로 하나를 골라 쓰고 나머지는 병기한다.
VISITOR_SOURCE_PRIORITY: dict[VisitorSource, int] = {
    VisitorSource.BEACON: 1,
    VisitorSource.MANUAL_COUNTER: 2,
    VisitorSource.KTO_BIGDATA: 3,
    VisitorSource.PARTNER: 4,
    VisitorSource.ESTIMATE: 5,
}


class BoothLoadStatus(str, enum.Enum):
    """QR 완료 기반 참여 편중 지표. 실제 밀집도가 아니다."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    LOW = "LOW"
    CAUTION = "CAUTION"
    HIGH = "HIGH"


class RecommendationType(str, enum.Enum):
    REDISTRIBUTE = "REDISTRIBUTE"
    NO_ACTIVITY = "NO_ACTIVITY"
