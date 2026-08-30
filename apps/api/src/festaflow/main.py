"""FestaFlow API 진입점."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.core.errors import HTTP_MESSAGES, translate_validation_error
from festaflow.routers import (
    announcements,
    auth,
    booths,
    campaigns,
    consumer,
    diagnoses,
    exhibits,
    festivals,
    lectures,
    operations,
    participants,
    prizes,
    reports,
    search,
    staff,
    stamp_board,
)
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
security.assert_deployment_is_safe()

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
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_host_list,
)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """모든 HTTP 오류를 계약의 봉투 하나로 낸다 — 계약 §0.

    FastAPI 기본 핸들러는 `HTTPException.detail` 을 **`{"detail": ...}` 로 한 겹
    더 감쌉니다.** `ApiError` 는 detail 자리에 이미 `{"error": {...}}` 를 넣으므로
    밖으로는 `{"detail": {"error": {...}}}` 가 나가고, 계약이 명시한 모양과
    달라집니다. 화면 클라이언트가 두 겹을 모두 벗기도록 방어하고 있어 겉으로는
    멀쩡했지만, 그건 계약이 지켜지고 있다는 뜻이 아니라 클라이언트가 계약 위반을
    가려 주고 있었다는 뜻입니다.

    라우트를 못 찾은 404 나 메서드 불일치 405 처럼 **우리가 만들지 않은** 오류도
    여기로 옵니다. 그쪽 `detail` 은 Starlette 가 넣은 영어 평문("Not Found")이라,
    아는 상태 코드는 한국어로 바꿔 같은 봉투에 담습니다.

    `headers` 를 그대로 넘기는 이유는 405 의 `Allow` 처럼 응답의 의미가 헤더에
    실려 오는 경우가 있기 때문입니다.
    """
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        content = detail
    else:
        content = {
            "error": {
                "code": "HTTP_ERROR",
                "message": HTTP_MESSAGES.get(exc.status_code, str(detail)),
                "details": {},
            }
        }
    return JSONResponse(
        status_code=exc.status_code, content=content, headers=getattr(exc, "headers", None)
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """검증 실패도 **다른 오류와 같은 모양으로** 낸다.

    FastAPI 기본 응답은 `{"detail": [{loc, msg, type}, ...]}` 이고 `msg` 가
    영어다. 이 저장소는 "message 는 그대로 화면에 노출된다" 를 규칙으로 삼는데
    (core/errors.py), 그 규칙이 검증 오류에서만 깨지고 있었다. 화면도 이 한 곳만
    보면 되도록 봉투를 맞춘다.
    """
    message, field = translate_validation_error(list(exc.errors()))
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_FAILED",
                "message": message,
                # 화면이 어느 칸 밑에 붙일지 아는 유일한 단서다.
                "details": {"field": field} if field else {},
            }
        },
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
app.include_router(prizes.router)
app.include_router(lectures.router)
app.include_router(exhibits.router)
app.include_router(staff.router)
app.include_router(operations.router)
app.include_router(campaigns.router)
app.include_router(consumer.router)
app.include_router(reports.router)
app.include_router(announcements.router)
app.include_router(search.router)
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
