/** 관객 화면 하단 탭.
 *
 * ## 왜 아래인가
 *
 * 축제장에서 이 화면을 쓰는 사람은 **한 손에 먹거리를 들고 서 있습니다.**
 * 엄지가 닿는 곳은 화면 아래쪽이고, 위쪽 모서리는 손을 고쳐 잡아야 닿습니다.
 *
 * ## 왜 필요했나
 *
 * 예전에는 참여 화면이 허브였고, 특강·전시로 들어가면 **되돌아가는 길이 화면
 * 맨 아래의 작은 회색 글씨** 하나뿐이었습니다. 조각을 하나 받고 보드를 보려면
 * 스크롤을 끝까지 내려 그 글씨를 찾아야 했습니다.
 *
 * ## 없는 탭은 띄우지 않는다
 *
 * 특강도 전시도 없는 축제가 대부분입니다 — 교내 행사에만 붙습니다. 늘 띄우면
 * 눌러도 "아직 없습니다" 만 나오고, **죽은 링크가 있는 메뉴는 없는 메뉴보다
 * 나쁩니다.** 서버가 `has_lectures` · `has_exhibits` 로 알려줍니다.
 *
 * 탭이 하나뿐이면 아예 띄우지 않습니다. 고를 것이 없는 탭 줄은 자리만
 * 차지합니다.
 *
 * ## 참여 코드가 없으면 띄우지 않는다
 *
 * 코드를 받기 전에는 갈 수 있는 곳이 참여 화면뿐입니다. 이때 탭을 띄우면
 * 눌러 봐야 전부 "참여 코드가 필요합니다" 로 돌아옵니다.
 */

import { useEffect, useState } from 'react';
import { NavLink, useParams } from 'react-router-dom';

import { loadParticipant, onParticipantChange } from '../api/participant';
import type { PublicFestival } from '../api/types';

interface Tab {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

export function AudienceTabs({ festival }: { festival?: PublicFestival }) {
  const { id = '' } = useParams<{ id: string }>();

  // 저장소를 한 번 읽고 마는 것으로는 부족하다. 참여 직후에도 "아직 참여 안
  // 함" 인 채로 남아 탭이 뜨지 않는다 — `localStorage` 는 같은 탭에서 바뀔 때
  // `storage` 이벤트를 내지 않기 때문이다.
  const [joined, setJoined] = useState(() => Boolean(loadParticipant(id)));
  useEffect(() => {
    const sync = () => setJoined(Boolean(loadParticipant(id)));
    sync();
    return onParticipantChange(sync);
  }, [id]);

  if (!joined || !festival) return null;

  const tabs: Tab[] = [
    { to: `/join/${id}`, label: '조각 보드', icon: '▦', end: true },
    { to: `/join/${id}/scan`, label: '찍기', icon: '◎' },
  ];
  if (festival.has_lectures) {
    tabs.push({ to: `/join/${id}/lectures`, label: '내 출결', icon: '✓' });
  }
  if (festival.has_exhibits) {
    tabs.push({ to: `/join/${id}/exhibition`, label: '전시 투표', icon: '★' });
  }

  // 고를 것이 없으면 탭 줄은 자리만 차지한다.
  if (tabs.length < 2) return null;

  return (
    <nav className="atabs" aria-label="축제 참여 메뉴">
      {tabs.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.end} className="atabs__tab">
          <span className="atabs__icon" aria-hidden>
            {t.icon}
          </span>
          <span className="atabs__label">{t.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
