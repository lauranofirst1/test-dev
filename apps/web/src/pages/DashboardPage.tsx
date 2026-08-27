/** 오늘 — 축제 당일에 띄워 두는 화면.
 *
 * 이름이 "운영 대시보드" 였을 때는 언제 여는 화면인지가 이름에 없었습니다.
 * 이 화면은 당일에만 엽니다.
 *
 * **여기 나오는 것은 혼잡도가 아닙니다.** GPS·카메라·센서로 잰 인원수도, 물리적
 * 밀집도도 아니고, 부스에서 검증된 QR/미션 완료 건수입니다. QR 참여자는 방문객의
 * 일부이고 적극적 참여자에 편향된 표본입니다.
 *
 * 그래서 이 화면은 상태를 "여유 / 주의 / 집중" 으로 부르고 "한산 / 혼잡" 이라는
 * 말을 쓰지 않으며, 면책 문구를 접히지 않는 자리에 둡니다. 제한을 각주로 밀어
 * 두고 화면은 혼잡도처럼 그리면 그 문구는 면피가 됩니다.
 *
 * **차트 라이브러리를 쓰지 않습니다.** 부스별 최근 30분 비교는 CSS 막대로 충분하고,
 * 축제 당일 태블릿에서 300KB 짜리 번들을 더 받는 것보다 즉시 뜨는 쪽이 낫습니다.
 *
 * 10초마다 다시 부릅니다. 서버가 ETag 를 붙이므로 변화가 없으면 브라우저가
 * 조건부 요청으로 처리해 본문이 오가지 않습니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import { AnnouncementAdmin } from '../components/AnnouncementAdmin';
import { ParticipationChart } from '../components/ParticipationChart';
import { CampaignPanel } from '../components/CampaignPanel';
import type {
  OperationsTimeline,
  BoothLoad,
  BoothLoadStatus,
  FestivalDetail,
  Insights,
  Recommendation,
} from '../api/types';

const POLL_MS = 10_000;

/** 상태별 색 토큰. 색만으로 알리지 않고 아이콘·라벨·이유를 항상 함께 낸다 —
 *  색각 이상 사용자와 흑백 인쇄에서 색은 사라진다. */
const TONE: Record<BoothLoadStatus, { icon: string; token: string }> = {
  HIGH: { icon: '▲', token: 'high' },
  CAUTION: { icon: '◆', token: 'caution' },
  LOW: { icon: '●', token: 'low' },
  INSUFFICIENT_DATA: { icon: '·', token: 'none' },
};

const REC_LABEL: Record<Recommendation['type'], string> = {
  REDISTRIBUTE: '참여 편중',
  NO_ACTIVITY: '참여 없음',
};

function timeAgo(iso: string | null): string {
  if (!iso) return '기록 없음';
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (mins < 1) return '방금';
  if (mins < 60) return `${mins}분 전`;
  return `${Math.floor(mins / 60)}시간 전`;
}

