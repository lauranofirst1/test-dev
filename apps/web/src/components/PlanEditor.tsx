/** 축제 기획 수정 — 진단 → 교정 → 재진단 루프의 가운데 고리.
 *
 * ## 이 화면이 없으면 진단이 반쪽이다
 *
 * 진단 화면에는 「다시 진단하기」와 직전 대비 비교 차트가 이미 있습니다.
 * 그런데 기획을 고칠 수단이 없으면 재진단해도 **같은 입력에 같은 점수**가
 * 나옵니다. "무엇을 고치면 점수가 오르는가" 를 보여주고 고칠 곳을 주지 않는
 * 것은 진단이 아니라 채점입니다.
 *
 * ## 생성 폼과 필드가 다르다
 *
 * 생성 폼은 빨리 시작하는 것이 목적이라 최소한만 받습니다. 이 화면은
 * **기획서 전체**를 다룹니다 — 특히 지역 관광 연계 4개 항목은 DB·스키마·PUT
 * 이 전부 서 있는데 입력칸이 없어 지금까지 한 번도 채워진 적이 없습니다.
 *
 * ## 부분 저장이 아니다
 *
 * `PUT` 은 기획 전체를 덮어씁니다. 그래서 화면이 **서버 값을 먼저 읽어 폼을
 * 채우고** 그 위에서 고칩니다. 빈 폼에서 시작해 보내면 안 채운 칸이 전부
 * 지워집니다 — 저장 한 번에 남의 작업이 사라지는 사고가 여기서 납니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { FestivalDetail } from '../api/types';

/** 빈 문자열은 `null` 로 보낸다. `""` 를 그대로 보내면 "입력했는데 비어 있음" 과
 *  "입력하지 않음" 이 구분되지 않고, 진단의 부족 항목 판정이 흔들린다. */
const text = (v: string) => (v.trim() ? v.trim() : null);
const num = (v: string) => (v.trim() === '' ? null : Number(v));

interface Draft {
  name: string;
  region: string;
  venue: string;
  starts_on: string;
  ends_on: string;
  expected_visitors: string;
  total_budget: string;
  summary: string;
  description: string;
  core_audience: string;
  purposes: string;
  target_segments: string;
  staff_count: string;
  volunteer_count: string;
  safety_staff_count: string;
  parking_capacity: string;
  venue_capacity: string;
  planned_performance: string;
  planned_experience: string;
  planned_food: string;
  planned_local_shop: string;
  planned_tour_info: string;
  planned_etc: string;
  transit_access: string;
  traffic_plan: string;
  crowd_plan: string;
  safety_plan: string;
  tourism_link_plan: string;
  local_commerce_plan: string;
  lodging_plan: string;
  promotion_plan: string;
}

const EMPTY: Draft = {
  name: '', region: '', venue: '', starts_on: '', ends_on: '',
  expected_visitors: '', total_budget: '', summary: '', description: '',
  core_audience: '', purposes: '', target_segments: '', staff_count: '',
  volunteer_count: '', safety_staff_count: '', parking_capacity: '',
  venue_capacity: '', planned_performance: '', planned_experience: '',
  planned_food: '', planned_local_shop: '', planned_tour_info: '',
  planned_etc: '', transit_access: '', traffic_plan: '', crowd_plan: '',
  safety_plan: '', tourism_link_plan: '', local_commerce_plan: '',
  lodging_plan: '', promotion_plan: '',
};

