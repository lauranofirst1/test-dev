"""부스 지급 · 조각 공개 — docs/03-api-contract.md §4, §7, §8, §9.

여기가 축제 당일 현장에서 돌아가는 코드입니다. 중복 지급, 남의 부스 지급,
원격 완료, 오조작으로 인한 수집 초기화 — 되돌릴 수 없는 것들을 전부 막습니다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    Booth,
    Festival,
    FestivalStaff,
    Mission,
    Organization,
    Participation,
    RewardCampaign,
    StampBoard,
    StampReveal,
    StampTile,
)
from festaflow.models.enums import (
    BoothQrMode,
    BoothType,
    BoothVerifyMode,
    GrantUnit,
    RevealMode,
    StaffRole,
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
    """축제 + 3×3 보드 + 타일 9개. 생성 엔드포인트와 같은 모양을 손으로 만든다."""
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
    board = StampBoard(festival_id=f.id, rows=3, cols=3)
    db.add(board)
    db.flush()
    for idx in range(board.total_tiles):
        db.add(StampTile(board_id=board.id, board_version=board.version, tile_index=idx))
    db.flush()
    return f


def _board(db: Session, festival: Festival) -> StampBoard:
    return db.query(StampBoard).filter(StampBoard.festival_id == festival.id).one()


def _make_booth(
    db: Session,
    festival: Festival,
    *,
    name: str = "막국수 체험존",
    verify_mode: BoothVerifyMode = BoothVerifyMode.STAFF_SCAN,
    # 이 파일의 스캔 테스트는 **회전 QR** 을 검증한다. 모델 기본값은 인쇄이므로
    # (지역 축제 천막 부스에 태블릿이 없다는 전제) 여기서 명시해야 한다.
    qr_mode: BoothQrMode = BoothQrMode.ROTATING,
    is_active: bool = True,
    missions: int = 1,
    points: int = 100,
) -> tuple[Booth, list[Mission]]:
    booth = Booth(
        festival_id=festival.id,
        name=name,
        booth_type=BoothType.EXPERIENCE,
        verify_mode=verify_mode,
        qr_mode=qr_mode,
        is_active=is_active,
        qr_secret=b"x" * 32,
    )
    db.add(booth)
    db.flush()
    made = []
    for i in range(missions):
        m = Mission(
            festival_id=festival.id,
            booth_id=booth.id,
            title=f"{name} 미션{i + 1}",
            points=points,
        )
        db.add(m)
        made.append(m)
    db.flush()
    return booth, made


def _issue(client, festival) -> tuple[str, dict]:
    r = client.post(f"/api/festivals/{festival.id}/participants")
    assert r.status_code == 201, r.text
    body = r.json()
    return body["code"], {"X-Participant-Secret": body["secret"]}


def _grant(client, festival, booth, mission, code, **kw):
    return client.post(
        f"/api/festivals/{festival.id}/booths/{booth.id}/grants",
        json={"participant_code": code, "mission_id": mission.id, **kw},
    )


def _err(r) -> str:
    return r.json()["error"]["code"]


# ── 부스 · 미션 (§4) ────────────────────────────────────────────────────────


def test_create_booth_forces_mission_booth_id(client, festival):
    """요청에 다른 booth_id 가 들어와도 방금 만든 부스로 강제한다 — 계약 §4."""
    r = client.post(
        f"/api/festivals/{festival.id}/booths",
        json={
            "name": "막국수 체험존",
            "booth_type": "experience",
            "type_label": "체험",
            "verify_mode": "staff_scan",
            "first_mission": {"title": "막국수 반죽 체험", "points": 100, "booth_id": 999999},
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["first_mission"]["booth_id"] == body["booth"]["id"]


def test_qr_secret_never_appears_in_any_booth_response(client, festival, db):
    booth, _ = _make_booth(db, festival, verify_mode=BoothVerifyMode.PARTICIPANT_SCAN)
    db.commit()

    for r in (
        client.get(f"/api/festivals/{festival.id}/booths"),
        client.get(f"/api/festivals/{festival.id}/booths/{booth.id}/scan-token"),
    ):
        assert r.status_code == 200, r.text
        assert "qr_secret" not in r.text
        assert "7878" not in r.text  # b"xx" 의 hex 표현이 새지 않는지


def test_duplicate_booth_name_is_422_and_keeps_the_festival(client, festival):
    payload = {"name": "막국수 체험존", "booth_type": "experience"}
    assert client.post(f"/api/festivals/{festival.id}/booths", json=payload).status_code == 201
    r = client.post(f"/api/festivals/{festival.id}/booths", json=payload)
    assert r.status_code == 422
    # 첫 부스는 살아 있어야 한다 — 실패 처리가 트랜잭션을 통째로 날리면 안 된다.
    assert client.get(f"/api/festivals/{festival.id}/booths").json()["total"] == 1


def test_mission_cannot_attach_to_another_festivals_booth(client, festival, db, org):
    other = Festival(
        organization_id=org.id,
        name="다른 축제",
        region="서울특별시 영등포구",
        venue="여의도",
        starts_on=date(2026, 9, 30),
        ends_on=date(2026, 10, 1),
        expected_visitors=1000,
        total_budget=1000,
    )
    db.add(other)
    db.flush()
    foreign, _ = _make_booth(db, other, name="남의 부스", missions=0)
    db.commit()

    r = client.post(
        f"/api/festivals/{festival.id}/missions",
        json={"title": "침입", "booth_id": foreign.id},
    )
    assert r.status_code == 400
    assert _err(r) == "MISSION_BOOTH_FESTIVAL_MISMATCH"


def test_archiving_booth_unassigns_missions_and_tiles_but_keeps_grants(client, festival, db):
    booth, [mission] = _make_booth(db, festival)
    tile = db.query(StampTile).filter(StampTile.tile_index == 0).one()
    tile.assigned_booth_id = booth.id
    db.commit()

    code, _ = _issue(client, festival)
    assert _grant(client, festival, booth, mission, code).status_code == 200

    assert (
        client.post(f"/api/festivals/{festival.id}/booths/{booth.id}/archive").status_code == 204
    )

    db.expire_all()
    assert db.get(Mission, mission.id).booth_id is None
    assert db.get(StampTile, tile.id).assigned_booth_id is None
    # 지급 이력은 남는다 — 과거 집계가 소급해서 바뀌면 리포트를 못 믿는다.
    kept = db.query(Participation).filter(Participation.mission_id == mission.id).one()
    assert kept.booth_id == booth.id


# ── 참여자 (§9) ─────────────────────────────────────────────────────────────


def test_issued_code_matches_the_schema_constraint(client, festival):
    code, headers = _issue(client, festival)
    assert code.startswith("FF-") and len(code) == 11
    assert all(c in security.PARTICIPANT_ALPHABET for c in code[3:])
    assert headers["X-Participant-Secret"].startswith("s_")


def test_secret_is_returned_once_and_never_again(client, festival):
    code, headers = _issue(client, festival)
    secret = headers["X-Participant-Secret"]
    r = client.get(f"/api/festivals/{festival.id}/participants/me", headers=headers)
    assert r.status_code == 200
    assert secret not in r.text


def test_participant_me_requires_the_secret_not_the_code(client, festival):
    code, headers = _issue(client, festival)
    path = f"/api/festivals/{festival.id}/participants/me"

    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-Participant-Secret": "s_wrong"}).status_code == 401
    # 코드는 부스에서 노출되는 값이라 조회 인증에 쓰이지 않는다.
    assert client.get(path, headers={"X-Participant-Secret": code}).status_code == 401
    assert client.get(path, headers=headers).status_code == 200


def test_public_endpoint_hides_operational_fields(client, festival, db):
    _make_booth(db, festival)
    _make_booth(db, festival, name="중지된 부스", is_active=False)
    db.commit()

    r = client.get(f"/api/festivals/{festival.id}/public")
    assert r.status_code == 200
    body = r.json()
    assert [b["name"] for b in body["booths"]] == ["막국수 체험존"]  # 중지 부스는 안 보인다
    assert body["source_note"] == "출처: ⓒ한국관광공사"
    assert "manager_name" not in r.text
    assert "qr_secret" not in r.text


# ── 스태프 지급 (§8.1) ──────────────────────────────────────────────────────


def test_staff_grant_awards_points_and_reveals_a_tile(client, festival, db):
    booth, [mission] = _make_booth(db, festival)
    db.commit()
    code, headers = _issue(client, festival)

    r = _grant(client, festival, booth, mission, code)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["was_already_granted"] is False
    assert body["participation"]["granted_points"] == 100
    assert body["participation"]["verified_via"] == "staff_scan"
    assert body["revealed_tile"]["board_version"] == 1
    assert body["board_progress"] == {
        "revealed_count": 1,
        "total_tiles": 9,
        "is_complete": False,
    }

    board = client.get(f"/api/festivals/{festival.id}/stamp-board/me", headers=headers).json()
    assert sum(1 for t in board["tiles"] if t["is_revealed"]) == 1


def test_code_is_normalized_before_lookup(client, festival, db):
    """현장에서는 사람이 코드를 손으로 옮겨 적는다. 공백·소문자를 서버가 흡수한다."""
    booth, [mission] = _make_booth(db, festival)
    db.commit()
    code, _ = _issue(client, festival)

    messy = f"  {code.lower()[:6]} {code.lower()[6:]}  "
    r = _grant(client, festival, booth, mission, messy)
    assert r.status_code == 200, r.text


def test_duplicate_grant_returns_existing_state_without_paying_twice(client, festival, db):
    booth, [mission] = _make_booth(db, festival)
    db.commit()
    code, _ = _issue(client, festival)

    first = _grant(client, festival, booth, mission, code).json()
    second = _grant(client, festival, booth, mission, code)
    assert second.status_code == 200
    body = second.json()
    assert body["was_already_granted"] is True
    assert body["participation"]["id"] == first["participation"]["id"]
    assert body["board_progress"]["revealed_count"] == 1

    total = db.query(Participation).filter(Participation.mission_id == mission.id).count()
    assert total == 1


def test_client_request_id_makes_offline_resend_idempotent(client, festival, db):
    booth, [m1] = _make_booth(db, festival)
    db.commit()
    code, _ = _issue(client, festival)
    rid = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"

    a = _grant(client, festival, booth, m1, code, client_request_id=rid)
    b = _grant(client, festival, booth, m1, code, client_request_id=rid)
    assert a.status_code == b.status_code == 200
    assert b.json()["was_already_granted"] is True


def test_grant_rejects_wrong_booth_inactive_booth_and_inactive_mission(client, festival, db):
    booth, [mission] = _make_booth(db, festival)
    other, [other_mission] = _make_booth(db, festival, name="지역상점존")
    db.commit()
    code, _ = _issue(client, festival)

    r = _grant(client, festival, booth, other_mission, code)
    assert r.status_code == 409
    assert _err(r) == "MISSION_NOT_IN_BOOTH"

    mission.is_active = False
    db.commit()
    r = _grant(client, festival, booth, mission, code)
    assert r.status_code == 409
    assert _err(r) == "MISSION_INACTIVE"

    mission.is_active = True
    booth.is_active = False
    db.commit()
    r = _grant(client, festival, booth, mission, code)
    assert r.status_code == 409
    assert _err(r) == "BOOTH_INACTIVE"


def test_unknown_participant_code_is_404(client, festival, db):
    booth, [mission] = _make_booth(db, festival)
    db.commit()
    r = _grant(client, festival, booth, mission, "FF-ZZZZZZZZ")
    assert r.status_code == 404
    assert _err(r) == "PARTICIPANT_NOT_FOUND"


def test_staff_grant_refused_on_participant_scan_booth(client, festival, db):
    booth, [mission] = _make_booth(db, festival, verify_mode=BoothVerifyMode.PARTICIPANT_SCAN)
    db.commit()
    code, _ = _issue(client, festival)
    r = _grant(client, festival, booth, mission, code)
    assert r.status_code == 409
    assert _err(r) == "BOOTH_MODE_MISMATCH"


def test_booth_manager_cannot_grant_for_another_booth(client, festival, db):
    """역할 검사만으로는 부족하다 — booth_manager 는 부스까지 봐야 한다."""
    mine, [my_mission] = _make_booth(db, festival, name="내 부스")
    theirs, [their_mission] = _make_booth(db, festival, name="남의 부스")
    staff = FestivalStaff(
        festival_id=festival.id,
        role=StaffRole.BOOTH_MANAGER,
        display_name="김부스",
        booth_id=mine.id,
        access_code_hash=security.hash_access_code("8K2QD7"),
    )
    db.add(staff)
    db.commit()

    token = client.post(
        "/api/auth/staff/login",
        json={"festival_id": festival.id, "staff_id": staff.id, "access_code": "8K2QD7"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    code, _ = _issue(client, festival)

    ok = client.post(
        f"/api/festivals/{festival.id}/booths/{mine.id}/grants",
        json={"participant_code": code, "mission_id": my_mission.id},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text

    denied = client.post(
        f"/api/festivals/{festival.id}/booths/{theirs.id}/grants",
        json={"participant_code": code, "mission_id": their_mission.id},
        headers=headers,
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["details"]["assigned_booth_id"] == mine.id


# ── 보상 캠페인 보너스 ──────────────────────────────────────────────────────


def _campaign(db, festival, booth, *, bonus: int, mission_id=None, active=True, past=False):
    now = datetime.now(UTC)
    c = RewardCampaign(
        festival_id=festival.id,
        booth_id=booth.id,
        mission_id=mission_id,
        title=f"보너스 {bonus}",
        message="지금 방문하면 추가 포인트",
        bonus_points=bonus,
        starts_at=now - timedelta(hours=2 if past else 1),
        ends_at=now - timedelta(hours=1) if past else now + timedelta(hours=1),
        is_active=active,
    )
    db.add(c)
    db.flush()
    return c


def test_active_campaign_adds_bonus_and_overlaps_take_the_max_only(client, festival, db):
    """겹치면 합산하지 않고 최대 보너스 1건만 적용한다."""
    booth, [mission] = _make_booth(db, festival, points=100)
    small = _campaign(db, festival, booth, bonus=20)
    big = _campaign(db, festival, booth, bonus=50, mission_id=mission.id)
    db.commit()

    code, _ = _issue(client, festival)
    body = _grant(client, festival, booth, mission, code).json()
    assert body["participation"]["base_points"] == 100
    assert body["participation"]["bonus_points"] == 50  # 20+50 이 아니다
    assert body["participation"]["granted_points"] == 150
    assert body["participation"]["reward_campaign_id"] == big.id
    assert small.id != big.id


def test_expired_or_disabled_campaign_gives_no_bonus(client, festival, db):
    booth, [mission] = _make_booth(db, festival, points=100)
    _campaign(db, festival, booth, bonus=50, past=True)
    _campaign(db, festival, booth, bonus=70, active=False)
    db.commit()

    code, _ = _issue(client, festival)
    body = _grant(client, festival, booth, mission, code).json()
    assert body["participation"]["bonus_points"] == 0
    assert body["participation"]["reward_campaign_id"] is None


# ── 조각 공개 규칙 (§7) ─────────────────────────────────────────────────────


def test_grant_unit_booth_gives_one_tile_per_booth_but_still_pays(client, festival, db):
    """부스당 1조각 — 순회를 유도한다. 두 번째 미션은 포인트만 준다."""
    booth, [m1, m2] = _make_booth(db, festival, missions=2, points=100)
    db.commit()
    code, _ = _issue(client, festival)

    first = _grant(client, festival, booth, m1, code).json()
    second = _grant(client, festival, booth, m2, code).json()

    assert first["revealed_tile"] is not None
    assert second["revealed_tile"] is None
    assert second["participation"]["granted_points"] == 100  # 포인트는 준다
    assert second["board_progress"]["revealed_count"] == 1


def test_grant_unit_mission_gives_a_tile_per_mission(client, festival, db):
    board = _board(db, festival)
    board.grant_unit = GrantUnit.MISSION
    booth, [m1, m2] = _make_booth(db, festival, missions=2)
    db.commit()
    code, _ = _issue(client, festival)

    _grant(client, festival, booth, m1, code)
    second = _grant(client, festival, booth, m2, code).json()
    assert second["revealed_tile"] is not None
    assert second["board_progress"]["revealed_count"] == 2


def test_booth_assigned_mode_reveals_that_booths_tile_then_refuses(client, festival, db):
    board = _board(db, festival)
    board.reveal_mode = RevealMode.BOOTH_ASSIGNED
    board.grant_unit = GrantUnit.MISSION
    booth, [m1, m2] = _make_booth(db, festival, missions=2)
    tile = db.query(StampTile).filter(StampTile.tile_index == 4).one()
    tile.assigned_booth_id = booth.id
    db.commit()

    code, _ = _issue(client, festival)
    first = _grant(client, festival, booth, m1, code)
    assert first.json()["revealed_tile"]["tile_index"] == 4

    second = _grant(client, festival, booth, m2, code)
    assert second.status_code == 409
    assert _err(second) == "NO_TILE_AVAILABLE"


def test_board_completion_reveals_the_complete_message(client, festival, db):
    """미완성 상태에서 완성 문구를 미리 보여주면 완성의 의미가 없다."""
    board = _board(db, festival)
    board.rows, board.cols = 2, 2
    for t in db.query(StampTile).filter(StampTile.tile_index >= 4).all():
        db.delete(t)
    booths = [_make_booth(db, festival, name=f"부스{i}") for i in range(4)]
    db.commit()

    code, headers = _issue(client, festival)
    path = f"/api/festivals/{festival.id}/stamp-board/me"

    for i, (booth, [mission]) in enumerate(booths):
        body = _grant(client, festival, booth, mission, code).json()
        seen = client.get(path, headers=headers).json()
        if i < 3:
            assert seen["progress"]["is_complete"] is False
            assert seen["complete_message_shown"] is None
        else:
            assert body["board_progress"]["is_complete"] is True
            assert seen["complete_message_shown"] == board.complete_message


# ── 부스 QR 스캔 (§8.2, §8.3) ───────────────────────────────────────────────


@pytest.fixture
def scan_booth(db: Session, festival: Festival):
    booth, missions = _make_booth(
        db, festival, verify_mode=BoothVerifyMode.PARTICIPANT_SCAN, missions=2
    )
    db.commit()
    return booth, missions


def _token(booth: Booth, *, back: int = 0) -> str:
    return security.booth_scan_token(
        booth.qr_secret, booth.id, security.current_window() - back
    )


def test_scan_token_only_for_participant_scan_booths(client, festival, db, scan_booth):
    booth, _ = scan_booth
    r = client.get(f"/api/festivals/{festival.id}/booths/{booth.id}/scan-token")
    assert r.status_code == 200, r.text
    body = r.json()
    # 계약 §8.2 는 30초 갱신을 명시한다. 설정으로 바꿀 수 있게 두되 기본값을 지킨다.
    assert body["refresh_after_seconds"] == settings.scan_token_window_seconds == 30
    assert f"b={booth.id}" in body["scan_url"] and "t=" in body["scan_url"]

    staff_booth, _ = _make_booth(db, festival, name="스태프 확인 부스")
    db.commit()
    r = client.get(f"/api/festivals/{festival.id}/booths/{staff_booth.id}/scan-token")
    assert r.status_code == 409
    assert _err(r) == "BOOTH_MODE_MISMATCH"


def test_scan_grant_accepts_current_and_previous_window(client, festival, scan_booth):
    """갱신 직전에 스캔한 참여자를 실패시키지 않는다."""
    booth, [m1, m2] = scan_booth
    code, headers = _issue(client, festival)
    path = f"/api/festivals/{festival.id}/scan-grants"

    r = client.post(
        path, json={"booth_id": booth.id, "token": _token(booth), "mission_id": m1.id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["participation"]["verified_via"] == "participant_scan"

    r = client.post(
        path,
        json={"booth_id": booth.id, "token": _token(booth, back=1), "mission_id": m2.id},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_old_token_is_410_and_foreign_token_is_400(client, festival, db, scan_booth):
    booth, [m1, _] = scan_booth
    code, headers = _issue(client, festival)
    path = f"/api/festivals/{festival.id}/scan-grants"

    expired = client.post(
        path,
        json={"booth_id": booth.id, "token": _token(booth, back=3), "mission_id": m1.id},
        headers=headers,
    )
    assert expired.status_code == 410
    assert _err(expired) == "SCAN_TOKEN_EXPIRED"

    other, _ = _make_booth(
        db, festival, name="다른 스캔 부스", verify_mode=BoothVerifyMode.PARTICIPANT_SCAN
    )
    db.commit()
    forged = client.post(
        path,
        json={"booth_id": booth.id, "token": _token(other), "mission_id": m1.id},
        headers=headers,
    )
    assert forged.status_code == 400
    assert _err(forged) == "SCAN_TOKEN_INVALID"


def test_one_scan_grants_one_mission_only(client, festival, scan_booth):
    """부스 QR 은 방문을 확인할 뿐이다. 한 번 스캔으로 미션을 쓸어담지 못한다."""
    booth, [m1, m2] = scan_booth
    code, headers = _issue(client, festival)
    path = f"/api/festivals/{festival.id}/scan-grants"
    token = _token(booth)

    assert client.post(
        path, json={"booth_id": booth.id, "token": token, "mission_id": m1.id}, headers=headers
    ).status_code == 200

    second = client.post(
        path, json={"booth_id": booth.id, "token": token, "mission_id": m2.id}, headers=headers
    )
    assert second.status_code == 409
    assert _err(second) == "SCAN_ALREADY_USED"


def test_scan_context_marks_granted_missions_and_used_scan(client, festival, scan_booth):
    booth, [m1, m2] = scan_booth
    code, headers = _issue(client, festival)
    token = _token(booth)
    path = f"/api/festivals/{festival.id}/scan"

    before = client.get(
        path, params={"booth_id": booth.id, "token": token}, headers=headers
    ).json()
    assert before["scan_already_used"] is False
    assert [m["already_granted"] for m in before["missions"]] == [False, False]
    assert "answer_index" not in str(before)

    # 화면이 카운트다운에 쓰는 값은 accepted_until 이다. 서버가 직전 window 까지
    # 인정하므로 expires_at 보다 정확히 한 window 뒤이고, 남은 시간도 그만큼 길다.
    window = settings.scan_token_window_seconds
    expires = datetime.fromisoformat(before["expires_at"])
    accepted = datetime.fromisoformat(before["accepted_until"])
    assert (accepted - expires).total_seconds() == window
    # 토큰 생성과 서버 판정 사이에 window 가 넘어가면 서버는 직전 window 로 맞춘다.
    # 그때 남은 시간은 한 window 아래로 떨어지므로 하한을 걸면 시간 경계에서 흔들린다.
    assert 0 < before["seconds_remaining"] <= window * 2

    client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        json={"booth_id": booth.id, "token": token, "mission_id": m1.id},
        headers=headers,
    )
    after = client.get(
        path, params={"booth_id": booth.id, "token": token}, headers=headers
    ).json()
    assert after["scan_already_used"] is True
    assert [m["already_granted"] for m in after["missions"]] == [True, False]


def test_scan_endpoints_need_participant_auth(client, festival, scan_booth):
    booth, [m1, _] = scan_booth
    assert client.get(
        f"/api/festivals/{festival.id}/scan",
        params={"booth_id": booth.id, "token": _token(booth)},
    ).status_code == 401
    assert client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        json={"booth_id": booth.id, "token": _token(booth), "mission_id": m1.id},
    ).status_code == 401


# ── 보드 변경 (§7) ──────────────────────────────────────────────────────────


def _put_board(client, festival, **over):
    body = {
        "rows": 3,
        "cols": 3,
        "reveal_mode": "random",
        "grant_unit": "booth",
        "image_url": "/images/chuncheon-stamp-board.png",
        "complete_message": "모든 축제 조각을 완성했습니다!",
    }
    body.update(over)
    return client.put(f"/api/festivals/{festival.id}/stamp-board", json=body, **over.pop("kw", {}))


def test_cosmetic_change_keeps_the_version_and_progress(client, festival, db):
    booth, [mission] = _make_booth(db, festival)
    db.commit()
    code, _ = _issue(client, festival)
    _grant(client, festival, booth, mission, code)

    r = _put_board(client, festival, image_url="/images/new.png", complete_message="완성!")
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1
    assert db.query(StampReveal).count() == 1


def test_structural_change_needs_confirmation_when_progress_exists(client, festival, db):
    booth, [mission] = _make_booth(db, festival)
    db.commit()
    code, _ = _issue(client, festival)
    _grant(client, festival, booth, mission, code)

    r = _put_board(client, festival, rows=2, cols=2)
    assert r.status_code == 409
    body = r.json()["error"]
    assert body["code"] == "BOARD_RESET_REQUIRES_CONFIRMATION"
    assert body["details"] == {"affected_participants": 1, "revealed_count": 1}
    assert _board(db, festival).version == 1  # 아무것도 바뀌지 않았다


def test_confirmed_reset_bumps_version_and_preserves_old_reveals(client, festival, db):
    booth, [mission] = _make_booth(db, festival)
    db.commit()
    code, headers = _issue(client, festival)
    _grant(client, festival, booth, mission, code)

    r = client.put(
        f"/api/festivals/{festival.id}/stamp-board",
        params={"confirm": "true"},
        json={
            "rows": 2,
            "cols": 2,
            "reveal_mode": "random",
            "grant_unit": "booth",
            "image_url": "/images/chuncheon-stamp-board.png",
            "complete_message": "모든 축제 조각을 완성했습니다!",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    assert r.json()["total_tiles"] == 4

    # 과거 기록은 지우지 않는다 — 이전 버전 기록으로 남는다.
    assert db.query(StampReveal).count() == 1
    assert db.query(StampReveal).one().board_version == 1
    # 참여자 보드는 현재 버전만 집계한다.
    seen = client.get(f"/api/festivals/{festival.id}/stamp-board/me", headers=headers).json()
    assert seen["progress"] == {"revealed_count": 0, "total_tiles": 4, "is_complete": False}


def test_board_uncompletable_warning(festival, db):
    """9조각인데 활성 부스가 5개면 완성이 불가능하다 — 당일에 알면 늦다."""
    from festaflow.services import grants as g

    for i in range(5):
        _make_booth(db, festival, name=f"부스{i}")
    db.commit()

    board = _board(db, festival)
    warning = g.uncompletable_warning(db, festival.id, board)
    assert warning is not None
    assert warning["code"] == "BOARD_UNCOMPLETABLE"
    assert "9조각" in warning["message"] and "5개" in warning["message"]
    # 받침 없는 "부스"에는 `가`, 받침 있는 "미션"에는 `이` 가 붙어야 한다.
    assert "활성 부스가" in warning["message"]

    board.grant_unit = GrantUnit.MISSION
    db.flush()
    mission_warning = g.uncompletable_warning(db, festival.id, _board(db, festival))
    assert mission_warning is not None
    assert "활성 미션이" in mission_warning["message"]

    for i in range(5, 9):
        _make_booth(db, festival, name=f"부스{i}")
    db.commit()
    assert g.uncompletable_warning(db, festival.id, _board(db, festival)) is None
