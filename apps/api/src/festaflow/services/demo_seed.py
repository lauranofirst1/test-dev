"""데모 축제 시드 — 처음 열었을 때 빈 화면을 보여주지 않기 위한 것.

웹은 주소만 건네고 상대가 직접 들어옵니다. 그때 **첫 화면이 빈 워크스페이스**면
무엇을 하는 도구인지 알 방법이 없습니다. 로그인해서 축제를 만들고 부스를 넣고
진단을 돌려야 비로소 화면이 채워지는데, 처음 온 사람이 거기까지 갈 이유가 없습니다.

## 이 모듈이 조심하는 것 둘

**1. 지우지 않습니다.** `scripts/diagnose_demo.py` 의 `seed()` 는 기존 데모를
지우고 다시 만듭니다. CLI 로 한 번 돌릴 때는 그게 맞지만, 기동 훅에 그대로 붙이면
**서버를 재시작할 때마다 데모가 초기화**됩니다. 누가 데모 축제에서 뭘 해 보고
있었다면 그게 사라집니다. 그래서 여기서는 **이미 있으면 아무것도 하지 않습니다.**

**2. 부팅에서 TourAPI 를 부르지 않습니다.** 진단은 한국관광공사 API 를 실시간으로
호출하고 지역에 따라 10초가 걸립니다. 그걸 기동 경로에 넣으면 서버가 그만큼 늦게
뜨고, API 가 죽어 있으면 **서버가 아예 안 뜹니다.** 그래서 시드는 축제·부스·미션·
보드까지만 만들고, 진단은 화면의 「진단 실행」 버튼이 돌립니다.

## 언제 도는가

`DEMO_MODE=true` 일 때만 돕니다. 실제 축제를 운영하는 DB 에 예제 데이터가
섞이면 그때부터 모든 집계가 오염됩니다.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.models import (
    Booth,
    Festival,
    FestivalPlan,
    Mission,
    Organization,
    StampBoard,
    StampTile,
)
from festaflow.models.enums import BoothType

log = logging.getLogger(__name__)

DEMO_NAME = "춘천 가을 먹거리 축제"

#: 부스와 미션. 유형을 흩어 두는 이유는 진단의 프로그램 균형 점수가
#: 한쪽으로 몰린 구성을 낮게 주기 때문이다 — 데모가 스스로 나쁜 예가 되면 곤란하다.
BOOTHS: list[tuple[str, BoothType, str, list[str]]] = [
    ("막국수 체험존", BoothType.EXPERIENCE, "A구역 3번", ["막국수 반죽 체험", "메밀 이야기 듣기"]),
    ("닭갈비 골목", BoothType.FOOD, "B구역 1번", ["닭갈비 시식", "지역 식재료 퀴즈"]),
    ("지역상점존", BoothType.LOCAL_SHOP, "C구역", ["로컬 상점 방문", "장바구니 인증"]),
    ("관광안내소", BoothType.INFORMATION, "정문 옆", ["코스 안내 받기"]),
    ("공지천 무대", BoothType.PERFORMANCE, "중앙 잔디", ["공연 관람 인증"]),
    ("청년 창업존", BoothType.ETC, "D구역", ["창업 부스 둘러보기"]),
]


def ensure_demo(db: Session) -> Festival | None:
    """데모 축제가 없으면 만든다. **있으면 손대지 않는다.**

    돌려주는 값은 새로 만든 축제입니다. 이미 있었으면 `None` 입니다 —
    호출자가 "만들었다" 와 "이미 있었다" 를 로그로 구분할 수 있게.
    """
    existing = db.execute(
        select(Festival).where(Festival.is_demo.is_(True), Festival.archived_at.is_(None))
    ).scalars().first()
    if existing is not None:
        return None

    org = db.execute(
        select(Organization).where(Organization.is_active.is_(True)).order_by(Organization.id)
    ).scalars().first()
    if org is None:
        org = Organization(name="춘천시문화재단", kind="government")
        db.add(org)
        db.flush()

    from datetime import date

    festival = Festival(
        organization_id=org.id,
        name=DEMO_NAME,
        region="강원특별자치도 춘천시",
        venue="공지천 조각공원",
        starts_on=date(2026, 10, 10),
        ends_on=date(2026, 10, 12),
        expected_visitors=18000,
        total_budget=240_000_000,
        is_demo=True,
    )
    db.add(festival)
    db.flush()

    db.add(
        FestivalPlan(
            festival_id=festival.id,
            summary="지역 식재료와 로컬 뮤지션이 만나는 3일",
            description="춘천의 대표 먹거리와 지역 상권을 잇는 가을 축제",
            core_audience="가족 단위 방문객, 20~30대",
            purposes=["지역상권 활성화", "관광객 유치"],
            target_segments=["가족", "20~30대"],
            venue_capacity=4000,
            staff_count=30,
            volunteer_count=20,
            safety_staff_count=10,
            parking_capacity=600,
            planned_food=12,
            planned_performance=6,
            planned_experience=8,
            planned_local_shop=4,
            planned_tour_info=2,
            safety_plan="권역별 안전요원 2인 배치, 야간 조명 보강, 우천 시 중단 기준 사전 공지",
            traffic_plan="셔틀버스 20분 간격, 임시 주차장 3곳 운영",
            crowd_plan="입구 2곳 분산 입장, 시간대별 인원 계수",
            transit_access="춘천역 도보 15분, 시내버스 5개 노선",
            tourism_link_plan="인근 관광지와 잇는 축제 전후 반나절 코스 운영",
            local_commerce_plan="지역 상점가 쿠폰 연계",
            promotion_plan="SNS·지역 커뮤니티·현수막 3채널",
        )
    )

    for name, booth_type, location, missions in BOOTHS:
        booth = Booth(
            festival_id=festival.id, name=name, booth_type=booth_type, location=location
        )
        db.add(booth)
        db.flush()
        for title in missions:
            db.add(
                Mission(
                    festival_id=festival.id, booth_id=booth.id, title=title, points=100
                )
            )

    # 3×3 보드에 부스가 6개면 완성이 불가능하다. 2×3(6조각)으로 맞춘다 —
    # 데모가 대시보드에 "완성 불가" 경고를 띄운 채로 시작하면 안 된다.
    board = StampBoard(festival_id=festival.id, rows=2, cols=3)
    db.add(board)
    db.flush()
    for index in range(board.total_tiles):
        db.add(
            StampTile(board_id=board.id, board_version=board.version, tile_index=index)
        )

    db.flush()
    return festival