export function DashboardPage() {
  const { id = '' } = useParams<{ id: string }>();
  const qc = useQueryClient();
  // 추천 카드가 찍어 준 부스. 캠페인 폼이 열리면서 이 값을 소비한다.
  const [presetBoothId, setPresetBoothId] = useState<number | null>(null);

  const festival = useQuery({
    queryKey: ['festival', id],
    queryFn: () => api.get<FestivalDetail>(`/api/festivals/${id}`),
  });

  const insights = useQuery({
    queryKey: ['insights', id],
    queryFn: () => api.get<Insights>(`/api/festivals/${id}/operations/insights`),
    // 폴링은 인사이트만 갱신한다. 축제 정보를 함께 다시 받으면 편집 중인 폼이
    // 초기화된다.
    refetchInterval: POLL_MS,
    retry: false,
  });

  /** 시간대 그래프. 인사이트와 **따로** 부른다 — 인사이트는 10초마다 도는데
   *  10분 칸은 그 사이 거의 바뀌지 않는다. 같은 주기로 묶으면 축제 내내
   *  60배의 요청이 같은 답을 받는다. */
  const timeline = useQuery({
    queryKey: ['operations-timeline', id],
    queryFn: () =>
      api.get<OperationsTimeline>(`/api/festivals/${id}/operations/timeline?hours=6`),
    refetchInterval: 60_000,
    retry: false,
  });

  const d = insights.data;
  // 완료가 가장 많은 부스를 기준으로 막대 길이를 잡는다. 전체 합 대비로 그리면
  // 부스가 많을수록 모든 막대가 짧아져 서로 비교가 안 된다.
  const peak = Math.max(1, ...(d?.booths.map((b) => b.last_30m) ?? [0]));

  return (
    // `ops` 는 당일 밀도다. 같은 토큰으로 숫자를 키우고 카드를 성기게 한다 —
    // 운영본부에서는 서서 흘끗 보고 3초 안에 판단한다.
    <div className="shell stack ops" style={{ gap: 'var(--space-6)' }}>
      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <div className="stack" style={{ gap: 4 }}>
            <p className="eyebrow">오늘</p>
            <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>
              {festival.data?.name ?? '불러오는 중…'}
            </h1>
            <p className="muted">
              {d ? `${new Date(d.generated_at).toLocaleTimeString('ko-KR')} 기준` : '집계 중…'}
              {' · '}10초마다 자동 갱신
            </p>
          </div>
          <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
            <button
              className="btn btn--primary"
              onClick={() => qc.invalidateQueries({ queryKey: ['insights', id] })}
              disabled={insights.isFetching}
            >
              {insights.isFetching ? '갱신 중…' : '지금 새로고침'}
            </button>
          </div>
        </div>
      </div>

      {insights.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>
            <strong>지표를 불러오지 못했습니다.</strong> {insights.error.message}
          </span>
        </div>
      )}

      {d?.warnings.map((w) => (
        <div key={w.code} className="notice notice--warn">
          <span>⚠</span>
          <span>{w.message}</span>
        </div>
      ))}

      {d && (
        <>
          <section className="grid2">
            <Kpi label="총 참여자" value={d.kpi.total_participants} unit="명" icon="◍" />
            <Kpi label="총 미션 완료" value={d.kpi.total_completions} unit="건" icon="✓" />
            <Kpi label="최근 30분 참여" value={d.kpi.completions_last_30m} unit="건" icon="◔" />
            <Kpi
              label="참여 편중 위험 부스"
              value={d.kpi.high_concentration_booths}
              unit="개"
              icon="▲"
              tone={d.kpi.high_concentration_booths > 0 ? 'high' : undefined}
            />
          </section>

          {/* 스탯은 "지금 얼마" 를, 부스 표는 "어디가" 를 답한다. 둘 다
              **언제부터** 를 답하지 못한다 — 최근 30분 96건이 오르는 중인지
              식는 중인지에 따라 할 일이 정반대다. */}
          <section className="card stack" style={{ gap: 'var(--space-4)' }}>
            <div className="row wrap" style={{ justifyContent: 'space-between' }}>
              <h2 className="section">시간대별 참여</h2>
              <span className="muted">참여가 없던 구간도 그대로 그립니다</span>
            </div>
            {timeline.error instanceof ApiError ? (
              <p className="muted">
                추이를 불러오지 못했습니다. {timeline.error.message}
              </p>
            ) : timeline.data ? (
              <ParticipationChart
                points={timeline.data.points}
                peak={timeline.data.peak}
                caption={`최근 ${timeline.data.window_hours}시간 · ${timeline.data.bucket_minutes}분 간격`}
              />
            ) : (
              <div className="skeleton" style={{ height: 132 }} />
            )}
          </section>

          {/* 제한은 각주가 아니라 지표 바로 옆에 둔다. */}
          <p className="disclaimer">{d.disclaimer}</p>

          <div data-tour="dash-insight">
            <RecommendationCards
              festivalId={id}
            items={d.recommendations}
              insights={d}
              onSetReward={setPresetBoothId}
            />
          </div>

          {/* 공지는 캠페인보다 위에 둔다 — 무언가 잘못됐을 때 먼저 찾는 것이다. */}
          <div data-tour="dash-announce">
            <AnnouncementAdmin festivalId={id} />
          </div>

          <div data-tour="dash-campaign">
          <CampaignPanel
            festivalId={id}
            booths={d.booths}
            presetBoothId={presetBoothId}
            onConsumePreset={() => setPresetBoothId(null)}
          />
          </div>

          <section className="card stack" style={{ gap: 'var(--space-4)' }}>
            <div className="row wrap" style={{ justifyContent: 'space-between' }}>
              <h2 className="section">부스 참여 현황</h2>
              <span className="muted">막대는 최근 30분 완료 건수</span>
            </div>

            {d.booths.length === 0 ? (
              <p className="muted">아직 등록된 부스가 없습니다.</p>
            ) : (
              <div className="stack" style={{ gap: 'var(--space-3)' }}>
                {d.booths.map((b) => (
                  <BoothRow key={b.booth_id} booth={b} peak={peak} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function Kpi({
  label,
  value,
  unit,
  icon,
  tone,
}: {
  label: string;
  value: number;
  unit: string;
  icon: string;
  tone?: string;
}) {
  return (
    // 지금 손을 써야 하는 카드만 테두리가 선다. 전부 서면 아무것도 안 선 것과
    // 같다 — 당일 화면에서 눈이 먼저 가야 하는 곳은 하나여야 한다.
    <div className="card kpi" data-alert={tone === 'high' || undefined}>
      <p className="kpi__label">
        {/* 칩 색은 타일 순서로 돌아간다. **의미를 담지 않는다** —
            상태색과 섞이면 여유·주의·집중이 뜻을 잃는다. */}
        <span className="kpi__chip" aria-hidden>
          {icon}
        </span>
        {label}
      </p>
      <p className="kpi__value" data-tone={tone}>
        {value.toLocaleString()}
        <small>{unit}</small>
      </p>
    </div>
  );
}

function BoothRow({ booth, peak }: { booth: BoothLoad; peak: number }) {
  // 완료가 0건인 부스는 편중 판정으로는 LOW 지만 "여유" 로 보이면 안 된다 —
  // 서버가 라벨을 "참여 없음" 으로 내려주므로, 색과 아이콘도 거기에 맞춘다.
  // 파란 ● 옆에 "참여 없음" 이 붙으면 색과 글자가 반대로 말한다.
  const tone = booth.status_label === '참여 없음' ? { icon: '○', token: 'none' } : TONE[booth.status];
  return (
    <div className="loadrow" data-tone={tone.token} data-inactive={!booth.is_active}>
      <div className="loadrow__head">
        <span className="loadrow__name">
          {booth.name}
          {!booth.is_active && <span className="badge badge--off">비활성</span>}
        </span>
        <span className="loadrow__status">
          <span aria-hidden>{tone.icon}</span> {booth.status_label}
        </span>
      </div>

      <div className="loadbar" role="img" aria-label={`최근 30분 ${booth.last_30m}건`}>
        <span
          className="loadbar__fill"
          style={{ width: `${Math.round((booth.last_30m / peak) * 100)}%` }}
        />
        <b className="loadbar__count">{booth.last_30m}건</b>
      </div>

      <p className="loadrow__reason">{booth.status_reason}</p>
      <p className="loadrow__meta muted">
        10분 {booth.last_10m} · 30분 {booth.last_30m} · 60분 {booth.last_60m} · 누적{' '}
        {booth.total_completions}건 / {booth.unique_participants}명 · 마지막{' '}
        {timeAgo(booth.last_completed_at)}
      </p>
    </div>
  );
}

/** 추천 카드.
 *
 * **지시가 아니라 확인 요청입니다.** 그래서 상황 · 판단 근거 · 권장 행동을
 * 나눠 보여주고, 운영자가 현장을 보고 온 뒤 누를 두 버튼을 답니다. 그 판정은
 * 사후 리포트에서 추천 적중률로 집계되어 다음 축제에서 이 규칙을 점검하는
 * 근거가 됩니다.
 */
function RecommendationCards({
  festivalId,
  items,
  insights,
  onSetReward,
}: {
  festivalId: string;
  items: Recommendation[];
  insights: Insights;
  onSetReward: (boothId: number) => void;
}) {
  // 판정한 카드는 접는다. 같은 카드가 계속 떠 있으면 다음부터 아무도 안 읽는다.
  const [judged, setJudged] = useState<Record<string, boolean>>({});

  const feedback = useMutation({
    mutationFn: (v: { rec: Recommendation; verdict: boolean }) =>
      api.post(`/api/festivals/${festivalId}/recommendations/feedback`, {
        rec_type: v.rec.type,
        booth_id: v.rec.target_booth_id,
        // 지금이 아니라 **추천이 화면에 떠 있던 시각**이다. 확인하러 갔다 오는
        // 사이에 상태는 바뀐다.
        observed_at: insights.generated_at,
        verdict: v.verdict,
      }),
  });

  const key = (r: Recommendation) => `${r.type}:${r.target_booth_id}`;

  if (items.length === 0) {
    const enough = insights.kpi.completions_last_30m >= 10;
    return (
      <section className="card stack" style={{ gap: 'var(--space-2)' }}>
        <h2 className="section">FestaFlow 운영 인사이트</h2>
        <p className="muted">
          {enough
            ? '지금 확인을 요청할 만한 편중이 없습니다.'
            : '최근 30분 참여가 10건 미만이라 운영 판단을 내리기에 데이터가 부족합니다.'}
        </p>
      </section>
    );
  }

  return (
    <section className="stack" style={{ gap: 'var(--space-3)' }}>
      <h2 className="section">FestaFlow 운영 인사이트</h2>
      {items.map((r) => {
        const k = key(r);
        if (judged[k] !== undefined) {
          return (
            <div key={k} className="card reccard reccard--done">
              <span className="muted">
                {REC_LABEL[r.type]} — {judged[k] ? '확인함' : '해당 없음'}으로 기록했습니다.
              </span>
            </div>
          );
        }
        return (
          <article key={k} className="card reccard" data-kind={r.type}>
            <p className={`badge badge--${r.type === 'REDISTRIBUTE' ? 'risk' : 'caution'}`}>
              <i aria-hidden />
              {REC_LABEL[r.type]}
            </p>
            <p className="reccard__situation">{r.situation}</p>
            <p className="reccard__evidence">{r.evidence}</p>
            <p className="reccard__action">{r.action}</p>
            <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
              <button
                className="btn btn--primary"
                disabled={feedback.isPending}
                onClick={() => {
                  feedback.mutate({ rec: r, verdict: true });
                  setJudged((s) => ({ ...s, [k]: true }));
                }}
              >
                확인함
              </button>
              <button
                className="btn btn--ghost"
                disabled={feedback.isPending}
                onClick={() => {
                  feedback.mutate({ rec: r, verdict: false });
                  setJudged((s) => ({ ...s, [k]: false }));
                }}
              >
                해당 없음
              </button>
              {/* 자동 실행이 아니다 — 대상 부스만 채워 주고, 제출은 운영자가 한다.
                  참여 없음은 QR 이 안 보이는 문제일 수 있어 포인트를 올려도
                  완료는 그대로 0건이므로 이 버튼을 달지 않는다. */}
              {r.target_booth_id !== null && r.type === 'REDISTRIBUTE' && (
                <button
                  className="btn btn--ghost"
                  onClick={() => onSetReward(r.target_booth_id!)}
                >
                  추가 보상 설정
                </button>
              )}
              <Link to={`/festivals/${festivalId}/booths`} className="btn btn--ghost">
                이 부스 보기
              </Link>
            </div>
          </article>
        );
      })}
    </section>
  );
}
