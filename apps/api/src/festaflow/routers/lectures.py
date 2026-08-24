"""특강 세션 · 체크인 · 출결 — 공결이 걸린 강의의 출튀 방지.

운영자 경로와 참여자 경로가 **한 파일에 있지만 인증 경계는 다릅니다.**
운영자 쪽은 기관 스코프를, 참여자 쪽은 `X-Participant-Secret` 만 봅니다.
경계마다 의존성이 다르니 함수 시그니처를 보면 어느 쪽인지 알 수 있습니다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.core.deps import (
    CanOperate,
    CurrentOrg,
    CurrentParticipant,
    DbSession,
    FestivalAccess,
    OptionalStaff,
)
from festaflow.core.errors import ApiError, not_found
from festaflow.models import (
    Festival,
    LectureSession,
    SessionAttendance,
    SessionCheckpoint,
)
from festaflow.schemas.lecture import (
    CertificateIssued,
    CertificateOut,
    CheckInIn,
    CheckInResult,
    CheckpointOut,
    CheckpointToken,
    LectureSessionDetail,
    LectureSessionIn,
    LectureSessionList,
    LectureSessionOut,
    MyAttendance,
    RosterOut,
    RosterRow,
)
from festaflow.services import attendance as svc

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["lectures"])

#: 운영자 경로에만 붙인다. 참여자 경로는 기관 스코프를 쓰지 않는다.
OPERATOR = [FestivalAccess]


def _owned(db: Session, org_id: int, festival_id: int) -> Festival:
    f = db.execute(
        select(Festival).where(
            Festival.id == festival_id,
            Festival.organization_id == org_id,
            Festival.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if f is None:
        raise not_found("축제")
    return f


def _live(db: Session, festival_id: int) -> Festival:
    f = db.execute(
        select(Festival).where(Festival.id == festival_id, Festival.archived_at.is_(None))
    ).scalar_one_or_none()
    if f is None:
        raise not_found("축제")
    return f


def _detail(db: Session, session: LectureSession) -> LectureSessionDetail:
    opened = db.execute(
        select(func.count(SessionCheckpoint.id)).where(
            SessionCheckpoint.session_id == session.id
        )
    ).scalar_one()
    rows = svc.roster(db, session)
    return LectureSessionDetail(
        **LectureSessionOut.model_validate(session).model_dump(),
        opened_checkpoints=int(opened),
        attendee_count=len(rows),
        met_count=sum(1 for _, n in rows if n >= session.required_checkins),
    )


# ── 운영자: 세션 ────────────────────────────────────────────────────────────


@router.get("/lectures", response_model=LectureSessionList, dependencies=OPERATOR)
def list_lectures(festival_id: int, db: DbSession, org: CurrentOrg) -> LectureSessionList:
    _owned(db, org.id, festival_id)
    sessions = list(
        db.execute(
            select(LectureSession)
            .where(
                LectureSession.festival_id == festival_id,
                LectureSession.archived_at.is_(None),
            )
            .order_by(LectureSession.starts_at)
        ).scalars()
    )
    items = [_detail(db, s) for s in sessions]
    return LectureSessionList(items=items, total=len(items))


@router.post(
    "/lectures",
    response_model=LectureSessionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[*OPERATOR, CanOperate],
)
def create_lecture(
    festival_id: int, payload: LectureSessionIn, db: DbSession, org: CurrentOrg
) -> LectureSessionOut:
    festival = _owned(db, org.id, festival_id)
    session = LectureSession(festival_id=festival.id, **payload.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return LectureSessionOut.model_validate(session)


@router.put(
    "/lectures/{session_id}",
    response_model=LectureSessionOut,
    dependencies=[*OPERATOR, CanOperate],
)
def update_lecture(
    festival_id: int,
    session_id: int,
    payload: LectureSessionIn,
    db: DbSession,
    org: CurrentOrg,
) -> LectureSessionOut:
    _owned(db, org.id, festival_id)
    session = svc.get_session(db, festival_id, session_id)
    for k, v in payload.model_dump().items():
        setattr(session, k, v)
    db.commit()
    db.refresh(session)
    return LectureSessionOut.model_validate(session)


@router.post(
    "/lectures/{session_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[*OPERATOR, CanOperate],
)
def archive_lecture(
    festival_id: int, session_id: int, db: DbSession, org: CurrentOrg
) -> None:
    _owned(db, org.id, festival_id)
    session = svc.get_session(db, festival_id, session_id)
    session.archived_at = datetime.now(UTC)
    session.is_active = False
    db.commit()


# ── 운영자: 체크인 ──────────────────────────────────────────────────────────


def _checkpoint_out(db: Session, cp: SessionCheckpoint) -> CheckpointOut:
    count = db.execute(
        select(func.count(SessionAttendance.id)).where(
            SessionAttendance.checkpoint_id == cp.id
        )
    ).scalar_one()
    return CheckpointOut(
        id=cp.id,
        session_id=cp.session_id,
        sequence=cp.sequence,
        opens_at=cp.opens_at,
        closes_at=cp.closes_at,
        is_open=svc.is_open(cp),
        checked_count=int(count),
    )


@router.get(
    "/lectures/{session_id}/checkpoints",
    response_model=list[CheckpointOut],
    dependencies=OPERATOR,
)
def list_checkpoints(
    festival_id: int, session_id: int, db: DbSession, org: CurrentOrg
) -> list[CheckpointOut]:
    _owned(db, org.id, festival_id)
    session = svc.get_session(db, festival_id, session_id)
    rows = list(
        db.execute(
            select(SessionCheckpoint)
            .where(SessionCheckpoint.session_id == session.id)
            .order_by(SessionCheckpoint.sequence.desc())
        ).scalars()
    )
    return [_checkpoint_out(db, cp) for cp in rows]


@router.post(
    "/lectures/{session_id}/checkpoints",
    response_model=CheckpointToken,
    status_code=status.HTTP_201_CREATED,
    dependencies=[*OPERATOR, CanOperate],
)
def open_checkpoint(
    festival_id: int,
    session_id: int,
    request: Request,
    db: DbSession,
    org: CurrentOrg,
    staff: OptionalStaff,
) -> CheckpointToken:
    """지금 체크인을 연다 — 강의 중 예고 없이 누른다.

    **언제 누를지 알려주지 않는 것이 이 장치의 전부입니다.** 시간표에 적어 두면
    그 시각에만 자리에 있으면 되고, 출튀는 그대로입니다.
    """
    _owned(db, org.id, festival_id)
    session = svc.get_session(db, festival_id, session_id)
    checkpoint = svc.open_checkpoint(db, session, staff_id=staff.id if staff else None)
    db.commit()
    db.refresh(checkpoint)
    return _token_for(request, festival_id, session, checkpoint)


def _token_for(
    request: Request,
    festival_id: int,
    session: LectureSession,
    checkpoint: SessionCheckpoint,
) -> CheckpointToken:
    window = security.current_window()
    token = svc.checkpoint_token(session.qr_secret, checkpoint.id, window)
    # 특강 id 를 함께 담는다. 없으면 참여자 화면이 어느 특강의 체크인인지 몰라
    # 자기 특강 목록을 하나씩 시도해 보게 되고, 열려 있는 시간이 90초뿐인
    # 화면에서 그 왕복은 그대로 실패가 된다.
    path = f"/join/{festival_id}/checkin?s={session.id}&c={checkpoint.id}&t={token}"
    base = (settings.public_web_origin or str(request.base_url)).rstrip("/")
    return CheckpointToken(
        checkpoint_id=checkpoint.id,
        sequence=checkpoint.sequence,
        scan_path=path,
        scan_url=f"{base}{path}",
        expires_at=security.window_expires_at(window),
        closes_at=checkpoint.closes_at,
        refresh_after_seconds=settings.scan_token_window_seconds,
    )


@router.get(
    "/lectures/{session_id}/checkpoints/{checkpoint_id}/token",
    response_model=CheckpointToken,
    dependencies=OPERATOR,
)
def checkpoint_token(
    festival_id: int,
    session_id: int,
    checkpoint_id: int,
    request: Request,
    db: DbSession,
    org: CurrentOrg,
) -> CheckpointToken:
    """스크린용 회전 QR. 30초마다 다시 받는다."""
    _owned(db, org.id, festival_id)
    session = svc.get_session(db, festival_id, session_id)
    checkpoint = db.get(SessionCheckpoint, checkpoint_id)
    if checkpoint is None or checkpoint.session_id != session.id:
        raise not_found("체크인")
    return _token_for(request, festival_id, session, checkpoint)


# ── 운영자: 명단 ────────────────────────────────────────────────────────────


@router.get("/lectures/{session_id}/roster", response_model=RosterOut, dependencies=OPERATOR)
def roster(festival_id: int, session_id: int, db: DbSession, org: CurrentOrg) -> RosterOut:
    """공결 명단. **학번이 나가는 유일한 경로다.**"""
    _owned(db, org.id, festival_id)
    session = svc.get_session(db, festival_id, session_id)
    opened = db.execute(
        select(func.count(SessionCheckpoint.id)).where(
            SessionCheckpoint.session_id == session.id
        )
    ).scalar_one()

    rows = [
        RosterRow(
            participant_code=p.code,
            student_no=p.student_no,
            checked=n,
            required=session.required_checkins,
            is_met=n >= session.required_checkins,
            recovery_attempts=p.recovery_attempts or 0,
        )
        for p, n in svc.roster(db, session)
    ]
    return RosterOut(
        session_id=session.id,
        title=session.title,
        opened_checkpoints=int(opened),
        required_checkins=session.required_checkins,
        grants_excused_absence=session.grants_excused_absence,
        rows=rows,
        met_count=sum(1 for r in rows if r.is_met),
        total=len(rows),
    )


# ── 참여자 ──────────────────────────────────────────────────────────────────


def _mine(db: Session, session: LectureSession, participant_id: int) -> MyAttendance:
    r = svc.result_for(db, session, participant_id)
    return MyAttendance(
        session_id=session.id,
        title=session.title,
        starts_at=session.starts_at,
        ends_at=session.ends_at,
        grants_excused_absence=session.grants_excused_absence,
        checked=r.checked,
        required=r.required,
        opened=r.opened,
        is_met=r.is_met,
        remaining=r.remaining,
    )


@router.get(
    "/lectures/{session_id}/certificate",
    response_model=CertificateIssued,
)
def issue_certificate(
    festival_id: int,
    session_id: int,
    db: DbSession,
    participant: CurrentParticipant,
) -> CertificateIssued:
    """공결 확인서를 발급한다. **학생 본인만.**

    코드는 HMAC 으로 파생되므로 몇 번을 불러도 같은 값이 나옵니다 — 발급이라기보다
    조회에 가깝고, 그래서 학생이 잃어버려도 다시 열면 그만입니다.
    """
    session = svc.get_session(db, festival_id, session_id)
    result = svc.result_for(db, session, participant.id)
    if result.checked == 0:
        # 한 번도 안 찍은 사람에게 확인서를 만들어 주면 그 확인서는
        # "안 왔다" 를 증명하는 종이가 된다. 그건 확인서가 아니다.
        raise ApiError(
            409,
            "NO_ATTENDANCE",
            "이 특강에 체크인한 기록이 없습니다.",
            {"session_id": session.id},
        )

    code = security.attendance_certificate_code(
        session.qr_secret, session.id, participant.id
    )
    return CertificateIssued(
        session_id=session.id,
        title=session.title,
        code=code,
        verify_path=f"/verify/{festival_id}/{code}",
    )


@router.get("/attendance-certificates/{code}", response_model=CertificateOut)
def verify_certificate(festival_id: int, code: str, db: DbSession) -> CertificateOut:
    """확인 코드로 출결을 조회한다. **인증이 없습니다.**

    교수님은 이 시스템의 사용자가 아닙니다. 계정을 발급하려면 수십 명에게
    나눠 줘야 하고, 그렇게 만든 절차는 쓰이지 않습니다. 대신 학생이 스스로
    증명을 건네고, 코드가 그 증명의 진위를 담보합니다.

    코드가 틀리면 **404** 입니다 — 형식이 맞는지 틀린지를 구분해 주면
    코드를 훑어 볼 수 있습니다.
    """
    festival = db.execute(
        select(Festival).where(
            Festival.id == festival_id, Festival.archived_at.is_(None)
        )
    ).scalar_one_or_none()
    if festival is None:
        raise not_found("축제")

    cert = svc.certificate_for(db, festival_id, code)
    if cert is None:
        raise not_found("확인서")

    return CertificateOut(
        festival_name=festival.name,
        title=cert.session.title,
        speaker=cert.session.speaker,
        starts_at=cert.session.starts_at,
        ends_at=cert.session.ends_at,
        student_no_masked=cert.student_no_masked,
        participant_code=cert.participant_code,
        checked=cert.checked,
        opened=cert.opened,
        required=cert.required,
        is_met=cert.is_met,
        grants_excused_absence=cert.grants_excused_absence,
        verified_at=datetime.now(UTC),
    )


@router.get("/lectures/me", response_model=list[MyAttendance])
def my_attendance(
    festival_id: int, db: DbSession, participant: CurrentParticipant
) -> list[MyAttendance]:
    """내 출결. 몇 번 찍었고 몇 번을 놓쳤는지 스스로 볼 수 있어야 한다."""
    _live(db, festival_id)
    sessions = list(
        db.execute(
            select(LectureSession)
            .where(
                LectureSession.festival_id == festival_id,
                LectureSession.archived_at.is_(None),
                LectureSession.is_active.is_(True),
            )
            .order_by(LectureSession.starts_at)
        ).scalars()
    )
    return [_mine(db, s, participant.id) for s in sessions]


@router.post("/lectures/{session_id}/checkin", response_model=CheckInResult)
def check_in(
    festival_id: int,
    session_id: int,
    payload: CheckInIn,
    db: DbSession,
    participant: CurrentParticipant,
) -> CheckInResult:
    """체크인 QR 을 찍었다."""
    _live(db, festival_id)
    session = svc.get_session(db, festival_id, session_id)
    checkpoint = db.get(SessionCheckpoint, payload.checkpoint_id)
    if checkpoint is None:
        raise not_found("체크인")

    record, was_new = svc.check_in(
        db,
        session=session,
        checkpoint=checkpoint,
        participant=participant,
        token=payload.token,
    )
    db.commit()

    return CheckInResult(
        was_new=was_new,
        sequence=checkpoint.sequence,
        attendance=_mine(db, session, participant.id),
    )
