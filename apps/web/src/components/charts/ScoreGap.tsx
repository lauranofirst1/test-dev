/** 잃은 점수 순위 — "어디부터 손대야 총점이 오르나".
 *
 * 불릿 차트와 **다른 질문에 답합니다.** 불릿은 배점 대비 달성률을 배점 순으로
 * 보여주고, 이 차트는 잃은 점수의 절대 크기를 큰 순으로 세웁니다.
 *
 * 두 순서는 어긋납니다. 배점이 가장 큰 혼잡·수용(30점)에서 4.8점을 잃고,
 * 배점이 그보다 작은 관광수요(25점)에서 10.3점을 잃었다면, 먼저 손댈 곳은
 * 뒤쪽입니다. 달성률만 보면 그 판단이 나오지 않습니다.
 *
 * **색은 순위가 아니라 등급을 담습니다.** 막대 길이가 이미 손실 크기를 말하므로,
 * 값이 클수록 진하게 칠하는 순위 색칠은 금지입니다(§7) — 유일하게 남은 채널이
 * 낭비됩니다. 대신 서버가 판정한 등급을 칠합니다. 이건 상태 인코딩이라 허용되고
 * (§3.1), 옆에 나란히 선 불릿 차트와 **색의 뜻이 같아집니다.**
 *
 * 한 화면에서 같은 빨강이 어떤 차트에서는 "위험 등급", 다른 차트에서는 "그냥
 * 손실 막대"를 뜻하면 둘 다 못 읽게 됩니다.
 */

import type { DiagnosisItem } from '../../api/types';
import { CATEGORY_LABEL, RISK_LABEL } from '../../api/types';
import { ChartFrame } from './ChartFrame';
import { useEChart, type ChartPalette } from './useEChart';

/** 등급색. 불릿 차트와 같은 함수를 쓴다 — 색의 뜻이 두 차트에서 같아야 한다. */
function levelColor(level: string, p: ChartPalette): string {
  if (level === 'stable') return p.stateLow;
  if (level === 'caution') return p.stateCaution;
  return p.stateHigh;
}

const MAX_FALLBACK: Record<string, number> = {
  tourism_demand: 25,
  crowd_safety: 30,
  program_balance: 20,
  local_linkage: 15,
  ops_readiness: 10,
};

export function ScoreGap({ items }: { items: DiagnosisItem[] }) {
  const rows = items
    .map((it) => {
      const max = it.max_score ?? MAX_FALLBACK[it.category] ?? 20;
      return { item: it, max, lost: Math.max(0, max - (it.score ?? 0)) };
    })
    .sort((a, b) => b.lost - a.lost);

  const totalLost = rows.reduce((sum, r) => sum + r.lost, 0);

  const box = useEChart(
    (p) => ({
      grid: { left: 118, right: 76, top: 8, bottom: 26 },
      tooltip: {
        trigger: 'item',
        backgroundColor: p.surface,
        borderColor: p.line,
        textStyle: { color: p.ink, fontSize: 13 },
        formatter: (params: { dataIndex: number }) => {
          const r = rows[params.dataIndex];
          const share = totalLost > 0 ? ((r.lost / totalLost) * 100).toFixed(0) : '0';
          return `<b>${CATEGORY_LABEL[r.item.category]}</b><br/>${r.lost.toFixed(
            1,
          )}점 손실 (배점 ${r.max}점)<br/>전체 손실의 ${share}% · ${RISK_LABEL[r.item.level]}`;
        },
      },
      xAxis: {
        type: 'value',
        min: 0,
        splitLine: { lineStyle: { color: p.grid, type: 'solid' } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: p.inkMute, fontSize: 11 },
      },
      yAxis: {
        type: 'category',
        data: rows.map((r) => CATEGORY_LABEL[r.item.category]),
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: p.ink, fontSize: 13, fontWeight: 500 },
      },
      series: [
        {
          type: 'bar',
          barWidth: 18,
          itemStyle: {
            borderRadius: [0, 4, 4, 0],
            color: (c: { dataIndex: number }) => levelColor(rows[c.dataIndex].item.level, p),
          },
          data: rows.map((r) => Number(r.lost.toFixed(1))),
          label: {
            show: true,
            position: 'right',
            distance: 10,
            color: p.inkSoft,
            fontSize: 12,
            fontWeight: 'bold',
            formatter: (c: { value: number }) => `-${c.value.toFixed(1)}점`,
          },
        },
      ],
    }),
    [rows.map((r) => `${r.item.category}:${r.lost}:${r.item.level}`).join('|')],
  );

  return (
    <ChartFrame
      title="어디서 점수를 잃었나"
      hint={`배점 대비 못 채운 점수입니다. 합계 ${totalLost.toFixed(1)}점 — 위쪽부터 손대는 것이 총점에 가장 크게 듭니다.`}
      height={Math.max(170, rows.length * 40 + 40)}
      table={{
        columns: ['항목', '잃은 점수', '배점', '전체 손실 중 비중', '등급'],
        rows: rows.map((r) => [
          CATEGORY_LABEL[r.item.category],
          `-${r.lost.toFixed(1)}`,
          r.max,
          totalLost > 0 ? `${((r.lost / totalLost) * 100).toFixed(0)}%` : '—',
          RISK_LABEL[r.item.level],
        ]),
      }}
    >
      <div ref={box} style={{ width: '100%', height: '100%' }} />
    </ChartFrame>
  );
}
