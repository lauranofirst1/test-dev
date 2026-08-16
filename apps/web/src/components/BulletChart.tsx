/**
 * 진단 5항목 불릿 차트.
 *
 * 레이더 차트를 쓰지 않는 이유 — 배점이 25·30·20·15·10 으로 다른 항목을
 * 같은 반지름에 놓으면 왜곡되고, 축 순서만 바꿔도 면적이 달라진다.
 * 불릿은 "배점 대비 얼마"를 정확히 보여준다.
 *
 * 트랙 길이가 배점을 그대로 나타내므로, 30점짜리 항목의 트랙이 가장 길다.
 */

import type { DiagnosisItem } from '../api/types';
import { CATEGORY_LABEL, FULFILLMENT_LABEL } from '../api/types';

interface Props {
  items: DiagnosisItem[];
  /** checklist 모드면 점수 대신 충족 상태만 보여준다 */
  disclosed: boolean;
}

const LEVEL_CLASS = { stable: 'stable', caution: 'caution', risk: 'risk' } as const;

export function BulletChart({ items, disclosed }: Props) {
  const maxOfAll = Math.max(...items.map((i) => i.max_score ?? scoreMaxFallback(i)), 1);

  return (
    <div className="bullet" role="table" aria-label="진단 항목별 점수">
      {items.map((item) => {
        const max = item.max_score ?? scoreMaxFallback(item);
        const score = item.score ?? 0;
        const trackWidth = (max / maxOfAll) * 100;
        const fillWidth = max > 0 ? (score / max) * 100 : 0;

        return (
          <div className="bullet__row" role="row" key={item.category}>
            <span className="bullet__label" role="cell">
              {CATEGORY_LABEL[item.category]}
            </span>

            <div className="bullet__trackwrap" role="cell">
              <div className="bullet__track" style={{ width: `${trackWidth}%` }}>
                {disclosed && (
                  <>
                    <div
                      className={`bullet__fill bullet__fill--${LEVEL_CLASS[item.level]}`}
                      style={{ width: `${fillWidth}%` }}
                    />
                    <div className="bullet__tick" style={{ left: `${fillWidth}%` }} />
                  </>
                )}
                {!disclosed && (
                  <div className={`bullet__checklist bullet__checklist--${LEVEL_CLASS[item.level]}`}>
                    {FULFILLMENT_LABEL[item.fulfillment]}
                  </div>
                )}
              </div>
            </div>

            <span className="bullet__value tabular" role="cell">
              {disclosed ? (
                <>
                  <b>{score.toFixed(1)}</b>
                  <span className="bullet__max">/{max}</span>
                </>
              ) : (
                <span className={`bullet__fulfil bullet__fulfil--${LEVEL_CLASS[item.level]}`}>
                  {FULFILLMENT_LABEL[item.fulfillment]}
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** checklist 모드에서는 max_score 가 null 이라 배점표 기본값으로 트랙 길이를 잡는다. */
function scoreMaxFallback(item: DiagnosisItem): number {
  const defaults: Record<string, number> = {
    tourism_demand: 25,
    crowd_safety: 30,
    program_balance: 20,
    local_linkage: 15,
    ops_readiness: 10,
  };
  return defaults[item.category] ?? 20;
}
