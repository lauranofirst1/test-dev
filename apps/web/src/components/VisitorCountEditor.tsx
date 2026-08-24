/** 실측 방문객 입력.
 *
 * FestaFlow 는 방문객을 **측정하지 않지만 받아올 수는 있습니다.** 운영자가
 * 입구 계수기나 지자체 집계를 넣어 주면 리포트가 비로소 근거 있는 참여율을
 * 계산합니다.
 *
 * 같은 날짜에 여러 출처가 공존할 수 있습니다. 입구 계수기 수치와 지자체 집계가
 * 다른 것은 정상이고, 하나로 합치라고 강요하면 운영자는 아무 값이나 하나 골라
 * 넣습니다. 그 선택은 기록에 남지 않습니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, api } from '../api/client';
import type { VisitorCountList, VisitorSource } from '../api/types';

/** 신뢰도 순. 리포트가 같은 날짜에서 위쪽을 먼저 고른다. */
const SOURCES: { value: VisitorSource; label: string }[] = [
  { value: 'beacon', label: '출입구 센서' },
  { value: 'manual_counter', label: '입구 계수기' },
  { value: 'partner', label: '지자체·조직위 집계' },
  { value: 'estimate', label: '주최측 추산' },
];

export function VisitorCountEditor({ festivalId }: { festivalId: string }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ count_date: '', visitors: '', source: 'manual_counter', note: '' });

  const counts = useQuery({
    queryKey: ['visitor-counts', festivalId],
    queryFn: () => api.get<VisitorCountList>(`/api/festivals/${festivalId}/visitor-counts`),
    retry: false,
  });

  const reload = () => {
    qc.invalidateQueries({ queryKey: ['visitor-counts', festivalId] });
    qc.invalidateQueries({ queryKey: ['report', festivalId] });
  };

  const add = useMutation({
    mutationFn: () =>
      api.post(`/api/festivals/${festivalId}/visitor-counts`, {
        count_date: form.count_date,
        visitors: Number(form.visitors) || 0,
        source: form.source,
        note: form.note.trim() || null,
      }),
    onSuccess: () => {
      setForm({ ...form, visitors: '', note: '' });
      reload();
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/festivals/${festivalId}/visitor-counts/${id}`),
    onSuccess: reload,
  });

  const items = counts.data?.items ?? [];

  return (
    <details>
      <summary className="muted">실측 방문객 입력</summary>

      <div className="stack" style={{ gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
        {items.map((v) => (
          <div key={v.id} className="row wrap" style={{ justifyContent: 'space-between' }}>
            <span>
              {v.count_date} · {v.visitors.toLocaleString()}명{' '}
              <span className="muted">
                {v.source_label}
                {v.note ? ` · ${v.note}` : ''}
              </span>
            </span>
            <button className="btn btn--ghost" onClick={() => remove.mutate(v.id)}>
              지우기
            </button>
          </div>
        ))}

        <div className="grid2">
          <div className="field">
            <label htmlFor="v-date">날짜</label>
            <input
              id="v-date"
              type="date"
              value={form.count_date}
              onChange={(e) => setForm({ ...form, count_date: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="v-count">방문객 수</label>
            <input
              id="v-count"
              type="number"
              min={0}
              value={form.visitors}
              onChange={(e) => setForm({ ...form, visitors: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="v-source">출처</label>
            <select
              id="v-source"
              value={form.source}
              onChange={(e) => setForm({ ...form, source: e.target.value })}
            >
              {SOURCES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="v-note">메모</label>
            <input
              id="v-note"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              placeholder="정문+후문 합산"
            />
          </div>
        </div>

        <p className="muted">
          같은 날짜에 출처가 여럿이어도 됩니다. 리포트는 신뢰도가 높은 하나를 쓰고 나머지는
          함께 보여줍니다.
        </p>

        {add.error instanceof ApiError && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>{add.error.message}</span>
          </div>
        )}

        <button
          className="btn btn--primary"
          disabled={!form.count_date || !form.visitors || add.isPending}
          onClick={() => add.mutate()}
        >
          방문객 기록 추가
        </button>
      </div>
    </details>
  );
}
