/** 내 출결 — 학생이 자기 출석 상태를 보는 화면.
 *
 * **몇 번을 놓쳤는지 보여줍니다.** 인정 여부만 보여주면 미달된 학생은 왜 미달인지
 * 모른 채 결과만 받게 되고, 이의를 제기할 근거도 없습니다. 열린 체크인 수와 내가
 * 찍은 수를 나란히 두면 스스로 계산할 수 있습니다.
 *
 * 다음 체크인이 언제인지는 **알려주지 않습니다.** 알려주는 순간 그 시각에만 자리에
 * 있으면 되고, 예고 없는 확인이라는 장치가 통째로 무의미해집니다.
 *
 * ## 확인서는 여기서 나온다
 *
 * 공결을 인정하는 사람은 특강 주최자가 아니라 **그 시간 정규 수업 담당 교수**
 * 입니다. 그 교수님에게 계정을 발급하는 절차는 만들어도 쓰이지 않습니다.
 * 대신 학생이 여기서 확인서를 열어 교수님께 보여줍니다 — QR 을 찍거나 코드를
 * 불러 주면 계정 없이 진위가 확인됩니다.
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';
import { Link, useParams } from 'react-router-dom';

import { ApiError } from '../api/client';
import { loadParticipant, participantApi } from '../api/participant';
import type { CertificateIssued, MyAttendance } from '../api/types';

export function MyLecturesPage() {
  const { id = '' } = useParams<{ id: string }>();
  const stored = loadParticipant(id);

  const mine = useQuery({
    queryKey: ['my-lectures', id, stored?.code],
    queryFn: () => participantApi.get<MyAttendance[]>(id, '/lectures/me', stored!.secret),
    enabled: !!stored,
    // 체크인이 열리면 이 화면이 그 사실을 모른다. 짧게 다시 물어본다.
    refetchInterval: 15_000,
    retry: false,
  });

  if (!stored) {
    return (
      <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
        <div className="card state">
          <p className="eyebrow">먼저 참여를 시작해 주세요</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            학번으로 참여를 시작하면 특강 출결이 기록됩니다.
          </p>
          <Link to={`/join/${id}`} className="btn btn--primary btn--lg">
            참여 시작하기
          </Link>
        </div>
      </div>
    );
  }

  const items = mine.data ?? [];

  return (
    <div className="shell stack" style={{ gap: 'var(--space-5)' }}>
      <div className="stack" style={{ gap: 4 }}>
        <p className="eyebrow">내 출결</p>
        <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>특강</h1>
      </div>

      {mine.isLoading && <div className="skeleton" style={{ height: 140 }} />}

      {mine.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{mine.error.message}</span>
        </div>
      )}

      {items.length === 0 && !mine.isLoading && (
        <div className="card state">
          <p className="eyebrow">아직 특강이 없습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            특강이 열리면 여기에 표시됩니다.
          </p>
        </div>
      )}

      {items.map((a) => (
        <AttendanceCard key={a.session_id} a={a} festivalId={id} secret={stored.secret} />
      ))}

      {items.length > 0 && (
        <p className="hint">
          체크인은 강의 중 <b>예고 없이</b> 열립니다. 언제 열릴지 미리 알려드리지 않으니
          자리를 지켜 주세요.
        </p>
      )}

      <Link to={`/join/${id}`} className="muted" style={{ textAlign: 'center' }}>
        내 조각 보기 →
      </Link>
    </div>
  );
}

function AttendanceCard({
  a,
  festivalId,
  secret,
}: {
  a: MyAttendance;
  festivalId: string;
  secret: string;
}) {
  const when = new Date(a.starts_at);
  const missed = Math.max(0, a.opened - a.checked);
  const [showCert, setShowCert] = useState(false);

  return (
    <div className="card stack" style={{ gap: 'var(--space-4)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div className="stack" style={{ gap: 4, minWidth: 0 }}>
          <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
            <h3 style={{ fontSize: 'var(--text-h3)' }}>{a.title}</h3>
            {a.grants_excused_absence && <span className="badge badge--caution">공결</span>}
          </div>
          <span className="muted tabular">
            {when.toLocaleString('ko-KR', {
              month: 'long',
              day: 'numeric',
              weekday: 'short',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
        {a.is_met ? (
          <span className="stamp">
            출석
            <small>MET</small>
          </span>
        ) : (
          <span className="badge badge--none tabular">
            {a.checked} / {a.required}
          </span>
        )}
      </div>

      {/* 진행 막대. 인정 기준까지 얼마나 남았는지가 이 화면에서 가장 중요한 사실이다. */}
      <div className="attbar" role="img" aria-label={`${a.required}회 중 ${a.checked}회 체크인`}>
        {Array.from({ length: a.required }, (_, i) => (
          <span key={i} className={`attbar__slot${i < a.checked ? ' attbar__slot--on' : ''}`}>
            {i < a.checked ? '✓' : i + 1}
          </span>
        ))}
      </div>

      {a.is_met ? (
        <p className="muted">
          출석 인정 기준을 채웠습니다.
          {a.grants_excused_absence && ' 공결 명단에 올라갑니다.'}
        </p>
      ) : (
        <p className="muted">
          {a.remaining}번 더 찍으면 인정됩니다.
          {/* 놓친 횟수를 숨기지 않는다. 미달 사유를 스스로 알아야 이의를 낼 수 있다. */}
          {missed > 0 && ` 지금까지 ${a.opened}번 열렸고 ${missed}번 놓쳤습니다.`}
        </p>
      )}

      {/* 확인서는 **찍은 기록이 있을 때만** 의미가 있다. 미달이어도 열 수 있게
          두는 이유는, 교수님이 "몇 번 왔는지" 를 보고 판단하는 경우가 있기
          때문이다 — 인정 여부는 학교가 정하지 우리가 정하지 않는다. */}
      {a.checked > 0 && (
        <>
          <button className="btn btn--ghost" onClick={() => setShowCert((v) => !v)}>
            {showCert ? '확인서 닫기' : '교수님께 보여줄 확인서'}
          </button>
          {showCert && (
            <Certificate festivalId={festivalId} sessionId={a.session_id} secret={secret} />
          )}
        </>
      )}
    </div>
  );
}

