#!/usr/bin/env python3
"""조각 보드 자리표시 이미지를 만든다.

`stamp_boards.image_url` 의 기본값이 `/images/chuncheon-stamp-board.png` 인데
그 파일이 없으면, Vite 개발 서버가 없는 경로에 index.html 을 200 으로 돌려주고
브라우저가 HTML 을 이미지로 디코딩하려다 멈춥니다(스크린샷·렌더 지연).
기본값이 항상 실제 파일을 가리키게 두기 위한 스크립트입니다.

실제 축제 그림이 준비되면 같은 경로에 덮어쓰면 됩니다. 파일명을 바꾸려면
DB 기본값(server_default)도 함께 바꿔야 합니다.

    python3 scripts/make-placeholder-board.py

의존성이 없습니다 — Pillow 를 깔지 않고 zlib 로 PNG 를 직접 씁니다.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 900  # 3×3 으로 잘라도 300px 이라 모바일에서 충분하다

# 프로젝트 팔레트(tokens.css)에서 가져온 값. 조각 경계가 눈에 보이도록
# 인접한 칸의 명도를 다르게 둔다.
PALETTE = [
    (0xBE, 0xE3, 0xD4),
    (0xDD, 0xF0, 0xE7),
    (0xD6, 0xCB, 0xF3),
    (0xEC, 0xE6, 0xFA),
    (0xF6, 0xF7, 0xF3),
    (0xBE, 0xE3, 0xD4),
    (0xEC, 0xE6, 0xFA),
    (0xDD, 0xF0, 0xE7),
    (0xD6, 0xCB, 0xF3),
]
INK = (0x25, 0x60, 0x48)


def pixel(x: int, y: int) -> tuple[int, int, int]:
    cell = (y * 3 // SIZE) * 3 + (x * 3 // SIZE)
    r, g, b = PALETTE[cell % len(PALETTE)]

    # 칸 안에서 대각선 그라데이션 — 단색 9칸보다 그림처럼 읽힌다.
    t = ((x % (SIZE // 3)) + (y % (SIZE // 3))) / (2 * SIZE / 3)
    r = int(r + (INK[0] - r) * t * 0.18)
    g = int(g + (INK[1] - g) * t * 0.18)
    b = int(b + (INK[2] - b) * t * 0.18)

    # 조각 경계선
    if x % (SIZE // 3) < 3 or y % (SIZE // 3) < 3:
        return INK
    return (r, g, b)


def main() -> None:
    raw = bytearray()
    for y in range(SIZE):
        raw.append(0)  # 필터 타입 0 (None)
        for x in range(SIZE):
            raw.extend(pixel(x, y))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")

    out = Path(__file__).resolve().parents[1] / "public" / "images" / "chuncheon-stamp-board.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"{out} ({len(png) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
