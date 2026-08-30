import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { ApiError } from '../../api/client';
import { participantApi, type StoredParticipant } from '../../api/participant';
import type {
  ParticipantBoard,
  ParticipantMe,
  PrizeDrawResult,
  PrizeDrawStatus,
} from '../../api/types';
import { TrailBoard } from '../TrailBoard';

const ROLL_MS = 1600;

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

export function ParticipantExtras({
  festivalId,
  participant,
  me,
  board,
  drawStatus,
  hasLectures,
}: {
  festivalId: string;
  participant: StoredParticipant;
  me?: ParticipantMe;
  board?: ParticipantBoard;
  drawStatus?: PrizeDrawStatus;
  hasLectures: boolean;
}) {
  return (
    <section className="consumer-extras stack" style={{ gap: 'var(--space-4)' }}>
      <div className="consumer-section-head">
        <div>
          <p className="eyebrow">Extras</p>
          <h2>오늘의 기록과 혜택</h2>
        </div>
        <p className="muted">Flow의 순간과는 별도로 모아 두었어요.</p>
      </div>

      <div className="consumer-utility-card">
        <div>
          <span className="muted">참여 코드</span>
          <strong className="consumer-utility-code tabular">{participant.code}</strong>
        </div>
        <dl className="consumer-utility-stats">
          <div>
            <dt>기록</dt>
            <dd className="tabular">{me?.completed_count ?? '—'}개</dd>
          </div>
          <div>
            <dt>포인트</dt>
            <dd className="tabular">{me ? me.total_points.toLocaleString() : '—'}P</dd>
          </div>
        </dl>
      </div>

      {board && <BoardExtra board={board} />}
      {drawStatus?.enabled && (
        <DrawExtra festivalId={festivalId} participant={participant} status={drawStatus} />
      )}

      {hasLectures && (
        <Link to={`/join/${festivalId}/lectures`} className="consumer-extra-link">
          <span>
            <small>출결 · 확인서</small>
            <strong>내 특강 기록 보기</strong>
          </span>
          <span aria-hidden>→</span>
        </Link>
      )}
    </section>
  );
}

function BoardExtra({ board }: { board: ParticipantBoard }) {
  const progress = board.progress;
  return (
    <div className="consumer-extra-card stack" style={{ gap: 'var(--space-4)' }}>
      <div className="consumer-extra-card__head">
        <div>
          <span className="muted">조각 컬렉션</span>
          <strong className="tabular">
            {progress.revealed_count} / {progress.total_tiles}
          </strong>
        </div>
        {progress.is_complete && <span className="badge badge--stable">완성</span>}
      </div>

      {board.board_style === 'trail' ? (
        <TrailBoard
          tiles={board.tiles}
          revealedCount={progress.revealed_count}
          totalTiles={progress.total_tiles}
        />
      ) : (
        <div
          className="stampgrid"
          style={{
            gridTemplateColumns: `repeat(${board.cols}, 1fr)`,
            ['--grid-ratio' as string]: `${board.cols} / ${board.rows}`,
          }}
          role="img"
          aria-label={`${progress.total_tiles}조각 중 ${progress.revealed_count}조각 공개`}
        >
          {board.tiles.map((tile) => (
            <div
              key={tile.tile_index}
              className={`stamptile${tile.is_revealed ? ' stamptile--on' : ''}`}
              style={
                tile.is_revealed
                  ? {
                      backgroundImage: `url(${board.image_url})`,
                      backgroundSize: `${board.cols * 100}% ${board.rows * 100}%`,
                      backgroundPosition: `${
                        (tile.tile_index % board.cols) * (100 / (board.cols - 1 || 1))
                      }% ${
                        Math.floor(tile.tile_index / board.cols) *
                        (100 / (board.rows - 1 || 1))
                      }%`,
                    }
                  : undefined
              }
            >
              {!tile.is_revealed && <span aria-hidden>?</span>}
            </div>
          ))}
        </div>
      )}

      {board.complete_message_shown && (
        <p className="consumer-extra-note">{board.complete_message_shown}</p>
      )}
    </div>
  );
}

function DrawExtra({
  festivalId,
  participant,
  status,
}: {
  festivalId: string;
  participant: StoredParticipant;
  status: PrizeDrawStatus;
}) {
  const qc = useQueryClient();
  const [rolling, setRolling] = useState(false);
  const [face, setFace] = useState(0);

  useEffect(() => {
    if (!rolling) return;
    const timer = window.setInterval(() => setFace((value) => value + 1), 90);
    const stop = window.setTimeout(() => setRolling(false), ROLL_MS);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(stop);
    };
  }, [rolling]);

  const draw = useMutation({
    mutationFn: () =>
      participantApi.post<PrizeDrawResult>(festivalId, '/prize-draw', participant.secret),
    onSuccess: () => {
      if (!prefersReducedMotion()) setRolling(true);
      void qc.invalidateQueries({ queryKey: ['prize-draw', festivalId] });
      void qc.invalidateQueries({ queryKey: ['my-overview', festivalId] });
    },
  });

  const result = draw.data ?? status.draw;
  const shown = status.prizes.length > 0 ? status.prizes[face % status.prizes.length] : null;

  return (
    <div className="consumer-extra-card stack" style={{ gap: 'var(--space-3)' }}>
      <div className="consumer-extra-card__head">
        <div>
          <span className="muted">경품</span>
          <strong>{result ? '뽑기 결과' : '조각 완성 혜택'}</strong>
        </div>
      </div>

      {rolling && shown ? (
        <p className="draw__name draw__rolling" aria-hidden>
          {shown.name}
        </p>
      ) : result ? (
        <div className="stack" style={{ gap: 'var(--space-2)' }} role="status">
          {result.prize_name === null ? (
            <strong>준비된 경품이 모두 소진되었습니다</strong>
          ) : (
            <>
              <strong>{result.is_blank ? '이번에는 아쉽게도 꽝이에요' : result.prize_name}</strong>
              {result.prize_description && <p className="muted">{result.prize_description}</p>}
              {!result.is_blank && !result.claimed_at && (
                <p className="consumer-extra-note">
                  수령대에서 참여 코드 <b className="tabular">{participant.code}</b>를 보여주세요.
                </p>
              )}
              {!result.is_blank && result.claimed_at && (
                <p className="consumer-extra-note">수령을 마쳤어요.</p>
              )}
            </>
          )}
        </div>
      ) : (
        <>
          {status.prizes.length > 0 && (
            <div className="consumer-prize-list">
              {status.prizes.map((prize) => (
                <span key={`${prize.name}-${prize.is_blank}`}>{prize.name}</span>
              ))}
            </div>
          )}
          {draw.error instanceof ApiError && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>{draw.error.message}</span>
            </div>
          )}
          {status.can_draw ? (
            <button
              type="button"
              className="btn btn--primary btn--lg"
              onClick={() => draw.mutate()}
              disabled={draw.isPending}
            >
              {draw.isPending ? '여는 중…' : '경품 봉투 열기'}
            </button>
          ) : (
            <p className="muted tabular">
              조각 {status.total_tiles - status.revealed_count}개가 더 필요해요.
            </p>
          )}
        </>
      )}
    </div>
  );
}
