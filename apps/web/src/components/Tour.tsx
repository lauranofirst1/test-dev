/** 화면 위에서 실제 요소를 짚어 가며 설명하는 안내.
 *
 * **글로 적어 둔 도움말은 읽지 않습니다.** "부스를 먼저 만드세요" 를 어딘가에
 * 적어 두면 그 문장은 화면에 없는 것이나 마찬가지고, 사람은 눈앞의 버튼을
 * 누릅니다. 그래서 설명을 문서가 아니라 **그 버튼 위에** 둡니다.
 *
 * 구멍이 한 요소에서 다음 요소로 **움직입니다.** 새 카드가 툭툭 나타나면 방금
 * 무엇을 봤는지 잊지만, 구멍이 이동하면 눈이 따라가면서 "여기 다음은 저기" 가
 * 위치로 남습니다. 순서가 있는 화면을 설명하는 데 이게 핵심입니다.
 *
 * 움직임 줄이기를 켠 사람에게는 이동이 사라집니다 — `--duration-*` 토큰이
 * `tokens.css` 에서 이미 0 으로 접히므로 여기서 따로 분기하지 않습니다.
 *
 * 대상은 `data-tour="키"` 로 표시합니다. 선택자를 화면 구조에 맞추면 마크업을
 * 조금만 고쳐도 안내가 조용히 깨지는데, 그때 아무도 모릅니다.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export interface TourStep {
  /** 짚을 요소의 `data-tour` 값. 없으면 화면 가운데에 카드만 띄운다. */
  target?: string;
  title: string;
  body: React.ReactNode;
}

interface Hole {
  top: number;
  left: number;
  width: number;
  height: number;
  /** 대상의 모서리 반경. 네모난 구멍으로 둥근 버튼을 덮으면 모서리가 삐져나온다. */
  radius: number;
}

function same(a: Hole | null, b: Hole | null): boolean {
  if (a === null || b === null) return a === b;
  return (
    Math.abs(a.top - b.top) < 0.5 &&
    Math.abs(a.left - b.left) < 0.5 &&
    Math.abs(a.width - b.width) < 0.5 &&
    Math.abs(a.height - b.height) < 0.5 &&
    a.radius === b.radius
  );
}

/** 구멍 둘레에 두는 여백. 요소에 딱 맞추면 잘린 것처럼 보인다. */
const PAD = 8;
/** 카드와 구멍 사이. */
const GAP = 12;
const CARD_W = 320;

function rectOf(target: string | undefined): Hole | null {
  if (!target) return null;
  const el = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return null;
  const corner = Number.parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
  return {
    top: r.top - PAD,
    left: r.left - PAD,
    width: r.width + PAD * 2,
    height: r.height + PAD * 2,
    radius: corner + PAD,
  };
}

