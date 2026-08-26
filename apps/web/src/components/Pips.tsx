/** 조각 격자 — 진행을 막대가 아니라 **칸**으로 센다.
 *
 * 이 제품의 심장은 부스를 돌면 그림이 한 조각씩 열리는 조각 보드입니다.
 * 그래서 진행 표시도 같은 문법을 씁니다. 장식이 아니라 정보의 차이입니다 —
 * **진행바는 비율만 말하고, 조각 격자는 개수를 말합니다.**
 *
 * 이 제품에서 개수는 실제로 의미가 있습니다. "부스 18/20 준비됨" 에서 안 찬
 * 두 칸이 눈에 보이는 것과 90% 막대를 보는 것은 다른 정보입니다. 부스 수가
 * 곧 조각 수이고, 조각이 다 안 차면 아무도 보드를 완성하지 못합니다.
 *
 * ## 숫자를 항상 함께 낸다
 *
 * 칸이 정보를 나르므로 **색과 모양만으로 뜻이 실리면 안 됩니다.** `count`
 * 를 끄지 않는 한 `18 / 20` 이 옆에 붙고, 스크린리더에는 칸 대신 문장이
 * 갑니다. 칸은 `aria-hidden` 입니다 — 스물 개의 빈 span 을 하나씩 읽어 주는
 * 것은 도움이 아니라 방해입니다.
 *
 * ## 많으면 접는다
 *
 * 칸이 너무 많으면 세는 행위 자체가 불가능해집니다. `max` 를 넘으면 칸을
 * 그리지 않고 숫자와 얇은 막대로 떨어집니다 — 이때는 개수보다 비율이 읽을 수
 * 있는 유일한 정보이기 때문입니다.
 */

const DEFAULT_MAX = 40;

export type PipTone = 'act' | 'done' | 'caution' | 'risk';

export function Pips({
  filled,
  total,
  tone = 'act',
  count = true,
  max = DEFAULT_MAX,
  label,
}: {
  /** 찬 칸 수. */
  filled: number;
  /** 전체 칸 수. */
  total: number;
  /** 찬 칸의 뜻. `done` 은 금색 — 이미 이룬 것에만 씁니다. */
  tone?: PipTone;
  /** 옆에 `18 / 20` 을 붙일지. 끄는 경우 반드시 `label` 로 뜻을 주세요. */
  count?: boolean;
  /** 이 수를 넘으면 칸 대신 막대로 떨어집니다. */
  max?: number;
  /** 스크린리더가 읽을 문장. 없으면 "20칸 중 18칸" 으로 나갑니다. */
  label?: string;
}) {
  const safeTotal = Math.max(0, Math.floor(total));
  const safeFilled = Math.min(Math.max(0, Math.floor(filled)), safeTotal);
  const text = label ?? `${safeTotal}칸 중 ${safeFilled}칸`;
  const ratio = safeTotal === 0 ? 0 : safeFilled / safeTotal;

  return (
    <span className="pipline">
      {safeTotal > max || safeTotal === 0 ? (
        // 셀 수 없는 개수다. 이때는 비율만이 읽을 수 있는 정보다.
        <span className="pipbar" aria-hidden>
          <i data-tone={tone} style={{ width: `${ratio * 100}%` }} />
        </span>
      ) : (
        <span className="pips" aria-hidden>
          {Array.from({ length: safeTotal }, (_, i) => (
            <i key={i} data-on={i < safeFilled || undefined} data-tone={tone} />
          ))}
        </span>
      )}
      {count && (
        <b className="pipline__n tabular">
          {safeFilled} / {safeTotal}
        </b>
      )}
      <span className="sr-only">{text}</span>
    </span>
  );
}
