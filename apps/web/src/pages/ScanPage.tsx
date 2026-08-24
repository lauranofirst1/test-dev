/** 부스 QR을 스캔한 관객이 도착하는 화면 — 계약 §8.3, §11.
 *
 * URL 은 부스 화면의 QR 에 담긴 `?b={booth_id}&t={token}` 입니다.
 *
 * 카운트다운은 서버가 준 `accepted_until` 을 씁니다. QR 은 30초마다 갱신되지만
 * 서버는 직전 window 까지 인정하므로, 화면이 `expires_at` 으로 잠그면 서버가
 * 받아줄 30초를 먼저 포기해 실제로 "되는데 안 되는" 상태가 됩니다.
 *
 * 실패를 한 덩어리로 뭉개지 않습니다. 만료(410)는 다시 스캔하면 되지만,
 * 위조(400)는 다시 스캔해도 안 되므로 그렇게 안내하면 영원히 다시 스캔합니다.
 *
 * **체험(퀴즈·안내)은 서버가 채점합니다.** 이 화면은 정답을 모릅니다 —
 * `experience_config` 에 `answer_index` 가 오지 않습니다. 오답이면 서버가
 * `EXPERIENCE_WRONG_ANSWER` 와 남은 시도 횟수를 돌려주고, 그때까지 참여
 * 이력은 만들어지지 않습니다.
 *
 * 미션이 하나뿐이면 선택 화면을 건너뛰고 바로 체험으로 들어갑니다(설계 05 §1).
 * 한 손에 먹거리를 들고 서 있는 사람에게 화면을 한 번 더 태우지 않습니다.
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { ApiError } from '../api/client';
import { clearParticipant, loadParticipant, participantApi } from '../api/participant';
import type {
  GrantResult,
  InfoConfig,
  QuizConfig,
  ScanContext,
  ScanContextMission,
} from '../api/types';

export function ScanPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [params] = useSearchParams();
  const boothId = params.get('b');
  // 회전 QR 은 `t`(토큰), 인쇄 QR 은 `s`(고정 서명). 어느 쪽이든 하나면 된다 —
  // 부스가 어느 모드인지는 서버가 알고, 맞지 않으면 서버가 거절한다.
  const token = params.get('t');
  const signature = params.get('s');
  const proof = token ?? signature;
  const stored = loadParticipant(id);

  const scan = useQuery({
    queryKey: ['scan', id, boothId, proof],
    queryFn: () => {
      const param = token
        ? `token=${encodeURIComponent(token)}`
        : `s=${encodeURIComponent(signature!)}`;
      return participantApi.get<ScanContext>(
        id,
        `/scan?booth_id=${boothId}&${param}`,
        stored!.secret,
      );
    },
    enabled: !!stored && !!boothId && !!proof,
    retry: false,
  });

  const grant = useMutation({
    mutationFn: (vars: { missionId: number; response?: Record<string, unknown> }) =>
      participantApi.post<GrantResult>(id, '/scan-grants', stored!.secret, {
        booth_id: Number(boothId),
        token,
        signature,
        mission_id: vars.missionId,
        response: vars.response ?? null,
      }),
  });

  const [remaining, setRemaining] = useState<number | null>(null);
  useEffect(() => {
    if (scan.data == null) return;
    // 인쇄 QR 은 seconds_remaining 이 null 이다. 카운트다운을 돌리지 않는다.
    if (scan.data.seconds_remaining == null) {
      setRemaining(null);
      return;
    }
    setRemaining(scan.data.seconds_remaining);
    const timer = setInterval(
      () => setRemaining((r) => (r === null ? null : Math.max(0, r - 1))),
      1000,
    );
    return () => clearInterval(timer);
  }, [scan.data]);

  // 아직 안 받은 미션만 고를 수 있다. 하나뿐이면 선택 화면을 건너뛴다.
  const open = useMemo(
    () => (scan.data?.missions ?? []).filter((m) => !m.already_granted),
    [scan.data],
  );
  const [pickedId, setPickedId] = useState<number | null>(null);
  useEffect(() => {
    if (open.length === 1) setPickedId(open[0].mission_id);
  }, [open]);
  const picked = open.find((m) => m.mission_id === pickedId) ?? null;

  if (!boothId || !proof) {
    return <Fail title="잘못된 링크입니다" body="부스 화면의 QR을 다시 스캔해 주세요." id={id} />;
  }

  if (!stored) {
    return (
      <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
        <div className="card state">
          <p className="eyebrow">먼저 참여를 시작해 주세요</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            참여 코드를 받은 뒤 다시 QR을 스캔하면 조각이 열립니다.
          </p>
          <Link to={`/join/${id}`} className="btn btn--primary btn--lg">
            참여 시작하기
          </Link>
        </div>
      </div>
    );
  }

  // 저장된 비밀이 죽었으면 여기서도 비운다. 그러지 않으면 스캔할 때마다 같은
  // 오류를 보고, 참여 화면으로 가도 갇힌 상태가 그대로다.
  if (scan.error instanceof ApiError && scan.error.status === 401) {
    clearParticipant(id);
    return (
      <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
        <div className="card state">
          <p className="eyebrow">참여 정보를 다시 만들어야 합니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            이전 참여 정보가 더 이상 유효하지 않습니다. 참여를 다시 시작한 뒤 QR을 스캔해
            주세요.
          </p>
          <Link to={`/join/${id}`} className="btn btn--primary btn--lg">
            참여 다시 시작하기
          </Link>
        </div>
      </div>
    );
  }

  if (scan.error instanceof ApiError) {
    const expired = scan.error.code === 'SCAN_TOKEN_EXPIRED';
    return (
      <Fail
        title={expired ? 'QR이 만료되었습니다' : '이 QR로는 지급할 수 없습니다'}
        body={scan.error.message}
        id={id}
        // 위조·모드 불일치는 다시 스캔해도 해결되지 않는다. 보드로 보낸다.
        retryable={expired}
      />
    );
  }

  const done = grant.data;
  if (done) {
    return (
      <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
        <div className="card state">
          {/* 이미 받은 건과 방금 받은 건은 도장 문구로 구분한다 — 같은 화면이지만
              "또 찍힌" 것과 "새로 찍힌" 것은 다른 사실이다. */}
          <span className="stamp stamp--lg">
            {done.was_already_granted ? '기지급' : '지급'}
            <small>{done.was_already_granted ? 'ALREADY' : 'GRANTED'}</small>
          </span>
          <p className="eyebrow">
            {done.was_already_granted ? '이미 받은 미션입니다' : '조각이 열렸습니다'}
          </p>
          <p className="figure tabular" style={{ textAlign: 'center' }}>
            {done.board_progress.revealed_count} / {done.board_progress.total_tiles}
            <small>모은 조각</small>
          </p>
          <p className="lede" style={{ textAlign: 'center' }}>
            {done.participation.granted_points.toLocaleString()}점 적립
            {done.participation.bonus_points > 0 &&
              ` (보너스 +${done.participation.bonus_points.toLocaleString()})`}
          </p>
          {/* 몇 번 만에 맞혔는지는 자랑거리다. 한 번에 맞힌 건 굳이 말하지 않는다. */}
          {done.participation.attempt_count > 1 && (
            <p className="muted tabular">{done.participation.attempt_count}번 만에 정답</p>
          )}
          {/* 해설은 서버가 맞힌 사람에게만 내려준다. 설정에는 담겨 오지 않는다. */}
          {done.explanation && (
            <div className="notice notice--info" style={{ textAlign: 'left' }}>
              <span>📖</span>
              <span>{done.explanation}</span>
            </div>
          )}
          <Link to={`/join/${id}`} className="btn btn--primary btn--lg">
            내 조각 보기
          </Link>
        </div>
      </div>
    );
  }

  const s = scan.data;
  // 인쇄 QR 은 만료가 없으므로 remaining 이 null 이고, 그때는 잠기지 않는다.
  const expired = remaining === 0;
  const locked = expired || s?.scan_already_used || grant.isPending;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-5)' }}>
      {scan.isLoading && <div className="skeleton" style={{ height: 180 }} />}

      {s && (
        <>
          <div className="stack" style={{ gap: 'var(--space-3)' }}>
            <p className="eyebrow">부스 도착</p>
            <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>{s.booth_name}</h1>
            <p className="punch">
              <span>{[s.type_label, s.location].filter(Boolean).join(' · ') || '위치 미정'}</span>
            </p>
          </div>

          {remaining !== null && (
            <div className={`notice ${remaining > 0 ? 'notice--info' : 'notice--warn'}`}>
              <span>{remaining > 0 ? '⏱' : '⚠'}</span>
              <span>
                {remaining > 0
                  ? `${remaining}초 안에 마쳐 주세요.`
                  : 'QR이 만료되었습니다. 부스 화면의 QR을 다시 스캔해 주세요.'}
              </span>
            </div>
          )}

          {s.scan_already_used && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>
                이 부스에서 방금 스탬프를 받았습니다. 한 번 스캔으로 미션 하나만 받을 수 있습니다.
              </span>
            </div>
          )}

          {open.length === 0 && (
            <div className="card state">
              <p className="eyebrow">받을 미션이 없습니다</p>
              <p className="lede" style={{ textAlign: 'center' }}>
                이 부스의 미션을 모두 받았습니다.
              </p>
            </div>
          )}

          {/* 미션이 여럿일 때만 고르게 한다. 하나뿐이면 위에서 이미 정해졌다. */}
          {open.length > 1 && !picked && (
            <div className="card stack" style={{ gap: 'var(--space-2)' }}>
              <p className="eyebrow">미션을 고르세요</p>
              <div className="rcpt">
                {open.map((m) => (
                  <button
                    key={m.mission_id}
                    type="button"
                    className="rcpt__row"
                    disabled={locked}
                    onClick={() => setPickedId(m.mission_id)}
                  >
                    <span className="rcpt__name">
                      <strong>{m.title}</strong>
                      <span>{EXPERIENCE_LABEL[m.experience_type] ?? '도착 확인'}</span>
                    </span>
                    <span className="rcpt__lead" aria-hidden="true" />
                    <span className="rcpt__value tabular">{m.points.toLocaleString()}점</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {picked && (
            <Experience
              mission={picked}
              locked={!!locked}
              pending={grant.isPending}
              error={grant.error instanceof ApiError ? grant.error : null}
              onBack={open.length > 1 ? () => setPickedId(null) : undefined}
              onSubmit={(response) =>
                grant.mutate({ missionId: picked.mission_id, response })
              }
            />
          )}

          <Link to={`/join/${id}`} className="muted" style={{ textAlign: 'center' }}>
            내 조각 보기 →
          </Link>
        </>
      )}
    </div>
  );
}

const EXPERIENCE_LABEL: Record<string, string> = {
  stamp: '도착 확인',
  quiz: '퀴즈',
  info: '안내 읽기',
  photo: '사진',
  survey: '설문',
};

// ── 체험 ────────────────────────────────────────────────────────────────────

interface ExperienceProps {
  mission: ScanContextMission;
  locked: boolean;
  pending: boolean;
  error: ApiError | null;
  onBack?: () => void;
  onSubmit: (response?: Record<string, unknown>) => void;
}

function Experience(props: ExperienceProps) {
  const { mission } = props;
  if (mission.experience_type === 'quiz') return <Quiz {...props} />;
  if (mission.experience_type === 'info') return <Info {...props} />;
  return <Stamp {...props} />;
}

function ExperienceShell({
  mission,
  onBack,
  children,
}: {
  mission: ScanContextMission;
  onBack?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="card stack" style={{ gap: 'var(--space-4)' }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <p className="eyebrow">{EXPERIENCE_LABEL[mission.experience_type] ?? '미션'}</p>
        <span className="rcpt__value tabular">{mission.points.toLocaleString()}점</span>
      </div>
      {children}
      {onBack && (
        <button type="button" className="btn btn--ghost" onClick={onBack}>
          다른 미션 고르기
        </button>
      )}
    </div>
  );
}

function Stamp({ mission, locked, pending, error, onBack, onSubmit }: ExperienceProps) {
  return (
    <ExperienceShell mission={mission} onBack={onBack}>
      <h2 style={{ fontSize: 'var(--text-h3)' }}>{mission.title}</h2>
      {mission.description && <p className="lede">{mission.description}</p>}
      {error && <Problem error={error} />}
      <button
        className="btn btn--primary btn--lg"
        disabled={locked}
        onClick={() => onSubmit()}
      >
        {pending ? '받는 중…' : '도착 확인'}
      </button>
    </ExperienceShell>
  );
}

function Quiz({ mission, locked, pending, error, onBack, onSubmit }: ExperienceProps) {
  const config = mission.experience_config as unknown as QuizConfig;
  const [choice, setChoice] = useState<number | null>(null);

  // 남은 횟수는 서버가 진실이다. 오답 응답에 담겨 오면 그 값으로 갈아탄다 —
  // 화면이 스스로 세면 새로고침으로 초기화되고, 서버와 어긋난 숫자를 보여준다.
  const left =
    (error?.code === 'EXPERIENCE_WRONG_ANSWER'
      ? (error.details.attempts_left as number | undefined)
      : undefined) ?? mission.attempts_left;

  const exhausted = error?.code === 'EXPERIENCE_ATTEMPTS_EXCEEDED' || left === 0;
  const wrong = error?.code === 'EXPERIENCE_WRONG_ANSWER';

  return (
    <ExperienceShell mission={mission} onBack={onBack}>
      <h2 style={{ fontSize: 'var(--text-h3)', lineHeight: 1.35 }}>{config.question}</h2>

      <div className="choices">
        {config.choices.map((label, i) => (
          <button
            key={i}
            type="button"
            className={`choice${choice === i ? ' choice--on' : ''}${
              wrong && choice === i ? ' choice--wrong' : ''
            }`}
            disabled={locked || exhausted}
            aria-pressed={choice === i}
            onClick={() => setChoice(i)}
          >
            <span className="choice__no tabular">{i + 1}</span>
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* 힌트는 처음부터 보여주지 않는다. 한 번 틀린 사람에게만 열린다. */}
      {config.hint && wrong && !exhausted && (
        <div className="notice notice--info">
          <span>💡</span>
          <span>{config.hint}</span>
        </div>
      )}

      {error && <Problem error={error} />}

      {/* 시도를 다 쓴 사람에게만 온다. 남아 있을 때 오면 남은 시도가 공짜가 된다. */}
      {typeof error?.details?.explanation === 'string' && (
        <div className="notice notice--info">
          <span>📖</span>
          <span>{error.details.explanation as string}</span>
        </div>
      )}

      {!exhausted && left != null && !error && (
        <p className="muted tabular">{left}번 시도할 수 있습니다</p>
      )}

      <button
        className="btn btn--primary btn--lg"
        disabled={locked || exhausted || choice === null}
        onClick={() => onSubmit({ choice_index: choice })}
      >
        {pending ? '채점 중…' : exhausted ? '시도 횟수를 모두 썼습니다' : '정답 제출'}
      </button>
    </ExperienceShell>
  );
}

function Info({ mission, locked, pending, error, onBack, onSubmit }: ExperienceProps) {
  const config = mission.experience_config as unknown as InfoConfig;
  const required = config.min_dwell_seconds ?? 0;
  const [waited, setWaited] = useState(0);

  useEffect(() => {
    if (!required) return;
    const timer = setInterval(() => setWaited((w) => w + 1), 1000);
    return () => clearInterval(timer);
  }, [required]);

  const left = Math.max(0, required - waited);

  return (
    <ExperienceShell mission={mission} onBack={onBack}>
      <h2 style={{ fontSize: 'var(--text-h3)' }}>{mission.title}</h2>
      <p className="lede" style={{ whiteSpace: 'pre-wrap' }}>
        {config.body}
      </p>

      {config.links?.length > 0 && (
        <div className="rcpt">
          {config.links.map((l) => (
            <a
              key={l.url}
              className="rcpt__row"
              href={l.url}
              target="_blank"
              rel="noreferrer noopener"
            >
              <span className="rcpt__name">
                <strong>{l.label}</strong>
              </span>
              <span className="rcpt__lead" aria-hidden="true" />
              <span className="rcpt__value">열기 ↗</span>
            </a>
          ))}
        </div>
      )}

      {error && <Problem error={error} />}

      <button
        className="btn btn--primary btn--lg"
        disabled={locked || left > 0}
        onClick={() => onSubmit({ dwell_seconds: waited })}
      >
        {pending ? '받는 중…' : left > 0 ? `${left}초 뒤에 확인할 수 있습니다` : '다 읽었습니다'}
      </button>
    </ExperienceShell>
  );
}

/** 체험 실패 안내. 서버 문구를 그대로 쓴다 — 무엇이 잘못됐고 어떻게 하는지 서버가 안다. */
function Problem({ error }: { error: ApiError }) {
  const fatal =
    error.code === 'EXPERIENCE_ATTEMPTS_EXCEEDED' || error.code === 'SCAN_ALREADY_USED';
  return (
    <div className={`notice ${fatal ? 'notice--warn' : 'notice--warn'}`}>
      <span>{error.code === 'EXPERIENCE_WRONG_ANSWER' ? '✗' : '⚠'}</span>
      <span>{error.message}</span>
    </div>
  );
}

function Fail({
  title,
  body,
  id,
  retryable = true,
}: {
  title: string;
  body: string;
  id: string;
  retryable?: boolean;
}) {
  return (
    <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
      <div className="card state">
        <p className="eyebrow">{title}</p>
        <p className="lede" style={{ textAlign: 'center' }}>{body}</p>
        {retryable && (
          <p className="muted" style={{ textAlign: 'center' }}>
            부스 화면의 QR은 30초마다 바뀝니다. 화면을 보고 다시 스캔해 주세요.
          </p>
        )}
        <Link to={`/join/${id}`} className="btn btn--primary btn--lg">
          내 조각 보기
        </Link>
      </div>
    </div>
  );
}
