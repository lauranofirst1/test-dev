"""오프라인 우선 지급 — 현장에서 누른 시각이 진짜 시각이다. 스펙 §8.1, 계약 §14.3.

축제장 통신은 끊기는 게 기본값입니다. 스태프 화면은 지급을 로컬 큐에 쌓았다가
복구되면 보내는데, 그때 서버가 도달 시각으로 기록하면 **완료가 통신 복구 순간에
몰려 보입니다.** 운영 인사이트의 "최근 30분 편중" 판정과 리포트 시간축이 통째로
왜곡됩니다.

그래서 `queued_at` 을 받아 `completed_at` 으로 씁니다. 다만 그 값은 **클라이언트가
정하는 시각**이라 그대로 믿으면 부스 폰 하나로 완료 시각을 마음대로 적을 수
있습니다. 믿어 줄 범위를 두고, 벗어나면 조용히 버립니다 — 거부하면 줄이 멈춥니다.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    Booth,
    Festival,
    FestivalStaff,
    Mission,
    Organization,
    Participant,
    Participation,
    StampBoard,
)
from festaflow.models.enums import (
    BoothType,
    BoothVerifyMode,
    StaffRole,
)
from festaflow.services import grants as svc

_codes = itertools.count(1)


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
def setup(db: Session, org: Organization):
    from datetime import date

    f = Festival(
        organization_id=org.id,
        name="춘천 가을 먹거리 축제",
        region="강원특별자치도 춘천시",
        venue="공지천 일대",
        starts_on=date(2026, 10, 8),
        ends_on=date(2026, 10, 12),
        expected_visitors=18000,
        total_budget=250000000,
    )
    db.add(f)
    db.flush()
    db.add(StampBoard(festival_id=f.id, rows=2, cols=2))
    booth = Booth(
        festival_id=f.id,
        name="막국수 체험존",
        booth_type=BoothType.FOOD,
        is_active=True,
        verify_mode=BoothVerifyMode.STAFF_SCAN,
    )
    db.add(booth)
    db.flush()
    mission = Mission(
        festival_id=f.id, booth_id=booth.id, title="막국수 만들기", points=100, is_active=True
    )
    db.add(mission)
    staff = FestivalStaff(
        festival_id=f.id,
        role=StaffRole.BOOTH_MANAGER,
        display_name="부스 담당",
        booth_id=booth.id,
        access_code_hash=security.hash_access_code("ABC123"),
    )
    db.add(staff)
    db.flush()
    token, _ = security.issue_staff_token(
        staff_id=staff.id, festival_id=f.id, role=staff.role, booth_id=booth.id
    )
    return f, booth, mission, token


def _participant(db: Session, festival: Festival) -> Participant:
    p = Participant(
        festival_id=festival.id, code=f"FF-{next(_codes):08d}", secret_hash="x"
    )
    db.add(p)
    db.flush()
    return p


def _grant(client: TestClient, setup, participant, **extra) -> dict:
    f, booth, mission, token = setup
    r = client.post(
        f"/api/festivals/{f.id}/booths/{booth.id}/grants",
        json={
            "participant_code": participant.code,
            "mission_id": mission.id,
            "client_request_id": str(uuid.uuid4()),
            **extra,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_현장에서_누른_시각으로_기록된다(
    db: Session, client: TestClient, setup
) -> None:
    """도달 시각으로 기록하면 완료가 통신 복구 순간에 몰려 보인다."""
    f, _, _, _ = setup
    p = _participant(db, f)
    pressed = datetime.now(UTC) - timedelta(minutes=25)

    body = _grant(client, setup, p, queued_at=pressed.isoformat())

    completed = datetime.fromisoformat(body["participation"]["completed_at"])
    assert abs((completed - pressed).total_seconds()) < 2

    row = db.query(Participation).filter(Participation.participant_id == p.id).one()
    assert row.queued_at is not None
    # 도달 시각도 따로 남는다 — 언제 늦게 도착했는지가 사후에 답할 질문이다.
    assert row.synced_at is not None
    assert row.synced_at > row.queued_at


def test_queued_at_이_없으면_서버_시각이다(
    db: Session, client: TestClient, setup
) -> None:
    """온라인 지급은 누른 즉시 도달한다. 그때는 서버 시각이 맞다."""
    f, _, _, _ = setup
    p = _participant(db, f)
    before = datetime.now(UTC)

    body = _grant(client, setup, p)

    completed = datetime.fromisoformat(body["participation"]["completed_at"])
    assert completed >= before - timedelta(seconds=2)
    row = db.query(Participation).filter(Participation.participant_id == p.id).one()
    assert row.queued_at is None
    assert row.synced_at is None


def test_미래_시각은_버린다(db: Session, client: TestClient, setup) -> None:
    """부스 폰 하나로 완료 시각을 앞당겨 적을 수 있으면, 편중 판정을 조작할 수 있다."""
    f, _, _, _ = setup
    p = _participant(db, f)
    future = datetime.now(UTC) + timedelta(hours=3)

    body = _grant(client, setup, p, queued_at=future.isoformat())

    completed = datetime.fromisoformat(body["participation"]["completed_at"])
    # 지급은 성공한다 — 거부하면 줄이 멈춘다. 시각만 서버 것으로 떨어진다.
    assert completed < future
    row = db.query(Participation).filter(Participation.participant_id == p.id).one()
    assert row.queued_at is None


def test_폰_시계가_조금_빠른_것은_받아준다(
    db: Session, client: TestClient, setup
) -> None:
    """시계 오차는 실제로 흔하다. 1분 빠르다고 오프라인 기록을 버리면 안 된다."""
    f, _, _, _ = setup
    p = _participant(db, f)
    slightly_ahead = datetime.now(UTC) + timedelta(seconds=60)

    _grant(client, setup, p, queued_at=slightly_ahead.isoformat())

    row = db.query(Participation).filter(Participation.participant_id == p.id).one()
    assert row.queued_at is not None


def test_하루를_넘긴_큐는_버린다(db: Session, client: TestClient, setup) -> None:
    """축제 하루가 끝나면 그 큐는 의미가 없다. 지난 축제 시간축에 구멍을 내면 안 된다."""
    f, _, _, _ = setup
    p = _participant(db, f)
    stale = datetime.now(UTC) - timedelta(days=3)

    _grant(client, setup, p, queued_at=stale.isoformat())

    row = db.query(Participation).filter(Participation.participant_id == p.id).one()
    assert row.queued_at is None


def test_같은_요청_id_는_두_번_지급하지_않는다(
    db: Session, client: TestClient, setup
) -> None:
    """오프라인 큐는 재전송한다. 재전송이 중복 지급이 되면 오프라인을 쓸 수 없다."""
    f, booth, mission, token = setup
    p = _participant(db, f)
    request_id = str(uuid.uuid4())
    payload = {
        "participant_code": p.code,
        "mission_id": mission.id,
        "client_request_id": request_id,
        "queued_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    }
    url = f"/api/festivals/{f.id}/booths/{booth.id}/grants"
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(url, json=payload, headers=headers).json()
    second = client.post(url, json=payload, headers=headers).json()

    assert first["was_already_granted"] is False
    assert second["was_already_granted"] is True
    assert first["participation"]["id"] == second["participation"]["id"]
    assert db.query(Participation).filter(Participation.participant_id == p.id).count() == 1


def test_신뢰_범위_판정(db: Session) -> None:
    """경계를 직접 두드린다."""
    at = datetime.now(UTC)

    assert svc._trusted_queued_at(None, at) is None
    # 범위 안
    assert svc._trusted_queued_at(at - timedelta(hours=1), at) is not None
    assert svc._trusted_queued_at(at + timedelta(minutes=1), at) is not None
    # 범위 밖
    assert svc._trusted_queued_at(at + timedelta(minutes=5), at) is None
    assert svc._trusted_queued_at(at - timedelta(hours=25), at) is None
    # 타임존 없는 값도 UTC 로 본다 — 손으로 만든 요청이 실제로 온다.
    naive = (at - timedelta(minutes=5)).replace(tzinfo=None)
    assert svc._trusted_queued_at(naive, at) is not None


# ── 통신 상태가 지급액을 바꾸면 안 된다 ─────────────────────────────────────


def test_보너스는_누른_시각으로_찾는다(db: Session, client: TestClient, setup) -> None:
    """도달 시각으로 찾으면 통신이 끊겼다는 이유만으로 참여자가 보너스를 잃는다.

    14시 50분에 "지금 두 배" 를 보고 미션을 했는데 큐가 15시 10분에 풀리면
    캠페인이 이미 끝나 있다. 참여자는 화면에서 약속받은 점수를 못 받고,
    그 사이 아무것도 잘못한 적이 없다.
    """
    from festaflow.services import reward_campaigns as camp

    f, booth, mission, _ = setup
    now = datetime.now(UTC)
    # 이미 끝난 캠페인. 하지만 참여자가 미션을 한 시각에는 살아 있었다.
    camp.create(
        db,
        f.id,
        booth_id=booth.id,
        mission_id=None,
        title="점심 두 배",
        message="지금 가면 두 배",
        bonus_points=100,
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(minutes=20),
    )
    db.commit()

    pressed = now - timedelta(minutes=40)  # 캠페인이 살아 있던 시각
    p = _participant(db, f)
    body = _grant(client, setup, p, queued_at=pressed.isoformat())

    assert body["participation"]["bonus_points"] == 100
    assert body["participation"]["granted_points"] == 200


def test_끝난_뒤에_한_것에는_보너스가_없다(
    db: Session, client: TestClient, setup
) -> None:
    """누른 시각 기준이라는 것은 양쪽으로 성립해야 한다."""
    from festaflow.services import reward_campaigns as camp

    f, booth, mission, _ = setup
    now = datetime.now(UTC)
    camp.create(
        db,
        f.id,
        booth_id=booth.id,
        mission_id=None,
        title="아침 두 배",
        message="지금 가면 두 배",
        bonus_points=100,
        starts_at=now - timedelta(hours=3),
        ends_at=now - timedelta(hours=2),
    )
    db.commit()

    pressed = now - timedelta(minutes=30)  # 캠페인이 이미 끝난 뒤
    p = _participant(db, f)
    body = _grant(client, setup, p, queued_at=pressed.isoformat())

    assert body["participation"]["bonus_points"] == 0


def test_이미_지급된_건은_부스가_닫혀도_성공이다(
    db: Session, client: TestClient, setup
) -> None:
    """오프라인 큐는 재전송한다. 그 사이 운영자가 부스를 중지하면 이미 지급이
    끝난 건이 거절된다 — 스태프 화면에는 "보내지 못했다" 로 뜨지만 실제로는
    이미 지급돼 있다. 그 상태의 진실은 실패가 아니라 성공이다."""
    f, booth, mission, token = setup
    p = _participant(db, f)
    request_id = str(uuid.uuid4())
    payload = {
        "participant_code": p.code,
        "mission_id": mission.id,
        "client_request_id": request_id,
    }
    url = f"/api/festivals/{f.id}/booths/{booth.id}/grants"
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(url, json=payload, headers=headers)
    assert first.status_code == 200

    # 운영자가 부스를 닫았다.
    booth.is_active = False
    db.commit()

    again = client.post(url, json=payload, headers=headers)

    assert again.status_code == 200
    assert again.json()["was_already_granted"] is True
    # 지급은 일어난 시점에 일어난 것이고, 나중에 부스를 닫았다고 없던 일이 되지 않는다.
    assert db.query(Participation).filter(Participation.participant_id == p.id).count() == 1


def test_닫힌_부스에_새_지급은_여전히_막힌다(
    db: Session, client: TestClient, setup
) -> None:
    """멱등 조회를 앞으로 옮긴 것이 활성 검사를 무력화하면 안 된다."""
    f, booth, mission, token = setup
    booth.is_active = False
    db.commit()
    p = _participant(db, f)

    r = client.post(
        f"/api/festivals/{f.id}/booths/{booth.id}/grants",
        json={"participant_code": p.code, "mission_id": mission.id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "BOOTH_INACTIVE"


# ── 클라이언트가 넣는 값은 믿지 않는다 ──────────────────────────────────────


def test_남의_축제_재전송_키로는_열리지_않는다(
    db: Session, client: TestClient, org: Organization, setup
) -> None:
    """`client_request_id` 는 클라이언트가 만들어 보내는 값이고 유니크 제약은
    전역이다. 스코프가 없으면 남의 축제 지급 기록이 `was_already_granted: true`
    와 함께 포인트·미션·부스·완료 시각까지 실려 돌아온다."""
    from datetime import date

    f, booth, mission, token = setup
    p = _participant(db, f)
    rid = str(uuid.uuid4())
    client.post(
        f"/api/festivals/{f.id}/booths/{booth.id}/grants",
        json={"participant_code": p.code, "mission_id": mission.id, "client_request_id": rid},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 다른 축제에서 같은 키를 써 본다.
    other = Festival(
        organization_id=org.id,
        name="옆 축제",
        region="강원특별자치도 춘천시",
        venue="다른 곳",
        starts_on=date(2026, 10, 8),
        ends_on=date(2026, 10, 12),
        expected_visitors=100,
        total_budget=1000000,
    )
    db.add(other)
    db.flush()
    db.add(StampBoard(festival_id=other.id, rows=2, cols=2))
    b2 = Booth(
        festival_id=other.id,
        name="남의 부스",
        booth_type=BoothType.FOOD,
        is_active=True,
        verify_mode=BoothVerifyMode.STAFF_SCAN,
    )
    db.add(b2)
    db.flush()
    m2 = Mission(
        festival_id=other.id, booth_id=b2.id, title="남의 미션", points=50, is_active=True
    )
    db.add(m2)
    db.flush()
    p2 = _participant(db, other)
    db.commit()

    r = client.post(
        f"/api/festivals/{other.id}/booths/{b2.id}/grants",
        json={"participant_code": p2.code, "mission_id": m2.id, "client_request_id": rid},
    )

    # 남의 기록을 돌려주는 대신 이 축제에서 새로 지급해야 한다.
    assert r.status_code == 200
    assert r.json()["was_already_granted"] is False
    assert r.json()["participation"]["mission_id"] == m2.id


def test_uuid_가_아닌_재전송_키는_422(db: Session, client: TestClient, setup) -> None:
    """DB 컬럼이 UUID 라 그냥 통과시키면 Postgres 에서 500 이 되고,
    500 은 큐가 **재시도하는** 응답이라 그 항목 하나가 큐 앞에서 영원히 돈다."""
    f, booth, mission, token = setup
    p = _participant(db, f)

    r = client.post(
        f"/api/festivals/{f.id}/booths/{booth.id}/grants",
        json={
            "participant_code": p.code,
            "mission_id": mission.id,
            "client_request_id": "이건-uuid-가-아니다",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 422


def test_uuid_버전은_강제하지_않는다(db: Session, client: TestClient, setup) -> None:
    """우리 화면은 v4 를 만들지만, 다른 클라이언트가 v1 이나 v7 을 보낼 이유가
    충분하고 그게 재전송 키로서 못할 일이 없다."""
    f, booth, mission, token = setup
    p = _participant(db, f)

    r = client.post(
        f"/api/festivals/{f.id}/booths/{booth.id}/grants",
        json={
            "participant_code": p.code,
            "mission_id": mission.id,
            # UUID v1
            "client_request_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 200
