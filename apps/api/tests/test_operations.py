"""운영 인사이트 — 편중 판정과 추천.

이 파일이 지키는 것은 셋입니다.

**1. 표본이 적으면 판정하지 않는다.** 3건 중 2건을 "67% 집중"이라 부르면 그
숫자가 근거처럼 보입니다. 최근 30분 전체 10건 미만이면 모든 부스가
INSUFFICIENT_DATA 이고 추천은 빈 배열입니다.

**2. 추천은 지시가 아니라 확인 요청이다.** QR 참여자는 방문객의 편향된
일부입니다. 문구가 "확인해 주세요"로 끝나는지 테스트가 직접 봅니다.

**3. 이 지표는 혼잡도가 아니다.** 면책 문구는 조건부가 아니라 **항상** 나갑니다.
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
    Organization,
    Participant,
    Participation,
    RecommendationFeedback,
    StampBoard,
)
from festaflow.models.enums import BoothLoadStatus, BoothType, ParticipationStatus
from festaflow.services import operations_insights as ins
from festaflow.services import operations_recommendations as rec


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
        name="제8회 Hallym SW Week",
        region="강원특별자치도 춘천시",
        venue="한림대학교 공학관",
        starts_on=date(2026, 11, 3),
        ends_on=date(2026, 11, 7),
        expected_visitors=1200,
        total_budget=11800000,
    )
    db.add(f)
    db.flush()
    return f


def _booth(db: Session, festival: Festival, name: str, *, active: bool = True) -> Booth:
    b = Booth(
        festival_id=festival.id,
        name=name,
        booth_type=BoothType.EXPERIENCE,
        is_active=active,
    )
    db.add(b)
    db.flush()
    return b


#: 참여 코드는 `^FF-[0-9A-Z]{8}$` 여야 한다. 테스트마다 세는 대신 한 카운터로
#: 뽑아 쓴다 — 부스·시각 조합으로 만들면 조합이 겹치는 순간 유니크 제약에서 터진다.
_codes = itertools.count(1)


def _complete(
    db: Session, festival: Festival, booth: Booth, *, count: int, minutes_ago: int = 5
) -> None:
    """`count` 명이 `minutes_ago` 분 전에 이 부스에서 완료했다고 기록한다.

    참여자를 매번 새로 만든다 — 고유 참여자 집계가 참여 건수와 같은지도 함께
    확인되기 때문이다.
    """
    at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    for _ in range(count):
        p = Participant(
            festival_id=festival.id,
            code=f"FF-{next(_codes):08d}",
            secret_hash="x",
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


# ── 판정 임계값 ──────────────────────────────────────────────────────────────


def test_표본이_적으면_판정하지_않는다(db: Session, festival: Festival) -> None:
    """9건이면 한 부스가 전부 가져가도 INSUFFICIENT_DATA 다."""
    a = _booth(db, festival, "막국수 체험존")
    _booth(db, festival, "지역상점존")
    _complete(db, festival, a, count=9)

    result = ins.build(db, festival.id)

    assert result.completions_last_30m == 9
    assert not result.enough_data
    assert all(b.status == BoothLoadStatus.INSUFFICIENT_DATA for b in result.booths)
    assert rec.build(result) == []


def test_10건부터_판정한다(db: Session, festival: Festival) -> None:
    """9건과 10건 사이가 경계다. 한 건 차이로 판정이 켜진다."""
    a = _booth(db, festival, "막국수 체험존")
    b = _booth(db, festival, "지역상점존")
    _complete(db, festival, a, count=5)
    _complete(db, festival, b, count=5, minutes_ago=6)

    result = ins.build(db, festival.id)

    assert result.enough_data
    assert {x.status for x in result.booths} == {BoothLoadStatus.HIGH}


@pytest.mark.parametrize(
    ("mine", "others", "expected"),
    [
        # 24% — 25% 미만이므로 여유
        (24, 76, BoothLoadStatus.LOW),
        # 25% — 경계값은 CAUTION 쪽에 포함된다
        (25, 75, BoothLoadStatus.CAUTION),
        (39, 61, BoothLoadStatus.CAUTION),
        # 40% — 경계값은 HIGH 쪽에 포함된다
        (40, 60, BoothLoadStatus.HIGH),
    ],
)
def test_비율_경계값(
    db: Session, festival: Festival, mine: int, others: int, expected: BoothLoadStatus
) -> None:
    target = _booth(db, festival, "막국수 체험존")
    # 나머지를 두 부스로 쪼갠다 — 한 부스에 몰면 그쪽이 판정에 걸려
    # 이 테스트가 보려는 경계가 가려진다.
    filler1 = _booth(db, festival, "지역상점존")
    filler2 = _booth(db, festival, "청년창업존")
    _complete(db, festival, target, count=mine)
    _complete(db, festival, filler1, count=others // 2, minutes_ago=6)
    _complete(db, festival, filler2, count=others - others // 2, minutes_ago=7)

    result = ins.build(db, festival.id)
    loads = {b.booth.id: b for b in result.booths}

    assert loads[target.id].status == expected


def test_판정_이유가_숫자를_담는다(db: Session, festival: Festival) -> None:
    """색만으로 상태를 알리면 색각 이상 사용자와 흑백 인쇄에서 정보가 사라진다."""
    a = _booth(db, festival, "막국수 체험존")
    b = _booth(db, festival, "지역상점존")
    _complete(db, festival, a, count=15)
    _complete(db, festival, b, count=5, minutes_ago=6)

    result = ins.build(db, festival.id)
    load = next(x for x in result.booths if x.booth.id == a.id)

    assert "20건" in load.status_reason
    assert "15건" in load.status_reason
    assert "75%" in load.status_reason


def test_최근_창_세_개를_따로_센다(db: Session, festival: Festival) -> None:
    """30분 하나만으로는 '방금 몰린 것'과 '계속 몰리는 것'이 구분되지 않는다."""
    a = _booth(db, festival, "막국수 체험존")
    _complete(db, festival, a, count=3, minutes_ago=2)
    _complete(db, festival, a, count=4, minutes_ago=20)
    _complete(db, festival, a, count=5, minutes_ago=50)

    load = ins.build(db, festival.id).booths[0]

    assert load.recent[10] == 3
    assert load.recent[30] == 7
    assert load.recent[60] == 12
    assert load.total_completions == 12
    assert load.unique_participants == 12


def test_60분을_넘긴_참여는_최근에서_빠진다(db: Session, festival: Festival) -> None:
    a = _booth(db, festival, "막국수 체험존")
    _complete(db, festival, a, count=30, minutes_ago=90)

    result = ins.build(db, festival.id)

    assert result.total_completions == 30
    assert result.completions_last_30m == 0
    assert result.booths[0].recent[60] == 0
    # 누적은 남지만 지금 판정할 근거는 없다.
    assert result.booths[0].status == BoothLoadStatus.INSUFFICIENT_DATA


def test_완료되지_않은_참여는_세지_않는다(db: Session, festival: Festival) -> None:
    """부스 앞에 서 있는 것과 미션을 끝낸 것은 다르다."""
    a = _booth(db, festival, "막국수 체험존")
    _complete(db, festival, a, count=12)
    p = Participant(festival_id=festival.id, code=f"FF-{next(_codes):08d}", secret_hash="x")
    db.add(p)
    db.flush()
    db.add(
        Participation(
            festival_id=festival.id,
            participant_id=p.id,
            booth_id=a.id,
            status=ParticipationStatus.ISSUED,
        )
    )
    db.flush()

    assert ins.build(db, festival.id).total_completions == 12


def test_다른_축제_참여는_섞이지_않는다(
    db: Session, org: Organization, festival: Festival
) -> None:
    other = Festival(
        organization_id=org.id,
        name="옆 축제",
        region="강원특별자치도 춘천시",
        venue="다른 곳",
        starts_on=date(2026, 11, 3),
        ends_on=date(2026, 11, 7),
        expected_visitors=100,
        total_budget=1000000,
    )
    db.add(other)
    db.flush()
    mine = _booth(db, festival, "막국수 체험존")
    theirs = _booth(db, other, "남의 부스")
    _complete(db, festival, mine, count=12)
    _complete(db, other, theirs, count=99)

    assert ins.build(db, festival.id).completions_last_30m == 12


# ── 추천 ────────────────────────────────────────────────────────────────────


def test_균형이면_추천하지_않는다(db: Session, festival: Festival) -> None:
    """할 말이 없을 때 카드를 만들면 다음부터 아무도 카드를 안 읽는다."""
    for i, name in enumerate(["A존", "B존", "C존", "D존"]):
        _complete(db, festival, _booth(db, festival, name), count=10, minutes_ago=i + 1)

    result = ins.build(db, festival.id)

    assert result.enough_data
    assert {b.status for b in result.booths} == {BoothLoadStatus.CAUTION}
    assert rec.build(result) == []


def test_편중되면_분산을_확인_요청한다(db: Session, festival: Festival) -> None:
    crowded = _booth(db, festival, "막국수 체험존")
    quiet = _booth(db, festival, "지역상점존")
    mid = _booth(db, festival, "청년창업존")
    _complete(db, festival, crowded, count=50)
    _complete(db, festival, quiet, count=8, minutes_ago=6)
    _complete(db, festival, mid, count=42, minutes_ago=7)

    cards = rec.build(ins.build(db, festival.id))

    assert len(cards) == 1
    card = cards[0]
    assert card.target_booth_id == quiet.id
    assert "막국수 체험존" in card.situation
    assert "지역상점존" in card.evidence
    # 지시가 아니라 확인 요청이다.
    assert "확인해 주세요" in card.action
    assert "검토할 수 있습니다" in card.action


def test_한산한_부스가_여럿이면_카드는_하나다(db: Session, festival: Festival) -> None:
    """같은 상황을 설명하는 카드가 다섯 장 뜨면 운영자는 다섯 개를 다 처리하지
    못하고, 처리 못 할 카드가 쌓이면 다음부터 카드를 읽지 않는다."""
    crowded = _booth(db, festival, "막국수 체험존")
    quiet = [_booth(db, festival, n) for n in ["지역상점존", "관광안내소", "부스 5"]]
    _complete(db, festival, crowded, count=50)
    for i, b in enumerate(quiet):
        _complete(db, festival, b, count=3, minutes_ago=i + 6)

    cards = [
        c
        for c in rec.build(ins.build(db, festival.id))
        if c.type == rec.RecommendationType.REDISTRIBUTE
    ]

    assert len(cards) == 1
    # 조용히 잘라내지 않는다 — 안 적힌 부스는 아무도 확인하러 가지 않는다.
    for b in quiet:
        assert b.name in cards[0].evidence
    # 확인하러 갈 곳은 가장 조용한 한 곳으로 찍어 준다.
    assert cards[0].target_booth_id in {b.id for b in quiet}


def test_부스_이름_뒤에_조사를_붙이지_않는다(db: Session, festival: Festival) -> None:
    """부스 이름은 운영자가 쓰는 자유 텍스트다. 나열 뒤에 조사를 붙이면
    "부스 5은" 같은 문장이 반드시 화면에 나간다."""
    crowded = _booth(db, festival, "막국수 체험존")
    quiet = _booth(db, festival, "부스 5")
    _complete(db, festival, crowded, count=50)
    _complete(db, festival, quiet, count=3, minutes_ago=6)

    card = rec.build(ins.build(db, festival.id))[0]

    assert "부스 5은" not in card.evidence
    assert card.evidence.endswith("부스 5(6%, 3건)")


def test_0건인_부스를_여유라고_부르지_않는다(db: Session, festival: Festival) -> None:
    """운영자는 "여유" 를 보고 "괜찮구나" 로 읽고 지나간다. 바로 위 추천 카드는
    같은 부스의 QR 을 확인해 달라고 말하고 있다 — 한 화면이 서로 다른 말을 하면
    둘 다 신뢰를 잃는다."""
    busy = _booth(db, festival, "막국수 체험존")
    silent = _booth(db, festival, "지역상점존")
    _complete(db, festival, busy, count=25)

    result = ins.build(db, festival.id)
    load = next(b for b in result.booths if b.booth.id == silent.id)

    # 계약이 정한 enum 은 그대로 LOW 다. 바뀌는 것은 사람이 읽는 라벨뿐이다.
    assert load.status == BoothLoadStatus.LOW
    assert rec.status_label(load, enough=result.enough_data) == "참여 없음"
    busy_load = next(b for b in result.booths if b.booth.id == busy.id)
    assert rec.status_label(busy_load, enough=result.enough_data) == "집중"


def test_비활성_부스는_추천_대상이_아니다(db: Session, festival: Festival) -> None:
    """오늘 안 여는 부스에 사람을 보내라고 하면 그 추천은 해롭다."""
    crowded = _booth(db, festival, "막국수 체험존")
    closed = _booth(db, festival, "지역상점존", active=False)
    _complete(db, festival, crowded, count=50)
    _complete(db, festival, closed, count=2, minutes_ago=6)

    cards = rec.build(ins.build(db, festival.id))

    assert cards == []


def test_비활성_부스는_집중_출발점도_아니다(db: Session, festival: Festival) -> None:
    """비활성인데 완료가 몰렸다면 그건 방금 닫은 부스다. 분산의 근거가 못 된다."""
    closed = _booth(db, festival, "막국수 체험존", active=False)
    quiet = _booth(db, festival, "지역상점존")
    _complete(db, festival, closed, count=50)
    _complete(db, festival, quiet, count=8, minutes_ago=6)

    cards = rec.build(ins.build(db, festival.id))

    assert [c for c in cards if c.type == rec.RecommendationType.REDISTRIBUTE] == []


def test_무참여는_전체_20건부터_말한다(db: Session, festival: Festival) -> None:
    """축제 자체가 조용하면 '이 부스만 0건'은 이상한 일이 아니다."""
    busy = _booth(db, festival, "막국수 체험존")
    silent = _booth(db, festival, "지역상점존")
    _complete(db, festival, busy, count=15)

    cards = rec.build(ins.build(db, festival.id))
    assert [c for c in cards if c.type == rec.RecommendationType.NO_ACTIVITY] == []

    _complete(db, festival, busy, count=5, minutes_ago=6)
    cards = rec.build(ins.build(db, festival.id))
    no_activity = [c for c in cards if c.type == rec.RecommendationType.NO_ACTIVITY]
    assert len(no_activity) == 1
    assert no_activity[0].target_booth_id == silent.id
    assert "QR 이 잘 보이는 자리에 있는지 확인해 주세요" in no_activity[0].action


def test_분산이_무참여보다_먼저_나온다(db: Session, festival: Festival) -> None:
    """HIGH → CAUTION 순. 지금 사람이 몰린 곳이 먼저다."""
    crowded = _booth(db, festival, "막국수 체험존")
    quiet = _booth(db, festival, "지역상점존")
    _booth(db, festival, "청년창업존")
    _complete(db, festival, crowded, count=40)
    _complete(db, festival, quiet, count=5, minutes_ago=6)

    cards = rec.build(ins.build(db, festival.id))
    kinds = [c.type for c in cards]

    assert kinds.index(rec.RecommendationType.REDISTRIBUTE) < kinds.index(
        rec.RecommendationType.NO_ACTIVITY
    )


def test_한_부스에_카드가_둘_붙지_않는다(db: Session, festival: Festival) -> None:
    """0건인 부스는 '한산한 부스'로도 잡힌다. 두 카드가 다른 말을 하면 현장에서
    어느 쪽을 믿을지 알 수 없다. 더 구체적인 무참여가 이긴다."""
    crowded = _booth(db, festival, "막국수 체험존")
    silent = _booth(db, festival, "지역상점존")
    _complete(db, festival, crowded, count=40)

    cards = [c for c in rec.build(ins.build(db, festival.id)) if c.target_booth_id == silent.id]

    assert [c.type for c in cards] == [rec.RecommendationType.NO_ACTIVITY]


# ── API ─────────────────────────────────────────────────────────────────────


def test_면책_문구는_항상_나간다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """조건부로 빼면 빠진 화면에서 혼잡도로 읽힌다."""
    r = client.get(f"/api/festivals/{festival.id}/operations/insights")

    assert r.status_code == 200
    body = r.json()
    assert "실제 인원수나 물리적 밀집도가 아닙니다" in body["disclaimer"]
    assert body["booths"] == []
    assert body["recommendations"] == []


def test_kpi_와_상태_라벨(db: Session, client: TestClient, festival: Festival) -> None:
    a = _booth(db, festival, "막국수 체험존")
    b = _booth(db, festival, "지역상점존")
    _complete(db, festival, a, count=15)
    _complete(db, festival, b, count=5, minutes_ago=6)

    body = client.get(f"/api/festivals/{festival.id}/operations/insights").json()

    assert body["kpi"] == {
        "total_participants": 20,
        "total_completions": 20,
        "completions_last_30m": 20,
        "high_concentration_booths": 1,
    }
    crowded = next(x for x in body["booths"] if x["booth_id"] == a.id)
    assert crowded["status"] == "HIGH"
    assert crowded["status_label"] == "집중"
    assert crowded["share_last_30m"] == 0.75
    assert crowded["last_30m"] == 15


def test_보드_완성불가_경고가_함께_나간다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """당일에 알면 늦다. 진단과 대시보드가 같은 경고를 본다."""
    db.add(StampBoard(festival_id=festival.id, rows=3, cols=3))
    _booth(db, festival, "막국수 체험존")
    db.flush()

    body = client.get(f"/api/festivals/{festival.id}/operations/insights").json()

    assert [w["code"] for w in body["warnings"]] == ["BOARD_UNCOMPLETABLE"]


def test_보드가_없어도_200(db: Session, client: TestClient, festival: Festival) -> None:
    """조각 보드를 안 쓰는 행사도 있다. 없으면 경고도 없다."""
    body = client.get(f"/api/festivals/{festival.id}/operations/insights").json()
    assert body["warnings"] == []


def test_변화가_없으면_304(db: Session, client: TestClient, festival: Festival) -> None:
    """10초 폴링의 대부분이 304 여야 축제 당일 집계 비용이 줄어든다."""
    a = _booth(db, festival, "막국수 체험존")
    _complete(db, festival, a, count=12)

    first = client.get(f"/api/festivals/{festival.id}/operations/insights")
    etag = first.headers["ETag"]
    assert etag

    again = client.get(
        f"/api/festivals/{festival.id}/operations/insights",
        headers={"If-None-Match": etag},
    )

    assert again.status_code == 304
    assert again.headers["ETag"] == etag


def test_참여가_늘면_etag_가_바뀐다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """`generated_at` 을 해시에 넣으면 매번 달라져 304 가 영원히 안 나온다.
    반대로 집계가 바뀌었는데 그대로면 화면이 멈춘 채 갱신되지 않는다."""
    a = _booth(db, festival, "막국수 체험존")
    _complete(db, festival, a, count=12)
    etag = client.get(f"/api/festivals/{festival.id}/operations/insights").headers["ETag"]

    _complete(db, festival, a, count=1, minutes_ago=1)
    r = client.get(
        f"/api/festivals/{festival.id}/operations/insights",
        headers={"If-None-Match": etag},
    )

    assert r.status_code == 200
    assert r.headers["ETag"] != etag


def test_추천_판정을_기록한다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """제품이 자기 추천의 정확도를 스스로 측정하게 만드는 입력이다."""
    booth = _booth(db, festival, "지역상점존")
    observed = datetime.now(UTC) - timedelta(minutes=3)

    r = client.post(
        f"/api/festivals/{festival.id}/recommendations/feedback",
        json={
            "rec_type": "REDISTRIBUTE",
            "booth_id": booth.id,
            "observed_at": observed.isoformat(),
            "verdict": False,
        },
    )

    assert r.status_code == 201
    assert r.json()["verdict"] is False
    saved = db.query(RecommendationFeedback).one()
    assert saved.booth_id == booth.id
    # 확인하러 갔다 온 시각이 아니라 추천이 떠 있던 시각을 남긴다.
    assert abs((saved.observed_at - observed).total_seconds()) < 1


def test_판정을_번복할_수_있다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """유니크 제약을 걸면 '아까 잘못 눌렀다'를 되돌릴 방법이 없어진다."""
    booth = _booth(db, festival, "지역상점존")
    body = {
        "rec_type": "NO_ACTIVITY",
        "booth_id": booth.id,
        "observed_at": datetime.now(UTC).isoformat(),
        "verdict": True,
    }
    assert client.post(
        f"/api/festivals/{festival.id}/recommendations/feedback", json=body
    ).status_code == 201
    assert client.post(
        f"/api/festivals/{festival.id}/recommendations/feedback", json={**body, "verdict": False}
    ).status_code == 201

    assert db.query(RecommendationFeedback).count() == 2


def test_남의_부스로는_판정을_남길_수_없다(
    db: Session, client: TestClient, org: Organization, festival: Festival
) -> None:
    """타 축제 부스 ID 가 들어오면 리포트 적중률이 조용히 오염된다."""
    other = Festival(
        organization_id=org.id,
        name="옆 축제",
        region="강원특별자치도 춘천시",
        venue="다른 곳",
        starts_on=date(2026, 11, 3),
        ends_on=date(2026, 11, 7),
        expected_visitors=100,
        total_budget=1000000,
    )
    db.add(other)
    db.flush()
    theirs = _booth(db, other, "남의 부스")

    r = client.post(
        f"/api/festivals/{festival.id}/recommendations/feedback",
        json={
            "rec_type": "REDISTRIBUTE",
            "booth_id": theirs.id,
            "observed_at": datetime.now(UTC).isoformat(),
            "verdict": True,
        },
    )

    assert r.status_code == 404


# ── 시간대 그래프 ───────────────────────────────────────────────────────────


def test_시간대_그래프는_빈_칸을_0으로_채운다(
    db: Session, festival: Festival
) -> None:
    """DB 는 완료가 있는 칸만 돌려준다. 그대로 선을 그으면 아무도 안 오던 30분이
    사라지고 양옆 점이 곧장 이어져, 없던 시간이 완만한 하강으로 보인다."""
    booth = _booth(db, festival, "A1")
    _complete(db, festival, booth, count=3, minutes_ago=5)
    _complete(db, festival, booth, count=2, minutes_ago=95)
    db.flush()

    points = ins.timeline(db, festival.id, hours=3)

    # 3시간 / 10분 = 18칸 + 지금 칸 하나.
    assert len(points) == 19
    assert all(p.completions >= 0 for p in points)
    filled = [p for p in points if p.completions > 0]
    assert len(filled) == 2, "완료가 두 시점에만 있으므로 0 이 아닌 칸도 둘이어야 한다"
    assert sum(p.completions for p in points) == 5
    # 칸은 10분 간격으로 빠짐없이 이어진다.
    gaps = {
        (points[i + 1].at - points[i].at).total_seconds() for i in range(len(points) - 1)
    }
    assert gaps == {600}


def test_시간대_그래프는_창_밖의_완료를_세지_않는다(
    db: Session, festival: Festival
) -> None:
    booth = _booth(db, festival, "A1")
    _complete(db, festival, booth, count=4, minutes_ago=10)
    _complete(db, festival, booth, count=7, minutes_ago=60 * 9)
    db.flush()

    points = ins.timeline(db, festival.id, hours=2)

    assert sum(p.completions for p in points) == 4


def test_시간대_그래프_창_길이는_상한이_있다(
    db: Session, festival: Festival
) -> None:
    """요청자가 정하는 값이라 막지 않으면 한 번의 호출로 임의 크기의 집계를
    돌릴 수 있다."""
    huge = ins.timeline(db, festival.id, hours=9999)
    capped = ins.timeline(db, festival.id, hours=ins.TIMELINE_MAX_HOURS)

    assert len(huge) == len(capped)


def test_시간대_엔드포인트가_peak_을_함께_낸다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """화면이 전체 점을 다시 훑어 최댓값을 찾게 두면, 화면마다 다르게 찾는다."""
    booth = _booth(db, festival, "A1")
    _complete(db, festival, booth, count=6, minutes_ago=5)
    db.commit()

    r = client.get(f"/api/festivals/{festival.id}/operations/timeline?hours=2")

    assert r.status_code == 200
    body = r.json()
    assert body["bucket_minutes"] == 10
    assert body["window_hours"] == 2
    assert body["peak"] == 6
    assert body["peak"] == max(p["completions"] for p in body["points"])
