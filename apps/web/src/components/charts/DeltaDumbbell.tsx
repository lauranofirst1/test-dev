/** 직전 진단 대비 — 덤벨 차트. docs/06-charts.md §3.2, §3.3.
 *
 * before·after 를 나란한 막대 두 개로 그리면 "증가했다"가 아니라 "두 개가 있다"로
 * 읽힙니다. 덤벨은 변화의 **방향과 크기를 하나의 획**으로 보여줍니다.
 *
 * 색은 발산 팔레트를 씁니다(§2.4). 스펙이 "파랑=좋음으로 고정하지 말고 축 라벨로
 * 명시"하라고 하므로, **이 차트의 축 방향을 여기서 못박습니다 — 진단 점수는
 * 오르는 것이 좋습니다.** 그래서 상승이 파랑, 하락이 빨강입니다.
 *
 * 토큰 이름(`--chart-div-pos` = 빨강)과 반대로 붙는 것이 헷갈릴 수 있는데,
 * 토큰은 축의 양끝 색을 담을 뿐 어느 쪽이 좋은지는 지표마다 다릅니다.
 *
 * 이 페이지에서 **빨강은 이미 "위험 등급"입니다.** 위쪽 두 차트가 그렇게 쓰고,
 * 총점 옆 증감 배지(`.delta--up/down`)도 상승을 파랑으로 씁니다. 여기서만
 * 상승을 빨강으로 두면 같은 화면의 같은 색이 정반대를 뜻하게 됩니다.
 *
 * 변화가 없는 항목도 지우지 않고 그대로 둡니다. 사라지면 "그 항목은 진단하지
 * 않았나"로 읽히고, 5개 항목이 매번 다 있다는 사실이 이 화면의 약속입니다.
 *
 * 다만 **전부 변화가 없으면 차트를 그리지 않습니다.** 아령이 하나도 없는 아령
 * 차트는 점이 흩어진 그림일 뿐이라 읽을 것이 없습니다. 표본이 부족할 때 선을
 * 긋지 않는 것과 같은 이유입니다(§3.2) — 그릴 게 없는데 그리면 그 그림이
 * 근거처럼 보입니다.
 */

import type { DiagnosisComparison } from '../../api/types';
import { CATEGORY_LABEL } from '../../api/types';
import { ChartFrame } from './ChartFrame';
import { useEChart } from './useEChart';

