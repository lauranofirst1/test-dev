/**
 * API 응답 타입.
 *
 * 백엔드(apps/api)가 계약의 원천입니다. 여기서 임의로 바꾸지 말고,
 * 계약이 틀렸다고 판단되면 "계약 이슈"로 보고하세요.
 */

export type RiskLevel = 'stable' | 'caution' | 'risk';
export type Fulfillment = 'met' | 'partial' | 'unmet';

export type DiagnosisCategory =
  | 'tourism_demand'
  | 'crowd_safety'
  | 'program_balance'
  | 'local_linkage'
  | 'ops_readiness';

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
  starts_on: string;
  ends_on: string;
  expected_visitors: number;
  total_budget: number;
  status: string;
  plan_stage: string;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface FestivalDetail extends Festival {
  plan: FestivalPlan | null;
  duration_days: number;
  booth_count: number;
  mission_count: number;
}

export interface FestivalList {
  items: Festival[];
  total: number;
}

export interface DiagnosisItem {
  category: DiagnosisCategory;
  /** checklist 모드에서는 null */
  score: number | null;
  max_score: number | null;
  level: RiskLevel;
  fulfillment: Fulfillment;
  reason: string;
  recommendation: string;
  details: Record<string, unknown>;
}

export interface TourismSource {
  provider: string;
  base_month: string;
  /** 지표별 조회/추정 구분 */
  indicators: Record<string, string>;
  note: string;
}

export interface Diagnosis {
  id: number;
  festival_id: number;
  status: string;
  rubric_version: string;
  display_mode: 'score' | 'checklist';
  score_disclosed: boolean;
  total_score: number | null;
  risk: RiskLevel | null;
  items: DiagnosisItem[];
  top_risks: string[];
  warnings: string[];
  tourism_source: TourismSource | null;
  /** 점수를 보여줄 때 화면에 반드시 함께 표시해야 하는 문구 */
  disclosure_note: string | null;
  api_calls: number | null;
  created_at: string;
}

export interface DiagnosisDelta {
  category: DiagnosisCategory;
  previous: number | null;
  current: number | null;
  delta: number | null;
}

export interface DiagnosisComparison {
  comparable: boolean;
  reason: string | null;
  previous: { id: number; total_score: number | null; risk: string | null; created_at: string } | null;
  current: { id: number; total_score: number | null; risk: string | null; created_at: string } | null;
  delta: number | null;
  items: DiagnosisDelta[];
  biggest_improvement: {
    category: string;
    label: string;
    delta: number;
    reason: string;
    recommendation: string;
  } | null;
}

export const CATEGORY_LABEL: Record<DiagnosisCategory, string> = {
  tourism_demand: '관광수요 적합성',
  crowd_safety: '혼잡·수용 안정성',
  program_balance: '프로그램 균형',
  local_linkage: '지역 관광 연계성',
  ops_readiness: '운영 준비도',
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  stable: '안정',
  caution: '주의',
  risk: '위험',
};

export const FULFILLMENT_LABEL: Record<Fulfillment, string> = {
  met: '충족',
  partial: '부분 충족',
  unmet: '미충족',
};

// ── 관객(참여자) 화면 — 계약 §7~§9 ──────────────────────────────────────────

export type BoothVerifyMode = 'staff_scan' | 'participant_scan';
export type RevealMode = 'random' | 'booth_assigned';
export type GrantUnit = 'booth' | 'mission';

export interface PublicMission {
  id: number;
  booth_id: number | null;
  title: string;
  description: string | null;
  points: number;
}

export interface PublicBooth {
  id: number;
  name: string;
  booth_type: string;
  type_label: string | null;
  location: string | null;
  verify_mode: BoothVerifyMode;
  missions: PublicMission[];
}

export interface PublicFestival {
  id: number;
  name: string;
  region: string;
  venue: string;
  starts_on: string;
  ends_on: string;
  booths: PublicBooth[];
  source_note: string;
}

export interface ParticipantIssued {
  code: string;
  secret: string;
  festival_id: number;
}

export interface MissionStatus {
  mission_id: number;
  booth_id: number | null;
  booth_name: string | null;
  title: string;
  points: number;
  status: 'pending' | 'granted';
  granted_points: number | null;
  completed_at: string | null;
}

export interface ActiveCampaign {
  id: number;
  booth_id: number;
  mission_id: number | null;
  title: string;
  message: string;
  bonus_points: number;
  ends_at: string;
}

export interface ParticipantMe {
  code: string;
  festival_id: number;
  total_points: number;
  completed_count: number;
  missions: MissionStatus[];
  active_campaigns: ActiveCampaign[];
}

export interface BoardTile {
  tile_index: number;
  assigned_booth_id: number | null;
  is_revealed: boolean;
  revealed_at: string | null;
}

export interface BoardProgress {
  revealed_count: number;
  total_tiles: number;
  is_complete: boolean;
}

export interface ParticipantBoard {
  id: number;
  festival_id: number;
  version: number;
  rows: number;
  cols: number;
  total_tiles: number;
  reveal_mode: RevealMode;
  grant_unit: GrantUnit;
  image_url: string;
  complete_message: string;
  tiles: BoardTile[];
  progress: BoardProgress;
  complete_message_shown: string | null;
}

export interface ScanContextMission {
  mission_id: number;
  title: string;
  description: string | null;
  points: number;
  already_granted: boolean;
}

export interface ScanContext {
  booth_id: number;
  booth_name: string;
  type_label: string | null;
  location: string | null;
  window_index: number;
  /** QR 이 부스 화면에서 갱신되는 시각. */
  expires_at: string;
  /** 서버가 실제로 받아주는 마지막 시각. 직전 window 까지 인정하므로 이쪽이 더 늦다. */
  accepted_until: string;
  seconds_remaining: number;
  missions: ScanContextMission[];
  scan_already_used: boolean;
}

export interface GrantResult {
  was_already_granted: boolean;
  participation: {
    id: number;
    mission_id: number | null;
    booth_id: number | null;
    base_points: number;
    bonus_points: number;
    granted_points: number;
    reward_campaign_id: number | null;
    verified_via: BoothVerifyMode | null;
    completed_at: string | null;
  };
  revealed_tile: { tile_index: number; board_version: number } | null;
  board_progress: BoardProgress;
}

// ── 부스 · 미션 (운영자) ─────────────────────────────────────────────────────

export type BoothType =
  | 'food'
  | 'experience'
  | 'performance'
  | 'information'
  | 'local_shop'
  | 'etc';

export type BoothQrMode = 'printed' | 'rotating';

export interface MissionOut {
  id: number;
  festival_id: number;
  booth_id: number | null;
  title: string;
  description: string | null;
  points: number;
  is_active: boolean;
  experience_type: string;
  created_at: string;
  updated_at: string;
}

export interface BoothDetail {
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
  created_at: string;
  updated_at: string;
  missions: MissionOut[];
}

export interface BoothList {
  items: BoothDetail[];
  total: number;
}

/** 운영자 보드 조회. 완성 가능성 경고를 서버가 판정해 내려준다. */
export interface StampBoardAdmin {
  id: number;
  festival_id: number;
  version: number;
  rows: number;
  cols: number;
  total_tiles: number;
  reveal_mode: RevealMode;
  grant_unit: GrantUnit;
  image_url: string;
  complete_message: string;
  tiles: BoardTile[];
  warnings: Record<string, unknown>[];
}
