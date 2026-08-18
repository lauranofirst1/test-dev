#!/usr/bin/env python
"""축제의 **현장 참여 데이터만** 지운다. 기획·부스·미션·보드는 그대로 둔다.

    cd apps/api
    ./.venv/bin/python scripts/reset_participation.py 4         # 무엇이 지워질지 보기만
    ./.venv/bin/python scripts/reset_participation.py 4 --yes   # 실제로 지우기

리허설을 반복하면 참여자와 지급 이력이 계속 쌓입니다. 데모를 다시 처음부터
보여주려면 그것만 비워야 하는데, 축제를 지우면 부스·미션·보드를 다시 만들어야 하고
부스를 보관하면 미션 배정과 타일 배정이 풀립니다. 그래서 참여 쪽만 따로 지웁니다.

지우는 것: participants, participations, stamp_reveals, booth_scan_uses
남기는 것: festivals, festival_plans, booths, missions, stamp_boards, stamp_tiles,
          diagnoses, reward_campaigns

participants 하나만 지우면 나머지는 FK 의 ON DELETE CASCADE 로 따라 지워집니다.
ORM 객체를 순회하며 지우지 않고 DELETE 문을 그대로 보내는 이유가 그것입니다 —
애플리케이션이 순서를 직접 관리하면 한 곳만 빠뜨려도 고아 행이 남습니다.

🚨 되돌릴 수 없습니다. `--yes` 없이는 세어만 봅니다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import delete, func, select  # noqa: E402

from festaflow.db.session import SessionLocal  # noqa: E402
from festaflow.models import (  # noqa: E402
    BoothScanUse,
    Festival,
    Participant,
    Participation,
    StampReveal,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="축제의 현장 참여 데이터만 초기화")
    ap.add_argument("festival_id", type=int)
    ap.add_argument("--yes", action="store_true", help="실제로 지운다")
    args = ap.parse_args()

    with SessionLocal() as db:
        festival = db.get(Festival, args.festival_id)
        if festival is None:
            print(f"✗ 축제 {args.festival_id} 을 찾을 수 없습니다.", file=sys.stderr)
            return 1

        pids = list(
            db.execute(
                select(Participant.id).where(Participant.festival_id == festival.id)
            ).scalars()
        )

        def count(model, column) -> int:
            if not pids:
                return 0
            return db.execute(
                select(func.count(model.id)).where(column.in_(pids))
            ).scalar_one()

        counts = {
            "참여자": len(pids),
            "지급 이력": count(Participation, Participation.participant_id),
            "조각 공개": count(StampReveal, StampReveal.participant_id),
            "스캔 사용": count(BoothScanUse, BoothScanUse.participant_id),
        }

        print(f"축제 {festival.id} — {festival.name}")
        for label, n in counts.items():
            print(f"  {label:6} {n:>5}")

        if not pids:
            print("\n비울 것이 없습니다.")
            return 0

        if not args.yes:
            print("\n세어만 봤습니다. 실제로 지우려면 --yes 를 붙이세요.")
            return 0

        # participants 만 지우면 participations·stamp_reveals·booth_scan_uses 가
        # ON DELETE CASCADE 로 함께 지워진다.
        db.execute(delete(Participant).where(Participant.festival_id == festival.id))
        db.commit()

        left = db.execute(
            select(func.count(Participant.id)).where(Participant.festival_id == festival.id)
        ).scalar_one()
        orphan = db.execute(
            select(func.count(Participation.id)).where(
                Participation.festival_id == festival.id
            )
        ).scalar_one()
        print(f"\n✓ 지웠습니다. 남은 참여자 {left}명, 남은 지급 이력 {orphan}건")
        return 0 if (left == 0 and orphan == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
