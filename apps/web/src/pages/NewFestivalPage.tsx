/** 새 축제 생성. 필수 항목만 받고 진단으로 바로 넘깁니다. */

import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError, api } from '../api/client';

interface Created {
  festival: { id: number };
  operator_access_code: string;
}

const PRESET = {
  name: '춘천 가을 먹거리 축제',
  region: '강원특별자치도 춘천시',
  venue: '공지천 조각공원',
  starts_on: '2026-10-10',
  ends_on: '2026-10-12',
  expected_visitors: '18000',
  total_budget: '240000000',
  venue_capacity: '4000',
  summary: '지역 식재료와 로컬 뮤지션이 만나는 3일',
};

export function NewFestivalPage() {
  const nav = useNavigate();
  const [form, setForm] = useState({
    name: '',
    region: '',
    venue: '',
    starts_on: '',
    ends_on: '',
    expected_visitors: '',
    total_budget: '',
    venue_capacity: '',
    summary: '',
  });
  const [code, setCode] = useState<{ id: number; code: string } | null>(null);

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((p) => ({ ...p, [k]: e.target.value }));

  const periodInvalid =
    !!form.starts_on && !!form.ends_on && form.ends_on < form.starts_on;

  const create = useMutation({
    mutationFn: () =>
      api.post<Created>('/api/festivals', {
        name: form.name,
        region: form.region,
        venue: form.venue,
        starts_on: form.starts_on,
        ends_on: form.ends_on,
        expected_visitors: Number(form.expected_visitors),
        total_budget: Number(form.total_budget),
        plan: {
          summary: form.summary || null,
          venue_capacity: form.venue_capacity ? Number(form.venue_capacity) : null,
        },
      }),
    onSuccess: (d) => setCode({ id: d.festival.id, code: d.operator_access_code }),
  });

  if (code) {
    return (
      <div className="shell">
        <div className="card state">
          <p className="eyebrow">축제를 만들었습니다</p>
          <h2 style={{ fontSize: 'var(--text-h2)' }}>운영자 접근 코드</h2>
          <div className="accesscode tabular">{code.code}</div>
          <p className="lede" style={{ textAlign: 'center' }}>
            <strong>이 코드는 다시 볼 수 없습니다.</strong> 현장 운영자에게 전달하세요.
          </p>
          <div className="row">
            <button
              className="btn btn--ghost"
              onClick={() => navigator.clipboard?.writeText(code.code)}
            >
              복사
            </button>
            <button
              className="btn btn--primary btn--lg"
              onClick={() => nav(`/festivals/${code.id}/diagnosis`)}
            >
              사전 진단 보기
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">새 축제</p>
          <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>축제 기획 등록</h1>
        </div>
        <button className="btn btn--ghost" onClick={() => setForm({ ...PRESET })}>
          샘플 기획안 불러오기
        </button>
      </div>

      <form
        className="card stack"
        style={{ gap: 'var(--space-5)' }}
        onSubmit={(e) => {
          e.preventDefault();
          if (!periodInvalid) create.mutate();
        }}
      >
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
            <span className="hint">시·도와 시·군·구를 함께 적으면 지역 데이터가 정확해집니다</span>
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
            <input id="starts" type="date" required value={form.starts_on} onChange={set('starts_on')} />
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

        <div className="grid2">
          <div className="field field--inline">
            <label htmlFor="visitors">
              예상 방문객 <span className="req">*필수</span>
            </label>
            <input
              id="visitors"
              type="number"
              required
              min={1}
              value={form.expected_visitors}
              onChange={set('expected_visitors')}
            />
            <span className="unit">명</span>
          </div>
          <div className="field field--inline">
            <label htmlFor="budget">
              총예산 <span className="req">*필수</span>
            </label>
            <input
              id="budget"
              type="number"
              required
              min={0}
              value={form.total_budget}
              onChange={set('total_budget')}
            />
            <span className="unit">원</span>
          </div>
        </div>

        <div className="field field--inline">
          <label htmlFor="capacity">동시 수용 인원</label>
          <input
            id="capacity"
            type="number"
            min={0}
            value={form.venue_capacity}
            onChange={set('venue_capacity')}
          />
          <span className="unit">명</span>
          <span className="hint">
            입력하면 진단이 추정치 대신 이 값으로 수용력을 판정합니다
          </span>
        </div>

        <div className="field">
          <label htmlFor="summary">한 줄 소개</label>
          <input id="summary" value={form.summary} onChange={set('summary')} />
        </div>

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
            {create.isPending ? '만드는 중…' : '축제 만들기'}
          </button>
        </div>
      </form>
    </div>
  );
}
