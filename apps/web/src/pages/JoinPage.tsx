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
import { Link, useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import { TrailBoard } from '../components/TrailBoard';
import {
  clearParticipant,
  loadParticipant,
  participantApi,
  saveParticipant,
} from '../api/participant';
import type {
  MyAttendance,
  ParticipantBoard,
  ParticipantMe,
  PrizeDrawResult,
  PrizeDrawStatus,
  PublicFestival,
} from '../api/types';

/** 두구두구 지속 시간. 길면 지루하고 짧으면 연출로 안 읽힌다. */
const ROLL_MS = 1600;

/** 움직임 줄이기를 켠 사람인가. 연출을 통째로 건너뛴다. */
function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

export function JoinPage() {
  const { id = '' } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [stored, setStored] = useState(() => loadParticipant(id));
  const [wasReset, setWasReset] = useState(false);
  //: 같은 학번으로 다시 들어와 기존 참여를 이어받았는가. 새로 시작한 것과
  //: 다른 사실이라 그대로 말해 준다 — 모은 조각이 사라진 줄 알면 안 된다.
  const [resumed, setResumed] = useState(false);

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

  // 뽑기는 완성해야 열린다. 완성 여부가 서버에서 바뀌므로 보드와 같이 갱신한다.
  const drawStatus = useQuery({
    queryKey: ['prize-draw', id, stored?.code],
    queryFn: () => participantApi.get<PrizeDrawStatus>(id, '/prize-draw/me', stored!.secret),
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

  const [studentNo, setStudentNo] = useState('');

  const join = useMutation({
    mutationFn: () => participantApi.issue(id, studentNo.trim() || undefined),
    onSuccess: (issued) => {
      // secret 은 이 응답에서만 나온다. 여기서 저장하지 않으면 되돌릴 방법이 없다.
      saveParticipant(id, { code: issued.code, secret: issued.secret });
      setStored({ code: issued.code, secret: issued.secret });
      setResumed(issued.resumed);
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
            <div className="stack" style={{ gap: 'var(--space-3)' }}>
              <p className="eyebrow">축제 참여</p>
              <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>{f.name}</h1>
              {/* 지역·장소·기간은 읽고 넘기는 정보라 인쇄된 띠로 눕힌다. */}
              <p className="punch">
                <span>
                  {f.region} · {f.venue} · {f.starts_on} ~ {f.ends_on}
                </span>
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

            {/* 학번을 묻는지는 축제가 정한다. 관광 축제는 지나가는 관광객에게
                신원을 요구할 수 없어 익명이 옳고, 교내 행사는 1인 1표와 공결
                처리 때문에 학번이 필요하다. */}
            <form
              className="card stack"
              style={{ gap: 'var(--space-4)' }}
              onSubmit={(e) => {
                e.preventDefault();
                if (!join.isPending) join.mutate();
              }}
            >
              {f.identity_mode === 'student_id' ? (
                <>
                  <p className="lede">
                    부스를 돌면 그림이 한 조각씩 열리고, 특강 출결도 함께 기록됩니다.
                  </p>
                  <div className="field">
                    <label htmlFor="student-no">
                      학번 <span className="req">*</span>
                    </label>
                    <input
                      id="student-no"
                      className="tabular"
                      value={studentNo}
                      onChange={(e) => setStudentNo(e.target.value)}
                      placeholder="20251234"
                      inputMode="numeric"
                      autoComplete="off"
                    />
                    {/* 왜 받는지 말한다. 이유 없이 학번을 요구하면 가짜를 넣는다. */}
                    <span className="hint">
                      한 학번에 한 번만 참여할 수 있습니다. 투표를 여러 번 하는 것을 막고,
                      공결 명단을 만들기 위해 받습니다. 이름과 연락처는 받지 않습니다.
                    </span>
                  </div>
                </>
              ) : (
                <p className="lede">
                  부스를 돌면 축제 그림이 한 조각씩 열립니다. 이름이나 연락처는 받지 않습니다.
                </p>
              )}

              <button
                className="btn btn--primary btn--lg"
                type="submit"
                disabled={
                  join.isPending || (f.identity_mode === 'student_id' && !studentNo.trim())
                }
              >
                {join.isPending ? '확인 중…' : '참여 시작하기'}
              </button>
              {join.error instanceof ApiError && (
                <div className="notice notice--warn">
                  <span>⚠</span>
                  <span>{join.error.message}</span>
                </div>
              )}
            </form>

            <BoothGuide festival={f} />
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
      {/* 헤더가 축제 이름을 계속 보여주므로 여기서 반복하지 않는다.
          참여 전에는 "이 축제가 맞나" 확인이 중요해 이름을 크게 두지만,
          참여 후에는 확인이 끝났고 필요한 건 지금 어디까지 모았는지다. */}
      <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>내 축제 조각</h1>

      {resumed && (
        <div className="notice notice--ok">
          <span>✓</span>
          <span>
            이미 참여한 학번입니다. 기존 참여를 이어받았고 모은 조각도 그대로입니다.
            이전에 쓰던 기기에서는 로그아웃됩니다.
          </span>
        </div>
      )}

      {/* ── 학생에게는 공결이 먼저다 ──
          조각 보드는 재미고 공결은 이해관계입니다. 성적에 직결되는 것을 퍼즐
          아래에 두면, 정작 미달인 학생이 그 사실을 축제가 끝난 뒤에 압니다.
          익명 축제에서는 이 블록이 통째로 나타나지 않습니다 — 지나가는
          관광객에게 출결과 투표는 아무 의미가 없습니다. */}
      {f?.identity_mode === 'student_id' && <StudentDuties festivalId={id} secret={stored.secret} />}

      <div className="ticket">
        <div className="ticket__stub">
          <p className="eyebrow">부스에서 이 코드를 보여주세요</p>
          <div className="accesscode tabular">{stored.code}</div>
        </div>
        <div className="ticket__perf" aria-hidden="true">
          <i />
        </div>
        <div className="ticket__foot">
          <span>지급 {me.data ? me.data.completed_count : '—'}건</span>
          <span className="tabular">
            {me.data ? me.data.total_points.toLocaleString() : '—'}점
          </span>
        </div>
      </div>

      {board.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{board.error.message}</span>
        </div>
      )}

      {b && progress && (
        <div className="card stack boardcard" style={{ gap: 'var(--space-4)' }}>
          <div
            className="row"
            style={{ justifyContent: 'space-between', alignItems: 'center' }}
          >
            <p className="figure tabular">
              {progress.revealed_count} / {progress.total_tiles}
              <small>모은 조각</small>
            </p>
            {progress.is_complete && (
              <span className="stamp">
                완성
                <small>COMPLETE</small>
              </span>
            )}
          </div>

          {/* 같은 타일·같은 공개 기록을 운영자가 고른 표현으로 그린다.
              구조가 아니라 표현이라 이 값을 바꿔도 진행은 그대로다. */}
          {b.board_style === 'trail' ? (
            <TrailBoard
              tiles={b.tiles}
              revealedCount={progress.revealed_count}
              totalTiles={progress.total_tiles}
            />
          ) : (
          <div
            className="stampgrid"
            style={{
              gridTemplateColumns: `repeat(${b.cols}, 1fr)`,
              // 원본 그림의 비율을 지켜야 조각이 맞춰졌을 때 그림이 된다.
              ['--grid-ratio' as string]: `${b.cols} / ${b.rows}`,
            }}
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
          )}

          {b.complete_message_shown && (
            <div className="notice notice--ok">
              <span>✓</span>
              <span>{b.complete_message_shown}</span>
            </div>
          )}
        </div>
      )}

      {drawStatus.data?.enabled && <DrawCard festivalId={id} status={drawStatus.data} />}

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
        <div className="card stack" style={{ gap: 'var(--space-2)' }}>
          <p className="eyebrow">미션</p>
          {me.data.missions.length === 0 && (
            <p className="muted">아직 열린 미션이 없습니다. 부스가 준비되면 여기에 표시됩니다.</p>
          )}
          <div className="rcpt">
            {me.data.missions.map((m) => (
              <div key={m.mission_id} className="rcpt__row">
                <span className="rcpt__name">
                  <strong>{m.title}</strong>
                  <span>{m.booth_name ?? '미배정'}</span>
                </span>
                <span className="rcpt__lead" aria-hidden="true" />
                {m.status === 'granted' ? (
                  <span className="rcpt__value rcpt__value--done tabular">
                    ✓ +{(m.granted_points ?? m.points).toLocaleString()}
                  </span>
                ) : (
                  <span className="rcpt__value rcpt__value--muted tabular">
                    {m.points.toLocaleString()}점
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}

/** 경품 뽑기 — 조각을 다 모은 사람만, 축제당 한 번.
 *
 * 결과는 **서버가 뽑습니다.** 화면이 뽑아서 보여주면 새로고침으로 다시 뽑을 수
 * 있고, 재고도 지킬 수 없습니다. 여기는 봉투를 뜯는 동작만 담당합니다.
 *
 * 완성 전에도 카드를 보여줍니다 — 무엇이 걸려 있는지 알아야 부스를 더 돌 이유가
 * 생깁니다. 다만 재고와 확률은 오지 않습니다(서버가 안 내려줍니다).
 */
function DrawCard({ festivalId, status }: { festivalId: string; status: PrizeDrawStatus }) {
  const qc = useQueryClient();
  const stored = loadParticipant(festivalId);

  // 두구두구 — 결과는 **서버가 이미 정했고** 이 연출은 그 위에 덮는 장막이다.
  // 화면이 뽑는 것처럼 보이면 안 된다. 그래서 응답을 받은 **뒤에** 돌리고,
  // 도는 동안 보여주는 이름은 실제 결과와 아무 관계가 없다.
  const [rolling, setRolling] = useState(false);
  const [face, setFace] = useState(0);

  useEffect(() => {
    if (!rolling) return;
    const timer = setInterval(() => setFace((f) => f + 1), 90);
    const stop = setTimeout(() => setRolling(false), ROLL_MS);
    return () => {
      clearInterval(timer);
      clearTimeout(stop);
    };
  }, [rolling]);

  const draw = useMutation({
    mutationFn: () =>
      participantApi.post<PrizeDrawResult>(festivalId, '/prize-draw', stored!.secret),
    onSuccess: () => {
      // 움직임을 끈 사람에게는 연출을 생략한다. 기다리게 할 이유가 없다.
      if (!prefersReducedMotion()) setRolling(true);
      qc.invalidateQueries({ queryKey: ['prize-draw', festivalId] });
    },
  });

  const result = draw.data ?? status.draw;

  if (rolling && status.prizes.length > 0) {
    const shown = status.prizes[face % status.prizes.length];
    return (
      <div className="card draw">
        <div className="draw__flap" aria-hidden="true" />
        <div className="draw__body">
          <p className="eyebrow">두구두구…</p>
          {/* aria-live 를 쓰지 않는다 — 90ms 마다 바뀌는 값을 읽어주면 소음이다.
              스크린리더에는 결과가 나온 뒤 한 번만 전해진다. */}
          <p className="draw__name draw__rolling" aria-hidden="true">
            {shown.name}
          </p>
          <p className="muted">경품을 뽑고 있습니다</p>
        </div>
      </div>
    );
  }

  if (result) {
    return (
      <div className="card draw">
        <div className="draw__flap" aria-hidden="true" />
        <div className="draw__body" role="status">
          <p className="eyebrow">뽑기 결과</p>
          {result.prize_name === null ? (
            // 상품이 하나도 남지 않은 상태. 꽝이라고 말하면 거짓말이다.
            <>
              <p className="draw__name">준비된 경품이 모두 소진되었습니다</p>
              <p className="muted">부스 스태프에게 문의해 주세요.</p>
            </>
          ) : (
            <>
              <span className={`stamp stamp--lg draw__result`}>
                {result.is_blank ? '꽝' : '당첨'}
                <small>{result.is_blank ? 'BLANK' : 'WINNER'}</small>
              </span>
              <p className="draw__name">{result.prize_name}</p>
              {result.prize_description && <p className="muted">{result.prize_description}</p>}
              {!result.is_blank &&
                (result.claimed_at ? (
                  <div className="notice notice--ok">
                    <span>✓</span>
                    <span>
                      수령 완료되었습니다 (
                      {new Date(result.claimed_at).toLocaleString('ko-KR')}).
                    </span>
                  </div>
                ) : (
                  // 수령은 스태프가 이 코드로 찾아 확인한다. 위 티켓에도 코드가
                  // 있지만 여기서 다시 크게 보여준다 — 당첨 화면을 열어 둔 채로
                  // 창구에 서는데, 그때 위로 스크롤하게 만들면 줄이 멈춘다.
                  <div className="stack" style={{ gap: 'var(--space-2)', alignItems: 'center' }}>
                    <p className="eyebrow">이 코드를 보여주세요</p>
                    <div className="accesscode tabular">{stored?.code ?? ''}</div>
                    <p className="muted">경품 수령대에서 스태프가 확인해 드립니다.</p>
                  </div>
                ))}
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="card draw">
      <div className="draw__flap" aria-hidden="true" />
      <div className="draw__body">
        <p className="eyebrow">조각을 다 모으면 뽑기 1회</p>

        {status.prizes.length > 0 && (
          <div className="draw__prizes">
            {status.prizes.map((p) => (
              <span
                key={p.name}
                className={`draw__chip${p.is_blank ? ' draw__chip--blank' : ''}`}
              >
                {p.name}
              </span>
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
            className="btn btn--primary btn--lg"
            onClick={() => draw.mutate()}
            disabled={draw.isPending}
          >
            {draw.isPending ? '뽑는 중…' : '봉투 열기'}
          </button>
        ) : (
          <p className="muted tabular">
            {status.total_tiles - status.revealed_count}조각 남았습니다
          </p>
        )}
      </div>
    </div>
  );
}

function BoothGuide({ festival }: { festival: PublicFestival }) {
  if (festival.booths.length === 0) return null;
  return (
    <div className="card stack" style={{ gap: 'var(--space-2)' }}>
      <p className="eyebrow">부스 {festival.booths.length}곳</p>
      <div className="rcpt">
        {festival.booths.map((b) => (
          <div key={b.id} className="rcpt__row">
            <span className="rcpt__name">
              <strong>{b.name}</strong>
              <span>{[b.type_label, b.location].filter(Boolean).join(' · ') || '위치 미정'}</span>
            </span>
            <span className="rcpt__lead" aria-hidden="true" />
            <span className="rcpt__value rcpt__value--muted">
              {b.verify_mode === 'participant_scan' ? 'QR 스캔' : '스태프 확인'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 학생이 먼저 봐야 하는 것 — 공결과 투표.
 *
 * **링크만 두지 않고 숫자를 함께 보여줍니다.** "내 출결 확인하기" 는 눌러야만
 * 알 수 있고, 안 누르면 미달인 줄 모릅니다. 몇 번 중 몇 번인지가 여기 보이면
 * 눌러야 할 사람이 스스로 눌러 봅니다.
 */
function StudentDuties({ festivalId, secret }: { festivalId: string; secret: string }) {
  const mine = useQuery({
    queryKey: ['my-lectures', festivalId],
    queryFn: () => participantApi.get<MyAttendance[]>(festivalId, '/lectures/me', secret),
    retry: false,
  });

  const items = mine.data ?? [];
  // 공결이 걸린 특강만 센다. 공결이 아닌 특강은 미달이어도 성적에 영향이 없다.
  const graded = items.filter((a) => a.grants_excused_absence);
  const short = graded.filter((a) => !a.is_met);

  return (
    <div className="duties stack" style={{ gap: 'var(--space-3)' }}>
      <Link to={`/join/${festivalId}/lectures`} className="card lecturelink">
        <span className="stack" style={{ gap: 2 }}>
          <span className="eyebrow">특강 출결</span>
          {graded.length === 0 ? (
            <strong>내 출결 확인하기</strong>
          ) : short.length > 0 ? (
            // 미달을 숨기지 않는다. 지금 알아야 오늘 채울 수 있다.
            <strong className="duties__short">
              {short.length}개 특강이 아직 인정 기준에 못 미칩니다
            </strong>
          ) : (
            <strong>공결 대상 {graded.length}개 모두 인정 기준을 채웠습니다</strong>
          )}
          {graded.length > 0 && (
            <span className="muted tabular">
              {graded.map((a) => `${a.title} ${a.checked}/${a.required}`).join(' · ')}
            </span>
          )}
        </span>
        <span aria-hidden="true">→</span>
      </Link>

      <Link to={`/join/${festivalId}/exhibition`} className="card lecturelink">
        <span className="stack" style={{ gap: 2 }}>
          <span className="eyebrow">전시 투표</span>
          <strong>작품 보고 투표하기</strong>
        </span>
        <span aria-hidden="true">→</span>
      </Link>
    </div>
  );
}
