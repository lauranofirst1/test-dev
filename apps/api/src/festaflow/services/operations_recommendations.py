"""운영 추천 — 지금 검토할 행동. 계약 §5, 기획서 7.1.

**추천은 지시가 아니라 확인 요청입니다.** QR 참여자는 방문객의 일부이고 적극적
참여자에 편향된 표본입니다. 그 데이터로 "이렇게 하세요" 라고 지시하면, 문구로만
제한을 밝히고 행동은 시키는 구조가 됩니다. 그래서 모든 문장이 "현장이 실제로
그런지 확인해 주세요" 로 끝납니다.

**AI 를 쓰지 않습니다.** 여기 있는 상수와 규칙이 전부이며, 그래서 왜 이 추천이
나왔는지를 언제나 그대로 설명할 수 있습니다.
"""

from __future__ import annotations

from dataclasses import dataclass

from festaflow.models.enums import BoothLoadStatus, RecommendationType
from festaflow.services.operations_insights import (
    HIGH_SHARE,
    PRIMARY_WINDOW,
    BoothLoad,
    Insights,
)

#: 분산 대상으로 볼 비율 상한. 집중 부스가 있어도 나머지가 고르면 추천하지 않는다.
QUIET_SHARE = 0.15

#: 무참여 추천을 낼 최소 표본. 편중 판정(10건)보다 높게 잡는다 —
#: "30분간 0건" 이 이상하려면 축제 자체가 돌아가고 있어야 한다.
NO_ACTIVITY_MIN_TOTAL = 20


@dataclass
class Recommendation:
    type: RecommendationType
    situation: str
    evidence: str
    action: str
    target_booth_id: int | None


def _active(load: BoothLoad) -> bool:
    """비활성 부스는 집중 출발점에서도, 분산·무참여 대상에서도 뺀다."""
    return load.booth.is_active and load.booth.archived_at is None


def build(insights: Insights) -> list[Recommendation]:
    if not insights.enough_data:
        # 표본이 적으면 추천하지 않는다. 3건 중 2건으로 "67% 집중" 이라 말하면
        # 그 숫자가 근거처럼 보인다.
        return []

    total = insights.completions_last_30m
    active = [b for b in insights.booths if _active(b)]
    if not active:
        return []

    out: list[Recommendation] = []

    # ── 무참여: 축제는 도는데 이 부스만 0건 ──
    #
    # 분산보다 **먼저** 고른다. 완료가 0건인 부스는 "한산한 부스"로도 잡히는데,
    # 두 카드가 같은 부스에 대해 다른 말을 하면 현장에서 어느 쪽을 믿을지 알 수
    # 없다. QR 이 안 보이는 것이라면 사람을 더 보내도 완료는 그대로 0건이므로,
    # 더 구체적인 쪽인 무참여가 이긴다.
    silent: set[int] = set()
    if total >= NO_ACTIVITY_MIN_TOTAL:
        for b in active:
            if b.recent.get(PRIMARY_WINDOW, 0) == 0:
                silent.add(b.booth.id)
                out.append(
                    Recommendation(
                        type=RecommendationType.NO_ACTIVITY,
                        situation=(
                            f"{b.booth.name}에서 최근 {PRIMARY_WINDOW}분간 완료가 없습니다."
                        ),
                        evidence=f"같은 시간 축제 전체는 {total}건이 완료됐습니다.",
                        action=(
                            "QR 이 잘 보이는 자리에 있는지 확인해 주세요. "
                            "인쇄물이 떨어졌거나 화면이 꺼져 있을 수 있습니다."
                        ),
                        target_booth_id=b.booth.id,
                    )
                )

    # ── 편중: 한 부스가 40% 이상이고 다른 부스가 15% 이하 ──
    #
    # 한산한 부스가 다섯이라도 카드는 **하나만** 만든다. 같은 상황을 설명하는
    # 카드 다섯 장이 한꺼번에 뜨면 운영자는 다섯 개를 다 처리하지 못하고,
    # 처리 못 할 카드가 쌓이면 다음부터 카드를 읽지 않는다.
    #
    # 대신 한산한 부스를 카드 하나에 **전부 적는다.** 조용히 잘라내면 안 적힌
    # 부스는 아무도 확인하러 가지 않는다.
    crowded = [b for b in active if b.share_last_30m >= HIGH_SHARE]
    quiet = [b for b in active if b.share_last_30m <= QUIET_SHARE and b.booth.id not in silent]
    if crowded and quiet:
        top = max(crowded, key=lambda b: b.share_last_30m)
        ranked = sorted(quiet, key=lambda b: b.share_last_30m)
        listed = ", ".join(
            f"{b.booth.name}({round(b.share_last_30m * 100)}%, "
            f"{b.recent.get(PRIMARY_WINDOW, 0)}건)"
            for b in ranked
        )
        target = ranked[0]
        out.append(
            Recommendation(
                type=RecommendationType.REDISTRIBUTE,
                situation=(
                    f"{top.booth.name}에 최근 {PRIMARY_WINDOW}분 참여의 "
                    f"{round(top.share_last_30m * 100)}%가 몰렸습니다."
                ),
                # 조사를 붙이지 않는 문장 구조를 고른다. 부스 이름은 운영자가
                # 쓰는 자유 텍스트라 "부스 5은" 처럼 받침 판정이 틀어지는 이름이
                # 반드시 섞이고, 나열 뒤에 조사를 붙이면 매번 마지막 항목에
                # 걸린다.
                evidence=(
                    f"같은 시간 {round(QUIET_SHARE * 100)}% 이하에 머문 부스 — {listed}"
                ),
                # 지시가 아니라 확인 요청이다.
                action=(
                    f"{target.booth.name} 현장이 실제로 한산한지 확인해 주세요. "
                    "맞다면 한시 추가 보상을 검토할 수 있습니다."
                ),
                target_booth_id=target.booth.id,
            )
        )

    # HIGH → CAUTION 순. 같은 종류 안에서는 더 조용한 쪽을 먼저 본다.
    order = {RecommendationType.REDISTRIBUTE: 0, RecommendationType.NO_ACTIVITY: 1}
    out.sort(key=lambda r: order[r.type])
    return out


#: 판정 근거를 화면이 다시 계산하지 않게 서버가 함께 내려주는 값.
STATUS_LABEL = {
    BoothLoadStatus.INSUFFICIENT_DATA: "데이터 부족",
    BoothLoadStatus.LOW: "여유",
    BoothLoadStatus.CAUTION: "주의",
    BoothLoadStatus.HIGH: "집중",
}


def status_label(load: BoothLoad, *, enough: bool) -> str:
    """화면에 띄울 상태 이름.

    **0건인 부스를 "여유" 라고 부르지 않습니다.** 편중 판정으로는 LOW 가 맞지만
    (25% 미만), 운영자는 "여유" 를 보고 "괜찮구나" 로 읽고 지나갑니다. 그 부스는
    한산한 게 아니라 QR 이 안 보이거나 인쇄물이 떨어졌을 수 있고, 바로 위 추천
    카드는 그걸 확인해 달라고 말하고 있습니다. 한 화면이 서로 다른 말을 하면
    둘 다 신뢰를 잃습니다.

    상태 enum 자체는 계약대로 LOW 로 둡니다 — 라벨은 사람이 읽는 말이고,
    enum 은 계약이 정한 값입니다.
    """
    if enough and load.recent.get(PRIMARY_WINDOW, 0) == 0:
        return "참여 없음"
    return STATUS_LABEL[load.status]
