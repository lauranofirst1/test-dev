"""업로드 파일 저장.

조각 보드 그림과 전시 포스터를 올립니다. 업로드는 조용히 위험한 경로라 세 가지를
지킵니다.

1. **클라이언트가 준 `content_type` 과 파일명을 믿지 않습니다.** 매직 바이트로
   실제 형식을 판별하고, 확장자는 판별 결과로 우리가 붙입니다. 파일명을 그대로
   쓰면 `../` 로 저장 경로를 벗어나거나 `.html` 로 저장돼 같은 오리진에서
   스크립트가 실행됩니다.
2. **크기를 먼저 자릅니다.** 스트림을 다 읽고 나서 재면 그 사이에 메모리를 다 씁니다.
3. 저장 이름은 서버가 난수로 만듭니다 — 다른 축제의 그림 주소를 추측할 수 없게.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import BinaryIO

from festaflow.core.config import settings
from festaflow.core.errors import ApiError, validation_failed

#: 매직 바이트 → 확장자. 여기 없는 형식은 저장하지 않는다.
SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"RIFF", ".webp"),  # RIFF....WEBP — 아래에서 WEBP 까지 확인한다
)

MAX_BYTES = 5 * 1024 * 1024
CHUNK = 64 * 1024


def _sniff(head: bytes) -> str:
    for magic, ext in SIGNATURES:
        if head.startswith(magic):
            if ext == ".webp" and head[8:12] != b"WEBP":
                continue
            return ext
    raise validation_failed(
        "PNG · JPG · WEBP 이미지만 올릴 수 있습니다.", "file"
    )


def media_root() -> Path:
    root = Path(settings.media_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_image(stream: BinaryIO, festival_id: int, *, prefix: str) -> str:
    """이미지를 저장하고 화면이 쓸 URL 경로를 돌려준다.

    `prefix` 는 파일 이름 앞머리일 뿐이며 경로에 쓰이지 않습니다 — 저장 위치는
    항상 `media_root()` 이고, 이름의 나머지는 서버가 난수로 만듭니다.
    """
    head = stream.read(32)
    if not head:
        raise validation_failed("빈 파일입니다.", "file")
    ext = _sniff(head)

    name = f"{prefix}-{festival_id}-{secrets.token_urlsafe(8)}{ext}"
    path = media_root() / name

    written = 0
    with path.open("wb") as out:
        out.write(head)
        written += len(head)
        while chunk := stream.read(CHUNK):
            written += len(chunk)
            if written > MAX_BYTES:
                # 여기서 멈추지 않으면 디스크와 메모리를 그대로 내준다.
                out.close()
                path.unlink(missing_ok=True)
                raise ApiError(
                    413,
                    "FILE_TOO_LARGE",
                    f"이미지는 {MAX_BYTES // (1024 * 1024)}MB 이하만 올릴 수 있습니다.",
                    {"max_bytes": MAX_BYTES},
                )
            out.write(chunk)

    return f"/media/{name}"


def save_board_image(stream: BinaryIO, festival_id: int) -> str:
    """조각 보드 그림."""
    return save_image(stream, festival_id, prefix="board")


def save_poster(stream: BinaryIO, festival_id: int) -> str:
    """전시 작품 포스터. 보드 그림과 같은 검사를 거친다."""
    return save_image(stream, festival_id, prefix="poster")


def delete_festival_media(festival_id: int) -> None:
    """영구 삭제된 축제의 업로드 파일을 함께 지운다.

    파일 이름은 서버가 만든 ``{종류}-{축제 ID}-{난수}`` 형식만 대상으로 한다.
    기본 이미지나 다른 축제의 파일은 건드리지 않는다.
    """
    root = media_root()
    for prefix in ("board", "poster"):
        for path in root.glob(f"{prefix}-{festival_id}-*"):
            if path.is_file():
                path.unlink(missing_ok=True)
