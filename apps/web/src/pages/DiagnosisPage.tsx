/**
 * 사전 진단 화면 — 지정과제 9번의 사용자 접점.
 *
 * 점수만 크게 띄우지 않습니다. 점수 옆에 **계산 근거와 개선 제안**을 항상 붙이고,
 * 지표별로 조회값인지 추정값인지 표시합니다. 근거 없는 점수는 점술이기 때문입니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { PlanEditor } from '../components/PlanEditor';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { Diagnosis, DiagnosisComparison, FestivalDetail } from '../api/types';
import { CATEGORY_LABEL, FULFILLMENT_LABEL } from '../api/types';
import { BulletChart } from '../components/BulletChart';
import {
  LazyDeltaDumbbell,
  LazyScoreBullet,
  LazyScoreGap,
} from '../components/charts/lazy';
// 스탯 타일은 CSS 만 쓴다(§1) — 지연 로드할 것이 없다.
import { ScoreTile } from '../components/charts/ScoreTile';

export function DiagnosisPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  /** 탭을 주소에 둔다. 새로고침하거나 링크를 건네도 같은 탭이 열려야 하고,
   *  «기획 고치기» 를 보내 놓고 상대가 점수 탭을 보는 일이 없어야 한다. */
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'plan' ? 'plan' : 'score';
  const goTab = (next: 'score' | 'plan') => {
    const p = new URLSearchParams(params);
    if (next === 'score') p.delete('tab');
    else p.set('tab', next);
    setParams(p, { replace: true });
  };

  const festival = useQuery({
    queryKey: ['festival', id],
    queryFn: () => api.get<FestivalDetail>(`/api/festivals/${id}`),
  });

  const diagnosis = useQuery({
    queryKey: ['diagnosis', id],
    queryFn: () => api.get<Diagnosis>(`/api/festivals/${id}/diagnoses/latest`),
    retry: false,
  });

  const comparison = useQuery({
    queryKey: ['comparison', id],
    queryFn: () => api.get<DiagnosisComparison>(`/api/festivals/${id}/diagnoses/comparison`),
    retry: false,
  });

  const run = useMutation({
    mutationFn: () => api.post<Diagnosis>(`/api/festivals/${id}/diagnoses`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['diagnosis', id] });
      qc.invalidateQueries({ queryKey: ['comparison', id] });
    },
  });

  const f = festival.data;
  const d = diagnosis.data;
  const notFound = diagnosis.error instanceof ApiError && diagnosis.error.status === 404;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <div className="stack" style={{ gap: 4 }}>
            <p className="eyebrow">사전 진단</p>
            <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>
              {f?.name ?? '불러오는 중…'}
            </h1>
            {f && (
              <p className="muted">
                {f.region} · {f.venue} · {f.starts_on}~{f.ends_on} ({f.duration_days}일) ·
                예상 {f.expected_visitors.toLocaleString()}명 · 부스 {f.booth_count}개
              </p>
            )}
          </div>
          <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
            {/* 어느 탭에 있든 여기 있다. 고치는 도중에 "이제 다시 재 보자" 가
                되는 것이 이 루프의 전부다. */}
            <button
              className="btn btn--primary btn--lg"
              data-tour="diagnosis-run"
              onClick={() => {
                goTab('score');
                run.mutate();
              }}
              disabled={run.isPending}
            >
              {run.isPending ? '관광 데이터 조회 중…' : d ? '다시 진단하기' : '진단 실행'}
            </button>
          </div>
        </div>
      </div>

      {/* 탭은 두 개뿐이고 둘은 한 루프의 두 자리다 — 점수를 보고, 고치고,
          다시 잰다. 예전에는 별개 화면이라 고치러 가면 점수가 사라졌다. */}
      <div className="tabs" role="tablist" aria-label="사전 진단">
        <button
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={tab === 'score'}
          onClick={() => goTab('score')}
        >
          점수
          {d?.total_score != null && (
            <b className="tabs__num tabular">{d.total_score.toFixed(1)}</b>
          )}
        </button>
        <button
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={tab === 'plan'}
          onClick={() => goTab('plan')}
        >
          기획 고치기
        </button>
      </div>

      {run.isPending && (
        <div className="notice notice--info">
          <span>◐</span>
          <span>
            한국관광공사 OpenAPI 를 실시간으로 호출하고 있습니다. 지역에 따라 10초 정도 걸립니다.
          </span>
        </div>
      )}

      {run.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>
            <strong>진단에 실패했습니다.</strong> {run.error.message}
          </span>
        </div>
      )}

      {tab === 'plan' && <PlanEditor onSaved={() => goTab('score')} />}

      {tab === 'score' && diagnosis.isLoading && <DiagnosisSkeleton />}

      {tab === 'score' && notFound && !run.isPending && (
        <div className="card state">
          <p className="eyebrow">아직 진단 결과가 없습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            한국관광공사 데이터로 이 축제의 준비도를 진단합니다.
            <br />
            관광 수요·수용력·프로그램 구성·지역 연계·운영 준비를 5개 항목으로 점검합니다.
          </p>
          <button
            className="btn btn--primary btn--lg"
            onClick={() => run.mutate()}
            disabled={run.isPending}
          >
            진단 실행
          </button>
        </div>
      )}

      {tab === 'score' && d && (
        <DiagnosisResult
          d={d}
          comparison={comparison.data}
          festivalId={id ?? ''}
          boothCount={f?.booth_count ?? 0}
        />
      )}
    </div>
  );
}

