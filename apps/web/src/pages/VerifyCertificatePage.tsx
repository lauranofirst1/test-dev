/** 공결 확인 — 교수님이 보는 화면.
 *
 * **이 화면의 사용자는 이 제품을 처음 봅니다.** 계정도, 사전 지식도 없습니다.
 * 학생이 코드나 QR 을 내밀었고, 교수님이 알고 싶은 것은 딱 하나입니다 —
 * "이 학생이 그 시간에 정말 있었나."
 *
 * 그래서 판정을 가장 크게, 맨 위에 둡니다. 근거(몇 번 중 몇 번)는 바로 아래
 * 두되 계산을 시키지 않습니다. FestaFlow 가 무엇인지는 설명하지 않습니다 —
 * 교수님은 우리 제품을 알고 싶은 게 아닙니다.
 *
 * **이 결과는 스냅샷이 아닙니다.** 지금 조회한 값이라, 출결이 정정되면 이
 * 화면도 함께 바뀝니다. 종이 확인서가 옛 사실을 말하는 문제가 없습니다.
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { CertificateVerified } from '../api/types';

const when = (iso: string) =>
  new Date(iso).toLocaleString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

export function VerifyCertificatePage() {
  const { id = '', code = '' } = useParams<{ id: string; code: string }>();

  const cert = useQuery({
    queryKey: ['certificate', id, code],
    queryFn: () =>
      api.get<CertificateVerified>(`/api/festivals/${id}/attendance-certificates/${code}`),
    retry: false,
  });

  useEffect(() => {
    document.title = '출석 확인';
  }, []);

  const d = cert.data;
  const notFound = cert.error instanceof ApiError && cert.error.status === 404;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-5)', maxWidth: 560 }}>
      {cert.isLoading && <div className="skeleton" style={{ height: 220 }} />}

      {notFound && (
        <div className="card stack" style={{ gap: 'var(--space-3)' }}>
          <h1 style={{ fontSize: 'var(--text-h2)', fontWeight: 800 }}>확인할 수 없습니다</h1>
          <p>
            이 확인 코드는 유효하지 않습니다. 학생에게 코드를 다시 받아 주세요.
            링크가 잘리거나 잘못 옮겨 적혔을 수 있습니다.
          </p>
        </div>
      )}

      {d && (
        <>
          {/* ── 판정이 가장 크다. 교수님이 알고 싶은 것은 이것 하나다 ── */}
          <div className="verdict" data-met={d.is_met}>
            <span className="verdict__icon" aria-hidden>
              {d.is_met ? '✓' : '✕'}
            </span>
            <strong className="verdict__text">
              {d.is_met ? '출석 인정' : '출석 미달'}
            </strong>
            <span className="verdict__sub">
              열린 확인 {d.opened}회 중 {d.checked}회 참여 (기준 {d.required}회)
            </span>
          </div>

          {!d.grants_excused_absence && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>
                <strong>이 특강은 공결 대상이 아닙니다.</strong> 참석 사실만 확인됩니다.
              </span>
            </div>
          )}

          <div className="card stack" style={{ gap: 'var(--space-3)' }}>
            <div className="stack" style={{ gap: 2 }}>
              <p className="eyebrow">특강</p>
              <strong style={{ fontSize: 'var(--text-h3)' }}>{d.title}</strong>
              <p className="muted">
                {d.speaker ? `${d.speaker} · ` : ''}
                {when(d.starts_at)} ~ {new Date(d.ends_at).toLocaleTimeString('ko-KR', {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </p>
              <p className="muted">{d.festival_name}</p>
            </div>

            <div className="stack" style={{ gap: 2 }}>
              <p className="eyebrow">학생</p>
              {/* 명단 수집이 아니라 본인 확인이 목적이라 뒷 세 자리만 보여준다. */}
              <strong className="tabular">{d.student_no_masked ?? '학번 미등록'}</strong>
              <p className="muted tabular">참여 코드 {d.participant_code}</p>
            </div>
          </div>

          {/* 어떻게 확인된 것인지 한 줄로 밝힌다. 교수님이 이 화면을 신뢰할지
              판단할 근거가 있어야 한다. */}
          <p className="disclaimer">
            강의 중 예고 없이 열린 확인 시점마다 학생이 현장에서 QR 을 찍은 기록입니다.
            입장 스캔 한 번이 아니라 여러 번의 확인이므로 중간에 자리를 뜨면 채워지지
            않습니다. {new Date(d.verified_at).toLocaleString('ko-KR')} 기준으로 조회했으며,
            출결이 정정되면 이 화면도 함께 바뀝니다.
          </p>
        </>
      )}
    </div>
  );
}
