#!/usr/bin/env python
"""TourAPI 실호출 점검.

.env 에 KTO_API_KEY 를 넣은 뒤 실행하세요.

    cd apps/api && ./.venv/bin/python scripts/kto_smoke.py

승인된 API만 성공합니다. 미승인 서비스는 code 30(등록되지 않은 서비스키)이 나오는데,
이건 키가 틀린 게 아니라 그 API를 아직 활용신청하지 않았다는 뜻입니다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from festaflow.core.config import KtoService, settings  # noqa: E402
from festaflow.services.tourapi import (  # noqa: E402
    KtoError,
    KtoNoData,
    TourApiClient,
    category_code,
    coordinates,
    image_url,
    region_codes,
)

# (라벨, 서비스, 오퍼레이션, 추가 파라미터)
CHECKS: list[tuple[str, str, str, dict]] = [
    ("국문 관광정보 · 지역기반", KtoService.KOR, "areaBasedList2", {"arrange": "A"}),
    ("국문 관광정보 · 지역코드", KtoService.KOR, "areaCode2", {}),
    ("관광 빅데이터 · 기초지자체 방문자수", KtoService.DATALAB, "locgoRegnVisitrDDList", {}),
    ("관광 빅데이터 · 혼잡도 예측", KtoService.DATALAB, "tarDecoList", {}),
    ("관광 빅데이터 · 관광 소요시간", KtoService.DATALAB, "tarTursmRqmtList", {}),
    ("관광지 집중률 30일 예측", KtoService.CONCENTRATION, "tatsCnctrRateList", {}),
    ("관광지별 연관 관광지", KtoService.RELATED, "areaBasedList", {}),
    ("기초지자체 중심 관광지", KtoService.HUB, "areaBasedList", {}),
    ("관광사진갤러리", KtoService.PHOTO, "galleryList1", {}),
]

GREEN, YELLOW, RED, DIM, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"


async def main() -> int:
    if not settings.has_kto_key:
        print(f"{RED}✗ 인증키가 없습니다.{RESET} .env 의 KTO_API_KEY 를 채우세요.")
        print(f"{DIM}  포털이 주는 Encoding/Decoding 두 벌 중 'Decoding 키'입니다.{RESET}")
        return 1

    print(f"base : {settings.kto_base_url}")
    print(f"app  : {settings.kto_mobile_app}")
    print(f"cache: {settings.tourism_snapshot_cache_enabled} "
          f"{DIM}(공모전 기간에는 False 여야 호출 이력이 남습니다){RESET}\n")

    ok = blocked = failed = 0

    async with TourApiClient() as client:
        for label, service, operation, extra in CHECKS:
            try:
                res = await client.call(service, operation, extra, num_of_rows=3)
            except KtoNoData:
                print(f"{YELLOW}◐{RESET} {label:<34} 데이터 없음 {DIM}(정상 — 에러 아님){RESET}")
                ok += 1
                continue
            except KtoError as exc:
                mark = RED if exc.code not in {"30", "20"} else YELLOW
                note = "미승인 API로 보입니다" if exc.code == "30" else str(exc)[:70]
                print(f"{mark}✗{RESET} {label:<34} code={exc.code} {DIM}{note}{RESET}")
                if exc.code in {"30", "20"}:
                    blocked += 1
                else:
                    failed += 1
                continue

            print(f"{GREEN}✓{RESET} {label:<34} total={res.total_count:,} items={len(res.items)}")

            # 국문 관광정보는 필드 파싱까지 확인
            if service == KtoService.KOR and operation == "areaBasedList2" and res.items:
                it = res.items[0]
                print(
                    f"  {DIM}└ {it.get('title', '?')} | 유형 {category_code(it)} | "
                    f"법정동 {'-'.join(x or '?' for x in region_codes(it))} | "
                    f"좌표 {coordinates(it)} | 이미지 {(image_url(it) or '없음')[:48]}{RESET}"
                )

        print(f"\n총 요청 {client.call_count}건 전송")

    print(f"{GREEN}성공 {ok}{RESET} · {YELLOW}미승인 {blocked}{RESET} · {RED}실패 {failed}{RESET}")
    if blocked:
        print(f"{DIM}미승인 API는 공공데이터포털에서 활용신청하면 약 10분 뒤 열립니다.{RESET}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
