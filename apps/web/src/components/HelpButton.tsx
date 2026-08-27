/** 오른쪽 아래에 떠 있는 도움말.
 *
 * 누르면 **작은 패널이 스르륵 올라옵니다.** 곧장 안내를 시작하지 않는 이유는,
 * 뭘 하려고 들어온 사람 앞을 전체 화면 안내가 가로막으면 그건 안내가 아니라
 * 방해이기 때문입니다. 패널은 구석에 뜨고, 시작할지는 본인이 정합니다.
 *
 * 패널에는 **이 화면이 무엇인지**와 **안내가 무엇을 짚는지**가 먼저 있습니다.
 * 그것만 읽고 닫는 경우가 실제로 많고, 그때도 답을 얻은 것입니다.
 *
 * 안내가 없는 화면에서는 단추 자체가 나오지 않습니다. 눌러서 "준비 중입니다" 를
 * 보는 것은 없느니만 못합니다.
 */

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation } from 'react-router-dom';

import { Tour } from './Tour';
import type { TourStep } from './Tour';
import { TOURS, type TourId } from '../lib/tours';

/** 주소에서 이 화면의 안내를 고른다. 끝 조각만 본다. */
function tourFor(pathname: string): TourId | null {
  if (pathname === '/') return 'workspace';
  if (/\/festivals\/\d+\/booths$/.test(pathname)) return 'booths';
  if (/\/festivals\/\d+\/diagnosis$/.test(pathname)) return 'diagnosis';
  if (/\/festivals\/\d+\/dashboard$/.test(pathname)) return 'dashboard';
  if (/\/festivals\/\d+\/report$/.test(pathname)) return 'report';
  if (/\/festivals\/\d+\/lectures$/.test(pathname)) return 'lectures';
  if (/\/festivals\/\d+\/exhibits$/.test(pathname)) return 'exhibits';
  if (/\/festivals\/\d+\/staff$/.test(pathname)) return 'staff';
  if (/\/festivals\/\d+$/.test(pathname)) return 'overview';
  return null;
}

const seenKey = (id: TourId) => `festaflow-tour-${id}`;

function markSeen(id: TourId): void {
  try {
    localStorage.setItem(seenKey(id), '1');
  } catch {
    /* 사파리 프라이빗 모드처럼 저장이 막힌 환경에서도 도움말 자체는 돌아야 한다 */
  }
}

function wasSeen(id: TourId): boolean {
  try {
    return localStorage.getItem(seenKey(id)) === '1';
  } catch {
    // 저장을 못 읽으면 **본 것으로 친다.** 갈 때마다 다시 펼치면 그게 더 방해다.
    return true;
  }
}

