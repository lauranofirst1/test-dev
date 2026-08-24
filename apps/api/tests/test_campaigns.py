"""보상 캠페인 — 한시 추가 포인트와 개입 효과.

이 파일이 지키는 것은 셋입니다.

**1. 이미 지급된 보너스는 바뀌지 않는다.** 캠페인을 고치거나 꺼도 과거 지급액은
그대로입니다. 받은 포인트가 나중에 줄어드는 것만큼 현장에서 설명하기 어려운
일이 없습니다.

**2. 활성 판정은 서버가 한다.** 클라이언트가 `ends_at` 을 보고 거르면 폰 시계가
틀어진 만큼 끝난 캠페인이 계속 떠 있습니다.

**3. 전후 변화는 인과 효과가 아니다.** 표본이 얇으면 판정하지 않고, before 가
0건이면 배수를 만들어 내지 않습니다.
"""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    Booth,
    Festival,
    Mission,
    Organization,
    Participant,
    Participation,
    RewardCampaign,
)
from festaflow.models.enums import BoothType, ParticipationStatus
from festaflow.services import reward_campaign_impact as impact
from festaflow.services import reward_campaigns as svc

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
def festival(db: Session, org: Organization) -> Festival:
    f = Festival(
        organization_id=org.id,
        name="춘천 가을 먹거리 축제",
        region="강원특별자치도 춘천시",
        venue="공지천 일대",
        starts_on=date(2026, 10, 8),
        ends_on=date(2026, 10, 12),
        expected_visitors=30000,
        total_budget=250000000,
    )
    db.add(f)
    db.flush()
    return f


def _booth(db: Session, festival: Festival, name: str) -> Booth:
    b = Booth(
        festival_id=festival.id, name=name, booth_type=BoothType.EXPERIENCE, is_active=True
    )
    db.add(b)
    db.flush()
    return b


def _mission(db: Session, festival: Festival, booth: Booth, title: str) -> Mission:
    m = Mission(
        festival_id=festival.id, booth_id=booth.id, title=title, points=100, is_active=True
    )
    db.add(m)
    db.flush()
    return m


def _complete(db: Session, festival: Festival, booth: Booth, *, count: int, at: datetime) -> None:
    for _ in range(count):
        p = Participant(
            festival_id=festival.id, code=f"FF-{next(_codes):08d}", secret_hash="x"
        )
        db.add(p)
        db.flush()
        db.add(
            Participation(
                festival_id=festival.id,
                participant_id=p.id,
                booth_id=booth.id,
                status=ParticipationStatus.COMPLETED,
                completed_at=at,
            )
        )
    db.flush()


def _campaign(db: Session, festival: Festival, booth: Booth, **kw) -> RewardCampaign:
    now = datetime.now(UTC)
    defaults = dict(
        mission_id=None,
        title="지역상점존 두 배",
        message="지금 지역상점존에서 미션을 하면 포인트를 두 배로 드립니다.",
        bonus_points=100,
        starts_at=now - timedelta(minutes=10),
        ends_at=now + timedelta(minutes=20),
    )
    return svc.create(db, festival.id, booth_id=booth.id, **{**defaults, **kw})


# ── 검증 ────────────────────────────────────────────────────────────────────


def test_남의_축제_부스에는_걸_수_없다(
    db: Session, org: Organization, festival: Festival
) -> None:
    """타 축제 부스에 캠페인을 걸면 그 축제 참여자에게 포인트가 나간다."""
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
    theirs = _booth(db, other, "남의 부스")

    with pytest.raises(Exception) as exc:
        _campaign(db, festival, theirs)

    assert getattr(exc.value, "status_code", None) == 404


