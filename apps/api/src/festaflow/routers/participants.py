"""참여자 · 공개 정보 · 참여자 스캔 지급 — docs/03-api-contract.md §8.3, §9.

이 라우터는 **기관 스코프를 쓰지 않습니다.** 관객은 로그인하지 않고 축제 링크로
들어옵니다. 대신 조회 범위를 축제 하나로 못 박고, 본인 데이터는
`X-Participant-Secret` 으로만 열어 줍니다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from festaflow.core.deps import CurrentParticipant, DbSession
from festaflow.core.errors import ApiError, not_found
from festaflow.models import (
    Booth,
    Exhibit,
    Festival,
    LectureSession,
    Mission,
    Participation,
    Prize,
)
from festaflow.models.enums import BoothQrMode, BoothVerifyMode
from festaflow.routers import stamp_board as board_svc
from festaflow.schemas.participation import (
    ActiveCampaign,
    GrantResult,
    MissionStatus,
    ParticipantIssue,
    ParticipantIssued,
    ParticipantMe,
    ParticipantOverview,
    PublicBooth,
    PublicFestival,
    PublicMission,
    ScanContext,
    ScanContextMission,
    ScanGrantIn,
)
from festaflow.schemas.prize import (
    PrizeDrawOut,
    PrizeDrawStatus,
    PrizePreview,
)
from festaflow.services import experience as exp
from festaflow.services import grants as svc
from festaflow.services import prizes as prize_svc

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["participants"])


def _live_festival(db: Session, festival_id: int) -> Festival:
    f = db.execute(
        select(Festival).where(Festival.id == festival_id, Festival.archived_at.is_(None))
    ).scalar_one_or_none()
    if f is None:
        raise not_found("축제")
    return f


def _active_booths(db: Session, festival_id: int) -> list[Booth]:
    return list(
        db.execute(
            select(Booth)
            .where(
                Booth.festival_id == festival_id,
                Booth.archived_at.is_(None),
                Booth.is_active.is_(True),
            )
            .order_by(Booth.id)
        ).scalars()
    )


def _active_missions(db: Session, festival_id: int) -> list[Mission]:
    return list(
        db.execute(
            select(Mission)
            .where(
                Mission.festival_id == festival_id,
                Mission.archived_at.is_(None),
                Mission.is_active.is_(True),
                Mission.booth_id.is_not(None),
            )
            .order_by(Mission.id)
        ).scalars()
    )


# ── 공개 정보 ───────────────────────────────────────────────────────────────


@router.get("/public", response_model=PublicFestival)
def public_festival(festival_id: int, db: DbSession) -> PublicFestival:
    """참여 전 관객이 보는 화면. 인증이 없으므로 운영 정보는 담지 않는다."""
    festival = _live_festival(db, festival_id)
    missions = _active_missions(db, festival_id)
    by_booth: dict[int, list[Mission]] = {}
    for m in missions:
        by_booth.setdefault(m.booth_id, []).append(m)

    return PublicFestival(
        id=festival.id,
        name=festival.name,
        region=festival.region,
        venue=festival.venue,
        starts_on=festival.starts_on.isoformat(),
        ends_on=festival.ends_on.isoformat(),
        booths=[
            PublicBooth(
                id=b.id,
                name=b.name,
                booth_type=b.booth_type,
                type_label=b.type_label,
                location=b.location,
                verify_mode=b.verify_mode,
                missions=[PublicMission.model_validate(m) for m in by_booth.get(b.id, [])],
            )
            for b in _active_booths(db, festival_id)
        ],
        identity_mode=festival.identity_mode,
        # 있고 없음만. 탭을 띄울지 정하는 데 필요한 전부다.
        has_lectures=db.execute(
            select(func.count(LectureSession.id)).where(
                LectureSession.festival_id == festival_id,
                LectureSession.is_active.is_(True),
            )
        ).scalar_one()
        > 0,
        has_exhibits=db.execute(
            select(func.count(Exhibit.id)).where(
                Exhibit.festival_id == festival_id,
                Exhibit.is_active.is_(True),
            )
        ).scalar_one()
        > 0,
    )


# ── 발급 · 본인 조회 ────────────────────────────────────────────────────────


@router.post(
    "/participants", response_model=ParticipantIssued, status_code=status.HTTP_201_CREATED
)
def issue_participant(
    festival_id: int, db: DbSession, payload: ParticipantIssue | None = None
) -> ParticipantIssued:
    """참여 코드를 발급한다.

    익명 축제에서는 이름도 연락처도 받지 않습니다 — 지나가는 관광객에게 신원을
    요구할 수 없기 때문입니다.

    학번 축제(교내 행사)에서는 학번을 받습니다. **1 학번 = 1 참여자**이며, 이미
    발급된 학번이면 새로 만들지 않고 비밀만 새로 냅니다. 여기서 새 참여자를
    만들면 학번 하나가 코드 여러 개를 갖게 되고, 그건 종이 스티커를 여러 장
    붙이는 것과 정확히 같습니다.
    """
    festival = _live_festival(db, festival_id)
    before = svc.find_by_student_no(db, festival.id, payload.student_no) if (
        payload and payload.student_no
    ) else None

    participant, secret = svc.issue_participant(
        db, festival, student_no=payload.student_no if payload else None
    )
    db.commit()
    db.refresh(participant)
    return ParticipantIssued(
        code=participant.code,
        secret=secret,
        festival_id=festival.id,
        resumed=before is not None,
    )


#: `last_seen_at` 을 다시 쓰기까지 두는 최소 간격.
#:
#: 이 값은 "마지막으로 화면을 보고 있었나" 를 대략 알기 위한 것이지 초 단위
#: 정확도가 필요한 값이 아니다. 그런데 관객 화면이 주기적으로 이 조회를 하므로,
#: 매번 쓰면 **참여자 수 × 폴링 주기만큼 쓰기가 발생한다** — 1000명이 붙으면
#: 10초마다 1000번이다. 조회가 쓰기를 만드는 구조는 그 자체로 확장되지 않는다.
LAST_SEEN_MIN_INTERVAL = timedelta(minutes=1)


def _touch_last_seen(db: Session, participant) -> None:
    """마지막 접속 시각을 **가끔만** 갱신한다."""
    now = datetime.now(UTC)
    seen = participant.last_seen_at
    if seen is not None and seen.tzinfo is None:
        # 드라이버 설정에 따라 naive 로 올라올 수 있다. UTC 로 읽는다.
        seen = seen.replace(tzinfo=UTC)
    if seen is not None and now - seen < LAST_SEEN_MIN_INTERVAL:
        return
    participant.last_seen_at = now
    db.commit()


def _me_payload(db: Session, festival_id: int, participant) -> ParticipantMe:
    """미션별 지급 상태와 포인트 합계. 활성 캠페인 안내를 함께 싣는다."""
    granted = {
        p.mission_id: p
        for p in db.execute(
            select(Participation).where(
                Participation.participant_id == participant.id,
                Participation.mission_id.is_not(None),
            )
        ).scalars()
    }
    booth_names = {
        b.id: b.name for b in _active_booths(db, festival_id)
    }

    statuses: list[MissionStatus] = []
    for m in _active_missions(db, festival_id):
        p = granted.get(m.id)
        statuses.append(
            MissionStatus(
                mission_id=m.id,
                booth_id=m.booth_id,
                booth_name=booth_names.get(m.booth_id),
                title=m.title,
                points=m.points,
                status="granted" if p else "pending",
                granted_points=p.granted_points if p else None,
                completed_at=p.completed_at if p else None,
            )
        )

    total = db.execute(
        select(func.coalesce(func.sum(Participation.granted_points), 0)).where(
            Participation.participant_id == participant.id
        )
    ).scalar_one()

    _touch_last_seen(db, participant)

    return ParticipantMe(
        code=participant.code,
        festival_id=festival_id,
        total_points=int(total),
        completed_count=len(granted),
        missions=statuses,
        active_campaigns=[
            ActiveCampaign(
                id=c.id,
                booth_id=c.booth_id,
                mission_id=c.mission_id,
                title=c.title,
                message=c.message,
                bonus_points=c.bonus_points,
                ends_at=c.ends_at,
            )
            for c in svc.active_campaigns(db, festival_id)
        ],
    )


@router.get("/participants/me", response_model=ParticipantMe)
def participant_me(
    festival_id: int, db: DbSession, participant: CurrentParticipant
) -> ParticipantMe:
    """미션별 지급 상태와 포인트 합계. 활성 캠페인 안내를 함께 싣는다."""
    _live_festival(db, festival_id)
    return _me_payload(db, festival_id, participant)


# ── 부스 QR 스캔 (§8.3) ─────────────────────────────────────────────────────


def _scan_booth(db: Session, festival_id: int, booth_id: int) -> Booth:
    booth = db.execute(
        select(Booth).where(
            Booth.id == booth_id,
            Booth.festival_id == festival_id,
            Booth.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if booth is None:
        raise not_found("부스")
    if booth.verify_mode != BoothVerifyMode.PARTICIPANT_SCAN:
        raise ApiError(
            409,
            "BOOTH_MODE_MISMATCH",
            "이 부스는 스태프가 확인해 지급합니다. 스태프에게 참여 코드를 보여주세요.",
            {"verify_mode": booth.verify_mode.value},
        )
    return booth


@router.get("/scan", response_model=ScanContext)
def scan_context(
    festival_id: int,
    db: DbSession,
    participant: CurrentParticipant,
    booth_id: int = Query(...),
    # 회전 QR 은 `t`(토큰), 인쇄 QR 은 `s`(고정 서명)를 담아 온다 — 계약 §14.4.
    # 어느 쪽을 받을지는 부스의 qr_mode 가 정한다.
    token: str | None = Query(None),
    signature: str | None = Query(None, alias="s"),
) -> ScanContext:
    """스캔 직후 체험 화면에 필요한 것만 돌려준다.

    `experience_config` 는 **정답을 뺀 사본**이다. quiz 의 `answer_index` 는
    여기 담기지 않으며 채점은 서버에서만 한다 — 문항과 보기는 화면이 그려야
    하므로 내려가지만, 정답이 함께 가면 개발자 도구로 전부 통과된다.
    """
    _live_festival(db, festival_id)
    booth = _scan_booth(db, festival_id, booth_id)

    # 예산을 먼저 정한다. 퀴즈가 붙은 부스는 30초로 끝나지 않는다.
    missions = [m for m in _active_missions(db, festival_id) if m.booth_id == booth.id]
    windows = exp.accepted_windows(missions)
    window = svc.verify_scan_proof(
        booth, token=token, signature=signature, windows=windows
    )

    from festaflow.core import security

    expires_at = security.window_expires_at(window)
    # 서버가 **실제로 받아주는** 마지막 시각. 화면은 이 값으로 카운트다운해야
    # 서버가 아직 받아줄 시간을 화면이 먼저 포기하지 않는다.
    accepted_until = security.window_expires_at(window + windows - 1)
    # 인쇄 QR 은 만료되지 않는다. 카운트다운을 내려보내면 화면이 없는 제한 시간을
    # 만들어 내고, 0 이 되는 순간 멀쩡한 QR 을 두고 "다시 찍으라"고 말한다.
    printed = booth.qr_mode == BoothQrMode.PRINTED
    granted = {
        p.mission_id
        for p in db.execute(
            select(Participation).where(
                Participation.participant_id == participant.id,
                Participation.mission_id.is_not(None),
            )
        ).scalars()
    }

    return ScanContext(
        booth_id=booth.id,
        booth_name=booth.name,
        type_label=booth.type_label,
        location=booth.location,
        window_index=window,
        expires_at=expires_at,
        accepted_until=accepted_until,
        seconds_remaining=(
            None
            if printed
            else max(0, int((accepted_until - datetime.now(UTC)).total_seconds()))
        ),
        qr_mode=booth.qr_mode,
        missions=[
            ScanContextMission(
                mission_id=m.id,
                title=m.title,
                description=m.description,
                points=m.points,
                already_granted=m.id in granted,
                experience_type=m.experience_type,
                # 정답이 빠진 설정만. 화이트리스트는 서비스가 쥔다.
                experience_config=exp.public_config(m),
                attempts_left=exp.attempts_left(db, m, participant.id),
            )
            for m in missions
        ],
        scan_already_used=svc.scan_used_in_window(
            db, booth_id=booth.id, window_index=window, participant_id=participant.id
        ),
    )


@router.post("/scan-grants", response_model=GrantResult)
def scan_grant(
    festival_id: int,
    payload: ScanGrantIn,
    db: DbSession,
    participant: CurrentParticipant,
) -> GrantResult:
    """참여자가 부스 QR 을 스캔해 지급받는다. 1 스캔 = 1 미션.

    체험(퀴즈·안내)은 **여기서 채점한 뒤에야** 지급으로 넘어갑니다. 통과하지
    못하면 참여 이력을 만들지 않습니다 — 계약 §11 대로 집계에 섞이지 않게
    하기 위함입니다.
    """
    festival = _live_festival(db, festival_id)
    booth = _scan_booth(db, festival_id, payload.booth_id)

    mission = db.get(Mission, payload.mission_id)
    if mission is None or mission.festival_id != festival_id:
        raise not_found("미션")

    # 예산은 부스 단위다 — `GET /scan` 이 세어 준 카운트다운과 같은 값이어야 한다.
    windows = exp.accepted_windows(
        [m for m in _active_missions(db, festival_id) if m.booth_id == booth.id]
    )
    window = svc.verify_scan_proof(
        booth, token=payload.token, signature=payload.signature, windows=windows
    )

    used = exp.attempts_used(db, participant_id=participant.id, mission_id=mission.id)
    try:
        graded = exp.grade(
            mission, payload.response, attempts_used=used, window_index=window
        )
    except ApiError as exc:
        # 오답은 시도를 하나 먹는다. **커밋해야** 한다 — 실패 응답과 함께
        # 롤백되면 새로고침만으로 시도 횟수가 초기화된다.
        code = (exc.detail or {}).get("error", {}).get("code")
        if code == "EXPERIENCE_WRONG_ANSWER":
            exp.record_attempt(db, participant_id=participant.id, mission_id=mission.id)
            db.commit()
        raise

    outcome = svc.grant(
        db,
        festival=festival,
        booth=booth,
        mission=mission,
        participant=participant,
        verified_via=BoothVerifyMode.PARTICIPANT_SCAN,
        scan_window_index=window,
        client_request_id=payload.client_request_id,
        queued_at=payload.queued_at,
        response=graded.response,
        attempt_count=graded.attempt_count,
    )
    db.commit()

    from festaflow.routers.booths import _result

    result = _result(outcome)
    # 해설은 맞힌 사람에게만 간다. 재전송(was_already_granted)에도 실어야
    # 화면을 새로고침한 사람이 읽던 글을 잃지 않는다.
    result.explanation = graded.explanation
    return result


# ── 경품 뽑기 ───────────────────────────────────────────────────────────────


def _draw_out(draw, prize: Prize | None) -> PrizeDrawOut:
    return PrizeDrawOut(
        id=draw.id,
        drawn_at=draw.drawn_at,
        prize_name=prize.name if prize else None,
        prize_description=prize.description if prize else None,
        is_blank=bool(prize.is_blank) if prize else False,
        claimed_at=draw.claimed_at,
    )


def _draw_payload(db: Session, festival_id: int, participant, *, board=None, progress=None):
    """뽑기 카드를 그리는 데 필요한 전부.

    상품 미리보기에 **재고와 가중치는 담지 않는다.** 남은 재고가 보이면 언제
    뽑을지를 재는 사람이 생기고, 그 순간 추첨이 아니게 된다.

    보드와 진행률은 묶음 조회가 이미 계산해 두므로 인자로 받는다.
    """
    prizes = prize_svc.active_prizes(db, festival_id)
    if board is None:
        board = svc.get_board(db, festival_id)
    if progress is None:
        progress = svc.progress_of(db, board, participant.id)
    existing = prize_svc.existing_draw(db, festival_id, participant.id)

    return PrizeDrawStatus(
        enabled=bool(prizes),
        can_draw=bool(prizes) and progress.is_complete and existing is None,
        revealed_count=progress.revealed_count,
        total_tiles=progress.total_tiles,
        is_complete=progress.is_complete,
        draw=(
            _draw_out(existing, db.get(Prize, existing.prize_id) if existing.prize_id else None)
            if existing
            else None
        ),
        prizes=[
            PrizePreview(name=p.name, description=p.description, is_blank=p.is_blank)
            for p in prizes
        ],
    )


@router.get("/prize-draw/me", response_model=PrizeDrawStatus)
def prize_draw_status(
    festival_id: int, db: DbSession, participant: CurrentParticipant
) -> PrizeDrawStatus:
    """뽑기 카드를 그리는 데 필요한 전부."""
    _live_festival(db, festival_id)
    return _draw_payload(db, festival_id, participant)


@router.get("/participants/me/overview", response_model=ParticipantOverview)
def participant_overview(
    festival_id: int, db: DbSession, participant: CurrentParticipant
) -> ParticipantOverview:
    """관객 화면이 주기적으로 물어보는 세 가지를 한 번에.

    `/stamp-board/me` + `/participants/me` + `/prize-draw/me` 와 **같은 값**을
    돌려준다. 화면이 세 번 물어보던 것을 한 번으로 줄이려고 만든 자리이고,
    그래서 셋 중 하나라도 값이 달라지면 그것은 버그다.

    보드와 진행률을 한 번만 계산해 보드 응답과 뽑기 응답이 나눠 쓴다 — 따로
    부를 때는 같은 것을 세 번 세고 있었다.
    """
    _live_festival(db, festival_id)

    board = svc.get_board(db, festival_id)
    progress = svc.progress_of(db, board, participant.id)

    return ParticipantOverview(
        board=board_svc.participant_board(db, board, participant.id, progress=progress),
        me=_me_payload(db, festival_id, participant),
        prize_draw=_draw_payload(db, festival_id, participant, board=board, progress=progress),
    )


@router.post("/prize-draw", response_model=PrizeDrawOut)
def prize_draw(
    festival_id: int, db: DbSession, participant: CurrentParticipant
) -> PrizeDrawOut:
    """뽑기 1회. 조각을 다 모은 참여자만, 축제당 한 번."""
    _live_festival(db, festival_id)
    outcome = prize_svc.draw(db, festival_id=festival_id, participant=participant)
    db.commit()
    db.refresh(outcome.draw)
    return _draw_out(outcome.draw, outcome.prize)
