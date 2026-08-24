"""스태프 인증 — docs/03-api-contract.md §1.

여기가 깨지면 남의 축제 데이터가 새거나, 6자리 코드가 무한 대입에 열립니다.
둘 다 되돌릴 수 없는 종류의 사고입니다.
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
from festaflow.models import Festival, FestivalStaff, Organization
from festaflow.models.enums import StaffRole

CODE = "8K2QD7"

LOGIN = "/api/auth/staff/login"


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="춘천시문화재단")
    db.add(o)
    db.flush()
    return o


def _festival(db: Session, org: Organization, name: str = "춘천 가을 먹거리 축제") -> Festival:
    f = Festival(
        organization_id=org.id,
        name=name,
        region="강원특별자치도 춘천시",
        venue="공지천 조각공원",
        starts_on=date(2026, 10, 10),
        ends_on=date(2026, 10, 12),
        expected_visitors=18000,
        total_budget=240000000,
    )
    db.add(f)
    db.flush()
    return f


def _staff(
    db: Session,
    festival: Festival,
    *,
    role: StaffRole = StaffRole.OPERATOR,
    code: str = CODE,
    is_active: bool = True,
) -> FestivalStaff:
    s = FestivalStaff(
        festival_id=festival.id,
        role=role,
        display_name="김운영",
        access_code_hash=security.hash_access_code(code),
        is_active=is_active,
    )
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def client(db: Session):
    """토큰 흐름을 그대로 태운다 — get_current_org 를 덮어쓰지 않는다."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def festival(db: Session, org: Organization) -> Festival:
    return _festival(db, org)


# ── 로그인 ──────────────────────────────────────────────────────────────────


