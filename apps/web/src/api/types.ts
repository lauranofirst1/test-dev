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
/** 진행 보드의 표현. 구조가 아니라 보여주는 방식이라 바꿔도 진행이 초기화되지 않습니다. */
export type BoardStyle = 'grid' | 'trail';
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

/** 참여자를 어떻게 식별하는가.
 *
 * 관광 축제는 지나가는 관광객에게 신원을 요구할 수 없어 익명이 옳고,
 * 교내 행사는 1인 1표와 공결 처리 때문에 학번이 필요합니다.
 */
export type IdentityMode = 'anonymous' | 'student_id';

export interface PublicFestival {
  id: number;
  name: string;
  region: string;
  venue: string;
  starts_on: string;
  ends_on: string;
  booths: PublicBooth[];
  /** 참여 시작 화면이 학번을 물어야 하는지 여기서 정해집니다. */
  identity_mode: IdentityMode;
  source_note: string;
  /** 하단 탭을 띄울지 정합니다. 없는데 띄우면 눌러도 "아직 없습니다" 만
   *  나오고, 죽은 링크가 있는 메뉴는 없는 메뉴보다 나쁩니다. */
  has_lectures: boolean;
  has_exhibits: boolean;
}

export interface ParticipantIssued {
  code: string;
  secret: string;
  festival_id: number;
  /** 이미 있던 학번이라 기존 참여를 이어받았는가. 화면 문구가 달라집니다. */
  resumed: boolean;
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
  board_style: BoardStyle;
  image_url: string;
  complete_message: string;
  tiles: BoardTile[];
  progress: BoardProgress;
  complete_message_shown: string | null;
}

export type ExperienceType = 'stamp' | 'quiz' | 'photo' | 'survey' | 'info';

/** 참여자에게 내려오는 퀴즈 설정. **정답(answer_index)은 오지 않습니다.** */
export interface QuizConfig {
  question: string;
  choices: string[];
  max_attempts: number;
  hint?: string;
}

export interface InfoConfig {
  body: string;
  links: { label: string; url: string }[];
  min_dwell_seconds: number;
}

/** 운영자 편집용 — 이쪽에는 정답이 있습니다. */
export interface QuizConfigAdmin extends QuizConfig {
  answer_index: number;
  /** 정답을 설명하는 글이라 사실상 정답입니다. 참여자 설정에는 담기지 않습니다. */
  explanation?: string;
}

export interface ScanContextMission {
  mission_id: number;
  title: string;
  description: string | null;
  points: number;
  already_granted: boolean;
  experience_type: ExperienceType;
  /** 정답이 빠진 설정. 유형에 따라 QuizConfig | InfoConfig | {} */
  experience_config: Record<string, unknown>;
  /** 남은 시도 횟수. 제한이 없는 유형이면 null. */
  attempts_left: number | null;
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
  /** 인쇄 QR 은 만료되지 않아 null. 그때는 카운트다운을 그리지 않습니다. */
  seconds_remaining: number | null;
  qr_mode: BoothQrMode;
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
    /** 지급까지 걸린 시도 횟수. 퀴즈에서만 1 보다 커집니다. */
    attempt_count: number;
  };
  revealed_tile: { tile_index: number; board_version: number } | null;
  board_progress: BoardProgress;
  /** 퀴즈 해설. 맞혔을 때만 내려옵니다 — 설정에는 담기지 않습니다. */
  explanation: string | null;
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
  experience_type: ExperienceType;
  /** **운영자 전용.** 퀴즈의 정답이 여기 들어 있습니다. */
  experience_config: Record<string, unknown>;
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

/** 격자 후보. 서버가 지급 단위 수를 보고 계산한다 (A안·B안·C안). */
export interface GridOption {
  rows: number;
  cols: number;
  total: number;
  /** 지급 단위 수와 정확히 맞는가 */
  exact: boolean;
  /** 조각을 못 받고 남는 지급 단위 수 */
  leftover: number;
}

/** 운영자 보드 조회. 완성 가능성 경고와 격자 후보를 서버가 판정해 내려준다. */
export interface StampBoardAdmin {
  id: number;
  festival_id: number;
  version: number;
  rows: number;
  cols: number;
  total_tiles: number;
  reveal_mode: RevealMode;
  grant_unit: GrantUnit;
  board_style: BoardStyle;
  /** 격자가 부스(또는 미션) 수를 계속 따라가는가. 직접 고르면 거짓이 됩니다. */
  grid_auto: boolean;
  image_url: string;
  complete_message: string;
  tiles: BoardTile[];
  warnings: Record<string, unknown>[];
  unit_count: number;
  unit_label: string;
  grid_options: GridOption[];
}


