"""채점표 로딩과 점수 공개 판정.

배점을 코드가 아니라 config/rubrics/*.json 에 둡니다.
하드코딩하면 배점을 바꾸는 순간 과거 진단의 근거를 재현할 수 없습니다.

점수 공개는 **백테스트를 통과한 채점표에만** 허용됩니다.
근거 없는 78.5점보다 근거 있는 체크리스트가 낫기 때문입니다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core.config import settings
from festaflow.models import RubricCalibration
from festaflow.models.enums import RiskLevel

RUBRIC_DIR = Path(__file__).resolve().parents[3] / "config" / "rubrics"

#: 점수를 공개하려면 이 표본 수 이상의 백테스트 기록이 필요하다.
MIN_CALIBRATION_SAMPLE = 10

DEFAULT_VERSION = "v1"


@lru_cache
def load(version: str = DEFAULT_VERSION) -> dict[str, Any]:
    path = RUBRIC_DIR / f"{version}.json"
    if not path.is_file():
        raise FileNotFoundError(f"채점표 {version} 을 찾을 수 없습니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def max_score(version: str, category: str) -> float:
    return float(load(version)["max_scores"][category])


def total_max(version: str = DEFAULT_VERSION) -> float:
    return float(sum(load(version)["max_scores"].values()))


def risk_for_total(total: float, version: str = DEFAULT_VERSION) -> RiskLevel:
    th = load(version)["risk_thresholds"]
    if total >= th["stable"]:
        return RiskLevel.STABLE
    if total >= th["caution"]:
        return RiskLevel.CAUTION
    return RiskLevel.RISK


def level_for_item(score: float, maximum: float, version: str = DEFAULT_VERSION) -> RiskLevel:
    """항목 수준은 **배점 대비 비율**로 판단한다. 절대 점수가 아니다."""
    ratio = (score / maximum) if maximum else 0.0
    th = load(version)["item_ratio"]
    if ratio >= th["stable"]:
        return RiskLevel.STABLE
    if ratio >= th["caution"]:
        return RiskLevel.CAUTION
    return RiskLevel.RISK


def is_score_disclosed(db: Session, version: str) -> bool:
    """이 채점표로 계산한 점수를 화면에 보여도 되는가.

    검증 기록이 없으면 체크리스트 모드로 표시합니다.
    점수는 계산·저장되며 **표시만** 감춥니다.

    DIAGNOSIS_SCORE_MODE 로 강제할 수 있습니다.
    공모전 출품 버전은 `score` 로 켜되, 화면에 채점표의 한계를 함께 표시해야 합니다
    (docs/08-contest-submission.md §2.4.1).
    """
    mode = settings.diagnosis_score_mode.lower()
    if mode == "score":
        return True
    if mode == "checklist":
        return False

    row = db.execute(
        select(RubricCalibration).where(RubricCalibration.rubric_version == version)
    ).scalar_one_or_none()
    return bool(row and row.sample_size >= MIN_CALIBRATION_SAMPLE)


#: 체크리스트 모드에서 RiskLevel 을 이 값으로 매핑해 표시한다.
FULFILLMENT = {
    RiskLevel.STABLE: "met",
    RiskLevel.CAUTION: "partial",
    RiskLevel.RISK: "unmet",
}
