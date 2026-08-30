/** 리포트 — 축제가 끝난 뒤 여는 화면.
 *
 * 담당자는 "사후 성과 리포트" 라고 말하지 않고 "리포트 뽑아야 해" 라고 말합니다.
 *
 * **이 화면이 그리지 않는 것이 그리는 것만큼 중요합니다.**
 *
 * - 실측 방문객이 없으면 참여율을 그리지 않습니다. 대신 예상 방문객 대비
 *   **참여 규모**로만 부르고, 그게 방문률이 아니라는 문구를 붙입니다.
 * - 측정하지 않는 지표에는 달성률 막대를 그리지 않습니다. 회색 참고값입니다.
 * - 미션 성공률을 만들지 않습니다. 시도자 분모를 모르기 때문입니다.
 *
 * 차트 라이브러리를 쓰지 않습니다 — 시간대 분포는 CSS 막대로 충분하고,
 * 이 화면은 인쇄해서 보고서에 붙이는 용도라 가벼울수록 좋습니다.
 */

import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import { ParticipationChart } from '../components/ParticipationChart';
import { KpiTargetEditor } from '../components/KpiTargetEditor';
import { VisitorCountEditor } from '../components/VisitorCountEditor';
import type { FestivalReport } from '../api/types';

const HOUR = (iso: string) => new Date(iso).getHours();

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** 참여율은 소수 첫째 자리까지 남긴다. 3.5% 를 3% 로 반올림하면 축제끼리
 *  비교할 때 차이가 통째로 사라진다 — 이 값은 대개 한 자릿수다. */
const rate = (v: number) => `${(v * 100).toFixed(1)}%`;

const sourceLabel = { mission: '미션', lecture: '특강', exhibit: '전시' } as const;
const contextLabel: Record<string, string> = {
  now: '지금', featured: '추천', explore_time: '시간별 둘러보기', explore_place: '장소별 둘러보기',
  explore_type: '유형별 둘러보기', search: '검색', shared_link: '공유 링크', flow: '나의 Flow',
};

