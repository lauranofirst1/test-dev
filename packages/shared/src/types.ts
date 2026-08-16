/**
 * FestaFlow API 타입 — MVP 관문 범위
 *
 * 백엔드 소유. 프론트엔드는 import만 하고 수정하지 않습니다.
 * API 응답 타입을 프론트에서 다시 선언하지 마세요.
 *
 * 원천은 apps/api 의 Pydantic 스키마이며, 이 파일은 packages/shared/openapi.json 에서
 * 생성됩니다. 계약이 틀렸다고 판단되면 직접 고치지 말고 "계약 이슈"로 보고하세요.
 */

import type {
  BoothLoadStatus,
  BoothQrMode,
  BoothType,
  BoothVerifyMode,
  DiagnosisCategory,
  DiagnosisDisplay,
  ErrorCode,
  FestivalStatus,
  Fulfillment,
  GrantUnit,
  PlanStage,
  PlanTier,
  RecommendationType,
  RevealMode,
  RiskLevel,
  StaffRole,
  VisitorSource,
} from './enums';

/** ISO 8601 UTC — 예: "2026-10-10T05:04:00Z" */
export type IsoDateTime = string;
/** ISO 8601 date — 예: "2026-10-10" */
export type IsoDate = string;

// ── 공통 ─────────────────────────────────────────────────────────────────

