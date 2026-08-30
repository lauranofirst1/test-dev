import { useEffect, useState } from 'react';
import { NavLink, useParams } from 'react-router-dom';

import { loadParticipant, onParticipantChange } from '../api/participant';
import type { PublicFestival } from '../api/types';
import { resolveEventPhase } from '../consumer/lifecycle';

const tabIcon = { now: '●', explore: '⌁', flow: '∿' } as const;

export function AudienceTabs({ festival }: { festival?: PublicFestival }) {
  const { id = '' } = useParams<{ id: string }>();
  const [joined, setJoined] = useState(() => Boolean(loadParticipant(id)));

  useEffect(() => {
    const sync = () => setJoined(Boolean(loadParticipant(id)));
    sync();
    return onParticipantChange(sync);
  }, [id]);

  if (!joined || !festival) return null;

  const ended = resolveEventPhase({
    status: festival.status,
    startsOn: festival.starts_on,
    endsOn: festival.ends_on,
  }) === 'ended';
  const tabs = ended
    ? [
        { to: `/join/${id}`, label: '기억', icon: tabIcon.now, end: true },
        { to: `/join/${id}/flow`, label: '나의 Flow', icon: tabIcon.flow },
      ]
    : [
        { to: `/join/${id}`, label: '지금', icon: tabIcon.now, end: true },
        { to: `/join/${id}/explore`, label: '둘러보기', icon: tabIcon.explore },
        { to: `/join/${id}/flow`, label: '나의 Flow', icon: tabIcon.flow },
      ];

  return (
    <nav className="atabs" aria-label={`${festival.name} 참여 메뉴`}>
      {tabs.map((tab) => (
        <NavLink key={tab.to} to={tab.to} end={tab.end} className="atabs__tab">
          <span className="atabs__icon" aria-hidden>{tab.icon}</span>
          <span className="atabs__label">{tab.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
