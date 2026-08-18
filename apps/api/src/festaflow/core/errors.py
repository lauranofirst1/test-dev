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
