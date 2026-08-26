/** 상단바 통합 검색 — 부스 · 미션 · 작품 · 참여자.
 *
 * 축제 하나에 부스 스무 개, 미션 서른 개, 작품 서른 점, 참여자 천 명이
 * 붙습니다. "B7 이 어느 화면에 있었지" 를 메뉴로 되짚는 대신 이름을 치면
 * 나와야 합니다.
 *
 * ## 타이핑마다 부르지 않는다
 *
 * 한 글자에 한 번씩 부르면 "AI 체험존" 을 치는 동안 여섯 번 훑습니다.
 * 250ms 쉬면 그때 한 번 부릅니다 — 사람이 다음 글자를 치는 간격보다 길고,
 * 손을 멈춘 것을 알아채기에는 짧습니다.
 *
 * ## 두 글자부터
 *
 * 서버가 `min_query` 를 함께 내려주므로 화면이 같은 숫자를 따로 들고 있지
 * 않습니다. 한 글자일 때는 오류가 아니라 **안내**를 냅니다 — 타이핑 중인
 * 상태를 오류로 알리면 글자를 칠 때마다 빨간 글씨가 깜빡입니다.
 *
 * ## 잘렸으면 잘렸다고 말한다
 *
 * 종류마다 상한이 있습니다. 조용히 자르면 "없다" 와 구분되지 않고, 운영자는
 * 없는 줄 알고 다른 곳을 찾습니다.
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { api } from '../api/client';
import type { SearchHit, SearchResult } from '../api/types';

const DEBOUNCE_MS = 250;

const KIND_LABEL: Record<SearchHit['kind'], string> = {
  booth: '부스',
  mission: '미션',
  exhibit: '작품',
  participant: '참여자',
};

/** 종류마다 어느 화면으로 보내는지. **서버가 주소를 만들지 않는다** —
 *  만들면 프런트 라우팅이 바뀔 때마다 백엔드를 고쳐야 한다. */
function hrefFor(hit: SearchHit, festivalId: string): string {
  switch (hit.kind) {
    case 'booth':
    case 'mission':
      return `/festivals/${festivalId}/booths`;
    case 'exhibit':
      return `/festivals/${festivalId}/exhibits`;
    case 'participant':
      return `/festivals/${festivalId}/claim`;
  }
}

export function FestivalSearch({ festivalId }: { festivalId: string }) {
  const navigate = useNavigate();
  const [raw, setRaw] = useState('');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // 손을 멈추면 그때 한 번 부른다.
  useEffect(() => {
    const t = setTimeout(() => setQ(raw.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [raw]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const results = useQuery({
    queryKey: ['search', festivalId, q],
    queryFn: () =>
      api.get<SearchResult>(
        `/api/festivals/${festivalId}/search?q=${encodeURIComponent(q)}`,
      ),
    // 두 글자 미만은 아예 부르지 않는다. 서버도 빈 결과를 주지만, 부르지
    // 않으면 왕복 자체가 없다.
    enabled: q.length >= 2,
    retry: false,
    staleTime: 15_000,
  });

  const data = results.data;
  const hits = data?.hits ?? [];

  const go = (hit: SearchHit) => {
    setOpen(false);
    setRaw('');
    navigate(hrefFor(hit, festivalId));
  };

  return (
    <div className="fsearch" ref={box}>
      <input
        type="search"
        className="fsearch__input"
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="부스 · 작품 · 코드 찾기"
        aria-label="축제 안에서 찾기"
        autoComplete="off"
      />

      {open && raw.trim().length > 0 && (
        <div className="fsearch__pop">
          {raw.trim().length < 2 ? (
            <p className="fsearch__note">두 글자부터 찾습니다.</p>
          ) : results.isLoading ? (
            <p className="fsearch__note">찾는 중…</p>
          ) : hits.length === 0 ? (
            <p className="fsearch__note">
              «{q}» 에 걸리는 것이 없습니다. 부스 · 미션 · 작품 · 참여 코드를
              찾습니다. 학번은 <b>전체를 정확히</b> 입력해야 찾습니다.
            </p>
          ) : (
            <>
              <ul className="fsearch__list">
                {hits.map((h) => (
                  <li key={`${h.kind}-${h.id}`}>
                    <button type="button" className="fsearch__item" onClick={() => go(h)}>
                      <span className="fsearch__kind">{KIND_LABEL[h.kind]}</span>
                      <span className="fsearch__title">{h.title}</span>
                      {h.subtitle && <span className="fsearch__sub">{h.subtitle}</span>}
                    </button>
                  </li>
                ))}
              </ul>
              {data?.truncated && (
                <p className="fsearch__note">
                  결과가 더 있습니다. 더 좁혀서 입력해 보세요.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
