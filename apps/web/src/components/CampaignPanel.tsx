/** 한시 추가 보상 — 대시보드에서 지금 거는 개입.
 *
 * **경품이 아닙니다.** 경품은 보드를 완성한 사람에게 주는 실물이고, 이건 특정
 * 부스의 미션 포인트를 정해진 시간 동안만 올리는 장치입니다. 운영자가 "보상"
 * 이라는 말을 보고 경품 설정을 찾으러 가지 않게, 화면에서는 **한시 추가 포인트**
 * 라고 부릅니다.
 *
 * **추천이 이걸 자동으로 실행하지 않습니다.** 추천 카드의 버튼은 대상 부스를
 * 폼에 채워 줄 뿐이고, 실제 실행은 운영자가 값을 확인하고 제출해야 일어납니다.
 * 참여 데이터가 편향된 표본인 이상, 그 데이터로 포인트를 자동으로 바꾸면
 * 아무도 결정하지 않은 개입이 현장에 나갑니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { ApiError, api } from '../api/client';
import type { BoothLoad, Campaign, CampaignImpact, CampaignList } from '../api/types';

/** 기본 지속 시간(분). 30분은 추천 카드가 보는 창과 같은 길이라,
 *  효과 분석의 before/after 와 자연스럽게 맞물린다. */
const DEFAULT_MINUTES = 30;

const EMPTY = {
  booth_id: '',
  title: '',
  message: '',
  bonus_points: '100',
  minutes: String(DEFAULT_MINUTES),
};

function remaining(iso: string): string {
  const secs = Math.floor((new Date(iso).getTime() - Date.now()) / 1000);
  if (secs <= 0) return '종료';
  const m = Math.floor(secs / 60);
  return m >= 60 ? `${Math.floor(m / 60)}시간 ${m % 60}분 남음` : `${m}분 남음`;
}

