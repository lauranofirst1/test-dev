"""모든 모델을 여기서 import 합니다.

Alembic 의 autogenerate 가 metadata 를 훑을 때 모델이 로드돼 있어야 하므로,
새 모델 파일을 만들면 반드시 여기에 추가하세요. 빠뜨리면 조용히 테이블이 누락됩니다.
"""

from festaflow.db.base import Base
from festaflow.models.account import OrganizationAccount, PasswordResetToken
from festaflow.models.announcement import Announcement, AnnouncementAck
from festaflow.models.booth import Booth, Mission
from festaflow.models.diagnosis import (
    Diagnosis,
    DiagnosisItem,
    RubricCalibration,
    TourismSnapshot,
)
from festaflow.models.exhibit import (
    AudienceVote,
    Exhibit,
    JudgeScore,
    VoteCriterion,
)
from festaflow.models.festival import (
    Festival,
    FestivalPlan,
    FestivalStaff,
    Organization,
)
from festaflow.models.kpi import BUILTIN_METRICS, KpiTarget
from festaflow.models.lecture import (
    LectureSession,
    SessionAttendance,
    SessionCheckpoint,
)
from festaflow.models.ops import RecommendationFeedback, RewardCampaign, VisitorCount
from festaflow.models.participation import (
    BoothScanUse,
    MissionAttempt,
    Participant,
    Participation,
)
from festaflow.models.prize import Prize, PrizeDraw
from festaflow.models.stamp import StampBoard, StampReveal, StampTile

__all__ = [
    "Base",
    "Announcement",
    "AnnouncementAck",
    "AudienceVote",
    "Booth",
    "BoothScanUse",
    "Diagnosis",
    "DiagnosisItem",
    "Exhibit",
    "Festival",
    "FestivalPlan",
    "FestivalStaff",
    "Mission",
    "MissionAttempt",
    "JudgeScore",
    "BUILTIN_METRICS",
    "KpiTarget",
    "LectureSession",
    "Organization",
    "OrganizationAccount",
    "Participant",
    "PasswordResetToken",
    "Participation",
    "Prize",
    "PrizeDraw",
    "RecommendationFeedback",
    "RewardCampaign",
    "RubricCalibration",
    "SessionAttendance",
    "SessionCheckpoint",
    "StampBoard",
    "StampReveal",
    "StampTile",
    "TourismSnapshot",
    "VoteCriterion",
    "VisitorCount",
]
