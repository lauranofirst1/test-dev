/** 화면 묶음별 껍데기.
 *
 * 기획자와 관객은 **같은 헤더를 쓸 수 없습니다.** 관객은 축제 링크로 들어온
 * 방문객이지 이 도구의 사용자가 아닙니다. 기획자 헤더를 그대로 보여주면
 * "축제 기획 진단"이라는 낯선 브랜드가 걸리고, 로고를 누르면 남의 기관
 * 워크스페이스로 떨어집니다.
 *
 * 그래서 관객 껍데기는 축제 이름만 보여주고 밖으로 나가는 링크를 두지 않습니다.
 *
 * 관객 쪽만 `.paper` 로 감쌉니다. 페이퍼 테마는 그 안에서만 토큰을 덮어쓰므로
 * (styles/paper.css) 기획자 화면으로 새지 않습니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';

import { api } from './api/client';
import { AnnouncementProvider } from './components/announcements/AnnouncementProvider';
import { AnnouncementSurface } from './components/announcements/AnnouncementSurface';
import { FestivalNav } from './components/FestivalNav';
import { useSession } from './components/RequireAccount';
import type { PublicFestival } from './api/types';

const PLANNER_TITLE = 'FestaFlow — 축제 기획 진단';

/** 사이드바 접힘 상태. **기억한다.**
 *
 * 좁은 화면에서 접어 뒀는데 화면을 옮길 때마다 다시 펴지면, 옮길 때마다 다시
 * 접어야 합니다. 그건 금방 "이 메뉴 짜증난다" 가 됩니다.
 */
const COLLAPSE_KEY = 'festaflow-nav-collapsed';

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1';
  } catch {
    return false;
  }
}

export function PlannerLayout() {
  // 사이드바는 **축제 안에서만** 나온다. 축제가 정해지지 않았는데 "부스 관리 /
  // 사후 리포트" 를 띄우면 전부 죽은 링크가 되고, 죽은 링크가 있는 메뉴는
  // 없는 메뉴보다 나쁘다.
  const { id } = useParams<{ id: string }>();
  const location = useLocation();

  const [collapsed, setCollapsed] = useState(loadCollapsed);
  // 모바일은 서랍이다. 좁은 화면에서 사이드바를 눌러 담으면 본문이 읽을 수
  // 없을 만큼 좁아진다 — 축제 당일 태블릿에서 쓰는 화면이다.
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    document.title = PLANNER_TITLE;
  }, []);

  // 화면을 옮기면 서랍은 닫힌다. 열린 채로 남으면 도착한 화면이 안 보인다.
  useEffect(() => setDrawerOpen(false), [location.pathname]);

  // 서랍이 열려 있는 동안 뒤가 스크롤되면 서랍이 아니다. ESC 로 닫는다 —
  // 여기서는 실수로 닫혀도 잃는 것이 없으므로 긴급 공지 덮개와 다르다.
  useEffect(() => {
    if (!drawerOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [drawerOpen]);

  const toggle = useCallback(() => {
    setCollapsed((v) => {
      const next = !v;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0');
      } catch {
        /* 저장 못 해도 이번 세션은 유지된다 */
      }
      return next;
    });
  }, []);

  const body = id ? (
    <AnnouncementProvider festivalId={id} channel="staff">
      <AnnouncementSurface />
      <Outlet />
    </AnnouncementProvider>
  ) : (
    <Outlet />
  );

  return (
    <div className="app" data-collapsed={collapsed} data-nav={Boolean(id)}>
      {/* 키보드 사용자가 메뉴 12개를 매번 지나치지 않게 한다. */}
      <a href="#main" className="skip">
        본문으로 건너뛰기
      </a>

      <header className="topbar">
        <div className="row" style={{ gap: 'var(--space-3)' }}>
          {id && (
            <>
              <button
                className="iconbtn only-narrow"
                onClick={() => setDrawerOpen(true)}
                aria-label="메뉴 열기"
                aria-expanded={drawerOpen}
              >
                ☰
              </button>
              <button
                className="iconbtn only-wide"
                onClick={toggle}
                aria-label={collapsed ? '메뉴 펼치기' : '메뉴 접기'}
                aria-expanded={!collapsed}
              >
                {collapsed ? '»' : '«'}
              </button>
            </>
          )}
          <Link to="/" className="brand">
            FestaFlow <small>축제 기획 진단</small>
          </Link>
        </div>
        <div className="row" style={{ gap: 'var(--space-4)' }}>
          <span className="muted only-wide">출처: ⓒ한국관광공사</span>
          <AccountMenu />
        </div>
      </header>

      <div className="app__body">
        {id && (
          <>
            {/* 넓은 화면: 붙박이 사이드바 */}
            <aside className="side only-wide">
              <FestivalTitle />
              <FestivalNav collapsed={collapsed} />
            </aside>

            {/* 좁은 화면: 서랍. 같은 메뉴를 다른 그릇에 담는다 */}
            {drawerOpen && (
              <div className="drawer" role="presentation">
                <button
                  className="drawer__scrim"
                  onClick={() => setDrawerOpen(false)}
                  aria-label="메뉴 닫기"
                />
                <aside className="drawer__panel" aria-label="축제 메뉴">
                  <FestivalTitle />
                  <FestivalNav collapsed={false} onNavigate={() => setDrawerOpen(false)} />
                </aside>
              </div>
            )}
          </>
        )}

        <main id="main" className="app__main">
          {body}
        </main>
      </div>
    </div>
  );
}

