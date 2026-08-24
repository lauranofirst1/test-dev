"""부스 QR 체험 — 설정 검증과 채점. docs/05-booth-experience.md, 계약 §11.

**채점은 여기서만 합니다.** `quiz` 의 `answer_index` 는 참여자 응답에 절대
내려가지 않습니다. 그래서 이 모듈은 두 개의 얼굴을 가집니다.

- `public_config()` — 참여자에게 내려도 되는 것만 남긴 설정
- `grade()` — 서버에서만 도는 채점

정답을 화면으로 내리고 클라이언트가 맞히면, 집에서 개발자 도구를 여는 것으로
축제 전체를 통과할 수 있습니다. 부스 QR 토큰이 현장 방문을 보장하더라도
퀴즈의 의미는 그때 사라집니다.

**설정은 저장할 때 검증합니다.** 현장에서 참여자가 깨진 문항을 만나면 그때는
고칠 수 없습니다. 운영자가 저장을 누르는 순간이 마지막 기회입니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from festaflow.core.config import settings
from festaflow.core.errors import ApiError, validation_failed
from festaflow.core.security import DEFAULT_ACCEPTED_WINDOWS
from festaflow.models import Mission, MissionAttempt
from festaflow.models.enums import ExperienceType

#: 퀴즈 기본 시도 횟수. 설정에 없으면 이 값을 쓴다.
DEFAULT_MAX_ATTEMPTS = 3

#: 체험이 붙은 부스가 인정받는 window 수(30초 × N).
#:
#: 기본값 2 는 도착 확인용이라 실질 30~60초다. 퀴즈는 그 안에 끝나지 않는다 —
#: 문제를 읽고, 보기를 고르고, 틀리면 힌트를 보고 다시 푼다. 3번 시도를 허용해
#: 놓고 예산을 60초로 두면 설정과 현실이 어긋나고, 참여자는 "정답을 아는데
#: 만료됐다"는 상태에 갇힌다.
#:
#: 5 면 2분~2분 30초다. 늘어난 뒤에도 분 단위라 "QR 사진을 찍어 현장 밖에서
#: 쓴다"를 막는다는 성질은 그대로다.
EXPERIENCE_ACCEPTED_WINDOWS = 5
MAX_ATTEMPTS_LIMIT = 10
MAX_CHOICES = 6
MAX_DWELL_SECONDS = 120

#: 설문 문항 수 상한. 부스 앞에 서서 답하는 것이라 길면 아무도 끝내지 않고,
#: 중간에 그만두면 참여 자체가 완료되지 않는다.
MAX_SURVEY_QUESTIONS = 5
#: 평점 척도 상한. 7 을 넘으면 사람이 구간을 구분하지 못해 답이 가운데로 몰린다.
MAX_RATING_SCALE = 7


# ── 설정 검증 (운영자가 저장할 때) ──────────────────────────────────────────


def _require_text(config: dict, key: str, *, label: str, limit: int) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise validation_failed(f"{label}을(를) 입력해 주세요.", key)
    if len(value) > limit:
        raise validation_failed(f"{label}은(는) {limit}자를 넘을 수 없습니다.", key)
    return value.strip()


def _validate_quiz(config: dict) -> dict:
    question = _require_text(config, "question", label="문제", limit=500)

    choices = config.get("choices")
    if not isinstance(choices, list) or len(choices) < 2:
        raise validation_failed("보기를 2개 이상 입력해 주세요.", "choices")
    if len(choices) > MAX_CHOICES:
        raise validation_failed(f"보기는 최대 {MAX_CHOICES}개입니다.", "choices")
    cleaned: list[str] = []
    for i, c in enumerate(choices):
        if not isinstance(c, str) or not c.strip():
            raise validation_failed(f"{i + 1}번 보기가 비어 있습니다.", "choices")
        if len(c) > 200:
            raise validation_failed(f"{i + 1}번 보기가 200자를 넘습니다.", "choices")
        cleaned.append(c.strip())

    answer_index = config.get("answer_index")
    if not isinstance(answer_index, int) or isinstance(answer_index, bool):
        raise validation_failed("정답을 골라 주세요.", "answer_index")
    if not 0 <= answer_index < len(cleaned):
        raise validation_failed(
            f"정답 번호가 보기 범위를 벗어났습니다(보기 {len(cleaned)}개).", "answer_index"
        )

    max_attempts = config.get("max_attempts", DEFAULT_MAX_ATTEMPTS)
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool):
        raise validation_failed("시도 횟수는 숫자여야 합니다.", "max_attempts")
    if not 1 <= max_attempts <= MAX_ATTEMPTS_LIMIT:
        raise validation_failed(
            f"시도 횟수는 1~{MAX_ATTEMPTS_LIMIT} 사이여야 합니다.", "max_attempts"
        )

    hint = config.get("hint")
    if hint is not None and (not isinstance(hint, str) or len(hint) > 300):
        raise validation_failed("힌트는 300자를 넘을 수 없습니다.", "hint")

    explanation = config.get("explanation")
    if explanation is not None and (not isinstance(explanation, str) or len(explanation) > 1000):
        raise validation_failed("해설은 1000자를 넘을 수 없습니다.", "explanation")

    out = {
        "question": question,
        "choices": cleaned,
        "answer_index": answer_index,
        "max_attempts": max_attempts,
    }
    if hint and hint.strip():
        out["hint"] = hint.strip()
    if explanation and explanation.strip():
        out["explanation"] = explanation.strip()
    return out


def _validate_info(config: dict) -> dict:
    body = _require_text(config, "body", label="안내 내용", limit=2000)

    links_raw = config.get("links", [])
    if not isinstance(links_raw, list):
        raise validation_failed("링크 목록의 형식이 올바르지 않습니다.", "links")
    if len(links_raw) > 5:
        raise validation_failed("링크는 최대 5개입니다.", "links")
    links: list[dict] = []
    for i, link in enumerate(links_raw):
        if not isinstance(link, dict):
            raise validation_failed(f"{i + 1}번 링크의 형식이 올바르지 않습니다.", "links")
        label = link.get("label")
        url = link.get("url")
        if not isinstance(label, str) or not label.strip():
            raise validation_failed(f"{i + 1}번 링크의 이름이 비어 있습니다.", "links")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise validation_failed(
                f"{i + 1}번 링크 주소는 http:// 또는 https:// 로 시작해야 합니다.", "links"
            )
        links.append({"label": label.strip()[:60], "url": url.strip()})

    dwell = config.get("min_dwell_seconds", 0)
    if not isinstance(dwell, int) or isinstance(dwell, bool):
        raise validation_failed("최소 열람 시간은 숫자여야 합니다.", "min_dwell_seconds")
    if not 0 <= dwell <= MAX_DWELL_SECONDS:
        raise validation_failed(
            f"최소 열람 시간은 0~{MAX_DWELL_SECONDS}초 사이여야 합니다.", "min_dwell_seconds"
        )

    return {"body": body, "links": links, "min_dwell_seconds": dwell}


def _validate_survey(config: dict) -> dict:
    """설문 설정.

    **개인정보를 받지 않습니다.** 문항은 평점과 선택지뿐이고 자유 서술이 없습니다 —
    자유 입력을 열면 사람들이 이름·연락처·민원을 적고, 그 순간 이 기능의 수집
    범위가 완전히 달라집니다(설계 05 §6: "설문 응답은 참여 코드와만 연결되며
    별도 신원 정보를 수집하지 않습니다").
    """
    questions_raw = config.get("questions")
    if not isinstance(questions_raw, list) or not questions_raw:
        raise validation_failed("설문 문항을 1개 이상 만들어 주세요.", "questions")
    if len(questions_raw) > MAX_SURVEY_QUESTIONS:
        raise validation_failed(
            f"문항은 최대 {MAX_SURVEY_QUESTIONS}개입니다. 부스 앞에 서서 답하는 "
            "설문이라 길면 아무도 끝내지 않습니다.",
            "questions",
        )

    questions: list[dict] = []
    for i, q in enumerate(questions_raw):
        where = f"{i + 1}번 문항"
        if not isinstance(q, dict):
            raise validation_failed(f"{where}의 형식이 올바르지 않습니다.", "questions")

        text = q.get("text")
        if not isinstance(text, str) or not text.strip():
            raise validation_failed(f"{where}의 질문이 비어 있습니다.", "questions")
        if len(text) > 200:
            raise validation_failed(f"{where}의 질문이 200자를 넘습니다.", "questions")

        kind = q.get("type")
        if kind == "rating":
            scale = q.get("scale", 5)
            if not isinstance(scale, int) or isinstance(scale, bool):
                raise validation_failed(f"{where}의 척도는 숫자여야 합니다.", "questions")
            if not 2 <= scale <= MAX_RATING_SCALE:
                raise validation_failed(
                    f"{where}의 척도는 2~{MAX_RATING_SCALE} 사이여야 합니다.", "questions"
                )
            questions.append({"type": "rating", "text": text.strip(), "scale": scale})
        elif kind == "choice":
            choices = q.get("choices")
            if not isinstance(choices, list) or len(choices) < 2:
                raise validation_failed(f"{where}의 보기를 2개 이상 넣어 주세요.", "questions")
            if len(choices) > MAX_CHOICES:
                raise validation_failed(
                    f"{where}의 보기는 최대 {MAX_CHOICES}개입니다.", "questions"
                )
            cleaned = []
            for j, c in enumerate(choices):
                if not isinstance(c, str) or not c.strip():
                    raise validation_failed(
                        f"{where}의 {j + 1}번 보기가 비어 있습니다.", "questions"
                    )
                cleaned.append(c.strip()[:100])
            questions.append({"type": "choice", "text": text.strip(), "choices": cleaned})
        else:
            # 자유 서술을 막는 자리다. 유형을 열거로 두지 않으면 나중에
            # `"type": "text"` 가 조용히 들어온다.
            raise validation_failed(
                f"{where}의 유형은 평점(rating) 또는 선택(choice)이어야 합니다. "
                "자유 서술은 개인정보가 섞일 수 있어 지원하지 않습니다.",
                "questions",
            )

    return {"questions": questions}


def _grade_survey(mission: Mission, payload: dict) -> Graded:
    """설문 제출. **채점하지 않습니다** — 틀린 답이 없습니다.

    모든 문항에 답했는지만 봅니다. 빈 응답으로 완료를 받아가면 설문 결과가
    허수로 채워지고, 그 숫자가 사후 리포트의 정성 지표로 실립니다.
    """
    questions = (mission.experience_config or {}).get("questions", [])
    answers = payload.get("answers")
    if not isinstance(answers, list) or len(answers) != len(questions):
        raise ApiError(
            422,
            "EXPERIENCE_INVALID_RESPONSE",
            f"{len(questions)}개 문항에 모두 답해 주세요.",
            {"expected": len(questions)},
        )

    cleaned: list[int] = []
    for i, (q, a) in enumerate(zip(questions, answers, strict=False)):
        if not isinstance(a, int) or isinstance(a, bool):
            raise ApiError(
                422,
                "EXPERIENCE_INVALID_RESPONSE",
                f"{i + 1}번 문항에 답해 주세요.",
                {"question_index": i},
            )
        if q.get("type") == "rating":
            upper = q.get("scale", 5)
            # 평점은 1부터 센다. 0 을 허용하면 "안 골랐음" 과 구분되지 않는다.
            if not 1 <= a <= upper:
                raise ApiError(
                    422,
                    "EXPERIENCE_INVALID_RESPONSE",
                    f"{i + 1}번 문항은 1~{upper} 사이로 답해 주세요.",
                    {"question_index": i},
                )
        else:
            if not 0 <= a < len(q.get("choices", [])):
                raise ApiError(
                    422,
                    "EXPERIENCE_INVALID_RESPONSE",
                    f"{i + 1}번 문항의 보기를 골라 주세요.",
                    {"question_index": i},
                )
        cleaned.append(a)

    return Graded(response={"answers": cleaned})


#: 아직 구현하지 않은 유형. 저장은 막고, 왜 막는지 말한다.
#:
#: 사진만 남았습니다. 원본 저장소(S3), 수집·이용 동의 기록, 삭제 요청 경로,
#: 90일 보관 배치가 함께 필요하고 **법률 검토가 선행돼야 합니다**(설계 05 §6).
#: 설문은 개인정보를 받지 않으므로 그 제약에 걸리지 않아 먼저 열었습니다.
_UNSUPPORTED = {
    ExperienceType.PHOTO: "사진 체험",
}


def validate_config(experience_type: ExperienceType, config: dict) -> dict:
    """저장 직전 설정을 검증하고 **정규화된 설정을 돌려준다.**

    돌려준 값을 저장해야 합니다. 검증만 하고 원본을 저장하면 공백이 섞인 값과
    알 수 없는 키가 그대로 남고, 화면은 그것을 다시 읽습니다.
    """
    if experience_type == ExperienceType.STAMP:
        return {}
    if experience_type == ExperienceType.QUIZ:
        return _validate_quiz(config or {})
    if experience_type == ExperienceType.INFO:
        return _validate_info(config or {})
    if experience_type == ExperienceType.SURVEY:
        return _validate_survey(config or {})

    label = _UNSUPPORTED.get(experience_type)
    if label:
        raise ApiError(
            422,
            "EXPERIENCE_TYPE_UNSUPPORTED",
            f"{label}은 아직 지원하지 않습니다. 개인정보 수집·보관 정책이 정해진 뒤 열립니다.",
            {"experience_type": experience_type.value},
        )
    raise validation_failed("알 수 없는 체험 유형입니다.", "experience_type")


# ── 참여자에게 내려갈 설정 ──────────────────────────────────────────────────


def public_config(mission: Mission) -> dict:
    """참여자 화면이 받을 설정. **정답은 절대 포함하지 않는다.**

    화이트리스트로 고릅니다. 블랙리스트(`answer_index` 만 지우기)로 두면
    나중에 정답성 필드가 하나 늘 때 조용히 새어 나갑니다.
    """
    config = mission.experience_config or {}
    if mission.experience_type == ExperienceType.QUIZ:
        # `answer_index` 와 `explanation` 은 여기 없다. 해설은 정답을 설명하는
        # 글이라 사실상 정답이다 — 문제와 함께 내리면 풀 필요가 없어진다.
        out = {
            "question": config.get("question", ""),
            "choices": list(config.get("choices", [])),
            "max_attempts": config.get("max_attempts", DEFAULT_MAX_ATTEMPTS),
        }
        if config.get("hint"):
            out["hint"] = config["hint"]
        return out
    if mission.experience_type == ExperienceType.INFO:
        return {
            "body": config.get("body", ""),
            "links": list(config.get("links", [])),
            "min_dwell_seconds": config.get("min_dwell_seconds", 0),
        }
    if mission.experience_type == ExperienceType.SURVEY:
        # 설문에는 감출 것이 없다. 정답이 없으므로 설정 전체가 문항이다.
        return {"questions": list(config.get("questions", []))}
    return {}


def max_attempts_of(mission: Mission) -> int | None:
    """이 미션이 시도 횟수를 제한하는가. 제한이 없으면 None."""
    if mission.experience_type != ExperienceType.QUIZ:
        return None
    return (mission.experience_config or {}).get("max_attempts", DEFAULT_MAX_ATTEMPTS)


# ── 채점 ────────────────────────────────────────────────────────────────────


@dataclass
class Graded:
    """채점 결과. `response` 는 참여 이력에 그대로 저장된다."""

    response: dict | None = None
    #: 지급까지 걸린 시도 횟수. participations.attempt_count 로 옮겨 적힌다.
    attempt_count: int = 1
    #: 채점을 위해 시도를 하나 소비했는가(퀴즈만 true).
    consumed_attempt: bool = field(default=False)
    #: 이 응답과 함께 보여 줄 해설. 아래 규칙에 맞을 때만 채운다.
    explanation: str | None = None


def _explanation(mission: Mission) -> str | None:
    return (mission.experience_config or {}).get("explanation")


def _grade_quiz(mission: Mission, response: dict, *, attempts_used: int) -> Graded:
    config = mission.experience_config or {}
    limit = config.get("max_attempts", DEFAULT_MAX_ATTEMPTS)

    # 이미 소진했으면 채점하지 않는다 — 정답이어도 받지 않는다.
    if attempts_used >= limit:
        details = {"max_attempts": limit}
        if _explanation(mission):
            details["explanation"] = _explanation(mission)
        raise ApiError(
            429,
            "EXPERIENCE_ATTEMPTS_EXCEEDED",
            "시도 횟수를 모두 사용했습니다. 부스 스태프에게 문의해 주세요.",
            details,
        )

    choice = response.get("choice_index")
    if not isinstance(choice, int) or isinstance(choice, bool):
        raise validation_failed("보기를 골라 주세요.", "choice_index")

    attempt_no = attempts_used + 1
    if choice != config.get("answer_index"):
        left = max(0, limit - attempt_no)
        details: dict = {"attempts_left": left, "max_attempts": limit}
        # 해설은 **남은 시도가 없을 때만** 붙인다. 첫 오답에 해설을 주면 거기에
        # 정답이 적혀 있어 남은 두 번이 공짜가 되고, 시도 횟수 설정이 무의미해진다.
        # 다 쓴 사람에게는 더 이상 악용할 시도가 없으므로 알려주는 편이 낫다 —
        # 왜 틀렸는지 모른 채 부스를 떠나는 것이 이 화면의 최악이다.
        if left == 0 and _explanation(mission):
            details["explanation"] = _explanation(mission)
        raise ApiError(
            422,
            "EXPERIENCE_WRONG_ANSWER",
            (
                f"정답이 아닙니다. {left}번 더 시도할 수 있습니다."
                if left
                else "정답이 아닙니다. 시도 횟수를 모두 사용했습니다."
            ),
            details,
        )

    return Graded(
        response={"choice_index": choice, "correct": True},
        attempt_count=attempt_no,
        consumed_attempt=True,
        # 맞힌 사람에게는 언제나 보여 준다. 악용할 여지가 없고, 왜 그런지 읽는
        # 것이 부스 체험의 목적이다.
        explanation=_explanation(mission),
    )


def _grade_info(mission: Mission, response: dict, *, window_index: int | None) -> Graded:
    required = (mission.experience_config or {}).get("min_dwell_seconds", 0)
    if not required:
        return Graded(response={"dwell_seconds": response.get("dwell_seconds")})

    # 클라이언트가 보낸 체류 시간은 참고만 한다. 진실은 스캔 시각이다 —
    # 화면이 dwell_seconds: 9999 를 보내면 그대로 통과하기 때문이다.
    if window_index is None:
        raise validation_failed("스캔 정보가 없어 열람 시간을 확인할 수 없습니다.")

    window = settings.scan_token_window_seconds
    scanned_at = datetime.fromtimestamp(window_index * window, tz=UTC)
    elapsed = (datetime.now(UTC) - scanned_at).total_seconds()
    if elapsed < required:
        raise ApiError(
            422,
            "EXPERIENCE_DWELL_TOO_SHORT",
            f"안내를 {required}초 이상 읽어 주세요.",
            {"min_dwell_seconds": required, "elapsed_seconds": int(elapsed)},
        )
    return Graded(response={"dwell_seconds": int(elapsed)})


def grade(
    mission: Mission,
    response: dict | None,
    *,
    attempts_used: int = 0,
    window_index: int | None = None,
) -> Graded:
    """체험을 채점한다. 통과하지 못하면 계약 §11 의 오류로 실패한다.

    `attempts_used` 는 이 참여자가 이 미션에 지금까지 쓴 시도 횟수입니다.
    호출자가 `mission_attempts` 에서 읽어 넘깁니다 — 채점 함수가 DB 를 보지
    않아야 테스트에서 경계값을 직접 넣어볼 수 있습니다.
    """
    payload = response or {}
    if mission.experience_type == ExperienceType.STAMP:
        return Graded()
    if mission.experience_type == ExperienceType.QUIZ:
        return _grade_quiz(mission, payload, attempts_used=attempts_used)
    if mission.experience_type == ExperienceType.INFO:
        return _grade_info(mission, payload, window_index=window_index)
    if mission.experience_type == ExperienceType.SURVEY:
        return _grade_survey(mission, payload)

    label = _UNSUPPORTED.get(mission.experience_type, "이 체험")
    raise ApiError(
        422,
        "EXPERIENCE_TYPE_UNSUPPORTED",
        f"{label}은 아직 지원하지 않습니다.",
        {"experience_type": mission.experience_type.value},
    )


# ── 시도 횟수 ───────────────────────────────────────────────────────────────


def attempts_used(db: Session, *, participant_id: int, mission_id: int) -> int:
    row = db.execute(
        select(MissionAttempt.attempt_count).where(
            MissionAttempt.participant_id == participant_id,
            MissionAttempt.mission_id == mission_id,
        )
    ).scalar_one_or_none()
    return int(row or 0)


def attempts_left(db: Session, mission: Mission, participant_id: int) -> int | None:
    """화면에 "2번 더" 를 띄우기 위한 값. 제한이 없는 유형이면 None."""
    limit = max_attempts_of(mission)
    if limit is None:
        return None
    return max(0, limit - attempts_used(db, participant_id=participant_id, mission_id=mission.id))


def record_attempt(db: Session, *, participant_id: int, mission_id: int) -> int:
    """시도를 하나 올리고 누적 횟수를 돌려준다.

    **오답일 때도 반드시 커밋해야 합니다.** 실패 응답과 함께 롤백되면 시도가
    세어지지 않고, 참여자는 새로고침만으로 무한히 다시 풀 수 있습니다.
    호출자가 커밋 책임을 집니다.
    """
    row = db.execute(
        select(MissionAttempt).where(
            MissionAttempt.participant_id == participant_id,
            MissionAttempt.mission_id == mission_id,
        )
    ).scalar_one_or_none()

    if row is None:
        row = MissionAttempt(
            participant_id=participant_id, mission_id=mission_id, attempt_count=1
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            # 동시 요청이 먼저 만들었다. 그 행을 다시 읽어 올린다.
            db.expunge(row)
            row = db.execute(
                select(MissionAttempt).where(
                    MissionAttempt.participant_id == participant_id,
                    MissionAttempt.mission_id == mission_id,
                )
            ).scalar_one()
            row.attempt_count += 1
    else:
        row.attempt_count += 1

    row.last_attempt_at = datetime.now(UTC)
    db.flush()
    return row.attempt_count


def accepted_windows(missions: list[Mission]) -> int:
    """이 부스가 인정할 window 수.

    미션별이 아니라 **부스 단위**로 정한다. 미션마다 다르면 `GET /scan` 이
    카운트다운에 무엇을 실을지 정할 수 없다 — 참여자가 아직 미션을 고르기
    전이기 때문이다. 화면이 60초를 세는데 서버가 2분을 받아주면(혹은 그 반대면)
    둘 중 하나는 반드시 거짓말이 된다.
    """
    needs_time = any(
        m.experience_type in (ExperienceType.QUIZ, ExperienceType.INFO, ExperienceType.SURVEY)
        for m in missions
    )
    return EXPERIENCE_ACCEPTED_WINDOWS if needs_time else DEFAULT_ACCEPTED_WINDOWS
