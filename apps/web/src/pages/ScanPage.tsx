/** 부스 QR을 스캔한 관객이 도착하는 화면 — 계약 §8.3.
 *
 * URL 은 부스 화면의 QR 에 담긴 `?b={booth_id}&t={token}` 입니다.
 *
 * 카운트다운은 서버가 준 `accepted_until` 을 씁니다. QR 은 30초마다 갱신되지만
 * 서버는 직전 window 까지 인정하므로, 화면이 `expires_at` 으로 잠그면 서버가
 * 받아줄 30초를 먼저 포기해 실제로 "되는데 안 되는" 상태가 됩니다.
 *
 * 실패를 한 덩어리로 뭉개지 않습니다. 만료(410)는 다시 스캔하면 되지만,
 * 위조(400)는 다시 스캔해도 안 되므로 그렇게 안내하면 영원히 다시 스캔합니다.
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { ApiError } from '../api/client';
import { clearParticipant, loadParticipant, participantApi } from '../api/participant';
import type { GrantResult, ScanContext } from '../api/types';

export function ScanPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [params] = useSearchParams();
  const boothId = params.get('b');
  const token = params.get('t');
  const stored = loadParticipant(id);

  const scan = useQuery({
    queryKey: ['scan', id, boothId, token],
    queryFn: () =>
      participantApi.get<ScanContext>(
        id,
        `/scan?booth_id=${boothId}&token=${encodeURIComponent(token!)}`,
        stored!.secret,
      ),
    enabled: !!stored && !!boothId && !!token,
    retry: false,
  });

  const grant = useMutation({
    mutationFn: (missionId: number) =>
      participantApi.post<GrantResult>(id, '/scan-grants', stored!.secret, {
        booth_id: Number(boothId),
        token,
        mission_id: missionId,
      }),
  });

  const [remaining, setRemaining] = useState<number | null>(null);
  useEffect(() => {
    if (scan.data == null) return;
    setRemaining(scan.data.seconds_remaining);
    const timer = setInterval(
      () => setRemaining((r) => (r === null ? null : Math.max(0, r - 1))),
      1000,
    );
    return () => clearInterval(timer);
  }, [scan.data]);

  if (!boothId || !token) {
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
          <p className="eyebrow">
            {done.was_already_granted ? '이미 받은 미션입니다' : '조각이 열렸습니다'}
          </p>
          <div className="accesscode tabular">
            {done.board_progress.revealed_count} / {done.board_progress.total_tiles}
          </div>
          <p className="lede" style={{ textAlign: 'center' }}>
            {done.participation.granted_points.toLocaleString()}점 적립
            {done.participation.bonus_points > 0 &&
              ` (보너스 +${done.participation.bonus_points.toLocaleString()})`}
          </p>
          <Link to={`/join/${id}`} className="btn btn--primary btn--lg">
            내 조각 보기
          </Link>
        </div>
      </div>
    );
  }

  const s = scan.data;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-5)' }}>
      {scan.isLoading && <div className="skeleton" style={{ height: 180 }} />}

      {s && (
        <>
          <div className="stack" style={{ gap: 4 }}>
            <p className="eyebrow">부스 도착</p>
            <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>{s.booth_name}</h1>
            <p className="muted">
              {[s.type_label, s.location].filter(Boolean).join(' · ') || '위치 미정'}
            </p>
          </div>

          {remaining !== null && (
            <div className={`notice ${remaining > 0 ? 'notice--info' : 'notice--warn'}`}>
              <span>{remaining > 0 ? '⏱' : '⚠'}</span>
              <span>
                {remaining > 0
                  ? `${remaining}초 안에 미션을 선택해 주세요.`
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

          {grant.error instanceof ApiError && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>{grant.error.message}</span>
            </div>
          )}

          <div className="card stack" style={{ gap: 'var(--space-3)' }}>
            <p className="eyebrow">미션을 고르세요</p>
            {s.missions.length === 0 && (
              <p className="muted">이 부스에 열린 미션이 없습니다.</p>
            )}
            {s.missions.map((m) => (
              <button
                key={m.mission_id}
                className="btn btn--ghost"
                style={{ justifyContent: 'space-between', width: '100%' }}
                disabled={
                  m.already_granted ||
                  s.scan_already_used ||
                  remaining === 0 ||
                  grant.isPending
                }
                onClick={() => grant.mutate(m.mission_id)}
              >
                <span>{m.title}</span>
                <span className="tabular">
                  {m.already_granted ? '받음' : `${m.points.toLocaleString()}점`}
                </span>
              </button>
            ))}
          </div>

          <Link to={`/join/${id}`} className="muted" style={{ textAlign: 'center' }}>
            내 조각 보기 →
          </Link>
        </>
      )}
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
