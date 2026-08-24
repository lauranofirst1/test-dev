"""스태프 발급 · 재발급 · 비활성화 — 계약 §1.

**평문 접근 코드는 발급 응답에서만 나옵니다.** 저장하는 것은 bcrypt 해시뿐이라
서버도 다시 알아낼 수 없습니다. 잃어버리면 재발급이 유일한 길이며, 그게 맞습니다 —
서버가 되읽을 수 있다면 유출됐을 때 전부 함께 나갑니다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core.config import settings
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import Booth, Festival, FestivalStaff, Organization
from festaflow.models.enums import BoothType, StaffRole


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="한림대학교 SW중심대학사업단")
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
        name="제9회 Hallym SW Week",
        region="강원특별자치도 춘천시",
        venue="한림대학교 공학관",
        starts_on=date(2026, 11, 2),
        ends_on=date(2026, 11, 6),
        expected_visitors=1200,
        total_budget=11800000,
    )
    db.add(f)
    db.flush()
    return f


def _err(r) -> str:
    return r.json()["error"]["code"]


def _issue(client, festival, **over):
    return client.post(
        f"/api/festivals/{festival.id}/staff",
        json={"display_name": "김심사", "role": "judge", **over},
    )


# ── 발급 ────────────────────────────────────────────────────────────────────


def test_issue_returns_the_code_once_and_stores_only_a_hash(client, festival, db):
    db.commit()
    r = _issue(client, festival)
    assert r.status_code == 201, r.text
    body = r.json()

    code = body["access_code"]
    assert len(code) == 6
    # 헷갈리는 글자는 알파벳에서 빠져 있다 — 종이에서 읽어 폰에 옮겨 적는 값이다.
    assert not set(code) & set("01OI")

    staff = db.query(FestivalStaff).filter(FestivalStaff.id == body["staff"]["id"]).one()
    assert staff.access_code_hash != code
    assert staff.access_code_hash.startswith("$2b$")

    # 목록에는 코드도 해시도 나오지 않는다.
    listing = client.get(f"/api/festivals/{festival.id}/staff")
    assert code not in listing.text
    assert "access_code" not in listing.text
    assert staff.access_code_hash not in listing.text


def test_invite_url_carries_no_secret(client, festival, db):
    """QR 사진이 유출돼도 코드 없이는 들어올 수 없다는 것이 2단계의 요점이다."""
    db.commit()
    body = _issue(client, festival).json()
    # 브라우저가 쓰는 것은 경로다 — 전체 주소는 API 서버를 가리킬 수 있다.
    assert body["invite_path"].startswith("/staff/login?")
    assert "://" not in body["invite_path"]
    assert f"f={festival.id}" in body["invite_path"]
    assert f"s={body['staff']['id']}" in body["invite_path"]
    assert body["access_code"] not in body["invite_path"]
    assert body["access_code"] not in body["invite_url"]


def test_the_issued_code_actually_logs_in(client, festival, db):
    db.commit()
    body = _issue(client, festival).json()

    r = client.post(
        "/api/auth/staff/login",
        json={
            "festival_id": festival.id,
            "staff_id": body["staff"]["id"],
            "access_code": body["access_code"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["staff"]["role"] == "judge"
    # 세션이 httpOnly 쿠키로도 함께 나간다.
    assert settings.session_cookie_name in r.cookies


def test_two_issues_do_not_share_a_code(client, festival, db):
    db.commit()
    a = _issue(client, festival, display_name="A").json()["access_code"]
    b = _issue(client, festival, display_name="B").json()["access_code"]
    assert a != b


def test_booth_manager_without_a_booth_is_refused(client, festival, db):
    """부스를 안 정하면 그 스태프는 **어느 부스에도 지급할 수 없다.**

    발급은 성공했는데 현장에서 아무것도 못 하는 상태가 된다.
    """
    db.commit()
    r = _issue(client, festival, role="booth_manager", booth_id=None)
    assert r.status_code == 422
    assert r.json()["error"]["details"]["field"] == "booth_id"


def test_booth_manager_cannot_point_at_another_festivals_booth(client, festival, db, org):
    other = Festival(
        organization_id=org.id,
        name="다른 축제",
        region="강원특별자치도 춘천시",
        venue="어딘가",
        starts_on=date(2026, 12, 1),
        ends_on=date(2026, 12, 2),
        expected_visitors=100,
        total_budget=1000000,
    )
    db.add(other)
    db.flush()
    booth = Booth(
        festival_id=other.id, name="남의 부스", booth_type=BoothType.ETC, qr_secret=b"x" * 32
    )
    db.add(booth)
    db.commit()

    r = _issue(client, festival, role="booth_manager", booth_id=booth.id)
    assert r.status_code == 422


# ── 재발급 ──────────────────────────────────────────────────────────────────


def test_rotate_kills_the_old_code(client, festival, db):
    db.commit()
    first = _issue(client, festival).json()
    staff_id = first["staff"]["id"]

    second = client.post(f"/api/festivals/{festival.id}/staff/{staff_id}/rotate")
    assert second.status_code == 200, second.text
    assert second.json()["access_code"] != first["access_code"]

    old = client.post(
        "/api/auth/staff/login",
        json={
            "festival_id": festival.id,
            "staff_id": staff_id,
            "access_code": first["access_code"],
        },
    )
    assert old.status_code == 401

    new = client.post(
        "/api/auth/staff/login",
        json={
            "festival_id": festival.id,
            "staff_id": staff_id,
            "access_code": second.json()["access_code"],
        },
    )
    assert new.status_code == 200


def test_rotate_also_clears_the_lock(client, festival, db):
    """재발행했는데 잠긴 채로 두면 새 코드로도 못 들어온다."""
    db.commit()
    issued = _issue(client, festival).json()
    staff_id = issued["staff"]["id"]

    staff = db.query(FestivalStaff).filter(FestivalStaff.id == staff_id).one()
    staff.failed_attempts = settings.login_max_attempts
    staff.locked_until = datetime.now(UTC) + timedelta(minutes=10)
    db.commit()

    rotated = client.post(f"/api/festivals/{festival.id}/staff/{staff_id}/rotate").json()
    login = client.post(
        "/api/auth/staff/login",
        json={
            "festival_id": festival.id,
            "staff_id": staff_id,
            "access_code": rotated["access_code"],
        },
    )
    assert login.status_code == 200


# ── 비활성화 ────────────────────────────────────────────────────────────────


def test_deactivate_blocks_login_but_keeps_the_row(client, festival, db):
    """행을 지우면 지급 이력의 "누가 줬는지" 가 끊긴다."""
    db.commit()
    issued = _issue(client, festival).json()
    staff_id = issued["staff"]["id"]

    assert (
        client.delete(f"/api/festivals/{festival.id}/staff/{staff_id}")
    ).status_code == 204

    blocked = client.post(
        "/api/auth/staff/login",
        json={
            "festival_id": festival.id,
            "staff_id": staff_id,
            "access_code": issued["access_code"],
        },
    )
    assert blocked.status_code == 401
    assert db.query(FestivalStaff).filter(FestivalStaff.id == staff_id).one() is not None


def test_reactivate_restores_login_with_the_same_code(client, festival, db):
    """비활성화가 코드 유출을 뜻하지는 않는다. 바꿀지는 운영자가 따로 고른다."""
    db.commit()
    issued = _issue(client, festival).json()
    staff_id = issued["staff"]["id"]
    client.delete(f"/api/festivals/{festival.id}/staff/{staff_id}")

    assert (
        client.post(f"/api/festivals/{festival.id}/staff/{staff_id}/reactivate")
    ).status_code == 200
    assert (
        client.post(
            "/api/auth/staff/login",
            json={
                "festival_id": festival.id,
                "staff_id": staff_id,
                "access_code": issued["access_code"],
            },
        )
    ).status_code == 200


def test_unlock_clears_a_lock_without_changing_the_code(client, festival, db):
    """코드를 아는 사람이 오타를 반복한 경우. 새 코드를 다시 전달할 필요가 없다."""
    db.commit()
    issued = _issue(client, festival).json()
    staff_id = issued["staff"]["id"]

    staff = db.query(FestivalStaff).filter(FestivalStaff.id == staff_id).one()
    staff.failed_attempts = settings.login_max_attempts
    staff.locked_until = datetime.now(UTC) + timedelta(minutes=10)
    db.commit()

    assert (
        client.post(f"/api/festivals/{festival.id}/staff/{staff_id}/unlock")
    ).status_code == 200
    assert (
        client.post(
            "/api/auth/staff/login",
            json={
                "festival_id": festival.id,
                "staff_id": staff_id,
                "access_code": issued["access_code"],
            },
        )
    ).status_code == 200


def test_staff_of_another_organization_is_not_reachable(client, festival, db):
    """다른 기관의 축제에 스태프를 발급하거나 목록을 볼 수 없다."""
    other_org = Organization(name="남의 기관")
    db.add(other_org)
    db.flush()
    other = Festival(
        organization_id=other_org.id,
        name="남의 축제",
        region="서울",
        venue="어딘가",
        starts_on=date(2026, 12, 1),
        ends_on=date(2026, 12, 2),
        expected_visitors=100,
        total_budget=1000000,
    )
    db.add(other)
    db.commit()

    # 헤더 폴백이 살아 있는 로컬에서도 **기관 스코프가 다르면** 못 본다.
    r = client.get(f"/api/festivals/{other.id}/staff")
    assert r.status_code == 404