def test_다른_부스의_미션은_거부한다(db: Session, festival: Festival) -> None:
    """조용히 통과시키면 캠페인이 영원히 안 걸리는데 운영자는 이유를 모른다."""
    a = _booth(db, festival, "지역상점존")
    b = _booth(db, festival, "막국수 체험존")
    mission_of_b = _mission(db, festival, b, "막국수 만들기")

    with pytest.raises(Exception) as exc:
        _campaign(db, festival, a, mission_id=mission_of_b.id)

    assert getattr(exc.value, "status_code", None) == 422


def test_기간이_거꾸로면_거부한다(db: Session, festival: Festival) -> None:
    booth = _booth(db, festival, "지역상점존")
    now = datetime.now(UTC)

    with pytest.raises(Exception) as exc:
        _campaign(db, festival, booth, starts_at=now, ends_at=now - timedelta(minutes=1))

    assert getattr(exc.value, "status_code", None) == 422


def test_24시간을_넘기면_거부한다(db: Session, festival: Festival) -> None:
    """축제 하루보다 길면 "한시" 가 아니다. 그건 미션 포인트를 올리는 것과 같고,
    그쪽은 미션 편집으로 해야 이력이 남는다."""
    booth = _booth(db, festival, "지역상점존")
    now = datetime.now(UTC)

    with pytest.raises(Exception) as exc:
        _campaign(db, festival, booth, starts_at=now, ends_at=now + timedelta(hours=25))

    assert getattr(exc.value, "status_code", None) == 422


# ── 활성 판정 ───────────────────────────────────────────────────────────────


def test_활성_판정은_서버_시각으로_한다(db: Session, festival: Festival) -> None:
    booth = _booth(db, festival, "지역상점존")
    now = datetime.now(UTC)
    live = _campaign(db, festival, booth)
    past = _campaign(
        db,
        festival,
        booth,
        title="끝난 캠페인",
        starts_at=now - timedelta(hours=3),
        ends_at=now - timedelta(hours=2),
    )
    future = _campaign(
        db,
        festival,
        booth,
        title="아직인 캠페인",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
    )

    active = svc.listing(db, festival.id, active_only=True, now=now)

    assert [c.id for c in active] == [live.id]
    assert svc.is_active(past, now=now) is False
    assert svc.is_active(future, now=now) is False


def test_끈_캠페인은_활성이_아니다(db: Session, festival: Festival) -> None:
    booth = _booth(db, festival, "지역상점존")
    c = _campaign(db, festival, booth)
    svc.stop(db, c)

    assert svc.listing(db, festival.id, active_only=True) == []
    # 끄는 것이지 지우는 것이 아니다 — 지급 이력이 이 행을 가리킨다.
    assert svc.get(db, festival.id, c.id).is_active is False


# ── 지급된 보너스는 얼지 않는다 ─────────────────────────────────────────────


def test_캠페인을_고쳐도_과거_지급액은_그대로다(db: Session, festival: Festival) -> None:
    """받은 포인트가 나중에 줄어드는 것만큼 현장에서 설명하기 어려운 일이 없다."""
    booth = _booth(db, festival, "지역상점존")
    c = _campaign(db, festival, booth, bonus_points=100)

    p = Participant(festival_id=festival.id, code=f"FF-{next(_codes):08d}", secret_hash="x")
    db.add(p)
    db.flush()
    granted = Participation(
        festival_id=festival.id,
        participant_id=p.id,
        booth_id=booth.id,
        status=ParticipationStatus.COMPLETED,
        completed_at=datetime.now(UTC),
        base_points=100,
        bonus_points=100,
        reward_campaign_id=c.id,
    )
    db.add(granted)
    db.flush()

    svc.update(db, c, bonus_points=0)
    svc.stop(db, c)
    db.refresh(granted)

    assert granted.bonus_points == 100
    assert granted.granted_points == 200
    assert granted.reward_campaign_id == c.id


# ── 개입 효과 ───────────────────────────────────────────────────────────────