export function Tour({
  steps,
  onClose,
}: {
  steps: TourStep[];
  onClose: () => void;
}) {
  //: 화면에 실제로 있는 단계만 남긴다. 부스가 없으면 부스 표도 없고, 없는 것을
  //: 짚으면 안내가 빈 화면을 가리킨다.
  //:
  //: **열 때 한 번만 정한다.** 매 렌더마다 다시 걸러내면 도중에 목록 길이가
  //: 바뀔 수 있고, 그러면 «3 / 5» 였던 표시가 갑자기 «3 / 4» 가 되거나 보던
  //: 단계가 통째로 건너뛰어진다.
  const [live] = useState(() => steps.filter((s) => !s.target || rectOf(s.target)));
  const [i, setI] = useState(0);
  const step = live[i];
  const [hole, setHole] = useState<Hole | null>(null);
  const raf = useRef(0);

  // 대상으로 스크롤하고, **안내가 열려 있는 내내** 다시 잰다.
  //
  // 처음에는 스크롤이 끝날 무렵까지만 쟀는데, 부드러운 스크롤이 그보다 오래
  // 걸리는 긴 화면에서는 구멍이 중간 좌표에 멈춰 대상과 어긋났다. 스크롤·리사이즈
  // 이벤트만 듣는 것도 부족하다 — 늦게 온 이미지나 폰트 때문에 레이아웃이
  // 밀리는 것은 어느 이벤트로도 오지 않는다.
  //
  // 값이 실제로 달라졌을 때만 상태를 바꾸므로, 가만히 있을 때는 매 프레임
  // 재기만 하고 다시 그리지는 않는다.
  useLayoutEffect(() => {
    if (!step) return;
    // 이미 보이는 것은 굳이 스크롤하지 않는다.
    //
    // 화면이 움직이는 **동시에** 구멍도 움직이면 두 움직임이 겹쳐서, 구멍이
    // 대상을 뒤쫓는 것처럼 보인다. 대부분의 단계는 대상이 이미 화면 안에 있어
    // 스크롤이 필요 없다 — 그때는 구멍만 미끄러지므로 눈이 따라가기 쉽다.
    const el = step.target
      ? document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`)
      : null;
    if (el) {
      const r = el.getBoundingClientRect();
      const margin = 80; // 상단 바에 가리는 만큼은 보이는 것으로 치지 않는다
      const visible = r.top >= margin && r.bottom <= window.innerHeight - margin;
      if (!visible) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }

    let current: Hole | null = null;
    const tick = () => {
      const next = rectOf(step.target);
      if (!same(current, next)) {
        current = next;
        setHole(next);
      }
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [step]);

  const next = useCallback(() => {
    setI((n) => (n + 1 < live.length ? n + 1 : n));
  }, [live.length]);
  const prev = useCallback(() => setI((n) => Math.max(0, n - 1)), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight') next();
      if (e.key === 'ArrowLeft') prev();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [next, prev, onClose]);

  if (!step) return null;

  const last = i === live.length - 1;

  // 카드는 구멍 아래가 기본이고, 아래가 좁으면 위로 올린다. 구멍을 덮으면
  // 무엇을 설명하는지 안 보인다.
  const below = hole ? hole.top + hole.height + GAP : 0;
  const roomBelow = hole ? window.innerHeight - below : 0;
  const putAbove = hole !== null && roomBelow < 200 && hole.top > 220;
  const cardStyle: React.CSSProperties = hole
    ? {
        top: putAbove ? undefined : below,
        bottom: putAbove ? window.innerHeight - hole.top + GAP : undefined,
        left: Math.min(
          Math.max(GAP, hole.left + hole.width / 2 - CARD_W / 2),
          Math.max(GAP, window.innerWidth - CARD_W - GAP),
        ),
      }
    : { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' };

  // ── body 로 내보낸다 ──
  //
  // 이 컴포넌트는 상단 바 안에서 렌더된다. 상단 바는 `position: sticky` 에
  // `z-index` 를 갖고 있어 **쌓임 맥락**을 만들고, 그 안의 `z-index` 는 바깥과
  // 겨루지 못한다. 조상 어딘가에 `transform` 이 생기면 `position: fixed` 의
  // 기준이 화면이 아니라 그 조상이 되어 구멍이 통째로 밀리기도 한다.
  //
  // 어느 쪽도 이 파일을 고쳐서 막을 수 없다 — 남의 화면 CSS 가 바뀌면 그만이다.
  // body 로 내보내면 조상이 무엇이든 상관없어진다.
  return createPortal(
    <div className="tour" role="dialog" aria-modal="true" aria-label="화면 안내">
      {/* 구멍. 바깥을 어둡게 하는 것은 그림자 하나가 다 한다 — 네 조각으로
          나눠 덮으면 이동할 때 조각들이 따로 논다. */}
      {hole && (
        <div
          className="tour__hole"
          style={{
            top: hole.top,
            left: hole.left,
            width: hole.width,
            height: hole.height,
            borderRadius: hole.radius,
          }}
        />
      )}
      {!hole && <div className="tour__veil" />}

      <div className="tour__card" style={cardStyle}>
        <p className="tour__count tabular">
          {i + 1} / {live.length}
        </p>
        <h2 className="tour__title">{step.title}</h2>
        <div className="tour__body">{step.body}</div>
        <div className="tour__acts">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            그만 보기
          </button>
          <span className="tour__spacer" />
          {i > 0 && (
            <button type="button" className="btn btn--ghost" onClick={prev}>
              이전
            </button>
          )}
          <button
            type="button"
            className="btn btn--primary"
            onClick={last ? onClose : next}
          >
            {last ? '알겠습니다' : '다음'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
