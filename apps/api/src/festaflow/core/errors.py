"""공통 오류 포맷.

전 엔드포인트가 같은 모양으로 실패해야 프런트가 한 곳에서 처리할 수 있습니다.

    {"error": {"code": "...", "message": "...", "details": {...}}}

`message` 는 그대로 화면에 노출됩니다. 무엇이 잘못됐고 어떻게 고치는지 쓰세요.
사과문·모호한 표현 금지.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            detail={"error": {"code": code, "message": message, "details": details or {}}},
        )


#: 우리가 만들지 않은 HTTP 오류의 한국어 문구.
#:
#: 라우트 오타나 잘못된 메서드는 대개 개발 중에 나지만, 배포 후에도 오래된
#: 북마크나 잘못된 링크로 사용자가 봅니다. 이 저장소는 "message 는 그대로 화면에
#: 노출된다" 를 규칙으로 삼는데, 여기서만 영어가 새어 나가고 있었습니다.
HTTP_MESSAGES: dict[int, str] = {
    404: "요청한 주소를 찾을 수 없습니다.",
    405: "이 주소에서는 쓸 수 없는 방식입니다.",
    413: "보낸 데이터가 너무 큽니다.",
    429: "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.",
    500: "서버에서 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.",
}


def object_particle(word: str) -> str:
    """목적격 조사를 받침 유무로 고른다 — `축제를`, `진단을`.

    리소스명을 문장에 끼워 넣을 때 조사를 고정하면 반드시 한쪽이 틀린다.
    한글이 아닌 글자로 끝나면(영문·숫자) 읽는 방식이 갈리므로 `를`로 둔다.
    """
    if not word:
        return "를"
    last = word[-1]
    if "가" <= last <= "힣":
        return "를" if (ord(last) - 0xAC00) % 28 == 0 else "을"
    return "를"


def subject_particle(word: str) -> str:
    """주격 조사를 받침 유무로 고른다 — `부스가`, `미션이`."""
    if not word:
        return "가"
    last = word[-1]
    if "가" <= last <= "힣":
        return "가" if (ord(last) - 0xAC00) % 28 == 0 else "이"
    return "가"


def not_found(what: str = "리소스") -> ApiError:
    """타 기관 리소스도 이걸로 응답한다 — 403 을 쓰면 존재 여부가 노출된다."""
    return ApiError(404, "NOT_FOUND", f"{what}{object_particle(what)} 찾을 수 없습니다.")


def validation_failed(message: str, field: str | None = None) -> ApiError:
    return ApiError(422, "VALIDATION_FAILED", message, {"field": field} if field else None)


def quota_exceeded(limit: int) -> ApiError:
    return ApiError(
        402,
        "QUOTA_EXCEEDED",
        f"요금제의 축제 수({limit}건)를 초과했습니다. 요금제를 변경하거나 기존 축제를 보관하세요.",
        {"limit": limit},
    )


# ── 요청 검증 오류 번역 ──────────────────────────────────────────────────────
#
# FastAPI 는 Pydantic 검증 실패를 `{"detail": [{loc, msg, type}, ...]}` 로 내는데,
# `msg` 가 영어입니다. 이 저장소는 "message 는 그대로 화면에 노출된다" 를 규칙으로
# 삼고 있으므로(이 파일 맨 위), 그 규칙이 검증 오류에서만 깨지고 있었습니다.
#
# 필드 이름까지 번역하지는 않습니다. 화면이 `details.field` 로 어느 칸인지 알고,
# 그 칸의 라벨은 이미 한국어이기 때문입니다 — 서버가 라벨을 두 벌 갖게 되면
# 화면을 고칠 때마다 어긋납니다.

#: Pydantic 오류 종류 → 한국어. 없는 종류는 아래 기본 문장으로 떨어진다.
_VALIDATION_MESSAGES: dict[str, str] = {
    "missing": "필수 항목입니다.",
    "string_too_short": "너무 짧습니다.",
    "string_too_long": "너무 깁니다.",
    "string_pattern_mismatch": "형식이 올바르지 않습니다.",
    "value_error": "값이 올바르지 않습니다.",
    "int_parsing": "숫자를 입력해 주세요.",
    "float_parsing": "숫자를 입력해 주세요.",
    "bool_parsing": "참·거짓 값이어야 합니다.",
    "date_parsing": "날짜 형식이 올바르지 않습니다.",
    "date_from_datetime_parsing": "날짜 형식이 올바르지 않습니다.",
    "datetime_parsing": "날짜·시각 형식이 올바르지 않습니다.",
    "datetime_from_date_parsing": "날짜·시각 형식이 올바르지 않습니다.",
    "greater_than": "더 큰 값이어야 합니다.",
    "greater_than_equal": "더 큰 값이어야 합니다.",
    "less_than": "더 작은 값이어야 합니다.",
    "less_than_equal": "더 작은 값이어야 합니다.",
    "enum": "허용되지 않는 값입니다.",
    "literal_error": "허용되지 않는 값입니다.",
    "too_short": "항목이 더 필요합니다.",
    "too_long": "항목이 너무 많습니다.",
    "json_invalid": "요청 본문을 읽을 수 없습니다.",
}

#: 종류만으로는 부족한 것들. 제약값을 문장에 넣어 무엇을 고쳐야 하는지 말한다.
_WITH_LIMIT: dict[str, str] = {
    "string_too_short": "{min_length}자 이상이어야 합니다.",
    "string_too_long": "{max_length}자 이하여야 합니다.",
    "greater_than_equal": "{ge} 이상이어야 합니다.",
    "greater_than": "{gt}보다 커야 합니다.",
    "less_than_equal": "{le} 이하여야 합니다.",
    "less_than": "{lt}보다 작아야 합니다.",
    "too_short": "{min_length}개 이상이어야 합니다.",
    "too_long": "{max_length}개 이하여야 합니다.",
}

#: 이메일은 종류가 `value_error` 로 뭉뚱그려져 나온다. 문구로 알아본다.
_EMAIL_HINT = "valid email address"


def translate_validation_error(errors: list[dict[str, Any]]) -> tuple[str, str | None]:
    """Pydantic 오류 목록 → (한국어 문장, 문제가 된 필드).

    **첫 번째 오류만 문장으로 만듭니다.** 여러 개를 한 문장에 붙이면 읽히지
    않고, 화면은 어차피 한 칸씩 고쳐 나갑니다.
    """
    if not errors:
        return "요청을 처리할 수 없습니다.", None

    first = errors[0]
    kind = str(first.get("type", ""))
    loc = [str(p) for p in first.get("loc", []) if p not in ("body", "query", "path")]
    field = loc[-1] if loc else None

    if kind == "value_error" and _EMAIL_HINT in str(first.get("msg", "")):
        return "이메일 주소 형식이 올바르지 않습니다.", field

    ctx = first.get("ctx") or {}
    template = _WITH_LIMIT.get(kind)
    if template:
        try:
            return template.format(**ctx), field
        except (KeyError, IndexError):
            pass

    return _VALIDATION_MESSAGES.get(kind, "값이 올바르지 않습니다."), field
