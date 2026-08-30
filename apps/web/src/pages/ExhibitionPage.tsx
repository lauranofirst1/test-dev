/** 관객 투표 — 전시 작품을 보고 표를 준다.
 *
 * **다른 사람의 표는 화면에 없습니다.** 서버가 내려주지 않습니다. 투표 중에
 * 순위가 보이면 표가 순위를 따라가고, 그건 더 이상 관객 투표가 아닙니다.
 * 자기가 준 표는 보입니다 — 그건 남의 정보가 아닙니다.
 *
 * **남은 표를 항상 크게 둡니다.** 표가 한정돼 있다는 사실이 이 화면의 규칙이고,
 * 다 쓴 뒤에야 알게 되면 이미 준 표를 후회하게 됩니다. 그래서 표를 거두는 길도
 * 같은 화면에 둡니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { ApiError } from '../api/client';
import { loadParticipant, participantApi } from '../api/participant';
import type { PublicExhibit, VoteResult, VotingStatus } from '../api/types';

export function ExhibitionPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const qc = useQueryClient();
  const stored = loadParticipant(id);
  const [tag, setTag] = useState<string | null>(null);

  const status = useQuery({
    queryKey: ['exhibition', id, stored?.code],
    queryFn: () => participantApi.get<VotingStatus>(id, '/exhibition', stored!.secret),
    enabled: !!stored,
    retry: false,
  });

  const vote = useMutation({
    mutationFn: (v: { exhibitId: number; on: boolean }) =>
      v.on
        ? participantApi.post<VoteResult>(id, `/exhibits/${v.exhibitId}/vote`, stored!.secret)
        : participantApi.del<VoteResult>(id, `/exhibits/${v.exhibitId}/vote`, stored!.secret),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['exhibition', id] });
    },
  });

  if (!stored) {
    return (
      <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
        <div className="card state">
          <p className="eyebrow">먼저 참여를 시작해 주세요</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            학번으로 참여를 시작해야 투표할 수 있습니다.
          </p>
          <Link to={`/join/${id}`} className="btn btn--primary btn--lg">
            참여 시작하기
          </Link>
        </div>
      </div>
    );
  }

  const s = status.data;
  const focusId = Number(searchParams.get('focus')) || null;
  const shown = (s?.exhibits ?? [])
    .filter((e) => !tag || e.tags.includes(tag))
    .sort((a, b) => Number(b.id === focusId) - Number(a.id === focusId));
  const left = s ? s.votes_limit - s.votes_used : 0;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-5)' }}>
      <div className="stack" style={{ gap: 4 }}>
        <p className="eyebrow">전시 투표</p>
        <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>작품</h1>
      </div>

      {status.isLoading && <div className="skeleton" style={{ height: 200 }} />}

      {focusId && s?.exhibits.some((exhibit) => exhibit.id === focusId) && (
        <div className="notice notice--ok">
          <span aria-hidden>↓</span>
          <span>상세에서 고른 작품을 목록 맨 앞에 두었습니다.</span>
        </div>
      )}

      {status.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{status.error.message}</span>
        </div>
      )}

      {/* 투표할 수 없는 이유는 서버가 문장으로 준다. 화면이 다시 판정하지 않는다. */}
      {s && !s.can_vote && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{s.reason}</span>
        </div>
      )}

      {s && s.can_vote && (
        <div className="votebar">
          <span className="votebar__label">남은 표</span>
          <span className="votebar__slots" aria-label={`${s.votes_limit}표 중 ${left}표 남음`}>
            {Array.from({ length: s.votes_limit }, (_, i) => (
              <span
                key={i}
                className={`votebar__slot${i < left ? ' votebar__slot--on' : ''}`}
                aria-hidden="true"
              />
            ))}
          </span>
          <span className="votebar__count tabular">
            {left} / {s.votes_limit}
          </span>
        </div>
      )}

      {vote.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{vote.error.message}</span>
        </div>
      )}

      {vote.data?.voted && (
        <div className="notice notice--ok" role="status">
          <span>✓</span>
          <span>
            My Flow에 ‘{s?.exhibits.find((exhibit) => exhibit.id === vote.data?.exhibit_id)?.title ?? '이 작품'}’
            순간이 남았어요. <Link to={`/join/${id}/flow`}>Flow 보기</Link>
          </span>
        </div>
      )}

      {/* 태그 거르기. 작품이 수십 점이면 훑는 것만으로 시간이 간다. */}
      {s && s.tags.length > 0 && (
        <div className="tagbar">
          <button
            type="button"
            className={`tagchip${tag === null ? ' tagchip--on' : ''}`}
            aria-pressed={tag === null}
            onClick={() => setTag(null)}
          >
            전체 {s.exhibits.length}
          </button>
          {s.tags.map((t) => (
            <button
              key={t}
              type="button"
              className={`tagchip${tag === t ? ' tagchip--on' : ''}`}
              aria-pressed={tag === t}
              onClick={() => setTag(tag === t ? null : t)}
            >
              #{t}
            </button>
          ))}
        </div>
      )}

      {s && shown.length === 0 && (
        <div className="card state">
          <p className="eyebrow">{tag ? '이 태그의 작품이 없습니다' : '아직 작품이 없습니다'}</p>
        </div>
      )}

      <div className="exhibits">
        {shown.map((e) => (
          <ExhibitCard
            key={e.id}
            exhibit={e}
            canVote={!!s?.can_vote}
            outOfVotes={left === 0}
            pending={vote.isPending}
            focused={e.id === focusId}
            onToggle={(on) => vote.mutate({ exhibitId: e.id, on })}
          />
        ))}
      </div>

      <Link to={`/join/${id}`} className="muted" style={{ textAlign: 'center' }}>
        내 조각 보기 →
      </Link>
    </div>
  );
}

