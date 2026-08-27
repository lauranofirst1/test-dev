/** 스탬프 랠리 지도 — 진행 보드의 `trail` 표현.
 *
 * 격자 퍼즐(`grid`)과 **같은 타일, 같은 공개 기록**을 다르게 그릴 뿐입니다.
 * 은유가 다릅니다 — 퍼즐은 "그림이 완성된다", 지도는 "길을 따라간다".
 * 부스를 순회하는 축제에서는 뒤쪽이 실제 동선과 닮았습니다.
 *
 * 경로는 **결정적으로** 만듭니다. 매 렌더마다 좌표가 흔들리면 10초 폴링 때문에
 * 화면이 계속 출렁이고, 참여자는 "내가 어디까지 왔는지"를 위치로 기억할 수 없습니다.
 * 그래서 난수 대신 인덱스에서 좌표를 계산합니다.
 *
 * 이음선만 SVG 입니다. 컨테이너가 정사각이 아니라(폭 100%, 높이는 줄 수 비례)
 * 대각선 각도를 CSS 의 % 로 계산하면 화면 비율에 따라 선이 노드를 빗나갑니다.
 * `viewBox="0 0 100 100"` + `preserveAspectRatio="none"` 이면 % 좌표가 그대로
 * 맞아떨어지고, `vector-effect="non-scaling-stroke"` 가 선 굵기만 원래대로 지킵니다.
 * 노드는 글자를 담아야 해서 평범한 span 으로 둡니다.
 */

import type { BoardTile } from '../api/types';

/** 한 줄에 놓는 노드 수. 줄이 바뀔 때마다 진행 방향이 뒤집혀 뱀처럼 이어진다. */
const PER_ROW = 3;

interface Point {
  /** 컨테이너 폭 대비 % */
  x: number;
  /** 컨테이너 높이 대비 % */
  y: number;
}

/** 인덱스 → 좌표. 뱀 모양(boustrophedon)이라 줄 끝과 다음 줄 시작이 붙는다. */
function positionOf(index: number, total: number): Point {
  const rows = Math.ceil(total / PER_ROW);
  const row = Math.floor(index / PER_ROW);
  const col = index % PER_ROW;
  // 홀수 줄은 오른쪽에서 왼쪽으로. 이래야 줄이 바뀔 때 선이 가로지르지 않는다.
  const dir = row % 2 === 0 ? col : PER_ROW - 1 - col;

  const xGap = 100 / (PER_ROW + 1);
  const yGap = 100 / (rows + 1);
  // 짝수/홀수 줄에 약간의 어긋남을 준다 — 자로 잰 격자처럼 보이면 '길'로 안
  // 읽힌다. 폭을 460px 로 묶은 뒤에는 3% 도 과해서 절반으로 줄였다.
  const wobble = row % 2 === 0 ? 1.5 : -1.5;

  return { x: xGap * (dir + 1) + wobble, y: yGap * (row + 1) };
}

/** 후보를 고르는 화면에 쓰는 작은 지도.
 *
 * **격자를 보여주고 지도를 내주면 고른 것과 나온 것이 다릅니다.** 지도 표현을
 * 골랐는데 미리보기가 그림 격자면, 운영자는 화면에 나오지도 않을 배치를 보고
 * 조각 수를 정하게 됩니다. 그래서 좌표 계산을 실제 보드와 **같은 함수**로
 * 합니다 — 여기서 따로 그리면 언젠가 어긋납니다.
 */
export function TrailPreview({ total }: { total: number }) {
  const points = Array.from({ length: total }, (_, i) => positionOf(i, total));
  const rows = Math.ceil(total / PER_ROW);

  return (
    <span className="trailprev" style={{ aspectRatio: `${PER_ROW} / ${rows}` }} aria-hidden="true">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none">
        {points.slice(0, -1).map((from, i) => (
          <line
            key={i}
            x1={from.x}
            y1={from.y}
            x2={points[i + 1].x}
            y2={points[i + 1].y}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
      {points.map((pt, i) => (
        <i key={i} style={{ left: `${pt.x}%`, top: `${pt.y}%` }} />
      ))}
    </span>
  );
}

export function TrailBoard({
  tiles,
  revealedCount,
  totalTiles,
}: {
  tiles: BoardTile[];
  revealedCount: number;
  totalTiles: number;
}) {
  const ordered = [...tiles].sort((a, b) => a.tile_index - b.tile_index);
  const rows = Math.ceil(totalTiles / PER_ROW);
  const points = ordered.map((_, i) => positionOf(i, totalTiles));

  return (
    <div
      className="trail"
      // 줄 수에 따라 높이를 늘린다. 고정하면 조각이 많은 축제에서 노드가 겹친다.
      style={{ height: `${Math.max(180, rows * 84)}px` }}
      role="img"
      aria-label={`축제 스탬프 지도, ${totalTiles}곳 중 ${revealedCount}곳 방문`}
    >
      {/* 이음선을 먼저 깔아 노드 아래에 둔다. */}
      <svg
        className="trail__links"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {points.slice(0, -1).map((from, i) => (
          <line
            key={`link-${i}`}
            className={`trail__link${ordered[i + 1].is_revealed ? ' trail__link--on' : ''}`}
            x1={from.x}
            y1={from.y}
            x2={points[i + 1].x}
            y2={points[i + 1].y}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>

      {ordered.map((t, i) => (
        <span
          key={t.tile_index}
          className={`trail__node${t.is_revealed ? ' trail__node--on' : ''}`}
          style={{ left: `${points[i].x}%`, top: `${points[i].y}%` }}
        >
          {/* 방문한 곳은 도장, 아직인 곳은 번호. 색만으로 구분하지 않는다 —
              야외 직사광선에서 색은 가장 먼저 사라지는 단서다. */}
          <span aria-hidden="true">{t.is_revealed ? '✓' : i + 1}</span>
        </span>
      ))}
    </div>
  );
}
