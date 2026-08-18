"""스탬프 보드 — docs/03-api-contract.md §7, docs/02-data-model.md §7.

구조를 바꿔도 **기존 공개 이력을 삭제하지 않습니다.** version 을 올리고 새 타일
집합을 만들며, 과거 reveal 은 이전 버전 기록으로 남습니다. 축제 당일 오조작 한 번에
모든 참여자의 수집이 증발하는 일을 막기 위한 것이고, 그래서 되돌릴 수 없는 변경은
`?confirm=true` 를 요구합니다.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from festaflow.core.deps import (
    CanOperate,
    CurrentOrg,
    CurrentParticipant,
    DbSession,
    FestivalAccess,
)
from festaflow.core.errors import ApiError, not_found
from festaflow.models import Festival, StampBoard, StampReveal, StampTile
from festaflow.schemas.participation import (
    BoardProgress,
    BoardTile,
    ParticipantBoard,
    StampBoardAdmin,
    StampBoardOut,
    StampBoardUpdate,
)
from festaflow.services import grants as svc

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["stamp-board"])

#: version 을 올려야 하는 필드. 이걸 바꾸면 타일 집합 자체가 달라진다.
STRUCTURAL = ("rows", "cols", "reveal_mode", "grant_unit")


def _out(db: Session, board: StampBoard, *, tiles: list[StampTile] | None = None) -> StampBoardOut:
    rows = tiles if tiles is not None else svc.current_tiles(db, board)
    return StampBoardOut(
        id=board.id,
        festival_id=board.festival_id,
        version=board.version,
        rows=board.rows,
        cols=board.cols,
        total_tiles=board.total_tiles,
        reveal_mode=board.reveal_mode,
        grant_unit=board.grant_unit,
        image_url=board.image_url,
        complete_message=board.complete_message,
        tiles=[
            BoardTile(tile_index=t.tile_index, assigned_booth_id=t.assigned_booth_id)
            for t in rows
        ],
    )


# ── 운영자 ──────────────────────────────────────────────────────────────────


def _admin(db: Session, festival_id: int, board: StampBoard) -> StampBoardAdmin:
    warning = svc.uncompletable_warning(db, festival_id, board)
    return StampBoardAdmin(
        **_out(db, board).model_dump(),
        warnings=[warning] if warning else [],
    )


@router.get("/stamp-board", response_model=StampBoardAdmin, dependencies=[FestivalAccess])
def get_stamp_board(festival_id: int, db: DbSession, org: CurrentOrg) -> StampBoardAdmin:
    """운영자 조회. 완성 가능성 경고를 함께 싣는다 — 같은 판정을 화면이 다시
    계산하면 규칙이 두 곳에 살고 반드시 어긋난다."""
    _owned(db, org.id, festival_id)
    return _admin(db, festival_id, svc.get_board(db, festival_id))


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


@router.put(
    "/stamp-board",
    response_model=StampBoardAdmin,
    dependencies=[FestivalAccess, CanOperate],
)
def update_stamp_board(
    festival_id: int,
    payload: StampBoardUpdate,
    db: DbSession,
    org: CurrentOrg,
    confirm: bool = Query(False),
) -> StampBoardAdmin:
    """구조를 바꾸면 진행이 초기화된다. 공개 이력이 있으면 확인 없이는 진행하지 않는다."""
    _owned(db, org.id, festival_id)
    board = svc.get_board(db, festival_id)

    structural_change = any(
        getattr(board, f) != getattr(payload, f) for f in STRUCTURAL
    )

    if structural_change:
        revealed_count = db.execute(
            select(func.count(StampReveal.id)).where(
                StampReveal.board_id == board.id, StampReveal.board_version == board.version
            )
        ).scalar_one()
        affected = db.execute(
            select(func.count(func.distinct(StampReveal.participant_id))).where(
                StampReveal.board_id == board.id, StampReveal.board_version == board.version
            )
        ).scalar_one()

        if revealed_count and not confirm:
            raise ApiError(
                409,
                "BOARD_RESET_REQUIRES_CONFIRMATION",
                f"참여자 {affected}명의 수집 진행이 초기화됩니다.",
                {"affected_participants": affected, "revealed_count": revealed_count},
            )

    # image_url / complete_message 만 바꾸는 요청은 버전을 올리지 않는다 — 진행 유지.
    board.image_url = payload.image_url
    board.complete_message = payload.complete_message

    if structural_change:
        board.rows = payload.rows
        board.cols = payload.cols
        board.reveal_mode = payload.reveal_mode
        board.grant_unit = payload.grant_unit
        board.version += 1
        for idx in range(board.total_tiles):
            db.add(StampTile(board_id=board.id, board_version=board.version, tile_index=idx))
        # 기존 stamp_reveals 는 지우지 않는다. 이전 버전 기록으로 남는다.

    db.commit()
    db.refresh(board)
    return _admin(db, festival_id, board)


# ── 참여자 ──────────────────────────────────────────────────────────────────


@router.get("/stamp-board/me", response_model=ParticipantBoard)
def my_stamp_board(
    festival_id: int, db: DbSession, participant: CurrentParticipant
) -> ParticipantBoard:
    """내 수집 현황. 공개된 조각만 `is_revealed` 가 참이다."""
    board = svc.get_board(db, festival_id)
    tiles = svc.current_tiles(db, board)
    reveals = {r.tile_id: r for r in svc.reveals_of(db, board, participant.id)}
    progress = svc.progress_of(db, board, participant.id)

    base = _out(db, board, tiles=tiles)
    return ParticipantBoard(
        **base.model_dump(exclude={"tiles"}),
        tiles=[
            BoardTile(
                tile_index=t.tile_index,
                assigned_booth_id=t.assigned_booth_id,
                is_revealed=t.id in reveals,
                revealed_at=reveals[t.id].revealed_at if t.id in reveals else None,
            )
            for t in tiles
        ],
        progress=BoardProgress(
            revealed_count=progress.revealed_count,
            total_tiles=progress.total_tiles,
            is_complete=progress.is_complete,
        ),
        # 완성 전에 미리 보여주면 완성의 의미가 없다.
        complete_message_shown=board.complete_message if progress.is_complete else None,
    )
