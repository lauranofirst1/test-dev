"""오류 봉투 — 전 엔드포인트가 같은 모양으로 실패한다. 계약 §0.

계약이 정한 모양은 하나입니다.

    {"error": {"code": "...", "message": "...", "details": {...}}}

FastAPI 기본 핸들러는 `HTTPException.detail` 을 `{"detail": ...}` 로 한 겹 더
감싸는데, `ApiError` 는 detail 자리에 이미 봉투를 넣습니다. 그래서 예전에는
`{"detail": {"error": {...}}}` 가 나갔습니다. 화면 클라이언트가 두 겹을 모두
벗도록 방어하고 있어 겉으로는 멀쩡했지만, 그건 계약이 지켜졌다는 뜻이 아니라
클라이언트가 위반을 가려 주고 있었다는 뜻입니다.

**`message` 는 그대로 화면에 노출됩니다.** 그래서 우리가 만들지 않은 오류도
한국어여야 합니다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import Organization


@pytest.fixture
def client(db: Session):
    # 기관이 하나도 없으면 기관 스코프가 409 로 먼저 끊겨, 정작 보려던
    # NOT_FOUND 경로에 닿지 못한다.
    db.add(Organization(name="춘천시문화재단"))
    db.flush()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _envelope(body: object) -> dict:
    """봉투가 딱 한 겹인지 확인하고 안을 돌려준다."""
    assert isinstance(body, dict)
    # `detail` 이 남아 있으면 한 겹 더 싸여 나간 것이다.
    assert set(body) == {"error"}, body
    error = body["error"]
    assert set(error) >= {"code", "message", "details"}
    return error


def test_apierror_는_봉투_한_겹이다(client: TestClient) -> None:
    r = client.get("/api/festivals/99999999")

    assert r.status_code == 404
    error = _envelope(r.json())
    assert error["code"] == "NOT_FOUND"
    assert error["message"] == "축제를 찾을 수 없습니다."


def test_검증_실패도_같은_봉투다(client: TestClient) -> None:
    r = client.post("/api/auth/signup", json={"email": "말이 안 되는 값"})

    assert r.status_code == 422
    error = _envelope(r.json())
    assert error["code"] == "VALIDATION_FAILED"
    # 화면이 어느 칸 밑에 붙일지 아는 유일한 단서다.
    assert "field" in error["details"]


def test_없는_주소도_같은_봉투다(client: TestClient) -> None:
    """오래된 북마크나 잘못된 링크로 사용자가 실제로 본다."""
    r = client.get("/api/그런거없음")

    assert r.status_code == 404
    error = _envelope(r.json())
    assert error["message"] == "요청한 주소를 찾을 수 없습니다."


def test_잘못된_메서드도_같은_봉투다(client: TestClient) -> None:
    r = client.patch("/api/health")

    assert r.status_code == 405
    assert _envelope(r.json())["message"] == "이 주소에서는 쓸 수 없는 방식입니다."
    # 405 는 응답의 의미가 헤더에 실려 온다. 봉투를 갈아 끼우면서 잃으면 안 된다.
    assert r.headers.get("allow")


def test_영어_문장이_새어_나가지_않는다(client: TestClient) -> None:
    """이 저장소는 "message 는 그대로 화면에 노출된다" 를 규칙으로 삼는다."""
    for call in (
        lambda: client.get("/api/nope"),
        lambda: client.patch("/api/health"),
        lambda: client.post("/api/auth/signup", json={"email": "x"}),
        lambda: client.get("/api/festivals/99999999"),
    ):
        message = _envelope(call().json())["message"]
        assert not message.isascii(), message