def test_표본이_얇으면_판정하지_않는다(db: Session, festival: Festival) -> None:
    """2건에서 6건이 되면 "200% 증가" 가 되는데 그건 증가가 아니라 잡음이다."""
    booth = _booth(db, festival, "지역상점존")
    start = datetime.now(UTC) - timedelta(hours=2)
    c = _campaign(db, festival, booth, starts_at=start, ends_at=start + timedelta(hours=1))
    _complete(db, festival, booth, count=2, at=start - timedelta(minutes=10))
    _complete(db, festival, booth, count=6, at=start + timedelta(minutes=10))

    result = impact.build(db, c)

    assert result.data_status == impact.INSUFFICIENT_DATA
    assert result.in_progress is False


def test_before_가_0건이면_배수를_만들지_않는다(db: Session, festival: Festival) -> None:
    """0 을 분모로 두고 "무한 증가" 를 만들면 그 숫자가 화면에 나가고,
    아무도 그게 0 에서 시작했다는 걸 모른다."""
    booth = _booth(db, festival, "지역상점존")
    start = datetime.now(UTC) - timedelta(hours=2)
    c = _campaign(db, festival, booth, starts_at=start, ends_at=start + timedelta(hours=1))
    _complete(db, festival, booth, count=25, at=start + timedelta(minutes=10))

    result = impact.build(db, c)

    assert result.before.target_completions == 0
    assert result.completion_change_rate is None
    assert result.data_status == impact.SUFFICIENT


def test_전후_비율과_증감을_센다(db: Session, festival: Festival) -> None:
    booth = _booth(db, festival, "지역상점존")
    crowded = _booth(db, festival, "막국수 체험존")
    start = datetime.now(UTC) - timedelta(hours=2)
    c = _campaign(db, festival, booth, starts_at=start, ends_at=start + timedelta(hours=1))

    before_at = start - timedelta(minutes=10)
    after_at = start + timedelta(minutes=10)
    _complete(db, festival, booth, count=8, at=before_at)
    _complete(db, festival, crowded, count=42, at=before_at)
    _complete(db, festival, booth, count=24, at=after_at)
    _complete(db, festival, crowded, count=26, at=after_at)

    result = impact.build(db, c)

    assert result.before.target_completions == 8
    assert result.before.festival_completions == 50
    assert result.before.share == 0.16
    assert result.after.share == 0.48
    assert result.share_change_pp == 32.0
    assert result.completion_change_rate == 2.0
    # 몰려 있던 쪽이 실제로 내려갔는지 함께 본다 — 대상 부스만 올랐다면
    # 사람이 더 온 것이지 분산된 것이 아니다.
    assert result.top_booth_before is not None
    assert result.top_booth_before.booth_id == crowded.id
    assert result.top_booth_before.share_before == 0.84
    assert result.top_booth_before.share_after == 0.52


def test_몰린_부스가_없으면_비교_대상도_없다(db: Session, festival: Festival) -> None:
    """before 에서 40% 이상 몰린 부스가 없으면 편중이 없었다는 뜻이다."""
    booth = _booth(db, festival, "지역상점존")
    others = [_booth(db, festival, f"부스 {i}") for i in range(4)]
    start = datetime.now(UTC) - timedelta(hours=2)
    c = _campaign(db, festival, booth, starts_at=start, ends_at=start + timedelta(hours=1))

    _complete(db, festival, booth, count=6, at=start - timedelta(minutes=5))
    for b in others:
        _complete(db, festival, b, count=6, at=start - timedelta(minutes=5))
        _complete(db, festival, b, count=6, at=start + timedelta(minutes=5))
    _complete(db, festival, booth, count=10, at=start + timedelta(minutes=5))

    result = impact.build(db, c)

    assert result.top_booth_before is None


def test_아직_안_지난_구간은_집계_중이라_밝힌다(db: Session, festival: Festival) -> None:
    """지금 숫자로 결론을 내면 안 된다. after 30분이 아직 안 찼다."""
    booth = _booth(db, festival, "지역상점존")
    now = datetime.now(UTC)
    c = _campaign(
        db, festival, booth, starts_at=now - timedelta(minutes=5), ends_at=now + timedelta(hours=1)
    )
    _complete(db, festival, booth, count=25, at=now - timedelta(minutes=1))

    assert impact.build(db, c).in_progress is True