function ExhibitCard({
  exhibit,
  canVote,
  outOfVotes,
  pending,
  focused,
  onToggle,
}: {
  exhibit: PublicExhibit;
  canVote: boolean;
  outOfVotes: boolean;
  pending: boolean;
  focused: boolean;
  onToggle: (on: boolean) => void;
}) {
  // 표를 다 썼어도 **이미 준 표는 거둘 수 있어야 한다.** 그러지 않으면 첫
  // 세 작품에 준 표가 영원히 묶인다.
  const disabled = pending || (!exhibit.voted && (outOfVotes || !canVote));

  return (
    <article
      id={`exhibit-${exhibit.id}`}
      className={`card exhibit${exhibit.voted ? ' exhibit--voted' : ''}${focused ? ' exhibit--focused' : ''}`}
    >
      {exhibit.poster_url ? (
        <img className="exhibit__poster" src={exhibit.poster_url} alt={`${exhibit.title} 포스터`} />
      ) : (
        <div className="exhibit__poster exhibit__poster--none" aria-hidden="true">
          <span className="tabular">{exhibit.entry_no}</span>
        </div>
      )}

      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        <div className="row" style={{ gap: 'var(--space-2)', alignItems: 'baseline' }}>
          <span className="exhibit__no tabular">{exhibit.entry_no}</span>
          <h3 style={{ fontSize: 'var(--text-h3)' }}>{exhibit.title}</h3>
        </div>
        {exhibit.team_name && <span className="muted">{exhibit.team_name}</span>}
        {exhibit.summary && <p className="soft">{exhibit.summary}</p>}
        {exhibit.location && <span className="muted">📍 {exhibit.location}</span>}

        {exhibit.tags.length > 0 && (
          <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
            {exhibit.tags.map((t) => (
              <span key={t} className="tagchip tagchip--flat">
                #{t}
              </span>
            ))}
          </div>
        )}
      </div>

      <button
        className={`btn btn--lg ${exhibit.voted ? 'btn--soft' : 'btn--primary'}`}
        disabled={disabled}
        onClick={() => onToggle(!exhibit.voted)}
      >
        {exhibit.voted
          ? '✓ 표를 줬습니다 — 거두기'
          : outOfVotes
            ? '표를 모두 썼습니다'
            : '이 작품에 투표'}
      </button>
    </article>
  );
}