/** 교수님께 보여줄 확인서.
 *
 * QR 과 코드를 함께 둡니다 — 교수님이 폰을 꺼내기 어려운 상황이면 코드를 불러
 * 주고, 편하면 찍습니다. 어느 쪽도 막다른 길이 되지 않아야 합니다.
 *
 * **코드가 곧 비밀입니다.** 아는 사람은 누구나 이 출결을 봅니다. 화면이 그 사실을
 * 함께 말하지 않으면 학생은 단톡방에 올립니다.
 */
function Certificate({
  festivalId,
  sessionId,
  secret,
}: {
  festivalId: string;
  sessionId: number;
  secret: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [copied, setCopied] = useState(false);

  const cert = useQuery({
    queryKey: ['certificate', festivalId, sessionId],
    queryFn: () =>
      participantApi.get<CertificateIssued>(
        festivalId,
        `/lectures/${sessionId}/certificate`,
        secret,
      ),
    retry: false,
  });

  // 서버가 준 것은 **오리진 없는 경로**다. 브라우저가 자기 오리진을 붙이는 것이
  // 가장 정확하다 — 서버의 base_url 은 API 서버 주소라 교수님 폰에서 안 열린다.
  const url = cert.data ? `${window.location.origin}${cert.data.verify_path}` : '';

  useEffect(() => {
    if (!url || !canvas.current) return;
    void QRCode.toCanvas(canvas.current, url, { margin: 1, width: 220 }).then(() => {
      // qrcode 가 인라인 style 로 크기를 박아 CSS 를 이긴다. 걷어낸다.
      canvas.current?.style.removeProperty('width');
      canvas.current?.style.removeProperty('height');
    });
  }, [url]);

  if (cert.isLoading) return <div className="skeleton" style={{ height: 260 }} />;
  if (cert.error instanceof ApiError) {
    return (
      <div className="notice notice--warn">
        <span>⚠</span>
        <span>{cert.error.message}</span>
      </div>
    );
  }
  if (!cert.data) return null;

  return (
    <div className="cert stack">
      <p className="eyebrow">교수님께 이 화면을 보여주세요</p>
      <canvas ref={canvas} className="cert__qr" aria-label="출석 확인 QR" />
      <p className="cert__code tabular">{cert.data.code}</p>
      <p className="muted">QR 을 찍거나 위 코드를 불러 주시면 확인됩니다.</p>
      <button
        className="btn btn--ghost"
        onClick={() => {
          void navigator.clipboard?.writeText(url).then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          });
        }}
      >
        {copied ? '복사했습니다' : '링크 복사'}
      </button>
      {/* 이 경고가 없으면 학생은 단톡방에 올린다. */}
      <p className="disclaimer">
        이 코드를 아는 사람은 누구나 내 출결을 볼 수 있습니다. 확인이 필요한
        분에게만 보여주세요.
      </p>
    </div>
  );
}
