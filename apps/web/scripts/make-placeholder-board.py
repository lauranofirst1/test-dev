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

import math
import struct
import zlib
from pathlib import Path

#: 2×2·2×3·3×3 어느 격자로 잘라도 각 조각이 300px 이상이 되게 6의 배수로 둔다.
SIZE = 900

# 프로젝트 팔레트(tokens.css)에서 가져온 값.
MINT = (0xBE, 0xE3, 0xD4)
MINT_WASH = (0xDD, 0xF0, 0xE7)
LAV = (0xD6, 0xCB, 0xF3)
LAV_WASH = (0xEC, 0xE6, 0xFA)
INK = (0x25, 0x60, 0x48)


def _mix(a, b, t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def pixel(x: int, y: int) -> tuple[int, int, int]:
    """격자를 모르는 그림.

    보드는 2×2·2×3·3×3 중에 고를 수 있으므로 **조각 경계를 그림에 그려 넣으면
    안 된다.** 3×3 기준으로 선을 그려두면 2×3 으로 바꾼 순간 선이 조각 안쪽을
    지나가 잘못 자른 것처럼 보인다. 어디서 잘라도 자연스럽도록 경계 없는
    사선 그라데이션과 완만한 물결만 쓴다.
    """
    u = x / SIZE
    v = y / SIZE

    # 좌상 민트 → 우하 라벤더 대각 그라데이션
    base = _mix(_mix(MINT, MINT_WASH, v), _mix(LAV_WASH, LAV, v), u)

    # 어느 조각에도 특징이 남도록 완만한 물결을 얹는다(주기가 격자와 무관하다).
    wave = 0.5 + 0.5 * math.sin(6.0 * (u + v) + 1.5 * math.sin(5.0 * v))
    return _mix(base, INK, 0.10 * wave)


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
