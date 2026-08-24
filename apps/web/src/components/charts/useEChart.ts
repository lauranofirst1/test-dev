/** ECharts 인스턴스 공통 배선 — docs/06-charts.md §1, §5, §6.
 *
 * 화면마다 인스턴스를 손으로 만들면 렌더러·팔레트·다크모드·리사이즈 처리가
 * 조금씩 달라지고, 그 차이는 반드시 어긋납니다. 여기 한 곳에 둡니다.
 *
 * **렌더러는 `svg` 로 고정합니다.** 최종 기획서 PDF 에 벡터로 들어가야 하고,
 * canvas 로 그리면 거기서 래스터가 됩니다(§1).
 *
 * **색은 CSS 토큰에서 읽습니다.** 팔레트를 여기에 하드코딩하면 tokens.css 와
 * 두 벌이 되고, 다크 모드 값은 반드시 한쪽만 고쳐집니다. 토큰이 유일한 원본이며
 * 그 값들은 이미 색각·명도·대비 검증을 통과한 것입니다(§2).
 *
 * 다크 모드는 **자동 반전이 아니라 별도 팔레트**라(§6), 테마가 바뀌면 색을 다시
 * 읽어 차트를 새로 그립니다. 명시 토글(`data-theme`)과 OS 설정 둘 다 봅니다.
 */

import * as echarts from 'echarts/core';
import { BarChart, CustomChart, ScatterChart } from 'echarts/charts';
import {
  GraphicComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';
import { useEffect, useRef, useState } from 'react';

echarts.use([
  BarChart,
  CustomChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  MarkLineComponent,
  GraphicComponent,
  SVGRenderer,
]);

/** 차트가 쓰는 토큰 묶음. 이름은 tokens.css 의 것을 그대로 따른다. */
export interface ChartPalette {
  series: string[];
  stateLow: string;
  stateCaution: string;
  stateHigh: string;
  stateNone: string;
  divNeg: string;
  divMid: string;
  divPos: string;
  grid: string;
  axis: string;
  surface: string;
  ink: string;
  inkSoft: string;
  inkMute: string;
  line: string;
  sunk: string;
}

function readPalette(): ChartPalette {
  const s = getComputedStyle(document.documentElement);
  const v = (name: string) => s.getPropertyValue(name).trim();
  return {
    series: [1, 2, 3, 4, 5, 6].map((n) => v(`--chart-series-${n}`)),
    stateLow: v('--color-state-low'),
    stateCaution: v('--color-state-caution'),
    stateHigh: v('--color-state-high'),
    stateNone: v('--color-state-none'),
    divNeg: v('--chart-div-neg'),
    divMid: v('--chart-div-mid'),
    divPos: v('--chart-div-pos'),
    grid: v('--chart-grid'),
    axis: v('--chart-axis'),
    surface: v('--chart-surface'),
    ink: v('--color-ink'),
    inkSoft: v('--color-ink-soft'),
    inkMute: v('--color-ink-mute'),
    line: v('--color-line'),
    sunk: v('--color-surface-sunk'),
  };
}

/** 애니메이션은 `prefers-reduced-motion` 을 존중한다(§6). */
function reducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

/** 테마가 바뀌면 팔레트를 다시 읽는다. 명시 토글과 OS 설정 둘 다 본다. */
export function useChartPalette(): ChartPalette {
  const [palette, setPalette] = useState<ChartPalette>(() =>
    typeof window === 'undefined' ? ({} as ChartPalette) : readPalette(),
  );

  useEffect(() => {
    const reread = () => setPalette(readPalette());
    reread();

    const media = window.matchMedia('(prefers-color-scheme: dark)');
    media.addEventListener('change', reread);
    // 뷰어가 테마를 토글하면 :root 의 data-theme 이 바뀐다.
    const observer = new MutationObserver(reread);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });

    return () => {
      media.removeEventListener('change', reread);
      observer.disconnect();
    };
  }, []);

  return palette;
}

/**
 * 옵션을 주면 차트를 그려 주는 훅. 컨테이너 ref 를 돌려준다.
 *
 * 옵션은 **팔레트를 인자로 받는 함수**로 넘긴다. 그래야 테마가 바뀔 때 색만
 * 다시 계산해 같은 인스턴스에 다시 그릴 수 있다.
 */
export function useEChart(
  build: (palette: ChartPalette) => Record<string, unknown>,
  deps: unknown[],
) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const palette = useChartPalette();

  useEffect(() => {
    if (!box.current) return;
    // 크기는 넘기지 않는다. echarts 가 컨테이너를 재고, 아래 ResizeObserver 가
    // 이후 변화를 따라간다. 'auto' 를 넘기면 SVG 렌더러가 그 문자열을 그대로
    // width 속성에 써서 매 렌더 오류가 난다.
    const instance = echarts.init(box.current, undefined, { renderer: 'svg' });
    chart.current = instance;

    // 컨테이너 크기가 바뀌면 다시 그린다 — 카드 폭이 화면에 따라 달라진다.
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(box.current);

    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chart.current || !palette.surface) return;
    chart.current.setOption(
      { animation: !reducedMotion(), ...build(palette) },
      // 시리즈 수가 바뀔 수 있으므로 병합하지 않고 갈아끼운다.
      { notMerge: true },
    );
    // build 는 매 렌더 새 함수라 deps 에 넣지 않는다. 호출부가 실제 의존성을 준다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [palette, ...deps]);

  return box;
}

export { echarts };