/** 서버 값으로 폼을 채운다. 여기서 빠뜨린 필드는 저장할 때 **지워진다.** */
function draftOf(f: FestivalDetail): Draft {
  const p = f.plan ?? ({} as NonNullable<FestivalDetail['plan']>);
  const s = (v: unknown) => (v === null || v === undefined ? '' : String(v));
  return {
    name: f.name,
    region: f.region,
    venue: f.venue,
    starts_on: f.starts_on,
    ends_on: f.ends_on,
    expected_visitors: s(f.expected_visitors),
    total_budget: s(f.total_budget),
    summary: s(p.summary),
    description: s(p.description),
    core_audience: s(p.core_audience),
    purposes: (p.purposes ?? []).join(', '),
    target_segments: (p.target_segments ?? []).join(', '),
    staff_count: s(p.staff_count),
    volunteer_count: s(p.volunteer_count),
    safety_staff_count: s(p.safety_staff_count),
    parking_capacity: s(p.parking_capacity),
    venue_capacity: s(p.venue_capacity),
    planned_performance: s(p.planned_performance),
    planned_experience: s(p.planned_experience),
    planned_food: s(p.planned_food),
    planned_local_shop: s(p.planned_local_shop),
    planned_tour_info: s(p.planned_tour_info),
    planned_etc: s(p.planned_etc),
    transit_access: s(p.transit_access),
    traffic_plan: s(p.traffic_plan),
    crowd_plan: s(p.crowd_plan),
    safety_plan: s(p.safety_plan),
    tourism_link_plan: s(p.tourism_link_plan),
    local_commerce_plan: s(p.local_commerce_plan),
    lodging_plan: s(p.lodging_plan),
    promotion_plan: s(p.promotion_plan),
  };
}

/** 쉼표로 나눠 목록으로. 빈 항목은 버린다. */
const list = (v: string) =>
  v.split(',').map((x) => x.trim()).filter(Boolean);

/** 기획 편집 폼.
 *
 * **화면이 아니라 탭입니다.** 진단 → 교정 → 재진단이 이 제품의 핵심 루프인데
 * 예전에는 진단과 수정이 별개 화면이라, 점수를 보고 고치러 가면 점수가 화면에서
 * 사라졌습니다. 무엇을 고쳐야 점수가 오르는지 보면서 고칠 수 없었습니다.
 *
 * 그래서 폼만 떼어 `DiagnosisPage` 의 탭으로 들어갑니다. 점수 요약은 탭 위에
 * 남아 있어, 고치는 동안에도 지금 점수가 보입니다.
 */