// ── 경품 뽑기 ────────────────────────────────────────────────────────────────

/** 참여자에게 보여줄 상품. **재고와 확률은 오지 않습니다.** */
export interface PrizePreview {
  name: string;
  description: string | null;
  is_blank: boolean;
}

export interface PrizeDrawResult {
  id: number;
  drawn_at: string;
  /** 뽑을 수 있는 상품이 하나도 없었으면 null. 꽝(is_blank)과 다릅니다. */
  prize_name: string | null;
  prize_description: string | null;
  is_blank: boolean;
  claimed_at: string | null;
}

export interface PrizeDrawStatus {
  /** 운영자가 상품을 하나라도 켰는가. false 면 화면에 카드를 그리지 않습니다. */
  enabled: boolean;
  can_draw: boolean;
  revealed_count: number;
  total_tiles: number;
  is_complete: boolean;
  draw: PrizeDrawResult | null;
  prizes: PrizePreview[];
}

/** 관객 화면이 주기적으로 물어보는 전부 — `GET /participants/me/overview`.
 *
 * 낱개 세 엔드포인트와 **같은 값**입니다. 셋을 따로 물으면 참여자 1명이
 * 초당 0.3 요청이 되고, 1000명 규모에서는 그것만으로 초당 300 요청입니다.
 */
export interface ParticipantOverview {
  board: ParticipantBoard;
  me: ParticipantMe;
  prize_draw: PrizeDrawStatus;
}

// ── 경품 (운영자) ────────────────────────────────────────────────────────────

