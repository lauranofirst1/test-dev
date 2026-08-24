#!/usr/bin/env python
"""축제의 **현장 참여 데이터만** 지운다. 기획·부스·미션·보드는 그대로 둔다.

    cd apps/api
    ./.venv/bin/python scripts/reset_participation.py 4         # 무엇이 지워질지 보기만
    ./.venv/bin/python scripts/reset_participation.py 4 --yes   # 실제로 지우기

리허설을 반복하면 참여자와 지급 이력이 계속 쌓입니다. 데모를 다시 처음부터
보여주려면 그것만 비워야 하는데, 축제를 지우면 부스·미션·보드를 다시 만들어야 하고
부스를 보관하면 미션 배정과 타일 배정이 풀립니다. 그래서 참여 쪽만 따로 지웁니다.

지우는 것: participants, participations, stamp_reveals, booth_scan_uses,
          mission_attempts, prize_draws
남기는 것: festivals, festival_plans, booths, missions, stamp_boards, stamp_tiles,
          diagnoses, reward_campaigns, prizes

**경품 재고는 자동으로 되돌리지 않습니다.** 뽑기 기록은 참여 데이터지만 재고는
운영자가 정한 설정이라, 지우는 김에 건드리면 리허설 뒤에 실제 재고를 덮어씁니다.
리허설로 줄어든 재고를 되돌리려면 `--restore-stock` 을 붙이세요 — 이 축제의
뽑기 기록에서 상품별로 몇 개가 나갔는지 세어 그만큼만 더합니다.

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
    MissionAttempt,
    Participant,
    Participation,
    Prize,
    PrizeDraw,
    StampReveal,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="축제의 현장 참여 데이터만 초기화")
    ap.add_argument("festival_id", type=int)
    ap.add_argument("--yes", action="store_true", help="실제로 지운다")
    ap.add_argument(
        "--restore-stock",
        action="store_true",
        help="리허설 뽑기로 줄어든 경품 재고를 그만큼 되돌린다",
    )
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
            "체험 시도": count(MissionAttempt, MissionAttempt.participant_id),
            "뽑기": count(PrizeDraw, PrizeDraw.participant_id),
        }

        # 상품별로 몇 개가 나갔는지. 되돌릴 때도, 세어만 볼 때도 같은 수를 쓴다.
        drawn = dict(
            db.execute(
                select(PrizeDraw.prize_id, func.count(PrizeDraw.id))
                .where(
                    PrizeDraw.festival_id == festival.id,
                    PrizeDraw.prize_id.is_not(None),
                )
                .group_by(PrizeDraw.prize_id)
            ).all()
        )

        print(f"축제 {festival.id} — {festival.name}")
        for label, n in counts.items():
            print(f"  {label:6} {n:>5}")

        if drawn:
            print("\n  뽑기로 나간 경품")
            for prize_id, n in drawn.items():
                prize = db.get(Prize, prize_id)
                stock = "무제한" if prize is None or prize.stock is None else prize.stock
                name = prize.name if prize else f"(삭제된 상품 {prize_id})"
                print(f"    {name} {n}개 (현재 재고 {stock})")
            if not args.restore_stock:
                print("    → 재고는 그대로 둡니다. 되돌리려면 --restore-stock")

        if not pids:
            print("\n비울 것이 없습니다.")
            return 0

        if not args.yes:
            print("\n세어만 봤습니다. 실제로 지우려면 --yes 를 붙이세요.")
            return 0

        # 재고는 뽑기 기록이 지워지기 **전에** 되돌린다. 지운 뒤에는 몇 개가
        # 나갔는지 알 방법이 없다.
        if args.restore_stock and drawn:
            for prize_id, n in drawn.items():
                prize = db.get(Prize, prize_id)
                if prize is None or prize.stock is None:
                    continue  # 삭제됐거나 무제한이면 되돌릴 것이 없다
                prize.stock += n
                print(f"  ↩ {prize.name} 재고 +{n} → {prize.stock}")

        # participants 만 지우면 participations·stamp_reveals·booth_scan_uses·
        # mission_attempts·prize_draws 가 ON DELETE CASCADE 로 함께 지워진다.
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
