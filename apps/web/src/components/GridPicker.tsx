/** 조각 격자 후보 선택 — A안 · B안 · C안.
 *
 * 조각 수는 단독으로 정할 값이 아닙니다. 지급 단위(부스 또는 미션) 수보다 많으면
 * 아무도 완성할 수 없고, 적으면 그만큼의 부스가 조각 없이 남습니다. 그래서 후보를
 * **서버가 계산해** 내려주고(`GET /api/stamp-board/grid-options`) 화면은 고르게만
 * 합니다. 같은 규칙이 화면에도 살면 반드시 어긋납니다.
 *
 * 후보는 숫자가 아니라 **실제 그림을 그 격자로 쪼갠 미리보기**로 보여줍니다.
 * "3×4 · 12조각"은 감이 오지 않지만 쪼개진 그림은 바로 읽힙니다.
 */

import { useQuery } from '@tanstack/react-query';

import { api } from '../api/client';
import type { GridOption } from '../api/types';
import { subject, topic } from '../lib/particles';

export interface Grid {
  rows: number;
  cols: number;
}

const PLAN_LABELS = ['A안', 'B안', 'C안', 'D안', 'E안'];

export function useGridOptions(unitCount: number) {
  return useQuery({
    queryKey: ['grid-options', unitCount],
    queryFn: () => api.get<GridOption[]>(`/api/stamp-board/grid-options?unit_count=${unitCount}`),
    enabled: unitCount > 0,
    staleTime: 60 * 60_000, // 순수 계산이라 바뀌지 않는다
  });
}

export function GridPlanPicker({
  options,
  value,
  onChange,
  imageUrl,
  unitLabel,
  unitCount,
}: {
  options: GridOption[];
  value: Grid;
  onChange: (g: Grid) => void;
  /** 미리보기에 쓸 그림. 없으면 색 블록으로 보여준다. */
  imageUrl?: string;
  unitLabel: string;
  unitCount: number;
}) {
  if (options.length === 0) {
    return (
      <div className="notice notice--warn">
        <span>⚠</span>
        <span>
          {unitLabel}
          {subject(unitLabel)} {unitCount}개라 나눌 수 있는 격자가 없습니다. 최소 4개가 필요합니다.
        </span>
      </div>
    );
  }

  return (
    <div className="plans">
      {options.map((o, i) => {
        const on = o.rows === value.rows && o.cols === value.cols;
        return (
          <button
            key={`${o.rows}x${o.cols}`}
            type="button"
            className={`plan${on ? ' plan--on' : ''}`}
            aria-pressed={on}
            onClick={() => onChange({ rows: o.rows, cols: o.cols })}
          >
            <span className="plan__head">
              <span className="plan__name">{PLAN_LABELS[i] ?? `${i + 1}안`}</span>
              {o.exact && <span className="plan__badge">딱 맞음</span>}
            </span>

            <GridPreview rows={o.rows} cols={o.cols} imageUrl={imageUrl} />

            <span className="plan__total tabular">
              {o.total}조각 · {o.rows}×{o.cols}
            </span>
            <span className="plan__note">
              {o.exact
                ? `${unitLabel} ${unitCount}개가 각각 한 조각`
                : `${unitLabel} ${o.leftover}개는 조각 없음`}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** 그림을 격자로 쪼갠 미리보기. 실제 관객 보드와 같은 방식으로 자른다. */
export function GridPreview({
  rows,
  cols,
  imageUrl,
}: {
  rows: number;
  cols: number;
  imageUrl?: string;
}) {
  return (
    <span
      className="gridprev"
      style={{
        gridTemplateColumns: `repeat(${cols}, 1fr)`,
        ['--grid-ratio' as string]: `${cols} / ${rows}`,
      }}
      aria-hidden="true"
    >
      {Array.from({ length: rows * cols }, (_, i) => (
        <i
          key={i}
          style={
            imageUrl
              ? {
                  backgroundImage: `url(${imageUrl})`,
                  backgroundSize: `${cols * 100}% ${rows * 100}%`,
                  backgroundPosition: `${(i % cols) * (100 / (cols - 1 || 1))}% ${
                    Math.floor(i / cols) * (100 / (rows - 1 || 1))
                  }%`,
                }
              : undefined
          }
        />
      ))}
    </span>
  );
}

/** 조각 수와 지급 단위 수의 관계를 한 줄로 설명한다. */
export function gridBasisHint(unitLabel: string, unitCount: number): string {
  return `조각 수가 지급 단위보다 많으면 아무도 완성할 수 없습니다. 지금 기준이 되는 활성 ${unitLabel}${topic(unitLabel)} ${unitCount}개입니다.`;
}
