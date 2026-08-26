/** 부스 지급 화면 — 스펙 §8.1. 축제 당일 8시간 내내 열려 있는 화면.
 *
 * ## 이 화면의 유일한 일
 *
 * **줄 서 있는 사람을 빠르게 처리한다.** 다른 모든 것은 그다음입니다. 그래서
 * 입력칸과 미션 버튼이 화면의 대부분을 차지하고, 설정·통계·링크는 아래로
 * 밀거나 아예 없습니다.
 *
 * ## 통신이 끊겨도 멈추지 않는다
 *
 * 지급은 로컬 큐에 쌓였다가 복구되면 나갑니다(lib/grantQueue.ts). 스태프에게는
 * 즉시 성공으로 답합니다 — 줄이 서 있는데 "전송 중…" 이 돌면 그 부스는
 * 마비됩니다.
 *
 * 대신 **큐에 몇 건이 남았는지를 항상 보여줍니다.** "보낸 줄 알았는데 안 갔다"
 * 가 현장에서 제일 위험합니다.
 *
 * ## 참여자가 스스로 완료할 수 없다는 원칙
 *
 * 이 화면은 스태프 토큰으로만 열립니다. 미션 수행을 눈으로 확인한 사람이
 * 지급을 누릅니다 — 그게 `staff_scan` 모드의 현장 확인 근거 전부입니다.
 *
 * ## 부스마다 화면이 갈린다
 *
 * `participant_scan` 부스에서는 스태프가 지급하지 않습니다. 참여자가 부스 QR 을
 * 찍고 스스로 미션을 고릅니다. 그런 부스에 지급 버튼을 띄우면 스태프가 누르고
 * `409 BOOTH_MODE_MISMATCH` 를 받습니다 — 화면이 할 수 없는 일을 권한 셈이고,
 * 현장에서는 "고장 났다" 로 읽힙니다.
 */

import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { api } from '../api/client';
import { loadBooths, saveBooths } from '../lib/boothCache';
import { getGrantQueue } from '../lib/grantQueue';
import type { QueueSnapshot } from '../lib/grantQueue';
import { extractParticipantCode, scannerSupported, startScanner } from '../lib/scanner';
import type { BoothList, RecentGrant, StaffMe } from '../api/types';

/** 지급 결과를 띄워 두는 시간. 줄이 빠르면 다음 사람이 바로 오므로 짧게. */
const FLASH_MS = 2_600;

interface Flash {
  kind: 'ok' | 'dup' | 'error';
  code: string;
  mission: string;
  message: string;
  queued: boolean;
}

