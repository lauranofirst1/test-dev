/** 내 축제 — 축제 목록.
 *
 * 담당자는 자기를 "기획자" 라고 부르지 않고, "워크스페이스" 도 이 사람의
 * 말이 아닙니다. 화면 이름은 쓰는 사람의 말이어야 합니다. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { FestivalList } from '../api/types';

export function WorkspacePage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ['festivals'],
    queryFn: () => api.get<FestivalList>('/api/festivals'),
    retry: false,
  });

  const remove = useMutation({
    mutationFn: (festival: { id: number; name: string }) =>
      api.del<void>(`/api/festivals/${festival.id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['festivals'] }),
  });

  const removeFestival = (festival: { id: number; name: string }) => {
    const confirmed = window.confirm(
      `'${festival.name}' 축제를 완전히 삭제할까요?\n\n` +
        '참여 기록, 리포트, 부스, 특강을 포함한 모든 데이터가 삭제되며 복구할 수 없습니다.',
    );
    if (confirmed) remove.mutate(festival);
  };

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="pagehead row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">기획자 워크스페이스</p>
          <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>내 축제</h1>
          <p className="lede">준비 중인 축제를 선택해 진단부터 현장 운영까지 관리하세요.</p>
        </div>
        <Link to="/festivals/new" className="btn btn--primary btn--lg">
          ＋ 새 축제
        </Link>
      </div>

      {isLoading && (
        <div className="cards">
          {[0, 1, 2].map((i) => (
            <div className="skeleton" style={{ height: 168 }} key={i} />
          ))}
        </div>
      )}

      {error instanceof ApiError && (
        <div className="card state">
          <p className="eyebrow">불러오지 못했습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            {error.message}
          </p>
        </div>
      )}

      {remove.error instanceof ApiError && (
        <div className="notice notice--warn" role="alert">
          <span>⚠</span>
          <span>축제를 삭제하지 못했습니다 — {remove.error.message}</span>
        </div>
      )}

      {data && data.items.length === 0 && (
        <div className="card state">
          <p className="eyebrow">아직 축제가 없습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            첫 축제를 만들면 한국관광공사 데이터로 기획 준비도를 진단해 드립니다.
          </p>
          <Link to="/festivals/new" className="btn btn--primary btn--lg">
            첫 축제 만들기
          </Link>
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="cards">
          {data.items.map((f) => (
            <article className="fcard__wrap" key={f.id}>
            <Link to={`/festivals/${f.id}/diagnosis`} className="card fcard">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="muted tabular">#{f.id}</span>
                {f.is_demo && <span className="badge badge--none">데모</span>}
              </div>
              <h3 style={{ fontSize: 'var(--text-h3)' }}>{f.name}</h3>
              <p className="muted">
                {f.region} · {f.venue}
              </p>
              <p className="muted tabular">
                {f.starts_on} ~ {f.ends_on}
              </p>
              <div className="fcard__stats">
                <div>
                  <b className="tabular">{f.expected_visitors.toLocaleString()}</b>
                  <small>예상 방문객</small>
                </div>
                <div>
                  <b className="tabular">{(f.total_budget / 100_000_000).toFixed(1)}억</b>
                  <small>총예산</small>
                </div>
              </div>
              <span className="fcard__cta">사전 진단 열기 <span aria-hidden>→</span></span>
            </Link>
            {/* 진단만으로는 현장이 준비되지 않는다. 부스 등록으로 가는 길을
                카드에서 바로 열어 둔다. */}
            <nav className="fcard__actions" aria-label={`${f.name} 바로가기`}>
              <Link to={`/festivals/${f.id}/booths`} className="fcard__sub">
                <strong>부스 · 미션</strong>
                <span>참여 동선 준비</span>
              </Link>
            {/* 축제 당일에 여는 화면. 준비 단계에서는 볼 것이 없지만, 당일
                아침에 어디로 들어가는지를 미리 알아 두어야 한다. */}
              <Link to={`/festivals/${f.id}/dashboard`} className="fcard__sub">
                <strong>오늘</strong>
                <span>현장 운영 현황</span>
              </Link>
            <Link to={`/festivals/${f.id}/report`} className="fcard__sub">
                <strong>리포트</strong>
                <span>종료 후 성과</span>
            </Link>
              <button
                type="button"
                className="fcard__sub fcard__sub--danger"
                onClick={() => removeFestival(f)}
                disabled={remove.isPending}
              >
                <strong>{remove.isPending && remove.variables?.id === f.id ? '삭제 중…' : '축제 삭제'}</strong>
                <span>영구 삭제</span>
              </button>
            </nav>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
