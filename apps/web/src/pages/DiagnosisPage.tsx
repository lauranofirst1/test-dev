/**
 * 사전 진단 화면 — 지정과제 9번의 사용자 접점.
 *
 * 점수만 크게 띄우지 않습니다. 점수 옆에 **계산 근거와 개선 제안**을 항상 붙이고,
 * 지표별로 조회값인지 추정값인지 표시합니다. 근거 없는 점수는 점술이기 때문입니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { Diagnosis, DiagnosisComparison, FestivalDetail } from '../api/types';
import { CATEGORY_LABEL, FULFILLMENT_LABEL, RISK_LABEL } from '../api/types';
import { BulletChart } from '../components/BulletChart';

export function DiagnosisPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

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
        <Link to="/" className="muted">
          ← 축제 목록
        </Link>
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
            <Link to={`/festivals/${id}/booths`} className="btn btn--ghost">
              부스 · 미션 관리
            </Link>
            <button
              className="btn btn--primary btn--lg"
              onClick={() => run.mutate()}
              disabled={run.isPending}
            >
              {run.isPending ? '관광 데이터 조회 중…' : d ? '다시 진단하기' : '진단 실행'}
            </button>
          </div>
        </div>
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

      {diagnosis.isLoading && <DiagnosisSkeleton />}

      {notFound && !run.isPending && (
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

      {d && (
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
      {/* 종합 */}
      <div className="card card--accent">
        <div className="row wrap" style={{ gap: 'var(--space-7)', alignItems: 'flex-start' }}>
          <div className="stack" style={{ gap: 4 }}>
            <p className="eyebrow">종합 준비도</p>
            {disclosed && d.total_score !== null ? (
              <>
                <div className="row" style={{ gap: 'var(--space-3)', alignItems: 'baseline' }}>
                  <span className="score tabular">{d.total_score.toFixed(1)}</span>
                  <span className="score__max">/ 100</span>
                  {d.risk && (
                    <span className={`badge badge--${d.risk}`}>
                      <i />
                      {RISK_LABEL[d.risk]}
                    </span>
                  )}
                </div>
              </>
            ) : (
              <>
                <span className="score score--muted">체크리스트</span>
                <p className="muted" style={{ maxWidth: '46ch' }}>
                  {d.disclosure_note}
                </p>
              </>
            )}
          </div>

          <div className="grow" />

          <div className="stack" style={{ gap: 6, minWidth: 220 }}>
            <BulletChart items={d.items} disclosed={disclosed} />
          </div>
        </div>

        {disclosed && d.disclosure_note && (
          <p className="disclaimer">{d.disclosure_note}</p>
        )}
      </div>

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
            <p className="eyebrow">다음 단계</p>
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
        <p className="eyebrow">직전 진단 대비</p>
        {disclosed && c.delta !== null && (
          <span className={`delta ${c.delta > 0 ? 'delta--up' : c.delta < 0 ? 'delta--down' : ''}`}>
            {c.delta > 0 ? '▲' : c.delta < 0 ? '▼' : '—'} {Math.abs(c.delta).toFixed(1)}점
          </span>
        )}
      </div>

      <div className="deltas">
        {c.items.map((item) => (
          <div className="deltas__row" key={item.category}>
            <span>{CATEGORY_LABEL[item.category]}</span>
            {disclosed && item.delta !== null ? (
              <span className="tabular">
                <span className="muted">{item.previous?.toFixed(1)}</span>
                <span className="muted"> → </span>
                <b>{item.current?.toFixed(1)}</b>
                <span
                  className={
                    item.delta > 0 ? 'delta--up' : item.delta < 0 ? 'delta--down' : 'muted'
                  }
                  style={{ marginLeft: 8 }}
                >
                  {item.delta > 0 ? '+' : ''}
                  {item.delta.toFixed(1)}
                </span>
              </span>
            ) : (
              <span className="muted">—</span>
            )}
          </div>
        ))}
      </div>

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
