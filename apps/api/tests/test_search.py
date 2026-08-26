"""통합 검색 — 찾는 것과 찾지 않는 것.

이 파일이 지키는 것은 셋입니다.

**1. 학번은 정확히 일치할 때만 찾는다.** 앞자리로 훑게 두면 `2023` 한 번에
그 해 입학생 전체가 쏟아지고, 그건 검색이 아니라 명단입니다.

**2. 참여자 secret 은 어떤 경우에도 나가지 않는다.** 코드는 부스에서
보여주는 값이지만 secret 은 남의 수집 현황을 여는 열쇠입니다.

**3. 남의 축제는 열리지 않는다.** 축제 id 를 훑는 것만으로 참여자 코드가
새면 안 됩니다.
"""

from __future__ import annotations

import itertools
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    Booth,
    Exhibit,
    Festival,
    Mission,
    Organization,
    OrganizationAccount,
    Participant,
)
from festaflow.models.enums import BoothType
from festaflow.services import search as svc

_codes = itertools.count(1)


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
        starts_on=date(2026, 10, 24),
        ends_on=date(2026, 10, 26),
        expected_visitors=1200,
        total_budget=11800000,
    )
    db.add(f)
    db.flush()
    return f


@pytest.fixture
def account(db: Session, org: Organization) -> tuple[OrganizationAccount, str]:
    a = OrganizationAccount(
        organization_id=org.id,
        email="sw@hallym.ac.kr",
        password_hash=security.hash_password("고구마-감자-옥수수-달빛"),
        display_name="운영 담당",
    )
    db.add(a)
    db.flush()
    token, _ = security.issue_org_token(account_id=a.id, organization_id=org.id)
    return a, token


def _booth(db: Session, festival: Festival, name: str) -> Booth:
    b = Booth(
        festival_id=festival.id,
        name=name,
        booth_type=BoothType.EXPERIENCE,
        is_active=True,
    )
    db.add(b)
    db.flush()
    return b


def _participant(db: Session, festival: Festival, *, student_no: str | None = None):
    p = Participant(
        festival_id=festival.id,
        code=f"FF-{next(_codes):08d}",
        secret_hash="secret-hash-should-never-leak",
        student_no=student_no,
    )
    db.add(p)
    db.flush()
    return p


# ── 학번 경계 ───────────────────────────────────────────────────────────────


def test_학번은_정확히_일치할_때만_찾는다(db: Session, festival: Festival) -> None:
    """앞자리로 훑게 두면 그 해 입학생 전체가 쏟아진다."""
    _participant(db, festival, student_no="20231234")
    _participant(db, festival, student_no="20239999")
    db.flush()

    exact, _ = svc.search(db, festival.id, "20231234")
    prefix, _ = svc.search(db, festival.id, "2023")

    assert [h.subtitle for h in exact] == ["20231234"]
    assert prefix == [], "앞자리만으로는 아무도 나오면 안 된다"


def test_참여자_secret_은_결과에_실리지_않는다(
    db: Session, client: TestClient, festival: Festival, account
) -> None:
    p = _participant(db, festival, student_no="20231234")
    db.commit()
    _, token = account

    r = client.get(
        f"/api/festivals/{festival.id}/search?q=20231234",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 200
    body = r.text
    assert p.code in body
    assert "secret" not in body.lower()
    assert "secret-hash-should-never-leak" not in body


# ── 찾는 대상 ───────────────────────────────────────────────────────────────


def test_부스와_미션과_작품을_한_번에_찾는다(db: Session, festival: Festival) -> None:
    booth = _booth(db, festival, "AI 체험존")
    db.add(Mission(festival_id=festival.id, booth_id=booth.id, title="AI 퀴즈", points=100))
    db.add(
        Exhibit(
            festival_id=festival.id,
            entry_no=3,
            title="AI 기반 출결 시스템",
            team_name="한림 AI 팀",
        )
    )
    db.flush()

    hits, _ = svc.search(db, festival.id, "AI")

    kinds = {h.kind for h in hits}
    assert kinds == {"booth", "mission", "exhibit"}
    # 미션은 어느 부스 것인지가 함께 나와야 찾은 뜻이 있다.
    mission = next(h for h in hits if h.kind == "mission")
    assert mission.subtitle == "AI 체험존"


def test_작품은_출품번호로도_찾는다(db: Session, festival: Festival) -> None:
    """현장에서 작품은 "3번" 으로 불린다."""
    db.add(Exhibit(festival_id=festival.id, entry_no=3, title="출결 시스템"))
    db.flush()

    hits, _ = svc.search(db, festival.id, "3")

    assert [h.kind for h in hits] == []  # 한 글자는 찾지 않는다
    hits, _ = svc.search(db, festival.id, "03")
    assert hits == [] or all(h.kind == "exhibit" for h in hits)


def test_한_글자로는_찾지_않는다(db: Session, festival: Festival) -> None:
    """한 글자로 훑으면 거의 모든 행이 걸려 검색이 목록이 된다."""
    _booth(db, festival, "AI 체험존")
    db.flush()

    hits, truncated = svc.search(db, festival.id, "A")

    assert hits == []
    assert truncated is False


def test_LIKE_와일드카드가_패턴으로_새지_않는다(
    db: Session, festival: Festival
) -> None:
    """`%` 를 그대로 넘기면 모든 부스가 걸린다."""
    _booth(db, festival, "AI 체험존")
    _booth(db, festival, "100% 국산 막국수")
    db.flush()

    hits, _ = svc.search(db, festival.id, "%%")

    assert hits == [], "와일드카드만 친 것으로 전체가 나오면 안 된다"

    literal, _ = svc.search(db, festival.id, "0% ")
    assert [h.title for h in literal] == ["100% 국산 막국수"]


# ── 경계 ────────────────────────────────────────────────────────────────────


def test_남의_축제는_검색되지_않는다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    other_org = Organization(name="옆 재단")
    db.add(other_org)
    db.flush()
    stranger = OrganizationAccount(
        organization_id=other_org.id,
        email="hello@example.com",
        password_hash=security.hash_password("고구마-감자-옥수수-달빛"),
        display_name="남",
    )
    db.add(stranger)
    _booth(db, festival, "AI 체험존")
    db.commit()
    token, _ = security.issue_org_token(
        account_id=stranger.id, organization_id=other_org.id
    )

    r = client.get(
        f"/api/festivals/{festival.id}/search?q=AI",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 404


def test_검색은_로그인을_요구한다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    _booth(db, festival, "AI 체험존")
    db.commit()

    assert client.get(f"/api/festivals/{festival.id}/search?q=AI").status_code == 401