def test_다른_축제_참여는_분모에_들어가지_않는다(
    db: Session, org: Organization, festival: Festival
) -> None:
    """전체 완료 수가 분모라 한 건만 새도 비율이 통째로 틀어진다."""
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
    booth = _booth(db, festival, "지역상점존")
    theirs = _booth(db, other, "남의 부스")
    start = datetime.now(UTC) - timedelta(hours=2)
    c = _campaign(db, festival, booth, starts_at=start, ends_at=start + timedelta(hours=1))

    _complete(db, festival, booth, count=20, at=start + timedelta(minutes=5))
    _complete(db, other, theirs, count=500, at=start + timedelta(minutes=5))

    result = impact.build(db, c)

    assert result.after.festival_completions == 20
    assert result.after.share == 1.0


# ── API ─────────────────────────────────────────────────────────────────────


def test_만들고_고치고_끈다(db: Session, client: TestClient, festival: Festival) -> None:
    booth = _booth(db, festival, "지역상점존")
    now = datetime.now(UTC)

    created = client.post(
        f"/api/festivals/{festival.id}/reward-campaigns",
        json={
            "booth_id": booth.id,
            "title": "지역상점존 두 배",
            "message": "지금 가면 포인트를 두 배로 드립니다.",
            "bonus_points": 100,
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(minutes=30)).isoformat(),
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["is_live"] is True
    assert body["booth_name"] == "지역상점존"

    changed = client.put(
        f"/api/festivals/{festival.id}/reward-campaigns/{body['id']}",
        json={"bonus_points": 50},
    )
    assert changed.status_code == 200
    assert changed.json()["bonus_points"] == 50

    stopped = client.delete(
        f"/api/festivals/{festival.id}/reward-campaigns/{body['id']}"
    )
    assert stopped.status_code == 200
    assert stopped.json()["is_active"] is False
    assert stopped.json()["is_live"] is False


def test_active_only_는_서버가_거른다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    booth = _booth(db, festival, "지역상점존")
    now = datetime.now(UTC)
    live = _campaign(db, festival, booth)
    _campaign(
        db,
        festival,
        booth,
        title="끝난 캠페인",
        starts_at=now - timedelta(hours=3),
        ends_at=now - timedelta(hours=2),
    )

    every = client.get(f"/api/festivals/{festival.id}/reward-campaigns").json()
    only = client.get(
        f"/api/festivals/{festival.id}/reward-campaigns", params={"active_only": True}
    ).json()

    assert every["total"] == 2
    assert [c["id"] for c in only["items"]] == [live.id]


def test_효과_응답에_면책_문구가_붙는다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """빼면 이 표는 인과 효과처럼 읽힌다."""
    booth = _booth(db, festival, "지역상점존")
    start = datetime.now(UTC) - timedelta(hours=2)
    c = _campaign(db, festival, booth, starts_at=start, ends_at=start + timedelta(hours=1))
    _complete(db, festival, booth, count=25, at=start + timedelta(minutes=5))

    body = client.get(
        f"/api/festivals/{festival.id}/reward-campaigns/{c.id}/impact"
    ).json()

    assert body["disclaimer"] == "캠페인 전후 참여 변화이며 보상의 인과 효과가 아닙니다."
    assert body["before"]["from"] is not None
    assert body["data_status"] == "SUFFICIENT"


def test_남의_축제_캠페인은_보이지_않는다(
    db: Session, client: TestClient, org: Organization, festival: Festival
) -> None:
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
    theirs = _booth(db, other, "남의 부스")
    c = _campaign(db, other, theirs)

    r = client.get(f"/api/festivals/{festival.id}/reward-campaigns/{c.id}/impact")

    assert r.status_code == 404
