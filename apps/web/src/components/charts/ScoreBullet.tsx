/** 진단 5항목 불릿 차트 — docs/06-charts.md §3.3.
 *
 * **레이더를 쓰지 않는 이유**가 이 차트의 존재 이유입니다. 배점이 30·25·20·15·10
 * 으로 다른 항목을 같은 반지름에 놓으면 왜곡되고, 축 순서만 바꿔도 면적이 달라집니다.
 * 불릿은 트랙 길이가 곧 배점이라 "30점짜리 항목"과 "10점짜리 항목"이 눈으로 구분되고,
 * 채운 길이가 "그중 얼마"를 정확히 말합니다.
 *
 * **등급 밴드(위험/주의/안정 구간)를 그리지 않습니다.** API 가 임계값을 주지 않기
 * 때문입니다. 눈대중으로 구간을 그리면 없는 근거를 화면이 만들어 내는 셈이고,
 * 이 제품이 점수 옆에 항상 계산 근거를 붙이는 이유와 정면으로 어긋납니다.
 * 막대 색이 서버가 판정한 등급을 담고, 그 등급은 라벨로도 함께 나갑니다(§2.2).
 *
 * 값 축은 0 에서 시작합니다(§7). 배점이 가장 큰 항목이 축 끝을 정합니다.
 */

import type { DiagnosisItem } from '../../api/types';
import { CATEGORY_LABEL, FULFILLMENT_LABEL, RISK_LABEL } from '../../api/types';
import { ChartFrame } from './ChartFrame';
import { useEChart, type ChartPalette } from './useEChart';

const MAX_FALLBACK: Record<string, number> = {
  tourism_demand: 25,
  crowd_safety: 30,
  program_balance: 20,
  local_linkage: 15,
  ops_readiness: 10,
};

function maxOf(item: DiagnosisItem): number {
  return item.max_score ?? MAX_FALLBACK[item.category] ?? 20;
}

/** 등급색. 상태는 정체성이 아니라 상태이므로 상태 팔레트를 쓴다(§2.2). */
function levelColor(level: string, p: ChartPalette): string {
  if (level === 'stable') return p.stateLow;
  if (level === 'caution') return p.stateCaution;
  return p.stateHigh;
}

export function ScoreBullet({
  items,
  disclosed,
}: {
  items: DiagnosisItem[];
  /** checklist 모드면 점수가 없다. 트랙과 충족 상태만 보여준다. */
  disclosed: boolean;
}) {
  // 배점 큰 순으로 세운다. 트랙 길이가 단조 감소해 계단처럼 읽힌다.
  const rows = [...items].sort((a, b) => maxOf(b) - maxOf(a));
  const axisMax = Math.max(...rows.map(maxOf), 1);

  const box = useEChart(
    (p) => ({
      grid: { left: 118, right: 64, top: 8, bottom: 26 },
      tooltip: {
        trigger: 'item',
        backgroundColor: p.surface,
        borderColor: p.line,
        textStyle: { color: p.ink, fontSize: 13 },
        formatter: (params: { dataIndex: number }) => {
          const it = rows[params.dataIndex];
          const max = maxOf(it);
          const label = CATEGORY_LABEL[it.category];
          if (!disclosed || it.score === null) {
            return `<b>${label}</b><br/>${FULFILLMENT_LABEL[it.fulfillment]} · 배점 ${max}점`;
          }
          const pct = ((it.score / max) * 100).toFixed(0);
          return `<b>${label}</b><br/>${it.score.toFixed(1)} / ${max}점 (${pct}%)<br/>${RISK_LABEL[it.level]}`;
        },
      },
      xAxis: {
        type: 'value',
        min: 0, // §7 — 막대 값 축은 반드시 0에서 시작
        max: axisMax,
        splitLine: { lineStyle: { color: p.grid, type: 'solid' } }, // 점선 격자 금지
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: p.inkMute, fontSize: 11 },
      },
      yAxis: {
        type: 'category',
        data: rows.map((r) => CATEGORY_LABEL[r.category]),
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: p.ink, fontSize: 13, fontWeight: 500 },
      },
      series: [
        {
          // 트랙 = 배점. 이 막대의 길이 자체가 "이 항목이 총점에서 차지하는 몫"이다.
          type: 'bar',
          silent: true,
          barWidth: 22,
          // 트랙이 너무 흐리면 배점 차이가 안 보인다. 배점 차이는 이 차트가
          // 레이더 대신 존재하는 이유이므로 읽혀야 한다.
          itemStyle: { color: p.grid, borderRadius: [0, 4, 4, 0] },
          data: rows.map(maxOf),
          z: 1,
        },
        {
          // 실측 = 획득 점수. 트랙 위에 겹쳐 그린다.
          type: 'bar',
          barWidth: 22,
          barGap: '-100%',
          itemStyle: {
            borderRadius: [0, 4, 4, 0], // 데이터 끝만 라운드, 기준선 쪽은 각지게(§4)
            color: (c: { dataIndex: number }) => levelColor(rows[c.dataIndex].level, p),
          },
          data: disclosed ? rows.map((r) => r.score ?? 0) : rows.map(() => 0),
          label: {
            show: disclosed,
            position: 'right',
            distance: 10,
            color: p.inkSoft,
            fontSize: 12,
            fontWeight: 'bold',
            formatter: (c: { dataIndex: number }) => {
              const it = rows[c.dataIndex];
              return `${(it.score ?? 0).toFixed(1)} / ${maxOf(it)}`;
            },
          },
          z: 2,
        },
      ],
    }),
    [rows.map((r) => `${r.category}:${r.score}:${r.level}`).join('|'), disclosed],
  );

  return (
    <ChartFrame
      title="항목별 점수와 배점"
      hint="막대 전체 길이가 배점입니다. 배점이 큰 항목일수록 총점을 많이 움직입니다."
      height={Math.max(180, rows.length * 46 + 40)}
      table={{
        columns: ['항목', '점수', '배점', '달성률', '등급'],
        rows: rows.map((r) => {
          const max = maxOf(r);
          return [
            CATEGORY_LABEL[r.category],
            disclosed && r.score !== null ? r.score.toFixed(1) : '—',
            max,
            disclosed && r.score !== null ? `${((r.score / max) * 100).toFixed(0)}%` : '—',
            RISK_LABEL[r.level],
          ];
        }),
      }}
    >
      <div ref={box} style={{ width: '100%', height: '100%' }} />
    </ChartFrame>
  );
}
