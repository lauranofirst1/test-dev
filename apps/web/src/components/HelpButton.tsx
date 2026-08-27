/** 지금 보고 있는 화면의 안내를 켜는 단추.
 *
 * 화면마다 다른 안내를 띄웁니다. 한 곳에 모아 둔 도움말 페이지로 보내면, 거기서
 * 자기 화면을 다시 찾아야 하고 대부분 그 지점에서 그만둡니다.
 *
 * 안내가 없는 화면에서는 **단추 자체가 나오지 않습니다.** 눌러서 "준비 중입니다"
 * 를 보는 것은 없느니만 못합니다.
 */

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation } from 'react-router-dom';

import { Tour } from './Tour';
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

  // ── 떠 있는 단추 ──
  //
  // 상단 바에 두었더니 다른 아이콘들 사이에 섞여 눈에 띄지 않았고, 화면을
  // 내리면 같이 사라졌습니다. 안내는 **막혔을 때** 찾는 것이라, 막힌 그 자리에서
  // 손이 닿아야 합니다. 오른쪽 아래는 엄지가 가장 쉽게 닿는 자리이기도 합니다.
  //
  // body 로 내보냅니다 — 상단 바 안에서 그리면 그 쌓임 맥락에 갇혀 본문 위로
  // 올라오지 못하는 일이 생깁니다.
  return createPortal(
    <>
      {!open && (
        <button
          type="button"
          className="helpfab"
          onClick={() => {
            setOffer(false);
            setOpen(true);
          }}
          aria-label={`${TOURS[id].label} 안내 보기`}
          title={`${TOURS[id].label} 안내`}
        >
          ?
        </button>
      )}

      {offer && !open && (
        <div className="helpoffer" role="status">
          <span>
            처음이신가요? <strong>{TOURS[id].label}</strong>을 짚어 드립니다.
          </span>
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
    </>,
    document.body,
  );
}
