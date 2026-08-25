/** 경품 관리와 당첨자 확인 — 조각 보드를 완성한 관객이 돌리는 뽑기의 설정.
 *
 * **확률(%)이 아니라 가중치를 받습니다.** 확률로 받으면 합이 100 이 되도록
 * 운영자가 맞춰야 하고, 상품 하나를 중지하는 순간 합이 100 이 아니게 됩니다.
 * 가중치는 그때그때 남은 후보들로 정규화되므로 무엇을 끄든 계산이 성립합니다.
 * 대신 화면이 **지금 기준 당첨 확률을 계산해 함께 보여줍니다** — 가중치 30 이
 * 몇 %인지 머리로 계산하게 두면 설정이 어렵습니다.
 *
 * 경고는 서버가 판정한 것을 그대로 씁니다. 같은 규칙이 화면에도 살면 어긋납니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { Prize, PrizeDrawList, PrizeDrawRow, PrizeList } from '../api/types';

const EMPTY = { name: '', description: '', stock: '', weight: '10', is_blank: false };

export function PrizeSettings({ festivalId }: { festivalId: string }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);

  const prizes = useQuery({
    queryKey: ['prizes', festivalId],
    queryFn: () => api.get<PrizeList>(`/api/festivals/${festivalId}/prizes`),
    retry: false,
  });

  const draws = useQuery({
    queryKey: ['prize-draws', festivalId],
    queryFn: () => api.get<PrizeDrawList>(`/api/festivals/${festivalId}/prize-draws`),
    retry: false,
  });

  const reload = () => {
    qc.invalidateQueries({ queryKey: ['prizes', festivalId] });
    qc.invalidateQueries({ queryKey: ['prize-draws', festivalId] });
  };

  const create = useMutation({
    mutationFn: () =>
      api.post<Prize>(`/api/festivals/${festivalId}/prizes`, {
        name: form.name.trim(),
        description: form.description.trim() || null,
        // 빈칸 = 무제한. 꽝은 반드시 무제한이어야 뽑기가 멈추지 않는다.
        stock: form.is_blank || form.stock === '' ? null : Number(form.stock),
        weight: Number(form.weight) || 1,
        is_blank: form.is_blank,
      }),
    onSuccess: () => {
      setForm(EMPTY);
      reload();
    },
  });

  const items = prizes.data?.items ?? [];
  const active = items.filter((p) => p.is_active);
  // 지금 실제로 뽑힐 수 있는 것들만 분모에 넣는다 — 소진·중지된 상품을 넣으면
  // 화면의 확률과 서버의 추첨이 다른 말을 하게 된다.
  const pool = active.filter((p) => p.stock === null || p.stock > 0);
  const totalWeight = pool.reduce((sum, p) => sum + p.weight, 0);

  return (
    <div className="card stack" style={{ gap: 'var(--space-5)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">경품 뽑기</p>
          <p className="muted">
            조각을 다 모은 관객이 <b>축제당 한 번</b> 돌립니다. 포인트가 아니라 실물 경품을
            주므로 보상 캠페인과 겹치지 않습니다.
          </p>
        </div>
        {/* 현장에서 실물을 건네는 화면. 창구 태블릿에 따로 띄운다. */}
        <Link to={`/festivals/${festivalId}/claim`} className="btn btn--soft" target="_blank">
          경품 수령대 열기 ↗
        </Link>
      </div>

      {prizes.data?.warnings.map((w) => (
        <div key={w.code} className="notice notice--warn">
          <span>⚠</span>
          <span>{w.message}</span>
        </div>
      ))}

      {items.length > 0 && (
        <div className="prizes">
          {items.map((p) => (
            <PrizeRow
              key={p.id}
              festivalId={festivalId}
              prize={p}
              share={
                p.is_active && (p.stock === null || p.stock > 0) && totalWeight > 0
                  ? p.weight / totalWeight
                  : null
              }
              onChanged={reload}
            />
          ))}
        </div>
      )}

      <form
        className="stack"
        style={{ gap: 'var(--space-3)' }}
        onSubmit={(e) => {
          e.preventDefault();
          if (form.name.trim()) create.mutate();
        }}
      >
        <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="경품 이름 (예: 막국수 쿠폰)"
            style={{ flex: '2 1 200px' }}
            aria-label="경품 이름"
          />
          <input
            type="number"
            min={0}
            className="tabular"
            value={form.is_blank ? '' : form.stock}
            onChange={(e) => setForm({ ...form, stock: e.target.value })}
            placeholder="재고"
            disabled={form.is_blank}
            style={{ width: 100 }}
            aria-label="재고 (비우면 무제한)"
          />
          <input
            type="number"
            min={1}
            className="tabular"
            value={form.weight}
            onChange={(e) => setForm({ ...form, weight: e.target.value })}
            placeholder="가중치"
            style={{ width: 100 }}
            aria-label="가중치"
          />
          <button className="btn btn--ghost" type="submit" disabled={create.isPending}>
            추가
          </button>
        </div>

        <label className="row" style={{ gap: 'var(--space-2)' }}>
          <input
            type="checkbox"
            checked={form.is_blank}
            onChange={(e) =>
              setForm({ ...form, is_blank: e.target.checked, stock: '' })
            }
            style={{ width: 20, height: 20 }}
          />
          <span className="muted">
            꽝으로 등록 — 재고 무제한이 되고 수령 확인 대상에서 빠집니다.
          </span>
        </label>

        <p className="hint">재고를 비우면 무제한입니다. 가중치는 상대값이라 합이 100 일 필요가 없습니다.</p>

        {create.error instanceof ApiError && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>{create.error.message}</span>
          </div>
        )}
      </form>

      {draws.data && draws.data.total > 0 && (
        <Winners festivalId={festivalId} list={draws.data} onChanged={reload} />
      )}
    </div>
  );
}

