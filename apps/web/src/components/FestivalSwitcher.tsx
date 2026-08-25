/** 상단바 축제 전환.
 *
 * 예전에는 축제 안에서 다른 축제로 가는 길이 «← 다른 축제» 하나뿐이었습니다.
 * SW Week 과 해커톤을 같은 주에 돌리는 담당자는 목록까지 나갔다 오는 왕복을
 * 하루에 여러 번 합니다.
 *
 * ## 보던 자리로 넘어간다
 *
 * 부스 화면에서 다른 축제를 고르면 **그 축제의 부스 화면**이 열립니다.
 * 늘 현황으로 보내면 비교하려고 옮기는 사람이 매번 두 번 눌러야 합니다.
 * 다만 지금 화면이 그 축제에 없을 수 있는 경우(진단의 탭 상태 같은 것)는
 * 쿼리스트링을 떼고 보냅니다.
 *
 * ## 기간과 상태를 함께 보여준다
 *
 * 이름만 늘어놓으면 «SW Week» 이 작년 것인지 올해 것인지 알 수 없습니다.
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import { api } from '../api/client';
import type { Festival, FestivalList } from '../api/types';

const STATUS_LABEL: Record<string, string> = {
  planning: '준비 중',
  ongoing: '진행 중',
  closed: '끝남',
};

function period(f: Festival) {
  const short = (iso: string) => iso.slice(5).replace('-', '.');
  return `${short(f.starts_on)}–${short(f.ends_on)}`;
}

export function FestivalSwitcher() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  const festivals = useQuery({
    queryKey: ['festivals'],
    queryFn: () => api.get<FestivalList>('/api/festivals'),
    // 목록은 드롭다운을 열 때 필요하다. 축제 화면마다 미리 받아 둘 이유가 없다.
    enabled: open,
    retry: false,
    staleTime: 60_000,
  });

  const current = useQuery({
    queryKey: ['festival', id],
    queryFn: () => api.get<Festival>(`/api/festivals/${id}`),
    enabled: Boolean(id),
  });

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

  if (!id) return null;

  const items = festivals.data?.items ?? [];
  const f = current.data;

  /** 보던 자리의 같은 화면으로. 쿼리스트링은 뗀다 — 탭 상태 같은 것이
   *  다른 축제에서 뜻이 다를 수 있다. */
  const switchTo = (next: number) => {
    const rest = location.pathname.replace(`/festivals/${id}`, '');
    setOpen(false);
    navigate(`/festivals/${next}${rest}`);
  };

  return (
    <div className="fswitch" ref={box}>
      <button
        type="button"
        className="fswitch__btn"
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen((v) => !v)}
      >
        {/* 이름과 기간은 크기가 달라 **서로는 베이스라인**을 맞춰야 읽기 좋고,
            그 묶음은 버튼 상자 안에서 **가운데**에 서야 한다. 두 정렬이
            달라서 한 겹을 더 둔다 — 하나로 하면 글자가 상자 위쪽으로 뜬다. */}
        <span className="fswitch__text">
          <span className="fswitch__name">{f?.name ?? '축제'}</span>
          {f && (
            <span className="fswitch__meta tabular">
              {period(f)} · {STATUS_LABEL[f.status] ?? f.status}
            </span>
          )}
        </span>
        <span className="fswitch__caret" aria-hidden>
          ▾
        </span>
      </button>

      {open && (
        <div className="fswitch__pop" role="listbox" aria-label="축제 고르기">
          {festivals.isLoading && <p className="fsearch__note">불러오는 중…</p>}
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="option"
              aria-selected={String(item.id) === id}
              className="fswitch__item"
              onClick={() => switchTo(item.id)}
            >
              <strong>{item.name}</strong>
              <span className="tabular">
                {period(item)} · {STATUS_LABEL[item.status] ?? item.status}
              </span>
            </button>
          ))}
          <a className="fswitch__all" href="/">
            내 축제 전체 →
          </a>
        </div>
      )}
    </div>
  );
}
