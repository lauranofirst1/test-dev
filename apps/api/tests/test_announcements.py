"""현장 공지 — 전달과 도달.

이 파일이 지키는 것은 셋입니다.

**1. 스태프 공지가 관객에게 새지 않는다.** "현금 정산 30분 뒤" 같은 내부 전달은
관객이 볼 것을 전제로 쓰이지 않습니다. 경계를 파라미터가 아니라 경로로 만든
이유이고, 그 경계를 여기서 직접 두드려 봅니다.

**2. 안내를 받으려고 등록할 필요가 없다.** 참여 코드를 아직 못 받은 사람도 우천
중단 공지는 봐야 합니다.

**3. 문구가 바뀌면 다시 봐야 한다.** "야외 부스 중단" 을 확인한 사람에게 "행사
전체 종료" 로 바뀐 같은 공지가 안 뜨면, 그 사람은 바뀐 내용을 영영 못 봅니다.
"""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    AnnouncementAck,
    Festival,
    FestivalStaff,
    Organization,
    Participant,
)
from festaflow.models.enums import (
    AnnouncementChannel,
    AnnouncementLevel,
    StaffRole,
)
from festaflow.services import announcements as svc

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
        expected_visitors=18000,
        total_budget=250000000,
    )
    db.add(f)
    db.flush()
    return f


@pytest.fixture
def participant(db: Session, festival: Festival) -> tuple[Participant, str]:
    # 실제 발급 함수를 쓴다. 손으로 만든 값을 넣으면 헤더에 못 싣는 문자열로
    # 테스트가 깨지고(HTTP 헤더는 ASCII 다), 진짜 형식을 확인하지도 못한다.
    secret = security.generate_participant_secret()
    p = Participant(
        festival_id=festival.id,
        code=f"FF-{next(_codes):08d}",
        secret_hash=security.hash_participant_secret(secret),
    )
    db.add(p)
    db.flush()
    return p, secret


@pytest.fixture
def staff(db: Session, festival: Festival) -> tuple[FestivalStaff, str]:
    s = FestivalStaff(
        festival_id=festival.id,
        role=StaffRole.BOOTH_MANAGER,
        display_name="부스 담당",
        access_code_hash=security.hash_access_code("ABC123"),
    )
    db.add(s)
    db.flush()
    token, _ = security.issue_staff_token(
        staff_id=s.id, festival_id=festival.id, role=s.role, booth_id=None
    )
    return s, token


def _post(db: Session, festival: Festival, **kw) -> object:
    defaults = dict(
        channel=AnnouncementChannel.AUDIENCE,
        level=AnnouncementLevel.NORMAL,
        title="3층 전시는 17시까지입니다",
        body="관람을 원하시면 16시 30분까지 입장해 주세요.",
    )
    return svc.create(db, festival.id, **{**defaults, **kw})


def _audience(client: TestClient, festival: Festival, secret: str | None = None) -> list[dict]:
    headers = {"X-Participant-Secret": secret} if secret else {}
    r = client.get(f"/api/festivals/{festival.id}/announcements/live", headers=headers)
    assert r.status_code == 200
    return r.json()["items"]


# ── 채널 경계 ───────────────────────────────────────────────────────────────


def test_스태프_공지는_관객에게_보이지_않는다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """"현금 정산 30분 뒤" 는 관객이 볼 것을 전제로 쓰이지 않는다."""
    _post(
        db,
        festival,
        channel=AnnouncementChannel.STAFF,
        title="현금 정산 30분 뒤",
        body="부스별 현금함을 본부로 가져와 주세요.",
    )
    _post(db, festival, title="관객용 안내")
    db.commit()

    titles = [a["title"] for a in _audience(client, festival)]

    assert titles == ["관객용 안내"]


def test_관객_경로는_채널을_파라미터로_받지_않는다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """파라미터로 두면 그 값은 요청자가 정하는 값이 되고, 경계는 문서에만 남는다."""
    _post(db, festival, channel=AnnouncementChannel.STAFF, title="내부 전달")
    db.commit()

    for query in ("?channel=staff", "?channel=both", "?for=staff"):
        r = client.get(f"/api/festivals/{festival.id}/announcements/live{query}")
        assert r.status_code == 200
        assert r.json()["items"] == [], query