export interface ApiError {
  error: {
    code: ErrorCode;
    /** 그대로 화면에 노출되는 한국어 문장 */
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// ── 기관 ─────────────────────────────────────────────────────────────────

export interface Organization {
  id: number;
  name: string;
  plan_tier: PlanTier;
  /** null = 무제한 (enterprise) */
  festival_quota: number | null;
  festival_count: number;
}

// ── 축제 ─────────────────────────────────────────────────────────────────

export interface FestivalPlan {
  summary: string | null;
  description: string | null;
  purposes: string[];
  target_segments: string[];
  core_audience: string | null;
  staff_count: number | null;
  volunteer_count: number | null;
  safety_staff_count: number | null;
  parking_capacity: number | null;
  venue_capacity: number | null;
  planned_performance: number;
  planned_experience: number;
  planned_food: number;
  planned_local_shop: number;
  planned_tour_info: number;
  planned_etc: number;
  transit_access: string | null;
  traffic_plan: string | null;
  crowd_plan: string | null;
  safety_plan: string | null;
  tourism_link_plan: string | null;
  local_commerce_plan: string | null;
  lodging_plan: string | null;
  promotion_plan: string | null;
}

export interface Festival {
  id: number;
  organization_id: number;
  name: string;
  region: string;
  venue: string;
  starts_on: IsoDate;
  ends_on: IsoDate;
  expected_visitors: number;
  total_budget: number;
  status: FestivalStatus;
  plan_stage: PlanStage;
  is_demo: boolean;
  allow_photo_experience: boolean;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface FestivalDetail extends Festival {
  plan: FestivalPlan;
  /** 등록된 활성 미션 수 — 목록 카드 표시용 */
  mission_count: number;
  booth_count: number;
}

export interface FestivalCreateRequest {
  name: string;
  region: string;
  venue: string;
  starts_on: IsoDate;
  ends_on: IsoDate;
  expected_visitors: number;
  total_budget: number;
  plan?: Partial<FestivalPlan>;
}

export interface FestivalCreateResponse {
  festival: Festival;
  diagnosis: { id: number; status: string };
  stamp_board: { id: number; version: number; rows: number; cols: number };
  /** 이 응답에서만 평문으로 노출된다. 이후 어떤 조회에도 나오지 않는다. */
  operator_access_code: string;
}

// ── 스태프 ───────────────────────────────────────────────────────────────

export interface FestivalStaff {
  id: number;
  festival_id: number;
  role: StaffRole;
  display_name: string;
  booth_id: number | null;
  is_active: boolean;
  last_login_at: IsoDateTime | null;
}

export interface StaffCreateResponse {
  staff: FestivalStaff;
  /** QR로 인코딩할 URL. 비밀이 담겨 있지 않다. */
  invite_url: string;
  /** 1회만 노출 */
  access_code: string;
}

export interface StaffLoginRequest {
  festival_id: number;
  staff_id: number;
  access_code: string;
}

export interface StaffSession {
  token: string;
  expires_at: IsoDateTime;
  staff: FestivalStaff;
}

// ── 부스와 미션 ──────────────────────────────────────────────────────────

export interface Booth {
  id: number;
  festival_id: number;
  name: string;
  booth_type: BoothType;
  type_label: string | null;
  location: string | null;
  manager_name: string | null;
  is_active: boolean;
  verify_mode: BoothVerifyMode;
  qr_mode: BoothQrMode;
  use_experience: boolean;
}

export interface Mission {
  id: number;
  festival_id: number;
  booth_id: number | null;
  title: string;
  description: string | null;
  points: number;
  is_active: boolean;
}

export interface BoothCreateRequest {
  name: string;
  booth_type: BoothType;
  type_label?: string;
  location?: string;
  manager_name?: string;
  verify_mode?: BoothVerifyMode;
  qr_mode?: BoothQrMode;
  /** 함께 만들면 하나의 트랜잭션으로 커밋된다. 실패 시 부스도 롤백. */
  first_mission?: {
    title: string;
    points: number;
    description?: string;
    is_active?: boolean;
  };
}

// ── 참여자 ───────────────────────────────────────────────────────────────

export interface ParticipantIssueRequest {
  /** 선택. 없으면 기기 변경 시 복구할 수 없다. */
  phone_last4?: string;
}

export interface ParticipantIssueResponse {
  code: string;
  /** 이 응답에서만 노출. localStorage에 저장한다. */
  secret: string;
  festival_id: number;
  recovery_enabled: boolean;
}

export interface ParticipantRecoverRequest {
  code: string;
  phone_last4: string;
}

// ── 지급 ─────────────────────────────────────────────────────────────────

export interface Participation {
  id: number;
  mission_id: number | null;
  /** 지급 시점 스냅샷. 나중에 미션을 옮겨도 이 값은 변하지 않는다. */
  booth_id: number | null;
  base_points: number;
  bonus_points: number;
  granted_points: number;
  reward_campaign_id: number | null;
  verified_via: BoothVerifyMode | null;
  completed_at: IsoDateTime | null;
}

export interface GrantRequest {
  participant_code: string;
  mission_id: number;
  /** 오프라인 큐 멱등 키. 재전송해도 중복 지급되지 않는다. */
  client_request_id?: string;
  /** 오프라인에서 지급 버튼을 누른 시각. completed_at 이 이 값으로 기록된다. */
  queued_at?: IsoDateTime;
}

export interface GrantResponse {
  was_already_granted: boolean;
  participation: Participation;
  revealed_tile: { tile_index: number; board_version: number } | null;
  board_progress: BoardProgress;
}

export interface GrantBatchRequest {
  grants: GrantRequest[];
}

export interface GrantBatchResult {
  client_request_id: string;
  status: 'granted' | 'duplicate' | 'failed';
  participation?: Participation;
  error?: ApiError['error'];
}

// ── 스탬프 보드 ──────────────────────────────────────────────────────────

export interface BoardProgress {
  revealed_count: number;
  total_tiles: number;
  is_complete: boolean;
}

export interface StampTile {
  tile_index: number;
  assigned_booth_id: number | null;
  is_revealed: boolean;
  revealed_by_booth_id: number | null;
  revealed_at: IsoDateTime | null;
}

export interface StampBoard {
  id: number;
  festival_id: number;
  version: number;
  rows: number;
  cols: number;
  reveal_mode: RevealMode;
  grant_unit: GrantUnit;
  image_url: string;
  complete_message: string;
  tiles: StampTile[];
  progress: BoardProgress;
  /** 타일 수 > 지급 단위 수이면 채워진다. 아무도 완성할 수 없다는 뜻. */
  uncompletable_warning: string | null;
}

// ── 운영 인사이트 ────────────────────────────────────────────────────────

export interface BoothInsight {
  booth_id: number;
  name: string;
  is_active: boolean;
  total_completions: number;
  unique_participants: number;
  last_10m: number;
  last_30m: number;
  last_60m: number;
  share_last_30m: number;
  status: BoothLoadStatus;
  /** 왜 그 상태인지 — 색만으로 말하지 않기 위해 항상 채운다. */
  status_reason: string;
  last_completed_at: IsoDateTime | null;
}

export interface Recommendation {
  type: RecommendationType;
  target_booth_id: number | null;
  /** 상황 */
  situation: string;
  /** 판단 근거 */
  evidence: string;
  /** 권장 행동 — 지시가 아니라 확인 요청 문구 */
  action: string;
}

export interface OperationsInsights {
  generated_at: IsoDateTime;
  kpi: {
    total_participants: number;
    total_completions: number;
    completions_last_30m: number;
    high_concentration_booths: number;
  };
  booths: BoothInsight[];
  /** 표본이 부족하면 빈 배열. 억지로 만들지 않는다. */
  recommendations: Recommendation[];
  warnings: { code: string; message: string }[];
  /** 이 지표가 무엇이 아닌지 — 화면에 항상 표시한다. */
  disclaimer: string;
}

export interface RecommendationFeedbackRequest {
  rec_type: RecommendationType;
  booth_id: number | null;
  observed_at: IsoDateTime;
  /** true = 현장과 일치함 */
  verdict: boolean;
}

// ── 진단 ─────────────────────────────────────────────────────────────────

export interface DiagnosisItem {
  category: DiagnosisCategory;
  /** display_mode 가 'score' 일 때만 채워진다. */
  score: number | null;
  max_score: number | null;
  level: RiskLevel;
  /** checklist 모드에서 표시하는 값 */
  fulfillment: Fulfillment;
  reason: string;
  recommendation: string;
}

export interface Diagnosis {
  id: number;
  festival_id: number;
  rubric_version: string;
  display_mode: DiagnosisDisplay;
  /** 채점표가 검증되지 않았으면 false — 점수는 계산·저장되지만 응답에서 감춘다. */
  score_disclosed: boolean;
  total_score: number | null;
  risk: RiskLevel | null;
  items: DiagnosisItem[];
  tourism_source: { provider: string; base_month: string; note: string } | null;
  disclosure_note: string | null;
  created_at: IsoDateTime;
}

// ── 실측 방문객 ──────────────────────────────────────────────────────────

export interface VisitorCount {
  id: number;
  count_date: IsoDate;
  visitors: number;
  source: VisitorSource;
  note: string | null;
}

// ── 사후 리포트 ──────────────────────────────────────────────────────────

export interface ReportSummary {
  unique_participants: number;
  total_completions: number;
  avg_completions_per_participant: number;
  missions_with_completion: { count: number; total: number; ratio: number };
}

export interface ReportBoothRow {
  booth_id: number | null;
  name: string;
  completions: number;
  unique_participants: number;
  share: number;
  /** 동률은 같은 순위 */
  rank: number;
  peak_hour_kst: IsoDateTime | null;
  peak_completions: number;
}

export interface ReportKpiRow {
  metric_key: string;
  label: string;
  target: number;
  /** 측정 불가 지표는 null */
  actual: number | null;
  achievement: number | null;
  measurable: boolean;
  unit: string;
  note?: string;
}

export interface FestivalReport {
  summary: ReportSummary;
  /** 실측 방문객이 있을 때만. 없으면 null 이고 참여율을 만들지 않는다. */
  participation_rate: {
    visitors: number;
    source: VisitorSource;
    rate: number;
    note: string;
  } | null;
  plan_vs_actual: {
    expected_visitors: number;
    festaflow_participants: number;
    participation_scale: number;
    /** 이 값이 실제 방문률이 아니라는 설명 */
    disclaimer: string;
  };
  timeline: { hour_kst: IsoDateTime; completions: number }[];
  booths: ReportBoothRow[];
  /** 부스 스냅샷이 해제된 참여. 특정 부스에 임의 배정하지 않는다. */
  unassigned_completions: number;
  kpi: ReportKpiRow[];
  recommendation_accuracy: { total: number; matched: number; rate: number } | null;
  improvements: { rule: string; message: string }[];
}
