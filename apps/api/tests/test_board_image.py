"""조각 보드 그림 업로드 — 클라이언트를 믿지 않는지 확인한다.

업로드는 조용히 위험합니다. 파일명을 그대로 쓰면 저장 경로를 벗어나거나
`.html` 로 저장돼 같은 오리진에서 스크립트가 실행됩니다.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core.config import settings
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import Festival, Organization, StampBoard, StampTile
from festaflow.services import media

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBP" + b"\x00" * 64


@pytest.fixture(autouse=True)
def media_dir(tmp_path, monkeypatch):
    """실제 업로드 디렉터리를 건드리지 않는다."""
    monkeypatch.setattr(settings, "media_dir", str(tmp_path / "media"), raising=False)
    return tmp_path / "media"


@pytest.fixture
def festival(db: Session) -> Festival:
    org = Organization(name="춘천시문화재단")
    db.add(org)
    db.flush()
    f = Festival(
        organization_id=org.id,
        name="춘천 가을 먹거리 축제",
        region="강원특별자치도 춘천시",
        venue="공지천 조각공원",
        starts_on=date(2026, 10, 10),
        ends_on=date(2026, 10, 12),
        expected_visitors=18000,
        total_budget=240000000,
    )
    db.add(f)
    db.flush()
    board = StampBoard(festival_id=f.id, rows=3, cols=3)
    db.add(board)
    db.flush()
    for idx in range(board.total_tiles):
        db.add(StampTile(board_id=board.id, board_version=board.version, tile_index=idx))
    db.flush()
    return f


@pytest.fixture
def client(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _upload(client, festival, content: bytes, filename: str = "board.png", ctype="image/png"):
    return client.post(
        f"/api/festivals/{festival.id}/stamp-board/image",
        files={"file": (filename, io.BytesIO(content), ctype)},
    )


def test_upload_sets_image_url_without_bumping_version(client, festival, db):
    """그림만 바꾸는 것은 되돌릴 수 있어 진행을 초기화하지 않는다."""
    r = _upload(client, festival, PNG)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["image_url"].startswith("/media/board-")
    assert body["image_url"].endswith(".png")
    assert body["version"] == 1


def test_extension_comes_from_magic_bytes_not_the_filename(client, festival):
    """`.html` 로 저장되면 같은 오리진에서 스크립트가 실행된다."""
    r = _upload(client, festival, PNG, filename="evil.html", ctype="text/html")
    assert r.status_code == 200, r.text
    assert r.json()["image_url"].endswith(".png")


def test_path_traversal_in_filename_is_ignored(client, festival, media_dir):
    r = _upload(client, festival, PNG, filename="../../../../etc/passwd")
    assert r.status_code == 200, r.text
    url = r.json()["image_url"]
    assert ".." not in url
    saved = Path(media.media_root()) / url.removeprefix("/media/")
    assert saved.is_file()
    assert saved.parent == Path(media.media_root())


def test_jpg_and_webp_are_accepted(client, festival):
    assert _upload(client, festival, JPG, "x.bin").json()["image_url"].endswith(".jpg")
    assert _upload(client, festival, WEBP, "x.bin").json()["image_url"].endswith(".webp")


def test_non_image_is_422(client, festival):
    r = _upload(client, festival, b"<html>not an image</html>", "sneaky.png")
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "VALIDATION_FAILED"


def test_empty_file_is_422(client, festival):
    assert _upload(client, festival, b"").status_code == 422


def test_oversized_file_is_413_and_leaves_nothing_behind(client, festival, monkeypatch):
    """스트림을 다 읽고 나서 재면 그 사이에 메모리를 다 쓴다."""
    monkeypatch.setattr(media, "MAX_BYTES", 1024, raising=False)
    r = _upload(client, festival, PNG + b"\x00" * 4096)
    assert r.status_code == 413
    assert r.json()["detail"]["error"]["code"] == "FILE_TOO_LARGE"
    # 자른 파일이 남아 있으면 깨진 그림이 보드에 걸린다.
    assert list(Path(media.media_root()).glob("board-*")) == []
