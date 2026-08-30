"""애플리케이션 설정.

프로젝트 루트의 .env 를 읽습니다. 값의 의미는 .env.example 주석을 보세요.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    # 못 찾았으면 없는 것이다. **위치를 지어내지 않는다.**
    #
    # 여기서 parents[5] 를 세던 코드가 컨테이너에서 IndexError 로 터졌다 —
    # 저장소에서는 6단계 위에 루트가 있지만 이미지 안에서는 /app/src/festaflow/core
    # 라 그만큼 깊지 않다. 바로 위 docstring 이 경고하는 그 실수다.
    #
    # .env 파일이 없는 것은 오류가 아니다. 배포에서는 환경변수로만 넣는 게
    # 정상이고, pydantic 은 없는 파일을 조용히 무시한다.
    return Path(".env")


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
    #: 요청의 Host 헤더 허용 목록. 운영에서는 API가 실제로 받는 호스트만 적는다.
    #: `testserver`는 FastAPI TestClient의 기본 호스트이며 로컬 기본값에만 둔다.
    trusted_hosts: str = "localhost,127.0.0.1,::1,testserver"
    demo_mode: bool = False

    #: 관객이 실제로 접속하는 프런트엔드 주소. 부스 QR 에 담을 링크를 만들 때 쓴다.
    #:
    #: 비워 두면 요청이 도착한 주소(`request.base_url`)를 쓰는데, 그건 **API 서버**
    #: 주소다. 개발 환경에서는 프런트가 5173, API 가 8000 이라 QR 이 API 서버를
    #: 가리키고 그쪽에는 `/join` 라우트가 없다. 리버스 프록시 뒤에서도 내부 주소가
    #: 잡힌다. 배포에서는 반드시 채우세요.
    #:
    #: 브라우저(부스 QR 화면)는 이 값 대신 자기 오리진을 쓰는 것이 가장 정확하다 —
    #: 응답의 `scan_path` 가 그 용도다.
    public_web_origin: str | None = None

    # ── 데이터베이스 ────────────────────────────────────────
    database_url: str = "postgresql+psycopg://festaflow:festaflow@localhost:5432/festaflow"

    # ── 인증 ────────────────────────────────────────────────
    jwt_secret: str = "dev-only-change-me"
    jwt_ttl_hours: int = 12
    #: 접근 코드 해시 비용. 12 는 한 번에 약 180ms — 온라인 대입을 무의미하게 만든다.
    #: 테스트에서만 낮춘다(테스트가 해시를 수십 번 만든다).
    bcrypt_rounds: int = 12
    #: 접근 코드 연속 실패 허용 횟수와 잠금 시간 — docs/03-api-contract.md §1
    login_max_attempts: int = 5
    login_lock_minutes: int = 10

    #: 기관 계정 세션 쿠키 이름. 토큰을 localStorage 에 두면 XSS 한 번에 전부
    #: 털린다. httpOnly 쿠키는 스크립트가 읽을 수 없다.
    session_cookie_name: str = "festaflow_session"
    #: 스태프 세션은 **다른 쿠키**에 담는다. 한 이름을 같이 쓰면 나중에 로그인한
    #: 쪽이 앞의 세션을 덮어쓴다 — 운영자가 콘솔에서 심사표를 열어 심사위원으로
    #: 로그인하는 순간(그러라고 만든 링크다) 콘솔의 운영자 세션이 사라졌다.
    #: 한 브라우저에 기관 세션과 스태프 세션이 함께 있는 것이 정상이다.
    staff_cookie_name: str = "festaflow_staff"
    #: 쿠키에 Secure 를 붙일지. 로컬(http://192.168.x.x:5173)에서는 붙이면
    #: 브라우저가 아예 저장하지 않으므로 개발에서만 끈다. **배포에서는 반드시 켠다.**
    session_cookie_secure: bool = False
    #: SameSite=strict 면 외부 사이트에서 온 요청에 쿠키가 실리지 않는다 —
    #: 우리 요청은 전부 같은 사이트라 CSRF 가 구조적으로 막힌다.
    session_cookie_samesite: str = "strict"

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

    # ── 메일 ────────────────────────────────────────────────
    #: SMTP 설정. 비어 있으면 **보내지 않고 로그에 남깁니다** —
    #: 조용히 성공한 척하면 사용자는 영원히 메일을 기다립니다.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    #: 587 포트의 STARTTLS. 465 를 쓸 때만 smtp_use_ssl 을 켭니다.
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    #: 보내는 주소. 도메인의 SPF·DKIM 에 등록된 주소여야 스팸함을 피합니다.
    mail_from: str = ""
    mail_from_name: str = "FestaFlow"

    #: 재설정 링크 유효 시간(분). 메일 본문이 이 값을 그대로 알립니다 —
    #: 서비스와 문구가 다르면 사용자는 만료된 링크를 계속 누릅니다.
    reset_ttl_minutes: int = 30

    # ── 업로드 ──────────────────────────────────────────────
    #: 조각 보드 그림이 저장되는 곳. /media 로 서빙된다.
    media_dir: str = "media"

    # ── 도메인 임계값 ───────────────────────────────────────
    #: 부스 회전 QR 의 window 길이. 서버가 현재·직전 window 를 모두 인정하므로
    #: 실질 유효기간은 30~60초다. docs/02-data-model.md §7 과 계약 §8.2 기준.
    #: (01-product-spec 의 "5분 회전"은 더 느슨한 초기 서술이라 따르지 않는다)
    scan_token_window_seconds: int = 30
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
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

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
