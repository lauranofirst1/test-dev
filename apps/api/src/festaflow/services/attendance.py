"""특강 출결 — 예고 없는 다중 체크인.

**입장 스캔 한 번은 출석을 증명하지 않습니다.** 찍고 나가면 그만이고, 공결이
걸려 있으면 그렇게 하는 사람이 반드시 생깁니다. 퇴장 스캔을 더해도 중간에
나갔다가 끝날 때 돌아오면 같습니다.

그래서 **언제 열릴지 모르는 확인을 여러 번** 둡니다. 자리를 뜨면 놓칩니다.

체크인 QR 은 회전합니다. 인쇄 QR 을 쓰면 사진 한 장이 단톡방에 돌면서 출결이
통째로 무너집니다 — 부스 지급에서는 인쇄가 합리적인 선택지였지만 여기서는
아닙니다. 그래서 이 모듈은 인쇄 서명을 아예 다루지 않습니다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.errors import ApiError, not_found
from festaflow.models import (
    LectureSession,
    Participant,
    SessionAttendance,
    SessionCheckpoint,
)

#: 체크인이 열려 있는 시간. 짧아야 "그때 그 자리에 있었다"를 증명한다.
#:
#: 너무 짧으면 폰을 꺼내는 사이에 닫히고, 길면 늦게 들어온 사람도 전부 찍힌다.
#: 90초는 강의실에서 "지금 QR 띄웁니다" 를 듣고 꺼내 찍기에 충분하면서,
#: 옆 건물에서 뛰어오기에는 모자란 길이다.
CHECKPOINT_OPEN_SECONDS = 90


def checkpoint_token(qr_secret: bytes, checkpoint_id: int, window_index: int) -> str:
    """체크인 QR 토큰. 부스 토큰과 **메시지 접두어가 다르다.**

    같은 방식이지만 섞이면 안 됩니다 — 부스 토큰이 출결로 통하거나 그 반대가
    되면 두 기능이 서로의 구멍이 됩니다.
    """
    msg = f"checkin|{checkpoint_id}|{window_index}".encode()
    digest = hmac.new(qr_secret, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:12]


def match_checkpoint_window(
    qr_secret: bytes, checkpoint_id: int, token: str, now: datetime | None = None
) -> int | None:
    """현재와 직전 window 를 인정한다. 갱신 직전에 찍은 사람을 실패시키지 않는다."""
    current = security.current_window(now)
    for candidate in (current, current - 1):
        if hmac.compare_digest(
            checkpoint_token(qr_secret, checkpoint_id, candidate), token
        ):
            return candidate
    return None


# ── 세션 ────────────────────────────────────────────────────────────────────


def get_session(db: Session, festival_id: int, session_id: int) -> LectureSession:
    s = db.execute(
        select(LectureSession).where(
            LectureSession.id == session_id,
            LectureSession.festival_id == festival_id,
            LectureSession.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if s is None:
        raise not_found("특강")
    return s


def open_checkpoint(
    db: Session,
    session: LectureSession,
    *,
    staff_id: int | None = None,
    seconds: int = CHECKPOINT_OPEN_SECONDS,
    now: datetime | None = None,
) -> SessionCheckpoint:
    """지금 체크인을 연다. 운영자가 강의 중 아무 때나 누른다."""
    at = now or datetime.now(UTC)

    used = db.execute(
        select(func.coalesce(func.max(SessionCheckpoint.sequence), 0)).where(
            SessionCheckpoint.session_id == session.id
        )
    ).scalar_one()

    checkpoint = SessionCheckpoint(
        session_id=session.id,
        sequence=used + 1,
        opens_at=at,
        closes_at=at + timedelta(seconds=seconds),
        opened_by_staff_id=staff_id,
    )
    db.add(checkpoint)
    db.flush()
    return checkpoint


def is_open(checkpoint: SessionCheckpoint, *, now: datetime | None = None) -> bool:
    at = now or datetime.now(UTC)
    return checkpoint.opens_at <= at < checkpoint.closes_at


# ── 체크인 ──────────────────────────────────────────────────────────────────


def check_in(
    db: Session,
    *,
    session: LectureSession,
    checkpoint: SessionCheckpoint,
    participant: Participant,
    token: str,
    now: datetime | None = None,
) -> tuple[SessionAttendance, bool]:
    """체크인 한 건. `(기록, 방금_새로_찍혔는가)` 를 돌려준다."""
    at = now or datetime.now(UTC)

    if checkpoint.session_id != session.id:
        raise not_found("체크인")

    if not is_open(checkpoint, now=at):
        raise ApiError(
            410,
            "CHECKPOINT_CLOSED",
            "체크인 시간이 지났습니다. 다음 체크인 때 다시 찍어 주세요.",
            {"closes_at": checkpoint.closes_at.isoformat()},
        )

    if match_checkpoint_window(session.qr_secret, checkpoint.id, token, at) is None:
        raise ApiError(
            400,
            "CHECKIN_TOKEN_INVALID",
            "이 특강의 체크인 QR 이 아닙니다. 화면의 QR 을 다시 찍어 주세요.",
        )

    record = SessionAttendance(
        session_id=session.id,
        checkpoint_id=checkpoint.id,
        participant_id=participant.id,
        checked_at=at,
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
    except IntegrityError:
        # 같은 체크인에 두 번 찍었다. 두 번째는 아무 일도 아니다 — 오류가 아니라
        # "이미 찍혔습니다" 로 답한다.
        #
        # savepoint 롤백이 객체를 이미 세션에서 떼어냈을 수 있다. 무조건
        # expunge 하면 InvalidRequestError 가 나 원래 오류를 덮어쓴다.
        if record in db:
            db.expunge(record)
        existing = db.execute(
            select(SessionAttendance).where(
                SessionAttendance.checkpoint_id == checkpoint.id,
                SessionAttendance.participant_id == participant.id,
            )
        ).scalar_one()
        return existing, False

    return record, True


# ── 판정 ────────────────────────────────────────────────────────────────────


@dataclass
class AttendanceResult:
    """한 참여자의 출석 판정."""

    checked: int
    #: 지금까지 열린 체크인 수. 강의 중에는 계속 늘어난다.
    opened: int
    required: int
    #: 가장 최근 체크인 시각. 출석 인정 여부는 호출자가 함께 확인한다.
    completed_at: datetime | None = None

    @property
    def is_met(self) -> bool:
        return self.checked >= self.required

    @property
    def remaining(self) -> int:
        """앞으로 몇 번 더 찍어야 하는가. 이미 채웠으면 0."""
        return max(0, self.required - self.checked)


def result_for(
    db: Session, session: LectureSession, participant_id: int
) -> AttendanceResult:
    checked, completed_at = db.execute(
        select(
            func.count(SessionAttendance.id),
            func.max(SessionAttendance.checked_at),
        ).where(
            SessionAttendance.session_id == session.id,
            SessionAttendance.participant_id == participant_id,
        )
    ).one()
    opened = db.execute(
        select(func.count(SessionCheckpoint.id)).where(
            SessionCheckpoint.session_id == session.id
        )
    ).scalar_one()
    return AttendanceResult(
        checked=int(checked),
        opened=int(opened),
        required=session.required_checkins,
        completed_at=completed_at,
    )


# ── 공결 확인서 ─────────────────────────────────────────────────────────────


@dataclass
class Certificate:
    """교수님이 보는 확인 결과.

    **학번을 통째로 보여주지 않습니다.** 교수는 "이 학생이 왔는가" 를 확인하려는
    것이지 명단을 수집하려는 것이 아닙니다. 코드가 유출됐을 때 새어 나가는 정보를
    최소로 줄이되, 본인 확인이 가능할 만큼은 남깁니다.
    """

    session: LectureSession
    #: 뒷 세 자리만. 앞자리는 학번 체계상 학과·학번을 그대로 노출한다.
    student_no_masked: str | None
    participant_code: str
    checked: int
    opened: int
    required: int
    is_met: bool
    #: 이 특강이 애초에 공결 대상인가. 아니면 확인서의 뜻이 다르다.
    grants_excused_absence: bool


def mask_student_no(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 3:
        return "*" * len(value)
    return "*" * (len(value) - 3) + value[-3:]


def certificate_for(
    db: Session, festival_id: int, code: str
) -> Certificate | None:
    """확인 코드로 출결을 조회한다. **인증 없이 불린다.**

    코드 자체가 비밀입니다. 교수님에게 계정을 발급하는 대신 이 방식을 쓰는 이유는,
    공결을 인정하는 사람이 특강 주최자가 아니라 **그 시간 정규 수업 담당 교수**라서
    수십 명에게 계정을 나눠 줘야 하기 때문입니다. 쓰이지 않을 절차를 만드는 것보다
    학생이 스스로 증명을 건네는 쪽이 실제로 돌아갑니다.

    코드에서 세션과 참여자를 **역산할 수 없으므로** 축제 안의 모든 (세션, 참여자)
    조합을 훑어 맞춰 봅니다. 특강 수와 참여자 수가 곱해지지만, 이 조회는 학기당
    수십 건이고 인덱스가 있는 단순 조회라 감당할 수 있습니다. 코드에 id 를 심어
    보내면 그 순간 남의 확인서를 만들어 볼 수 있는 표면이 생깁니다.
    """
    sessions = list(
        db.execute(
            select(LectureSession).where(
                LectureSession.festival_id == festival_id,
                LectureSession.archived_at.is_(None),
            )
        ).scalars()
    )
    for session in sessions:
        # 이 특강에 실제로 찍은 사람만 후보다. 온 적 없는 사람의 확인서는
        # 애초에 존재하지 않는다.
        rows = db.execute(
            select(Participant)
            .join(SessionAttendance, SessionAttendance.participant_id == Participant.id)
            .where(SessionAttendance.session_id == session.id)
            .distinct()
        ).scalars()
        for participant in rows:
            if security.match_certificate_code(
                session.qr_secret, session.id, participant.id, code
            ):
                result = result_for(db, session, participant.id)
                return Certificate(
                    session=session,
                    student_no_masked=mask_student_no(participant.student_no),
                    participant_code=participant.code,
                    checked=result.checked,
                    opened=result.opened,
                    required=result.required,
                    is_met=result.is_met,
                    grants_excused_absence=session.grants_excused_absence,
                )
    return None


def roster(db: Session, session: LectureSession) -> list[tuple[Participant, int]]:
    """참여자별 체크인 횟수. 공결 명단의 재료다.

    체크인을 한 번도 안 한 사람은 나오지 않습니다 — 이 세션에 온 적이 없다는
    뜻이고, 명단에 0회로 올리면 "왔는데 못 찍은 사람"과 구분되지 않습니다.
    """
    rows = db.execute(
        select(Participant, func.count(SessionAttendance.id))
        .join(SessionAttendance, SessionAttendance.participant_id == Participant.id)
        .where(SessionAttendance.session_id == session.id)
        .group_by(Participant.id)
        .order_by(func.count(SessionAttendance.id).desc(), Participant.code)
    ).all()
    return [(p, int(n)) for p, n in rows]
