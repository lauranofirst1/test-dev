/** 지금 보고 있는 화면의 안내를 켜는 단추.
 *
 * 화면마다 다른 안내를 띄웁니다. 한 곳에 모아 둔 도움말 페이지로 보내면, 거기서
 * 자기 화면을 다시 찾아야 하고 대부분 그 지점에서 그만둡니다.
 *
 * 안내가 없는 화면에서는 **단추 자체가 나오지 않습니다.** 눌러서 "준비 중입니다"
 * 를 보는 것은 없느니만 못합니다.
 */

import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { Tour } from './Tour';
import { TOURS, type TourId } from '../lib/tours';

/** 주소에서 이 화면의 안내를 고른다. 끝 조각만 본다. */
function tourFor(pathname: string): TourId | null {
  if (/\/festivals\/\d+\/booths$/.test(pathname)) return 'booths';
  if (/\/festivals\/\d+\/diagnosis$/.test(pathname)) return 'diagnosis';
  if (/\/festivals\/\d+\/dashboard$/.test(pathname)) return 'dashboard';
  if (/\/festivals\/\d+$/.test(pathname)) return 'overview';
  return null;
}

const seenKey = (id: TourId) => `festaflow-tour-${id}`;

function markSeen(id: TourId): void {
  try {
    localStorage.setItem(seenKey(id), '1');
  } catch {
    /* 사파리 프라이빗 모드처럼 저장이 막힌 환경에서도 안내 자체는 돌아야 한다 */
  }
}

function wasSeen(id: TourId): boolean {
  try {
    return localStorage.getItem(seenKey(id)) === '1';
  } catch {
    // 저장을 못 읽으면 **본 것으로 친다.** 매번 다시 권하면 그게 더 방해다.
    return true;
  }
}

export function HelpButton() {
  const { pathname } = useLocation();
  const id = tourFor(pathname);
  const [open, setOpen] = useState(false);
  //: 처음 온 화면인가. 자동으로 켜지 않고 **권하기만** 한다 — 뭘 하려고 들어온
  //: 사람 앞을 안내가 가로막으면 안내가 아니라 방해다.
  const [offer, setOffer] = useState(false);

  useEffect(() => {
    setOpen(false);
    setOffer(id !== null && !wasSeen(id));
  }, [id]);

  if (!id) return null;

  const close = () => {
    setOpen(false);
    setOffer(false);
    markSeen(id);
  };

  return (
    <>
      <button
        type="button"
        className="iconbtn"
        onClick={() => {
          setOffer(false);
          setOpen(true);
        }}
        aria-label={`${TOURS[id].label} 안내 보기`}
        title={`${TOURS[id].label} 안내`}
      >
        ?
      </button>

      {offer && !open && (
        <div className="helpoffer" role="status">
          <span>처음이신가요? {TOURS[id].label}을 짚어 드립니다.</span>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => {
              setOffer(false);
              setOpen(true);
            }}
          >
            안내 보기
          </button>
          <button
            type="button"
            className="helpoffer__no"
            onClick={close}
            aria-label="안내 권유 닫기"
          >
            ✕
          </button>
        </div>
      )}

      {open && <Tour steps={TOURS[id].steps} onClose={close} />}
    </>
  );
}