def test_login_returns_token_with_contract_claims(client, db, festival):
    staff = _staff(db, festival)

    r = client.post(
        LOGIN,
        json={"festival_id": festival.id, "staff_id": staff.id, "access_code": CODE},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.jwt_ttl_hours * 3600
    assert body["staff"] == {
        "id": staff.id,
        "festival_id": festival.id,
        "role": "operator",
        "display_name": "김운영",
        "booth_id": None,
    }

    claims = security.decode_staff_token(body["access_token"])
    assert claims.staff_id == staff.id
    assert claims.festival_id == festival.id
    assert claims.role == "operator"
    assert claims.booth_id is None

    db.refresh(staff)
    assert staff.last_login_at is not None
    assert staff.failed_attempts == 0


def test_login_response_never_contains_the_access_code(client, db, festival):
    staff = _staff(db, festival)
    r = client.post(
        LOGIN,
        json={"festival_id": festival.id, "staff_id": staff.id, "access_code": CODE},
    )
    assert CODE not in r.text
    assert staff.access_code_hash not in r.text


def test_wrong_code_is_401_and_counts_up(client, db, festival):
    staff = _staff(db, festival)
    r = client.post(
        LOGIN,
        json={"festival_id": festival.id, "staff_id": staff.id, "access_code": "WRONG1"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    db.refresh(staff)
    assert staff.failed_attempts == 1


def test_failures_do_not_say_which_part_was_wrong(client, db, festival):
    """축제·스태프·코드를 구분해주면 응답만 보고 유효한 staff_id 를 찾을 수 있다."""
    staff = _staff(db, festival)
    other = _festival(db, festival.organization, name="다른 축제")

    bad_code = client.post(
        LOGIN, json={"festival_id": festival.id, "staff_id": staff.id, "access_code": "WRONG1"}
    )
    bad_staff = client.post(
        LOGIN, json={"festival_id": festival.id, "staff_id": 999999, "access_code": CODE}
    )
    bad_festival = client.post(
        LOGIN, json={"festival_id": other.id, "staff_id": staff.id, "access_code": CODE}
    )

    bodies = {r.json()["error"]["message"] for r in (bad_code, bad_staff, bad_festival)}
    codes = {r.status_code for r in (bad_code, bad_staff, bad_festival)}
    assert codes == {401}
    assert len(bodies) == 1, bodies


def test_inactive_staff_cannot_log_in(client, db, festival):
    staff = _staff(db, festival, is_active=False)
    r = client.post(
        LOGIN, json={"festival_id": festival.id, "staff_id": staff.id, "access_code": CODE}
    )
    assert r.status_code == 401


def test_locks_after_max_attempts_and_refuses_the_right_code(client, db, festival):
    staff = _staff(db, festival)

    for _ in range(settings.login_max_attempts):
        r = client.post(
            LOGIN,
            json={"festival_id": festival.id, "staff_id": staff.id, "access_code": "WRONG1"},
        )
        assert r.status_code == 401

    db.refresh(staff)
    assert staff.locked_until is not None

    # 잠긴 동안은 맞는 코드도 받지 않는다.
    r = client.post(
        LOGIN, json={"festival_id": festival.id, "staff_id": staff.id, "access_code": CODE}
    )
    assert r.status_code == 429
    body = r.json()["error"]
    assert body["code"] == "ACCOUNT_LOCKED"
    assert 0 < body["details"]["retry_after_seconds"] <= settings.login_lock_minutes * 60


def test_lock_expiry_resets_the_counter(client, db, festival):
    staff = _staff(db, festival)
    staff.failed_attempts = settings.login_max_attempts
    staff.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    r = client.post(
        LOGIN, json={"festival_id": festival.id, "staff_id": staff.id, "access_code": CODE}
    )
    assert r.status_code == 200, r.text
    db.refresh(staff)
    assert staff.failed_attempts == 0
    assert staff.locked_until is None


# ── 토큰으로 접근 ───────────────────────────────────────────────────────────


def _token(client, festival, staff, code: str = CODE) -> str:
    r = client.post(
        LOGIN, json={"festival_id": festival.id, "staff_id": staff.id, "access_code": code}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_token_scopes_requests_to_its_own_festival(client, db, festival):
    """같은 기관이어도 A 축제 토큰으로 B 축제를 읽을 수 없다."""
    staff = _staff(db, festival)
    other = _festival(db, festival.organization, name="다른 축제")
    headers = {"Authorization": f"Bearer {_token(client, festival, staff)}"}

    assert client.get(f"/api/festivals/{festival.id}", headers=headers).status_code == 200
    r = client.get(f"/api/festivals/{other.id}", headers=headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_token_decides_the_org_scope_not_the_header(client, db, festival):
    """헤더로 남의 기관을 가리켜도 토큰이 이긴다."""
    staff = _staff(db, festival)
    intruder = Organization(name="남의재단")
    db.add(intruder)
    db.flush()

    r = client.get(
        "/api/festivals",
        headers={
            "Authorization": f"Bearer {_token(client, festival, staff)}",
            "X-Organization-Id": str(intruder.id),
        },
    )
    assert r.status_code == 200
    assert [f["id"] for f in r.json()["items"]] == [festival.id]


def test_booth_manager_can_read_but_not_mutate(client, db, festival):
    staff = _staff(db, festival, role=StaffRole.BOOTH_MANAGER)
    headers = {"Authorization": f"Bearer {_token(client, festival, staff)}"}

    assert client.get(f"/api/festivals/{festival.id}", headers=headers).status_code == 200
    r = client.post(f"/api/festivals/{festival.id}/archive", headers=headers)
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required_roles"] == ["operator", "planner"]


def test_garbage_and_expired_tokens_are_401(client, db, festival):
    staff = _staff(db, festival)
    path = f"/api/festivals/{festival.id}"

    assert client.get(path, headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    # Bearer 가 아닌 스킴
    assert client.get(path, headers={"Authorization": f"Basic {CODE}"}).status_code == 401

    expired = security.jwt.encode(
        {
            "sub": str(staff.id),
            "staff_id": staff.id,
            "festival_id": festival.id,
            "role": "operator",
            "booth_id": None,
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
        },
        settings.jwt_secret,
        algorithm=security.ALGORITHM,
    )
    r = client.get(path, headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


def test_token_signed_with_another_secret_is_rejected(client, db, festival):
    staff = _staff(db, festival)
    forged = security.jwt.encode(
        {
            "sub": str(staff.id),
            "staff_id": staff.id,
            "festival_id": festival.id,
            "role": "operator",
            "booth_id": None,
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        "attacker-secret",
        algorithm=security.ALGORITHM,
    )
    r = client.get(f"/api/festivals/{festival.id}", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_deactivated_staff_token_stops_working_immediately(client, db, festival):
    """해지가 즉시 듣지 않으면 해지가 아니다 — 서명이 맞아도 받지 않는다."""
    staff = _staff(db, festival)
    headers = {"Authorization": f"Bearer {_token(client, festival, staff)}"}
    assert client.get(f"/api/festivals/{festival.id}", headers=headers).status_code == 200

    staff.is_active = False
    db.flush()
    assert client.get(f"/api/festivals/{festival.id}", headers=headers).status_code == 401


# ── 헤더 폴백 ───────────────────────────────────────────────────────────────


def test_header_fallback_is_closed_outside_local(client, db, festival, monkeypatch):
    """폴백이 배포에 실려 나가면 헤더만 바꿔 남의 기관 데이터를 볼 수 있다."""
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    monkeypatch.setattr(settings, "demo_mode", False, raising=False)

    r = client.get("/api/festivals")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"

    r = client.get("/api/festivals", headers={"X-Organization-Id": str(festival.organization_id)})
    assert r.status_code == 401


def test_header_fallback_still_works_locally(client, db, festival):
    """로컬 개발과 데모는 로그인 없이 돌아야 한다 — 프런트에 로그인 화면이 없다."""
    assert settings.app_env == "local"
    r = client.get("/api/festivals")
    assert r.status_code == 200
    assert [f["id"] for f in r.json()["items"]] == [festival.id]


def test_demo_mode_reopens_the_fallback(client, db, festival, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    monkeypatch.setattr(settings, "demo_mode", True, raising=False)
    assert client.get("/api/festivals").status_code == 200


# ── 저장된 해시 ─────────────────────────────────────────────────────────────


def test_access_code_is_bcrypt_hashed_not_stored_plainly(client, db, org):
    """6자리 코드는 조합이 약 10억뿐이라 sha256 이면 유출 시 전수 대입이 된다."""
    payload = {
        "name": "춘천 가을 먹거리 축제",
        "region": "강원특별자치도 춘천시",
        "venue": "공지천 조각공원",
        "starts_on": "2026-10-10",
        "ends_on": "2026-10-12",
        "expected_visitors": 18000,
        "total_budget": 240000000,
    }
    r = client.post("/api/festivals", json=payload)
    assert r.status_code == 201, r.text
    code = r.json()["operator_access_code"]

    staff = (
        db.query(FestivalStaff)
        .filter(FestivalStaff.festival_id == r.json()["festival"]["id"])
        .one()
    )
    assert staff.access_code_hash.startswith("$2b$")
    assert code not in staff.access_code_hash
    assert security.verify_access_code(code, staff.access_code_hash)

    # 발급된 코드로 실제 로그인이 된다 — 생성과 로그인이 같은 해시를 쓴다.
    assert (
        client.post(
            LOGIN,
            json={
                "festival_id": r.json()["festival"]["id"],
                "staff_id": staff.id,
                "access_code": code,
            },
        ).status_code
        == 200
    )


def test_legacy_sha256_hash_fails_closed(db):
    """구 sha256 해시는 검증 불가 → 통과가 아니라 실패로 떨어져야 한다."""
    import hashlib

    legacy = hashlib.sha256(CODE.encode()).hexdigest()
    assert security.verify_access_code(CODE, legacy) is False


def test_default_secret_is_refused_outside_local(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    monkeypatch.setattr(settings, "jwt_secret", "dev-only-change-me", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        security.assert_secret_is_safe()

    monkeypatch.setattr(settings, "jwt_secret", "a" * 64, raising=False)
    security.assert_secret_is_safe()  # 충분히 길면 통과
