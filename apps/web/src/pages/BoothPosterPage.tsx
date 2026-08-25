/** 부스 인쇄용 안내문 — 종이에 뽑아 부스에 붙인다. 계약 §14.4, 기획서 E4.
 *
 * 계약은 `GET /booths/{bid}/qr.pdf` 로 PDF 를 내려주게 돼 있지만, 서버에서
 * PDF 를 만들려면 렌더링 스택이 하나 더 붙습니다. 브라우저 인쇄가 같은 결과를
 * 내고 지금 바로 쓸 수 있으므로 인쇄용 화면을 먼저 둡니다 — A4 한 장에 맞춰
 * 놓았고, 브라우저의 "PDF로 저장"이 그대로 §14.4 의 산출물이 됩니다.
 *
 * **화면용 장식을 인쇄에 남기지 않습니다.** 배경색, 그림자, 버튼은 잉크를 먹고
 * 흑백 출력에서 QR 주변을 지저분하게 만듭니다. `@media print` 에서 전부 뺍니다.
 *
 * 축제 여러 부스를 한 번에 뽑을 수 있게 `?all=1` 로 전 부스를 이어 붙입니다.
 * 부스가 여섯이면 여섯 번 인쇄 화면을 여는 것이 현장 준비에서 실제 부담입니다.
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import QRCode from 'qrcode';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { api } from '../api/client';
import type { BoothDetail, BoothList, FestivalDetail, ScanTokenOut } from '../api/types';

/** QR 을 캔버스에 그리고 **인라인 크기를 걷어낸다.**
 *
 * `qrcode` 는 `options.width` 를 캔버스의 인라인 style 에도 박습니다. 인라인은
 * 스타일시트를 이기므로, CSS 로 정한 표시 크기가 무시되고 비트맵 크기가 그대로
 * 화면 크기가 됩니다(900px 짜리가 카드를 뚫고 나옵니다).
 *
 * 비트맵은 크게, 표시는 CSS 가 정하게 — 인쇄에서 선명하려면 비트맵이 커야 하고,
 * 화면에서는 카드 안에 들어와야 합니다.
 */
async function paintQr(
  canvas: HTMLCanvasElement,
  url: string,
  options: Parameters<typeof QRCode.toCanvas>[2],
): Promise<void> {
  await QRCode.toCanvas(canvas, url, options);
  canvas.style.removeProperty('width');
  canvas.style.removeProperty('height');
}

export function BoothPosterPage() {
  const { id = '', boothId = '' } = useParams<{ id: string; boothId?: string }>();
  const [params] = useSearchParams();
  const all = params.get('all') === '1';

  const festival = useQuery({
    queryKey: ['festival', id],
    queryFn: () => api.get<FestivalDetail>(`/api/festivals/${id}`),
  });

  const booths = useQuery({
    queryKey: ['booths', id],
    queryFn: () => api.get<BoothList>(`/api/festivals/${id}/booths`),
  });

  // QR 을 붙일 수 있는 부스만. 스태프 확인 부스는 찍을 QR 자체가 없다.
  const scannable = (booths.data?.items ?? []).filter(
    (b) => b.verify_mode === 'participant_scan' && b.is_active,
  );
  const targets = all ? scannable : scannable.filter((b) => String(b.id) === boothId);

  return (
    <div className="poster">
      {/* 인쇄에는 나가지 않는 조작부. */}
      <div className="poster__bar">
        <div className="row" style={{ gap: 'var(--space-3)' }}>
          {!all && scannable.length > 1 && (
            <Link to={`/festivals/${id}/booths/poster?all=1`} className="btn btn--ghost">
              전 부스 한 번에
            </Link>
          )}
          <button className="btn btn--primary" onClick={() => window.print()}>
            인쇄 / PDF 저장
          </button>
        </div>
      </div>

      {targets.length === 0 && (
        <div className="card state">
          <p className="eyebrow">인쇄할 부스가 없습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            QR 스캔 방식으로 설정된 활성 부스만 안내문을 만들 수 있습니다.
          </p>
        </div>
      )}

      {targets.map((booth) => (
        <PosterSheet
          key={booth.id}
          festivalId={id}
          booth={booth}
          festivalName={festival.data?.name ?? ''}
        />
      ))}
    </div>
  );
}

function PosterSheet({
  festivalId,
  booth,
  festivalName,
}: {
  festivalId: string;
  booth: BoothDetail;
  festivalName: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);

  const token = useQuery({
    queryKey: ['scan-token', festivalId, booth.id],
    queryFn: () =>
      api.get<ScanTokenOut>(`/api/festivals/${festivalId}/booths/${booth.id}/scan-token`),
    retry: false,
  });

  // 서버의 scan_url 이 아니라 이 브라우저의 오리진을 쓴다 — 관객이 접속할
  // 주소가 곧 이 화면을 연 주소다.
  const scanUrl = token.data ? window.location.origin + token.data.scan_path : '';

  useEffect(() => {
    if (!scanUrl || !canvas.current) return;
    paintQr(canvas.current, scanUrl, {
      // 인쇄물은 확대·축소되고 빛도 고르지 않다. 오류 정정을 높게 잡는다 —
      // 종이가 구겨지거나 일부가 가려져도 읽힌다.
      errorCorrectionLevel: 'H',
      width: 900,
      margin: 2,
      color: { dark: '#000000', light: '#FFFFFF' },
    }).catch(() => {});
  }, [scanUrl]);

  const rotating = token.data?.qr_mode === 'rotating';

  return (
    <article className="sheet">
      <header className="sheet__head">
        <p className="sheet__festival">{festivalName}</p>
        <h1 className="sheet__booth">{booth.name}</h1>
        {(booth.type_label || booth.location) && (
          <p className="sheet__where">
            {[booth.type_label, booth.location].filter(Boolean).join(' · ')}
          </p>
        )}
      </header>

      <div className="sheet__qr">
        <canvas ref={canvas} aria-label={`${booth.name} 참여 QR 코드`} />
      </div>

      <p className="sheet__cta">휴대폰 카메라로 QR을 찍어 주세요</p>
      <p className="sheet__sub">부스를 돌면 축제 그림이 한 조각씩 열립니다</p>

      {/* QR 이 안 찍히는 폰은 반드시 나온다. 그때 부스가 할 수 있는 게 없으면
          줄이 멈춘다. 주소를 함께 인쇄해 손으로 입력할 수 있게 한다. */}
      <p className="sheet__url">{scanUrl}</p>

      {rotating && (
        <p className="sheet__warn">
          ⚠ 이 부스는 <b>회전 QR</b> 설정입니다. 인쇄물의 QR은 30초 뒤 만료됩니다.
          인쇄해서 붙이려면 부스 설정을 <b>인쇄 QR</b>로 바꾸고 다시 뽑으세요.
        </p>
      )}

      {/* 규정상 화면과 인쇄물 모두에 출처를 표기한다. */}
      <footer className="sheet__foot">출처: ⓒ한국관광공사</footer>
    </article>
  );
}