export function PlanEditor({ onSaved }: { onSaved?: () => void }) {
  const { id = '' } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [form, setForm] = useState<Draft>(EMPTY);
  const [loaded, setLoaded] = useState(false);

  const festival = useQuery({
    queryKey: ['festival', id],
    queryFn: () => api.get<FestivalDetail>(`/api/festivals/${id}`),
    retry: false,
  });

  // 서버 값이 도착하면 폼을 채운다. **한 번만** — 저장 뒤 캐시가 갱신될 때
  // 다시 채우면 사용자가 이어서 고치던 값이 서버 값으로 되돌아간다.
  useEffect(() => {
    if (festival.data && !loaded) {
      setForm(draftOf(festival.data));
      setLoaded(true);
    }
  }, [festival.data, loaded]);

  const save = useMutation({
    mutationFn: () =>
      api.put(`/api/festivals/${id}`, {
        name: form.name.trim(),
        region: form.region.trim(),
        venue: form.venue.trim(),
        starts_on: form.starts_on,
        ends_on: form.ends_on,
        expected_visitors: Number(form.expected_visitors) || 0,
        total_budget: Number(form.total_budget) || 0,
        plan: {
          summary: text(form.summary),
          description: text(form.description),
          core_audience: text(form.core_audience),
          purposes: list(form.purposes),
          target_segments: list(form.target_segments),
          staff_count: num(form.staff_count),
          volunteer_count: num(form.volunteer_count),
          safety_staff_count: num(form.safety_staff_count),
          parking_capacity: num(form.parking_capacity),
          venue_capacity: num(form.venue_capacity),
          planned_performance: num(form.planned_performance) ?? 0,
          planned_experience: num(form.planned_experience) ?? 0,
          planned_food: num(form.planned_food) ?? 0,
          planned_local_shop: num(form.planned_local_shop) ?? 0,
          planned_tour_info: num(form.planned_tour_info) ?? 0,
          planned_etc: num(form.planned_etc) ?? 0,
          transit_access: text(form.transit_access),
          traffic_plan: text(form.traffic_plan),
          crowd_plan: text(form.crowd_plan),
          safety_plan: text(form.safety_plan),
          tourism_link_plan: text(form.tourism_link_plan),
          local_commerce_plan: text(form.local_commerce_plan),
          lodging_plan: text(form.lodging_plan),
          promotion_plan: text(form.promotion_plan),
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['festival', id] });
      qc.invalidateQueries({ queryKey: ['festivals'] });
      // 고쳤으면 다시 진단해 봐야 한다. 그게 이 탭의 존재 이유다 —
      // 점수 탭으로 돌려보내고, 거기서 «다시 진단하기» 가 기다린다.
      onSaved?.();
    },
  });

  const set = (key: keyof Draft) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const err = save.error instanceof ApiError ? save.error : null;

  if (festival.isLoading) {
    return <div className="skeleton" style={{ height: 320 }} />;
  }

  return (
    <div className="stack" style={{ gap: 'var(--space-5)' }}>
      <p className="muted">
        고치고 저장하면 점수 탭으로 돌아갑니다. 거기서 다시 진단하면 무엇이
        달라졌는지 직전 결과와 나란히 비교됩니다.
      </p>

      {err && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{err.message}</span>
        </div>
      )}

      <Section title="기본" hint="진단의 규모·기간 판정에 쓰입니다.">
        <Field label="축제명" id="f-name" value={form.name} onChange={set('name')} />
        <div className="grid2">
          <Field label="지역" id="f-region" value={form.region} onChange={set('region')} />
          <Field label="장소" id="f-venue" value={form.venue} onChange={set('venue')} />
        </div>
        <div className="grid2">
          <Field label="시작일" id="f-start" type="date" value={form.starts_on} onChange={set('starts_on')} />
          <Field label="종료일" id="f-end" type="date" value={form.ends_on} onChange={set('ends_on')} />
        </div>
        <div className="grid2">
          <Field
            label="예상 방문객"
            id="f-visitors"
            type="number"
            value={form.expected_visitors}
            onChange={set('expected_visitors')}
            hint="FestaFlow 가 측정하는 값이 아니라 기획 목표입니다."
          />
          <Field label="총예산 (원)" id="f-budget" type="number" value={form.total_budget} onChange={set('total_budget')} />
        </div>
      </Section>

      <Section title="개요" hint="무엇을 하는 축제인지. 진단 점수에는 들어가지 않지만 기획서의 뼈대입니다.">
        <Field label="한 줄 요약" id="f-summary" value={form.summary} onChange={set('summary')} />
        <Area label="설명" id="f-desc" value={form.description} onChange={set('description')} />
        <Field label="핵심 관객" id="f-core" value={form.core_audience} onChange={set('core_audience')} placeholder="20~30대 지역 주민" />
        <div className="grid2">
          <Field label="개최 목적" id="f-purposes" value={form.purposes} onChange={set('purposes')} hint="쉼표로 구분" placeholder="지역 상권 활성화, 관광객 유치" />
          <Field label="타깃 세그먼트" id="f-targets" value={form.target_segments} onChange={set('target_segments')} hint="쉼표로 구분" placeholder="가족, 청년, 외지 관광객" />
        </div>
      </Section>

      <Section title="운영 인력과 수용" hint="혼잡·수용 안정성과 운영 준비도 점수의 근거입니다.">
        <div className="grid2">
          <Field label="동시 수용 인원" id="f-cap" type="number" value={form.venue_capacity} onChange={set('venue_capacity')} hint="배치도가 없는 지금, 수용력 판정의 1순위 근거입니다." />
          <Field label="주차 대수" id="f-park" type="number" value={form.parking_capacity} onChange={set('parking_capacity')} />
        </div>
        <div className="grid3">
          <Field label="운영 인력" id="f-staff" type="number" value={form.staff_count} onChange={set('staff_count')} />
          <Field label="자원봉사" id="f-vol" type="number" value={form.volunteer_count} onChange={set('volunteer_count')} />
          <Field label="안전 인력" id="f-safe" type="number" value={form.safety_staff_count} onChange={set('safety_staff_count')} />
        </div>
      </Section>

      <Section title="프로그램 구성" hint="유형이 한쪽으로 몰리면 프로그램 균형 점수가 깎입니다.">
        <div className="grid3">
          <Field label="공연" id="f-perf" type="number" value={form.planned_performance} onChange={set('planned_performance')} />
          <Field label="체험" id="f-exp" type="number" value={form.planned_experience} onChange={set('planned_experience')} />
          <Field label="먹거리" id="f-food" type="number" value={form.planned_food} onChange={set('planned_food')} />
          <Field label="지역상점" id="f-shop" type="number" value={form.planned_local_shop} onChange={set('planned_local_shop')} />
          <Field label="관광안내" id="f-info" type="number" value={form.planned_tour_info} onChange={set('planned_tour_info')} />
          <Field label="기타" id="f-etc" type="number" value={form.planned_etc} onChange={set('planned_etc')} />
        </div>
      </Section>

      <Section title="교통 · 혼잡 · 안전" hint="비어 있으면 운영 준비도에서 부족 항목으로 잡힙니다.">
        <Area label="대중교통 접근성" id="f-transit" value={form.transit_access} onChange={set('transit_access')} />
        <Area label="교통 대책" id="f-traffic" value={form.traffic_plan} onChange={set('traffic_plan')} />
        <Area label="혼잡 대응" id="f-crowd" value={form.crowd_plan} onChange={set('crowd_plan')} />
        <Area label="안전 계획" id="f-safety" value={form.safety_plan} onChange={set('safety_plan')} />
      </Section>

      {/* 이 영역이 지금까지 통째로 없었다. DB·스키마·PUT 은 다 있는데 입력칸이
          없어 한 번도 채워진 적이 없다 — 관광 연계를 내세우면서 관광 연계
          입력칸이 없는 기획 도구였다. */}
      <Section title="지역 관광 연계" hint="지역 관광 연계성 점수의 근거입니다.">
        <Area label="관광지 연계 계획" id="f-tourism" value={form.tourism_link_plan} onChange={set('tourism_link_plan')} placeholder="인근 관광지와 연계한 스탬프 코스 운영" />
        <Area label="지역 상권 연계" id="f-commerce" value={form.local_commerce_plan} onChange={set('local_commerce_plan')} />
        <Area label="숙박 연계" id="f-lodging" value={form.lodging_plan} onChange={set('lodging_plan')} />
        <Area label="홍보 계획" id="f-promo" value={form.promotion_plan} onChange={set('promotion_plan')} />
      </Section>

      <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
        <button
          className="btn btn--primary btn--lg"
          onClick={() => save.mutate()}
          disabled={save.isPending}
        >
          {save.isPending ? '저장 중…' : '저장하고 진단으로'}
        </button>
        <button className="btn btn--ghost" onClick={() => onSaved?.()}>
          취소
        </button>
      </div>
    </div>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card stack" style={{ gap: 'var(--space-4)' }}>
      <div className="stack" style={{ gap: 2 }}>
        <h2 className="section">{title}</h2>
        {/* 각 영역이 진단의 무엇을 움직이는지 밝힌다. 그래야 "무엇을 고치면
            점수가 오르는가" 에 답이 된다. */}
        <p className="muted">{hint}</p>
      </div>
      {children}
    </section>
  );
}

function Field({
  label,
  id,
  value,
  onChange,
  type = 'text',
  hint,
  placeholder,
}: {
  label: string;
  id: string;
  value: string;
  onChange: (e: { target: { value: string } }) => void;
  type?: string;
  hint?: string;
  placeholder?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} type={type} value={value} onChange={onChange} placeholder={placeholder} />
      {hint && <small className="muted">{hint}</small>}
    </div>
  );
}

function Area({
  label,
  id,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  id: string;
  value: string;
  onChange: (e: { target: { value: string } }) => void;
  placeholder?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea id={id} rows={2} value={value} onChange={onChange} placeholder={placeholder} />
    </div>
  );
}
