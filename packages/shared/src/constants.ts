/**
 * FestaFlow 공유 상수 — 도메인 임계값
 *
 * 백엔드 소유. 프론트는 import만 합니다.
 * 프론트가 이 값을 하드코딩하면 서버 판정과 어긋나 화면과 API가 다른 말을 하게 됩니다.
 *
 * 서버가 판정한 결과(status, is_active 등)를 그대로 표시하는 것이 원칙이고,
 * 여기 값들은 안내 문구를 쓰기 위한 참조용입니다.
 */

// ── 운영 인사이트 (docs/01-product-spec.md §7.1) ──────────────────────────

/** 최근 참여 집계 window (분) */
export const INSIGHT_WINDOWS_MINUTES = [10, 30, 60] as const;

/** 판정 기준이 되는 주 window */
export const INSIGHT_PRIMARY_WINDOW_MINUTES = 30;

/** 이 미만이면 판정하지 않고 INSUFFICIENT_DATA. 표본이 적을 때 초록으로 칠하면 거짓말이 된다. */
export const INSIGHT_MIN_SAMPLE = 10;

/** 부스 최근 30분 점유 비율 임계값 */
export const BOOTH_SHARE_CAUTION = 0.25;
export const BOOTH_SHARE_HIGH = 0.4;

/** REDISTRIBUTE 추천: 집중 부스가 이 이상이고, 다른 활성 부스가 LOW_SHARE 이하일 때 */
export const RECOMMEND_HIGH_SHARE = 0.4;
export const RECOMMEND_LOW_SHARE = 0.15;

/** NO_ACTIVITY 추천: 축제 전체가 이 이상인데 해당 부스 완료가 0일 때 */
export const RECOMMEND_NO_ACTIVITY_MIN_TOTAL = 20;

// ── 보상 캠페인 영향 분석 (docs/01-product-spec.md §7.2) ──────────────────

/** 캠페인 시작 기준 전후 window (분). 반개구간 [start-30, start) / [start, start+30) */
export const CAMPAIGN_IMPACT_WINDOW_MINUTES = 30;

/** before + after 표본 합계가 이 미만이면 INSUFFICIENT_DATA. 선을 그으면 근거처럼 보인다. */
export const CAMPAIGN_IMPACT_MIN_SAMPLE = 20;

/** before 구간에서 대상 부스를 제외한 최다 부스가 이 이상이면 함께 표시 */
export const CAMPAIGN_TOP_BOOTH_SHARE = 0.4;

// ── QR 스캔 ──────────────────────────────────────────────────────────────

/**
 * 부스 QR 토큰 유효 window (초).
 * 30초가 아니라 5분인 이유: 오프라인 상태에서는 서버가 토큰을 검증할 수 없어
 * 동기화 시점에 window를 검사한다. 30초로는 그 지연을 감당할 수 없다.
 */
export const SCAN_TOKEN_WINDOW_SECONDS = 300;

/** 서버가 인정하는 window 수 (현재 + 직전) */
export const SCAN_TOKEN_ACCEPTED_WINDOWS = 2;

/** 부스 화면이 QR을 갱신하는 주기 (초) */
export const SCAN_TOKEN_REFRESH_SECONDS = 30;

// ── 참여자 ───────────────────────────────────────────────────────────────

export const PARTICIPANT_CODE_PATTERN = /^FF-[0-9A-Z]{8}$/;
export const PARTICIPANT_CODE_PREFIX = 'FF-';

/** localStorage 키. 축제 ID별로 분리 저장. */
export const participantStorageKey = (festivalId: number | string): string =>
  `festaflow-participant-${festivalId}`;

/** 뒷 4자리는 1만 분의 1이라 무제한 시도를 허용하면 뚫린다. */
export const RECOVERY_MAX_ATTEMPTS = 5;

/** 스태프 접근 코드 실패 잠금 */
export const STAFF_CODE_MAX_ATTEMPTS = 5;
export const STAFF_LOCK_MINUTES = 10;

// ── 폴링 ─────────────────────────────────────────────────────────────────

/** 관객 참여 화면 (초) */
export const PARTICIPANT_POLL_SECONDS = 3;

/** 운영 대시보드 (초). 변경 없으면 304를 받는다. */
export const DASHBOARD_POLL_SECONDS = 10;

/** 새 조각이 열렸을 때 강조 유지 시간 (ms). prefers-reduced-motion에서도 줄이지 않는다. */
export const REVEAL_HIGHLIGHT_MS = 3500;

// ── 입력 제약 (DB CHECK와 일치해야 함) ────────────────────────────────────

export const LIMITS = {
  festivalName: { min: 2, max: 120 },
  boothName: { min: 2, max: 120 },
  boothTypeLabel: { max: 60 },
  boothLocation: { max: 200 },
  boothManagerName: { max: 120 },
  missionTitle: { min: 2, max: 120 },
  missionDescription: { max: 2000 },
  missionPoints: { min: 0, max: 1_000_000 },
  participantCode: { min: 4, max: 80 },
  campaignTitle: { min: 2, max: 120 },
  campaignMessage: { max: 500 },
  planSummary: { max: 300 },
} as const;

// ── 스탬프 보드 ──────────────────────────────────────────────────────────

/** 지원하는 격자 [rows, cols] */
export const SUPPORTED_GRIDS = [
  [2, 2],
  [2, 3],
  [3, 3],
] as const;

export const DEFAULT_BOARD_IMAGE = '/images/chuncheon-stamp-board.png';
export const DEFAULT_COMPLETE_MESSAGE = '모든 축제 조각을 완성했습니다!';

// ── 진단 ─────────────────────────────────────────────────────────────────

/** 채점표 배점 (rubric v1). config/rubrics/v1.json 과 일치. */
export const RUBRIC_V1_MAX_SCORES: Record<string, number> = {
  tourism_demand: 25,
  crowd_safety: 30,
  program_balance: 20,
  local_linkage: 15,
  ops_readiness: 10,
};

/** 총점 → 위험 수준 경계 */
export const RISK_THRESHOLD_STABLE = 85;
export const RISK_THRESHOLD_CAUTION = 70;

/** 항목별 수준 판정 (배점 대비 비율) */
export const ITEM_RATIO_STABLE = 0.8;
export const ITEM_RATIO_CAUTION = 0.6;

/** 점수를 공개하려면 이 표본 수 이상의 백테스트 기록이 필요하다. */
export const RUBRIC_MIN_CALIBRATION_SAMPLE = 10;

// ── 데이터 보존 ──────────────────────────────────────────────────────────

/** 축제 종료 후 참여자 개인 식별자를 익명화하기까지의 일수 */
export const ANONYMIZE_AFTER_DAYS = 90;

/** 사진 응답 보관 일수 */
export const MEDIA_RETENTION_DAYS = 90;

/** 보관된 축제를 물리 삭제할 수 있게 되기까지의 일수 */
export const PURGE_AFTER_ARCHIVE_DAYS = 30;

// ── 시각 ─────────────────────────────────────────────────────────────────

/** 저장·연산은 UTC. 표시와 집계 버킷 경계만 이 타임존. */
export const DISPLAY_TIMEZONE = 'Asia/Seoul';

/** 리포트 timeline 버킷 크기 (분) */
export const REPORT_BUCKET_MINUTES = 60;
