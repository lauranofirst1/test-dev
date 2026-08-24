/** 성과 목표 입력.
 *
 * **측정 가능 여부를 운영자가 정하지 않습니다.** 그건 지표의 성질이지 선택이
 * 아닙니다. 목표 방문객에 체크 하나로 달성률을 켤 수 있게 두면 반드시 켜지고,
 * 그 순간 QR 참여자 수가 방문객 수로 둔갑합니다. 그래서 서버가 정한 값을
 * 그대로 보여주고, 무엇이 왜 측정 불가인지 화면에서 미리 알립니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, api } from '../api/client';
import type { KpiTargetList } from '../api/types';

export function KpiTargetEditor({ festivalId }: { festivalId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [metric, setMetric] = useState('');
  const [value, setValue] = useState('');
  const [customName, setCustomName] = useState('');
  const [unit, setUnit] = useState('');

  const targets = useQuery({
    queryKey: ['kpi-targets', festivalId],
    queryFn: () => api.get<KpiTargetList>(`/api/festivals/${festivalId}/kpi-targets`),
    retry: false,
  });

  const reload = () => {
    qc.invalidateQueries({ queryKey: ['kpi-targets', festivalId] });
    qc.invalidateQueries({ queryKey: ['report', festivalId] });
  };

  const save = useMutation({
    mutationFn: () =>
      api.put(`/api/festivals/${festivalId}/kpi-targets`, {
        metric_key: metric === 'custom' ? `custom:${customName.trim()}` : metric,
        label: metric === 'custom' ? customName.trim() : null,
        target_value: Number(value) || 0,
        unit: metric === 'custom' ? unit.trim() || '건' : null,
      }),
    onSuccess: () => {
      setMetric('');
      setValue('');
      setCustomName('');
      setUnit('');
      reload();
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/festivals/${festivalId}/kpi-targets/${id}`),
    onSuccess: reload,
  });

  const available = targets.data?.available ?? [];
  const items = targets.data?.items ?? [];
  const isCustom = metric === 'custom';
  const ready = isCustom ? customName.trim() && value : metric && value;

  return (
    <details open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="muted">성과 목표 {items.length > 0 ? '고치기' : '세우기'}</summary>

      <div className="stack" style={{ gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
        {items.map((t) => (
          <div key={t.id} className="row wrap" style={{ justifyContent: 'space-between' }}>
            <span>
              {t.label} — {t.target_value.toLocaleString()}
              {t.unit}
              {!t.is_measurable && (
                <b className="badge badge--off" style={{ marginLeft: 6 }}>
                  참고값
                </b>
              )}
            </span>
            <button className="btn btn--ghost" onClick={() => remove.mutate(t.id)}>
              지우기
            </button>
          </div>
        ))}

        <div className="grid2">
          <div className="field">
            <label htmlFor="k-metric">지표</label>
            {/* 목록을 화면에 박아 두면 서버에 기본 지표가 늘어날 때 조용히 어긋난다. */}
            <select id="k-metric" value={metric} onChange={(e) => setMetric(e.target.value)}>
              <option value="">지표를 고르세요</option>
              {available.map((a) => (
                <option key={a.metric_key} value={a.metric_key}>
                  {a.label}
                  {!a.is_measurable && ' (참고값)'}
                </option>
              ))}
              <option value="custom">사용자 정의 지표…</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="k-value">목표값</label>
            <input
              id="k-value"
              type="number"
              min={0}
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </div>
        </div>

        {isCustom && (
          <div className="grid2">
            <div className="field">
              <label htmlFor="k-name">지표 이름</label>
              <input
                id="k-name"
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                placeholder="재방문 의향"
              />
            </div>
            <div className="field">
              <label htmlFor="k-unit">단위</label>
              <input
                id="k-unit"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                placeholder="%"
              />
            </div>
          </div>
        )}

        {/* 무엇이 왜 측정 불가인지 입력 화면에서 미리 알린다. 리포트에 가서야
            "참고값" 을 보면 목표를 잘못 세운 것이 된다. */}
        <p className="muted">
          FestaFlow 가 실제값을 집계할 수 있는 것은 QR 참여 지표뿐입니다. 목표 방문객은
          실측치를 입력해야 달성률이 생기고, 사용자 정의 지표는 참고값으로만 남습니다.
        </p>

        {save.error instanceof ApiError && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>{save.error.message}</span>
          </div>
        )}

        <button
          className="btn btn--primary"
          disabled={!ready || save.isPending}
          onClick={() => save.mutate()}
        >
          목표 저장
        </button>
      </div>
    </details>
  );
}
