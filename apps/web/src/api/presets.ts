/**
 * 샘플 기획안 3종.
 *
 * 날짜는 **버튼을 누른 시점 기준 미래 날짜**로 계산합니다.
 * 고정 날짜를 박아두면 시간이 지나 과거 축제가 되고,
 * 진단의 계절 적합도가 엉뚱한 달을 보게 됩니다.
 *
 * 진단이 실제로 소비하는 필드를 전부 채웁니다 — 인력·안전/교통/혼잡 계획이
 * 비어 있으면 운영 준비도가 낮게 나오고, planned_* 가 비면 프로그램 균형이
 * 예정값 기준으로도 평가되지 않습니다.
 */

export interface PresetForm {
  name: string;
  region: string;
  venue: string;
  starts_on: string;
  ends_on: string;
  expected_visitors: string;
  total_budget: string;
  summary: string;
  core_audience: string;
  venue_capacity: string;
  staff_count: string;
  volunteer_count: string;
  safety_staff_count: string;
  parking_capacity: string;
  planned_performance: string;
  planned_experience: string;
  planned_food: string;
  planned_local_shop: string;
  planned_tour_info: string;
  planned_etc: string;
  safety_plan: string;
  traffic_plan: string;
  crowd_plan: string;
}

export const EMPTY_FORM: PresetForm = {
  name: '',
  region: '',
  venue: '',
  starts_on: '',
  ends_on: '',
  expected_visitors: '',
  total_budget: '',
  summary: '',
  core_audience: '',
  venue_capacity: '',
  staff_count: '',
  volunteer_count: '',
  safety_staff_count: '',
  parking_capacity: '',
  planned_performance: '',
  planned_experience: '',
  planned_food: '',
  planned_local_shop: '',
  planned_tour_info: '',
  planned_etc: '',
  safety_plan: '',
  traffic_plan: '',
  crowd_plan: '',
};

/** 오늘로부터 N일 뒤 날짜를 YYYY-MM-DD 로. */
function future(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export interface Preset {
  id: string;
  label: string;
  tagline: string;
  /** 이 프리셋이 진단에서 어떤 결과를 보여주려는지 */
  note: string;
  build: () => PresetForm;
}

export const PRESETS: Preset[] = [
  {
    id: 'local-food',
    label: '지역 먹거리·문화 축제',
    tagline: '18,000명 · 3일',
    note: '관광·상권·문화가 균형 잡힌 구성. 표준적인 지역 축제 형태입니다.',
    build: () => ({
      ...EMPTY_FORM,
      name: '춘천 가을 먹거리 축제',
      region: '강원특별자치도 춘천시',
      venue: '공지천 조각공원',
      starts_on: future(60),
      ends_on: future(62),
      expected_visitors: '18000',
      total_budget: '240000000',
      summary: '지역 식재료와 로컬 뮤지션이 만나는 3일',
      core_audience: '가족 단위 방문객, 20~30대',
      venue_capacity: '4000',
      staff_count: '30',
      volunteer_count: '20',
      safety_staff_count: '10',
      parking_capacity: '400',
      planned_performance: '6',
      planned_experience: '8',
      planned_food: '12',
      planned_local_shop: '6',
      planned_tour_info: '2',
      planned_etc: '2',
      safety_plan: '권역별 안전요원 2인 배치, 야간 조명 보강, 응급 대응소 1개소 운영',
      traffic_plan: '셔틀버스 20분 간격 운행, 임시 주차장 3곳, 인근 공영주차장 연계',
      crowd_plan: '무대 앞 구역 인원 상한 운영, 피크 시간대 입장 분산 안내',
    }),
  },
  {
    id: 'youth-night',
    label: '청년 음악·야간 축제',
    tagline: '20,000명 · 2일 · 야간',
    note: '공연 중심이라 무대 앞 밀집이 큽니다. 혼잡·수용 항목이 낮게 나오는 구성입니다.',
    build: () => ({
      ...EMPTY_FORM,
      name: '한강 나이트 뮤직 페스타',
      region: '서울특별시 영등포구',
      venue: '여의도 한강공원 물빛무대',
      starts_on: future(45),
      ends_on: future(46),
      expected_visitors: '20000',
      total_budget: '380000000',
      summary: '해가 진 뒤 시작되는 이틀간의 도심 음악 축제',
      core_audience: '20~30대 음악 팬',
      venue_capacity: '5000',
      staff_count: '45',
      volunteer_count: '15',
      safety_staff_count: '25',
      parking_capacity: '200',
      planned_performance: '14',
      planned_experience: '3',
      planned_food: '10',
      planned_local_shop: '2',
      planned_tour_info: '1',
      planned_etc: '3',
      safety_plan: '야간 조도 확보, 무대 전방 압사 방지 구역 설정, 의무실 2개소',
      traffic_plan: '심야 셔틀 1시간 연장, 지하철 막차 연계 안내, 택시 승강장 별도 운영',
      crowd_plan: '',
    }),
  },
  {
    id: 'family',
    label: '가족 체험형 축제',
    tagline: '8,000명 · 2일',
    note: '체험 중심에 규모가 작아 여유가 큽니다. 대부분 항목이 높게 나옵니다.',
    build: () => ({
      ...EMPTY_FORM,
      name: '순천만 가족 자연놀이터',
      region: '전라남도 순천시',
      venue: '순천만국가정원 잔디마당',
      starts_on: future(75),
      ends_on: future(76),
      expected_visitors: '8000',
      total_budget: '120000000',
      summary: '아이와 함께 하루를 보내는 자연 체험 축제',
      core_audience: '미취학~초등 자녀 동반 가족',
      venue_capacity: '3000',
      staff_count: '22',
      volunteer_count: '30',
      safety_staff_count: '12',
      parking_capacity: '600',
      planned_performance: '3',
      planned_experience: '14',
      planned_food: '6',
      planned_local_shop: '4',
      planned_tour_info: '2',
      planned_etc: '4',
      safety_plan: '미아 방지 손목밴드 배포, 어린이 안전요원 상주, 그늘 쉼터 6곳',
      traffic_plan: '주차장 3곳 분산, 유모차 동선 확보, 정문 진입 일방통행',
      crowd_plan: '체험 부스 사전예약제, 시간대별 입장 인원 제한',
    }),
  },
];
