/** 체크인 QR 을 찍은 학생이 도착하는 화면.
 *
 * URL 은 스크린 QR 에 담긴 `?c={checkpoint_id}&t={token}` 입니다.
 *
 * **실패를 한 덩어리로 뭉개지 않습니다.** 시간이 지나 닫힌 것(410)은 다음 체크인을
 * 기다리면 되고, 위조·다른 강의 QR(400)은 기다려도 안 됩니다. 같은 문구로 안내하면
 * 닫힌 줄 알고 계속 기다리거나, 기다리면 되는데 포기합니다.
 *
 * 이미 찍힌 경우는 **오류가 아닙니다.** 두 번 찍었다고 빨간 화면을 띄우면 학생은
 * 자기가 뭘 잘못했다고 생각합니다.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { ApiError } from '../api/client';
import { loadParticipant, participantApi } from '../api/participant';
import type { CheckInResult } from '../api/types';

export function CheckInPage() {
  const { id = '' } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const sessionId = params.get('s');
  const checkpointId = params.get('c');
  const token = params.get('t');
  const stored = loadParticipant(id);

  // 체크인은 90초만 열린다. 도착하자마자 보낸다 — 버튼을 한 번 더 누르게 하면
  // 그 몇 초가 그대로 실패가 된다.
  //
  // **POST 지만 `useQuery` 를 쓴다.** "도착하면 한 번" 을 `useEffect` + `useRef` 로
  // 만들면 StrictMode(마운트 → 언마운트 → 재마운트)에서 깨진다. ref 로 잠그면 첫
  // 마운트의 요청이 버려진 뒤 재마운트가 막혀 아무것도 나가지 않고, 잠그지 않으면
  // 두 번 나가서 방금 찍은 사람이 "이미 찍었습니다" 를 본다.
  //
  // 쿼리 키로 묶으면 재마운트가 진행 중인 요청을 그대로 이어받아 **정확히 한 번**
  // 나가고, 첫 응답(`was_new: true`)이 그대로 화면에 남는다. 서버가 유니크 제약으로
  // 멱등하므로 POST 를 쿼리로 두어도 안전하다.
  const checkIn = useQuery({
    queryKey: ['checkin', id, sessionId, checkpointId, token],
    queryFn: () =>
      participantApi.post<CheckInResult>(id, `/lectures/${sessionId}/checkin`, stored!.secret, {
        checkpoint_id: Number(checkpointId),
        token,
      }),
    enabled: !!stored && !!sessionId && !!checkpointId && !!token,
    retry: false,
    // 결과는 한 번 정해지면 바뀌지 않는다. 다시 찍으려면 QR 을 다시 찍는다.
    staleTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  useEffect(() => {
    if (!checkIn.data) return;
    void qc.invalidateQueries({ queryKey: ['my-lectures', id] });
  }, [checkIn.data, id, qc]);


  if (!sessionId || !checkpointId || !token) {
    return (
      <Fail id={id} title="잘못된 링크입니다" body="강의실 화면의 QR 을 다시 찍어 주세요." />
    );
  }

  if (!stored) {
    return (
      <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
        <div className="card state">
          <p className="eyebrow">먼저 참여를 시작해 주세요</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            학번으로 참여를 시작한 뒤 다시 QR 을 찍으면 출석이 기록됩니다.
          </p>
          <Link
            to={`/join/${id}?returnTo=${encodeURIComponent(
              `${window.location.pathname}${window.location.search}`,
            )}`}
            className="btn btn--primary btn--lg"
          >
            참여 시작하기
          </Link>
        </div>
      </div>
    );
  }

  const done = checkIn.data;
  if (done) {
    const a = done.attendance;
    return (
      <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
        <div className="card state">
          <span className="stamp stamp--lg">
            {done.was_new ? '출석' : '확인'}
            <small>{done.was_new ? 'CHECKED' : 'ALREADY'}</small>
          </span>
          <p className="eyebrow">
            {done.was_new && a.is_met
              ? '하나의 순간이 남았어요'
              : done.was_new
                ? '체크인이 기록됐어요'
                : '이미 이 회차를 찍었습니다'}
          </p>
          <h2 style={{ textAlign: 'center' }}>{a.title}</h2>
          <p className="figure tabular" style={{ textAlign: 'center' }}>
            {a.checked} / {a.required}
            <small>체크인</small>
          </p>
          {a.is_met ? (
            <div className="notice notice--ok">
              <span>✓</span>
              <span>
                출석 인정 기준을 채웠습니다.
                {a.grants_excused_absence && ' 공결 명단에 올라갑니다.'}
              </span>
            </div>
          ) : (
            <p className="lede" style={{ textAlign: 'center' }}>
              {a.remaining}번 더 찍어야 출석으로 인정됩니다. 자리를 지켜 주세요.
            </p>
          )}
          <Link to={`/join/${id}`} className="btn btn--primary btn--lg">
            닫기
          </Link>
          <Link to={`/join/${id}/lectures`} className="btn btn--ghost">
            출결 자세히 보기
          </Link>
        </div>
      </div>
    );
  }

  const err = checkIn.error instanceof ApiError ? checkIn.error : null;
  if (err) {
    const closed = err.code === 'CHECKPOINT_CLOSED';
    return (
      <Fail
        id={id}
        title={closed ? '체크인 시간이 지났습니다' : '이 QR 로는 출석되지 않습니다'}
        body={err.message}
        // 닫힌 것은 기다리면 되고, 위조는 기다려도 안 된다.
        waitable={closed}
      />
    );
  }

  return (
    <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
      <div className="card state">
        <p className="eyebrow">출석을 기록하는 중…</p>
        <div className="skeleton" style={{ height: 60, width: '100%' }} />
      </div>
    </div>
  );
}

function Fail({
  id,
  title,
  body,
  waitable = false,
}: {
  id: string;
  title: string;
  body: string;
  waitable?: boolean;
}) {
  return (
    <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
      <div className="card state">
        <p className="eyebrow">{title}</p>
        <p className="lede" style={{ textAlign: 'center' }}>{body}</p>
        {waitable && (
          <p className="muted" style={{ textAlign: 'center' }}>
            체크인은 강의 중 여러 번 열립니다. 자리를 지키고 다음 QR 을 기다려 주세요.
          </p>
        )}
        <Link to={`/join/${id}/lectures`} className="btn btn--primary btn--lg">
          내 출결 보기
        </Link>
      </div>
    </div>
  );
}
