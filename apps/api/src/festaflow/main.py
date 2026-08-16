"""FestaFlow API 진입점."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from festaflow.core.config import settings
from festaflow.routers import diagnoses, festivals
from festaflow.services.tourapi import KtoError

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
)

# httpx 는 요청 URL 을 통째로 INFO 로 남긴다.
# serviceKey 가 쿼리스트링에 있으므로 그대로 두면 **인증키가 로그에 박힌다.**
# 우리 스펙이 금지한 항목이라 요청 로그는 끄고, 실패만 남긴다.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI(
    title="FestaFlow API",
    version="0.1.0",
    description="축제 기획 진단부터 현장 참여 측정까지",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(KtoError)
async def kto_error_handler(_: Request, exc: KtoError) -> JSONResponse:
    """TourAPI 오류를 전 엔드포인트 공통 포맷으로 변환한다."""
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": f"KTO_{exc.code or 'ERROR'}",
                "message": "관광 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
                "details": {"reason": str(exc)},
            }
        },
    )


app.include_router(festivals.router)
app.include_router(diagnoses.router)


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "env": settings.app_env,
        "kto_key_configured": settings.has_kto_key,
        "tourism_cache_enabled": settings.tourism_snapshot_cache_enabled,
    }
