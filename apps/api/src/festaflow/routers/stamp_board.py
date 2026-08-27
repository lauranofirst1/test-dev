"""스탬프 보드 — docs/03-api-contract.md §7, docs/02-data-model.md §7.

구조를 바꿔도 **기존 공개 이력을 삭제하지 않습니다.** version 을 올리고 새 타일
집합을 만들며, 과거 reveal 은 이전 버전 기록으로 남습니다. 축제 당일 오조작 한 번에
모든 참여자의 수집이 증발하는 일을 막기 위한 것이고, 그래서 되돌릴 수 없는 변경은
`?confirm=true` 를 요구합니다.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Query, UploadFile
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
from festaflow.models.enums import GrantUnit
from festaflow.schemas.participation import (
    BoardProgress,
    BoardTile,
    GridOptionOut,
    ParticipantBoard,
    StampBoardAdmin,
    StampBoardOut,
    StampBoardUpdate,
)
from festaflow.services import grants as svc
from festaflow.services import media

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["stamp-board"])

#: 축제와 무관한 순수 계산. 생성 화면은 축제가 없는 상태에서 후보를 물어야 한다.
grid_router = APIRouter(prefix="/api/stamp-board", tags=["stamp-board"])


@grid_router.get("/grid-options", response_model=list[GridOptionOut])
def grid_options(unit_count: int = Query(..., ge=0, le=1000)) -> list[GridOptionOut]:
    """지급 단위 수에 맞춰 쪼갤 격자 후보. 규칙을 화면에 복제하지 않기 위한 것이다.

    부스 등록 전에는 기획서의 예정 프로그램 수를, 등록 후에는 실제 부스·미션 수를
    넘긴다. 어느 쪽이든 판정 규칙은 서버 한 곳에만 있다.
    """
    return [
        GridOptionOut(
            rows=g.rows, cols=g.cols, total=g.total, exact=g.exact, leftover=g.leftover
        )
        for g in svc.grid_options(unit_count)
    ]

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
        board_style=board.board_style,
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
    units = svc.grant_unit_count(db, festival_id, board)
    return StampBoardAdmin(
        **_out(db, board).model_dump(),
        warnings=[warning] if warning else [],
        unit_count=units,
        unit_label="부스" if board.grant_unit == GrantUnit.BOOTH else "미션",
        # 후보 계산도 서버에 둔다 — 어떤 격자가 가능한지는 도메인 규칙이다.
        grid_options=[
            GridOptionOut(
                rows=g.rows, cols=g.cols, total=g.total, exact=g.exact, leftover=g.leftover
            )
            for g in svc.grid_options(units)
        ],
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

    # 표현·문구만 바꾸는 요청은 버전을 올리지 않는다 — 진행 유지.
    # board_style 이 여기 있는 이유: 격자↔지도는 같은 타일을 다르게 그릴 뿐이라
    # 타일 집합이 그대로다. STRUCTURAL 에 넣으면 표현을 바꿀 때마다 참여자
    # 전원의 수집이 초기화된다.
    board.image_url = payload.image_url
    board.complete_message = payload.complete_message
    board.board_style = payload.board_style

    if structural_change:
        board.rows = payload.rows
        board.cols = payload.cols
        board.reveal_mode = payload.reveal_mode
        board.grant_unit = payload.grant_unit
        board.version += 1
        # 직접 골랐으니 이제부터 서버가 되돌리지 않는다. 부스 8개에 6조각처럼
        # 일부러 고른 구성이 있고, 그것을 자동 맞춤이 덮으면 고른 의미가 없다.
        # `grid_auto` 를 본문으로 받으면 자동으로 돌아갈 수 있다.
        if payload.grid_auto is None:
            board.grid_auto = False

    if payload.grid_auto is not None:
        board.grid_auto = payload.grid_auto
        if payload.grid_auto:
            # 자동으로 되돌리는 순간 지금 부스 수에 맞춘다.
            svc.autofit_board(db, festival_id)
        for idx in range(board.total_tiles):
            db.add(StampTile(board_id=board.id, board_version=board.version, tile_index=idx))
        # 기존 stamp_reveals 는 지우지 않는다. 이전 버전 기록으로 남는다.

    db.commit()
    db.refresh(board)
    return _admin(db, festival_id, board)


@router.post(
    "/stamp-board/image",
    response_model=StampBoardAdmin,
    dependencies=[FestivalAccess, CanOperate],
)
def upload_board_image(
    festival_id: int,
    db: DbSession,
    org: CurrentOrg,
    # ruff B008: FastAPI 는 의존성을 기본값으로 선언한다 — 여기서는 관용구가 맞다.
    file: UploadFile = File(...),  # noqa: B008
) -> StampBoardAdmin:
    """조각 보드 그림을 올린다. 격자는 바뀌지 않으므로 진행도 초기화하지 않는다.

    그림만 바꾸는 것은 되돌릴 수 있는 변경이라 확인을 요구하지 않는다 —
    version 을 올리는 것은 타일 집합이 달라지는 변경뿐이다.
    """
    _owned(db, org.id, festival_id)
    board = svc.get_board(db, festival_id)
    board.image_url = media.save_board_image(file.file, festival_id)
    db.commit()
    db.refresh(board)
    return _admin(db, festival_id, board)


# ── 참여자 ──────────────────────────────────────────────────────────────────


def participant_board(
    db: Session,
    board: StampBoard,
    participant_id: int,
    *,
    progress=None,
) -> ParticipantBoard:
    """내 수집 현황 응답을 조립한다.

    엔드포인트 밖으로 꺼내 둔 이유는 관객 화면의 묶음 조회(`/participants/me/overview`)가
    같은 응답을 필요로 하기 때문이다. 거기서는 보드와 진행률을 이미 계산해 두었으므로
    `progress` 를 넘겨 다시 세지 않는다.
    """
    tiles = svc.current_tiles(db, board)
    reveals = {r.tile_id: r for r in svc.reveals_of(db, board, participant_id)}
    if progress is None:
        progress = svc.progress_of(db, board, participant_id)

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


@router.get("/stamp-board/me", response_model=ParticipantBoard)
def my_stamp_board(
    festival_id: int, db: DbSession, participant: CurrentParticipant
) -> ParticipantBoard:
    """내 수집 현황. 공개된 조각만 `is_revealed` 가 참이다."""
    return participant_board(db, svc.get_board(db, festival_id), participant.id)
