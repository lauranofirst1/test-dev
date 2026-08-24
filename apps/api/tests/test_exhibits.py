"""전시 심사와 관객 투표.

이 파일이 지키는 것은 셋입니다.

**1. 1인 1표.** 작년 행사의 스티커 부정이 디지털에서 재현되지 않아야 합니다.
익명 축제에서는 코드를 새로 받으면 그만이므로, 그 경우를 조용히 통과시키지 않고
거절합니다 — 막히는 줄 알고 켜 두면 그 오해 위에 시상이 세워집니다.

**2. 투표 중에 순위가 보이지 않는다.** 보이면 표가 순위를 따라가고, 그건 더 이상
관객 투표가 아닙니다.

**3. 최종 점수에는 근거가 남는다.** 이의가 들어왔을 때 "심사 70 · 관객 30 이고
심사는 항목별로 이렇게 나왔다"를 보여줄 수 없으면 그 점수는 선언입니다.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    AudienceVote,
    Exhibit,
    Festival,
    FestivalStaff,
    Organization,
    StampBoard,
)
from festaflow.models.enums import IdentityMode, StaffRole


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


def _festival(db: Session, org: Organization, mode=IdentityMode.STUDENT_ID) -> Festival:
    f = Festival(
        organization_id=org.id,
        name="제8회 Hallym SW Week",
        region="강원특별자치도 춘천시",
        venue="한림대학교 공학관",
        starts_on=date(2026, 11, 3),
        ends_on=date(2026, 11, 7),
        expected_visitors=1200,
        total_budget=11800000,
        identity_mode=mode,
        voting_open=True,
        audience_votes_per_participant=3,
        judge_weight_percent=70,
    )
    db.add(f)
    db.flush()
    db.add(StampBoard(festival_id=f.id, rows=2, cols=2))
    db.flush()
    return f


@pytest.fixture
def campus(db: Session, org: Organization) -> Festival:
    return _festival(db, org)


def _err(r) -> str:
    return r.json()["error"]["code"]


def _join(client, festival, student_no):
    r = client.post(
        f"/api/festivals/{festival.id}/participants", json={"student_no": student_no}
    )
    assert r.status_code == 201, r.text
    return {"X-Participant-Secret": r.json()["secret"]}


def _exhibit(client, festival, title="키링 제작기", tags=None):
    r = client.post(
        f"/api/festivals/{festival.id}/exhibits",
        json={"title": title, "team_name": "3팀", "tags": tags or ["하드웨어"]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _criterion(client, festival, label, max_score=5, weight=1):
    r = client.post(
        f"/api/festivals/{festival.id}/criteria",
        json={"label": label, "max_score": max_score, "weight": weight},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _judge(db: Session, festival: Festival, name="심사위원", role=StaffRole.JUDGE):
    s = FestivalStaff(
        festival_id=festival.id,
        display_name=name,
        role=role,
        access_code_hash=security.hash_access_code("123456"),
    )
    db.add(s)
    db.flush()
    return s


def _as(staff: FestivalStaff) -> dict:
    token, _ = security.issue_staff_token(
        staff_id=staff.id,
        festival_id=staff.festival_id,
        role=staff.role.value,
        booth_id=staff.booth_id,
    )
    return {"Authorization": f"Bearer {token}"}


# ── 1인 1표 ─────────────────────────────────────────────────────────────────


def test_one_vote_per_exhibit_per_person(client, campus, db):
    e = _exhibit(client, campus)
    db.commit()
    headers = _join(client, campus, "20251234")

    first = client.post(f"/api/festivals/{campus.id}/exhibits/{e['id']}/vote", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["votes_used"] == 1

    # 같은 작품에 또 눌러도 표가 늘지 않는다. 오류로 만들지도 않는다.
    again = client.post(f"/api/festivals/{campus.id}/exhibits/{e['id']}/vote", headers=headers)
    assert again.status_code == 200
    assert again.json()["votes_used"] == 1
    assert db.query(AudienceVote).filter(AudienceVote.exhibit_id == e["id"]).count() == 1


def test_vote_limit_is_enforced(client, campus, db):
    exhibits = [_exhibit(client, campus, f"작품 {i}") for i in range(4)]
    db.commit()
    headers = _join(client, campus, "20251234")

    for e in exhibits[:3]:
        assert (
            client.post(f"/api/festivals/{campus.id}/exhibits/{e['id']}/vote", headers=headers)
        ).status_code == 200

    over = client.post(
        f"/api/festivals/{campus.id}/exhibits/{exhibits[3]['id']}/vote", headers=headers
    )
    assert over.status_code == 409
    assert _err(over) == "VOTE_LIMIT_REACHED"


def test_unvoting_frees_a_vote(client, campus, db):
    """표가 한정돼 있으니 옮길 수 있어야 한다."""
    exhibits = [_exhibit(client, campus, f"작품 {i}") for i in range(4)]
    db.commit()
    headers = _join(client, campus, "20251234")

    for e in exhibits[:3]:
        client.post(f"/api/festivals/{campus.id}/exhibits/{e['id']}/vote", headers=headers)

    dropped = client.delete(
        f"/api/festivals/{campus.id}/exhibits/{exhibits[0]['id']}/vote", headers=headers
    )
    assert dropped.status_code == 200
    assert dropped.json()["votes_used"] == 2

    moved = client.post(
        f"/api/festivals/{campus.id}/exhibits/{exhibits[3]['id']}/vote", headers=headers
    )
    assert moved.status_code == 200


def test_anonymous_festival_cannot_open_voting(client, db, org):
    """**여기가 이 기능의 존재 이유다.**

    익명 축제에서는 참여 코드를 새로 받으면 표가 초기화된다. 조용히 통과시키면
    "1인 1표가 지켜진다"는 오해 위에 시상이 세워진다.
    """
    festival = _festival(db, org, IdentityMode.ANONYMOUS)
    e = _exhibit(client, festival)
    db.commit()

    issued = client.post(f"/api/festivals/{festival.id}/participants", json={}).json()
    headers = {"X-Participant-Secret": issued["secret"]}

    r = client.post(f"/api/festivals/{festival.id}/exhibits/{e['id']}/vote", headers=headers)
    assert r.status_code == 409
    assert _err(r) == "VOTING_REQUIRES_IDENTITY"

    status = client.get(f"/api/festivals/{festival.id}/exhibition", headers=headers).json()
    assert status["can_vote"] is False
    assert "익명" in status["reason"]


def test_new_code_for_the_same_student_does_not_reset_votes(client, campus, db):
    """스티커 부정의 디지털 판. 학번이 같으면 참여자가 같아 표도 그대로다."""
    exhibits = [_exhibit(client, campus, f"작품 {i}") for i in range(4)]
    db.commit()
    headers = _join(client, campus, "20251234")
    for e in exhibits[:3]:
        client.post(f"/api/festivals/{campus.id}/exhibits/{e['id']}/vote", headers=headers)

    # 새로고침해서 참여를 다시 시작한다 — 옛날 스티커라면 새 스티커를 받는 셈.
    fresh = _join(client, campus, "20251234")
    status = client.get(f"/api/festivals/{campus.id}/exhibition", headers=fresh).json()
    assert status["votes_used"] == 3

    blocked = client.post(
        f"/api/festivals/{campus.id}/exhibits/{exhibits[3]['id']}/vote", headers=fresh
    )
    assert blocked.status_code == 409
    assert _err(blocked) == "VOTE_LIMIT_REACHED"


def test_voting_closed_refuses(client, campus, db):
    e = _exhibit(client, campus)
    campus.voting_open = False
    db.commit()
    headers = _join(client, campus, "20251234")

    r = client.post(f"/api/festivals/{campus.id}/exhibits/{e['id']}/vote", headers=headers)
    assert r.status_code == 409
    assert _err(r) == "VOTING_CLOSED"


# ── 순위를 감춘다 ───────────────────────────────────────────────────────────


def test_audience_never_sees_vote_counts(client, campus, db):
    """투표 중에 순위가 보이면 표가 순위를 따라간다."""
    a = _exhibit(client, campus, "인기 작품")
    b = _exhibit(client, campus, "무명 작품")
    db.commit()

    voter = _join(client, campus, "20250001")
    client.post(f"/api/festivals/{campus.id}/exhibits/{a['id']}/vote", headers=voter)

    other = _join(client, campus, "20250002")
    body = client.get(f"/api/festivals/{campus.id}/exhibition", headers=other)
    assert body.status_code == 200

    # `votes_used` 는 **자기가 쓴 표 수**라 보여도 된다. 남의 정보가 아니다.
    # 새면 안 되는 것은 작품별 득표수와 순위다.
    payload = body.json()
    assert payload["votes_used"] == 0
    for item in payload["exhibits"]:
        assert "votes" not in item
        assert "vote_count" not in item
        assert "final_score" not in item
        assert "audience_score" not in item
    assert "items" not in payload  # 집계 타입이 섞여 나오지 않는다
    # 내가 준 표는 보인다 — 그건 남의 정보가 아니다.
    mine = client.get(f"/api/festivals/{campus.id}/exhibition", headers=voter).json()
    assert [x["voted"] for x in mine["exhibits"] if x["id"] == a["id"]] == [True]
    assert b["id"] not in [x["id"] for x in mine["exhibits"] if x["voted"]]


# ── 심사위원 ────────────────────────────────────────────────────────────────


def test_judge_scores_are_recorded_and_overwritten_not_duplicated(client, campus, db):
    e = _exhibit(client, campus)
    c1 = _criterion(client, campus, "창의성")
    c2 = _criterion(client, campus, "완성도")
    judge = _judge(db, campus)
    db.commit()

    first = client.put(
        f"/api/festivals/{campus.id}/exhibits/{e['id']}/scores",
        json={"scores": [{"criterion_id": c1["id"], "score": 4}, {"criterion_id": c2["id"], "score": 5}]},
        headers=_as(judge),
    )
    assert first.status_code == 200, first.text
    assert first.json()["is_complete"] is True

    # 고치는 것은 새 점수가 아니라 같은 행의 갱신이다.
    again = client.put(
        f"/api/festivals/{campus.id}/exhibits/{e['id']}/scores",
        json={"scores": [{"criterion_id": c1["id"], "score": 2}]},
        headers=_as(judge),
    )
    assert again.status_code == 200
    scores = {s["criterion_id"]: s["score"] for s in again.json()["my_scores"]}
    assert scores[c1["id"]] == 2
    assert scores[c2["id"]] == 5


def test_judge_sheet_hides_other_judges_scores(client, campus, db):
    """남의 점수가 보이면 거기에 끌려간다. 합의는 회의에서 하는 것이다."""
    e = _exhibit(client, campus)
    c = _criterion(client, campus, "창의성")
    a = _judge(db, campus, "심사위원 A")
    b = _judge(db, campus, "심사위원 B")
    db.commit()

    client.put(
        f"/api/festivals/{campus.id}/exhibits/{e['id']}/scores",
        json={"scores": [{"criterion_id": c["id"], "score": 5}]},
        headers=_as(a),
    )

    sheet = client.get(f"/api/festivals/{campus.id}/judging", headers=_as(b)).json()
    assert sheet["sheets"][0]["my_scores"] == []
    assert sheet["scored_exhibits"] == 0


def test_score_above_the_maximum_is_refused(client, campus, db):
    e = _exhibit(client, campus)
    c = _criterion(client, campus, "창의성", max_score=5)
    judge = _judge(db, campus)
    db.commit()

    r = client.put(
        f"/api/festivals/{campus.id}/exhibits/{e['id']}/scores",
        json={"scores": [{"criterion_id": c["id"], "score": 9}]},
        headers=_as(judge),
    )
    assert r.status_code == 422
    assert _err(r) == "SCORE_OUT_OF_RANGE"


def test_judging_requires_a_staff_token(client, campus, db):
    """누가 매겼는지가 기록의 일부다. 익명 심사는 심사가 아니다."""
    e = _exhibit(client, campus)
    c = _criterion(client, campus, "창의성")
    db.commit()

    r = client.put(
        f"/api/festivals/{campus.id}/exhibits/{e['id']}/scores",
        json={"scores": [{"criterion_id": c["id"], "score": 4}]},
    )
    assert r.status_code == 401
    assert _err(r) == "JUDGE_AUTH_REQUIRED"


def test_booth_manager_cannot_judge(client, campus, db):
    e = _exhibit(client, campus)
    c = _criterion(client, campus, "창의성")
    manager = _judge(db, campus, "부스 관리자", role=StaffRole.BOOTH_MANAGER)
    db.commit()

    r = client.put(
        f"/api/festivals/{campus.id}/exhibits/{e['id']}/scores",
        json={"scores": [{"criterion_id": c["id"], "score": 4}]},
        headers=_as(manager),
    )
    assert r.status_code == 403


# ── 집계 ────────────────────────────────────────────────────────────────────


def test_final_score_carries_its_own_evidence(client, campus, db):
    """최종 점수만 내려주면 이의에 답할 수 없다."""
    e = _exhibit(client, campus)
    c1 = _criterion(client, campus, "창의성", max_score=5, weight=2)
    c2 = _criterion(client, campus, "완성도", max_score=5, weight=1)
    judge = _judge(db, campus)
    db.commit()

    client.put(
        f"/api/festivals/{campus.id}/exhibits/{e['id']}/scores",
        json={
            "scores": [
                {"criterion_id": c1["id"], "score": 5},
                {"criterion_id": c2["id"], "score": 2},
            ]
        },
        headers=_as(judge),
    )

    body = client.get(f"/api/festivals/{campus.id}/exhibition-results").json()
    assert body["judge_weight_percent"] == 70
    assert body["audience_weight_percent"] == 30

    row = body["items"][0]
    # (5/5×2 + 2/5×1) / 3 × 100 = 80.0
    assert row["judge_score"] == 80.0
    assert row["judge_count"] == 1
    labels = {c["label"]: c for c in row["criteria"]}
    assert labels["창의성"]["average"] == 5.0
    assert labels["완성도"]["average"] == 2.0
    assert labels["창의성"]["weight"] == 2


def test_audience_score_is_normalised_to_the_top(client, campus, db):
    """절대 득표수를 쓰면 관객이 적은 해에는 관객 몫이 사실상 사라진다."""
    top = _exhibit(client, campus, "1등")
    half = _exhibit(client, campus, "2등")
    db.commit()

    for no in ("20250001", "20250002"):
        h = _join(client, campus, no)
        client.post(f"/api/festivals/{campus.id}/exhibits/{top['id']}/vote", headers=h)
    one = _join(client, campus, "20250003")
    client.post(f"/api/festivals/{campus.id}/exhibits/{half['id']}/vote", headers=one)

    body = client.get(f"/api/festivals/{campus.id}/exhibition-results").json()
    by_title = {r["exhibit"]["title"]: r for r in body["items"]}
    assert by_title["1등"]["audience_score"] == 100.0
    assert by_title["2등"]["audience_score"] == 50.0


def test_a_criterion_nobody_scored_is_left_out_of_the_denominator(client, campus, db):
    """0 으로 치면 심사를 덜 받은 작품이 점수를 잃는다 — 작품이 아니라 운영의 문제다."""
    e = _exhibit(client, campus)
    c1 = _criterion(client, campus, "창의성", max_score=5)
    _criterion(client, campus, "아무도 안 매긴 항목", max_score=5)
    judge = _judge(db, campus)
    db.commit()

    client.put(
        f"/api/festivals/{campus.id}/exhibits/{e['id']}/scores",
        json={"scores": [{"criterion_id": c1["id"], "score": 4}]},
        headers=_as(judge),
    )

    row = client.get(f"/api/festivals/{campus.id}/exhibition-results").json()["items"][0]
    # 4/5 = 80. 안 매긴 항목을 0 으로 쳤다면 40 이 됐을 것이다.
    assert row["judge_score"] == 80.0


def test_results_warn_when_judging_is_uneven(client, campus, db):
    """두 명이 본 평균과 다섯 명이 본 평균은 같은 무게가 아니다."""
    a = _exhibit(client, campus, "많이 본 작품")
    b = _exhibit(client, campus, "덜 본 작품")
    c = _criterion(client, campus, "창의성")
    j1 = _judge(db, campus, "A")
    j2 = _judge(db, campus, "B")
    db.commit()

    for j in (j1, j2):
        client.put(
            f"/api/festivals/{campus.id}/exhibits/{a['id']}/scores",
            json={"scores": [{"criterion_id": c["id"], "score": 4}]},
            headers=_as(j),
        )
    client.put(
        f"/api/festivals/{campus.id}/exhibits/{b['id']}/scores",
        json={"scores": [{"criterion_id": c["id"], "score": 4}]},
        headers=_as(j1),
    )

    body = client.get(f"/api/festivals/{campus.id}/exhibition-results").json()
    codes = {w["code"] for w in body["warnings"]}
    assert "UNEVEN_JUDGING" in codes


def test_results_warn_when_nothing_has_been_judged(client, campus, db):
    _exhibit(client, campus)
    _criterion(client, campus, "창의성")
    db.commit()

    body = client.get(f"/api/festivals/{campus.id}/exhibition-results").json()
    codes = {w["code"] for w in body["warnings"]}
    assert "UNJUDGED_EXHIBITS" in codes
    assert "NO_AUDIENCE_VOTES" in codes


def test_weighting_is_configurable(client, campus, db):
    """가중치를 코드에 박으면 축제마다 다른 심사 규정을 담을 수 없다."""
    e = _exhibit(client, campus)
    c = _criterion(client, campus, "창의성", max_score=5)
    judge = _judge(db, campus)
    db.commit()

    client.put(
        f"/api/festivals/{campus.id}/exhibits/{e['id']}/scores",
        json={"scores": [{"criterion_id": c["id"], "score": 5}]},
        headers=_as(judge),
    )
    h = _join(client, campus, "20250001")
    client.post(f"/api/festivals/{campus.id}/exhibits/{e['id']}/vote", headers=h)

    changed = client.put(
        f"/api/festivals/{campus.id}/exhibition-settings",
        json={
            "audience_votes_per_participant": 5,
            "judge_weight_percent": 50,
            "voting_open": True,
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["judge_weight_percent"] == 50
    assert changed.json()["audience_weight_percent"] == 50
    assert changed.json()["votes_limit"] == 5


def test_archived_exhibit_leaves_the_ranking(client, campus, db):
    """지우지 않고 아카이브한다 — 이미 받은 표와 점수를 지우면 집계가 흔들린다."""
    keep = _exhibit(client, campus, "남는 작품")
    drop = _exhibit(client, campus, "내리는 작품")
    db.commit()

    assert (
        client.post(f"/api/festivals/{campus.id}/exhibits/{drop['id']}/archive")
    ).status_code == 204

    titles = [
        r["exhibit"]["title"]
        for r in client.get(f"/api/festivals/{campus.id}/exhibition-results").json()["items"]
    ]
    assert titles == ["남는 작품"]
    # 행 자체는 남아 있다.
    assert db.query(Exhibit).filter(Exhibit.id == drop["id"]).one().archived_at is not None
