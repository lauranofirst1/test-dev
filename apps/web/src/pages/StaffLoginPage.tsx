/** 스태프 로그인 — 2단계. 계약 §1.
 *
 * 초대 링크가 `?f={festival_id}&s={staff_id}` 를 채우고, 사람이 6자리 접근 코드를
 * 입력합니다. **링크 사진이 유출돼도 코드 없이는 들어올 수 없습니다.**
 *
 * 실패 응답은 무엇이 틀렸는지 알려주지 않습니다 — 축제가 없는 것과 스태프가 없는
 * 것과 코드가 틀린 것을 구분해 주면, 응답만 보고 유효한 staff_id 를 훑을 수 있습니다.
 * 화면도 그 문구를 그대로 씁니다.
 *
 * 세션은 httpOnly 쿠키로 옵니다. 응답 본문에도 토큰이 있지만(부스 태블릿 앱 등
 * 브라우저가 아닌 클라이언트용) **이 화면은 그걸 저장하지 않습니다.**
 */

import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { StaffSession } from '../api/types';

/** 역할별로 로그인 뒤 갈 곳. 심사위원을 부스 관리로 보내면 할 일이 없다.
 *
 * 부스 담당자를 `/festivals/{f}/booths` 로 보내던 것을 고쳤습니다 — 그건 부스를
 * **만들고 고치는** 운영자 화면이라, 정작 스탬프를 줄 수가 없었습니다. */
const HOME: Record<string, (festivalId: number) => string> = {
  judge: (f) => `/festivals/${f}/judging`,
  booth_manager: (f) => `/booth/festivals/${f}`,
  operator: (f) => `/booth/festivals/${f}`,
  planner: (f) => `/festivals/${f}/diagnosis`,
};

export function StaffLoginPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const festivalId = params.get('f') ?? '';
  const staffId = params.get('s') ?? '';
  const [code, setCode] = useState('');

  const login = useMutation({
    mutationFn: () =>
      api.post<StaffSession>('/api/auth/staff/login', {
        festival_id: Number(festivalId),
        staff_id: Number(staffId),
        access_code: code.trim(),
      }),
    onSuccess: (session) => {
      const to = HOME[session.staff.role] ?? ((f: number) => `/festivals/${f}/booths`);
      navigate(to(session.staff.festival_id), { replace: true });
    },
  });

  const err = login.error instanceof ApiError ? login.error : null;
  const linkOk = !!festivalId && !!staffId;

  return (
    <div className="authshell">
      <div className="stack" style={{ gap: 'var(--space-2)', textAlign: 'center' }}>
        <p className="eyebrow">FestaFlow</p>
        <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>스태프 로그인</h1>
        <p className="muted">운영자에게 받은 6자리 접근 코드를 입력하세요.</p>
      </div>

      {!linkOk && (
        <div className="card state">
          <p className="eyebrow">초대 링크로 들어와 주세요</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            이 화면은 운영자가 보낸 링크에 담긴 정보가 있어야 열립니다. 링크를 다시
            확인해 주세요.
          </p>
        </div>
      )}

      {linkOk && (
        <form
          className="card stack"
          style={{ gap: 'var(--space-4)' }}
          onSubmit={(e) => {
            e.preventDefault();
            if (code.trim() && !login.isPending) login.mutate();
          }}
        >
          <div className="field">
            <label htmlFor="access-code">접근 코드</label>
            <input
              id="access-code"
              className="claimcode tabular"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase().slice(0, 12))}
              placeholder="XXXXXX"
              inputMode="text"
              autoComplete="one-time-code"
              autoCapitalize="characters"
              spellCheck={false}
              autoFocus
            />
            <span className="hint">
              여러 번 틀리면 잠깁니다. 6자리는 조합이 약 10억뿐이라, 잠금이 없으면
              대입이 실제로 통합니다.
            </span>
          </div>

          {err && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>{err.message}</span>
            </div>
          )}

          <button
            className="btn btn--primary btn--lg"
            type="submit"
            disabled={!code.trim() || login.isPending}
          >
            {login.isPending ? '확인 중…' : '들어가기'}
          </button>
        </form>
      )}
    </div>
  );
}
