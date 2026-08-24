"""설문 체험 — 개인정보를 받지 않는 유일한 방법.

설계 05 §6 은 사진과 설문을 함께 묶어 "개인정보를 다루므로 별도 처리가 필요"
하다고 했지만, 같은 절이 설문에 대해서만 이렇게 못박습니다 —
**"설문 응답은 참여 코드와만 연결되며 별도 신원 정보를 수집하지 않습니다."**

그 약속을 지키는 방법은 하나입니다. **자유 서술을 만들지 않는 것.** 자유 입력을
열면 사람들이 이름·연락처·민원을 적고, 그 순간 수집 범위가 완전히 달라집니다.
"""

from __future__ import annotations

import pytest

from festaflow.core.errors import ApiError
from festaflow.models import Mission
from festaflow.models.enums import ExperienceType
from festaflow.services import experience as exp


def _mission(config: dict) -> Mission:
    return Mission(
        festival_id=1,
        booth_id=1,
        title="설문",
        points=100,
        experience_type=ExperienceType.SURVEY,
        experience_config=config,
    )


VALID = {
    "questions": [
        {"type": "rating", "text": "부스 만족도", "scale": 5},
        {"type": "choice", "text": "어떻게 알고 오셨나요?", "choices": ["SNS", "현수막", "지인"]},
    ]
}


# ── 설정 ────────────────────────────────────────────────────────────────────


def test_설문을_저장할_수_있다() -> None:
    """사진과 함께 막혀 있었지만 설문은 개인정보 제약에 걸리지 않는다."""
    out = exp.validate_config(ExperienceType.SURVEY, VALID)

    assert len(out["questions"]) == 2
    assert out["questions"][0] == {"type": "rating", "text": "부스 만족도", "scale": 5}


def test_자유_서술은_거부한다() -> None:
    """자유 입력을 열면 사람들이 이름·연락처·민원을 적는다."""
    with pytest.raises(ApiError) as exc:
        exp.validate_config(
            ExperienceType.SURVEY,
            {"questions": [{"type": "text", "text": "하고 싶은 말씀"}]},
        )

    assert exc.value.status_code == 422
    assert "자유 서술" in exc.value.detail["error"]["message"]


def test_사진은_여전히_막혀_있다() -> None:
    """원본 저장소·동의 기록·삭제 경로·보관 배치가 없고 법률 검토가 선행돼야 한다."""
    with pytest.raises(ApiError) as exc:
        exp.validate_config(ExperienceType.PHOTO, {"guide_text": "찍어주세요"})

    assert exc.value.detail["error"]["code"] == "EXPERIENCE_TYPE_UNSUPPORTED"


def test_문항이_너무_많으면_거부한다() -> None:
    """부스 앞에 서서 답하는 설문이라 길면 아무도 끝내지 않는다."""
    many = {"questions": [{"type": "rating", "text": f"{i}", "scale": 5} for i in range(6)]}

    with pytest.raises(ApiError):
        exp.validate_config(ExperienceType.SURVEY, many)


def test_척도_범위를_지킨다() -> None:
    """7 을 넘으면 사람이 구간을 구분하지 못해 답이 가운데로 몰린다."""
    for scale in (1, 8):
        with pytest.raises(ApiError):
            exp.validate_config(
                ExperienceType.SURVEY,
                {"questions": [{"type": "rating", "text": "만족도", "scale": scale}]},
            )


def test_빈_설문은_거부한다() -> None:
    with pytest.raises(ApiError):
        exp.validate_config(ExperienceType.SURVEY, {"questions": []})


# ── 참여자에게 내려가는 것 ──────────────────────────────────────────────────


def test_설문에는_감출_것이_없다() -> None:
    """정답이 없으므로 설정 전체가 문항이다. 퀴즈와 다른 점이다."""
    public = exp.public_config(_mission(VALID))

    assert public["questions"] == VALID["questions"]


# ── 제출 ────────────────────────────────────────────────────────────────────


def test_모든_문항에_답해야_완료된다() -> None:
    """빈 응답으로 완료를 받아가면 설문 결과가 허수로 채워지고,
    그 숫자가 사후 리포트의 정성 지표로 실린다."""
    with pytest.raises(ApiError) as exc:
        exp.grade(_mission(VALID), {"answers": [5]})

    assert exc.value.detail["error"]["code"] == "EXPERIENCE_INVALID_RESPONSE"


def test_정상_제출() -> None:
    graded = exp.grade(_mission(VALID), {"answers": [4, 1]})

    assert graded.response == {"answers": [4, 1]}


def test_평점은_1부터_센다() -> None:
    """0 을 허용하면 "안 골랐음" 과 구분되지 않는다."""
    with pytest.raises(ApiError):
        exp.grade(_mission(VALID), {"answers": [0, 1]})
    with pytest.raises(ApiError):
        exp.grade(_mission(VALID), {"answers": [6, 1]})


def test_선택지_범위를_벗어나면_거부한다() -> None:
    with pytest.raises(ApiError):
        exp.grade(_mission(VALID), {"answers": [3, 9]})


def test_틀린_답이_없다() -> None:
    """채점하지 않는다. 어떤 값을 골라도 범위 안이면 완료다."""
    for rating in range(1, 6):
        assert exp.grade(_mission(VALID), {"answers": [rating, 0]}).response is not None
