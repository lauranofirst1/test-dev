import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';

import { participantApi } from '../api/participant';
import type { ExperienceOpen, ExperienceOpenContext } from '../api/types';
import { ShareAction } from '../components/consumer/ShareAction';
import { useConsumerJourney } from '../consumer/hooks';
import { experienceMetadata } from '../consumer/metadata';
import { isExperienceSourceType } from '../consumer/model';
import { removePersonalMoment, savePersonalMoment } from '../consumer/moments';
import { buildExperienceShareUrl } from '../lib/share';

const OPEN_CONTEXTS: ExperienceOpenContext[] = ['now', 'featured', 'explore_time', 'explore_place', 'explore_type', 'search', 'shared_link', 'flow'];

export function ExperiencePage() {
  const { id = '', sourceType = '', sourceId = '' } = useParams<{ id: string; sourceType: string; sourceId: string }>();
  const [params] = useSearchParams();
  const location = useLocation();
  const journey = useConsumerJourney(id);
  const [personal, setPersonal] = useState(false);
  const numericId = Number(sourceId);
  const experience = isExperienceSourceType(sourceType) ? journey.experiences.find((item) => item.sourceType === sourceType && item.sourceId === numericId) : undefined;
  const requestedContext = params.get('from') as ExperienceOpenContext | null;
  const context = requestedContext && OPEN_CONTEXTS.includes(requestedContext) ? requestedContext : 'shared_link';

  useQuery({
    queryKey: ['experience-open', id, sourceType, numericId, context, journey.participant?.code],
    queryFn: () => participantApi.post<ExperienceOpen>(id, '/experience-opens', journey.participant!.secret, { source_type: sourceType, source_id: numericId, source_context: context }),
    enabled: Boolean(journey.participant && experience),
    retry: false,
    // StrictMode의 즉시 재마운트는 합치되, 나중에 다시 상세를 여는 행동은
    // 별도의 의미 있는 Open으로 기록한다.
    staleTime: 5_000,
    refetchOnMount: true,
  });

  if (journey.festival.isLoading) return <div className="shell"><div className="skeleton" style={{ height: 260 }} /></div>;
  if (!experience) return <main className="shell consumer-page"><div className="card state"><p className="eyebrow">Experience를 찾을 수 없습니다</p><Link to={`/join/${id}/explore`} className="btn btn--primary">둘러보기</Link></div></main>;

  const signals = experienceMetadata(experience);
  const returnTo = `${location.pathname}${location.search}`;
  const actionHref = experience.participationAction.kind === 'scan_qr' ? `/join/${id}/scan` : experience.participationAction.kind === 'lecture_check_in' ? `/join/${id}/lectures` : experience.participationAction.kind === 'exhibit_vote' ? `/join/${id}/exhibition?focus=${experience.sourceId}` : null;
  const isPersonal = personal || journey.personal.some((item) => item.source_type === experience.sourceType && item.source_id === experience.sourceId);

  const shareUrl = buildExperienceShareUrl(window.location.origin, id, experience.sourceType, experience.sourceId);

  return (
    <main className="shell consumer-page consumer-detail stack">
      {experience.imageUrl && <img className="consumer-detail__image" src={experience.imageUrl} alt={`${experience.title} 이미지`} />}
      <header className="consumer-detail__head"><p className="eyebrow">{experience.typeLabel}</p><h1>{experience.title}</h1>{experience.summary && <p className="lede">{experience.summary}</p>}{experience.hostLabel && <p className="muted">{experience.hostLabel}</p>}</header>
      {signals.length > 0 && <dl className="consumer-context">{signals.map((signal) => <div key={signal.kind}><dt>{signal.kind === 'time' ? '언제' : signal.kind === 'duration' ? '얼마나' : '어디서'}</dt><dd>{signal.label}</dd></div>)}</dl>}

      <section className="consumer-action stack">
        <p className="eyebrow">이렇게 참여해요</p>
        <p>{experience.participationAction.label}</p>
        {!journey.participant && experience.participationAction.requiresParticipant ? (
          <Link to={`/join/${id}?returnTo=${encodeURIComponent(returnTo)}`} className="btn btn--primary btn--lg">행사 시작하고 계속하기</Link>
        ) : actionHref ? (
          <Link to={actionHref} className="btn btn--primary btn--lg">{experience.participationAction.label}</Link>
        ) : journey.participant && experience.participationAction.kind === 'show_participant_code' ? (
          <div className="consumer-utility-card"><span className="muted">스태프에게 보여줄 참여 코드</span><strong className="consumer-utility-code tabular">{journey.participant.code}</strong></div>
        ) : null}
      </section>

      {experience.reward && <section className="consumer-detail__secondary"><p className="eyebrow">Extra</p><p className="tabular">확인되면 {experience.reward.points.toLocaleString()}P</p></section>}
      {journey.participant && experience.completed !== true && (
        <button type="button" className={`btn ${isPersonal ? 'btn--soft' : 'btn--ghost'}`} onClick={() => { if (isPersonal) { removePersonalMoment(id, experience.sourceType, experience.sourceId); setPersonal(false); } else { savePersonalMoment(id, experience); setPersonal(true); } journey.refreshPersonal(); }}>
          {isPersonal ? '✓ 내 Flow에 남겼어요 — 지우기' : '내 Flow에 남기기'}
        </button>
      )}
      {experience.completed === true && <div className="notice notice--ok"><span>✓</span><span>확인된 순간으로 내 Flow에 남아 있어요.</span></div>}
      <ShareAction
        data={{ title: experience.title, text: experience.summary, url: shareUrl }}
        fallbackText={shareUrl}
        label="이 Experience 공유하기"
      />
    </main>
  );
}
