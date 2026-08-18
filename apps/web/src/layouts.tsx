/** 화면 묶음별 껍데기.
 *
 * 기획자와 관객은 **같은 헤더를 쓸 수 없습니다.** 관객은 축제 링크로 들어온
 * 방문객이지 이 도구의 사용자가 아닙니다. 기획자 헤더를 그대로 보여주면
 * "축제 기획 진단"이라는 낯선 브랜드가 걸리고, 로고를 누르면 남의 기관
 * 워크스페이스로 떨어집니다.
 *
 * 그래서 관객 껍데기는 축제 이름만 보여주고 밖으로 나가는 링크를 두지 않습니다.
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Link, Outlet, useParams } from 'react-router-dom';

import { api } from './api/client';
import type { PublicFestival } from './api/types';

const PLANNER_TITLE = 'FestaFlow — 축제 기획 진단';

export function PlannerLayout() {
  useEffect(() => {
    document.title = PLANNER_TITLE;
  }, []);

  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          FestaFlow <small>축제 기획 진단</small>
        </Link>
        <span className="muted">출처: ⓒ한국관광공사</span>
      </header>
      <Outlet />
    </>
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
    <>
      <header className="topbar topbar--audience">
        <span className="brand brand--plain">
          {festival.data?.name ?? '축제 참여'}
        </span>
        <span className="muted">출처: ⓒ한국관광공사</span>
      </header>
      <Outlet />
    </>
  );
}
