"""관객 화면 묶음 조회 — `/participants/me/overview`.

관객 화면은 보드·진행·뽑기를 주기적으로 다시 물어봅니다. 셋을 따로 물으면
참여자 1명이 초당 0.3 요청이 되고, 1000명이 붙는 축제에서는 그것만으로 초당
300 요청입니다. 묶음 조회는 그것을 3분의 1로 줄이려고 만든 자리입니다.

**그래서 이 파일이 지키는 것은 하나입니다 — 묶음이 낱개 셋과 같은 값이어야 한다.**
값이 갈라지는 순간 화면은 둘 중 어느 쪽을 믿어야 할지 알 수 없게 됩니다.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    Festival,
    Organization,
    Participant,
    Prize,
    StampBoard,
    StampReveal,
    StampTile,
)


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


def _issue(client, festival):
    r = client.post(f"/api/festivals/{festival.id}/participants")
    assert r.status_code == 201, r.text
    return r.json()["code"], {"X-Participant-Secret": r.json()["secret"]}


def _complete_board(db: Session, festival: Festival, code: str) -> Participant:
    participant = db.query(Participant).filter(Participant.code == code).one()
    board = db.query(StampBoard).filter(StampBoard.festival_id == festival.id).one()
    tiles = (
        db.query(StampTile)
        .filter(StampTile.board_id == board.id, StampTile.board_version == board.version)
        .all()
    )
    for t in tiles:
        db.add(
            StampReveal(
                board_id=board.id,
                board_version=board.version,
                participant_id=participant.id,
                tile_id=t.id,
                booth_id=None,
            )
        )
    db.flush()
    return participant


# ── 같은 값인가 ─────────────────────────────────────────────────────────────


def test_overview_matches_the_three_separate_calls(client, festival, db):
    """묶음 = 낱개 셋. 이 등식이 깨지면 화면이 믿을 값이 없어진다."""
    db.add(Prize(festival_id=festival.id, name="막국수 쿠폰", stock=10, weight=1))
    db.commit()
    _, headers = _issue(client, festival)
    base = f"/api/festivals/{festival.id}"

    board = client.get(f"{base}/stamp-board/me", headers=headers).json()
    me = client.get(f"{base}/participants/me", headers=headers).json()
    draw = client.get(f"{base}/prize-draw/me", headers=headers).json()

    r = client.get(f"{base}/participants/me/overview", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["board"] == board
    assert body["me"] == me
    assert body["prize_draw"] == draw


def test_overview_matches_after_the_board_is_complete(client, festival, db):
    """완성 뒤에도 같아야 한다 — 완성 문구와 뽑기 자격이 여기서 갈린다."""
    db.add(Prize(festival_id=festival.id, name="막국수 쿠폰", stock=10, weight=1))
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()
    base = f"/api/festivals/{festival.id}"

    body = client.get(f"{base}/participants/me/overview", headers=headers).json()

    assert body["board"] == client.get(f"{base}/stamp-board/me", headers=headers).json()
    assert body["prize_draw"] == client.get(f"{base}/prize-draw/me", headers=headers).json()
    assert body["board"]["progress"]["is_complete"] is True
    assert body["prize_draw"]["can_draw"] is True


def test_overview_needs_the_participant_secret(client, festival):
    """비밀 없이는 남의 진행을 볼 수 없다."""
    r = client.get(f"/api/festivals/{festival.id}/participants/me/overview")
    assert r.status_code == 401


# ── 조회가 쓰기를 만들지 않는가 ─────────────────────────────────────────────


def test_polling_does_not_write_last_seen_every_time(client, festival, db):
    """관객 화면은 이 조회를 반복한다. 매번 쓰면 참여자 수만큼 쓰기가 쌓인다.

    `last_seen_at` 은 "대략 언제까지 보고 있었나" 를 알기 위한 값이라 1분
    해상도면 충분하다. 그 안에 다시 물으면 쓰지 않는다.
    """
    code, headers = _issue(client, festival)
    base = f"/api/festivals/{festival.id}"

    client.get(f"{base}/participants/me/overview", headers=headers)
    participant = db.query(Participant).filter(Participant.code == code).one()
    db.refresh(participant)
    first = participant.last_seen_at
    assert first is not None, "첫 조회에서는 기록되어야 한다"

    for _ in range(5):
        client.get(f"{base}/participants/me/overview", headers=headers)
    db.refresh(participant)

    assert participant.last_seen_at == first, "1분 안의 반복 조회는 쓰기를 만들지 않는다"
