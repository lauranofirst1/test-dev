/** Lifecycle-aware participant entry: ARRIVE → NOW → REMEMBER. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { ApiError } from '../api/client';
import { participantApi, saveParticipant } from '../api/participant';
import type { FavoriteMemory, FavoriteMemoryReason, PublicFestival } from '../api/types';
import { ExperienceCard } from '../components/consumer/ExperienceCard';
import { FlowTimeline } from '../components/consumer/FlowTimeline';
import { ShareAction } from '../components/consumer/ShareAction';
import { featuredExperiences } from '../consumer/adapters';
import { useConsumerJourney } from '../consumer/hooks';
import { resolveEventPhase, resolveParticipantLifecycle } from '../consumer/lifecycle';
import { deriveTimeContext } from '../consumer/metadata';
import type { ConsumerExperience } from '../consumer/model';
import type { ConsumerMoment } from '../consumer/moments';
import { resolveJoinReturnTo } from '../lib/navigation';
import { buildFlowShareUrl } from '../lib/share';

export function JoinPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const journey = useConsumerJourney(id);
  const [studentNo, setStudentNo] = useState('');
  const [transition, setTransition] = useState<string | null>(null);

  const join = useMutation({
    mutationFn: () => participantApi.issue(id, studentNo.trim() || undefined),
    onSuccess: (issued) => {
      saveParticipant(id, { code: issued.code, secret: issued.secret });
      void qc.invalidateQueries({ queryKey: ['my-progress', id] });
      setTransition(
        issued.resumed ? '이전에 남긴 Flow를 이어서 불러왔어요.' : '오늘의 Flow가 시작됐어요.',
      );
      const requested = params.get('returnTo');
      const destination = resolveJoinReturnTo(requested, id, window.location.origin);
      if (destination) {
        navigate(destination, { replace: true });
      }
    },
  });

  if (journey.festival.isLoading) {
    return <div className="shell"><div className="skeleton" style={{ height: 260 }} /></div>;
  }
  if (journey.festival.error instanceof ApiError || !journey.festival.data) {
    return (
      <div className="shell">
        <div className="card state">
          <p className="eyebrow">행사를 찾을 수 없습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            {journey.festival.error instanceof ApiError
              ? journey.festival.error.message
              : '행사 정보를 불러오지 못했습니다.'}
          </p>
        </div>
      </div>
    );
  }

  const festival = journey.festival.data;
  if (!journey.participant) {
    return (
      <ArriveSurface
        festival={festival}
        experiences={journey.experiences}
        studentNo={studentNo}
        onStudentNo={setStudentNo}
        pending={join.isPending}
        error={join.error instanceof ApiError ? join.error : null}
        onJoin={() => join.mutate()}
      />
    );
  }

  const phase = resolveEventPhase({
    status: festival.status,
    startsOn: festival.starts_on,
    endsOn: festival.ends_on,
  });
  const lifecycle = resolveParticipantLifecycle({
    hasParticipant: true,
    momentCount: journey.moments.length,
    eventPhase: phase,
  });

  if (lifecycle === 'post_event') {
    return (
      <RememberSurface
        festivalId={id}
        festival={festival}
        secret={journey.participant.secret}
        moments={journey.moments}
      />
    );
  }

  return (
    <NowSurface
      festivalId={id}
      moments={journey.moments}
      experiences={journey.experiences}
      transition={transition}
    />
  );
}

function ArriveSurface({
  festival,
  experiences,
  studentNo,
  onStudentNo,
  pending,
  error,
  onJoin,
}: {
  festival: PublicFestival;
  experiences: ConsumerExperience[];
  studentNo: string;
  onStudentNo: (value: string) => void;
  pending: boolean;
  error: ApiError | null;
  onJoin: () => void;
}) {
  const preview = featuredExperiences(experiences, 3);
  return (
    <main className="shell consumer-page consumer-arrive stack">
      <section className="consumer-event-hero">
        <p className="eyebrow">오늘 만날 행사</p>
        <h1>{festival.name}</h1>
        <p className="consumer-event-meta tabular">
          <span>{festival.starts_on === festival.ends_on ? festival.starts_on : `${festival.starts_on} — ${festival.ends_on}`}</span>
          <span>{[festival.region, festival.venue].filter(Boolean).join(' · ')}</span>
        </p>
        {festival.summary && <p className="lede">{festival.summary}</p>}
      </section>

      {preview.length > 0 && (
        <section className="consumer-preview stack">
          <div className="consumer-section-head">
            <div><p className="eyebrow">이런 경험이 있어요</p><h2>행사에서 만날 순간</h2></div>
          </div>
          <div className="consumer-experience-list">
            {preview.map((experience, index) => (
              <ExperienceCard
                key={experience.key}
                festivalId={String(festival.id)}
                experience={experience}
                context="featured"
                featured={index === 0}
              />
            ))}
          </div>
        </section>
      )}

      <form
        className="consumer-start stack"
        onSubmit={(event) => {
          event.preventDefault();
          if (!pending) onJoin();
        }}
      >
        {festival.identity_mode === 'student_id' && (
          <div className="field">
            <label htmlFor="student-no">학번</label>
            <input id="student-no" inputMode="numeric" autoComplete="off" value={studentNo} onChange={(event) => onStudentNo(event.target.value)} placeholder="20251234" />
            <span className="hint">
              중복 투표를 막고 특강 출결 명단을 만들기 위해 사용합니다. 학교 로그인이나
              본인 인증은 아니며 이름과 연락처는 받지 않습니다.
            </span>
          </div>
        )}
        {festival.identity_mode === 'anonymous' && (
          <p className="muted">이름이나 연락처 없이 이 행사에서만 쓰는 참여 코드를 만듭니다.</p>
        )}
        <details className="consumer-privacy">
          <summary>기록은 어떻게 쓰이나요?</summary>
          <p className="muted">
            상세 열람과 현장에서 확인된 참여는 행사 개선을 위해 집계됩니다. 직접 My
            Flow에 담은 Personal Moment는 이 기기에만 남고, Favorite Memory는 제출할
            때만 행사에 전달됩니다.
          </p>
        </details>
        {error && <div className="notice notice--warn"><span>⚠</span><span>{error.message}</span></div>}
        <button className="btn btn--primary btn--lg" type="submit" disabled={pending || (festival.identity_mode === 'student_id' && !studentNo.trim())}>
          {pending ? '시작하는 중…' : '행사 시작하기'}
        </button>
      </form>
    </main>
  );
}

function NowSurface({ festivalId, moments, experiences, transition }: { festivalId: string; moments: ConsumerMoment[]; experiences: ConsumerExperience[]; transition: string | null }) {
  const timed = useMemo(
    () =>
      experiences
        .map((experience) => ({ experience, context: deriveTimeContext(experience) }))
        .filter((item) => item.context && item.context.phase !== 'ended')
        .sort((a, b) => Date.parse(a.context!.startAt) - Date.parse(b.context!.startAt))
        .slice(0, 3),
    [experiences],
  );
  const discovery = experiences.find(
    (experience) => !experience.completed && !timed.some((item) => item.experience.key === experience.key),
  );

  return (
    <main className="shell consumer-page consumer-now stack">
      {transition && <div className="notice notice--ok"><span>✓</span><span>{transition}</span></div>}
      <section className="consumer-now-flow">
        <div className="consumer-section-head">
          <div><p className="eyebrow">My Flow</p><h1>{moments.length > 0 ? `${moments.length}개의 순간이 남았어요.` : '첫 순간을 기다리고 있어요.'}</h1></div>
          <Link to={`/join/${festivalId}/flow`} className="consumer-text-link">전체 보기 →</Link>
        </div>
        <FlowTimeline moments={moments} compact />
      </section>

      <section className="stack" style={{ gap: 'var(--space-3)' }}>
        <div className="consumer-section-head"><div><p className="eyebrow">지금</p><h2>잠깐 확인할 것</h2></div></div>
        {timed.length > 0 ? (
          <div className="consumer-experience-list">
            {timed.map(({ experience }) => <ExperienceCard key={experience.key} festivalId={festivalId} experience={experience} context="now" />)}
          </div>
        ) : (
          <p className="consumer-quiet-state">지금 꼭 확인할 일정은 없어요. 행사장을 천천히 둘러봐도 좋아요.</p>
        )}
      </section>

      {discovery && (
        <section className="stack" style={{ gap: 'var(--space-3)' }}>
          <div className="consumer-section-head"><div><p className="eyebrow">이런 것도 있어요</p></div></div>
          <ExperienceCard festivalId={festivalId} experience={discovery} context="now" />
        </section>
      )}

      <div className="consumer-tool-row">
        <Link to={`/join/${festivalId}/scan`} className="btn btn--soft">◎ 현장 QR 읽기</Link>
        <Link to={`/join/${festivalId}/explore`} className="btn btn--ghost">둘러보기</Link>
      </div>
    </main>
  );
}

const REASONS: { value: FavoriteMemoryReason; label: string }[] = [
  { value: 'fun', label: '재밌어서' },
  { value: 'new', label: '새로워서' },
  { value: 'together', label: '함께해서' },
  { value: 'discovered', label: '우연히 발견해서' },
  { value: 'again', label: '다시 하고 싶어서' },
];

function RememberSurface({ festivalId, festival, secret, moments }: { festivalId: string; festival: PublicFestival; secret: string; moments: ConsumerMoment[] }) {
  const favorite = useQuery({
    queryKey: ['favorite-memory', festivalId],
    queryFn: () => participantApi.get<FavoriteMemory | null>(festivalId, '/favorite-memory', secret),
    retry: false,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [reason, setReason] = useState<FavoriteMemoryReason | null>(null);
  const [comment, setComment] = useState('');
  const effectiveKey = selected ?? (favorite.data ? `${favorite.data.source_type}:${favorite.data.source_id}` : null);

  useEffect(() => {
    if (!favorite.data) return;
    setReason(favorite.data.reason);
    setComment(favorite.data.comment ?? '');
  }, [favorite.data]);

  const save = useMutation({
    mutationFn: () => {
      const moment = moments.find((item) => item.key === effectiveKey);
      if (!moment) throw new Error('favorite missing');
      return participantApi.put<FavoriteMemory>(festivalId, '/favorite-memory', secret, {
        source_type: moment.sourceType,
        source_id: moment.sourceId,
        reason,
        comment: comment.trim() || null,
      });
    },
    onSuccess: (data) => {
      void favorite.refetch();
      setReason(data.reason);
      setComment(data.comment ?? '');
    },
  });

  const shareText = `${festival.name}에서 ${moments.length}개의 순간이 남았어요.`;
  const shareUrl = buildFlowShareUrl(window.location.origin, festivalId);

  return (
    <main className="shell consumer-page consumer-remember stack">
      <section className="consumer-event-hero">
        <p className="eyebrow">Remember</p><h1>{festival.name}에서 남은 순간들</h1>
        <p className="lede">놓친 것은 세지 않아요. 오늘 내 Flow에 남은 경험만 천천히 돌아보세요.</p>
      </section>
      <FlowTimeline moments={moments} />

      {moments.length > 0 && (
        <section className="consumer-memory stack">
          <div><p className="eyebrow">가장 기억에 남은 순간은?</p><h2>하나를 골라 남겨주세요</h2></div>
          <div className="consumer-memory-options">
            {moments.map((moment) => (
              <button type="button" key={moment.key} aria-pressed={effectiveKey === moment.key} className={effectiveKey === moment.key ? 'is-selected' : ''} onClick={() => {
                if (effectiveKey !== moment.key) {
                  setReason(null);
                  setComment('');
                }
                setSelected(moment.key);
              }}>
                <span>{moment.title}</span><small>{moment.typeLabel}</small>
              </button>
            ))}
          </div>
          {effectiveKey && (
            <>
              <div className="tagbar">
                {REASONS.map((item) => (
                  <button key={item.value} type="button" className={`tagchip${reason === item.value ? ' tagchip--on' : ''}`} onClick={() => setReason(reason === item.value ? null : item.value)}>{item.label}</button>
                ))}
              </div>
              <div className="field"><label htmlFor="memory-comment">한 줄 더 남기기 (선택)</label><input id="memory-comment" maxLength={500} value={comment} onChange={(event) => setComment(event.target.value)} /></div>
              {save.error instanceof ApiError && <div className="notice notice--warn"><span>⚠</span><span>{save.error.message}</span></div>}
              {save.isSuccess && <div className="notice notice--ok"><span>✓</span><span>이 순간을 행사에 전했어요.</span></div>}
              <button className="btn btn--primary btn--lg" type="button" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? '남기는 중…' : '가장 기억에 남은 순간으로 남기기'}</button>
            </>
          )}
        </section>
      )}
      <ShareAction
        data={{ title: `${festival.name} · My Flow`, text: shareText, url: shareUrl }}
        fallbackText={`${shareText}\n${shareUrl}`}
        label="My Flow 공유하기"
      />
      <Link to={`/join/${festivalId}/flow`} className="consumer-text-link">내 Flow 자세히 보기 →</Link>
    </main>
  );
}
