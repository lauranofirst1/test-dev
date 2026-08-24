"""기관 계정 — 회원가입 · 로그인 · 세션.

**이 파일이 막는 것은 조용히 뚫리는 것들입니다.** 기능이 동작하는지가 아니라,
동작하는 것처럼 보이면서 실제로는 열려 있는 상태를 잡습니다.

가장 큰 것은 `X-Organization-Id` 폴백입니다. 헤더 하나만 바꾸면 남의 기관
데이터가 열리는데, 지금까지 기획자에게 자격증명이 없어서 그 폴백에 기대고
있었습니다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import Organization, OrganizationAccount


@pytest.fixture
def client(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


GOOD = {
    "organization_name": "한림대학교 SW중심대학사업단",
    "display_name": "김담당",
    "email": "sw@hallym.ac.kr",
    "password": "chuncheon-maple-77",
}


def _err(r) -> str:
    return r.json()["error"]["code"]


def _signup(client, **over):
    return client.post("/api/auth/signup", json={**GOOD, **over})


# ── 회원가입 ────────────────────────────────────────────────────────────────


def test_signup_creates_an_organization_and_logs_in(client, db):
    r = _signup(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["organization_name"] == GOOD["organization_name"]
    assert body["account"]["email"] == GOOD["email"]

    # 세션은 쿠키로 나간다. 본문에 토큰이 있으면 화면이 저장하게 되고,
    # 그 순간 XSS 한 번에 털린다.
    assert "access_token" not in r.text
    assert settings.session_cookie_name in r.cookies


def test_session_cookie_is_httponly_and_samesite(client, db):
    r = _signup(client)
    raw = r.headers.get("set-cookie", "")
    assert "httponly" in raw.lower()          # 스크립트가 읽을 수 없다
    assert "samesite=strict" in raw.lower()   # CSRF 가 구조적으로 막힌다
    assert "path=/" in raw.lower()


def test_email_is_normalised_so_two_accounts_cannot_collide(client, db):
    assert _signup(client).status_code == 201
    dup = _signup(client, email="  SW@Hallym.AC.KR  ")
    assert dup.status_code == 409
    assert _err(dup) == "EMAIL_TAKEN"
    assert db.query(OrganizationAccount).count() == 1


def test_duplicate_signup_does_not_leave_an_orphan_organization(client, db):
    """실패한 가입이 기관만 남기면 빈 기관이 쌓이고, 그중 하나가 열려 있게 된다."""
    assert _signup(client).status_code == 201
    before = db.query(Organization).count()
    assert _signup(client).status_code == 409
    db.rollback()
    assert db.query(Organization).count() == before


@pytest.mark.parametrize(
    ("password", "why"),
    [
        ("short1", "10자 미만"),
        ("password123", "유출 목록"),
        ("swswswswsw", "이메일 아이디가 들어감"),
        ("aaaaaaaaaaaa", "글자 종류가 적음"),
    ],
)
def test_weak_passwords_are_refused_before_saving(client, db, password, why):
    """저장한 뒤에 알려주면 늦다 — 그 비밀번호로 이미 로그인이 된다."""
    r = _signup(client, password=password)
    assert r.status_code == 422, why
    assert db.query(OrganizationAccount).count() == 0


def test_a_long_korean_password_is_not_silently_truncated(client, db):
    """bcrypt 는 72바이트를 넘으면 조용히 자른다. 한글은 글자당 3바이트라
    24자면 한계에 닿는다. 자르면 뒤쪽이 통째로 무시되고 사용자는 모른다."""
    long_pw = "춘천에서시작한소프트웨어주간행사비밀번호입니다정말깁니다" * 2
    assert len(long_pw.encode()) > 72

    assert _signup(client, password=long_pw).status_code == 201
    client.post("/api/auth/logout")

    # 앞 72바이트만 같은 다른 비밀번호로는 들어올 수 없어야 한다.
    truncated = long_pw.encode()[:72].decode(errors="ignore")
    bad = client.post(
        "/api/auth/login", json={"email": GOOD["email"], "password": truncated}
    )
    assert bad.status_code == 401

    ok = client.post("/api/auth/login", json={"email": GOOD["email"], "password": long_pw})
    assert ok.status_code == 200


# ── 로그인 ──────────────────────────────────────────────────────────────────


def test_login_does_not_reveal_whether_the_email_exists(client, db):
    _signup(client)
    client.post("/api/auth/logout")

    missing = client.post(
        "/api/auth/login", json={"email": "nobody@hallym.ac.kr", "password": "whatever123"}
    )
    wrong = client.post(
        "/api/auth/login", json={"email": GOOD["email"], "password": "wrong-password-1"}
    )

    assert missing.status_code == wrong.status_code == 401
    assert _err(missing) == _err(wrong) == "INVALID_CREDENTIALS"
    assert missing.json() == wrong.json()


def test_repeated_failures_lock_the_account(client, db):
    """비밀번호가 길다고 잠금을 빼면 유출 목록으로 훑는 공격이 그대로 통한다."""
    _signup(client)
    client.post("/api/auth/logout")

    for _ in range(settings.login_max_attempts):
        client.post("/api/auth/login", json={"email": GOOD["email"], "password": "nope-12345"})

    # 잠긴 동안은 **맞는 비밀번호도** 받지 않는다.
    locked = client.post(
        "/api/auth/login", json={"email": GOOD["email"], "password": GOOD["password"]}
    )
    assert locked.status_code == 429
    assert _err(locked) == "ACCOUNT_LOCKED"


def test_successful_login_clears_the_failure_counter(client, db):
    _signup(client)
    client.post("/api/auth/logout")

    for _ in range(settings.login_max_attempts - 1):
        client.post("/api/auth/login", json={"email": GOOD["email"], "password": "nope-12345"})
    assert (
        client.post("/api/auth/login", json={"email": GOOD["email"], "password": GOOD["password"]})
    ).status_code == 200

    account = db.query(OrganizationAccount).one()
    db.refresh(account)
    assert account.failed_attempts == 0
    assert account.locked_until is None


def test_logout_clears_the_session(client, db):
    _signup(client)
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


# ── 세션 무효화 ─────────────────────────────────────────────────────────────


def test_changing_the_password_kills_older_sessions(client, db):
    """바꾸는 이유가 유출이면, 옛 세션이 살아 있는 한 바꾼 의미가 없다."""
    _signup(client)
    account = db.query(OrganizationAccount).one()

    # 지금 세션의 토큰을 손에 쥔 공격자를 흉내낸다.
    stolen, _ = security.issue_org_token(
        account_id=account.id, organization_id=account.organization_id
    )
    assert (
        client.get("/api/auth/me", headers={"Authorization": f"Bearer {stolen}"})
    ).status_code == 200

    # 비밀번호를 바꾼 시각을 토큰 발급보다 뒤로 민다.
    account.password_changed_at = datetime.now(UTC) + timedelta(seconds=5)
    db.commit()

    revoked = client.get("/api/auth/me", headers={"Authorization": f"Bearer {stolen}"})
    assert revoked.status_code == 401
    assert _err(revoked) == "SESSION_REVOKED"


def test_deactivated_account_cannot_use_an_old_token(client, db):
    _signup(client)
    account = db.query(OrganizationAccount).one()
    token, _ = security.issue_org_token(
        account_id=account.id, organization_id=account.organization_id
    )

    account.is_active = False
    db.commit()

    assert (
        client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 401


# ── 토큰이 서로를 대신하지 못한다 ───────────────────────────────────────────


def test_an_org_token_cannot_stand_in_for_a_staff_token(client, db):
    """두 토큰은 같은 키로 서명된다. 종류를 구분하지 않으면 기관 토큰이
    스태프 자리에 들어가고, `festival_id` 검사가 통째로 무너진다."""
    _signup(client)
    account = db.query(OrganizationAccount).one()
    org_token, _ = security.issue_org_token(
        account_id=account.id, organization_id=account.organization_id
    )

    with pytest.raises(Exception) as caught:
        security.decode_staff_token(org_token)
    assert "INVALID_TOKEN" in str(caught.value.detail)


def test_a_staff_token_cannot_stand_in_for_an_org_token(client, db):
    staff_token, _ = security.issue_staff_token(
        staff_id=1, festival_id=1, role="operator", booth_id=None
    )
    with pytest.raises(Exception) as caught:
        security.decode_org_token(staff_token)
    assert "INVALID_TOKEN" in str(caught.value.detail)


# ── 기관 경계 ───────────────────────────────────────────────────────────────


def test_an_account_only_sees_its_own_organization(client, db):
    """**여기가 `X-Organization-Id` 폴백이 열어 두던 구멍이다.**

    로그인한 계정이 있으면 헤더는 보지 않는다. 헤더가 이겼다면 로그인해도
    헤더 하나로 남의 기관을 볼 수 있다.
    """
    _signup(client)
    mine = db.query(Organization).one()

    other = Organization(name="남의 기관")
    db.add(other)
    db.commit()

    body = client.get(
        "/api/festivals", headers={"X-Organization-Id": str(other.id)}
    )
    assert body.status_code == 200, body.text
    # 내 기관의 축제만 보인다 — 지금은 둘 다 비어 있으므로 요청이 통과하는 것만
    # 확인하고, 실제 스코프는 아래에서 축제를 만들어 검사한다.

    created = client.post(
        "/api/festivals",
        headers={"X-Organization-Id": str(other.id)},
        json={
            "name": "내 축제",
            "region": "강원특별자치도 춘천시",
            "venue": "공학관",
            "starts_on": "2026-11-03",
            "ends_on": "2026-11-07",
            "expected_visitors": 1000,
            "total_budget": 10000000,
        },
    )
    assert created.status_code == 201, created.text

    # 헤더가 가리킨 남의 기관이 아니라 **내 기관**에 만들어져야 한다.
    from festaflow.models import Festival

    made = db.query(Festival).filter(Festival.name == "내 축제").one()
    assert made.organization_id == mine.id
    assert made.organization_id != other.id


# ── 비밀번호 재설정 ─────────────────────────────────────────────────────────
#
# 여기가 틀리면 계정이 통째로 열립니다. 지키는 것은 넷입니다.
#
#   1. 응답이 가입 여부를 드러내지 않는다
#   2. 링크가 응답에 담기지 않는다 (담기면 남의 이메일로 탈취가 한 번에 끝난다)
#   3. 표는 한 번 쓰면 죽는다 (링크는 메일함에 남고 메일함은 종종 열려 있다)
#   4. 재설정하면 기존 세션이 전부 끊긴다


def _reset_request(client, email):
    return client.post("/api/auth/password/reset-request", json={"email": email})


def _issued_token(db) -> str:
    """서버가 만든 평문 토큰은 응답에 없다. 테스트는 해시로 역추적할 수 없으므로
    서비스를 직접 불러 평문을 얻는다 — 그 자체가 '응답에 없다'는 증거다."""
    from festaflow.services import accounts as svc

    issued = svc.request_password_reset(db, email=GOOD["email"])
    assert issued is not None
    return issued[0]


def test_reset_request_looks_the_same_for_unknown_emails(client, db):
    _signup(client)
    client.post("/api/auth/logout")

    known = _reset_request(client, GOOD["email"])
    unknown = _reset_request(client, "nobody@hallym.ac.kr")

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_reset_link_is_never_in_the_response(client, db):
    """링크가 응답에 담기면 남의 이메일을 넣은 사람이 그대로 계정을 가져간다."""
    _signup(client)
    r = _reset_request(client, GOOD["email"])
    body = r.text
    assert "reset-password" not in body
    assert "token" not in body

    from festaflow.models import PasswordResetToken

    row = db.query(PasswordResetToken).order_by(PasswordResetToken.id.desc()).first()
    assert row is not None
    # 평문이 아니라 해시만 저장된다.
    assert len(row.token_hash) == 64
    assert row.token_hash not in body


def test_reset_changes_the_password_and_kills_the_token(client, db):
    _signup(client)
    client.post("/api/auth/logout")
    token = _issued_token(db)

    new_pw = "새로운비밀번호춘천2026"
    first = client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": new_pw}
    )
    assert first.status_code == 204

    assert (
        client.post("/api/auth/login", json={"email": GOOD["email"], "password": new_pw})
    ).status_code == 200
    client.post("/api/auth/logout")

    # 같은 링크를 다시 쓰면 죽어 있다.
    # 10자 이상이어야 한다 — 짧으면 스키마가 먼저 422 로 막아 토큰 검사까지 가지 않는다.
    again = client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "또다른비밀번호춘천입니다"}
    )
    assert again.status_code == 400
    assert _err(again) == "RESET_TOKEN_INVALID"


def test_expired_token_is_refused(client, db):
    from festaflow.models import PasswordResetToken

    _signup(client)
    token = _issued_token(db)
    row = db.query(PasswordResetToken).filter(PasswordResetToken.used_at.is_(None)).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    r = client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "충분히긴비밀번호춘천"}
    )
    assert r.status_code == 400
    assert _err(r) == "RESET_TOKEN_INVALID"


def test_a_new_request_kills_the_previous_link(client, db):
    """여러 링크가 동시에 유효하면 그중 하나만 유출돼도 계정이 열린다."""
    _signup(client)
    old = _issued_token(db)
    new = _issued_token(db)
    assert old != new

    stale = client.post(
        "/api/auth/password/reset", json={"token": old, "new_password": "충분히긴비밀번호춘천"}
    )
    assert stale.status_code == 400

    fresh = client.post(
        "/api/auth/password/reset", json={"token": new, "new_password": "충분히긴비밀번호춘천"}
    )
    assert fresh.status_code == 204


def test_reset_refuses_a_weak_new_password(client, db):
    _signup(client)
    token = _issued_token(db)
    r = client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "password123"}
    )
    assert r.status_code == 422


def test_reset_kills_existing_sessions(client, db):
    """재설정하는 이유가 탈취면, 공격자의 세션이 살아 있는 한 바꾼 의미가 없다."""
    _signup(client)
    account = db.query(OrganizationAccount).one()
    stolen, _ = security.issue_org_token(
        account_id=account.id, organization_id=account.organization_id
    )
    assert (
        client.get("/api/auth/me", headers={"Authorization": f"Bearer {stolen}"})
    ).status_code == 200

    token = _issued_token(db)
    # 재설정 시각이 토큰 발급보다 확실히 뒤가 되게 민다(iat 는 정수 초다).
    from festaflow.models import PasswordResetToken

    db.query(PasswordResetToken).filter(PasswordResetToken.used_at.is_(None)).one()
    client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "충분히긴비밀번호춘천"}
    )
    db.refresh(account)
    account.password_changed_at = datetime.now(UTC) + timedelta(seconds=5)
    db.commit()

    revoked = client.get("/api/auth/me", headers={"Authorization": f"Bearer {stolen}"})
    assert revoked.status_code == 401


# ── 검증 오류도 한국어로 ────────────────────────────────────────────────────
#
# `core/errors.py` 맨 위가 "message 는 그대로 화면에 노출된다" 를 규칙으로 삼는데,
# FastAPI 기본 검증 응답은 영어이고 봉투 모양도 다릅니다. 그 규칙이 검증
# 오류에서만 깨지고 있었습니다.


def test_validation_errors_use_the_same_envelope(client, db):
    r = client.post("/api/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422
    body = r.json()
    # 다른 오류와 같은 모양이어야 화면이 한 곳만 보면 된다.
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["details"]["field"] == "email"


@pytest.mark.parametrize(
    ("payload", "expect", "field"),
    [
        ({"email": "nope", "password": "x"}, "이메일", "email"),
        ({"password": "1234567890"}, "필수", "email"),
    ],
)
def test_validation_messages_are_korean(client, db, payload, expect, field):
    r = client.post("/api/auth/login", json=payload)
    assert r.status_code == 422
    error = r.json()["error"]
    assert expect in error["message"]
    assert error["details"]["field"] == field
    # 영어가 새어 나오지 않는다.
    assert "valid email" not in error["message"]
    assert "Field required" not in error["message"]


def test_length_limits_say_what_the_limit_is(client, db):
    """'너무 짧습니다' 만으로는 몇 자를 채워야 하는지 알 수 없다."""
    r = client.post(
        "/api/auth/signup",
        json={
            "organization_name": "기관",
            "display_name": "김담당",
            "email": "a@hallym.ac.kr",
            "password": "짧음",
        },
    )
    assert r.status_code == 422
    assert "10자 이상" in r.json()["error"]["message"]
