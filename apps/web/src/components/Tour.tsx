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
  return {
    top: r.top - PAD,
    left: r.left - PAD,
    width: r.width + PAD * 2,
    height: r.height + PAD * 2,
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

  const measure = useCallback(() => {
    setHole(rectOf(step?.target));
  }, [step?.target]);

  // 대상으로 스크롤한 뒤, 스크롤이 멎을 때까지 계속 다시 잰다. 한 번만 재면
  // 부드러운 스크롤이 끝나기 전의 좌표에 구멍이 남는다.
  useLayoutEffect(() => {
    if (!step) return;
    const el = step.target
      ? document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`)
      : null;
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });

    const until = Date.now() + 800;
    const tick = () => {
      measure();
      if (Date.now() < until) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [step, measure]);

  useEffect(() => {
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [measure]);

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

  return (
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
    </div>
  );
}
