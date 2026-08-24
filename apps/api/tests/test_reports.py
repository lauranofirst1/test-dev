"""사후 성과 리포트.

**이 리포트가 하지 않는 일이 하는 일만큼 중요합니다.** 그래서 이 파일의 절반은
"만들어 내지 않는다"를 확인합니다.

- 실측 방문객이 없으면 참여율을 만들지 않는다
- 측정하지 않는 지표에 달성률을 붙이지 않는다
- 미션 성공률을 만들지 않는다(시도자 분모를 모른다)
- 부스 집계는 스냅샷이라 미션을 옮겨도 과거가 안 움직인다
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
    KpiTarget,
    Mission,
    Organization,
    Participant,
    Participation,
    RecommendationFeedback,
    VisitorCount,
)
from festaflow.models.enums import (
    BoothType,
    ParticipationStatus,
    RecommendationType,
    VisitorSource,
)
from festaflow.services import reports as svc

_codes = itertools.count(1)

#: KST 기준으로 시각을 만든다. 리포트의 시간축이 KST 고정이라, UTC 로 만들면
#: 자정 근처 테스트가 하루 밀린다.
KST = svc.KST


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


def _booth(db: Session, festival: Festival, name: str) -> Booth:
    b = Booth(festival_id=festival.id, name=name, booth_type=BoothType.FOOD, is_active=True)
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


def _done(
    db: Session,
    festival: Festival,
    *,
    booth: Booth | None,
    mission: Mission | None = None,
    count: int = 1,
    at: datetime | None = None,
    participant: Participant | None = None,
) -> None:
    when = at or datetime(2026, 10, 10, 14, 30, tzinfo=KST)
    for _ in range(count):
        p = participant
        if p is None:
            p = Participant(
                festival_id=festival.id, code=f"FF-{next(_codes):08d}", secret_hash="x"
            )
            db.add(p)
            db.flush()
        db.add(
            Participation(
                festival_id=festival.id,
                participant_id=p.id,
                booth_id=booth.id if booth else None,
                mission_id=mission.id if mission else None,
                status=ParticipationStatus.COMPLETED,
                completed_at=when,
            )
        )
    db.flush()


# ── 요약 ────────────────────────────────────────────────────────────────────


def test_참여자당_평균_완료를_센다(db: Session, festival: Festival) -> None:
    booth = _booth(db, festival, "막국수 체험존")
    p = Participant(festival_id=festival.id, code=f"FF-{next(_codes):08d}", secret_hash="x")
    db.add(p)
    db.flush()
    # 한 사람이 세 번 완료했다.
    _done(db, festival, booth=booth, count=3, participant=p)
    _done(db, festival, booth=booth, count=1)

    r = svc.build(db, festival)

    assert r.summary.total_completions == 4
    assert r.summary.unique_participants == 2
    assert r.summary.avg_completions_per_participant == 2.0


def test_참여_발생_미션_비율을_센다(db: Session, festival: Festival) -> None:
    """"미션 성공률" 이 아니다. 시도자 분모를 모르므로 만들지 않는다 —
    여기 있는 것은 완료가 1건이라도 난 미션의 비율뿐이다."""
    booth = _booth(db, festival, "막국수 체험존")
    used = _mission(db, festival, booth, "막국수 만들기")
    _mission(db, festival, booth, "아무도 안 한 미션")
    _done(db, festival, booth=booth, mission=used, count=5)

    r = svc.build(db, festival)

    assert r.summary.missions_with_completion == 1
    assert r.summary.missions_total == 2
    assert r.summary.mission_ratio == 0.5


def test_참여가_0건이어도_리포트가_나온다(db: Session, festival: Festival) -> None:
    """빈 화면을 주면 운영자는 리포트가 고장 난 줄 안다."""
    r = svc.build(db, festival)

    assert r.summary.total_completions == 0
    assert r.summary.avg_completions_per_participant == 0.0
    assert [i.rule for i in r.improvements] == ["NO_DATA"]
    assert "참여 코드 안내물" in r.improvements[0].message


# ── 시간축 ──────────────────────────────────────────────────────────────────


def test_시간축은_KST_로_묶는다(db: Session, festival: Festival) -> None:
    """서버가 UTC 로 돌아도 "14시대에 몰렸다" 는 현장 사람의 시계로 읽혀야 한다."""
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=3, at=datetime(2026, 10, 10, 14, 10, tzinfo=KST))
    _done(db, festival, booth=booth, count=2, at=datetime(2026, 10, 10, 14, 50, tzinfo=KST))
    _done(db, festival, booth=booth, count=1, at=datetime(2026, 10, 10, 15, 5, tzinfo=KST))

    r = svc.build(db, festival)

    assert [(h.hour, n) for h, n in r.timeline] == [(14, 5), (15, 1)]
    assert r.timeline[0][0].utcoffset() == timedelta(hours=9)


def test_최다_시간대_개선안이_나온다(db: Session, festival: Festival) -> None:
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=9, at=datetime(2026, 10, 10, 14, 10, tzinfo=KST))
    _done(db, festival, booth=booth, count=2, at=datetime(2026, 10, 10, 16, 10, tzinfo=KST))

    peak = next(i for i in svc.build(db, festival).improvements if i.rule == "PEAK_HOUR")

    assert "14시대" in peak.message


# ── 부스 ────────────────────────────────────────────────────────────────────


def test_부스_집계는_스냅샷을_쓴다(db: Session, festival: Festival) -> None:
    """운영 중 미션을 다른 부스로 옮겨도 과거 집계가 따라 움직이면 안 된다.
    원문은 "현재 미션의 booth_id" 로 묶어서 재배치 한 번에 리포트가 뒤바뀌었다."""
    original = _booth(db, festival, "막국수 체험존")
    moved_to = _booth(db, festival, "지역상점존")
    mission = _mission(db, festival, original, "막국수 만들기")
    _done(db, festival, booth=original, mission=mission, count=5)

    # 미션을 다른 부스로 옮긴다.
    mission.booth_id = moved_to.id
    db.flush()

    r = svc.build(db, festival)
    by_name = {b.name: b.completions for b in r.booths}

    assert by_name["막국수 체험존"] == 5
    assert "지역상점존" not in by_name


def test_부스_스냅샷이_없는_참여는_따로_센다(db: Session, festival: Festival) -> None:
    """전체 완료에는 넣되 특정 부스에 임의로 배정하지 않는다."""
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=4)
    _done(db, festival, booth=None, count=2)

    r = svc.build(db, festival)

    assert r.summary.total_completions == 6
    assert r.unassigned_completions == 2
    assert sum(b.completions for b in r.booths) == 4


def test_동률은_같은_순위다(db: Session, festival: Festival) -> None:
    a = _booth(db, festival, "A존")
    b = _booth(db, festival, "B존")
    c = _booth(db, festival, "C존")
    _done(db, festival, booth=a, count=5)
    _done(db, festival, booth=b, count=5)
    _done(db, festival, booth=c, count=1)

    ranks = {x.name: x.rank for x in svc.build(db, festival).booths}

    assert ranks["A존"] == ranks["B존"] == 1
    # 1등이 둘이면 다음은 3등이다.
    assert ranks["C존"] == 3


def test_부스별_최다_시간대를_찾는다(db: Session, festival: Festival) -> None:
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=2, at=datetime(2026, 10, 10, 12, 5, tzinfo=KST))
    _done(db, festival, booth=booth, count=7, at=datetime(2026, 10, 10, 18, 5, tzinfo=KST))

    top = svc.build(db, festival).booths[0]

    assert top.peak_hour_kst.hour == 18
    assert top.peak_completions == 7


def test_편중_부스_개선안(db: Session, festival: Festival) -> None:
    a = _booth(db, festival, "막국수 체험존")
    b = _booth(db, festival, "지역상점존")
    _done(db, festival, booth=a, count=40)
    _done(db, festival, booth=b, count=10)

    rules = [i.rule for i in svc.build(db, festival).improvements]

    assert "CONCENTRATED_BOOTH" in rules
    assert "LOW_BOOTH" in rules


# ── 방문객 ──────────────────────────────────────────────────────────────────


def test_실측이_없으면_참여율을_만들지_않는다(db: Session, festival: Festival) -> None:
    """방문객 대비 참여율을 마음대로 만들면 그 숫자가 성과 보고서에 실린다."""
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=180)

    r = svc.build(db, festival)

    assert r.visitor_basis is None
    # 예상 방문객 대비는 "참여 규모" 로만 부른다.
    assert r.participation_scale == 0.01


def test_실측이_있으면_근거_있는_참여율을_만든다(
    db: Session, festival: Festival
) -> None:
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=300)
    db.add(
        VisitorCount(
            festival_id=festival.id,
            count_date=date(2026, 10, 10),
            visitors=6000,
            source=VisitorSource.MANUAL_COUNTER,
        )
    )
    db.flush()

    basis = svc.build(db, festival).visitor_basis

    assert basis is not None
    assert basis.visitors == 6000
    assert basis.participation_rate == 0.05
    assert basis.caveat is None


def test_우선순위가_높은_출처를_쓰고_나머지를_병기한다(
    db: Session, festival: Festival
) -> None:
    """입구 계수기 수치와 지자체 집계가 다른 건 정상이고, 그걸 숨기지 않는다."""
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=100)
    for source, n in [
        (VisitorSource.PARTNER, 9000),
        (VisitorSource.MANUAL_COUNTER, 5000),
        (VisitorSource.ESTIMATE, 12000),
    ]:
        db.add(
            VisitorCount(
                festival_id=festival.id,
                count_date=date(2026, 10, 10),
                visitors=n,
                source=source,
            )
        )
    db.flush()

    basis = svc.build(db, festival).visitor_basis

    assert basis.visitors == 5000
    assert basis.source == VisitorSource.MANUAL_COUNTER
    assert sorted(n for _, n in basis.others) == [9000, 12000]


def test_추산_출처에는_꼬리표가_붙는다(db: Session, festival: Festival) -> None:
    """센서 수치와 추산을 같은 굵기로 보여주면 둘을 구별할 방법이 없다."""
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=100)
    db.add(
        VisitorCount(
            festival_id=festival.id,
            count_date=date(2026, 10, 10),
            visitors=10000,
            source=VisitorSource.ESTIMATE,
        )
    )
    db.flush()

    assert svc.build(db, festival).visitor_basis.caveat == "주최측 추산 기준"


def test_여러_날은_날짜별로_하나씩_더한다(db: Session, festival: Festival) -> None:
    """단순 합계를 쓰면 같은 날 두 출처가 들어온 만큼 방문객이 두 배가 된다."""
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=100)
    for d, source, n in [
        (date(2026, 10, 10), VisitorSource.MANUAL_COUNTER, 5000),
        (date(2026, 10, 10), VisitorSource.PARTNER, 9000),
        (date(2026, 10, 11), VisitorSource.ESTIMATE, 3000),
    ]:
        db.add(
            VisitorCount(festival_id=festival.id, count_date=d, visitors=n, source=source)
        )
    db.flush()

    basis = svc.build(db, festival).visitor_basis

    assert basis.visitors == 8000
    # 하루는 계수기, 하루는 추산으로 채웠다면 합계 전체를 계수기 수치라 부를 수 없다.
    assert basis.source == VisitorSource.ESTIMATE
    assert basis.caveat == "주최측 추산 기준"


# ── 성과 목표 ───────────────────────────────────────────────────────────────


def test_목표가_없으면_블록을_생략한다(db: Session, festival: Festival) -> None:
    """빈 표를 그리면 "목표가 0" 처럼 읽힌다."""
    assert svc.build(db, festival).kpi == []


def test_측정_가능한_지표만_달성률을_만든다(db: Session, festival: Festival) -> None:
    """측정하지 않은 값에 달성률을 붙이면 리포트 전체의 신뢰가 무너진다."""
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=412)
    db.add_all(
        [
            KpiTarget(
                festival_id=festival.id,
                metric_key="qr_participants",
                label="목표 QR 참여자",
                target_value=500,
                unit="명",
                is_measurable=True,
            ),
            KpiTarget(
                festival_id=festival.id,
                metric_key="expected_visitors",
                label="목표 방문객",
                target_value=18000,
                unit="명",
                is_measurable=False,
            ),
        ]
    )
    db.flush()

    rows = {k.metric_key: k for k in svc.build(db, festival).kpi}

    assert rows["qr_participants"].actual == 412
    assert rows["qr_participants"].achievement == 0.824
    # 방문객은 실측이 없으므로 참고값이다.
    assert rows["expected_visitors"].measurable is False
    assert rows["expected_visitors"].actual is None
    assert rows["expected_visitors"].achievement is None
    assert "측정하지 않습니다" in rows["expected_visitors"].note


def test_실측이_들어오면_목표_방문객도_달성률을_갖는다(
    db: Session, festival: Festival
) -> None:
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=100)
    db.add(
        KpiTarget(
            festival_id=festival.id,
            metric_key="expected_visitors",
            label="목표 방문객",
            target_value=18000,
            unit="명",
            is_measurable=False,
        )
    )
    db.add(
        VisitorCount(
            festival_id=festival.id,
            count_date=date(2026, 10, 10),
            visitors=9000,
            source=VisitorSource.BEACON,
        )
    )
    db.flush()

    row = next(k for k in svc.build(db, festival).kpi if k.metric_key == "expected_visitors")

    assert row.measurable is True
    assert row.actual == 9000
    assert row.achievement == 0.5
    assert "출입구 센서" in row.note


# ── 추천 적중률 ─────────────────────────────────────────────────────────────


def test_추천_적중률을_집계한다(db: Session, festival: Festival) -> None:
    """제품이 자기 추천의 정확도를 스스로 보고하는 항목이다."""
    now = datetime.now(UTC)
    for verdict in [True, True, True, False]:
        db.add(
            RecommendationFeedback(
                festival_id=festival.id,
                rec_type=RecommendationType.REDISTRIBUTE,
                observed_at=now,
                verdict=verdict,
            )
        )
    db.flush()

    assert svc.build(db, festival).recommendation_hits == (3, 4)


def test_판정_기록이_없으면_적중률도_없다(db: Session, festival: Festival) -> None:
    assert svc.build(db, festival).recommendation_hits is None


# ── API ─────────────────────────────────────────────────────────────────────


def test_리포트_응답에_제한_문구가_붙는다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """빼면 이 숫자는 방문률로 읽힌다."""
    booth = _booth(db, festival, "막국수 체험존")
    _done(db, festival, booth=booth, count=180)

    body = client.get(f"/api/festivals/{festival.id}/report").json()

    assert body["plan_vs_actual"]["participation_scale"] == 0.01
    assert "실제 축제 방문률이나" in body["plan_vs_actual"]["disclaimer"]
    assert body["visitor_basis"] is None
    assert body["kpi"] == []


def test_기본_지표는_서버가_라벨을_정한다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """라벨이 제각각이면 축제 간 비교가 안 되고, 측정 가능 여부는 애초에
    운영자가 정할 값이 아니다."""
    r = client.put(
        f"/api/festivals/{festival.id}/kpi-targets",
        json={"metric_key": "expected_visitors", "label": "내맘대로", "target_value": 18000},
    )

    assert r.status_code == 200
    assert r.json()["label"] == "목표 방문객"
    assert r.json()["is_measurable"] is False


def test_같은_지표를_다시_보내면_덮어쓴다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """POST 로 두면 목표를 고치려던 운영자가 409 를 보고, 리포트에는 같은 줄이
    두 개 뜬다."""
    body = {"metric_key": "qr_participants", "target_value": 500}
    first = client.put(f"/api/festivals/{festival.id}/kpi-targets", json=body)
    second = client.put(
        f"/api/festivals/{festival.id}/kpi-targets", json={**body, "target_value": 800}
    )

    assert first.json()["id"] == second.json()["id"]
    assert second.json()["target_value"] == 800
    listed = client.get(f"/api/festivals/{festival.id}/kpi-targets").json()
    assert len(listed["items"]) == 1


def test_모르는_지표_키는_거부한다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    r = client.put(
        f"/api/festivals/{festival.id}/kpi-targets",
        json={"metric_key": "아무거나", "target_value": 10},
    )

    assert r.status_code == 422
    # ApiError 는 FastAPI 가 `detail` 로 한 겹 감싼다.
    assert "custom:" in r.json()["error"]["message"]


def test_사용자_정의_지표는_달성률을_만들지_않는다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """FestaFlow 가 집계할 방법이 없는 값이다."""
    r = client.put(
        f"/api/festivals/{festival.id}/kpi-targets",
        json={"metric_key": "custom:재방문 의향", "target_value": 80, "unit": "%"},
    )

    assert r.status_code == 200
    assert r.json()["is_measurable"] is False
    assert r.json()["label"] == "재방문 의향"

    row = client.get(f"/api/festivals/{festival.id}/report").json()["kpi"][0]
    assert row["achievement"] is None


def test_아직_안_세운_기본_지표를_알려준다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """화면이 지표 목록을 하드코딩하면 기본값이 늘어날 때 조용히 어긋난다."""
    client.put(
        f"/api/festivals/{festival.id}/kpi-targets",
        json={"metric_key": "qr_participants", "target_value": 500},
    )

    body = client.get(f"/api/festivals/{festival.id}/kpi-targets").json()

    keys = {a["metric_key"] for a in body["available"]}
    assert "qr_participants" not in keys
    assert "total_completions" in keys


def test_방문객_기록을_넣고_지운다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    created = client.post(
        f"/api/festivals/{festival.id}/visitor-counts",
        json={
            "count_date": "2026-10-10",
            "visitors": 6200,
            "source": "manual_counter",
            "note": "정문+후문 합산",
        },
    )
    assert created.status_code == 201
    assert created.json()["source_label"] == "입구 계수기"

    listed = client.get(f"/api/festivals/{festival.id}/visitor-counts").json()
    assert listed["total_visitors"] == 6200

    gone = client.delete(
        f"/api/festivals/{festival.id}/visitor-counts/{created.json()['id']}"
    )
    assert gone.status_code == 204
    assert client.get(f"/api/festivals/{festival.id}/visitor-counts").json()["items"] == []


def test_같은_날짜_같은_출처는_덮어쓴다(
    db: Session, client: TestClient, festival: Festival
) -> None:
    """오타를 고치려는 재입력이 유니크 제약에 걸려 500 이 나면 안 된다."""
    body = {"count_date": "2026-10-10", "visitors": 6200, "source": "manual_counter"}
    first = client.post(f"/api/festivals/{festival.id}/visitor-counts", json=body)
    second = client.post(
        f"/api/festivals/{festival.id}/visitor-counts", json={**body, "visitors": 6500}
    )

    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    listed = client.get(f"/api/festivals/{festival.id}/visitor-counts").json()
    assert listed["total_visitors"] == 6500


def test_남의_축제_리포트는_보이지_않는다(
    db: Session, client: TestClient, org: Organization, festival: Festival
) -> None:
    other_org = Organization(name="다른 재단")
    db.add(other_org)
    db.flush()
    theirs = Festival(
        organization_id=other_org.id,
        name="남의 축제",
        region="서울특별시",
        venue="어딘가",
        starts_on=date(2026, 10, 8),
        ends_on=date(2026, 10, 12),
        expected_visitors=100,
        total_budget=1000000,
    )
    db.add(theirs)
    db.flush()

    # 폴백 기관은 가장 낮은 id 라 festival 쪽 기관이 잡힌다.
    r = client.get(f"/api/festivals/{theirs.id}/report")

    assert r.status_code == 404



# ── 설문 만족도 ─────────────────────────────────────────────────────────────


def _survey_mission(db: Session, festival: Festival, booth: Booth, questions: list) -> Mission:
    from festaflow.models.enums import ExperienceType

    m = Mission(
        festival_id=festival.id,
        booth_id=booth.id,
        title="설문",
        points=50,
        is_active=True,
        experience_type=ExperienceType.SURVEY,
        experience_config={"questions": questions},
    )
    db.add(m)
    db.flush()
    return m


def _answer(db: Session, festival: Festival, booth: Booth, mission: Mission, answers: list) -> None:
    p = Participant(festival_id=festival.id, code=f"FF-{next(_codes):08d}", secret_hash="x")
    db.add(p)
    db.flush()
    db.add(
        Participation(
            festival_id=festival.id,
            participant_id=p.id,
            booth_id=booth.id,
            mission_id=mission.id,
            status=ParticipationStatus.COMPLETED,
            completed_at=datetime(2026, 10, 10, 14, 0, tzinfo=KST),
            response={"answers": answers},
        )
    )
    db.flush()


def test_설문이_없으면_만족도를_만들지_않는다(db: Session, festival: Festival) -> None:
    assert svc.satisfaction_average(db, festival.id) is None


def test_평점_문항을_평균낸다(db: Session, festival: Festival) -> None:
    booth = _booth(db, festival, "막국수 체험존")
    m = _survey_mission(db, festival, booth, [{"type": "rating", "text": "만족도", "scale": 5}])
    for value in (5, 4, 3):
        _answer(db, festival, booth, m, [value])

    # 5점 척도라 그대로 평균이 나온다.
    assert svc.satisfaction_average(db, festival.id) == 4.0


def test_척도가_다른_문항을_그대로_섞지_않는다(db: Session, festival: Festival) -> None:
    """5점 만점과 7점 만점을 함께 평균 내면 7점 문항이 저절로 높은 값이 되어
    결과가 그쪽으로 끌려간다."""
    booth = _booth(db, festival, "막국수 체험존")
    five = _survey_mission(db, festival, booth, [{"type": "rating", "text": "A", "scale": 5}])
    seven = _survey_mission(db, festival, booth, [{"type": "rating", "text": "B", "scale": 7}])
    # 둘 다 "최고점" 이다. 정규화하면 평균도 최고점이어야 한다.
    _answer(db, festival, booth, five, [5])
    _answer(db, festival, booth, seven, [7])

    assert svc.satisfaction_average(db, festival.id) == 5.0

    # 둘 다 최저점이면 평균도 최저점이다.
    db.query(Participation).delete()
    db.flush()
    _answer(db, festival, booth, five, [1])
    _answer(db, festival, booth, seven, [1])
    assert svc.satisfaction_average(db, festival.id) == 1.0


def test_선택_문항은_평균에_넣지_않는다(db: Session, festival: Festival) -> None:
    """"SNS/현수막/지인" 은 순서가 없는 값이라 평균이 아무 뜻도 없다."""
    booth = _booth(db, festival, "막국수 체험존")
    m = _survey_mission(
        db,
        festival,
        booth,
        [
            {"type": "rating", "text": "만족도", "scale": 5},
            {"type": "choice", "text": "경로", "choices": ["SNS", "현수막", "지인"]},
        ],
    )
    # 선택지가 2(지인)여도 평점 5만 반영돼야 한다.
    _answer(db, festival, booth, m, [5, 2])

    assert svc.satisfaction_average(db, festival.id) == 5.0


def test_응답이_없으면_만족도_달성률을_만들지_않는다(
    db: Session, festival: Festival
) -> None:
    """0 으로 치면 "만족도 0점" 이 되어 설문을 안 돌린 축제가 최악으로 보인다."""
    db.add(
        KpiTarget(
            festival_id=festival.id,
            metric_key="satisfaction",
            label="목표 만족도",
            target_value=4.5,
            unit="점",
            is_measurable=True,
        )
    )
    db.flush()

    row = next(k for k in svc.build(db, festival).kpi if k.metric_key == "satisfaction")

    assert row.measurable is False
    assert row.achievement is None
    assert "응답이 없어" in row.note
