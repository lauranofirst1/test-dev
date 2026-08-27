"""조각 보드가 부스 수를 따라간다.

조각 수는 부스 수에서 나옵니다. 기획 단계에 한 번 골라 굳혀 두면 부스를 더
만들었을 때 조각을 못 받는 부스가 생기고, 뒤늦게 고치면 이미 모은 조각이
초기화됩니다. 그래서 부스를 만들고 지울 때마다 서버가 따라 맞춥니다.

**여기서 지키는 것은 셋입니다.**

1. 부스가 늘고 줄면 격자가 따라온다.
2. 운영자가 직접 고른 격자는 서버가 되돌리지 않는다.
3. **누군가 이미 조각을 모았으면 손대지 않는다** — 그건 확인을 받고 할 일이지
   부스를 하나 추가했다고 조용히 벌어질 일이 아니다.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    Booth,
    Festival,
    Organization,
    Participant,
    StampBoard,
    StampReveal,
    StampTile,
)
from festaflow.models.enums import BoothType
from festaflow.services import grants as svc


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="춘천시문화재단")
    db.add(o)
    db.flush()
    return o


@pytest.fixture
def client(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def festival(db: Session, org: Organization) -> Festival:
    f = Festival(
        organization_id=org.id,
        name="춘천 가을 먹거리 축제",
        region="강원특별자치도 춘천시",
        venue="공지천 조각공원",
        starts_on=date(2026, 10, 10),
        ends_on=date(2026, 10, 12),
        expected_visitors=18000,
        total_budget=240000000,
    )
    db.add(f)
    db.flush()
    board = StampBoard(festival_id=f.id, rows=2, cols=2)
    db.add(board)
    db.flush()
    for idx in range(board.total_tiles):
        db.add(StampTile(board_id=board.id, board_version=board.version, tile_index=idx))
    db.flush()
    return f


def _booths(db: Session, festival: Festival, n: int) -> None:
    for i in range(n):
        db.add(Booth(festival_id=festival.id, name=f"부스 {i + 1}", booth_type=BoothType.ETC))
    db.flush()


def _board(db: Session, festival: Festival) -> StampBoard:
    b = svc.get_board(db, festival.id)
    db.refresh(b)
    return b


# ── 따라온다 ────────────────────────────────────────────────────────────────


def test_grid_follows_the_booth_count_upward(db, festival):
    """부스가 늘면 조각도 는다. 4개 → 6개면 2×2 가 2×3 이 된다."""
    _booths(db, festival, 6)

    changed = svc.autofit_board(db, festival.id)

    assert changed is not None
    board = _board(db, festival)
    assert (board.rows, board.cols) == (2, 3)
    assert board.total_tiles == 6


def test_grid_follows_the_booth_count_downward(db, festival):
    """줄어드는 쪽이 더 급하다 — 조각이 부스보다 많으면 아무도 완성할 수 없다."""
    _booths(db, festival, 9)
    svc.autofit_board(db, festival.id)
    assert _board(db, festival).total_tiles == 9

    for b in db.query(Booth).filter(Booth.festival_id == festival.id).limit(3):
        b.is_active = False
    db.flush()

    svc.autofit_board(db, festival.id)
    assert _board(db, festival).total_tiles == 6


def test_new_tiles_exist_for_the_new_version(db, festival):
    """격자를 바꿨으면 그 버전의 타일이 실제로 있어야 한다."""
    _booths(db, festival, 6)
    svc.autofit_board(db, festival.id)
    board = _board(db, festival)

    tiles = svc.current_tiles(db, board)
    assert len(tiles) == 6
    assert sorted(t.tile_index for t in tiles) == list(range(6))


def test_too_few_booths_leaves_the_board_alone(db, festival):
    """부스 3개로는 만들 격자가 없다. 지울 격자가 아니라 아직 정할 수 없는 상태다."""
    _booths(db, festival, 3)

    assert svc.autofit_board(db, festival.id) is None
    assert _board(db, festival).total_tiles == 4


# ── 손대지 않는다 ───────────────────────────────────────────────────────────


def test_a_hand_picked_grid_is_not_overwritten(db, festival):
    """부스 8개에 6조각처럼 일부러 고른 구성이 있다. 서버가 되돌리면 고른 의미가 없다."""
    board = _board(db, festival)
    board.grid_auto = False
    board.rows, board.cols = 2, 3
    db.flush()
    _booths(db, festival, 8)

    assert svc.autofit_board(db, festival.id) is None
    assert _board(db, festival).total_tiles == 6


def test_collected_pieces_are_never_reset_silently(db, festival):
    """이미 모은 사람이 있으면 격자를 바꾸지 않는다.

    격자를 바꾸는 것은 타일 집합을 바꾸는 일이라 그 순간 진행이 초기화된다.
    부스를 하나 추가했다고 조용히 벌어질 일이 아니다.
    """
    _booths(db, festival, 6)
    board = _board(db, festival)
    participant = Participant(festival_id=festival.id, code="FF-TESTTEST", secret_hash="x")
    db.add(participant)
    db.flush()
    tile = svc.current_tiles(db, board)[0]
    db.add(
        StampReveal(
            board_id=board.id,
            board_version=board.version,
            participant_id=participant.id,
            tile_id=tile.id,
            booth_id=None,
        )
    )
    db.flush()

    assert svc.autofit_board(db, festival.id) is None
    assert _board(db, festival).total_tiles == 4
