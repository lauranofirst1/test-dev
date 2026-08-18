"""FestaFlow API 진입점."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.routers import auth, booths, diagnoses, festivals, participants, stamp_board
from festaflow.services import media
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

# 개발용 기본 JWT 시크릿으로 로컬 밖에서 뜨는 것을 막는다.
# 시크릿이 저장소에 공개된 채로 배포되면 토큰을 누구나 위조할 수 있다.
security.assert_secret_is_safe()

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


# 업로드된 조각 보드 그림. StaticFiles 가 확장자로 Content-Type 을 정하므로,
# 저장할 때 매직 바이트로 판별한 확장자만 붙여야 한다(services/media.py).
app.mount("/media", StaticFiles(directory=str(media.media_root())), name="media")

app.include_router(auth.router)
app.include_router(festivals.router)
app.include_router(diagnoses.router)
app.include_router(booths.router)
app.include_router(stamp_board.router)
app.include_router(stamp_board.grid_router)
# 참여자 라우터는 기관 스코프를 쓰지 않는다. 마지막에 붙여 경로 충돌을 피한다.
app.include_router(participants.router)


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "env": settings.app_env,
        "kto_key_configured": settings.has_kto_key,
        "tourism_cache_enabled": settings.tourism_snapshot_cache_enabled,
    }
