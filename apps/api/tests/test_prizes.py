"""경품 뽑기 — 조각 보드를 완성한 참여자가 축제당 한 번 돌린다.

여기서 지키는 것은 셋입니다.

1. **완성한 사람만.** 판정은 서버가 한다.
2. **한 사람 한 번.** 유니크 제약이 진실이고, 조건문은 동시 요청에서 뚫린다.
3. **재고는 음수가 되지 않는다.** 읽고-쓰지 않고 조건부 UPDATE 로 차감한다.

그리고 참여자 응답에 재고와 가중치가 새지 않아야 합니다. 남은 재고가 보이면
언제 뽑을지를 재는 사람이 생기고, 그 순간 추첨이 아니게 됩니다.
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
    PrizeDraw,
    StampBoard,
    StampReveal,
    StampTile,
)
from festaflow.services import prizes as svc


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
    """2×2 보드 — 조각 4개면 완성이다. 테스트가 짧아진다."""
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


def _add_prize(db, festival, *, name, stock=None, weight=1, is_blank=False, is_active=True):
    p = Prize(
        festival_id=festival.id,
        name=name,
        stock=stock,
        weight=weight,
        is_blank=is_blank,
        is_active=is_active,
    )
    db.add(p)
    db.flush()
    return p


def _issue(client, festival):
    r = client.post(f"/api/festivals/{festival.id}/participants")
    assert r.status_code == 201, r.text
    return r.json()["code"], {"X-Participant-Secret": r.json()["secret"]}


def _complete_board(db: Session, festival: Festival, code: str) -> Participant:
    """보드를 채운다. 지급 경로를 타지 않고 공개 기록을 직접 넣는다 —
    이 파일이 검증하는 것은 뽑기이지 지급이 아니다."""
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


def _err(r) -> str:
    return r.json()["error"]["code"]


# ── 자격 ────────────────────────────────────────────────────────────────────


def test_cannot_draw_before_completing_the_board(client, festival, db):
    _add_prize(db, festival, name="막국수 쿠폰", stock=10)
    db.commit()
    _, headers = _issue(client, festival)

    r = client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)
    assert r.status_code == 409
    assert _err(r) == "DRAW_NOT_ELIGIBLE"
    assert db.query(PrizeDraw).count() == 0


def test_status_shows_progress_before_completion(client, festival, db):
    _add_prize(db, festival, name="막국수 쿠폰", stock=10)
    db.commit()
    _, headers = _issue(client, festival)

    r = client.get(f"/api/festivals/{festival.id}/prize-draw/me", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True
    assert body["can_draw"] is False
    assert body["is_complete"] is False
    assert body["total_tiles"] == 4
    assert body["draw"] is None


def test_completing_the_board_opens_the_draw(client, festival, db):
    _add_prize(db, festival, name="막국수 쿠폰", stock=10)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()

    status = client.get(f"/api/festivals/{festival.id}/prize-draw/me", headers=headers).json()
    assert status["can_draw"] is True

    r = client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["prize_name"] == "막국수 쿠폰"


def test_draw_is_disabled_when_the_operator_set_no_prizes(client, festival, db):
    """상품을 안 만들었으면 화면에 뽑기 카드를 그리지 않는다."""
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()

    body = client.get(f"/api/festivals/{festival.id}/prize-draw/me", headers=headers).json()
    assert body["enabled"] is False
    assert body["can_draw"] is False


# ── 1인 1회 ─────────────────────────────────────────────────────────────────


def test_second_draw_returns_the_same_result(client, festival, db):
    _add_prize(db, festival, name="막국수 쿠폰", stock=10)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()

    first = client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers).json()
    second = client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers).json()

    assert first["id"] == second["id"]
    assert db.query(PrizeDraw).count() == 1
    # 두 번 눌렀다고 재고가 두 개 빠지면 안 된다.
    assert db.query(Prize).filter(Prize.name == "막국수 쿠폰").one().stock == 9


# ── 재고 ────────────────────────────────────────────────────────────────────


def test_stock_is_decremented_once_per_draw(client, festival, db):
    prize = _add_prize(db, festival, name="기념 배지", stock=3)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()

    client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)
    db.refresh(prize)
    assert prize.stock == 2


def test_exhausted_prize_is_not_drawn_again(client, festival, db):
    """재고 1개를 두 사람이 노린다. 두 번째는 이 상품을 받을 수 없다."""
    prize = _add_prize(db, festival, name="한정 굿즈", stock=1)
    db.commit()

    winners = []
    for _ in range(2):
        code, headers = _issue(client, festival)
        _complete_board(db, festival, code)
        db.commit()
        winners.append(
            client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers).json()
        )

    db.refresh(prize)
    assert prize.stock == 0
    assert winners[0]["prize_name"] == "한정 굿즈"
    # 뽑을 수 있는 상품이 없었다 — 꽝(is_blank)과 구분해 기록한다.
    assert winners[1]["prize_name"] is None
    assert winners[1]["is_blank"] is False


def test_blank_prize_never_runs_out(client, festival, db):
    """꽝은 재고 무제한이어야 한다. 소진되면 아무도 못 뽑는 상태가 된다."""
    _add_prize(db, festival, name="꽝", stock=None, is_blank=True, weight=100)
    db.commit()

    for _ in range(5):
        code, headers = _issue(client, festival)
        _complete_board(db, festival, code)
        db.commit()
        body = client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers).json()
        assert body["is_blank"] is True
        assert body["prize_name"] == "꽝"


def test_inactive_prize_is_not_drawn(client, festival, db):
    _add_prize(db, festival, name="중지된 상품", stock=100, is_active=False)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()

    body = client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers).json()
    assert body["prize_name"] is None


def test_weight_actually_biases_the_pick(db, festival):
    """가중치가 반영되지 않으면 균등 추첨이 되고 운영자 설정이 무의미해진다."""
    heavy = _add_prize(db, festival, name="흔한 상품", weight=99)
    rare = _add_prize(db, festival, name="귀한 상품", weight=1)
    db.flush()

    picks = [svc._weighted_pick([heavy, rare]).name for _ in range(300)]
    # 99:1 이면 300회 중 흔한 쪽이 압도한다. 경계를 넉넉히 잡아 깜빡이지 않게 한다.
    assert picks.count("흔한 상품") > 250


# ── 참여자에게 새면 안 되는 것 ──────────────────────────────────────────────


def test_participant_never_sees_stock_or_weight(client, festival, db):
    _add_prize(db, festival, name="막국수 쿠폰", stock=7, weight=42)
    db.commit()
    _, headers = _issue(client, festival)

    r = client.get(f"/api/festivals/{festival.id}/prize-draw/me", headers=headers)
    assert r.status_code == 200
    assert "stock" not in r.text
    assert "weight" not in r.text
    assert '"7"' not in r.text and ": 7" not in r.text
    assert r.json()["prizes"][0]["name"] == "막국수 쿠폰"


# ── 운영자 ──────────────────────────────────────────────────────────────────


def test_operator_list_warns_when_nothing_can_be_drawn(client, festival, db):
    _add_prize(db, festival, name="소진된 상품", stock=0)
    db.commit()

    body = client.get(f"/api/festivals/{festival.id}/prizes").json()
    assert body["drawable_count"] == 0
    codes = {w["code"] for w in body["warnings"]}
    assert "NO_DRAWABLE_PRIZE" in codes
    assert "NO_BLANK_PRIZE" in codes


def test_operator_sees_winners_and_can_confirm_handover(client, festival, db):
    _add_prize(db, festival, name="막국수 쿠폰", stock=5)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()
    client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)

    listing = client.get(f"/api/festivals/{festival.id}/prize-draws").json()
    assert listing["total"] == 1
    assert listing["unclaimed"] == 1
    row = listing["items"][0]
    assert row["participant_code"] == code
    assert row["claimed_at"] is None

    r = client.post(f"/api/festivals/{festival.id}/prize-draws/{row['id']}/claim")
    assert r.status_code == 200, r.text
    assert r.json()["claimed_at"] is not None

    assert client.get(f"/api/festivals/{festival.id}/prize-draws").json()["unclaimed"] == 0


def test_blank_cannot_be_claimed(client, festival, db):
    """꽝에 수령 확인을 찍으면 미수령 집계가 거짓이 된다."""
    _add_prize(db, festival, name="꽝", is_blank=True)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()
    client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)

    row = client.get(f"/api/festivals/{festival.id}/prize-draws").json()["items"][0]
    r = client.post(f"/api/festivals/{festival.id}/prize-draws/{row['id']}/claim")
    assert r.status_code == 409
    assert _err(r) == "DRAW_NOT_CLAIMABLE"


def test_archived_prize_keeps_past_winners_readable(client, festival, db):
    """상품을 지우면 이미 당첨된 사람의 화면이 빈칸이 된다. 아카이브만 한다."""
    prize = _add_prize(db, festival, name="막국수 쿠폰", stock=5)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()
    client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)

    assert (
        client.post(f"/api/festivals/{festival.id}/prizes/{prize.id}/archive").status_code == 204
    )

    body = client.get(f"/api/festivals/{festival.id}/prize-draw/me", headers=headers).json()
    assert body["draw"]["prize_name"] == "막국수 쿠폰"


# ── 보드 표현 방식 ──────────────────────────────────────────────────────────
#
# 격자↔지도는 같은 타일을 다르게 그릴 뿐입니다. 구조로 취급하면 표현을 바꿀 때마다
# 참여자 전원의 수집이 초기화됩니다 — 축제 당일에 이게 일어나면 되돌릴 수 없습니다.


def test_changing_board_style_keeps_everyones_progress(client, festival, db):
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()

    before = client.get(f"/api/festivals/{festival.id}/stamp-board").json()
    assert before["board_style"] == "grid"

    r = client.put(
        f"/api/festivals/{festival.id}/stamp-board",
        json={
            "rows": before["rows"],
            "cols": before["cols"],
            "reveal_mode": before["reveal_mode"],
            "grant_unit": before["grant_unit"],
            "board_style": "trail",
            "image_url": before["image_url"],
            "complete_message": before["complete_message"],
        },
    )
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["board_style"] == "trail"
    # 버전이 오르면 타일 집합이 새로 생기고 공개 기록이 집계에서 빠진다.
    assert after["version"] == before["version"]

    mine = client.get(f"/api/festivals/{festival.id}/stamp-board/me", headers=headers).json()
    assert mine["progress"]["is_complete"] is True
    assert mine["board_style"] == "trail"


# ── 경품 수령대 ─────────────────────────────────────────────────────────────
#
# 당첨자 목록을 스크롤해 찾는 방식은 현장에서 쓸 수 없습니다. 줄이 서 있고,
# 당첨자가 수백 명이면 멈춥니다. 코드로 바로 찾아야 합니다.
#
# **못 건네는 경우를 오류로 만들지 않습니다.** 꽝·기수령·미뽑기는 전부 정상적인
# 사실이고 스태프가 읽고 안내해야 합니다. 404 로 뭉개면 화면이 "없는 코드"와
# "꽝을 뽑은 사람"을 구분하지 못합니다.


def _lookup(client, festival, code):
    return client.get(f"/api/festivals/{festival.id}/prize-draws/lookup", params={"code": code})


def test_lookup_finds_a_winner_and_marks_it_claimable(client, festival, db):
    _add_prize(db, festival, name="막국수 쿠폰", stock=5)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()
    client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)

    r = _lookup(client, festival, code)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["claimable"] is True
    assert body["reason"] is None
    assert body["draw"]["prize_name"] == "막국수 쿠폰"


def test_lookup_absorbs_spacing_and_case(client, festival, db):
    """코드는 사람이 손으로 옮겨 적는다. 서버가 흡수하지 않으면 그대로 운영 부담이 된다."""
    _add_prize(db, festival, name="막국수 쿠폰", stock=5)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()
    client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)

    messy = f"  {code.lower().replace('-', '- ')}  "
    assert _lookup(client, festival, messy).json()["participant_code"] == code


def test_lookup_says_why_a_blank_cannot_be_claimed(client, festival, db):
    _add_prize(db, festival, name="꽝", is_blank=True)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()
    client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)

    body = _lookup(client, festival, code).json()
    assert body["claimable"] is False
    assert "꽝" in body["reason"]
    # 꽝도 뽑기 기록은 있다 — 화면이 "뽑았다"와 "안 뽑았다"를 구분해야 한다.
    assert body["draw"]["is_blank"] is True


def test_lookup_reports_a_participant_who_has_not_drawn_yet(client, festival, db):
    _add_prize(db, festival, name="막국수 쿠폰", stock=5)
    code, _ = _issue(client, festival)
    db.commit()

    body = _lookup(client, festival, code).json()
    assert body["claimable"] is False
    assert "아직" in body["reason"]
    assert body["draw"] is None


def test_lookup_404s_only_for_an_unknown_code(client, festival, db):
    db.commit()
    r = _lookup(client, festival, "FF-ZZZZZZZZ")
    assert r.status_code == 404
    assert _err(r) == "PARTICIPANT_NOT_FOUND"


def test_claimed_prize_is_not_claimable_twice(client, festival, db):
    _add_prize(db, festival, name="막국수 쿠폰", stock=5)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()
    client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)

    draw_id = _lookup(client, festival, code).json()["draw"]["id"]
    first = client.post(f"/api/festivals/{festival.id}/prize-draws/{draw_id}/claim")
    assert first.status_code == 200
    stamped = first.json()["claimed_at"]

    again = _lookup(client, festival, code).json()
    assert again["claimable"] is False
    assert "이미 수령" in again["reason"]

    # 두 번 눌러도 수령 시각이 덮이지 않는다 — 언제 건넸는지가 흔들리면 안 된다.
    second = client.post(f"/api/festivals/{festival.id}/prize-draws/{draw_id}/claim")
    assert second.status_code == 200
    assert second.json()["claimed_at"] == stamped


def test_participant_sees_the_claim_reflected_on_their_own_screen(client, festival, db):
    """스태프가 건넨 사실이 관객 화면에도 나타나야 한다 — 폴링으로 따라온다."""
    _add_prize(db, festival, name="막국수 쿠폰", stock=5)
    code, headers = _issue(client, festival)
    _complete_board(db, festival, code)
    db.commit()
    client.post(f"/api/festivals/{festival.id}/prize-draw", headers=headers)

    before = client.get(f"/api/festivals/{festival.id}/prize-draw/me", headers=headers).json()
    assert before["draw"]["claimed_at"] is None

    draw_id = before["draw"]["id"]
    client.post(f"/api/festivals/{festival.id}/prize-draws/{draw_id}/claim")

    after = client.get(f"/api/festivals/{festival.id}/prize-draw/me", headers=headers).json()
    assert after["draw"]["claimed_at"] is not None
