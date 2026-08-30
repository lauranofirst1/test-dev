"""Consumer Experience 열람·회고 계약."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    Booth,
    Festival,
    Mission,
    Organization,
    Participant,
    Participation,
    StampBoard,
    StampTile,
)
from festaflow.models.enums import (
    BoothQrMode,
    BoothType,
    BoothVerifyMode,
    ParticipationStatus,
)
from festaflow.services.consumer import build_experience_insights


@pytest.fixture
def client(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def festival(db: Session) -> Festival:
    org = Organization(name="소비자 경험 테스트 조직")
    db.add(org)
    db.flush()
    item = Festival(
        organization_id=org.id,
        name="경험이 흐르는 축제",
        region="강원특별자치도 춘천시",
        venue="캠퍼스 광장",
        starts_on=date(2026, 8, 30),
        ends_on=date(2026, 8, 31),
        expected_visitors=1000,
        total_budget=10_000_000,
    )
    db.add(item)
    db.flush()
    return item


@pytest.fixture
def mission(db: Session, festival: Festival) -> Mission:
    booth = Booth(
        festival_id=festival.id,
        name="향기 연구소",
        booth_type=BoothType.EXPERIENCE,
        is_active=True,
    )
    db.add(booth)
    db.flush()
    item = Mission(
        festival_id=festival.id,
        booth_id=booth.id,
        title="나만의 향 만들기",
        description="세 가지 향을 골라 조합합니다.",
        points=100,
        estimated_duration_minutes=12,
        is_featured=True,
        is_active=True,
    )
    db.add(item)
    db.flush()
    return item


def _participant(client: TestClient, festival: Festival) -> tuple[dict, dict[str, str]]:
    response = client.post(f"/api/festivals/{festival.id}/participants")
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"X-Participant-Secret": body["secret"]}


def test_public_catalog_exposes_only_safe_consumer_metadata(
    client: TestClient, festival: Festival, mission: Mission
) -> None:
    response = client.get(f"/api/festivals/{festival.id}/public")

    assert response.status_code == 200
    body = response.json()
    public_mission = body["booths"][0]["missions"][0]
    assert public_mission["description"] == "세 가지 향을 골라 조합합니다."
    assert public_mission["estimated_duration_minutes"] == 12
    assert public_mission["is_featured"] is True
    assert "experience_config" not in public_mission
    assert "qr_secret" not in str(body)


def test_open_is_repeatable_but_report_keeps_unique_people_separate(
    db: Session, client: TestClient, festival: Festival, mission: Mission
) -> None:
    issued, headers = _participant(client, festival)
    payload = {"source_type": "mission", "source_id": mission.id, "source_context": "search"}

    first = client.post(
        f"/api/festivals/{festival.id}/experience-opens", json=payload, headers=headers
    )
    second = client.post(
        f"/api/festivals/{festival.id}/experience-opens", json=payload, headers=headers
    )

    assert first.status_code == 201
    assert second.status_code == 201
    insight = build_experience_insights(db, festival.id)[0]
    assert insight.opens == 2
    assert insight.unique_openers == 1
    assert insight.discovery_contexts == {"search": 2}
    assert issued["code"].startswith("FF-")


def test_favorite_memory_is_one_atomic_replaceable_choice(
    client: TestClient, festival: Festival, mission: Mission
) -> None:
    _, headers = _participant(client, festival)
    path = f"/api/festivals/{festival.id}/favorite-memory"

    first = client.put(
        path,
        headers=headers,
        json={
            "source_type": "mission",
            "source_id": mission.id,
            "reason": "fun",
            "comment": "  같이 만들어서 좋았다.  ",
        },
    )
    second = client.put(
        path,
        headers=headers,
        json={
            "source_type": "mission",
            "source_id": mission.id,
            "reason": "again",
            "comment": "다시 해 보고 싶다.",
        },
    )
    current = client.get(path, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert current.json()["reason"] == "again"
    assert current.json()["comment"] == "다시 해 보고 싶다."


def test_source_must_belong_to_festival_in_url(
    db: Session, client: TestClient, festival: Festival, mission: Mission
) -> None:
    _, headers = _participant(client, festival)
    other = Festival(
        organization_id=festival.organization_id,
        name="다른 축제",
        region="서울특별시",
        venue="다른 광장",
        starts_on=date(2026, 9, 1),
        ends_on=date(2026, 9, 1),
        expected_visitors=100,
        total_budget=1_000_000,
    )
    db.add(other)
    db.flush()
    other_booth = Booth(
        festival_id=other.id,
        name="다른 부스",
        booth_type=BoothType.EXPERIENCE,
        is_active=True,
    )
    db.add(other_booth)
    db.flush()
    other_mission = Mission(
        festival_id=other.id,
        booth_id=other_booth.id,
        title="다른 경험",
        points=0,
        is_active=True,
    )
    db.add(other_mission)
    db.flush()

    response = client.post(
        f"/api/festivals/{festival.id}/experience-opens",
        headers=headers,
        json={
            "source_type": "mission",
            "source_id": other_mission.id,
            "source_context": "now",
        },
    )

    assert response.status_code == 404


def test_insight_separates_verified_completion_from_opens(
    db: Session, client: TestClient, festival: Festival, mission: Mission
) -> None:
    issued, headers = _participant(client, festival)
    client.post(
        f"/api/festivals/{festival.id}/experience-opens",
        headers=headers,
        json={"source_type": "mission", "source_id": mission.id, "source_context": "now"},
    )
    # 발급 응답은 내부 id를 노출하지 않는다. 비밀로 인증한 본인 조회의 코드를 이용해 찾는다.
    participant = db.query(Participant).filter_by(code=issued["code"]).one()
    db.add(
        Participation(
            festival_id=festival.id,
            participant_id=participant.id,
            mission_id=mission.id,
            booth_id=mission.booth_id,
            status=ParticipationStatus.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    db.flush()

    insight = build_experience_insights(db, festival.id)[0]
    assert insight.opens == 1
    assert insight.unique_openers == 1
    assert insight.verified_participants == 1
    assert insight.completed_participants == 1


def test_consumer_journey_connects_discovery_verified_action_flow_and_memory(
    db: Session, client: TestClient, festival: Festival, mission: Mission
) -> None:
    """공개 탐색부터 현장 확인·Flow 재조회·회고·분석까지 한 계약으로 이어진다."""
    booth = db.get(Booth, mission.booth_id)
    assert booth is not None
    booth.verify_mode = BoothVerifyMode.PARTICIPANT_SCAN
    booth.qr_mode = BoothQrMode.PRINTED
    booth.qr_secret = b"consumer-journey-demo-secret-32b"[:32]
    board = StampBoard(festival_id=festival.id, rows=2, cols=2)
    db.add(board)
    db.flush()
    for tile_index in range(4):
        db.add(
            StampTile(
                board_id=board.id,
                board_version=board.version,
                tile_index=tile_index,
                assigned_booth_id=booth.id if tile_index == 0 else None,
            )
        )
    db.flush()

    public = client.get(f"/api/festivals/{festival.id}/public")
    assert public.status_code == 200
    assert public.json()["booths"][0]["missions"][0]["title"] == mission.title

    _, headers = _participant(client, festival)
    opened = client.post(
        f"/api/festivals/{festival.id}/experience-opens",
        headers=headers,
        json={"source_type": "mission", "source_id": mission.id, "source_context": "now"},
    )
    assert opened.status_code == 201

    signature = security.booth_print_signature(booth.qr_secret, booth.id)
    context = client.get(
        f"/api/festivals/{festival.id}/scan",
        headers=headers,
        params={"booth_id": booth.id, "s": signature},
    )
    assert context.status_code == 200, context.text
    granted = client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        headers=headers,
        json={"booth_id": booth.id, "signature": signature, "mission_id": mission.id},
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["was_already_granted"] is False

    progress = client.get(f"/api/festivals/{festival.id}/participants/me", headers=headers)
    assert progress.status_code == 200
    mine = next(item for item in progress.json()["missions"] if item["mission_id"] == mission.id)
    assert mine["status"] == "granted"
    assert mine["completed_at"] is not None

    favorite = client.put(
        f"/api/festivals/{festival.id}/favorite-memory",
        headers=headers,
        json={
            "source_type": "mission",
            "source_id": mission.id,
            "reason": "discovered",
            "comment": "몰랐던 경험을 발견했다.",
        },
    )
    assert favorite.status_code == 200

    insight = build_experience_insights(db, festival.id)[0]
    assert insight.opens == 1
    assert insight.unique_openers == 1
    assert insight.verified_participants == 1
    assert insight.completed_participants == 1
    assert insight.favorites == 1
    assert insight.favorite_reasons == {"discovered": 1}
