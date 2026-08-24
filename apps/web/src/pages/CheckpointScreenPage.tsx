/** 강의실 스크린에 띄우는 체크인 QR — 프로젝터용 전체화면.
 *
 * **QR 이 회전합니다.** 부스 지급에서는 인쇄 QR 이 합리적인 선택지였지만
 * 출결에서는 아닙니다 — 고정 QR 사진 한 장이 단톡방에 돌면 강의실 밖에서도
 * 출석이 찍히고, 공결이 걸린 강의에서 그건 기능이 아예 없는 것과 같습니다.
 *
 * 체크인은 90초만 열립니다. 닫히면 화면이 그 사실을 크게 말합니다 — 멀쩡해
 * 보이는 QR 을 계속 띄워 두면 학생들이 찍고도 실패하는 상황이 반복됩니다.
 *
 * 멀리서 읽어야 하므로 QR 을 화면 높이에 맞춰 키우고, 남은 시간을 큰 숫자로
 * 함께 둡니다.
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';
import { Link, useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { CheckpointToken, LectureSessionList } from '../api/types';

export function CheckpointScreenPage() {
  const {
    id = '',
    sessionId = '',
    checkpointId = '',
  } = useParams<{ id: string; sessionId: string; checkpointId: string }>();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [left, setLeft] = useState<number | null>(null);

  const lectures = useQuery({
    queryKey: ['lectures', id],
    queryFn: () => api.get<LectureSessionList>(`/api/festivals/${id}/lectures`),
    retry: false,
  });
  const session = lectures.data?.items.find((s) => String(s.id) === sessionId);

  const token = useQuery({
    queryKey: ['checkpoint-token', id, sessionId, checkpointId],
    queryFn: () =>
      api.get<CheckpointToken>(
        `/api/festivals/${id}/lectures/${sessionId}/checkpoints/${checkpointId}/token`,
      ),
    retry: false,
    // 서버가 알려준 갱신 시점을 그대로 쓴다. 화면이 30초를 직접 세면 서버 시계와
    // 어긋나 만료된 QR 을 띄운 채로 서 있게 된다.
    refetchInterval: (q) => {
      const data = q.state.data as CheckpointToken | undefined;
      if (!data) return 3_000;
      if (new Date(data.closes_at).getTime() <= Date.now()) return false;
      return Math.max(1_000, new Date(data.expires_at).getTime() - Date.now() - 500);
    },
    refetchIntervalInBackground: true,
  });

  // 체크인이 닫히기까지 남은 시간. 학생들이 보고 서두를 수 있어야 한다.
  useEffect(() => {
    const closes = token.data?.closes_at;
    if (!closes) return;
    const tick = () =>
      setLeft(Math.max(0, Math.ceil((new Date(closes).getTime() - Date.now()) / 1000)));
    tick();
    const timer = setInterval(tick, 250);
    return () => clearInterval(timer);
  }, [token.data]);

  const scanUrl = token.data ? window.location.origin + token.data.scan_path : '';
  const closed = left === 0;

  useEffect(() => {
    if (!scanUrl || !canvas.current || closed) return;
    QRCode.toCanvas(canvas.current, scanUrl, {
      width: 900,
      margin: 1,
      errorCorrectionLevel: 'M',
      color: { dark: '#000000', light: '#FFFFFF' },
    })
      .then(() => {
        // qrcode 가 인라인 style 로 크기를 박아 CSS 를 이긴다. 걷어낸다.
        canvas.current?.style.removeProperty('width');
        canvas.current?.style.removeProperty('height');
      })
      .catch(() => {});
  }, [scanUrl, closed]);

  const err = token.error instanceof ApiError ? token.error : null;

  return (
    <div className="checkscreen">
      <div className="checkscreen__head">
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">
            체크인 {token.data ? `${token.data.sequence}회차` : ''}
          </p>
          <h1 className="checkscreen__title">{session?.title ?? '특강'}</h1>
        </div>
        <Link to={`/festivals/${id}/lectures`} className="btn btn--ghost">
          ← 특강 관리
        </Link>
      </div>

      {err && (
        <div className="card state">
          <p className="eyebrow">QR 을 만들 수 없습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>{err.message}</p>
        </div>
      )}

      {!err && closed && (
        <div className="checkscreen__closed">
          <p className="checkscreen__big">체크인이 끝났습니다</p>
          <p className="muted">
            다음 체크인은 특강 관리 화면에서 다시 여세요. 만료된 QR 을 계속 띄워 두면
            학생들이 찍고도 실패합니다.
          </p>
          <Link to={`/festivals/${id}/lectures`} className="btn btn--primary btn--lg">
            특강 관리로
          </Link>
        </div>
      )}

      {!err && !closed && (
        <>
          <div className="checkscreen__qr">
            <canvas ref={canvas} aria-label="체크인 QR 코드" />
          </div>
          <p className="checkscreen__big">지금 QR 을 찍어 주세요</p>
          <p className="checkscreen__timer tabular">
            {left === null ? '…' : `${left}초 남음`}
          </p>
          {/* 이 QR 은 30초마다 바뀐다. 사진을 찍어 두어도 소용없다는 사실을
              화면이 직접 말한다 — 시도 자체를 줄인다. */}
          <p className="muted">QR 은 30초마다 바뀝니다. 사진으로는 출석되지 않습니다.</p>
        </>
      )}
    </div>
  );
}
