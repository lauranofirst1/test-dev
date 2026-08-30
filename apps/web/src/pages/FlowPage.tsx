import { Link, useParams } from 'react-router-dom';

import { FlowTimeline } from '../components/consumer/FlowTimeline';
import { ParticipantExtras } from '../components/consumer/ParticipantExtras';
import { ShareAction } from '../components/consumer/ShareAction';
import { useConsumerJourney } from '../consumer/hooks';
import { buildFlowShareUrl } from '../lib/share';

export function FlowPage() {
  const { id = '' } = useParams<{ id: string }>();
  const journey = useConsumerJourney(id, { extras: true });
  if (!journey.participant) {
    return <main className="shell consumer-page"><div className="card state"><p className="eyebrow">행사를 먼저 시작해 주세요</p><Link to={`/join/${id}?returnTo=${encodeURIComponent(`/join/${id}/flow`)}`} className="btn btn--primary btn--lg">행사 시작하기</Link></div></main>;
  }
  const name = journey.festival.data?.name ?? 'FestaFlow';
  const shareText = `${name}에서 ${journey.moments.length}개의 순간이 남았어요.`;
  const shareUrl = buildFlowShareUrl(window.location.origin, id);
  return (
    <main className="shell consumer-page consumer-flow-page stack">
      <header className="consumer-page-head"><p className="eyebrow">My Flow</p><h1>{journey.moments.length > 0 ? `${journey.moments.length}개의 순간이 남았어요.` : '첫 순간을 기다리고 있어요.'}</h1><p className="muted">이 선은 실제 이동 경로나 완성률이 아니라, 경험이 쌓이는 모습을 나타냅니다.</p></header>
      <FlowTimeline moments={journey.moments} />
      <ShareAction
        data={{ title: `${name} · My Flow`, text: shareText, url: shareUrl }}
        fallbackText={`${shareText}\n${shareUrl}`}
        label="My Flow 공유하기"
      />
      <ParticipantExtras festivalId={id} participant={journey.participant} me={journey.me.data} board={journey.board.data} drawStatus={journey.draw.data} hasLectures={Boolean(journey.festival.data?.has_lectures)} />
    </main>
  );
}
