/** 차트를 지연 로드한다.
 *
 * ECharts 는 트리셰이킹해도 무겁습니다. 한 번들에 넣으면 **관객 화면도 함께
 * 내려받습니다** — 축제장 통신이 느리다는 것이 이 제품의 기본 전제이고
 * (tokens.css 의 한글 웹폰트 결정도 같은 이유), 관객 화면은 차트를 하나도
 * 쓰지 않습니다.
 *
 * 차트는 기획자가 노트북에서 보는 진단 화면에만 있으므로, 그 화면에 들어갈 때만
 * 받습니다.
 */

import { Suspense, lazy } from 'react';

const Bullet = lazy(() =>
  import('./ScoreBullet').then((m) => ({ default: m.ScoreBullet })),
);
const Gap = lazy(() => import('./ScoreGap').then((m) => ({ default: m.ScoreGap })));
const Dumbbell = lazy(() =>
  import('./DeltaDumbbell').then((m) => ({ default: m.DeltaDumbbell })),
);

/** 로드되는 동안 자리를 잡아 둔다. 비워 두면 차트가 뜰 때 화면이 튄다. */
function Placeholder({ height }: { height: number }) {
  return <div className="skeleton" style={{ height }} />;
}

type Props<T> = T & { fallbackHeight?: number };

export function LazyScoreBullet(props: Props<React.ComponentProps<typeof Bullet>>) {
  const { fallbackHeight = 280, ...rest } = props;
  return (
    <Suspense fallback={<Placeholder height={fallbackHeight} />}>
      <Bullet {...rest} />
    </Suspense>
  );
}

export function LazyScoreGap(props: Props<React.ComponentProps<typeof Gap>>) {
  const { fallbackHeight = 260, ...rest } = props;
  return (
    <Suspense fallback={<Placeholder height={fallbackHeight} />}>
      <Gap {...rest} />
    </Suspense>
  );
}

export function LazyDeltaDumbbell(props: Props<React.ComponentProps<typeof Dumbbell>>) {
  const { fallbackHeight = 260, ...rest } = props;
  return (
    <Suspense fallback={<Placeholder height={fallbackHeight} />}>
      <Dumbbell {...rest} />
    </Suspense>
  );
}