export function CampaignPanel({
  festivalId,
  booths,
  /** 추천 카드가 찍어 준 부스. 폼이 열리면서 자동 선택된다. */
  presetBoothId,
  onConsumePreset,
}: {
  festivalId: string;
  booths: BoothLoad[];
  presetBoothId: number | null;
  onConsumePreset: () => void;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [openImpact, setOpenImpact] = useState<number | null>(null);

  const campaigns = useQuery({
    queryKey: ['campaigns', festivalId],
    queryFn: () => api.get<CampaignList>(`/api/festivals/${festivalId}/reward-campaigns`),
    // 남은 시간 배지가 흘러야 한다. 대시보드 폴링과 같은 주기로 맞춘다.
    refetchInterval: 10_000,
    retry: false,
  });

  // 추천 카드에서 넘어오면 폼을 열고 그 부스를 골라 둔다. 운영자가 부스 이름을
  // 다시 찾아 고르게 하면, 급한 현장에서 옆 부스를 고르는 일이 생긴다.
  useEffect(() => {
    if (presetBoothId === null) return;
    const booth = booths.find((b) => b.booth_id === presetBoothId);
    setForm({
      ...EMPTY,
      booth_id: String(presetBoothId),
      title: booth ? `${booth.name} 추가 포인트` : '',
    });
    setOpen(true);
    onConsumePreset();
  }, [presetBoothId, booths, onConsumePreset]);

  const create = useMutation({
    mutationFn: () => {
      const now = new Date();
      const minutes = Number(form.minutes) || DEFAULT_MINUTES;
      return api.post(`/api/festivals/${festivalId}/reward-campaigns`, {
        booth_id: Number(form.booth_id),
        title: form.title.trim(),
        message: form.message.trim(),
        bonus_points: Number(form.bonus_points) || 0,
        starts_at: now.toISOString(),
        ends_at: new Date(now.getTime() + minutes * 60_000).toISOString(),
      });
    },
    onSuccess: () => {
      setForm(EMPTY);
      setOpen(false);
      qc.invalidateQueries({ queryKey: ['campaigns', festivalId] });
    },
  });

  const stop = useMutation({
    mutationFn: (id: number) =>
      api.del(`/api/festivals/${festivalId}/reward-campaigns/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['campaigns', festivalId] }),
  });

  const items = campaigns.data?.items ?? [];
  const live = items.filter((c) => c.is_live);
  const past = items.filter((c) => !c.is_live);
  const ready = form.booth_id && form.title.trim() && form.message.trim();

  return (
    <section className="card stack" style={{ gap: 'var(--space-4)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 4 }}>
          <h2 className="section">한시 추가 포인트</h2>
          {/* 경품과 헷갈리지 않게 무엇인지 한 줄로 밝힌다. */}
          <p className="muted">
            정해진 시간 동안 한 부스의 미션 포인트를 올립니다. 경품 뽑기와는 다릅니다.
          </p>
        </div>
        <button className="btn btn--ghost" onClick={() => setOpen((v) => !v)}>
          {open ? '닫기' : '추가 보상 걸기'}
        </button>
      </div>

      {open && (
        <div className="card card--sunk stack" style={{ gap: 'var(--space-3)' }}>
          <div className="field">
            <label htmlFor="c-booth">대상 부스</label>
            <select
              id="c-booth"
              value={form.booth_id}
              onChange={(e) => setForm({ ...form, booth_id: e.target.value })}
            >
              <option value="">부스를 고르세요</option>
              {booths
                .filter((b) => b.is_active)
                .map((b) => (
                  <option key={b.booth_id} value={b.booth_id}>
                    {b.name}
                  </option>
                ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="c-title">제목</label>
            <input
              id="c-title"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="지역상점존 추가 포인트"
              maxLength={120}
            />
          </div>

          <div className="field">
            <label htmlFor="c-msg">참여자 안내 문구</label>
            <input
              id="c-msg"
              value={form.message}
              onChange={(e) => setForm({ ...form, message: e.target.value })}
              placeholder="지금 지역상점존에서 미션을 하면 포인트를 더 드립니다."
              maxLength={500}
            />
          </div>

          <div className="grid2">
            <div className="field">
              <label htmlFor="c-points">추가 포인트</label>
              <input
                id="c-points"
                type="number"
                min={0}
                value={form.bonus_points}
                onChange={(e) => setForm({ ...form, bonus_points: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="c-minutes">지속 시간 (분)</label>
              <input
                id="c-minutes"
                type="number"
                min={5}
                max={1440}
                value={form.minutes}
                onChange={(e) => setForm({ ...form, minutes: e.target.value })}
              />
            </div>
          </div>

          {/* 지금부터 시작한다. 예약을 넣을 수 있게 하면 "언제 시작하는지 모르는
              캠페인" 이 쌓이고, 축제 당일에 그걸 관리할 사람이 없다. */}
          <p className="muted">지금 시작해 {form.minutes || DEFAULT_MINUTES}분 뒤 끝납니다.</p>

          {create.error instanceof ApiError && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>{create.error.message}</span>
            </div>
          )}

          <button
            className="btn btn--primary"
            disabled={!ready || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? '거는 중…' : '지금 시작'}
          </button>
        </div>
      )}

      {live.length === 0 && !open && <p className="muted">지금 걸린 추가 포인트가 없습니다.</p>}

      {live.map((c) => (
        <CampaignRow
          key={c.id}
          campaign={c}
          festivalId={festivalId}
          onStop={() => stop.mutate(c.id)}
          stopping={stop.isPending}
          impactOpen={openImpact === c.id}
          onToggleImpact={() => setOpenImpact(openImpact === c.id ? null : c.id)}
        />
      ))}

      {past.length > 0 && (
        <details>
          <summary className="muted">지난 캠페인 {past.length}건</summary>
          <div className="stack" style={{ gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
            {past.map((c) => (
              <CampaignRow
                key={c.id}
                campaign={c}
                festivalId={festivalId}
                impactOpen={openImpact === c.id}
                onToggleImpact={() => setOpenImpact(openImpact === c.id ? null : c.id)}
              />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function CampaignRow({
  campaign,
  festivalId,
  onStop,
  stopping,
  impactOpen,
  onToggleImpact,
}: {
  campaign: Campaign;
  festivalId: string;
  onStop?: () => void;
  stopping?: boolean;
  impactOpen: boolean;
  onToggleImpact: () => void;
}) {
  return (
    <div className="camprow" data-live={campaign.is_live}>
      <div className="row wrap" style={{ justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <div className="stack" style={{ gap: 4 }}>
          <span className="camprow__title">
            🎁 {campaign.title}
            <b className="camprow__points">+{campaign.bonus_points}P</b>
          </span>
          <span className="muted">
            {campaign.booth_name}
            {campaign.mission_title ? ` · ${campaign.mission_title}` : ' · 부스 전체 미션'} ·{' '}
            {campaign.is_live ? remaining(campaign.ends_at) : '종료'}
          </span>
        </div>
        <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
          <button className="btn btn--ghost" onClick={onToggleImpact}>
            {impactOpen ? '변화 닫기' : '전후 변화'}
          </button>
          {onStop && (
            <button className="btn btn--ghost" onClick={onStop} disabled={stopping}>
              지금 끄기
            </button>
          )}
        </div>
      </div>

      {impactOpen && <ImpactView festivalId={festivalId} campaignId={campaign.id} />}
    </div>
  );
}

/** 캠페인 전후 참여 변화.
 *
 * **인과 효과가 아닙니다.** 캠페인을 켠 시점은 대개 사람이 몰리기 시작한 시점이고,
 * 같은 시간에 공연이 끝나거나 비가 그치거나 점심시간이 지납니다. 그래서 이 표는
 * "효과" 라는 말을 쓰지 않고 면책 문구를 항상 함께 답니다.
 */
function ImpactView({ festivalId, campaignId }: { festivalId: string; campaignId: number }) {
  const impact = useQuery({
    queryKey: ['impact', festivalId, campaignId],
    queryFn: () =>
      api.get<CampaignImpact>(
        `/api/festivals/${festivalId}/reward-campaigns/${campaignId}/impact`,
      ),
    retry: false,
  });

  if (impact.isLoading) return <div className="skeleton" style={{ height: 90 }} />;
  if (!impact.data) return null;
  const d = impact.data;

  if (d.data_status === 'INSUFFICIENT_DATA') {
    return (
      <div className="notice notice--info">
        <span>◐</span>
        <span>
          전후 {d.window_minutes}분 참여가 합쳐서 20건 미만이라 변화를 읽지 않습니다.
          {d.in_progress && ' 아직 집계 중입니다.'}
        </span>
      </div>
    );
  }

  const pp = d.share_change_pp;
  return (
    <div className="impact stack" style={{ gap: 'var(--space-3)' }}>
      {d.in_progress && (
        <div className="notice notice--info">
          <span>◐</span>
          <span>이후 {d.window_minutes}분이 아직 안 지났습니다. 지금 숫자는 집계 중입니다.</span>
        </div>
      )}

      <div className="impact__pair">
        <div>
          <p className="muted">이전 {d.window_minutes}분</p>
          <p className="impact__num">{d.before.target_completions}건</p>
          <p className="muted">전체의 {Math.round(d.before.share * 100)}%</p>
        </div>
        <span className="impact__arrow" aria-hidden>
          →
        </span>
        <div>
          <p className="muted">이후 {d.window_minutes}분</p>
          <p className="impact__num">{d.after.target_completions}건</p>
          <p className="muted">전체의 {Math.round(d.after.share * 100)}%</p>
        </div>
      </div>

      <p>
        축제 전체 참여 중 이 부스의 비중이{' '}
        <b>
          {pp > 0 ? '+' : ''}
          {pp}%p
        </b>{' '}
        {pp > 0 ? '올랐습니다' : pp < 0 ? '내렸습니다' : '그대로입니다'}.
        {d.completion_change_rate === null
          ? ' 이전 구간에는 완료가 없어 배수는 계산하지 않습니다.'
          : ` 완료 건수는 ${Math.abs(Math.round(d.completion_change_rate * 100))}% ${
              d.completion_change_rate > 0 ? '늘었습니다' : '줄었습니다'
            }.`}
      </p>

      {/* 부스 이름은 운영자가 쓰는 자유 텍스트라 뒤에 조사를 붙이지 않는다 —
          "막국수 체험존은(는)" 처럼 보이거나 받침 판정이 틀어진다. */}
      {d.top_booth_before && (
        <p className="muted">
          같은 시간 가장 몰려 있던 부스 — {d.top_booth_before.name}:{' '}
          {Math.round(d.top_booth_before.share_before * 100)}% →{' '}
          {Math.round(d.top_booth_before.share_after * 100)}%
        </p>
      )}

      <p className="disclaimer">{d.disclaimer}</p>
    </div>
  );
}