export function HelpButton() {
  const { pathname } = useLocation();
  const id = tourFor(pathname);
  const [panel, setPanel] = useState(false);
  //: 돌고 있는 안내. **화면이 바뀌어도 살아 있어야 한다** — 안내가 스스로 다음
  //: 화면으로 데려가는데 그때 죽으면 한 걸음도 못 넘어간다. 그래서 «지금 화면의
  //: 안내» 가 아니라 «시작할 때 집은 안내» 를 그대로 들고 간다.
  const [tour, setTour] = useState<{ id: TourId; steps: TourStep[] } | null>(null);
  const wrap = useRef<HTMLDivElement>(null);

  // 화면이 바뀌면 패널을 닫는다. 처음 오는 화면에서는 스스로 열린다 — 구석에
  // 뜨는 작은 것이라 하던 일을 막지 않는다.
  //
  // 안내가 도는 중에는 아무것도 하지 않는다. 안내가 데려간 화면에서 패널이
  // 튀어나오면 안내를 가린다.
  useEffect(() => {
    if (tour) return;
    setPanel(id !== null && !wasSeen(id));
    // 안내가 도는 동안에는 이 효과를 건너뛰므로 tour 를 의존성에 넣지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // 바깥을 누르거나 Esc 로 닫는다. 열어 둔 채로 다른 일을 하려는 사람을
  // 붙잡지 않는다.
  useEffect(() => {
    if (!panel) return;
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setPanel(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPanel(false);
    };
    document.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [panel]);

  // 안내가 도는 중에는 그 안내를 그린다. 화면이 바뀌어 이 화면에 안내가 없어도
  // 마찬가지다 — 데려간 화면이 마침 안내가 없는 곳일 수 있다.
  if (!id && !tour) return null;

  /** 경로의 `{id}` 를 지금 보고 있는 축제 번호로 채운다. */
  const withFestival = (steps: TourStep[]): TourStep[] => {
    const fid = pathname.match(/\/festivals\/(\d+)/)?.[1];
    return steps.map((s) =>
      s.to && fid ? { ...s, to: s.to.replace('{id}', fid) } : { ...s, to: s.to },
    );
  };

  const help = id ? TOURS[id] : null;
  //: «전체 둘러보기» 는 화면을 옮겨 다니므로 축제 번호가 있어야 한다.
  const festivalId = pathname.match(/\/festivals\/(\d+)/)?.[1] ?? null;

  /** 고른 안내를 시작한다. 전체 둘러보기와 이 화면 안내가 같은 길로 온다. */
  const start = (which: TourId) => {
    setPanel(false);
    setTour({ id: which, steps: withFestival(TOURS[which].steps) });
  };

  const closeTour = () => {
    if (tour) markSeen(tour.id);
    setTour(null);
  };

  return createPortal(
    <>
      {!tour && help && id && (
        <div className="helpdock" ref={wrap}>
          {panel && (
            <div className="helppanel" role="dialog" aria-label="도움말">
              <p className="helppanel__eyebrow">도움말</p>
              <h2 className="helppanel__title">{help.label}</h2>
              <p className="helppanel__summary">{help.summary}</p>

              {/* ── 두 갈래로 나눈다 ──
                  «처음이라 전체가 궁금한 사람» 과 «이 화면에서 막힌 사람» 은
                  다른 것을 찾는다. 하나로 묶으면 앞사람은 이 화면 얘기만 듣고
                  전체를 못 보고, 뒷사람은 관심 없는 다른 화면까지 끌려간다. */}
              <div className="helppanel__opts">
                {/* 축제 밖(워크스페이스)에서는 데려갈 축제가 없다. */}
                {festivalId && (
                  <button type="button" className="helpopt" onClick={() => start('overview')}>
                    <span className="helpopt__name">
                      전체 둘러보기
                      <b className="tabular">{TOURS.overview.steps.length}단계</b>
                    </span>
                    <span className="helpopt__note">
                      준비 순서를 화면을 옮겨 가며 한 바퀴 돕니다. 처음이라면 여기부터.
                    </span>
                  </button>
                )}

                {/* 지금 화면이 곧 전체 안내인 자리에서는 같은 것을 두 번 내밀지 않는다. */}
                {id !== 'overview' && (
                  <button type="button" className="helpopt" onClick={() => start(id)}>
                    <span className="helpopt__name">
                      이 화면 안내
                      <b className="tabular">{help.steps.length}단계</b>
                    </span>
                    <span className="helpopt__note">
                      «{help.label}» 화면의 구성 요소를 하나씩 짚습니다.
                    </span>
                  </button>
                )}
              </div>
            </div>
          )}

          <button
            type="button"
            className="helpfab"
            onClick={() => {
              setPanel((v) => !v);
              if (!panel) markSeen(id);
            }}
            aria-expanded={panel}
            aria-label={`${help.label} 도움말`}
            title={`${help.label} 도움말`}
          >
            {panel ? '✕' : '?'}
          </button>
        </div>
      )}

      {tour && <Tour steps={tour.steps} onClose={closeTour} />}
    </>,
    document.body,
  );
}