export function ReportPage() {
  const { id = '' } = useParams<{ id: string }>();

  const report = useQuery({
    queryKey: ['report', id],
    queryFn: () => api.get<FestivalReport>(`/api/festivals/${id}/report`),
    retry: false,
  });

  const d = report.data;
  const peak = Math.max(1, ...(d?.timeline.map((t) => t.completions) ?? [0]));
  const boothPeak = Math.max(1, ...(d?.booths.map((b) => b.completions) ?? [0]));

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <div className="stack" style={{ gap: 4 }}>
            <p className="eyebrow">리포트</p>
            <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>
              {d?.festival_name ?? '불러오는 중…'}
            </h1>
          </div>
          <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
            <button className="btn btn--ghost" onClick={() => window.print()}>
              인쇄
            </button>
          </div>
        </div>
      </div>

      {report.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>
            <strong>리포트를 불러오지 못했습니다.</strong> {report.error.message}
          </span>
        </div>
      )}

      {report.isLoading && <div className="skeleton" style={{ height: 240 }} />}

      {d && (
        <>
          {/* ── 행사 결과 요약 ── */}
          <section className="grid2">
            <Stat label="FestaFlow 참여자" value={d.summary.unique_participants} unit="명" icon="◍" />
            <Stat label="총 미션 완료" value={d.summary.total_completions} unit="건" icon="✓" />
            <Stat
              label="참여자당 평균 완료"
              value={d.summary.avg_completions_per_participant}
              unit="건"
              icon="◑"
            />
            <Stat
              label="참여 발생 미션"
              value={d.summary.missions_with_completion.count}
              unit={`/ ${d.summary.missions_with_completion.total}개`}
              icon="▤"
            />
          </section>

          {/* 미션 성공률을 만들지 않는 이유를 화면에도 적는다. */}
          <p className="disclaimer">
            미션 시도자 수나 전체 현장 방문객을 알 수 없으므로 "미션 성공률"은 만들지
            않습니다. 위 값은 완료가 1건 이상 발생한 미션의 비율입니다.
          </p>

          {/* ── 방문객 대비 ── */}
          <section className="card stack" style={{ gap: 'var(--space-4)' }}>
            <h2 className="section">방문객 대비 참여</h2>

            {d.visitor_basis ? (
              <>
                <div className="row wrap" style={{ gap: 'var(--space-6)' }}>
                  <div>
                    <p className="muted">실측 방문객</p>
                    <p className="stat__value">
                      {d.visitor_basis.visitors.toLocaleString()}
                      <small>명</small>
                    </p>
                    <p className="muted">
                      {d.visitor_basis.source_label}
                      {d.visitor_basis.caveat && (
                        <b className="badge badge--caution" style={{ marginLeft: 6 }}>
                          <i aria-hidden />
                          {d.visitor_basis.caveat}
                        </b>
                      )}
                    </p>
                  </div>
                  <div>
                    <p className="muted">참여율</p>
                    <p className="stat__value">{rate(d.visitor_basis.participation_rate)}</p>
                    <p className="muted">고유 완료 참여자 ÷ 실측 방문객</p>
                  </div>
                </div>

                {/* 입구 계수기와 지자체 집계가 다른 건 정상이고, 숨기지 않는다. */}
                {d.visitor_basis.others.length > 0 && (
                  <p className="muted">
                    같은 기간 다른 출처:{' '}
                    {d.visitor_basis.others
                      .map((o) => `${o.source_label} ${o.visitors.toLocaleString()}명`)
                      .join(' · ')}
                  </p>
                )}
              </>
            ) : (
              <>
                <div className="row wrap" style={{ gap: 'var(--space-6)' }}>
                  <div>
                    <p className="muted">예상 방문객</p>
                    <p className="stat__value">
                      {d.plan_vs_actual.expected_visitors.toLocaleString()}
                      <small>명</small>
                    </p>
                  </div>
                  <div>
                    <p className="muted">참여 규모</p>
                    <p className="stat__value">{rate(d.plan_vs_actual.participation_scale)}</p>
                  </div>
                </div>
                {/* 이 문구가 빠지면 위 퍼센트는 방문률로 읽힌다. */}
                <p className="disclaimer">{d.plan_vs_actual.disclaimer}</p>
              </>
            )}

            <VisitorCountEditor festivalId={id} />
          </section>

          {/* ── 목표 대비 ── */}
          <section className="card stack" style={{ gap: 'var(--space-4)' }}>
            <h2 className="section">목표 대비 실제</h2>

            {d.kpi.length === 0 ? (
              <p className="muted">아직 성과 목표를 세우지 않았습니다.</p>
            ) : (
              <div className="stack" style={{ gap: 'var(--space-3)' }}>
                {d.kpi.map((k) => (
                  <div key={k.metric_key} className="kpirow" data-measurable={k.measurable}>
                    <div className="row wrap" style={{ justifyContent: 'space-between' }}>
                      <span style={{ fontWeight: 700 }}>{k.label}</span>
                      <span className="tabular">
                        {k.actual === null ? '—' : k.actual.toLocaleString()} /{' '}
                        {k.target.toLocaleString()}
                        {k.unit}
                        {k.achievement !== null && (
                          <b style={{ marginLeft: 8 }}>{pct(k.achievement)}</b>
                        )}
                      </span>
                    </div>
                    {/* 측정하지 않는 지표에는 막대를 그리지 않는다. 막대가 보이는
                        순간 그 값은 달성률로 읽힌다. */}
                    {k.achievement !== null ? (
                      <div className="loadbar">
                        <span
                          className="loadbar__fill"
                          style={{ width: `${Math.min(100, Math.round(k.achievement * 100))}%` }}
                        />
                      </div>
                    ) : (
                      <p className="muted">{k.note}</p>
                    )}
                  </div>
                ))}
              </div>
            )}

            <KpiTargetEditor festivalId={id} />
          </section>

          {/* ── 시간대 ──
              막대 열이었다. 하루짜리 축제에서는 읽혔지만 여러 날이 되면 열이
              수십 개로 늘어 이름표가 겹쳤다. 선으로 바꾸면 며칠이 이어져도
              모양이 남고, 당일 화면과 같은 그림이라 두 화면을 오갈 때 눈이
              다시 적응하지 않아도 된다. */}
          {d.timeline.length > 0 && (
            <section className="card stack" style={{ gap: 'var(--space-4)' }}>
              <h2 className="section">시간대별 완료</h2>
              <ParticipationChart
                points={d.timeline.map((t) => ({
                  at: t.hour_kst,
                  completions: t.completions,
                }))}
                peak={peak}
                caption="축제 전체 · 1시간 간격 · 한국 표준시(KST)"
                emptyNote="완료 기록이 한 시간대에만 있어 추이를 그리지 않았습니다."
              />
            </section>
          )}

          {/* ── 부스 ── */}
          {d.booths.length > 0 && (
            <section className="card stack" style={{ gap: 'var(--space-4)' }}>
              <h2 className="section">부스별 성과</h2>
              {/* 카드를 세로로 쌓던 자리다. 부스가 스무 개면 스무 번 스크롤해야
                  1위와 20위를 비교할 수 있었다. 표는 열을 맞춰 주므로 눈이
                  한 열만 따라 내려가면 된다. */}
              <div className="tablewrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th className="num">순위</th>
                      <th>부스</th>
                      <th>참여 분포</th>
                      <th className="num">완료</th>
                      <th className="num">참여자</th>
                      <th className="num">비율</th>
                      <th>최다 시간대</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.booths.map((b) => (
                      <tr key={b.booth_id}>
                        <td className="num tabular">{b.rank}</td>
                        <td>
                          <strong>{b.name}</strong>
                        </td>
                        <td>
                          <span className="minibar" aria-hidden>
                            <i
                              style={{
                                width: `${Math.round((b.completions / boothPeak) * 100)}%`,
                              }}
                            />
                          </span>
                        </td>
                        <td className="num tabular">{b.completions}</td>
                        <td className="num tabular">{b.unique_participants}</td>
                        <td className="num tabular">{pct(b.share)}</td>
                        <td className="muted tabular">
                          {b.peak_hour_kst
                            ? `${HOUR(b.peak_hour_kst)}시 · ${b.peak_completions}건`
                            : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* 부스가 보관되어 스냅샷이 풀린 참여. 어디에도 배정하지 않는다. */}
              {d.unassigned_completions > 0 && (
                <p className="muted">
                  부스 정보가 없는 완료 {d.unassigned_completions}건은 전체 합계에는
                  포함했지만 특정 부스에 배정하지 않았습니다.
                </p>
              )}
            </section>
          )}

          {/* ── 미션 ── */}
          {d.missions.length > 0 && (
            <section className="card stack" style={{ gap: 'var(--space-3)' }}>
              <h2 className="section">미션별 성과</h2>
              <div className="tablewrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>미션</th>
                      <th>부스</th>
                      <th className="num">완료</th>
                      <th className="num">참여자</th>
                      <th className="num">비율</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.missions.map((m) => (
                      <tr key={m.mission_id}>
                        <td>{m.title}</td>
                        <td className="muted">{m.booth_name ?? '축제 공통'}</td>
                        <td className="num tabular">{m.completions}</td>
                        <td className="num tabular">{m.unique_participants}</td>
                        <td className="num tabular">{pct(m.share)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* 열람은 완료로, 즐겨찾기는 만족도로 해석하지 않는다. */}
          {d.experience_insights.length > 0 && (
            <section className="card stack" style={{ gap: 'var(--space-4)' }}>
              <div className="stack" style={{ gap: 'var(--space-1)' }}>
                <h2 className="section">Experience 발견과 참여</h2>
                <p className="muted">상세 열람, 확인된 현장 행동, Favorite Memory를 서로 다른 신호로 표시합니다.</p>
              </div>
              <div className="tablewrap">
                <table className="table">
                  <thead><tr><th>Experience</th><th>발견 경로</th><th className="num">열람</th><th className="num">고유 열람자</th><th className="num">확인 참여</th><th className="num">완료</th><th className="num">Favorite</th></tr></thead>
                  <tbody>
                    {d.experience_insights.map((item) => (
                      <tr key={`${item.source_type}-${item.source_id}`}>
                        <td><strong>{item.title}</strong><br /><span className="muted">{sourceLabel[item.source_type]}</span></td>
                        <td className="muted">{Object.entries(item.discovery_contexts).map(([key, count]) => `${contextLabel[key] ?? key} ${count}`).join(' · ') || '—'}</td>
                        <td className="num tabular">{item.opens}</td>
                        <td className="num tabular">{item.unique_openers}</td>
                        <td className="num tabular">{item.verified_participants}</td>
                        <td className="num tabular">{item.completed_participants ?? '해당 없음'}</td>
                        <td className="num tabular">{item.favorites}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {d.experience_insights.some((item) => item.observations.length > 0) && (
                <ul className="stack" style={{ gap: 'var(--space-2)' }}>
                  {d.experience_insights.flatMap((item) => item.observations.map((note) => (
                    <li key={`${item.source_type}-${item.source_id}-${note}`} className="tip"><b>{item.title}</b> — {note}</li>
                  )))}
                </ul>
              )}
              <p className="disclaimer">열람은 관심 신호일 뿐 참여 완료가 아니며, 이 표는 발견 경로가 결과의 원인이라고 판단하지 않습니다.</p>
            </section>
          )}

          {/* ── 운영 개입 ── */}
          {(d.campaigns.length > 0 || d.recommendation_accuracy) && (
            <section className="card stack" style={{ gap: 'var(--space-4)' }}>
              <h2 className="section">운영 개입 결과</h2>

              {/* 제품이 자기 추천의 정확도를 스스로 보고하는 항목. */}
              {d.recommendation_accuracy && (
                <p>
                  운영 추천 {d.recommendation_accuracy.total}건 중{' '}
                  <b>{d.recommendation_accuracy.hits}건</b>이 현장과 일치했습니다 (
                  {pct(d.recommendation_accuracy.rate)}).
                </p>
              )}

              {d.campaigns.map((c) => (
                <div key={c.campaign_id} className="row wrap camprow">
                  <span style={{ fontWeight: 700 }}>{c.title}</span>
                  <span className="muted">{c.booth_name}</span>
                  {c.data_status === 'INSUFFICIENT_DATA' ? (
                    <span className="muted">표본 부족으로 변화를 읽지 않음</span>
                  ) : (
                    <span className="tabular">
                      비중 {c.share_change_pp > 0 ? '+' : ''}
                      {c.share_change_pp}%p
                      {c.in_progress && ' (집계 중)'}
                    </span>
                  )}
                </div>
              ))}

              {d.campaigns.length > 0 && (
                <p className="disclaimer">
                  캠페인 전후 참여 변화이며 보상의 인과 효과가 아닙니다.
                </p>
              )}
            </section>
          )}

          {/* ── 개선안 ── */}
          <section className="card stack" style={{ gap: 'var(--space-3)' }}>
            <h2 className="section">다음 축제 개선안</h2>
            <p className="muted">
              AI 가 아니라 정해진 규칙으로 만듭니다. 왜 이 문장이 나왔는지 언제나 되짚을 수
              있습니다.
            </p>
            <ul className="stack" style={{ gap: 'var(--space-2)' }}>
              {d.improvements.map((i, index) => (
                <li key={`${i.rule}-${index}`} className="tip">
                  {i.message}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
  icon,
}: {
  label: string;
  value: number;
  unit: string;
  icon: string;
}) {
  return (
    <div className="card kpi">
      <p className="kpi__label">
        <span className="kpi__chip" aria-hidden>
          {icon}
        </span>
        {label}
      </p>
      <p className="kpi__value">
        {value.toLocaleString()}
        <small>{unit}</small>
      </p>
    </div>
  );
}
