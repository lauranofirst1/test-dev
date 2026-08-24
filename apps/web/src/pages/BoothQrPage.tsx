/** 부스에 띄워 두는 회전 QR 화면 — 계약 §8.2.
 *
 * 관객이 찍을 QR 을 실제로 보여주는 화면이 없어서, 지금까지 `participant_scan`
 * 부스는 스캔할 대상이 없었습니다. 토큰 엔드포인트만 있고 그리는 곳이 없었던
 * 셈입니다. 이 화면이 그 자리입니다.
 *
 * 부스는 두 모드 중 하나입니다 — 기획서 E4.
 *
 * - **인쇄(기본)** — 고정 서명 하나. 한 번 띄워 인쇄해 붙이면 끝입니다. 천막
 *   부스에 태블릿도 전원도 없는 것이 보통이라 이쪽이 기본입니다. 이 화면은
 *   갱신하지 않고, 인쇄 화면으로 가는 길만 안내합니다.
 * - **회전(상위)** — 30초마다 바뀝니다. 서버가 준 `expires_at` 까지 기다렸다가
 *   다시 받아옵니다. 화면이 스스로 30초를 세면 서버 시계와 어긋나 만료된 QR 을
 *   띄운 채로 서 있게 됩니다. 그 상태의 부스는 아무도 지급받지 못하는데
 *   화면만 멀쩡해 보여서, 현장에서 원인을 찾기가 가장 어렵습니다.
 *
 * 부스 태블릿은 종일 켜 두는 화면이라 어둡게 두지 않습니다. 야외에서 QR 을
 * 읽히려면 흰 바탕에 검은 코드가 가장 확실합니다.
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';
import { Link, useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { BoothList, ScanTokenOut } from '../api/types';

export function BoothQrPage() {
  const { id = '', boothId = '' } = useParams<{ id: string; boothId: string }>();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);

  const booths = useQuery({
    queryKey: ['booths', id],
    queryFn: () => api.get<BoothList>(`/api/festivals/${id}/booths`),
    retry: false,
  });
  const booth = booths.data?.items.find((b) => String(b.id) === boothId);

  const token = useQuery({
    queryKey: ['scan-token', id, boothId],
    queryFn: () => api.get<ScanTokenOut>(`/api/festivals/${id}/booths/${boothId}/scan-token`),
    retry: false,
    // 서버가 알려준 갱신 시점을 그대로 쓴다. 화면이 직접 세지 않는다.
    // 인쇄 QR 은 `expires_at` 이 없다 — 다시 받을 일이 없으므로 폴링하지 않는다.
    refetchInterval: (q) => {
      const data = q.state.data as ScanTokenOut | undefined;
      if (!data) return 5_000;
      if (!data.expires_at) return false;
      const ms = new Date(data.expires_at).getTime() - Date.now();
      // 만료 직전에 받으면 그리는 사이에 이미 지난 QR 이 된다. 조금 일찍 받는다.
      return Math.max(1_000, ms - 500);
    },
    refetchIntervalInBackground: true,
  });

  // 남은 시간 표시. 스태프가 "지금 화면이 살아 있나"를 눈으로 확인하는 유일한 단서다.
  // 인쇄 QR 에는 남은 시간이 없다.
  useEffect(() => {
    const expires = token.data?.expires_at;
    if (!expires) {
      setSecondsLeft(null);
      return;
    }
    const tick = () =>
      setSecondsLeft(Math.max(0, Math.ceil((new Date(expires).getTime() - Date.now()) / 1000)));
    tick();
    const timer = setInterval(tick, 250);
    return () => clearInterval(timer);
  }, [token.data]);

  // 서버의 `scan_url` 을 쓰지 않는다. 그건 요청이 도착한 주소(=API 서버)로
  // 만들어져서 개발 환경에서는 :8000 을 가리키고, 거기엔 `/join` 라우트가 없다.
  // 이 화면을 띄운 브라우저의 오리진이 곧 관객이 접속할 오리진이다 —
  // localhost 든 사내망 IP 든 운영 도메인이든 그대로 맞는다.
  const scanUrl = token.data ? window.location.origin + token.data.scan_path : '';

  useEffect(() => {
    if (!token.data || !canvas.current) return;
    // qrcode 가 인라인 style 로 크기를 박아 CSS 를 이긴다. 그리고 나서 걷어낸다.
    QRCode.toCanvas(canvas.current, scanUrl, {
      width: 520,
      margin: 1,
      errorCorrectionLevel: 'M',
      color: { dark: '#000000', light: '#FFFFFF' },
    }).then(() => {
      canvas.current?.style.removeProperty('width');
      canvas.current?.style.removeProperty('height');
    }).catch(() => {
      /* 그리기 실패는 다음 갱신에서 자연히 복구된다 */
    });
  }, [token.data, scanUrl]);

  const err = token.error instanceof ApiError ? token.error : null;
  const printed = token.data?.qr_mode === 'printed';

  return (
    <div className="boothqr">
      <div className="boothqr__head">
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">부스 QR</p>
          <h1 style={{ fontSize: 'var(--text-h2)' }}>{booth?.name ?? `부스 ${boothId}`}</h1>
          {token.data && (
            <span className="badge badge--none">
              {printed ? '인쇄 QR · 바뀌지 않음' : '회전 QR · 30초마다 갱신'}
            </span>
          )}
        </div>
        <Link to={`/festivals/${id}/booths`} className="btn btn--ghost">
          ← 부스 관리
        </Link>
      </div>

      {err && (
        <div className="card state">
          <p className="eyebrow">QR 을 만들 수 없습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>{err.message}</p>
          {err.code === 'BOOTH_MODE_MISMATCH' && (
            <p className="muted" style={{ textAlign: 'center' }}>
              부스 관리에서 확인 방식을 <b>QR 스캔</b>으로 바꾸면 이 화면을 쓸 수 있습니다.
            </p>
          )}
        </div>
      )}

      {!err && (
        <>
          <div className="boothqr__code">
            <canvas ref={canvas} aria-label="부스 QR 코드" />
          </div>

          <p className="boothqr__guide">휴대폰 카메라로 이 QR을 찍어 주세요</p>

          {printed ? (
            <div className="stack" style={{ gap: 'var(--space-3)', alignItems: 'center' }}>
              <p className="muted">
                이 QR은 <b>바뀌지 않습니다.</b> 인쇄해서 부스에 붙여 두면 됩니다.
              </p>
              <Link
                to={`/festivals/${id}/booths/${boothId}/poster`}
                className="btn btn--primary btn--lg"
              >
                인쇄용 안내문 열기 ↗
              </Link>
            </div>
          ) : (
            <p className="muted tabular">
              {secondsLeft === null
                ? 'QR을 불러오는 중…'
                : `${secondsLeft}초 뒤 자동으로 바뀝니다`}
            </p>
          )}

          {/* 스캔이 안 되는 폰을 위한 대비책. 현장에서 카메라가 말을 안 듣는 일은
              반드시 생기고, 그때 부스가 할 수 있는 게 없으면 줄이 멈춘다. */}
          {token.data && (
            <details className="boothqr__fallback">
              <summary>QR이 안 찍히면</summary>
              <p className="muted">이 주소를 관객 폰 브라우저에 직접 입력하게 하세요.</p>
              <code className="joinurl">{scanUrl}</code>
            </details>
          )}
        </>
      )}
    </div>
  );
}