export interface Prize {
  id: number;
  festival_id: number;
  name: string;
  description: string | null;
  /** null = 무제한. 꽝은 여기를 비웁니다. */
  stock: number | null;
  weight: number;
  is_blank: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PrizeList {
  items: Prize[];
  total: number;
  drawable_count: number;
  warnings: { code: string; message: string }[];
}

export interface PrizeDrawRow {
  id: number;
  participant_code: string;
  prize_id: number | null;
  prize_name: string | null;
  is_blank: boolean;
  drawn_at: string;
  claimed_at: string | null;
}

export interface PrizeDrawList {
  items: PrizeDrawRow[];
  total: number;
  /** 아직 실물을 안 가져간 당첨자 수. 꽝은 세지 않습니다. */
  unclaimed: number;
}


/** 부스 화면이 30초마다 다시 받아 QR 을 갱신합니다 — 계약 §8.2. */
export interface ScanTokenOut {
  booth_id: number;
  qr_mode: BoothQrMode;
  /** 오리진 없는 경로. **브라우저는 이걸 쓰고 자기 오리진을 앞에 붙입니다.** */
  scan_path: string;
  /** 서버가 짐작한 전체 주소. PUBLIC_WEB_ORIGIN 이 없으면 API 서버를 가리킵니다. */
  scan_url: string;
  /** 회전 QR 에서만 옵니다. */
  window_index: number | null;
  /** 이 QR 이 바뀌는 시각. 인쇄 QR 은 만료되지 않아 null 입니다. */
  expires_at: string | null;
  /** 다시 받아야 하는 주기(초). 인쇄 QR 은 null — 다시 받을 일이 없습니다. */
  refresh_after_seconds: number | null;
}


/** 수령대가 참여 코드로 찾은 결과.
 *
 * 못 건네는 경우(꽝·기수령·미뽑기)는 오류가 아니라 `claimable: false` + `reason`
 * 으로 옵니다. 스태프가 읽고 안내해야 하는 사실이기 때문입니다.
 */
export interface PrizeClaimLookup {
  participant_code: string;
  claimable: boolean;
  reason: string | null;
  draw: PrizeDrawRow | null;
}


// ── 특강 출결 ────────────────────────────────────────────────────────────────

export interface LectureSession {
  id: number;
  festival_id: number;
  title: string;
  speaker: string | null;
  affiliation: string | null;
  location: string | null;
  starts_at: string;
  ends_at: string;
  /** 출석 인정에 필요한 체크인 수. 열린 체크인 전부를 요구하지 않습니다. */
  required_checkins: number;
  grants_excused_absence: boolean;
  is_active: boolean;
}

export interface LectureSessionDetail extends LectureSession {
  opened_checkpoints: number;
  attendee_count: number;
  met_count: number;
}

export interface LectureSessionList {
  items: LectureSessionDetail[];
  total: number;
}

export interface Checkpoint {
  id: number;
  session_id: number;
  sequence: number;
  opens_at: string;
  closes_at: string;
  /** 지금 받고 있는가. 화면이 시각을 다시 판정하지 않게 서버가 정합니다. */
  is_open: boolean;
  checked_count: number;
}

/** 스크린에 띄울 회전 QR. **인쇄 QR 은 없습니다** — 사진이 돌면 출결이 무너집니다. */
export interface CheckpointToken {
  checkpoint_id: number;
  sequence: number;
  scan_path: string;
  scan_url: string;
  expires_at: string;
  closes_at: string;
  refresh_after_seconds: number;
}

export interface MyAttendance {
  session_id: number;
  title: string;
  starts_at: string;
  ends_at: string;
  grants_excused_absence: boolean;
  checked: number;
  required: number;
  /** 지금까지 열린 체크인 수. 몇 번을 놓쳤는지 스스로 알 수 있어야 합니다. */
  opened: number;
  is_met: boolean;
  remaining: number;
}

export interface CheckInResult {
  /** 방금 새로 찍혔는가. false 면 이미 찍혀 있었다는 뜻이고 오류가 아닙니다. */
  was_new: boolean;
  sequence: number;
  attendance: MyAttendance;
}

/** 공결 명단 한 줄. **학번이 여기에만 있습니다.** */
export interface RosterRow {
  participant_code: string;
  student_no: string | null;
  checked: number;
  required: number;
  is_met: boolean;
  /** 비밀 재발급 횟수. 남의 학번을 넣어 가로채려는 시도가 여기서 드러납니다. */
  recovery_attempts: number;
}

export interface Roster {
  session_id: number;
  title: string;
  opened_checkpoints: number;
  required_checkins: number;
  grants_excused_absence: boolean;
  rows: RosterRow[];
  met_count: number;
  total: number;
}


// ── 전시 심사 · 관객 투표 ────────────────────────────────────────────────────

export interface Exhibit {
  id: number;
  festival_id: number;
  /** 관객이 부르는 번호. "7번 작품" 으로 이야기합니다. */
  entry_no: number;
  title: string;
  team_name: string | null;
  summary: string | null;
  poster_url: string | null;
  tags: string[];
  location: string | null;
  is_active: boolean;
}

export interface ExhibitList {
  items: Exhibit[];
  total: number;
  /** 등록된 작품들이 쓴 태그 전체. 거르기 칩이 이걸 씁니다. */
  tags: string[];
}

export interface VoteCriterion {
  id: number;
  festival_id: number;
  label: string;
  description: string | null;
  max_score: number;
  /** 항목 간 상대 가중치. %가 아닙니다 — 항목 하나를 빼면 합이 100 이 아니게 됩니다. */
  weight: number;
  sort_order: number;
  is_active: boolean;
}

export interface MyScore {
  criterion_id: number;
  score: number;
  comment: string | null;
}

/** 심사위원이 보는 한 작품. **다른 심사위원의 점수는 오지 않습니다.** */
export interface JudgeSheet {
  exhibit: Exhibit;
  criteria: VoteCriterion[];
  my_scores: MyScore[];
  is_complete: boolean;
}

export interface JudgeProgress {
  total_exhibits: number;
  scored_exhibits: number;
  sheets: JudgeSheet[];
}

/** 관객이 보는 작품. **득표수가 오지 않습니다.** */
export interface PublicExhibit {
  id: number;
  entry_no: number;
  title: string;
  team_name: string | null;
  summary: string | null;
  poster_url: string | null;
  tags: string[];
  location: string | null;
  /** 내가 이 작품에 표를 줬는가. 자기 표는 남의 정보가 아닙니다. */
  voted: boolean;
}

export interface VotingStatus {
  voting_open: boolean;
  can_vote: boolean;
  /** 투표할 수 없다면 왜인지. 화면이 그대로 보여줄 문장입니다. */
  reason: string | null;
  votes_used: number;
  votes_limit: number;
  exhibits: PublicExhibit[];
  tags: string[];
}

export interface VoteResult {
  exhibit_id: number;
  voted: boolean;
  votes_used: number;
  votes_limit: number;
}

export interface CriterionResult {
  criterion_id: number;
  label: string;
  max_score: number;
  weight: number;
  /** 아무도 안 매겼으면 null. 0 과 다릅니다. */
  average: number | null;
  judge_count: number;
}

export interface ExhibitResult {
  exhibit: Exhibit;
  criteria: CriterionResult[];
  judge_count: number;
  votes: number;
  judge_score: number | null;
  audience_score: number | null;
  final_score: number | null;
}

/** 시상 근거. 최종 점수와 함께 그 점수가 나온 과정이 전부 옵니다. */
export interface ExhibitionResults {
  judge_weight_percent: number;
  audience_weight_percent: number;
  votes_limit: number;
  voting_open: boolean;
  items: ExhibitResult[];
  warnings: { code: string; message: string }[];
}


// ── 계정 · 세션 ──────────────────────────────────────────────────────────────

export interface AccountInfo {
  id: number;
  organization_id: number;
  email: string;
  display_name: string;
}

/** 세션은 **httpOnly 쿠키로** 옵니다. 본문에 토큰이 없습니다 —
 *  화면이 손에 쥘 수 없어야 XSS 로도 새지 않습니다. */
export interface AccountSession {
  account: AccountInfo;
  organization_name: string;
  expires_in: number;
}

export interface StaffInfo {
  id: number;
  festival_id: number;
  role: string;
  display_name: string;
  booth_id: number | null;
}

export interface StaffSession {
  access_token: string;
  expires_in: number;
  staff: StaffInfo;
}


// ── 스태프 발급 ──────────────────────────────────────────────────────────────

export type StaffRole = 'planner' | 'operator' | 'booth_manager' | 'judge';

export interface StaffRow {
  id: number;
  festival_id: number;
  role: StaffRole;
  display_name: string;
  booth_id: number | null;
  is_active: boolean;
  last_login_at: string | null;
  /** 지금 잠겨 있는가. 운영자가 "왜 못 들어오지" 를 바로 알 수 있어야 합니다. */
  locked_until: string | null;
  failed_attempts: number;
}

export interface StaffList {
  items: StaffRow[];
  total: number;
}

/** **평문 접근 코드는 이 응답에서만 옵니다.** 저장되는 것은 해시뿐이라
 *  서버도 다시 알아낼 수 없습니다. 잃어버리면 재발급이 유일한 길입니다. */
export interface StaffIssued {
  staff: { id: number; festival_id: number; role: StaffRole; display_name: string; booth_id: number | null };
  /** 오리진 없는 경로. **브라우저는 이걸 쓰고 자기 오리진을 붙입니다.** */
  invite_path: string;
  /** 서버가 짐작한 전체 주소. PUBLIC_WEB_ORIGIN 이 없으면 API 서버를 가리킵니다. */
  invite_url: string;
  access_code: string;
}

export interface PasswordResetAccepted {
  message: string;
  /** 메일 발송기가 아직 없다는 사실. 로컬에서만 채워집니다. */
  delivery_note: string | null;
}

// ── 운영 인사이트 ────────────────────────────────────────────────────────────

/** **혼잡도가 아닙니다.** QR/미션 완료 건수를 현장 참여량의 proxy 로 쓰는
 *  참여 편중 위험 지표입니다. 화면 문구도 "여유/주의/집중" 으로 부르고
 *  "한산/혼잡" 이라는 말을 쓰지 않습니다. */
export type BoothLoadStatus = 'INSUFFICIENT_DATA' | 'LOW' | 'CAUTION' | 'HIGH';

export type RecommendationType = 'REDISTRIBUTE' | 'NO_ACTIVITY';

export interface BoothLoad {
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
  /** 판정 근거 문장. 화면이 비율을 다시 계산하지 않는다. */
  status_reason: string;
  status_label: string;
  last_completed_at: string | null;
}

/** 상황 · 판단 근거 · 권장 행동이 **나뉘어** 옵니다.
 *  한 문단으로 합치면 근거와 지시가 섞여 "데이터가 그렇다니 하라는 대로" 읽힙니다. */
export interface Recommendation {
  type: RecommendationType;
  situation: string;
  evidence: string;
  action: string;
  target_booth_id: number | null;
}

/** 당일 화면의 시간대 그래프. **빈 칸도 0 으로 들어 있습니다** —
 *  화면이 구멍을 메우게 두면 없던 시간이 완만한 하강으로 그려집니다. */
/** 통합 검색. **참여자 secret 은 이 응답에 자리가 없습니다** —
 *  코드는 부스에서 보여주는 값이지만 secret 은 남의 수집 현황을 여는 열쇠입니다. */
export interface SearchHit {
  kind: 'booth' | 'mission' | 'exhibit' | 'participant';
  id: number;
  title: string;
  subtitle: string | null;
}

export interface SearchResult {
  query: string;
  /** 몇 글자부터 찾는지. 화면이 같은 숫자를 따로 들고 있지 않게 합니다. */
  min_query: number;
  /** 종류마다 상한이 있습니다. 잘렸으면 화면이 그 사실을 말해야 합니다. */
  truncated: boolean;
  hits: SearchHit[];
}

export interface TimelinePoint {
  /** 칸의 **시작** 시각(UTC ISO). 화면이 자기 시간대로 찍습니다. */
  at: string;
  completions: number;
}

export interface OperationsTimeline {
  bucket_minutes: number;
  window_hours: number;
  /** 가장 높은 칸. 화면이 다시 훑지 않게 서버가 함께 냅니다. */
  peak: number;
  points: TimelinePoint[];
}

export interface Insights {
  generated_at: string;
  kpi: {
    total_participants: number;
    total_completions: number;
    completions_last_30m: number;
    high_concentration_booths: number;
  };
  booths: BoothLoad[];
  recommendations: Recommendation[];
  warnings: { code: string; message: string }[];
  disclaimer: string;
}

// ── 보상 캠페인 ──────────────────────────────────────────────────────────────

/** **경품과 다른 물건입니다.** 경품은 보드를 완성한 사람에게 주는 실물이고,
 *  캠페인은 특정 부스의 미션 포인트를 정해진 시간 동안만 올리는 장치입니다. */
export interface Campaign {
  id: number;
  festival_id: number;
  booth_id: number;
  booth_name: string;
  mission_id: number | null;
  mission_title: string | null;
  title: string;
  message: string;
  bonus_points: number;
  starts_at: string;
  ends_at: string;
  is_active: boolean;
  /** **서버 시각** 판정 결과. 화면이 다시 계산하지 않습니다 —
   *  폰 시계가 틀어진 만큼 끝난 캠페인이 계속 떠 있게 됩니다. */
  is_live: boolean;
}

export interface CampaignList {
  items: Campaign[];
  total: number;
}

export interface ImpactWindow {
  from: string;
  to: string;
  target_completions: number;
  festival_completions: number;
  share: number;
}

export interface CampaignImpact {
  campaign_id: number;
  window_minutes: number;
  before: ImpactWindow;
  after: ImpactWindow;
  share_change_pp: number;
  /** before 가 0건이면 null. 0 을 분모로 배수를 만들지 않습니다. */
  completion_change_rate: number | null;
  top_booth_before: {
    booth_id: number;
    name: string;
    share_before: number;
    share_after: number;
  } | null;
  data_status: 'SUFFICIENT' | 'INSUFFICIENT_DATA';
  in_progress: boolean;
  disclaimer: string;
}

// ── 사후 리포트 ──────────────────────────────────────────────────────────────

export type VisitorSource =
  | 'beacon'
  | 'manual_counter'
  | 'partner'
  | 'estimate'
  | 'kto_bigdata';

export interface KpiTarget {
  id: number;
  metric_key: string;
  label: string;
  target_value: number;
  unit: string;
  /** **운영자가 정하지 않습니다.** 측정 가능 여부는 지표의 성질입니다. */
  is_measurable: boolean;
}

export interface KpiTargetList {
  items: KpiTarget[];
  /** 아직 안 세운 기본 지표. 화면이 목록을 하드코딩하지 않게 서버가 줍니다. */
  available: { metric_key: string; label: string; unit: string; is_measurable: boolean }[];
}

export interface VisitorCount {
  id: number;
  count_date: string;
  visitors: number;
  source: VisitorSource;
  source_label: string;
  note: string | null;
}

export interface VisitorCountList {
  items: VisitorCount[];
  /** 날짜별로 우선순위가 높은 출처 하나씩만 더한 값. 단순 합계가 아닙니다. */
  total_visitors: number;
}

export interface FestivalReport {
  festival_id: number;
  festival_name: string;
  generated_at: string;
  summary: {
    unique_participants: number;
    total_completions: number;
    avg_completions_per_participant: number;
    missions_with_completion: { count: number; total: number; ratio: number };
  };
  plan_vs_actual: {
    expected_visitors: number;
    festaflow_participants: number;
    participation_scale: number;
    disclaimer: string;
  };
  /** 실측이 없으면 null. 없는 참여율을 만들어 내지 않습니다. */
  visitor_basis: {
    visitors: number;
    source: VisitorSource;
    source_label: string;
    caveat: string | null;
    participation_rate: number;
    others: { source_label: string; visitors: number }[];
  } | null;
  timeline: { hour_kst: string; completions: number }[];
  booths: {
    booth_id: number;
    name: string;
    completions: number;
    unique_participants: number;
    share: number;
    rank: number;
    peak_hour_kst: string | null;
    peak_completions: number;
  }[];
  missions: {
    mission_id: number;
    title: string;
    booth_name: string | null;
    completions: number;
    unique_participants: number;
    share: number;
  }[];
  unassigned_completions: number;
  kpi: {
    metric_key: string;
    label: string;
    target: number;
    actual: number | null;
    /** `measurable: false` 면 항상 null. */
    achievement: number | null;
    measurable: boolean;
    unit: string;
    note: string | null;
  }[];
  recommendation_accuracy: { total: number; hits: number; rate: number } | null;
  campaigns: {
    campaign_id: number;
    title: string;
    booth_name: string;
    share_change_pp: number;
    data_status: string;
    in_progress: boolean;
  }[];
  improvements: { rule: string; message: string }[];
}

// ── 현장 공지 ────────────────────────────────────────────────────────────────

export type AnnouncementChannel = 'audience' | 'staff' | 'both';
export type AnnouncementLevel = 'normal' | 'urgent';

export interface Announcement {
  id: number;
  channel: AnnouncementChannel;
  level: AnnouncementLevel;
  title: string;
  body: string;
  starts_at: string;
  ends_at: string | null;
  is_active: boolean;
  /** **서버 시각** 판정. 화면이 다시 계산하지 않습니다. */
  is_live: boolean;
  /** 긴급 공지를 확인한 인원. 띄운 것과 전달된 것은 다릅니다. */
  ack_count: number;
}

export interface AnnouncementList {
  items: Announcement[];
  total: number;
}

export interface LiveAnnouncement {
  id: number;
  level: AnnouncementLevel;
  title: string;
  body: string;
  starts_at: string;
  /** 이 사람이 이미 확인했는가. 긴급 덮개를 다시 씌울지 정합니다. */
  acked: boolean;
}

export interface LiveAnnouncementList {
  /** 긴급이 먼저 옵니다. 첫 건이 곧 덮개 후보입니다. */
  items: LiveAnnouncement[];
}

// ── 부스 지급 ────────────────────────────────────────────────────────────────

/** 지금 로그인한 스태프. 새로고침 뒤에도 자기 부스를 알기 위해 조회합니다.
 *  **토큰은 들어 있지 않습니다** — 조회 응답에 토큰이 실리면 httpOnly 로 둔 뜻이 없습니다. */
export interface StaffMe {
  id: number;
  festival_id: number;
  role: StaffRole;
  display_name: string;
  booth_id: number | null;
}

export interface RecentGrant {
  participation_id: number;
  participant_code: string;
  mission_title: string | null;
  granted_points: number;
  completed_at: string | null;
}

// ── 공결 확인서 ──────────────────────────────────────────────────────────────

/** 학생이 교수님에게 건네는 확인 코드. **코드 자체가 비밀입니다.** */
export interface CertificateIssued {
  session_id: number;
  title: string;
  code: string;
  /** 오리진 없는 경로. 브라우저가 자기 오리진을 붙입니다. */
  verify_path: string;
}

/** 교수님이 보는 확인 결과. 인증 없이 열립니다. */
export interface CertificateVerified {
  festival_name: string;
  title: string;
  speaker: string | null;
  starts_at: string;
  ends_at: string;
  /** 뒷 세 자리만. 명단 수집이 아니라 본인 확인이 목적입니다. */
  student_no_masked: string | null;
  participant_code: string;
  checked: number;
  opened: number;
  required: number;
  is_met: boolean;
  grants_excused_absence: boolean;
  /** 스냅샷이 아니라 **지금** 조회한 결과입니다. */
  verified_at: string;
}
