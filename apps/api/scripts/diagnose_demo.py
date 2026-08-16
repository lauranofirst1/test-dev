#!/usr/bin/env python
"""데모 축제를 만들고 실제 관광 데이터로 진단을 돌린다.

    cd apps/api && ./.venv/bin/python scripts/diagnose_demo.py

한국관광공사 OpenAPI 를 실시간 호출합니다(캐시 없음).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import delete, select  # noqa: E402

from festaflow.db.session import SessionLocal  # noqa: E402
from festaflow.models import (  # noqa: E402
    Booth,
    Festival,
    FestivalPlan,
    Mission,
    Organization,
    StampBoard,
    StampTile,
)
from festaflow.models.enums import BoothType  # noqa: E402
from festaflow.services import diagnosis, rubric  # noqa: E402
from festaflow.services.tourapi import TourApiClient  # noqa: E402

DIM, BOLD, GREEN, YELLOW, RED, RESET = "\033[2m", "\033[1m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"

BOOTHS = [
    ("막국수 체험존", BoothType.EXPERIENCE, "A구역 3번"),
    ("닭갈비 골목", BoothType.FOOD, "B구역 1번"),
    ("지역상점존", BoothType.LOCAL_SHOP, "D구역 2번"),
    ("관광안내소", BoothType.INFORMATION, "정문"),
    ("메인 무대", BoothType.PERFORMANCE, "중앙"),
    ("포토존", BoothType.ETC, "C구역"),
]


def seed(db) -> Festival:
    """데모 축제를 새로 만든다 (기존 데모는 지운다)."""
    db.execute(delete(Festival).where(Festival.is_demo.is_(True)))
    org = db.execute(select(Organization).limit(1)).scalar_one_or_none()
    if org is None:
        org = Organization(name="춘천시문화재단", kind="government")
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
        total_budget=240_000_000,
        is_demo=True,
    )
    db.add(f)
    db.flush()

    db.add(
        FestivalPlan(
            festival_id=f.id,
            summary="지역 식재료와 로컬 뮤지션이 만나는 3일",
            description="춘천의 대표 먹거리와 지역 상권을 잇는 가을 축제",
            core_audience="가족 단위 방문객, 20~30대",
            purposes=["지역상권 활성화", "관광객 유치"],
            target_segments=["가족", "20~30대"],
            venue_capacity=4000,
            staff_count=30,
            volunteer_count=20,
            safety_staff_count=10,
            planned_food=12,
            planned_performance=6,
            planned_experience=8,
            safety_plan="권역별 안전요원 2인 배치, 야간 조명 보강",
            traffic_plan="셔틀버스 20분 간격, 임시 주차장 3곳",
        )
    )
    for name, btype, loc in BOOTHS:
        b = Booth(festival_id=f.id, name=name, booth_type=btype, location=loc)
        db.add(b)
        db.flush()
        for i in range(2):
            db.add(
                Mission(
                    festival_id=f.id, booth_id=b.id,
                    title=f"{name} 미션 {i + 1}", points=100,
                )
            )
    board = StampBoard(festival_id=f.id, rows=3, cols=3)
    db.add(board)
    db.flush()
    for idx in range(board.total_tiles):
        db.add(StampTile(board_id=board.id, board_version=board.version, tile_index=idx))
    db.commit()
    return f


def bar(score: float, maximum: float, width: int = 24) -> str:
    filled = round(width * score / maximum) if maximum else 0
    ratio = score / maximum if maximum else 0
    color = GREEN if ratio >= 0.8 else (YELLOW if ratio >= 0.6 else RED)
    return f"{color}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET}"


async def main() -> int:
    db = SessionLocal()
    try:
        festival = seed(db)
        print(f"{BOLD}{festival.name}{RESET}  {festival.region} · "
              f"{festival.starts_on}~{festival.ends_on} · "
              f"예상 {festival.expected_visitors:,}명 · 부스 {len(BOOTHS)}개\n")

        async with TourApiClient() as client:
            d = await diagnosis.run(db, festival, client=client)
            calls = client.call_count
        db.commit()

        if d.status.value != "completed":
            print(f"{RED}진단 실패{RESET}: {d.error_message}")
            return 1

        disclosed = rubric.is_score_disclosed(db, d.rubric_version)
        mode = "score" if disclosed else "checklist"

        print(f"{BOLD}종합 준비도{RESET}  ", end="")
        if disclosed:
            print(f"{d.total_score}/100  [{d.risk.value}]")
        else:
            print(f"{DIM}(체크리스트 모드 — 채점표 {d.rubric_version} 미검증){RESET}")
            print(f"{DIM}  내부 계산값 {d.total_score}/100 은 저장되지만 표시하지 않습니다{RESET}")
        print()

        db.refresh(d)
        for item in sorted(d.items, key=lambda i: -float(i.max_score)):
            label = {
                "tourism_demand": "관광수요 적합성",
                "crowd_safety": "혼잡·수용 안정성",
                "program_balance": "프로그램 균형",
                "local_linkage": "지역 관광 연계성",
                "ops_readiness": "운영 준비도",
            }[item.category.value]
            fulfil = rubric.FULFILLMENT[item.level]
            head = (
                f"{float(item.score):5.1f}/{float(item.max_score):.0f}"
                if disclosed else f"{fulfil:>7}"
            )
            print(f"  {label:<16} {bar(float(item.score), float(item.max_score))} {head}")
            print(f"    {DIM}근거  {item.reason}{RESET}")
            print(f"    {DIM}제안  {item.recommendation}{RESET}")
            print()

        risks = diagnosis.top_risks(list(d.items))
        if risks:
            print(f"{BOLD}주요 위험요소{RESET}")
            for r in risks:
                print(f"  ⚠ {r[:110]}")
            print()

        snap = d.input_snapshot or {}
        tour = snap.get("tourism", {})
        print(f"{BOLD}데이터 출처{RESET}")
        print(f"  {tour.get('source_note', '')}")
        print(f"  공급자 {tour.get('provider')} · 지역코드 {tour.get('area_code')}-"
              f"{tour.get('sigungu_code')} · 법정동 {tour.get('legal_dong_code')} · "
              f"관광자원 {tour.get('content_count'):,}건")
        if tour.get("daily_visitors_avg"):
            print(f"  실측 일평균 방문자 {tour['daily_visitors_avg']:,.0f}명 · "
                  f"외지인 비중 {tour.get('outsider_ratio', 0):.0%}")
        for r in tour.get("resources", [])[:5]:
            print(f"    {DIM}· [{r['category_label']}] {r['title']}{RESET}")
        for w in snap.get("warnings", []):
            print(f"  {YELLOW}⚠ {w}{RESET}")
        print(f"\n표시 모드 {mode} · API 실시간 호출 {calls}건 · 진단 #{d.id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
