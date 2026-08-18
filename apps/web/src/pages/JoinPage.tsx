/** 관객 화면 — 참여 시작과 내 조각 보드. 계약 §7, §9.
 *
 * 이 화면은 로그인이 없습니다. 축제 링크로 들어와 버튼 한 번으로 참여 코드를 받고,
 * 그 뒤로는 부스에서 코드를 보여주거나 부스 QR을 스캔해 조각을 모읍니다.
 *
 * 완성 문구는 서버가 완성 판정을 했을 때만 내려옵니다. 클라이언트가 미리 알고
 * 보여주면 완성의 의미가 없어서, 판정도 문구도 서버에만 둡니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import {
  clearParticipant,
  loadParticipant,
  participantApi,
  saveParticipant,
} from '../api/participant';
import type { ParticipantBoard, ParticipantMe, PublicFestival } from '../api/types';

export function JoinPage() {
  const { id = '' } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [stored, setStored] = useState(() => loadParticipant(id));
  const [wasReset, setWasReset] = useState(false);

  const festival = useQuery({
    queryKey: ['public', id],
    queryFn: () => api.get<PublicFestival>(`/api/festivals/${id}/public`),
    retry: false,
  });

  const board = useQuery({
    queryKey: ['my-board', id, stored?.code],
    queryFn: () => participantApi.get<ParticipantBoard>(id, '/stamp-board/me', stored!.secret),
    enabled: !!stored,
    // 부스에서 스태프가 지급하면 이 화면은 그 사실을 모른다. 짧게 다시 물어본다.
    refetchInterval: 10_000,
    retry: false,
  });

  const me = useQuery({
    queryKey: ['my-progress', id, stored?.code],
    queryFn: () => participantApi.get<ParticipantMe>(id, '/participants/me', stored!.secret),
    enabled: !!stored,
    refetchInterval: 10_000,
    retry: false,
  });

  // 저장된 비밀이 더 이상 통하지 않으면 스스로 비우고 처음 화면으로 돌아간다.
  //
  // 이걸 하지 않으면 화면에 죽은 코드와 오류 문구만 남고 빠져나갈 버튼이 없어서,
  // 관객은 localStorage 를 직접 지우는 방법밖에 없다. 운영자가 참여 데이터를
  // 초기화했거나(리허설), 90일 뒤 익명화됐거나, 축제를 다시 만든 경우에 실제로 걸린다.
  const authFailed =
    (board.error instanceof ApiError && board.error.status === 401) ||
    (me.error instanceof ApiError && me.error.status === 401);

  useEffect(() => {
    if (!authFailed) return;
    clearParticipant(id);
    setStored(null);
    setWasReset(true);
  }, [authFailed, id]);

  const join = useMutation({
    mutationFn: () => participantApi.issue(id),
    onSuccess: (issued) => {
      // secret 은 이 응답에서만 나온다. 여기서 저장하지 않으면 되돌릴 방법이 없다.
      saveParticipant(id, { code: issued.code, secret: issued.secret });
      setStored({ code: issued.code, secret: issued.secret });
      setWasReset(false);
      qc.invalidateQueries({ queryKey: ['my-board', id] });
    },
  });

  const f = festival.data;

  // ── 참여 전 ──
  if (!stored) {
    return (
      <div className="shell stack" style={{ gap: 'var(--space-5)' }}>
        {festival.isLoading && <div className="skeleton" style={{ height: 200 }} />}
        {festival.error instanceof ApiError && (
          <div className="card state">
            <p className="eyebrow">축제를 찾을 수 없습니다</p>
            <p className="lede" style={{ textAlign: 'center' }}>{festival.error.message}</p>
          </div>
        )}
        {f && (
          <>
            <div className="stack" style={{ gap: 4 }}>
              <p className="eyebrow">축제 참여</p>
              <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>{f.name}</h1>
              <p className="muted">
                {f.region} · {f.venue} · {f.starts_on} ~ {f.ends_on}
              </p>
            </div>

            {wasReset && (
              <div className="notice notice--warn">
                <span>⚠</span>
                <span>
                  이전 참여 정보가 더 이상 유효하지 않아 초기화했습니다. 다시 시작하면 새 참여
                  코드를 받습니다.
                </span>
              </div>
            )}

            <div className="card stack" style={{ gap: 'var(--space-4)' }}>
              <p className="lede">
                부스를 돌면 축제 그림이 한 조각씩 열립니다. 이름이나 연락처는 받지 않습니다.
              </p>
              <button
                className="btn btn--primary btn--lg"
                onClick={() => join.mutate()}
                disabled={join.isPending}
              >
                {join.isPending ? '참여 코드 발급 중…' : '참여 시작하기'}
              </button>
              {join.error instanceof ApiError && (
                <div className="notice notice--warn">
                  <span>⚠</span>
                  <span>{join.error.message}</span>
                </div>
              )}
            </div>

            <BoothGuide festival={f} />
            <p className="muted" style={{ textAlign: 'center' }}>{f.source_note}</p>
          </>
        )}
      </div>
    );
  }

  // ── 참여 후 ──
  const b = board.data;
  const progress = b?.progress;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-5)' }}>
      <div className="stack" style={{ gap: 4 }}>
        <p className="eyebrow">내 축제 조각</p>
        <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>{f?.name ?? '축제'}</h1>
      </div>

      <div className="card card--accent stack" style={{ gap: 'var(--space-3)' }}>
        <p className="eyebrow">부스에서 이 코드를 보여주세요</p>
        <div className="accesscode tabular">{stored.code}</div>
        {me.data && (
          <p className="muted tabular" style={{ textAlign: 'center' }}>
            지급 {me.data.completed_count}건 · {me.data.total_points.toLocaleString()}점
          </p>
        )}
      </div>

      {board.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{board.error.message}</span>
        </div>
      )}

      {b && progress && (
        <div className="card stack" style={{ gap: 'var(--space-4)' }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <p className="eyebrow">
              {progress.revealed_count} / {progress.total_tiles} 조각
            </p>
            {progress.is_complete && <span className="badge badge--stable">완성</span>}
          </div>

          <div
            className="stampgrid"
            style={{ gridTemplateColumns: `repeat(${b.cols}, 1fr)` }}
            role="img"
            aria-label={`축제 조각 보드, ${progress.total_tiles}조각 중 ${progress.revealed_count}조각 공개`}
          >
            {b.tiles.map((t) => (
              <div
                key={t.tile_index}
                className={`stamptile${t.is_revealed ? ' stamptile--on' : ''}`}
                style={
                  t.is_revealed
                    ? {
                        backgroundImage: `url(${b.image_url})`,
                        backgroundSize: `${b.cols * 100}% ${b.rows * 100}%`,
                        backgroundPosition: `${(t.tile_index % b.cols) * (100 / (b.cols - 1 || 1))}% ${
                          Math.floor(t.tile_index / b.cols) * (100 / (b.rows - 1 || 1))
                        }%`,
                      }
                    : undefined
                }
              >
                {!t.is_revealed && <span aria-hidden="true">?</span>}
              </div>
            ))}
          </div>

          {b.complete_message_shown && (
            <div className="notice notice--ok">
              <span>✓</span>
              <span>{b.complete_message_shown}</span>
            </div>
          )}
        </div>
      )}

      {me.data && me.data.active_campaigns.length > 0 && (
        <div className="card card--sunk stack" style={{ gap: 'var(--space-3)' }}>
          <p className="eyebrow">지금 추가 보상</p>
          {me.data.active_campaigns.map((c) => (
            <div key={c.id} className="stack" style={{ gap: 2 }}>
              <strong>
                {c.title} <span className="tabular">+{c.bonus_points}점</span>
              </strong>
              <span className="muted">{c.message}</span>
            </div>
          ))}
        </div>
      )}

      {me.data && (
        <div className="card stack" style={{ gap: 'var(--space-3)' }}>
          <p className="eyebrow">미션</p>
          {me.data.missions.length === 0 && (
            <p className="muted">아직 열린 미션이 없습니다. 부스가 준비되면 여기에 표시됩니다.</p>
          )}
          {me.data.missions.map((m) => (
            <div key={m.mission_id} className="row" style={{ justifyContent: 'space-between' }}>
              <div className="stack" style={{ gap: 2 }}>
                <strong>{m.title}</strong>
                <span className="muted">{m.booth_name ?? '미배정'}</span>
              </div>
              {m.status === 'granted' ? (
                <span className="badge badge--stable tabular">
                  +{(m.granted_points ?? m.points).toLocaleString()}
                </span>
              ) : (
                <span className="badge badge--none tabular">{m.points.toLocaleString()}점</span>
              )}
            </div>
          ))}
        </div>
      )}

      {f && <p className="muted" style={{ textAlign: 'center' }}>{f.source_note}</p>}
    </div>
  );
}

function BoothGuide({ festival }: { festival: PublicFestival }) {
  if (festival.booths.length === 0) return null;
  return (
    <div className="card stack" style={{ gap: 'var(--space-3)' }}>
      <p className="eyebrow">부스 {festival.booths.length}곳</p>
      {festival.booths.map((b) => (
        <div key={b.id} className="row" style={{ justifyContent: 'space-between' }}>
          <div className="stack" style={{ gap: 2 }}>
            <strong>{b.name}</strong>
            <span className="muted">
              {[b.type_label, b.location].filter(Boolean).join(' · ') || '위치 미정'}
            </span>
          </div>
          <span className="badge badge--none">
            {b.verify_mode === 'participant_scan' ? 'QR 스캔' : '스태프 확인'}
          </span>
        </div>
      ))}
    </div>
  );
}
