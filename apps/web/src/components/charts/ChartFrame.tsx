/** 차트 한 개를 감싸는 껍데기 — 제목, 설명, 그리고 **표 보기**.
 *
 * docs/06-charts.md §6 은 "모든 차트에 표 보기 토글이 있습니다"를 요구합니다.
 * 스크린리더와 인쇄, 그리고 "정확한 숫자가 필요한" 경우를 동시에 해결하기
 * 위해서입니다. 차트를 하나 더 만들 때마다 이 껍데기를 쓰면 그 요구가
 * 저절로 지켜집니다 — 껍데기 없이 그리면 반드시 빠뜨립니다.
 *
 * 표는 접혀 있을 때도 DOM 에 둡니다. `hidden` 이 아니라 시각적으로만 감추면
 * 스크린리더가 읽을 수 있고, 인쇄에도 함께 나갑니다.
 */

import { useId, useState } from 'react';

export interface TableSpec {
  columns: string[];
  rows: (string | number)[][];
}

export function ChartFrame({
  title,
  hint,
  table,
  height,
  children,
}: {
  title: string;
  hint?: string;
  /** 같은 데이터의 표 표현. 차트가 말하는 것을 숫자로 그대로 담는다. */
  table: TableSpec;
  /** 차트 높이(px). 행 수에 따라 호출부가 정한다. */
  height: number;
  children: React.ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  const id = useId();

  return (
    <section className="chart">
      <header className="chart__head">
        <div className="stack" style={{ gap: 2 }}>
          <h3 className="chart__title">{title}</h3>
          {hint && <p className="muted chart__hint">{hint}</p>}
        </div>
        <button
          type="button"
          className="btn btn--ghost chart__toggle"
          aria-pressed={asTable}
          aria-controls={id}
          onClick={() => setAsTable((v) => !v)}
        >
          {asTable ? '차트 보기' : '표 보기'}
        </button>
      </header>

      {/* 차트는 표 보기일 때만 감춘다. 표는 항상 DOM 에 남아 스크린리더·인쇄에 잡힌다. */}
      <div className="chart__canvas" style={{ height }} hidden={asTable}>
        {children}
      </div>

      <div id={id} className={asTable ? 'chart__table' : 'chart__table chart__table--folded'}>
        <table>
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr>
              {table.columns.map((c) => (
                <th key={c} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row) => (
              <tr key={String(row[0])}>
                {row.map((cell, i) =>
                  i === 0 ? (
                    <th key={i} scope="row">
                      {cell}
                    </th>
                  ) : (
                    <td key={i} className="tabular">
                      {cell}
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
