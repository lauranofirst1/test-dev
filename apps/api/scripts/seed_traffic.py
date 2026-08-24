#!/usr/bin/env python
"""운영 대시보드를 볼 수 있게 **가짜 현장 참여**를 만든다.

    cd apps/api
    ./.venv/bin/python scripts/seed_traffic.py 5              # 편중된 현장
    ./.venv/bin/python scripts/seed_traffic.py 5 --even       # 균형 잡힌 현장

편중 시나리오는 부스 수에 맞춰 "한 곳에 몰리고 한 곳은 조용한" 모양을 만듭니다.
부스가 4개 이상이면 완료 0건인 부스도 하나 둬서 참여 없음 카드까지 보입니다.

축제 당일이 되기 전에는 완료 이력이 하나도 없어 대시보드가 늘 "데이터 부족"
입니다. 판정과 추천 카드가 어떻게 보이는지는 그 상태에서 확인할 수 없습니다.

만드는 것은 참여자와 완료 참여뿐입니다. 조각 공개나 경품 뽑기는 건드리지
않습니다 — 지표만 보려고 남의 보드 진행을 바꿔 놓으면 안 됩니다.

부스에 활성 미션이 있으면 그중 하나를 골라 붙입니다. 안 붙이면 사후 리포트의
"참여 발생 미션" 이 0 으로 나오고 미션별 성과 표가 통째로 빕니다 — 실제 지급은
언제나 미션을 통해 일어나므로, 그 상태는 현장에서 나올 수 없는 모양입니다.

되돌리려면 `scripts/reset_participation.py {id} --yes` 를 쓰세요.

🚨 리허설·데모 전용입니다. 실제 축제 DB 에 돌리면 집계가 오염됩니다.
"""

from __future__ import annotations

import random
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.db.session import engine
from festaflow.models import Booth, Festival, Mission, Participant, Participation
from festaflow.models.enums import ParticipationStatus

#: 편중 시나리오에서 최상위 부스가 가져갈 비율. 40% 를 넘겨야 HIGH 판정이 뜬다.
TOP_SHARE = 0.5

#: 분산 확인 요청 카드가 뜨려면 15% 이하인 활성 부스가 있어야 한다.
QUIET_SHARE = 0.07

#: 이 정도는 만들어야 판정이 켜진다(최근 30분 10건 이상).
TOTAL = 80


def weights_for(booth_count: int, *, even: bool) -> list[int]:
    """부스 수에 맞춰 가중치를 만든다.

    고정 목록을 쓰면 부스가 8개인 축제에서만 시연이 되고, 3개인 축제에서는
    "가장 조용한 부스"가 16% 여서 추천 카드가 아예 안 뜬다. 시연용 스크립트가
    특정 부스 수에서만 시연되면 그건 시연이 아니다.
    """
    if booth_count == 0:
        return []
    if even:
        base = TOTAL // booth_count
        out = [base] * booth_count
        out[0] += TOTAL - base * booth_count
        return out

    # 최상위 하나가 몰리고, 하나는 확실히 조용하고, 부스가 넉넉하면 하나는 0 건이다.
    # 0 건인 부스가 있어야 "참여 없음" 카드까지 볼 수 있다.
    out = [round(TOTAL * TOP_SHARE), round(TOTAL * QUIET_SHARE)]
    if booth_count >= 4:
        out.append(0)
    rest = booth_count - len(out)
    if rest > 0:
        remaining = TOTAL - sum(out)
        each = max(1, remaining // rest)
        out.extend([each] * rest)
    return out[:booth_count]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    festival_id = int(sys.argv[1])
    even = "--even" in sys.argv
    now = datetime.now(UTC)
    rng = random.Random(festival_id)

    with Session(engine) as db:
        festival = db.get(Festival, festival_id)
        if festival is None:
            print(f"축제 {festival_id} 을(를) 찾을 수 없습니다.")
            return 1

        booths = list(
            db.execute(
                select(Booth)
                .where(Booth.festival_id == festival_id, Booth.archived_at.is_(None))
                .order_by(Booth.id)
            ).scalars()
        )
        if not booths:
            print("부스가 없습니다. 먼저 부스를 등록하세요.")
            return 1

        weights = weights_for(len(booths), even=even)

        missions = {
            b.id: list(
                db.execute(
                    select(Mission).where(
                        Mission.booth_id == b.id,
                        Mission.archived_at.is_(None),
                        Mission.is_active.is_(True),
                    )
                ).scalars()
            )
            for b in booths
        }

        made = 0
        for booth, weight in zip(booths, weights, strict=False):
            choices = missions.get(booth.id) or [None]
            for _ in range(weight):
                # 최근 30분 안에 흩어 놓는다. 전부 같은 시각이면 10·30·60분
                # 창이 전부 같은 값이 되어 세 창을 나눈 의미가 사라진다.
                minutes = rng.randint(0, 55)
                at = now - timedelta(minutes=minutes, seconds=rng.randint(0, 59))
                p = Participant(
                    festival_id=festival_id,
                    code=f"FF-{rng.randint(0, 99999999):08d}",
                    secret_hash="seed",
                )
                db.add(p)
                db.flush()
                mission = rng.choice(choices)
                db.add(
                    Participation(
                        festival_id=festival_id,
                        participant_id=p.id,
                        booth_id=booth.id,
                        mission_id=mission.id if mission else None,
                        status=ParticipationStatus.COMPLETED,
                        completed_at=at,
                        base_points=mission.points if mission else 0,
                    )
                )
                made += 1
        without_mission = sum(1 for b in booths if not missions.get(b.id))
        db.commit()

    if without_mission:
        print(f"⚠ 활성 미션이 없는 부스 {without_mission}개는 미션 없이 기록했습니다.")
    print(f"축제 {festival_id}: 완료 참여 {made}건을 만들었습니다.")
    print(f"→ http://localhost:5173/festivals/{festival_id}/dashboard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