export function BoothGrantPage() {
  const { id = '' } = useParams<{ id: string }>();
  const queue = getGrantQueue(id);

  const [boothId, setBoothId] = useState<number | null>(null);
  const [code, setCode] = useState('');
  const [flash, setFlash] = useState<Flash | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<QueueSnapshot>(() => queue.snapshot());

  const video = useRef<HTMLVideoElement>(null);
  const codeInput = useRef<HTMLInputElement>(null);

  useEffect(() => queue.subscribe(setSnapshot), [queue]);
  useEffect(() => queue.listen(), [queue]);

  // 큐가 응답을 받으면 그때 진짜 결과를 알려준다. 성공은 이미 보여줬으므로
  // 덮어쓰지 않고, **문제가 있을 때만** 화면을 바꾼다 — 잘 되고 있는데 화면이
  // 계속 깜빡이면 스태프가 결과를 읽지 않게 된다.
  useEffect(
    () =>
      queue.onOutcome((outcome) => {
        if (outcome.kind === 'ok') {
          void recent.refetch();
          return;
        }
        show({
          kind: outcome.kind === 'duplicate' ? 'dup' : 'error',
          code: outcome.item.participantCode,
          mission: outcome.item.missionTitle,
          message: outcome.message,
          queued: false,
        });
      }),
    // show 와 recent 는 렌더마다 새로 만들어지지만, 구독은 한 번이면 된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queue],
  );

  // 누가 로그인했는지. booth_manager 면 배정된 부스 하나로 고정된다.
  const session = useQuery({
    queryKey: ['staff-me', id],
    queryFn: () => api.get<StaffMe>('/api/auth/staff/me'),
    retry: false,
  });

  const festival = useQuery({
    queryKey: ['public', id],
    queryFn: () => api.get<{ name: string }>(`/api/festivals/${id}/public`),
    retry: false,
    staleTime: 5 * 60_000,
  });

  const booths = useQuery({
    queryKey: ['booths', id],
    queryFn: async () => {
      const list = await api.get<BoothList>(`/api/festivals/${id}/booths`);
      // 받을 때마다 저장한다. 다음에 통신이 끊긴 채로 화면이 떠도
      // 미션 버튼이 보여야 큐에 넣을 수 있다.
      saveBooths(id, list.items);
      return list;
    },
    retry: false,
  });

  // 서버를 못 받았을 때만 캐시를 쓴다. 캐시를 먼저 쓰면 부스를 중지했는데도
  // 옛 목록이 그대로 떠서, 스태프가 닫힌 부스에 계속 지급하게 된다.
  const cached = booths.data ? null : loadBooths(id);

  const recent = useQuery({
    queryKey: ['recent-grants', id, boothId],
    queryFn: () =>
      api.get<RecentGrant[]>(`/api/festivals/${id}/booths/${boothId}/grants/recent?limit=8`),
    enabled: boothId !== null,
    // 큐가 늦게 도착한 건까지 보이도록 주기적으로 다시 본다.
    refetchInterval: 20_000,
    retry: false,
  });

  const active = (booths.data?.items ?? cached?.items ?? []).filter((b) => b.is_active);

  // 부스가 정해지지 않았으면 고른다. booth_manager 는 배정된 하나뿐이라
  // 선택 UI 자체가 나타나지 않는다.
  //
  // **세션 조회가 끝나기를 기다린다.** 두 조회는 경주하는데, 부스 목록이 먼저
  // 오면 배정 정보 없이 첫 부스를 골라 버리고 그 뒤로 다시 고르지 않는다.
  // 그러면 부스관리자가 **남의 부스에 착지하고, 선택 UI 는 숨겨져 있어 고칠
  // 수도 없다.** 지급을 누르면 403 이 나는데 화면에는 이유가 없다.
  //
  // `isPending` 이 풀리면 실패했더라도(스태프 토큰 없는 운영자) 결론이 난 것이라
  // 그때 고르면 된다.
  useEffect(() => {
    if (boothId !== null || active.length === 0 || session.isPending) return;
    const assigned = session.data?.booth_id;
    // 배정된 부스가 목록에 없으면(보관됐거나 중지됐다) 첫 부스로 떨어진다.
    const target = active.find((b) => b.id === assigned) ?? active[0];
    setBoothId(target.id);
  }, [boothId, active, session.data, session.isPending]);

  const booth = active.find((b) => b.id === boothId) ?? null;
  // 이 부스가 스태프 지급 방식인가. 아니면 참여자가 QR 을 찍는 부스다.
  const staffGrants = booth?.verify_mode === 'staff_scan';
  // 부스 상세가 미션을 함께 실어 온다. 활성 미션만 보여준다 — 중지된 미션을
  // 눌러 거절당하면 스태프도 참여자도 이유를 모른다.
  const missionItems = (booth?.missions ?? []).filter((m) => m.is_active);

  /** 지급을 큐에 넣는다. **네트워크를 기다리지 않는다.**
   *
   * 클릭 시점에 응답을 기다리면, 요청 하나가 멈추는 순간 버튼이 잠기고 그 부스는
   * 마비됩니다. 축제장에서 요청이 멈추는 건 예외가 아니라 기본값입니다.
   *
   * 그래서 항상 큐에 넣고 즉시 답합니다. 결과(중복·실패)는 큐가 응답을 받는
   * 대로 알려주고, 온라인에서는 대개 사람이 서 있는 동안 도착합니다.
   */
  const submit = (mission: { id: number; title: string }) => {
    const normalized = code.trim().toUpperCase();
    if (!normalized || boothId === null) return;

    queue.enqueue({
      boothId,
      missionId: mission.id,
      missionTitle: mission.title,
      participantCode: normalized,
    });

    show({
      kind: 'ok',
      code: normalized,
      mission: mission.title,
      message: navigator.onLine
        ? '보내는 중입니다. 문제가 있으면 바로 알려드립니다.'
        : '통신이 끊겨 있어 대기열에 넣었습니다. 복구되면 자동으로 전송됩니다.',
      queued: !navigator.onLine,
    });
    setCode('');
    codeInput.current?.focus();
  };

  const show = useCallback((next: Flash) => {
    setFlash(next);
    // 시끄럽고 밝은 야외다. 색만으로는 확인이 안 된다 — 진동을 함께 쓴다.
    // 실패는 길게 두 번, 성공은 짧게 한 번. 주머니에서도 구분된다.
    if ('vibrate' in navigator) {
      navigator.vibrate(next.kind === 'error' ? [90, 60, 90] : 40);
    }
    window.setTimeout(() => setFlash((f) => (f === next ? null : f)), FLASH_MS);
  }, []);

  // 스캐너. 켜져 있는 동안만 카메라를 잡고, 화면을 벗어나면 반드시 끈다 —
  // 카메라를 켜 둔 채 두면 배터리가 몇 시간 만에 바닥난다.
  useEffect(() => {
    if (!scanning || !video.current) return;
    let handle: { stop: () => void } | null = null;
    let cancelled = false;
    void startScanner(
      video.current,
      (raw) => setCode(extractParticipantCode(raw)),
      (message) => {
        setScanError(message);
        setScanning(false);
      },
    ).then((h) => {
      if (cancelled) h.stop();
      else handle = h;
    });
    return () => {
      cancelled = true;
      handle?.stop();
    };
  }, [scanning]);

  const ready = code.trim().length >= 4 && boothId !== null;
  const offline = !snapshot.online;
  const waiting = snapshot.pending.length;

  return (
    <div className="boothapp">
      {/* 이 화면에는 운영자 사이드바가 없다 — 부스 담당자는 오늘 하루 여기
          서 있는 사람이지 이 도구의 사용자가 아니다. 그렇다고 머리가 없으면
          "고장 난 페이지" 로 보인다. 지금 어느 축제 어느 부스인지, 그리고
          나가는 길만 담은 얇은 머리를 둔다. */}
      <header className="topbar boothbar">
        <div className="row" style={{ gap: 'var(--space-3)', minWidth: 0 }}>
          <span className="brand brand--plain">FestaFlow</span>
          <span className="boothbar__sep" aria-hidden>
            /
          </span>
          <span className="boothbar__where">
            {festival.data?.name ?? '축제'}
            {booth ? ` · ${booth.name}` : ''}
          </span>
        </div>
        <Link to={`/festivals/${id}/dashboard`} className="btn btn--ghost">
          오늘
        </Link>
      </header>

      <div className="shell stack" style={{ gap: 'var(--space-5)' }}>
      {/* ── 통신 상태는 항상 맨 위 ──
          "보낸 줄 알았는데 안 갔다" 가 현장에서 제일 위험하다. */}
      <div className="netbar" data-offline={offline} data-waiting={waiting > 0} role="status">
        <span aria-hidden>{offline ? '⚠' : waiting > 0 ? '◐' : '●'}</span>
        <span>
          {offline
            ? '통신이 끊겼습니다. 지급은 계속할 수 있고, 복구되면 자동으로 전송됩니다.'
            : waiting > 0
              ? `전송 대기 ${waiting}건`
              : '연결됨'}
        </span>
        {snapshot.dead.length > 0 && (
          <b className="netbar__dead">보내지 못한 {snapshot.dead.length}건</b>
        )}
      </div>

      {cached && (
        <div className="notice notice--info">
          <span>◐</span>
          <span>
            서버에서 부스 목록을 받지 못해 <strong>이 기기에 저장된 목록</strong>으로
            표시하고 있습니다
            {cached.at && ` (${new Date(cached.at).toLocaleString('ko-KR')} 기준)`}. 지급은
            그대로 되고, 연결이 돌아오면 대기열이 자동으로 전송됩니다. 그 사이 부스나
            미션이 바뀌었다면 여기 반영되지 않습니다.
          </span>
        </div>
      )}

      {snapshot.storageBroken && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>
            <strong>이 브라우저에 대기열을 저장할 수 없습니다.</strong> 통신이 끊기면 지급이
            사라질 수 있습니다. 시크릿 모드를 끄거나 저장 공간을 비워 주세요.
          </span>
        </div>
      )}

      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 2 }}>
          <p className="eyebrow">부스 지급</p>
          <h1 style={{ fontSize: 'var(--text-h2)', fontWeight: 800 }}>
            {booth?.name ?? '부스를 고르세요'}
          </h1>
          {booth && (
            <p className="muted">
              {booth.location ?? '위치 미지정'}
              {booth.manager_name ? ` · ${booth.manager_name}` : ''}
            </p>
          )}
        </div>
        {/* booth_manager 는 배정된 부스 하나뿐이라 선택 UI 가 나타나지 않는다. */}
        {active.length > 1 && !session.data?.booth_id && (
          <div className="field" style={{ minWidth: 180 }}>
            <label htmlFor="g-booth">부스</label>
            <select
              id="g-booth"
              value={boothId ?? ''}
              onChange={(e) => {
                setBoothId(Number(e.target.value));
                // 부스를 바꾸면 이전 결과와 코드를 지운다 — 남아 있으면
                // 다른 부스 미션을 그대로 누르게 된다.
                setCode('');
                setFlash(null);
              }}
            >
              {active.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* ── 참여자 스캔 부스에서는 스태프가 지급하지 않는다 ── */}
      {booth && !staffGrants && (
        <div className="card stack" style={{ gap: 'var(--space-4)' }}>
          <div className="notice notice--info">
            <span>ℹ</span>
            <span>
              <strong>이 부스는 참여자가 QR 을 찍습니다.</strong> 스태프가 코드를 받아
              지급하는 방식이 아니라, 참여자가 부스 QR 을 스캔하고 스스로 미션을 고릅니다.
            </span>
          </div>
          <p className="muted">
            {booth.qr_mode === 'printed'
              ? '인쇄된 QR 이 잘 보이는 자리에 붙어 있는지 확인해 주세요. 떨어졌다면 아래에서 다시 인쇄할 수 있습니다.'
              : '태블릿에 QR 화면을 띄워 두세요. 30초마다 자동으로 갱신됩니다.'}
          </p>
          <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
            {booth.qr_mode === 'rotating' ? (
              <Link
                to={`/festivals/${id}/booths/${booth.id}/qr`}
                className="btn btn--primary btn--lg"
              >
                QR 화면 띄우기
              </Link>
            ) : (
              <Link
                to={`/festivals/${id}/booths/${booth.id}/poster`}
                className="btn btn--primary btn--lg"
              >
                인쇄용 안내문 열기
              </Link>
            )}
          </div>
          {/* 지급 방식을 바꾸는 것은 운영자의 일이다. 여기서 바꿀 수 있게 하면
              부스마다 다른 사람이 다른 판단으로 바꾼다. */}
          <p className="muted">방식을 바꾸려면 운영자에게 요청하세요.</p>
        </div>
      )}

      {/* ── 결과는 입력칸 바로 위. 눈이 가는 자리다 ── */}
      {flash && (
        <div className="flash" data-kind={flash.kind} role="status" aria-live="assertive">
          <span className="flash__icon" aria-hidden>
            {flash.kind === 'ok' ? '✓' : flash.kind === 'dup' ? '!' : '✕'}
          </span>
          <div className="flash__text">
            <strong>
              {flash.kind === 'ok'
                ? flash.queued
                  ? '대기열에 넣었습니다'
                  : '지급 완료'
                : flash.kind === 'dup'
                  ? '이미 받았습니다'
                  : '지급 실패'}
            </strong>
            <span>
              {flash.code}
              {flash.mission ? ` · ${flash.mission}` : ''}
            </span>
            <span className="muted">{flash.message}</span>
          </div>
        </div>
      )}

      {/* ── 입력 ── */}
      {staffGrants && (
      <div className="card stack" style={{ gap: 'var(--space-3)' }}>
        <div className="field">
          <label htmlFor="g-code">참여 코드</label>
          <input
            ref={codeInput}
            id="g-code"
            className="codeinput"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="FF-XXXXXXXX"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={32}
            inputMode="text"
          />
          {/* 카메라는 되면 좋은 것이다. 수동 입력이 언제나 함께 있다. */}
          <div className="row wrap" style={{ gap: 'var(--space-2)', marginTop: 6 }}>
            {scannerSupported() && (
              <button className="btn btn--ghost" onClick={() => setScanning((v) => !v)}>
                {scanning ? '카메라 끄기' : '카메라로 스캔'}
              </button>
            )}
            {code && (
              <button className="btn btn--ghost" onClick={() => setCode('')}>
                지우기
              </button>
            )}
          </div>
          {scanError && <p className="muted">{scanError}</p>}
        </div>

        {scanning && (
          <video
            ref={video}
            className="scanview"
            muted
            playsInline
            aria-label="참여자 QR 카메라"
          />
        )}
      </div>
      )}

      {/* ── 미션 버튼 ── */}
      {staffGrants && (
      <div className="card stack" style={{ gap: 'var(--space-3)' }}>
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <h2 className="section">미션</h2>
          <span className="muted">수행을 확인한 뒤 눌러 주세요</span>
        </div>

        {missionItems.length === 0 ? (
          <p className="muted">이 부스에 열린 미션이 없습니다. 운영자에게 알려 주세요.</p>
        ) : (
          <div className="stack" style={{ gap: 'var(--space-2)' }}>
            {missionItems.map((m) => (
              <button
                key={m.id}
                className="missionbtn"
                // **전송 중이라고 잠그지 않는다.** 잠그면 요청 하나가 멈출 때
                // 부스 전체가 멈춘다. 큐가 순서를 지키므로 연타해도 안전하다.
                disabled={!ready}
                onClick={() => submit({ id: m.id, title: m.title })}
              >
                <span className="missionbtn__title">{m.title}</span>
                <span className="missionbtn__points tabular">+{m.points}점</span>
              </button>
            ))}
          </div>
        )}
        {!ready && (
          <p className="muted">참여 코드를 먼저 입력하면 지급 버튼이 켜집니다.</p>
        )}
      </div>
      )}

      {/* ── 보내지 못한 건은 사람이 처리한다 ── */}
      {snapshot.dead.length > 0 && (
        <div className="card stack" style={{ gap: 'var(--space-3)' }}>
          <h2 className="section">보내지 못한 지급</h2>
          <p className="muted">
            다시 보내도 같은 이유로 실패할 수 있습니다. 코드가 틀렸다면 참여자에게 다시
            물어보고 새로 지급해 주세요.
          </p>
          {snapshot.dead.map((d) => (
            <div key={d.clientRequestId} className="row wrap" style={{ justifyContent: 'space-between' }}>
              <div className="stack" style={{ gap: 2 }}>
                <strong>
                  {d.participantCode} · {d.missionTitle}
                </strong>
                <span className="muted">{d.lastError}</span>
              </div>
              <div className="row" style={{ gap: 'var(--space-2)' }}>
                <button className="btn btn--ghost" onClick={() => queue.retry(d.clientRequestId)}>
                  다시 보내기
                </button>
                <button className="btn btn--ghost" onClick={() => queue.discard(d.clientRequestId)}>
                  포기
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── 최근 지급 ── */}
      <div className="card stack" style={{ gap: 'var(--space-3)' }}>
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <h2 className="section">최근 지급</h2>
          <button className="btn btn--ghost" onClick={() => void recent.refetch()}>
            새로고침
          </button>
        </div>
        {(recent.data ?? []).length === 0 ? (
          <p className="muted">아직 지급 기록이 없습니다.</p>
        ) : (
          <div className="rcpt">
            {(recent.data ?? []).map((g) => (
              <div key={g.participation_id} className="rcpt__row">
                <span className="rcpt__name">
                  <strong>{g.participant_code}</strong>
                  <span>{g.mission_title ?? '미션 없음'}</span>
                </span>
                <span className="tabular">+{g.granted_points}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      </div>
    </div>
  );
}
