/** 종합 준비도 스탯 타일 — docs/06-charts.md §3.3 "스탯 타일 + 상태 배지, 게이지 금지".
 *
 * **게이지를 쓰지 않는 이유.** 반원 게이지는 각도로 크기를 읽게 하는데, 사람은
 * 각도 비교를 길이 비교만큼 못 합니다. 76점과 82점이 게이지에서는 거의 같아 보입니다.
 * 그리고 게이지는 구간(빨강·노랑·초록)을 그리게 유도하는데, 그 임계값을 서버가
 * 주지 않으므로 눈대중으로 그리면 없는 근거를 만드는 셈입니다.
 *
 * 대신 **0~100 자 위의 위치**를 씁니다. 길이 비교라 정확하고, 구간을 칠하지
 * 않으므로 임계값을 지어내지 않습니다. 등급은 서버가 판정한 값을 배지로 답니다.
 *
 * 라이브러리를 쓰지 않습니다 — 축도 범례도 없는 그림에 차트 인스턴스를 띄우는
 * 것은 낭비입니다(§1).
 */

import type { RiskLevel } from '../../api/types';
import { RISK_LABEL } from '../../api/types';

export function ScoreTile({
  score,
  risk,
  previous,
}: {
  score: number;
  risk: RiskLevel | null;
  /** 직전 진단 총점. 있으면 자 위에 흔적으로 남긴다. */
  previous?: number | null;
}) {
  const pct = Math.max(0, Math.min(100, score));
  const prevPct = previous == null ? null : Math.max(0, Math.min(100, previous));
  const delta = previous == null ? null : score - previous;

  return (
    <div className="scoretile">
      <div className="row wrap" style={{ gap: 'var(--space-3)', alignItems: 'baseline' }}>
        <span className="score tabular">{score.toFixed(1)}</span>
        <span className="score__max">/ 100</span>
        {risk && (
          <span className={`badge badge--${risk}`}>
            <i />
            {RISK_LABEL[risk]}
          </span>
        )}
        {delta !== null && Math.abs(delta) >= 0.05 && (
          <span className={`delta ${delta > 0 ? 'delta--up' : 'delta--down'}`}>
            {delta > 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}
          </span>
        )}
      </div>

      {/* 0~100 자. 구간을 칠하지 않는다 — 임계값을 모르기 때문이다. */}
      <div
        className="scoretile__ruler"
        role="img"
        aria-label={`종합 준비도 100점 만점에 ${score.toFixed(1)}점${
          risk ? `, ${RISK_LABEL[risk]}` : ''
        }`}
      >
        <div className={`scoretile__fill scoretile__fill--${risk ?? 'none'}`} style={{ width: `${pct}%` }} />
        {prevPct !== null && (
          <span
            className="scoretile__prev"
            style={{ left: `${prevPct}%` }}
            title={`직전 ${previous!.toFixed(1)}점`}
          />
        )}
        {[25, 50, 75].map((t) => (
          <span key={t} className="scoretile__tick" style={{ left: `${t}%` }} aria-hidden="true" />
        ))}
      </div>
      <div className="scoretile__scale tabular" aria-hidden="true">
        <span>0</span>
        <span>50</span>
        <span>100</span>
      </div>
    </div>
  );
}
