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


def not_found(what: str = "리소스") -> ApiError:
    """타 기관 리소스도 이걸로 응답한다 — 403 을 쓰면 존재 여부가 노출된다."""
    return ApiError(404, "NOT_FOUND", f"{what}를 찾을 수 없습니다.")


def validation_failed(message: str, field: str | None = None) -> ApiError:
    return ApiError(422, "VALIDATION_FAILED", message, {"field": field} if field else None)


def quota_exceeded(limit: int) -> ApiError:
    return ApiError(
        402,
        "QUOTA_EXCEEDED",
        f"요금제의 축제 수({limit}건)를 초과했습니다. 요금제를 변경하거나 기존 축제를 보관하세요.",
        {"limit": limit},
    )