export function DeltaDumbbell({ c }: { c: DiagnosisComparison }) {
  const rows = c.items.filter((i) => i.previous !== null && i.current !== null);
  const moved = rows.filter((r) => Math.abs(r.delta ?? 0) >= 0.05);

  const axisMax = Math.max(...rows.map((r) => Math.max(r.previous!, r.current!)), 1);

  const box = useEChart(
    (p) => {
      // 진단 점수는 오르는 것이 좋다. 그래서 상승이 파랑(divNeg 슬롯), 하락이
      // 빨강(divPos 슬롯)이다 — 토큰 이름이 아니라 이 지표의 방향을 따른다.
      const colorOf = (delta: number) =>
        delta > 0 ? p.divNeg : delta < 0 ? p.divPos : p.divMid;

      return {
        grid: { left: 118, right: 92, top: 8, bottom: 26 },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          backgroundColor: p.surface,
          borderColor: p.line,
          textStyle: { color: p.ink, fontSize: 13 },
          formatter: (params: { dataIndex: number }[]) => {
            const r = rows[params[0].dataIndex];
            const delta = (r.delta ?? 0).toFixed(1);
            const sign = (r.delta ?? 0) > 0 ? '+' : '';
            return `<b>${CATEGORY_LABEL[r.category]}</b><br/>${r.previous!.toFixed(
              1,
            )} → ${r.current!.toFixed(1)}점<br/>${sign}${delta}점`;
          },
        },
        xAxis: {
          type: 'value',
          min: 0,
          max: Math.ceil(axisMax / 5) * 5,
          splitLine: { lineStyle: { color: p.grid, type: 'solid' } },
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
            // 두 점을 잇는 획. 이것이 변화 그 자체다.
            type: 'custom',
            silent: true,
            renderItem: (
              params: { dataIndex: number },
              api: {
                value: (i: number) => number;
                coord: (v: number[]) => number[];
                size: (v: number[]) => number[];
              },
            ) => {
              const row = rows[params.dataIndex];
              const from = api.coord([api.value(1), params.dataIndex]);
              const to = api.coord([api.value(2), params.dataIndex]);
              return {
                type: 'line',
                shape: { x1: from[0], y1: from[1], x2: to[0], y2: to[1] },
                style: {
                  stroke: colorOf(row.delta ?? 0),
                  lineWidth: 4,
                  lineCap: 'round',
                },
              };
            },
            encode: { x: [1, 2], y: 0 },
            data: rows.map((r, i) => [i, r.previous, r.current]),
            z: 1,
          },
          {
            // 직전 — 표면색 링을 둘러 겹쳐도 구분된다(§4). 변화가 없는 행은
            // 두 점이 정확히 포개져 "빈 점 위에 찬 점"이 지저분해지므로 뺀다.
            type: 'scatter',
            symbolSize: 12,
            itemStyle: { color: p.surface, borderColor: p.inkMute, borderWidth: 2 },
            data: rows
              .map((r, i) => ({ r, i }))
              .filter(({ r }) => Math.abs(r.delta ?? 0) >= 0.05)
              .map(({ r, i }) => [r.previous, i]),
            z: 2,
          },
          {
            // 현재 — 변화 방향의 색을 채운다.
            type: 'scatter',
            symbolSize: 16,
            itemStyle: {
              color: (ctx: { dataIndex: number }) => colorOf(rows[ctx.dataIndex].delta ?? 0),
              borderColor: p.surface,
              borderWidth: 2,
            },
            data: rows.map((r, i) => [r.current, i]),
            label: {
              show: true,
              position: 'right',
              distance: 12,
              color: p.inkSoft,
              fontSize: 12,
              fontWeight: 'bold',
              // 끝점 라벨만 붙인다(§4). 값이 없으면 호버해야만 읽을 수 있어
              // 인쇄와 스크린샷에서 차트가 무의미해진다.
              formatter: (ctx: { dataIndex: number }) => {
                const r = rows[ctx.dataIndex];
                const delta = r.delta ?? 0;
                const now = (r.current ?? 0).toFixed(1);
                if (Math.abs(delta) < 0.05) return now;
                return `${now}  ${delta > 0 ? '▲' : '▼'}${Math.abs(delta).toFixed(1)}`;
              },
            },
            z: 3,
          },
        ],
      };
    },
    [rows.map((r) => `${r.category}:${r.previous}:${r.current}`).join('|')],
  );

  if (rows.length === 0) return null;

  if (moved.length === 0) {
    return (
      <div className="notice notice--info">
        <span>ⓘ</span>
        <span>
          다섯 항목 모두 직전 진단과 같습니다. 기획을 고치거나 부스를 등록한 뒤 다시
          진단하면 무엇이 달라졌는지 여기에 표시됩니다.
        </span>
      </div>
    );
  }

  return (
    <ChartFrame
      title="직전 진단 대비"
      hint="빈 점이 직전, 채운 점이 이번입니다. 오른쪽으로 움직였으면 점수가 오른 것이고, 오른 항목은 파랑·내린 항목은 빨강입니다."
      height={Math.max(170, rows.length * 42 + 40)}
      table={{
        columns: ['항목', '직전', '이번', '변화'],
        rows: rows.map((r) => [
          CATEGORY_LABEL[r.category],
          r.previous!.toFixed(1),
          r.current!.toFixed(1),
          `${(r.delta ?? 0) > 0 ? '+' : ''}${(r.delta ?? 0).toFixed(1)}`,
        ]),
      }}
    >
      <div ref={box} style={{ width: '100%', height: '100%' }} />
    </ChartFrame>
  );
}
