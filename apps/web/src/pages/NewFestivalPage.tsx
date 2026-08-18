/** 새 축제 생성.
 *
 * 진단이 실제로 소비하는 필드를 전부 받습니다 — 인력·안전/교통/혼잡 계획이
 * 비어 있으면 운영 준비도가 낮게 나오고, 예정 프로그램 수가 없으면
 * 부스 등록 전까지 프로그램 균형을 평가할 근거가 없습니다.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import { EMPTY_FORM, PRESETS, type PresetForm } from '../api/presets';

interface Created {
  festival: { id: number };
  operator_access_code: string;
}

/** 생성 결과. `diagnosisError` 가 있으면 축제는 저장됐지만 진단만 실패한 상태다. */
interface Result {
  id: number;
  code: string;
  diagnosisError: string | null;
}

const num = (v: string): number | null => (v.trim() === '' ? null : Number(v));

export function NewFestivalPage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [form, setForm] = useState<PresetForm>(EMPTY_FORM);
  const [loadedPreset, setLoadedPreset] = useState<string | null>(null);
  const [created, setCreated] = useState<Result | null>(null);
  const [phase, setPhase] = useState<'idle' | 'creating' | 'diagnosing'>('idle');

  const set = (k: keyof PresetForm) => (e: { target: { value: string } }) => {
    setForm((p) => ({ ...p, [k]: e.target.value }));
    setLoadedPreset(null);
  };

  const periodInvalid = !!form.starts_on && !!form.ends_on && form.ends_on < form.starts_on;

  // 버튼이 "축제 만들고 진단하기"인 만큼 생성에서 끝내지 않고 진단까지 이어서 돌린다.
  // 백엔드 생성 엔드포인트는 pending 진단 레코드만 만들고 실제 실행은 하지 않는다 —
  // 외부 API 호출을 생성 트랜잭션 안에 넣지 않으려는 설계이므로 호출은 여기서 한다.
  const create = useMutation({
    mutationFn: async (): Promise<Result> => {
      setPhase('creating');
      const d = await api.post<Created>('/api/festivals', {
        name: form.name,
        region: form.region,
        venue: form.venue,
        starts_on: form.starts_on,
        ends_on: form.ends_on,
        expected_visitors: Number(form.expected_visitors),
        total_budget: Number(form.total_budget),
        plan: {
          summary: form.summary || null,
          core_audience: form.core_audience || null,
          venue_capacity: num(form.venue_capacity),
          staff_count: num(form.staff_count),
          volunteer_count: num(form.volunteer_count),
          safety_staff_count: num(form.safety_staff_count),
          parking_capacity: num(form.parking_capacity),
          planned_performance: num(form.planned_performance) ?? 0,
          planned_experience: num(form.planned_experience) ?? 0,
          planned_food: num(form.planned_food) ?? 0,
          planned_local_shop: num(form.planned_local_shop) ?? 0,
          planned_tour_info: num(form.planned_tour_info) ?? 0,
          planned_etc: num(form.planned_etc) ?? 0,
          safety_plan: form.safety_plan || null,
          traffic_plan: form.traffic_plan || null,
          crowd_plan: form.crowd_plan || null,
        },
      });

      // 축제는 이미 저장됐다. 진단이 실패해도 생성을 되돌리지 않고
      // 접근 코드는 반드시 보여준 뒤, 진단만 다시 실행하게 한다.
      setPhase('diagnosing');
      let diagnosisError: string | null = null;
      try {
        await api.post(`/api/festivals/${d.festival.id}/diagnoses`);
      } catch (e) {
        diagnosisError =
          e instanceof ApiError ? e.message : '진단을 실행하지 못했습니다.';
      }

      return { id: d.festival.id, code: d.operator_access_code, diagnosisError };
    },
    onSuccess: (r) => {
      setCreated(r);
      qc.invalidateQueries({ queryKey: ['festivals'] });
    },
    onSettled: () => setPhase('idle'),
  });

  if (created) {
    return (
      <div className="shell">
        <div className="card state">
          <p className="eyebrow">축제를 만들었습니다</p>
          <h2 style={{ fontSize: 'var(--text-h2)' }}>운영자 접근 코드</h2>
          <div className="accesscode tabular">{created.code}</div>
          <p className="lede" style={{ textAlign: 'center' }}>
            <strong>이 코드는 다시 볼 수 없습니다.</strong> 현장 운영자에게 전달하세요.
          </p>
          {created.diagnosisError && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>
                축제는 저장됐지만 진단에 실패했습니다 — {created.diagnosisError} 진단
                화면에서 다시 실행할 수 있습니다.
              </span>
            </div>
          )}
          <div className="row">
            <button
              className="btn btn--ghost"
              onClick={() => navigator.clipboard?.writeText(created.code)}
            >
              코드 복사
            </button>
            <button
              className="btn btn--primary btn--lg"
              onClick={() => nav(`/festivals/${created.id}/diagnosis`)}
            >
              {created.diagnosisError ? '진단 다시 실행하기' : '사전 진단 보기'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="stack" style={{ gap: 4 }}>
        <p className="eyebrow">새 축제</p>
        <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>축제 기획 등록</h1>
        <p className="muted">
          입력한 값으로 한국관광공사 데이터를 조회해 준비도를 진단합니다.
        </p>
      </div>

      {/* ── 샘플 기획안 ── */}
      <section className="card card--sunk stack" style={{ gap: 'var(--space-4)' }}>
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">테스트 데이터 불러오기</p>
          <p className="muted">
            처음이라면 샘플 기획안으로 진단을 먼저 확인해 보세요. 불러온 뒤 자유롭게 고칠 수
            있고, 저장 전까지 아무것도 기록되지 않습니다.
          </p>
        </div>

        <div className="presets">
          {PRESETS.map((p) => (
            <button
              type="button"
              key={p.id}
              className={`preset${loadedPreset === p.id ? ' preset--on' : ''}`}
              onClick={() => {
                setForm(p.build());
                setLoadedPreset(p.id);
              }}
            >
              <span className="preset__label">{p.label}</span>
              <span className="preset__tagline tabular">{p.tagline}</span>
              <span className="preset__note">{p.note}</span>
            </button>
          ))}
        </div>

        {loadedPreset && (
          <div className="notice notice--info">
            <span>✓</span>
            <span>
              샘플을 불러왔습니다. 날짜는 <strong>오늘 기준 미래 날짜</strong>로 계산됐습니다.
              값을 고치면 이 표시가 사라집니다.
            </span>
          </div>
        )}
      </section>

      <form
        className="stack"
        style={{ gap: 'var(--space-5)' }}
        onSubmit={(e) => {
          e.preventDefault();
          if (!periodInvalid) create.mutate();
        }}
      >
        {/* ── 기본 정보 ── */}
        <section className="card stack" style={{ gap: 'var(--space-5)' }}>
          <h2 className="section">기본 정보</h2>

          <div className="field">
            <label htmlFor="name">
              축제명 <span className="req">*필수</span>
            </label>
            <input id="name" required minLength={2} value={form.name} onChange={set('name')} />
          </div>

          <div className="grid2">
            <div className="field">
              <label htmlFor="region">
                지역 <span className="req">*필수</span>
              </label>
              <input
                id="region"
                required
                value={form.region}
                onChange={set('region')}
                placeholder="강원특별자치도 춘천시"
              />
              <span className="hint">시·도와 시·군·구를 함께 적어야 지역 데이터가 정확합니다</span>
            </div>
            <div className="field">
              <label htmlFor="venue">
                행사 장소 <span className="req">*필수</span>
              </label>
              <input id="venue" required value={form.venue} onChange={set('venue')} />
            </div>
          </div>

          <div className="grid2">
            <div className="field">
              <label htmlFor="starts">
                시작일 <span className="req">*필수</span>
              </label>
              <input
                id="starts"
                type="date"
                required
                value={form.starts_on}
                onChange={set('starts_on')}
              />
            </div>
            <div className="field">
              <label htmlFor="ends">
                종료일 <span className="req">*필수</span>
              </label>
              <input
                id="ends"
                type="date"
                required
                value={form.ends_on}
                min={form.starts_on || undefined}
                onChange={set('ends_on')}
                aria-invalid={periodInvalid}
                aria-describedby={periodInvalid ? 'ends-err' : undefined}
              />
              {periodInvalid && (
                <span className="err" id="ends-err">
                  종료일은 시작일보다 빠를 수 없습니다.
                </span>
              )}
            </div>
          </div>

          <div className="field">
            <label htmlFor="summary">한 줄 소개</label>
            <input id="summary" value={form.summary} onChange={set('summary')} />
          </div>
        </section>

        {/* ── 목표와 규모 ── */}
        <section className="card stack" style={{ gap: 'var(--space-5)' }}>
          <h2 className="section">목표와 규모</h2>

          <div className="grid2">
            <NumField
              id="visitors"
              label="예상 방문객"
              unit="명"
              required
              min={1}
              value={form.expected_visitors}
              onChange={set('expected_visitors')}
            />
            <NumField
              id="budget"
              label="총예산"
              unit="원"
              required
              min={0}
              value={form.total_budget}
              onChange={set('total_budget')}
            />
          </div>

          <div className="field">
            <label htmlFor="audience">핵심 방문 대상</label>
            <input
              id="audience"
              value={form.core_audience}
              onChange={set('core_audience')}
              placeholder="가족 단위 방문객, 20~30대"
            />
          </div>

          <div className="grid2">
            <NumField
              id="capacity"
              label="동시 수용 인원"
              unit="명"
              value={form.venue_capacity}
              onChange={set('venue_capacity')}
              hint="입력하면 진단이 추정치 대신 이 값으로 수용력을 판정합니다"
            />
            <NumField
              id="parking"
              label="주차 가능 대수"
              unit="대"
              value={form.parking_capacity}
              onChange={set('parking_capacity')}
            />
          </div>
        </section>

        {/* ── 운영 인력 ── */}
        <section className="card stack" style={{ gap: 'var(--space-5)' }}>
          <h2 className="section">운영 인력</h2>
          <p className="muted">비어 있으면 운영 준비도 점수가 낮게 나옵니다.</p>
          <div className="grid2">
            <NumField id="staff" label="운영 인력" unit="명" value={form.staff_count} onChange={set('staff_count')} />
            <NumField id="volunteer" label="자원봉사" unit="명" value={form.volunteer_count} onChange={set('volunteer_count')} />
            <NumField id="safety" label="안전관리 인력" unit="명" value={form.safety_staff_count} onChange={set('safety_staff_count')} />
          </div>
        </section>

        {/* ── 예정 프로그램 ── */}
        <section className="card stack" style={{ gap: 'var(--space-5)' }}>
          <h2 className="section">예정 프로그램 구성</h2>
          <p className="muted">
            부스를 아직 등록하지 않았어도 이 값으로 프로그램 균형을 평가합니다.
            부스가 등록되면 실제 값이 우선합니다.
          </p>
          <div className="grid3">
            <NumField id="p1" label="공연" unit="개" value={form.planned_performance} onChange={set('planned_performance')} />
            <NumField id="p2" label="체험" unit="개" value={form.planned_experience} onChange={set('planned_experience')} />
            <NumField id="p3" label="먹거리" unit="개" value={form.planned_food} onChange={set('planned_food')} />
            <NumField id="p4" label="지역상점" unit="개" value={form.planned_local_shop} onChange={set('planned_local_shop')} />
            <NumField id="p5" label="관광안내" unit="개" value={form.planned_tour_info} onChange={set('planned_tour_info')} />
            <NumField id="p6" label="기타" unit="개" value={form.planned_etc} onChange={set('planned_etc')} />
          </div>
        </section>

        {/* ── 안전·교통 계획 ── */}
        <section className="card stack" style={{ gap: 'var(--space-5)' }}>
          <h2 className="section">안전·교통·혼잡 계획</h2>
          <p className="muted">세 항목 모두 운영 준비도 점수에 직접 반영됩니다.</p>

          <div className="field">
            <label htmlFor="safety-plan">안전 계획</label>
            <textarea id="safety-plan" value={form.safety_plan} onChange={set('safety_plan')} />
          </div>
          <div className="field">
            <label htmlFor="traffic-plan">교통 대책</label>
            <textarea id="traffic-plan" value={form.traffic_plan} onChange={set('traffic_plan')} />
          </div>
          <div className="field">
            <label htmlFor="crowd-plan">혼잡 대응 계획</label>
            <textarea id="crowd-plan" value={form.crowd_plan} onChange={set('crowd_plan')} />
          </div>
        </section>

        {create.error instanceof ApiError && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>{create.error.message}</span>
          </div>
        )}

        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button
            type="submit"
            className="btn btn--primary btn--lg"
            disabled={create.isPending || periodInvalid}
          >
            {phase === 'creating'
              ? '만드는 중…'
              : phase === 'diagnosing'
                ? '진단 중…'
                : '축제 만들고 진단하기'}
          </button>
        </div>
      </form>
    </div>
  );
}

function NumField({
  id,
  label,
  unit,
  value,
  onChange,
  required,
  min,
  hint,
}: {
  id: string;
  label: string;
  unit: string;
  value: string;
  onChange: (e: { target: { value: string } }) => void;
  required?: boolean;
  min?: number;
  hint?: string;
}) {
  return (
    <div className="field field--inline">
      <label htmlFor={id}>
        {label}
        {required && <span className="req">*필수</span>}
      </label>
      <input id={id} type="number" required={required} min={min} value={value} onChange={onChange} />
      <span className="unit">{unit}</span>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}