function PrizeRow({
  festivalId,
  prize,
  share,
  onChanged,
}: {
  festivalId: string;
  prize: Prize;
  /** 지금 기준 당첨 확률. 뽑힐 수 없는 상품이면 null. */
  share: number | null;
  onChanged: () => void;
}) {
  const update = useMutation({
    mutationFn: (patch: Partial<Prize>) =>
      api.put<Prize>(`/api/festivals/${festivalId}/prizes/${prize.id}`, {
        name: prize.name,
        description: prize.description,
        stock: prize.stock,
        weight: prize.weight,
        is_blank: prize.is_blank,
        is_active: prize.is_active,
        ...patch,
      }),
    onSuccess: onChanged,
  });

  const exhausted = prize.stock === 0;

  return (
    <div className={`prize${prize.is_active && !exhausted ? '' : ' prize--off'}`}>
      <div className="stack" style={{ gap: 2, minWidth: 0 }}>
        <div className="row" style={{ gap: 'var(--space-2)' }}>
          <strong>{prize.name}</strong>
          {prize.is_blank && <span className="badge badge--none">꽝</span>}
          {exhausted && <span className="badge badge--risk">소진</span>}
          {!prize.is_active && <span className="badge badge--none">중지</span>}
        </div>
        <span className="muted tabular">
          재고 {prize.stock === null ? '무제한' : `${prize.stock.toLocaleString()}개`}
          {' · '}
          가중치 {prize.weight}
          {share !== null && ` · 당첨 확률 ${(share * 100).toFixed(1)}%`}
        </span>
      </div>

      <div className="row" style={{ gap: 'var(--space-2)' }}>
        <button
          className="btn btn--ghost"
          onClick={() => update.mutate({ is_active: !prize.is_active })}
          disabled={update.isPending}
        >
          {prize.is_active ? '중지' : '재개'}
        </button>
      </div>
    </div>
  );
}

function Winners({
  festivalId,
  list,
  onChanged,
}: {
  festivalId: string;
  list: PrizeDrawList;
  onChanged: () => void;
}) {
  const claim = useMutation({
    mutationFn: (draw: PrizeDrawRow) =>
      api.post(`/api/festivals/${festivalId}/prize-draws/${draw.id}/claim`),
    onSuccess: onChanged,
  });

  return (
    <div className="stack" style={{ gap: 'var(--space-3)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <p className="eyebrow">당첨자 {list.total}명</p>
        {list.unclaimed > 0 && (
          <span className="badge badge--caution tabular">미수령 {list.unclaimed}건</span>
        )}
      </div>
      <p className="hint">
        여기서도 확인할 수 있지만, 줄이 선 창구에서는 <b>경품 수령대</b>가 빠릅니다 —
        목록을 훑는 대신 참여 코드로 바로 찾습니다.
      </p>

      <div className="prizes">
        {list.items.map((d) => (
          <div key={d.id} className={`prize${d.is_blank ? ' prize--off' : ''}`}>
            <div className="stack" style={{ gap: 2 }}>
              <strong className="tabular">{d.participant_code}</strong>
              <span className="muted">
                {d.prize_name ?? '경품 소진 상태에서 뽑음'}
                {d.claimed_at && ' · 수령 완료'}
              </span>
            </div>
            {/* 꽝은 건넬 실물이 없다. 여기에 확인 버튼을 두면 미수령 집계가 거짓이 된다. */}
            {!d.is_blank && d.prize_name && !d.claimed_at && (
              <button
                className="btn btn--soft"
                onClick={() => claim.mutate(d)}
                disabled={claim.isPending}
              >
                수령 확인
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
