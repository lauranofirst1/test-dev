"""경품 관리와 당첨자 확인 — 운영자용.

참여자용 뽑기(`/prize-draw`)는 `routers/participants.py` 에 있습니다. 같은 도메인을
두 파일로 나눈 이유는 **인증 경계가 다르기 때문**입니다. 이 라우터는 기관 스코프와
운영자 권한을 요구하고, 저쪽은 로그인 없이 `X-Participant-Secret` 만 봅니다.
한 파일에 섞으면 어느 엔드포인트가 어느 경계에 있는지 읽어서 알 수 없습니다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from festaflow.core.deps import (
    CanOperate,
    CurrentOrg,
    DbSession,
    FestivalAccess,
    OptionalStaff,
)
from festaflow.core.errors import ApiError, not_found
from festaflow.models import Festival, Participant, Prize, PrizeDraw
from festaflow.schemas.prize import (
    PrizeClaimLookup,
    PrizeDrawList,
    PrizeDrawRow,
    PrizeIn,
    PrizeList,
    PrizeOut,
)
from festaflow.services import grants
from festaflow.services import prizes as svc

router = APIRouter(
    prefix="/api/festivals/{festival_id}",
    tags=["prizes"],
    dependencies=[FestivalAccess],
)


def _festival(db: Session, org_id: int, festival_id: int) -> Festival:
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


def _prize(db: Session, festival_id: int, prize_id: int) -> Prize:
    p = db.execute(
        select(Prize).where(
            Prize.id == prize_id,
            Prize.festival_id == festival_id,
            Prize.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if p is None:
        raise not_found("경품")
    return p


def _warnings(prizes: list[Prize]) -> list[dict]:
    """당일에 알면 늦는 것들. 저장할 때마다 다시 계산해 화면에 띄운다."""
    out: list[dict] = []
    if not prizes:
        return out

    drawable = svc.drawable(prizes)
    if not drawable:
        out.append(
            {
                "code": "NO_DRAWABLE_PRIZE",
                "message": "뽑을 수 있는 경품이 없습니다. 재고가 모두 소진됐거나 전부 중지 상태입니다.",
            }
        )
    if not any(p.is_blank for p in prizes):
        out.append(
            {
                "code": "NO_BLANK_PRIZE",
                "message": (
                    "꽝이 없습니다. 재고가 떨어지면 아무도 뽑을 수 없게 되므로, "
                    "재고 무제한인 꽝을 하나 두는 것을 권합니다."
                ),
            }
        )
    finite = [p for p in drawable if p.stock is not None]
    if finite and len(finite) == len(drawable):
        out.append(
            {
                "code": "ALL_STOCK_FINITE",
                "message": "모든 경품에 재고가 있습니다. 전부 소진되면 뽑기가 멈춥니다.",
            }
        )
    return out


def _list(db: Session, festival_id: int) -> PrizeList:
    items = list(
        db.execute(
            select(Prize)
            .where(Prize.festival_id == festival_id, Prize.archived_at.is_(None))
            .order_by(Prize.is_blank, Prize.id)
        ).scalars()
    )
    active = [p for p in items if p.is_active]
    return PrizeList(
        items=[PrizeOut.model_validate(p) for p in items],
        total=len(items),
        drawable_count=len(svc.drawable(active)),
        warnings=_warnings(active),
    )


# ── 경품 ────────────────────────────────────────────────────────────────────


@router.get("/prizes", response_model=PrizeList)
def list_prizes(festival_id: int, db: DbSession, org: CurrentOrg) -> PrizeList:
    _festival(db, org.id, festival_id)
    return _list(db, festival_id)


@router.post(
    "/prizes",
    response_model=PrizeOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanOperate],
)
def create_prize(
    festival_id: int, payload: PrizeIn, db: DbSession, org: CurrentOrg
) -> PrizeOut:
    festival = _festival(db, org.id, festival_id)
    prize = Prize(festival_id=festival.id, **payload.model_dump())
    db.add(prize)
    db.commit()
    db.refresh(prize)
    return PrizeOut.model_validate(prize)


@router.put("/prizes/{prize_id}", response_model=PrizeOut, dependencies=[CanOperate])
def update_prize(
    festival_id: int, prize_id: int, payload: PrizeIn, db: DbSession, org: CurrentOrg
) -> PrizeOut:
    _festival(db, org.id, festival_id)
    prize = _prize(db, festival_id, prize_id)
    for k, v in payload.model_dump().items():
        setattr(prize, k, v)
    db.commit()
    db.refresh(prize)
    return PrizeOut.model_validate(prize)


@router.post(
    "/prizes/{prize_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[CanOperate],
)
def archive_prize(festival_id: int, prize_id: int, db: DbSession, org: CurrentOrg) -> None:
    """삭제가 아니라 아카이브. 이미 당첨된 사람의 화면이 빈칸이 되면 안 된다."""
    _festival(db, org.id, festival_id)
    prize = _prize(db, festival_id, prize_id)
    prize.archived_at = datetime.now(UTC)
    prize.is_active = False
    db.commit()


# ── 당첨자 ──────────────────────────────────────────────────────────────────


@router.get("/prize-draws", response_model=PrizeDrawList)
def list_draws(festival_id: int, db: DbSession, org: CurrentOrg) -> PrizeDrawList:
    """당첨자 목록. 실물을 건넬 때 스태프가 보는 화면이다."""
    _festival(db, org.id, festival_id)

    rows = list(
        db.execute(
            select(PrizeDraw, Participant.code, Prize)
            .join(Participant, Participant.id == PrizeDraw.participant_id)
            .outerjoin(Prize, Prize.id == PrizeDraw.prize_id)
            .where(PrizeDraw.festival_id == festival_id)
            .order_by(PrizeDraw.drawn_at.desc())
        )
    )

    unclaimed = db.execute(
        select(func.count(PrizeDraw.id))
        .join(Prize, Prize.id == PrizeDraw.prize_id)
        .where(
            PrizeDraw.festival_id == festival_id,
            PrizeDraw.claimed_at.is_(None),
            Prize.is_blank.is_(False),
        )
    ).scalar_one()

    return PrizeDrawList(
        items=[
            PrizeDrawRow(
                id=d.id,
                participant_code=code,
                prize_id=d.prize_id,
                prize_name=prize.name if prize else None,
                is_blank=bool(prize.is_blank) if prize else False,
                drawn_at=d.drawn_at,
                claimed_at=d.claimed_at,
            )
            for d, code, prize in rows
        ],
        total=len(rows),
        unclaimed=int(unclaimed),
    )


@router.get("/prize-draws/lookup", response_model=PrizeClaimLookup)
def lookup_draw(
    festival_id: int, db: DbSession, org: CurrentOrg, code: str = Query(..., min_length=1)
) -> PrizeClaimLookup:
    """참여 코드로 수령 대상을 찾는다 — 경품 수령대 화면이 쓴다.

    당첨자 목록을 스크롤해 찾는 것은 현장에서 쓸 수 없습니다. 줄이 서 있고,
    당첨자가 수백 명이면 그 방식은 멈춥니다.

    코드는 사람이 손으로 옮겨 적습니다. 공백·대소문자는 서버가 흡수합니다 —
    참여 코드 알파벳에서 0/O·1/I 를 뺀 것과 같은 이유입니다.
    """
    _festival(db, org.id, festival_id)

    # 존재하지 않는 코드만 404 다. 나머지는 전부 "읽어야 할 사실"이다.
    participant = grants.find_participant(db, festival_id, code)

    draw = svc.existing_draw(db, festival_id, participant.id)
    if draw is None:
        return PrizeClaimLookup(
            participant_code=participant.code,
            claimable=False,
            reason="아직 뽑기를 하지 않았습니다. 조각을 모두 모으면 뽑기가 열립니다.",
        )

    prize = db.get(Prize, draw.prize_id) if draw.prize_id else None
    row = PrizeDrawRow(
        id=draw.id,
        participant_code=participant.code,
        prize_id=draw.prize_id,
        prize_name=prize.name if prize else None,
        is_blank=bool(prize.is_blank) if prize else False,
        drawn_at=draw.drawn_at,
        claimed_at=draw.claimed_at,
    )

    if prize is None:
        reason = "뽑을 수 있는 경품이 없는 상태에서 뽑았습니다. 운영자에게 문의하세요."
    elif prize.is_blank:
        reason = "꽝입니다. 건넬 경품이 없습니다."
    elif draw.claimed_at is not None:
        reason = "이미 수령한 경품입니다."
    else:
        reason = None

    return PrizeClaimLookup(
        participant_code=participant.code,
        claimable=reason is None,
        reason=reason,
        draw=row,
    )


@router.post(
    "/prize-draws/{draw_id}/claim", response_model=PrizeDrawRow, dependencies=[CanOperate]
)
def claim_draw(
    festival_id: int,
    draw_id: int,
    db: DbSession,
    org: CurrentOrg,
    staff: OptionalStaff,
) -> PrizeDrawRow:
    """실물 수령 확인. **스태프만 찍는다** — 참여자가 스스로 찍으면 확인이 아니다."""
    _festival(db, org.id, festival_id)
    draw = db.execute(
        select(PrizeDraw).where(
            PrizeDraw.id == draw_id, PrizeDraw.festival_id == festival_id
        )
    ).scalar_one_or_none()
    if draw is None:
        raise not_found("뽑기 기록")

    prize = db.get(Prize, draw.prize_id) if draw.prize_id else None
    if prize is None or prize.is_blank:
        raise ApiError(
            409,
            "DRAW_NOT_CLAIMABLE",
            "꽝은 수령 확인 대상이 아닙니다.",
            {"draw_id": draw_id},
        )
    if draw.claimed_at is None:
        draw.claimed_at = datetime.now(UTC)
        draw.claimed_by_staff_id = staff.id if staff else None
        db.commit()
        db.refresh(draw)

    code = db.execute(
        select(Participant.code).where(Participant.id == draw.participant_id)
    ).scalar_one()
    return PrizeDrawRow(
        id=draw.id,
        participant_code=code,
        prize_id=draw.prize_id,
        prize_name=prize.name,
        is_blank=prize.is_blank,
        drawn_at=draw.drawn_at,
        claimed_at=draw.claimed_at,
    )