function DiagnosisResult({
  d,
  comparison,
  festivalId,
  boothCount,
}: {
  d: Diagnosis;
  comparison?: DiagnosisComparison;
  festivalId: string;
  /** 부스가 없으면 프로그램 균형·운영 준비도가 예정값으로 계산된다. */
  boothCount: number;
}) {
  const disclosed = d.score_disclosed;

  return (
    <>
      {/* 종합 — 숫자 하나에 차트를 붙이지 않는다(§3.1). 스탯 타일 + 상태 배지. */}
      <div className="card card--accent">
        <p className="eyebrow" data-tour="diagnosis-total">종합 준비도</p>
        {disclosed && d.total_score !== null ? (
          <ScoreTile
            score={d.total_score}
            risk={d.risk}
            previous={comparison?.comparable ? comparison.previous?.total_score : null}
          />
        ) : (
          <div className="stack" style={{ gap: 4, marginTop: 'var(--space-2)' }}>
            <span className="score score--muted">체크리스트</span>
            <p className="muted" style={{ maxWidth: '46ch' }}>
              {d.disclosure_note}
            </p>
            {/* 점수를 공개하지 않는 모드에서는 충족 상태만 CSS 로 보여준다. */}
            <div style={{ marginTop: 'var(--space-4)' }}>
              <BulletChart items={d.items} disclosed={false} />
            </div>
          </div>
        )}

        {disclosed && d.disclosure_note && (
          <p className="disclaimer">{d.disclosure_note}</p>
        )}
      </div>

      {/* 항목별 — 두 차트가 서로 다른 질문에 답한다.
          불릿: 배점 대비 얼마나 찼나. 손실: 어디부터 손대야 총점이 오르나. */}
      {disclosed && (
        <div className="chartgrid" data-tour="diagnosis-score">
          <div className="card">
            <LazyScoreBullet items={d.items} disclosed={disclosed} />
          </div>
          <div className="card">
            <LazyScoreGap items={d.items} />
          </div>
        </div>
      )}

      {/* 경고 */}
      {d.warnings.map((w) => (
        <div className="notice notice--warn" key={w}>
          <span>⚠</span>
          <span>{w}</span>
        </div>
      ))}

      {/* 주요 위험요소 */}
      {d.top_risks.length > 0 && (
        <div className="card">
          <p className="eyebrow" style={{ marginBottom: 'var(--space-4)' }}>
            주요 위험요소
          </p>
          <ul className="risks">
            {d.top_risks.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 직전 대비 */}
      {comparison && <ComparisonCard c={comparison} disclosed={disclosed} />}

      {/* 항목별 상세 */}
      <div className="stack" style={{ gap: 'var(--space-4)' }}>
        {d.items.map((item) => (
          <article className="card item" key={item.category}>
            <div className="row wrap" style={{ justifyContent: 'space-between' }}>
              <h3>{CATEGORY_LABEL[item.category]}</h3>
              {disclosed && item.score !== null ? (
                <span className="tabular soft">
                  <b style={{ fontSize: 'var(--text-h3)' }}>{item.score.toFixed(1)}</b>
                  <span className="muted"> / {item.max_score}</span>
                </span>
              ) : (
                <span className={`badge badge--${item.level}`}>
                  <i />
                  {FULFILLMENT_LABEL[item.fulfillment]}
                </span>
              )}
            </div>
            <div className="item__block">
              <span className="item__tag">계산 근거</span>
              <p className="soft">{item.reason}</p>
            </div>
            <div className="item__block">
              <span className="item__tag item__tag--rec">개선 제안</span>
              <p className="soft">{item.recommendation}</p>
            </div>
          </article>
        ))}
      </div>

      {/* 다음 단계 — 권고와 행동을 같은 흐름에 둔다.
          "부스를 등록하면 실제 구성으로 평가됩니다"라고 말하면서 등록할 곳을
          알려주지 않으면, 읽은 사람은 무엇을 해야 하는지 모른다. */}
      {boothCount === 0 && (
        <div className="card card--accent stack" style={{ gap: 'var(--space-4)' }}>
          <div className="stack" style={{ gap: 4 }}>
            <p className="eyebrow" data-tour="diagnosis-next">다음 단계</p>
            <h3 style={{ fontSize: 'var(--text-h3)' }}>부스를 등록하면 점수가 달라집니다</h3>
          </div>
          <p className="soft">
            지금 <strong>프로그램 균형</strong>과 <strong>운영 준비도</strong>는 기획서에 적은
            예정값으로 계산됐습니다. 부스와 미션을 등록하면 실제 구성으로 평가되고, 현장에서
            QR 참여를 측정할 수 있습니다. 등록한 뒤 <strong>다시 진단</strong>하면 직전 결과와
            비교해 개선 효과를 보여드립니다.
          </p>
          <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
            <Link to={`/festivals/${festivalId}/booths`} className="btn btn--primary btn--lg">
              부스 등록하러 가기
            </Link>
          </div>
        </div>
      )}

      {/* 데이터 출처 */}
      {d.tourism_source && (
        <div className="card card--sunk">
          <p className="eyebrow" style={{ marginBottom: 'var(--space-3)' }}>
            데이터 출처
          </p>
          <p className="soft" style={{ fontSize: 'var(--text-sm)', lineHeight: 1.6 }}>
            {d.tourism_source.note}
          </p>
          <div className="row wrap" style={{ gap: 'var(--space-2)', marginTop: 'var(--space-4)' }}>
            {Object.entries(d.tourism_source.indicators).map(([key, kind]) => (
              <span className={`src src--${kind === '조회' ? 'measured' : 'estimated'}`} key={key}>
                {key} <b>{kind}</b>
              </span>
            ))}
          </div>
          <p className="muted" style={{ marginTop: 'var(--space-4)' }}>
            기준월 {d.tourism_source.base_month}
            {d.api_calls !== null && ` · 실시간 API 호출 ${d.api_calls}회`} · 진단 #{d.id}
          </p>
        </div>
      )}
    </>
  );
}

function ComparisonCard({ c, disclosed }: { c: DiagnosisComparison; disclosed: boolean }) {
  if (!c.comparable) {
    const message =
      c.reason === 'PROVIDER_MISMATCH'
        ? '직전 진단과 관광 데이터 출처가 달라 비교하지 않습니다. 외부 API 상태 차이를 기획 개선 효과로 오해할 수 있기 때문입니다.'
        : '기획을 수정하고 다시 진단하면 직전 결과와 비교해 개선 효과를 보여드립니다.';
    return (
      <div className="notice notice--info">
        <span>ⓘ</span>
        <span>{message}</span>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <p className="eyebrow" data-tour="diagnosis-delta">직전 진단 대비</p>
        {disclosed && c.delta !== null && (
          <span className={`delta ${c.delta > 0 ? 'delta--up' : c.delta < 0 ? 'delta--down' : ''}`}>
            {c.delta > 0 ? '▲' : c.delta < 0 ? '▼' : '—'} {Math.abs(c.delta).toFixed(1)}점
          </span>
        )}
      </div>

      {/* 나란한 막대 두 개는 "증가했다"가 아니라 "두 개가 있다"로 읽힌다.
          덤벨이 방향과 크기를 하나의 획으로 보여준다(§3.2). */}
      {disclosed && <LazyDeltaDumbbell c={c} />}

      {/* 점수를 공개하지 않는 모드에서는 덤벨을 그릴 값이 없다. 그때만 목록을 쓴다. */}
      {!disclosed && (
        <div className="deltas deltas--folded">
          {c.items.map((item) => (
            <div className="deltas__row" key={item.category}>
              <span>{CATEGORY_LABEL[item.category]}</span>
              <span className="muted">—</span>
            </div>
          ))}
        </div>
      )}

      {c.biggest_improvement && (
        <div className="improve">
          <span className="item__tag">가장 큰 개선 · {c.biggest_improvement.label}</span>
          <p className="soft">{c.biggest_improvement.reason}</p>
          <p className="soft">{c.biggest_improvement.recommendation}</p>
        </div>
      )}
    </div>
  );
}

function DiagnosisSkeleton() {
  return (
    <div className="stack" style={{ gap: 'var(--space-4)' }}>
      <div className="skeleton" style={{ height: 180 }} />
      <div className="skeleton" style={{ height: 120 }} />
      <div className="skeleton" style={{ height: 120 }} />
    </div>
  );
}