/** 어느 축제를 보고 있는지. 메뉴 맨 위에 둔다 —
 *  축제가 여럿인 기관에서는 이게 없으면 남의 축제를 고치게 된다. */
function FestivalTitle() {
  const { id = '' } = useParams<{ id: string }>();
  const festival = useQuery({
    queryKey: ['festival', id],
    queryFn: () => api.get<{ name: string }>(`/api/festivals/${id}`),
    retry: false,
    staleTime: 5 * 60_000,
  });

  return (
    <div className="side__head">
      <p className="eyebrow">축제</p>
      <strong>{festival.data?.name ?? '불러오는 중…'}</strong>
      <Link to="/" className="muted">
        ← 다른 축제
      </Link>
    </div>
  );
}

/** 로그인한 기관과 로그아웃. 세션이 없으면 아무것도 그리지 않는다 —
 *  로그인 화면 자체가 이 껍데기를 쓰지 않으므로 비어 있는 경우는 로딩뿐이다. */
function AccountMenu() {
  const session = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const logout = useMutation({
    mutationFn: () => api.post('/api/auth/logout'),
    onSuccess: () => {
      // 캐시를 비우지 않으면 로그아웃 뒤에도 남의 기관 데이터가 화면에 남는다.
      qc.clear();
      navigate('/login', { replace: true });
    },
  });

  if (!session.data) return null;

  return (
    <div className="row" style={{ gap: 'var(--space-3)' }}>
      <span className="muted">{session.data.organization_name}</span>
      <button
        className="btn btn--ghost"
        style={{ minHeight: 32, padding: '0 var(--space-3)', fontSize: 'var(--text-sm)' }}
        onClick={() => logout.mutate()}
        disabled={logout.isPending}
      >
        로그아웃
      </button>
    </div>
  );
}


export function AudienceLayout() {
  const { id = '' } = useParams<{ id: string }>();

  // 헤더에 축제 이름을 띄우기 위한 조회. 화면들이 각자 또 받아오지만
  // react-query 가 같은 키로 캐시하므로 요청은 한 번이다.
  const festival = useQuery({
    queryKey: ['public', id],
    queryFn: () => api.get<PublicFestival>(`/api/festivals/${id}/public`),
    retry: false,
    staleTime: 5 * 60_000,
  });

  // 탭 제목도 컨텍스트다. 관객이 링크를 공유하면 "축제 기획 진단"이 아니라
  // 축제 이름이 보여야 한다.
  const name = festival.data?.name;
  useEffect(() => {
    document.title = name ? `${name} 참여` : '축제 참여';
    return () => {
      document.title = PLANNER_TITLE;
    };
  }, [name]);

  return (
    <div className="paper">
      <header className="topbar topbar--audience">
        <span className="brand brand--plain">
          {festival.data?.name ?? '축제 참여'}
        </span>
        <span className="muted">출처: ⓒ한국관광공사</span>
      </header>
      {/* 공지는 껍데기에 단다. 페이지마다 붙이면 어느 화면에 있느냐에 따라
          우천 중단 공지를 보기도 하고 못 보기도 한다. */}
      <AnnouncementProvider festivalId={id} channel="audience">
        <AnnouncementSurface />
        <Outlet />
      </AnnouncementProvider>
    </div>
  );
}
