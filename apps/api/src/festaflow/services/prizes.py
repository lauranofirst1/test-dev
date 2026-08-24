"""경품 뽑기 — 조각 보드를 완성한 참여자가 축제당 한 번 돌린다.

**동시성이 이 모듈의 전부입니다.** 재고가 1개 남은 상품을 두 사람이 같은 순간에
뽑으면, 조건문으로 확인하고 나서 차감하는 코드는 둘 다 통과시킵니다. 그래서
재고는 읽고-쓰지 않고 **조건부 UPDATE 한 번**으로 차감하며, 그 UPDATE 가 0행을
바꿨다면 방금 다른 사람이 가져간 것으로 보고 남은 후보로 다시 뽑습니다.

1인 1회도 마찬가지입니다. `uq_prize_draws_participant` 가 진실이고, 애플리케이션은
그 제약이 터졌을 때를 정상 흐름으로 받습니다.

가중치는 **남은 후보들 사이에서 정규화**합니다. 확률(%)을 저장하지 않는 이유는
상품 하나가 소진되거나 중지되는 순간 합이 100 이 아니게 되기 때문입니다.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from festaflow.core.errors import ApiError
from festaflow.models import Participant, Prize, PrizeDraw
from festaflow.services import grants

log = logging.getLogger(__name__)

#: 재고 경합으로 다시 뽑는 횟수의 상한. 이 이상 돌면 후보가 사실상 없는 상태다.
_MAX_RETRIES = 8


def active_prizes(db: Session, festival_id: int) -> list[Prize]:
    """운영자가 켜 둔 상품 전부. 소진된 것도 포함한다(화면이 회색으로 보여준다)."""
    return list(
        db.execute(
            select(Prize)
            .where(
                Prize.festival_id == festival_id,
                Prize.archived_at.is_(None),
                Prize.is_active.is_(True),
            )
            .order_by(Prize.is_blank, Prize.id)
        ).scalars()
    )


def drawable(prizes: list[Prize]) -> list[Prize]:
    """지금 실제로 뽑힐 수 있는 후보 — 재고가 무제한이거나 남아 있는 것."""
    return [p for p in prizes if p.stock is None or p.stock > 0]


def _weighted_pick(candidates: list[Prize]) -> Prize:
    """가중치 비례 추첨. `secrets` 를 쓴다 — 경품이 걸린 추첨은 예측 가능하면 안 된다."""
    total = sum(p.weight for p in candidates)
    roll = secrets.randbelow(total)
    upto = 0
    for p in candidates:
        upto += p.weight
        if roll < upto:
            return p
    return candidates[-1]  # 부동소수점이 없으므로 도달하지 않는다


def _take_stock(db: Session, prize: Prize) -> bool:
    """재고를 하나 줄인다. 성공하면 True.

    무제한(NULL)은 차감할 것이 없으므로 항상 성공합니다. 유한 재고는 조건부
    UPDATE 한 번으로 처리하며, 0행이면 방금 소진된 것입니다.
    """
    if prize.stock is None:
        return True
    result = db.execute(
        update(Prize)
        .where(Prize.id == prize.id, Prize.stock > 0)
        .values(stock=Prize.stock - 1)
    )
    if result.rowcount == 0:
        return False
    # 이 세션이 들고 있는 객체는 방금 DB 에서 바뀐 값을 모른다. 다시 읽게 만든다.
    db.expire(prize, ["stock"])
    return True


@dataclass
class DrawOutcome:
    draw: PrizeDraw
    prize: Prize | None
    #: 이미 뽑았던 참여자가 다시 요청했다 — 새로 뽑지 않고 기존 결과를 돌려준다.
    was_already_drawn: bool


def existing_draw(db: Session, festival_id: int, participant_id: int) -> PrizeDraw | None:
    return db.execute(
        select(PrizeDraw).where(
            PrizeDraw.festival_id == festival_id,
            PrizeDraw.participant_id == participant_id,
        )
    ).scalar_one_or_none()


def assert_eligible(db: Session, festival_id: int, participant_id: int) -> None:
    """완성하지 않았으면 뽑을 수 없다. 판정은 서버만 한다."""
    board = grants.get_board(db, festival_id)
    progress = grants.progress_of(db, board, participant_id)
    if not progress.is_complete:
        raise ApiError(
            409,
            "DRAW_NOT_ELIGIBLE",
            (
                f"조각을 모두 모으면 뽑기가 열립니다. "
                f"지금은 {progress.total_tiles}조각 중 {progress.revealed_count}조각입니다."
            ),
            {
                "revealed_count": progress.revealed_count,
                "total_tiles": progress.total_tiles,
            },
        )


def draw(db: Session, *, festival_id: int, participant: Participant) -> DrawOutcome:
    """뽑기 1회. 완성 판정 → 재고 확보 → 기록을 한 트랜잭션으로 처리한다."""
    already = existing_draw(db, festival_id, participant.id)
    if already is not None:
        return DrawOutcome(
            draw=already,
            prize=db.get(Prize, already.prize_id) if already.prize_id else None,
            was_already_drawn=True,
        )

    assert_eligible(db, festival_id, participant.id)

    # 재고를 먼저 확보하고 기록을 남긴다. 순서를 뒤집으면 기록은 남았는데 재고를
    # 못 가져간 참여자가 생기고, 그 사람은 다시 뽑을 수도 없다.
    won: Prize | None = None
    candidates = drawable(active_prizes(db, festival_id))
    for _ in range(_MAX_RETRIES):
        if not candidates:
            break
        picked = _weighted_pick(candidates)
        if _take_stock(db, picked):
            won = picked
            break
        # 방금 소진됐다. 이 후보를 빼고 다시 뽑는다.
        candidates = [c for c in candidates if c.id != picked.id]
    else:
        log.warning("뽑기 재고 경합이 %d회 반복됨 (festival=%s)", _MAX_RETRIES, festival_id)

    if won is None:
        # 상품이 하나도 없거나 전부 소진됐다. 꽝과 구분해 기록한다 —
        # 꽝은 운영자가 의도한 결과이고, 이쪽은 운영이 손봐야 할 상태다.
        log.warning("뽑기 후보 없음 (festival=%s, participant=%s)", festival_id, participant.id)

    record = PrizeDraw(
        festival_id=festival_id,
        participant_id=participant.id,
        prize_id=won.id if won else None,
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
    except IntegrityError:
        # 동시 요청이 먼저 넣었다. 우리가 차감한 재고를 되돌리고 기존 결과를 쓴다.
        db.expunge(record)
        if won is not None and won.stock is not None:
            db.execute(update(Prize).where(Prize.id == won.id).values(stock=Prize.stock + 1))
        raced = existing_draw(db, festival_id, participant.id)
        if raced is None:
            raise
        return DrawOutcome(
            draw=raced,
            prize=db.get(Prize, raced.prize_id) if raced.prize_id else None,
            was_already_drawn=True,
        )

    return DrawOutcome(draw=record, prize=won, was_already_drawn=False)
