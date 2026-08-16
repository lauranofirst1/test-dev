/**
 * FestaFlow 공유 열거형
 *
 * 이 파일은 백엔드(apps/api) 소유입니다. 프론트엔드는 import만 하고 수정하지 않습니다.
 * 값은 Postgres enum 타입과 1:1로 일치해야 합니다 (docs/02-data-model.md §2).
 * 계약이 틀렸다고 판단되면 직접 고치지 말고 "계약 이슈"로 보고하세요.
 */

export const FestivalStatus = {
  Draft: 'draft',
  Planning: 'planning',
  Ready: 'ready',
  Live: 'live',
  Closed: 'closed',
} as const;
export type FestivalStatus = (typeof FestivalStatus)[keyof typeof FestivalStatus];

/** 기획 파이프라인 진행 표시. 다음 단계를 잠그지 않는다. */
export const PlanStage = {
  Draft: 'draft',
  Layout: 'layout',
  Operations: 'operations',
  Proposal: 'proposal',
} as const;
export type PlanStage = (typeof PlanStage)[keyof typeof PlanStage];

export const StaffRole = {
  Planner: 'planner',
  Operator: 'operator',
  BoothManager: 'booth_manager',
} as const;
export type StaffRole = (typeof StaffRole)[keyof typeof StaffRole];

/** 부스 유형은 자유 텍스트가 아니다 — 진단의 "유형 수" 점수가 표기 흔들림으로 부풀지 않게. */
export const BoothType = {
  Food: 'food',
  Experience: 'experience',
  Performance: 'performance',
  Information: 'information',
  LocalShop: 'local_shop',
  Etc: 'etc',
} as const;
export type BoothType = (typeof BoothType)[keyof typeof BoothType];

/** 누가 누구의 QR을 스캔하는가 */
export const BoothVerifyMode = {
  /** 스태프가 참여자 QR을 스캔 — 미션 수행을 사람이 확인 */
  StaffScan: 'staff_scan',
  /** 참여자가 부스 QR을 스캔 — 현장 방문을 토큰이 확인 */
  ParticipantScan: 'participant_scan',
} as const;
export type BoothVerifyMode = (typeof BoothVerifyMode)[keyof typeof BoothVerifyMode];

/** 부스가 QR을 어떻게 내놓는가. 인쇄가 기본값 — 장비를 강요하면 안 쓰인다. */
export const BoothQrMode = {
  Printed: 'printed',
  Rotating: 'rotating',
} as const;
export type BoothQrMode = (typeof BoothQrMode)[keyof typeof BoothQrMode];

export const ParticipationStatus = {
  Issued: 'issued',
  Completed: 'completed',
} as const;
export type ParticipationStatus =
  (typeof ParticipationStatus)[keyof typeof ParticipationStatus];

export const ExperienceType = {
  Stamp: 'stamp',
  Quiz: 'quiz',
  Photo: 'photo',
  Survey: 'survey',
  Info: 'info',
} as const;
export type ExperienceType = (typeof ExperienceType)[keyof typeof ExperienceType];

export const RevealMode = {
  Random: 'random',
  BoothAssigned: 'booth_assigned',
} as const;
export type RevealMode = (typeof RevealMode)[keyof typeof RevealMode];

/** 조각 지급 단위. 타일 수 > 지급 단위 수이면 완성 불가 경고. */
export const GrantUnit = {
  Booth: 'booth',
  Mission: 'mission',
} as const;
export type GrantUnit = (typeof GrantUnit)[keyof typeof GrantUnit];

/** 부스별 참여 편중 상태. 실제 밀집도가 아니라 QR 완료 기반 대리 지표. */
export const BoothLoadStatus = {
  InsufficientData: 'INSUFFICIENT_DATA',
  Low: 'LOW',
  Caution: 'CAUTION',
  High: 'HIGH',
} as const;
export type BoothLoadStatus = (typeof BoothLoadStatus)[keyof typeof BoothLoadStatus];

export const RecommendationType = {
  Redistribute: 'REDISTRIBUTE',
  NoActivity: 'NO_ACTIVITY',
} as const;
export type RecommendationType =
  (typeof RecommendationType)[keyof typeof RecommendationType];

export const DiagnosisStatus = {
  Pending: 'pending',
  Running: 'running',
  Completed: 'completed',
  Failed: 'failed',
} as const;
export type DiagnosisStatus = (typeof DiagnosisStatus)[keyof typeof DiagnosisStatus];

/** 채점표가 검증되기 전에는 점수를 공개하지 않는다. */
export const DiagnosisDisplay = {
  Checklist: 'checklist',
  Score: 'score',
} as const;
export type DiagnosisDisplay = (typeof DiagnosisDisplay)[keyof typeof DiagnosisDisplay];

