/** 기획자 워크스페이스 — 축제 목록. */

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { FestivalList } from '../api/types';

export function WorkspacePage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['festivals'],
    queryFn: () => api.get<FestivalList>('/api/festivals'),
    retry: false,
  });

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">기획자 워크스페이스</p>
          <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>축제</h1>
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
            <div className="fcard__wrap" key={f.id}>
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
              <span className="fcard__cta">진단 보기 →</span>
            </Link>
            {/* 진단만으로는 현장이 준비되지 않는다. 부스 등록으로 가는 길을
                카드에서 바로 열어 둔다. */}
            <Link to={`/festivals/${f.id}/booths`} className="fcard__sub">
              부스 · 미션 관리 →
            </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
