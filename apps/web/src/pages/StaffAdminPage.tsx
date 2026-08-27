/** 스태프 관리 — 발급 · 재발급 · 비활성화. 계약 §1.
 *
 * **평문 접근 코드는 발급 직후 한 번만 보입니다.** 저장되는 것은 해시뿐이라
 * 서버도 다시 알아낼 수 없습니다. 화면이 그 사실을 분명히 말하고, 코드를 닫기
 * 전에 전달했는지 확인시킵니다 — 닫고 나면 재발급밖에 길이 없습니다.
 *
 * 초대 링크에는 **비밀이 없습니다.** 링크와 코드를 따로 전달하는 것이 2단계
 * 로그인의 요점이라, 화면도 둘을 나란히 두되 "따로 보내세요" 라고 적습니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type {
  BoothList,
  FestivalDetail,
  StaffIssued,
  StaffList,
  StaffRole,
  StaffRow,
} from '../api/types';

const ROLES: { value: StaffRole; label: string; hint: string }[] = [
  { value: 'operator', label: '운영자', hint: '부스·미션·경품·특강을 관리합니다.' },
  { value: 'booth_manager', label: '부스 관리자', hint: '담당 부스의 미션만 지급합니다.' },
  { value: 'judge', label: '심사위원', hint: '전시 작품에 점수만 매깁니다. 운영 권한은 없습니다.' },
];

const ROLE_LABEL: Record<string, string> = Object.fromEntries(
  ROLES.map((r) => [r.value, r.label]),
);
ROLE_LABEL.planner = '기획자';

export function StaffAdminPage() {
  const { id = '' } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [form, setForm] = useState({
    display_name: '',
    role: 'judge' as StaffRole,
    booth_id: '',
  });
  const [issued, setIssued] = useState<StaffIssued | null>(null);

  const festival = useQuery({
    queryKey: ['festival', id],
    queryFn: () => api.get<FestivalDetail>(`/api/festivals/${id}`),
  });

  const staff = useQuery({
    queryKey: ['staff', id],
    queryFn: () => api.get<StaffList>(`/api/festivals/${id}/staff`),
    retry: false,
  });

  const booths = useQuery({
    queryKey: ['booths', id],
    queryFn: () => api.get<BoothList>(`/api/festivals/${id}/booths`),
    retry: false,
  });

  const reload = () => qc.invalidateQueries({ queryKey: ['staff', id] });

  const issue = useMutation({
    mutationFn: () =>
      api.post<StaffIssued>(`/api/festivals/${id}/staff`, {
        display_name: form.display_name.trim(),
        role: form.role,
        booth_id: form.role === 'booth_manager' ? Number(form.booth_id) || null : null,
      }),
    onSuccess: (r) => {
      setIssued(r);
      setForm({ display_name: '', role: 'judge', booth_id: '' });
      reload();
    },
  });

  const err = issue.error instanceof ApiError ? issue.error : null;
  const needsBooth = form.role === 'booth_manager';
  const ready = form.display_name.trim() && (!needsBooth || form.booth_id);

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">스태프</p>
          <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>
            {festival.data?.name ?? '불러오는 중…'}
          </h1>
          <p className="muted">
            스태프를 발급하면 초대 링크와 6자리 접근 코드가 나옵니다. 둘은{' '}
            <b>따로 전달하세요</b> — 링크만으로는 들어올 수 없는 것이 이 방식의 요점입니다.
          </p>
        </div>
      </div>

      {issued && <IssuedCard issued={issued} onClose={() => setIssued(null)} />}

      <form
        className="card stack"
        style={{ gap: 'var(--space-4)' }}
        onSubmit={(e) => {
          e.preventDefault();
          if (ready && !issue.isPending) issue.mutate();
        }}
      >
        <p className="eyebrow" data-tour="staff-issue">스태프 발급</p>

        <div className="field">
          <label htmlFor="staff-name">
            이름 <span className="req">*</span>
          </label>
          <input
            id="staff-name"
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            placeholder="김심사"
          />
        </div>

        <div className="field">
          <label>역할</label>
          <div className="exptypes">
            {ROLES.map((r) => (
              <button
                key={r.value}
                type="button"
                className={`exptype${form.role === r.value ? ' exptype--on' : ''}`}
                aria-pressed={form.role === r.value}
                onClick={() => setForm({ ...form, role: r.value })}
              >
                <b>{r.label}</b>
                <small>{r.hint}</small>
              </button>
            ))}
          </div>
        </div>

        {/* 부스를 안 정하면 그 스태프는 어느 부스에도 지급할 수 없다. */}
        {needsBooth && (
          <div className="field">
            <label htmlFor="staff-booth">
              담당 부스 <span className="req">*</span>
            </label>
            <select
              id="staff-booth"
              value={form.booth_id}
              onChange={(e) => setForm({ ...form, booth_id: e.target.value })}
            >
              <option value="">고르세요</option>
              {(booths.data?.items ?? []).map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
            <span className="hint">
              부스 없이 발급하면 현장에서 아무 미션도 지급할 수 없습니다.
            </span>
          </div>
        )}

        {err && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>{err.message}</span>
          </div>
        )}

        <button className="btn btn--primary btn--lg" type="submit" disabled={!ready || issue.isPending}>
          {issue.isPending ? '발급 중…' : '＋ 스태프 발급'}
        </button>
      </form>

      <div className="card stack" style={{ gap: 'var(--space-3)' }}>
        <p className="eyebrow">스태프 {staff.data?.total ?? 0}명</p>
        {(staff.data?.items ?? []).length === 0 && (
          <p className="muted">아직 없습니다. 위에서 발급하세요.</p>
        )}
        <div className="rcpt">
          {(staff.data?.items ?? []).map((s) => (
            <StaffRowItem key={s.id} festivalId={id} row={s} onChanged={reload} onIssued={setIssued} />
          ))}
        </div>
      </div>
    </div>
  );
}