def test_both_은_양쪽에_다_보인다(
    db: Session, client: TestClient, festival: Festival, staff
) -> None:
    _post(db, festival, channel=AnnouncementChannel.BOTH, title="우천으로 야외 중단")
    db.commit()
    _, token = staff

    audience = _audience(client, festival)
    staff_side = client.get(
        f"/api/festivals/{festival.id}/announcements/staff-live",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["items"]

    assert [a["title"] for a in audience] == ["우천으로 야외 중단"]
    assert [a["title"] for a in staff_side] == ["우천으로 야외 중단"]


def test_스태프_경로는_토큰이_필요하다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    _post(db, festival, channel=AnnouncementChannel.STAFF, title="내부 전달")
    db.commit()

    r = client.get(f"/api/festivals/{festival.id}/announcements/staff-live")

    assert r.status_code == 401


def test_남의_축제_스태프_토큰으로는_못_본다(
    db: Session, client: TestClient, org: Organization, festival: Festival, staff
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
    _post(db, other, channel=AnnouncementChannel.STAFF, title="남의 내부 전달")
    db.commit()
    _, token = staff

    r = client.get(
        f"/api/festivals/{other.id}/announcements/staff-live",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code in (403, 404)


# ── 등록하지 않아도 보인다 ──────────────────────────────────────────────────


def test_참여_코드가_없어도_공지는_보인다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """안내를 받으려면 먼저 등록하라고 요구하는 순간, 그 안내는 가장 필요한
    사람에게 닿지 않는다."""
    _post(db, festival, level=AnnouncementLevel.URGENT, title="우천으로 야외 부스 중단")
    db.commit()

    items = _audience(client, festival)

    assert [a["title"] for a in items] == ["우천으로 야외 부스 중단"]
    # 누구인지 모르니 확인 여부도 알 수 없다.
    assert items[0]["acked"] is False


def test_틀린_secret_은_공지를_막지_않는다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """여기서 401 을 내면 공지가 안 보인다. 인증이 목적이 아닌 화면에서
    가장 나쁜 실패다."""
    _post(db, festival, title="안내")
    db.commit()

    items = _audience(client, festival, secret=security.generate_participant_secret())

    assert len(items) == 1


# ── 기간 ────────────────────────────────────────────────────────────────────


def test_종료_시각이_없으면_끌_때까지_떠_있다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """언제 끝날지 모르는 상황이 대부분이다. 종료 시각을 필수로 하면 운영자는
    임의의 값을 넣고, 그 시각이 지나면 비가 그대로인데 공지만 사라진다."""
    a = _post(db, festival, ends_at=None, title="우천 중단")
    db.commit()

    assert len(_audience(client, festival)) == 1

    svc.stop(db, a)
    db.commit()

    assert _audience(client, festival) == []


def test_지난_공지는_사라진다(db: Session, client: TestClient, festival: Festival) -> None:
    now = datetime.now(UTC)
    _post(
        db,
        festival,
        title="끝난 공지",
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1),
    )
    _post(db, festival, title="아직인 공지", starts_at=now + timedelta(hours=1))
    _post(db, festival, title="지금 공지")
    db.commit()

    assert [a["title"] for a in _audience(client, festival)] == ["지금 공지"]


def test_기간이_거꾸로면_거부한다(db: Session, festival: Festival) -> None:
    now = datetime.now(UTC)

    with pytest.raises(Exception) as exc:
        _post(db, festival, starts_at=now, ends_at=now - timedelta(minutes=1))

    assert getattr(exc.value, "status_code", None) == 422


def test_긴급이_먼저_온다(db: Session, client: TestClient, festival: Festival) -> None:
    """화면이 다시 정렬하지 않아도 첫 건이 덮개 후보여야 한다."""
    _post(db, festival, title="일반 안내")
    _post(db, festival, level=AnnouncementLevel.URGENT, title="긴급 안내")
    db.commit()

    assert [a["title"] for a in _audience(client, festival)] == ["긴급 안내", "일반 안내"]


# ── 확인 ────────────────────────────────────────────────────────────────────


def test_확인하면_덮개가_다시_안_뜬다(
    db: Session, client: TestClient, festival: Festival, participant
) -> None:
    """폴링마다 다시 뜨면 화면을 쓸 수 없다."""
    a = _post(db, festival, level=AnnouncementLevel.URGENT, title="우천 중단")
    db.commit()
    p, secret = participant

    assert _audience(client, festival, secret)[0]["acked"] is False

    r = client.post(
        f"/api/festivals/{festival.id}/announcements/{a.id}/ack",
        headers={"X-Participant-Secret": secret},
    )

    assert r.status_code == 201
    items = _audience(client, festival, secret)
    # 확인해도 목록에는 남는다 — "아까 뭐라고 했지" 를 다시 볼 수 있어야 한다.
    assert len(items) == 1
    assert items[0]["acked"] is True


def test_두_번_확인해도_기록은_하나다(
    db: Session, client: TestClient, festival: Festival, participant
) -> None:
    """덮개를 연타해도 확인 인원이 부풀면 안 된다."""
    a = _post(db, festival, level=AnnouncementLevel.URGENT, title="우천 중단")
    db.commit()
    _, secret = participant
    url = f"/api/festivals/{festival.id}/announcements/{a.id}/ack"
    headers = {"X-Participant-Secret": secret}

    assert client.post(url, headers=headers).status_code == 201
    assert client.post(url, headers=headers).status_code == 201

    assert svc.ack_counts(db, [a.id]) == {a.id: 1}


def test_일반_공지는_확인을_기록하지_않는다(
    db: Session, client: TestClient, festival: Festival, participant
) -> None:
    """조용히 받아 주면 확인 수가 부풀어 긴급 공지의 도달률을 읽을 수 없게 된다."""
    a = _post(db, festival, level=AnnouncementLevel.NORMAL)
    db.commit()
    _, secret = participant

    r = client.post(
        f"/api/festivals/{festival.id}/announcements/{a.id}/ack",
        headers={"X-Participant-Secret": secret},
    )

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_URGENT"


def test_관객은_스태프_공지를_확인할_수_없다(
    db: Session, client: TestClient, festival: Festival, participant
) -> None:
    """id 를 찍어 보는 것만으로 존재 여부가 새면 안 된다."""
    a = _post(db, festival, channel=AnnouncementChannel.STAFF, level=AnnouncementLevel.URGENT)
    db.commit()
    _, secret = participant

    r = client.post(
        f"/api/festivals/{festival.id}/announcements/{a.id}/ack",
        headers={"X-Participant-Secret": secret},
    )

    assert r.status_code == 404


def test_문구를_고치면_확인_기록이_지워진다(
    db: Session, client: TestClient, festival: Festival, participant
) -> None:
    """"야외 부스 중단" 을 확인한 사람에게 "행사 전체 종료" 가 안 뜨면,
    그 사람은 바뀐 내용을 영영 못 본다."""
    a = _post(db, festival, level=AnnouncementLevel.URGENT, title="야외 부스 중단")
    db.commit()
    _, secret = participant
    client.post(
        f"/api/festivals/{festival.id}/announcements/{a.id}/ack",
        headers={"X-Participant-Secret": secret},
    )
    assert _audience(client, festival, secret)[0]["acked"] is True

    svc.update(db, a, title="행사 전체 종료")
    db.commit()

    assert _audience(client, festival, secret)[0]["acked"] is False
    assert db.query(AnnouncementAck).count() == 0


def test_기간만_고치면_확인_기록이_남는다(
    db: Session, client: TestClient, festival: Festival, participant
) -> None:
    """공지를 30분 연장했다고 모두에게 덮개를 다시 씌우면, 그다음부터 아무도
    덮개를 읽지 않는다."""
    a = _post(db, festival, level=AnnouncementLevel.URGENT, title="우천 중단")
    db.commit()
    _, secret = participant
    client.post(
        f"/api/festivals/{festival.id}/announcements/{a.id}/ack",
        headers={"X-Participant-Secret": secret},
    )

    svc.update(db, a, ends_at=datetime.now(UTC) + timedelta(hours=3))
    db.commit()

    assert _audience(client, festival, secret)[0]["acked"] is True


# ── 운영자 ──────────────────────────────────────────────────────────────────


def test_확인_인원을_보여준다(
    db: Session, client: TestClient, festival: Festival, participant
) -> None:
    """띄운 것과 전달된 것은 다르다. 우천 중단 공지에서는 그게 전부다."""
    a = _post(db, festival, level=AnnouncementLevel.URGENT, title="우천 중단")
    db.commit()
    _, secret = participant
    client.post(
        f"/api/festivals/{festival.id}/announcements/{a.id}/ack",
        headers={"X-Participant-Secret": secret},
    )

    body = client.get(f"/api/festivals/{festival.id}/announcements").json()

    assert body["items"][0]["ack_count"] == 1
    assert body["items"][0]["is_live"] is True


def test_내려도_목록에_남는다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """무엇을 언제 띄웠는지가 사후에 답해야 하는 질문이다 — 특히 안전 공지에서."""
    a = _post(db, festival, title="우천 중단")
    db.commit()

    stopped = client.delete(f"/api/festivals/{festival.id}/announcements/{a.id}")

    assert stopped.status_code == 200
    assert stopped.json()["is_active"] is False
    assert stopped.json()["is_live"] is False
    body = client.get(f"/api/festivals/{festival.id}/announcements").json()
    assert body["total"] == 1


def test_공지를_올리고_고친다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    created = client.post(
        f"/api/festivals/{festival.id}/announcements",
        json={
            "channel": "audience",
            "level": "urgent",
            "title": "우천으로 야외 부스 중단",
            "body": "실내 전시장으로 이동해 주세요.",
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["is_live"] is True
    assert body["ack_count"] == 0
    assert body["ends_at"] is None

    changed = client.put(
        f"/api/festivals/{festival.id}/announcements/{body['id']}",
        json={"level": "normal"},
    )
    assert changed.json()["level"] == "normal"
