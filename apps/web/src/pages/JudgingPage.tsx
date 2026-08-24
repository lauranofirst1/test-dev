/** 심사위원 심사표 — 작품마다 항목별 점수를 매긴다.
 *
 * **다른 심사위원의 점수가 화면에 없습니다.** 서버가 내려주지 않습니다. 남의
 * 숫자가 보이면 거기에 끌려갑니다. 합의는 회의에서 하는 것이지 입력 화면에서
 * 서로의 숫자를 보며 하는 것이 아닙니다.
 *
 * 심사에는 스태프 세션이 필요합니다 — **누가 매겼는지가 점수의 일부**입니다.
 * 세션은 `/staff/login` 에서 접근 코드로 받고, **httpOnly 쿠키로** 옵니다.
 * 화면이 토큰을 손에 쥐지 않으므로 XSS 가 나도 새지 않습니다.
 *
 * 항목 만점이 5점이면 5칸짜리 버튼을 씁니다. 숫자를 타이핑하게 하면 현장에서
 * 태블릿을 들고 오타를 냅니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { JudgeProgress, JudgeSheet } from '../api/types';

export function JudgingPage() {
  const { id = '' } = useParams<{ id: string }>();
  const qc = useQueryClient();

  // 세션은 쿠키로 실려 간다. 화면이 토큰을 들고 있지 않으므로
  // 헤더를 붙일 것도, 저장할 것도 없다.
  const progress = useQuery({
    queryKey: ['judging', id],
    queryFn: () => api.get<JudgeProgress>(`/api/festivals/${id}/judging`),
    retry: false,
  });

  const err = progress.error instanceof ApiError ? progress.error : null;

  if (err && (err.status === 401 || err.status === 403)) {
    return (
      <div className="shell stack" style={{ gap: 'var(--space-5)' }}>
        <div className="card state">
          <p className="eyebrow">심사위원 로그인이 필요합니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            {err.message}
          </p>
          <p className="muted" style={{ textAlign: 'center' }}>
            운영자가 보낸 초대 링크로 들어와 접근 코드를 입력하세요. 누가 매겼는지가
            점수의 일부라 익명 심사는 받지 않습니다.
          </p>
        </div>
      </div>
    );
  }

  const p = progress.data;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-5)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">전시 심사</p>
          <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>내 심사표</h1>
          {p && (
            <p className="muted tabular">
              {p.scored_exhibits} / {p.total_exhibits}개 작품 완료
            </p>
          )}
        </div>
        <LogoutButton onDone={() => qc.clear()} />
      </div>

      {progress.isLoading && <div className="skeleton" style={{ height: 220 }} />}

      {p && p.sheets.length === 0 && (
        <div className="card state">
          <p className="eyebrow">심사할 작품이 없습니다</p>
        </div>
      )}

      {p?.sheets.map((sheet) => (
        <SheetCard
          key={sheet.exhibit.id}
          festivalId={id}
          sheet={sheet}
          onSaved={() => qc.invalidateQueries({ queryKey: ['judging', id] })}
        />
      ))}

      <Link to={`/festivals/${id}/exhibits`} className="muted" style={{ textAlign: 'center' }}>
        작품 관리로 →
      </Link>
    </div>
  );
}

/** 세션 쿠키를 지운다. 화면이 토큰을 들고 있지 않으니 이게 곧 로그아웃이다. */
function LogoutButton({ onDone }: { onDone: () => void }) {
  const logout = useMutation({
    mutationFn: () => api.post('/api/auth/logout'),
    onSuccess: onDone,
  });
  return (
    <button className="btn btn--ghost" onClick={() => logout.mutate()} disabled={logout.isPending}>
      로그아웃
    </button>
  );
}

function SheetCard({
  festivalId,
  sheet,
  onSaved,
}: {
  festivalId: string;
  sheet: JudgeSheet;
  onSaved: () => void;
}) {
  const initial = Object.fromEntries(sheet.my_scores.map((s) => [s.criterion_id, s.score]));
  const [scores, setScores] = useState<Record<number, number>>(initial);
  const [comment, setComment] = useState(sheet.my_scores[0]?.comment ?? '');

  const save = useMutation({
    mutationFn: () =>
      api.put(`/api/festivals/${festivalId}/exhibits/${sheet.exhibit.id}/scores`, {
        scores: Object.entries(scores).map(([criterion_id, score]) => ({
          criterion_id: Number(criterion_id),
          score,
          comment: comment.trim() || null,
        })),
      }),
    onSuccess: onSaved,
  });

  const filled = sheet.criteria.every((c) => scores[c.id] !== undefined);

  return (
    <article className={`card stack${sheet.is_complete ? ' judged' : ''}`} style={{ gap: 'var(--space-4)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="row" style={{ gap: 'var(--space-2)', alignItems: 'baseline' }}>
          <span className="exhibit__no tabular">{sheet.exhibit.entry_no}</span>
          <div className="stack" style={{ gap: 2 }}>
            <h3 style={{ fontSize: 'var(--text-h3)' }}>{sheet.exhibit.title}</h3>
            {sheet.exhibit.team_name && (
              <span className="muted">{sheet.exhibit.team_name}</span>
            )}
          </div>
        </div>
        {sheet.is_complete && (
          <span className="badge badge--stable">
            <i />
            심사 완료
          </span>
        )}
      </div>

      {sheet.criteria.length === 0 && (
        <p className="muted">심사 항목이 없습니다. 운영자가 먼저 항목을 만들어야 합니다.</p>
      )}

      {sheet.criteria.map((c) => (
        <div className="field" key={c.id}>
          <label>
            {c.label}
            <span className="muted tabular"> · {c.max_score}점 만점 · 가중치 {c.weight}</span>
          </label>
          {c.description && <span className="hint">{c.description}</span>}
          {/* 숫자를 타이핑하게 하면 태블릿에서 오타가 난다. */}
          <div className="scorepad">
            {Array.from({ length: c.max_score }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                className={`scorepad__key${scores[c.id] === n ? ' scorepad__key--on' : ''}`}
                aria-pressed={scores[c.id] === n}
                onClick={() => setScores({ ...scores, [c.id]: n })}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      ))}

      {sheet.criteria.length > 0 && (
        <div className="field">
          <label htmlFor={`comment-${sheet.exhibit.id}`}>심사평 (선택)</label>
          <textarea
            id={`comment-${sheet.exhibit.id}`}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="무엇이 좋았고 무엇이 아쉬웠는지"
          />
        </div>
      )}

      {save.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{save.error.message}</span>
        </div>
      )}

      {sheet.criteria.length > 0 && (
        <button
          className="btn btn--primary btn--lg"
          disabled={!filled || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending
            ? '저장 중…'
            : sheet.is_complete
              ? '점수 고치기'
              : filled
                ? '심사표 제출'
                : '모든 항목에 점수를 매겨 주세요'}
        </button>
      )}
    </article>
  );
}