/** 발급 직후 딱 한 번 보이는 코드. 닫으면 다시 볼 수 없다. */
function IssuedCard({ issued, onClose }: { issued: StaffIssued; onClose: () => void }) {
  const [confirmed, setConfirmed] = useState(false);
  // 서버의 `invite_url` 은 요청이 도착한 주소(=API 서버)로 만들어질 수 있다.
  // 이 화면을 연 오리진이 곧 스태프가 접속할 오리진이다.
  const inviteUrl = window.location.origin + issued.invite_path;

  return (
    <div className="card card--accent stack" style={{ gap: 'var(--space-4)' }}>
      <div className="stack" style={{ gap: 4 }}>
        <p className="eyebrow">{issued.staff.display_name} · 발급 완료</p>
        <h3 style={{ fontSize: 'var(--text-h3)' }}>지금 전달하세요</h3>
        <p className="muted">
          이 코드는 <b>다시 볼 수 없습니다.</b> 저장되는 것은 해시뿐이라 서버도 알아낼 수
          없고, 잃어버리면 재발급이 유일한 길입니다.
        </p>
      </div>

      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        <span className="eyebrow" data-tour="staff-code">접근 코드</span>
        <div className="claimcode tabular">{issued.access_code}</div>
      </div>

      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        <span className="eyebrow">초대 링크 (비밀 없음)</span>
        <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
          <code className="joinurl">{inviteUrl}</code>
          <button
            className="btn btn--ghost"
            onClick={() => navigator.clipboard?.writeText(inviteUrl)}
          >
            링크 복사
          </button>
        </div>
        <span className="hint">
          링크와 코드를 <b>다른 경로로</b> 보내세요. 한 채팅방에 함께 올리면 그 방이
          유출되는 순간 2단계가 1단계가 됩니다.
        </span>
      </div>

      <label className="row" style={{ gap: 'var(--space-2)' }}>
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          style={{ width: 20, height: 20 }}
        />
        <span className="muted">전달했습니다. 닫아도 됩니다.</span>
      </label>

      <button className="btn btn--primary btn--lg" disabled={!confirmed} onClick={onClose}>
        닫기
      </button>
    </div>
  );
}

function StaffRowItem({
  festivalId,
  row,
  onChanged,
  onIssued,
}: {
  festivalId: string;
  row: StaffRow;
  onChanged: () => void;
  onIssued: (r: StaffIssued) => void;
}) {
  const act = useMutation({
    mutationFn: (what: 'rotate' | 'deactivate' | 'reactivate' | 'unlock') =>
      what === 'deactivate'
        ? api.del(`/api/festivals/${festivalId}/staff/${row.id}`)
        : api.post<StaffIssued>(`/api/festivals/${festivalId}/staff/${row.id}/${what}`),
    onSuccess: (r, what) => {
      if (what === 'rotate') onIssued(r as StaffIssued);
      onChanged();
    },
  });

  const locked = !!row.locked_until && new Date(row.locked_until) > new Date();

  return (
    <div className="rcpt__row">
      <span className="rcpt__name">
        <strong>
          {row.display_name}
          {!row.is_active && ' (중지됨)'}
        </strong>
        <span>
          {ROLE_LABEL[row.role] ?? row.role}
          {row.last_login_at
            ? ` · 마지막 로그인 ${new Date(row.last_login_at).toLocaleDateString('ko-KR')}`
            : ' · 로그인 이력 없음'}
          {/* 잠긴 이유를 숨기지 않는다 — 운영자가 "왜 못 들어오지" 로 시간을 쓴다. */}
          {locked && ` · 🔒 잠김 (${row.failed_attempts}회 실패)`}
        </span>
      </span>
      <span className="rcpt__lead" aria-hidden="true" />
      <span className="row" style={{ gap: 'var(--space-2)' }}>
        {locked && (
          <button className="btn btn--soft" onClick={() => act.mutate('unlock')}>
            잠금 풀기
          </button>
        )}
        <button className="btn btn--ghost" onClick={() => act.mutate('rotate')}>
          코드 재발급
        </button>
        <button
          className="btn btn--ghost"
          onClick={() => act.mutate(row.is_active ? 'deactivate' : 'reactivate')}
        >
          {row.is_active ? '중지' : '재개'}
        </button>
      </span>
    </div>
  );
}
