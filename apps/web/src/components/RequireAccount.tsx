/** 기관 세션이 있어야 열리는 화면을 감싼다.
 *
 * **세션 확인을 서버에 묻습니다.** 화면이 토큰을 들고 있지 않으므로(httpOnly
 * 쿠키) "로그인했나"를 로컬에서 판단할 방법이 없고, 그게 맞습니다 — 로컬 플래그로
 * 판단하면 만료된 세션에서도 화면이 열리고 요청마다 401 이 흩어집니다.
 */

import { useQuery } from '@tanstack/react-query';
import { Navigate, useLocation } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { AccountSession } from '../api/types';

export function useSession() {
  return useQuery({
    queryKey: ['session'],
    queryFn: () => api.get<AccountSession>('/api/auth/me'),
    retry: false,
    staleTime: 60_000,
  });
}

export function RequireAccount({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const location = useLocation();

  if (session.isLoading) {
    return (
      <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
        <div className="skeleton" style={{ height: 180 }} />
      </div>
    );
  }

  if (session.error instanceof ApiError) {
    // 어디로 가려 했는지 남긴다 — 로그인 뒤 그 자리로 돌아갈 수 있게.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
