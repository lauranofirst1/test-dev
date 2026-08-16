"""애플리케이션 설정.

프로젝트 루트의 .env 를 읽습니다. 값의 의미는 .env.example 주석을 보세요.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

def _find_env_file() -> Path:
    """가장 가까운 .env 를 위로 올라가며 찾는다.

    경로를 parents[N] 으로 세면 파일이 옮겨질 때마다 조용히 어긋난다.
    실제로 한 번 어긋나서 키가 안 읽혔다.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    # 없으면 저장소 루트로 추정되는 위치를 반환한다 (pydantic 이 무시한다)
    return here.parents[5] / ".env"


ENV_FILE = _find_env_file()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 애플리케이션 ────────────────────────────────────────
    app_env: str = "local"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    demo_mode: bool = False

    # ── 데이터베이스 ────────────────────────────────────────
    database_url: str = "postgresql+psycopg://festaflow:festaflow@localhost:5432/festaflow"

    # ── 인증 ────────────────────────────────────────────────
    jwt_secret: str = "dev-only-change-me"
    jwt_ttl_hours: int = 12

    # ── 한국관광공사 OpenAPI ────────────────────────────────
    kto_api_key: str = ""
    kto_demand_api_key: str = ""
    kto_tour_api_key: str = ""
    kto_base_url: str = "https://apis.data.go.kr/B551011"
    kto_mobile_app: str = "FestaFlow"
    kto_daily_quota: int = 1000
    kto_timeout_seconds: float = 8.0
    kto_max_retries: int = 2

    # 진단 점수 표시 모드.
    #   auto      — 채점표 백테스트 기록이 있을 때만 점수 공개 (기본, 가장 정직)
    #   score     — 항상 공개. 공모전 지정과제 9번이 '흥행도 도출'을 요구하므로 출품 시 사용
    #   checklist — 항상 감춤
    diagnosis_score_mode: str = "auto"

    # 🚨 공모전 기간에는 False. 규정이 실시간 호출을 요구하고 호출 이력을 검증한다.
    tourism_snapshot_cache_enabled: bool = False
    tourism_snapshot_ttl_days: int = 7

    # ── 도메인 임계값 ───────────────────────────────────────
    scan_token_window_seconds: int = 300
    insights_min_sample: int = 10
    anonymize_after_days: int = 90
    media_retention_days: int = 90

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def tour_key(self) -> str:
        """국문 관광정보 등 콘텐츠 계열 키. 전용 키가 없으면 공통 키를 쓴다."""
        return self.kto_tour_api_key or self.kto_api_key

    @property
    def demand_key(self) -> str:
        """관광 수요 강도 등 데이터랩 계열 키."""
        return self.kto_demand_api_key or self.kto_api_key

    @property
    def has_kto_key(self) -> bool:
        return bool(self.tour_key and self.demand_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# 서비스 ID — docs/07-tourapi-catalog.md §6.1
class KtoService:
    KOR = "KorService2"  # 국문 관광정보
    DEMAND = "AreaTarDemDsService"  # 지역별 관광 수요 강도
    DATALAB = "DataLabService"  # 관광 빅데이터 (오퍼레이션 6종)
    CONCENTRATION = "TatsCnctrRateService"  # 관광지 집중률 30일 예측
    RELATED = "TarRlteTarService1"  # 관광지별 연관 관광지
    HUB = "LocgoHubTarService1"  # 기초지자체 중심 관광지
    PHOTO = "PhotoGalleryService1"  # 관광사진갤러리


# 데이터랩 계열은 demand 키, 나머지는 tour 키를 쓴다.
DEMAND_SERVICES = frozenset(
    {
        KtoService.DEMAND,
        KtoService.DATALAB,
        KtoService.CONCENTRATION,
        KtoService.RELATED,
        KtoService.HUB,
    }
)
