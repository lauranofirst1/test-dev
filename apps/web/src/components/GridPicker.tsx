/** 조각 격자 선택.
 *
 * 01-product-spec §5.2 는 2×2(4조각) / 2×3(6조각) / 3×3(9조각) 중 **선택**으로
 * 정의합니다. 숫자만 나열하면 감이 오지 않아 실제 격자 모양을 작게 그립니다.
 *
 * 지급 단위 수(부스 또는 미션)를 넘기면 완성 불가능한 격자에 표시를 붙입니다.
 * 조각 수는 단독으로 정할 값이 아니라 부스 계획과 함께 정해지는 값이기 때문입니다.
 */

import { topic } from '../lib/particles';

export interface Grid {
  rows: number;
  cols: number;
}

/** DB 의 grid_supported CHECK 와 같은 집합. 한쪽만 늘리면 422 로 튕긴다. */
export const GRIDS: (Grid & { label: string })[] = [
  { rows: 2, cols: 2, label: '2×2 · 4조각' },
  { rows: 2, cols: 3, label: '2×3 · 6조각' },
  { rows: 3, cols: 3, label: '3×3 · 9조각' },
];

export function GridPicker({
  value,
  onChange,
  unitCount,
  unitLabel,
}: {
  value: Grid;
  onChange: (g: Grid) => void;
  /** 지급 단위 수. 모르면 생략하면 경고를 붙이지 않는다. */
  unitCount?: number;
  unitLabel?: string;
}) {
  return (
    <div className="gridpick">
      {GRIDS.map((g) => {
        const on = g.rows === value.rows && g.cols === value.cols;
        const impossible = unitCount !== undefined && g.rows * g.cols > unitCount;
        return (
          <button
            key={g.label}
            type="button"
            className={`gridopt${on ? ' gridopt--on' : ''}`}
            aria-pressed={on}
            onClick={() => onChange({ rows: g.rows, cols: g.cols })}
          >
            <span
              className="gridopt__preview"
              style={{ gridTemplateColumns: `repeat(${g.cols}, 1fr)` }}
              aria-hidden="true"
            >
              {Array.from({ length: g.rows * g.cols }, (_, i) => (
                <i key={i} />
              ))}
            </span>
            <span className="gridopt__label">{g.label}</span>
            {impossible && (
              <span className="gridopt__warn">{unitLabel ?? '지급 단위'} 부족</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** 조각 수와 지급 단위 수의 관계를 한 줄로 설명한다. */
export function gridBasisHint(unitLabel: string, unitCount: number): string {
  return `조각 수가 지급 단위보다 많으면 아무도 완성할 수 없습니다. 지금 기준이 되는 활성 ${unitLabel}${topic(unitLabel)} ${unitCount}개입니다.`;
}
