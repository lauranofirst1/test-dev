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
    #: 전시 작품에 점수를 매기는 사람. **운영 권한은 없다** —
    #: 심사위원이 부스를 고치거나 경품을 건드릴 이유가 없고, 그 권한이 붙어
    #: 있으면 외부 심사위원에게 계정을 줄 때마다 축제 전체가 열린다.
    JUDGE = "judge"


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


class IdentityMode(str, enum.Enum):
    """참여자를 어떻게 식별하는가. **축제 성격이 정반대를 요구한다.**

    지역 관광 축제에서 지나가는 관광객에게 신원을 요구할 수 없습니다. 그래서
    익명이 기본이고, 화면도 "이름이나 연락처는 받지 않습니다"라고 약속합니다.

    교내 행사는 뒤집힙니다. 1인 1표를 강제하려면 "이 사람이 아까 그 사람"임을
    알아야 하는데, 익명 코드는 무한히 새로 받을 수 있어 스티커를 여러 장 붙이던
    행위가 새로고침 여러 번으로 바뀔 뿐입니다. 공결이 걸린 특강은 한 발 더
    나아가, **학교에 낼 명단**이 필요합니다.
    """

    #: 코드만. 개인정보를 받지 않는다.
    ANONYMOUS = "anonymous"
    #: 학번을 받아 1인 1계정을 강제한다. 공결 명단을 만들 수 있다.
    STUDENT_ID = "student_id"


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


class BoardStyle(str, enum.Enum):
    """진행 보드를 어떻게 보여줄지. **구조가 아니라 표현이다.**

    타일 수도, 배정도, 공개 기록도 달라지지 않는다. 그래서 이 값을 바꿔도
    참여자의 수집 진행이 초기화되지 않는다.

    `grid` 는 그림 한 장을 격자로 쪼갠 퍼즐이고, `trail` 은 점선으로 이어진
    스탬프 랠리 지도다. 은유가 다르다 — 퍼즐은 "그림이 완성된다",
    지도는 "길을 따라간다". 축제 성격에 맞는 쪽을 운영자가 고른다.
    """

    GRID = "grid"
    TRAIL = "trail"


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


class AnnouncementChannel(str, enum.Enum):
    """공지를 누가 보는가.

    **스태프 공지가 관객에게 새면 안 됩니다.** "3번 부스 QR 재출력하세요" 나
    "현금 정산 30분 뒤" 같은 내부 전달은 관객이 볼 것을 전제로 쓰이지 않습니다.
    그래서 관객용 조회 경로는 이 값을 **파라미터로 받지 않고** 서버가 고정합니다.
    """

    AUDIENCE = "audience"
    STAFF = "staff"
    BOTH = "both"


class AnnouncementLevel(str, enum.Enum):
    """공지의 급함.

    `NORMAL` 은 상단 배너로 흘려보냅니다. `URGENT` 는 화면을 덮고 확인을 받습니다 —
    우천 중단이나 안전 안내를 배너로 두면 스크롤 한 번에 사라지고, 그건 안내하지
    않은 것과 같습니다.

    등급을 셋 이상으로 늘리지 않은 이유는 운영자가 매번 고민해야 하고 실제로는
    대부분 가장 약한 등급으로 몰리기 때문입니다.
    """

    NORMAL = "normal"
    URGENT = "urgent"
