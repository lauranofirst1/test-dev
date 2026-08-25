/** 시간대별 참여 — 당일 화면의 선 그래프.
 *
 * ## 왜 선인가
 *
 * 스탯 카드는 "지금 얼마" 를 답하고 부스 표는 "어디가" 를 답합니다. 둘 다
 * **언제부터** 를 답하지 못합니다. "최근 30분 96건" 이 오르는 중인지 식는
 * 중인지에 따라 운영자가 할 일이 정반대입니다 — 인력을 더 보낼지, 철수를
 * 준비할지.
 *
 * ## 서버가 0 을 채워 보낸다
 *
 * 빈 칸을 화면이 메우게 두면 화면마다 다르게 메우고, 그중 하나는 반드시 없던
 * 시간을 완만한 하강으로 그립니다. `operations/timeline` 이 빈 10분 칸도
 * `completions: 0` 으로 내려주므로 여기서는 그대로 잇기만 합니다.
 *
 * ## 눈금은 정직하게
 *
 * y축은 **항상 0 에서 시작합니다.** 최솟값에서 자르면 3→4 가 두 배로 보입니다.
 * 참여 건수는 비율이 아니라 개수라 0 이 실제 바닥입니다.
 */

import { useId } from "react";

export interface ChartPoint {
  /** 칸의 시작 시각(ISO). 화면이 자기 시간대로 찍는다. */
  at: string;
  completions: number;
}

const H = 132;
const PAD_TOP = 10;
const PAD_BOTTOM = 22;

function hhmm(iso: string) {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function ParticipationChart({
  points,
  peak,
  caption,
  emptyNote = "아직 그릴 만큼 시간이 지나지 않았습니다.",
  unit = "건",
}: {
  points: ChartPoint[];
  /** 가장 높은 칸. 서버가 함께 내주면 화면이 다시 훑지 않는다. */
  peak: number;
  /** 그래프 아래 한 줄. 무엇을 어떤 간격으로 보고 있는지. */
  caption: string;
  emptyNote?: string;
  unit?: string;
}) {
  const gradient = useId();

  if (points.length < 2) {
    return <p className="muted">{emptyNote}</p>;
  }

  // 전부 0 이어도 선은 그린다 — 바닥에 붙은 선이 "아무도 안 왔다" 는 사실이다.
  // 여기서 그래프를 감추면 그 사실이 사라진다.
  const top = Math.max(peak, 1);
  const inner = H - PAD_TOP - PAD_BOTTOM;
  const stepX = 100 / (points.length - 1);

  const xy = points.map((p, i) => {
    const x = i * stepX;
    const y = PAD_TOP + inner * (1 - p.completions / top);
    return { x, y, p };
  });

  const line = xy
    .map(
      ({ x, y }, i) => `${i === 0 ? "M" : "L"}${x.toFixed(3)},${y.toFixed(2)}`,
    )
    .join(" ");
  const area = `${line} L100,${PAD_TOP + inner} L0,${PAD_TOP + inner} Z`;

  const last = xy[xy.length - 1];
  const total = points.reduce((n, p) => n + p.completions, 0);

  // 눈금은 양 끝과 가운데만. 10분 칸 서른여섯 개에 전부 이름을 달면 글자가 겹쳐
  // 하나도 안 읽힌다.
  const ticks = [xy[0], xy[Math.floor(xy.length / 2)], last];

  return (
    <figure className="tchart">
      <figcaption className="sr-only">
        {caption}. 합계 {total}
        {unit}, 최다 {peak}
        {unit}.
      </figcaption>

      {/* 끝점의 기준 상자. 이게 없으면 `top: %` 가 figure 전체(눈금·범례 포함)를
          기준으로 잡혀 점이 그래프 밖에 뜬다. */}
      <div className="tchart__plot">
        <svg
          className="tchart__svg"
          viewBox={`0 0 100 ${H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`${caption}. 합계 ${total}${unit}, 최다 ${peak}${unit}.`}
        >
          <defs>
            <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor="var(--color-act-solid)"
                stopOpacity="0.22"
              />
              <stop
                offset="100%"
                stopColor="var(--color-act-solid)"
                stopOpacity="0"
              />
            </linearGradient>
          </defs>

          {/* 바닥선. y축이 0 에서 시작한다는 것을 눈으로 보이게 한다. */}
          <line
            x1="0"
            x2="100"
            y1={PAD_TOP + inner}
            y2={PAD_TOP + inner}
            className="tchart__axis"
            vectorEffect="non-scaling-stroke"
          />
          <path d={area} fill={`url(#${gradient})`} />
          <path
            d={line}
            className="tchart__line"
            fill="none"
            vectorEffect="non-scaling-stroke"
          />
        </svg>

        {/* 끝점은 **SVG 밖에서** 찍는다. 서른여섯 개를 다 찍으면 선이 점에 묻히고,
          그렇다고 SVG 안에 원을 두면 `preserveAspectRatio="none"` 의 가로
          10배 확대에 눌려 원이 30×4px 짜리 막대가 된다. 선은
          `vector-effect` 로 두께를 지킬 수 있지만 원은 그럴 수 없다. */}
        <span
          className="tchart__dot"
          aria-hidden
          style={{ top: `${(last.y / H) * 100}%` }}
        />
      </div>

      <div className="tchart__ticks">
        {ticks.map((t, i) => (
          <span key={i} className="tabular">
            {hhmm(t.p.at)}
          </span>
        ))}
      </div>

      <p className="tchart__legend muted">
        {caption} · 최다{" "}
        <b className="tabular">
          {peak}
          {unit}
        </b>{" "}
        · 합계{" "}
        <b className="tabular">
          {total}
          {unit}
        </b>
      </p>
    </figure>
  );
}