export const DiagnosisCategory = {
  TourismDemand: 'tourism_demand',
  CrowdSafety: 'crowd_safety',
  ProgramBalance: 'program_balance',
  LocalLinkage: 'local_linkage',
  OpsReadiness: 'ops_readiness',
} as const;
export type DiagnosisCategory =
  (typeof DiagnosisCategory)[keyof typeof DiagnosisCategory];

export const RiskLevel = {
  Stable: 'stable',
  Caution: 'caution',
  Risk: 'risk',
} as const;
export type RiskLevel = (typeof RiskLevel)[keyof typeof RiskLevel];

/** 체크리스트 모드에서 RiskLevel을 이 값으로 매핑해 표시한다. */
export const Fulfillment = {
  Met: 'met',
  Partial: 'partial',
  Unmet: 'unmet',
} as const;
export type Fulfillment = (typeof Fulfillment)[keyof typeof Fulfillment];

export const RISK_TO_FULFILLMENT: Record<RiskLevel, Fulfillment> = {
  [RiskLevel.Stable]: Fulfillment.Met,
  [RiskLevel.Caution]: Fulfillment.Partial,
  [RiskLevel.Risk]: Fulfillment.Unmet,
};

export const TourismProvider = {
  KtoLive: 'kto_live',
  Demo: 'demo',
} as const;
export type TourismProvider = (typeof TourismProvider)[keyof typeof TourismProvider];

/** 실측 방문객 출처. 리포트는 우선순위가 높은 하나를 쓰고 나머지는 병기. */
export const VisitorSource = {
  Beacon: 'beacon',
  ManualCounter: 'manual_counter',
  /** 관광공사 DataLabService/locgoRegnVisitrDDList — 기초지자체 단위라 축제장보다 범위가 넓다 */
  KtoBigdata: 'kto_bigdata',
  Partner: 'partner',
  Estimate: 'estimate',
} as const;
export type VisitorSource = (typeof VisitorSource)[keyof typeof VisitorSource];

/** 낮을수록 우선. 현장 계수기보다는 낮고 주최측 추산보다는 높다. */
export const VISITOR_SOURCE_PRIORITY: Record<VisitorSource, number> = {
  [VisitorSource.Beacon]: 1,
  [VisitorSource.ManualCounter]: 2,
  [VisitorSource.KtoBigdata]: 3,
  [VisitorSource.Partner]: 4,
  [VisitorSource.Estimate]: 5,
};

export const PlanTier = {
  PerFestival: 'per_festival',
  Annual: 'annual',
  Enterprise: 'enterprise',
} as const;
export type PlanTier = (typeof PlanTier)[keyof typeof PlanTier];

export const RiskGrade = {
  Low: 'low',
  Medium: 'medium',
  High: 'high',
} as const;
export type RiskGrade = (typeof RiskGrade)[keyof typeof RiskGrade];

/** API 오류 코드. error.code 로 내려온다. */
export const ErrorCode = {
  ValidationFailed: 'VALIDATION_FAILED',
  QuotaExceeded: 'QUOTA_EXCEEDED',
  MissionBoothFestivalMismatch: 'MISSION_BOOTH_FESTIVAL_MISMATCH',
  MissionNotInBooth: 'MISSION_NOT_IN_BOOTH',
  BoothInactive: 'BOOTH_INACTIVE',
  MissionInactive: 'MISSION_INACTIVE',
  NoTileAvailable: 'NO_TILE_AVAILABLE',
  ParticipantNotFound: 'PARTICIPANT_NOT_FOUND',
  BoardResetRequiresConfirmation: 'BOARD_RESET_REQUIRES_CONFIRMATION',
  ScanTokenExpired: 'SCAN_TOKEN_EXPIRED',
  ScanTokenInvalid: 'SCAN_TOKEN_INVALID',
  ScanAlreadyUsed: 'SCAN_ALREADY_USED',
  BoothModeMismatch: 'BOOTH_MODE_MISMATCH',
  RecoveryNotAvailable: 'RECOVERY_NOT_AVAILABLE',
  RecoveryAttemptsExceeded: 'RECOVERY_ATTEMPTS_EXCEEDED',
  StaffLocked: 'STAFF_LOCKED',
  ExperienceWrongAnswer: 'EXPERIENCE_WRONG_ANSWER',
  ExperienceAttemptsExceeded: 'EXPERIENCE_ATTEMPTS_EXCEEDED',
  ExperienceConsentRequired: 'EXPERIENCE_CONSENT_REQUIRED',
  ExperienceDwellTooShort: 'EXPERIENCE_DWELL_TOO_SHORT',
} as const;
export type ErrorCode = (typeof ErrorCode)[keyof typeof ErrorCode];
