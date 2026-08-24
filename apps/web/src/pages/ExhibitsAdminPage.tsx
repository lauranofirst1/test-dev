/** 전시 관리 — 작품 등록, 심사 항목, 투표 설정, 시상 집계.
 *
 * **시상 집계는 최종 점수만 보여주지 않습니다.** 항목별 평균과 가중치, 심사위원
 * 수, 득표수를 함께 둡니다. 이의가 들어왔을 때 그 자리에서 보여줄 수 없으면
 * 그 점수는 근거가 아니라 선언입니다.
 *
 * 집계를 흔드는 사실(심사위원 수 불균등, 미심사 작품, 표 없음)은 서버가 판정해
 * 경고로 내려줍니다. 화면이 같은 규칙을 다시 구현하면 반드시 어긋납니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ApiError, api, upload as uploadFile } from '../api/client';
import type {
  Exhibit,
  ExhibitionResults,
  FestivalDetail,
  VoteCriterion,
} from '../api/types';

const EMPTY = { title: '', team_name: '', summary: '', tags: '', location: '' };

export function ExhibitsAdminPage() {
  const { id = '' } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);

  const festival = useQuery({
    queryKey: ['festival', id],
    queryFn: () => api.get<FestivalDetail>(`/api/festivals/${id}`),
  });

  const criteria = useQuery({
    queryKey: ['criteria', id],
    queryFn: () => api.get<VoteCriterion[]>(`/api/festivals/${id}/criteria`),
    retry: false,
  });

  const results = useQuery({
    queryKey: ['exhibition-results', id],
    queryFn: () => api.get<ExhibitionResults>(`/api/festivals/${id}/exhibition-results`),
    retry: false,
  });

  const reload = () => {
    // 집계 응답이 작품 목록을 이미 담는다. 목록을 따로 받으면 두 곳이 어긋난다.
    qc.invalidateQueries({ queryKey: ['criteria', id] });
    qc.invalidateQueries({ queryKey: ['exhibition-results', id] });
  };

  const create = useMutation({
    mutationFn: () =>
      api.post<Exhibit>(`/api/festivals/${id}/exhibits`, {
        title: form.title.trim(),
        team_name: form.team_name.trim() || null,
        summary: form.summary.trim() || null,
        location: form.location.trim() || null,
        // 쉼표로 나눈다. 태그 입력에 UI 를 얹으면 현장에서 붙여넣기가 안 된다.
        tags: form.tags
          .split(',')
          .map((t) => t.trim().replace(/^#/, ''))
          .filter(Boolean),
        is_active: true,
      }),
    onSuccess: () => {
      setForm(EMPTY);
      reload();
    },
  });

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        <Link to={`/festivals/${id}/booths`} className="muted">
          ← 부스 · 미션 관리
        </Link>
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <div className="stack" style={{ gap: 4 }}>
            <p className="eyebrow">전시 심사</p>
            <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>
              {festival.data?.name ?? '불러오는 중…'}
            </h1>
          </div>
          <Link to={`/festivals/${id}/judging`} className="btn btn--mint" target="_blank">
            심사표 열기 ↗
          </Link>
        </div>
      </div>

      {results.data && <Settings festivalId={id} results={results.data} onChanged={reload} />}

      <Criteria festivalId={id} items={criteria.data ?? []} onChanged={reload} />

      {/* 작품 등록 */}
      <form
        className="card stack"
        style={{ gap: 'var(--space-4)' }}
        onSubmit={(e) => {
          e.preventDefault();
          if (form.title.trim()) create.mutate();
        }}
      >
        <p className="eyebrow">작품 등록</p>
        <div className="grid2">
          <div className="field">
            <label htmlFor="ex-title">
              제목 <span className="req">*</span>
            </label>
            <input
              id="ex-title"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="키링 제작기"
            />
          </div>
          <div className="field">
            <label htmlFor="ex-team">팀</label>
            <input
              id="ex-team"
              value={form.team_name}
              onChange={(e) => setForm({ ...form, team_name: e.target.value })}
              placeholder="3팀"
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="ex-summary">한 줄 소개</label>
          <input
            id="ex-summary"
            value={form.summary}
            onChange={(e) => setForm({ ...form, summary: e.target.value })}
          />
        </div>
        <div className="grid2">
          <div className="field">
            <label htmlFor="ex-tags">태그</label>
            <input
              id="ex-tags"
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              placeholder="하드웨어, 3D프린팅"
            />
            <span className="hint">쉼표로 나눕니다. 관객 화면에서 거르기에 쓰입니다.</span>
          </div>
          <div className="field">
            <label htmlFor="ex-loc">전시 위치</label>
            <input
              id="ex-loc"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              placeholder="공학관 1층 A구역"
            />
          </div>
        </div>
        {create.error instanceof ApiError && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>{create.error.message}</span>
          </div>
        )}
        <button className="btn btn--primary btn--lg" type="submit" disabled={create.isPending}>
          {create.isPending ? '등록 중…' : '＋ 작품 등록'}
        </button>
      </form>

      {results.data && <Results festivalId={id} results={results.data} onChanged={reload} />}
    </div>
  );
}

function Settings({
  festivalId,
  results,
  onChanged,
}: {
  festivalId: string;
  results: ExhibitionResults;
  onChanged: () => void;
}) {
  const [limit, setLimit] = useState(String(results.votes_limit));
  const [weight, setWeight] = useState(String(results.judge_weight_percent));

  const save = useMutation({
    mutationFn: (open: boolean) =>
      api.put(`/api/festivals/${festivalId}/exhibition-settings`, {
        audience_votes_per_participant: Number(limit) || 3,
        judge_weight_percent: Number(weight),
        voting_open: open,
      }),
    onSuccess: onChanged,
  });

  return (
    <div className="card stack" style={{ gap: 'var(--space-4)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <p className="eyebrow">투표 설정</p>
        <span className={`badge badge--${results.voting_open ? 'stable' : 'none'}`}>
          <i />
          {results.voting_open ? '투표 진행 중' : '투표 닫힘'}
        </span>
      </div>

      <div className="grid2">
        <div className="field field--inline">
          <label htmlFor="vote-limit">1인당 표</label>
          <input
            id="vote-limit"
            type="number"
            min={1}
            max={20}
            className="tabular"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
          <span className="unit">표</span>
        </div>
        <div className="field field--inline">
          <label htmlFor="judge-weight">심사위원 비중</label>
          <input
            id="judge-weight"
            type="number"
            min={0}
            max={100}
            className="tabular"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
          />
          <span className="unit">%</span>
          <span className="hint">
            관객은 나머지 {100 - (Number(weight) || 0)}% 입니다.
          </span>
        </div>
      </div>

      {save.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{save.error.message}</span>
        </div>
      )}

      <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
        <button
          className="btn btn--ghost"
          onClick={() => save.mutate(results.voting_open)}
          disabled={save.isPending}
        >
          설정 저장
        </button>
        <button
          className={`btn ${results.voting_open ? 'btn--ghost' : 'btn--primary'}`}
          onClick={() => save.mutate(!results.voting_open)}
          disabled={save.isPending}
        >
          {results.voting_open ? '투표 닫기' : '투표 열기'}
        </button>
      </div>
    </div>
  );
}

function Criteria({
  festivalId,
  items,
  onChanged,
}: {
  festivalId: string;
  items: VoteCriterion[];
  onChanged: () => void;
}) {
  const [draft, setDraft] = useState({ label: '', max_score: '5', weight: '1' });

  const create = useMutation({
    mutationFn: () =>
      api.post(`/api/festivals/${festivalId}/criteria`, {
        label: draft.label.trim(),
        max_score: Number(draft.max_score) || 5,
        weight: Number(draft.weight) || 1,
        sort_order: items.length,
      }),
    onSuccess: () => {
      setDraft({ label: '', max_score: '5', weight: '1' });
      onChanged();
    },
  });

  const archive = useMutation({
    mutationFn: (cid: number) =>
      api.post(`/api/festivals/${festivalId}/criteria/${cid}/archive`),
    onSuccess: onChanged,
  });

  const totalWeight = items.reduce((sum, c) => sum + c.weight, 0);

  return (
    <div className="card stack" style={{ gap: 'var(--space-4)' }}>
      <div className="stack" style={{ gap: 4 }}>
        <p className="eyebrow">심사 항목</p>
        <p className="muted">
          심사위원이 이 항목마다 점수를 매깁니다. 가중치는 상대값이라 합이 100 일 필요가
          없습니다 — 항목 하나를 빼도 계산이 성립합니다.
        </p>
      </div>

      {items.length === 0 && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>심사 항목이 없습니다. 심사위원이 점수를 매길 수 없습니다.</span>
        </div>
      )}

      {items.length > 0 && (
        <div className="rcpt">
          {items.map((c) => (
            <div key={c.id} className="rcpt__row">
              <span className="rcpt__name">
                <strong>{c.label}</strong>
                <span>
                  {c.max_score}점 만점 · 가중치 {c.weight}
                  {totalWeight > 0 && ` (${((c.weight / totalWeight) * 100).toFixed(0)}%)`}
                </span>
              </span>
              <span className="rcpt__lead" aria-hidden="true" />
              <button
                className="btn btn--ghost"
                onClick={() => archive.mutate(c.id)}
                disabled={archive.isPending}
              >
                내리기
              </button>
            </div>
          ))}
        </div>
      )}

      <form
        className="row wrap"
        style={{ gap: 'var(--space-3)' }}
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.label.trim()) create.mutate();
        }}
      >
        <input
          value={draft.label}
          onChange={(e) => setDraft({ ...draft, label: e.target.value })}
          placeholder="항목 이름 (예: 창의성)"
          style={{ flex: '2 1 200px' }}
          aria-label="심사 항목 이름"
        />
        <input
          type="number"
          min={1}
          max={100}
          className="tabular"
          value={draft.max_score}
          onChange={(e) => setDraft({ ...draft, max_score: e.target.value })}
          style={{ width: 100 }}
          aria-label="만점"
        />
        <input
          type="number"
          min={1}
          className="tabular"
          value={draft.weight}
          onChange={(e) => setDraft({ ...draft, weight: e.target.value })}
          style={{ width: 100 }}
          aria-label="가중치"
        />
        <button className="btn btn--ghost" type="submit" disabled={create.isPending}>
          추가
        </button>
      </form>
    </div>
  );
}

function Results({
  festivalId,
  results,
  onChanged,
}: {
  festivalId: string;
  results: ExhibitionResults;
  onChanged: () => void;
}) {
  const upload = useMutation({
    mutationFn: (v: { exhibitId: number; file: File }) => {
      const body = new FormData();
      body.append('file', v.file);
      return uploadFile(`/api/festivals/${festivalId}/exhibits/${v.exhibitId}/poster`, body);
    },
    onSuccess: onChanged,
  });

  const archive = useMutation({
    mutationFn: (exhibitId: number) =>
      api.post(`/api/festivals/${festivalId}/exhibits/${exhibitId}/archive`),
    onSuccess: onChanged,
  });

  if (results.items.length === 0) {
    return (
      <div className="card state">
        <p className="eyebrow">아직 작품이 없습니다</p>
      </div>
    );
  }

  return (
    <div className="card stack" style={{ gap: 'var(--space-5)' }}>
      <div className="stack" style={{ gap: 4 }}>
        <p className="eyebrow">시상 집계</p>
        <p className="muted">
          최종 = 심사위원 {results.judge_weight_percent}% + 관객{' '}
          {results.audience_weight_percent}%. 관객 점수는 최다 득표를 100 으로 두고 환산합니다.
        </p>
      </div>

      {/* 집계를 흔드는 사실은 서버가 판정한다. 화면이 다시 계산하지 않는다. */}
      {results.warnings.map((w) => (
        <div className="notice notice--warn" key={w.code}>
          <span>⚠</span>
          <span>{w.message}</span>
        </div>
      ))}

      <div className="stack" style={{ gap: 'var(--space-4)' }}>
        {results.items.map((r, i) => (
          <div className="resultrow" key={r.exhibit.id}>
            <span className="resultrow__rank tabular">{i + 1}</span>

            <div className="stack" style={{ gap: 'var(--space-2)', minWidth: 0, flex: 1 }}>
              <div className="row wrap" style={{ gap: 'var(--space-2)', alignItems: 'baseline' }}>
                <span className="exhibit__no tabular">{r.exhibit.entry_no}</span>
                <strong style={{ fontSize: 'var(--text-h3)' }}>{r.exhibit.title}</strong>
                {r.exhibit.team_name && <span className="muted">{r.exhibit.team_name}</span>}
              </div>

              {/* 항목별 근거. 이게 없으면 최종 점수는 선언이다. */}
              <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
                {r.criteria.map((c) => (
                  <span key={c.criterion_id} className="critchip">
                    {c.label}{' '}
                    <b className="tabular">
                      {c.average === null ? '—' : c.average}
                    </b>
                    <span className="muted">/{c.max_score}</span>
                  </span>
                ))}
              </div>

              <span className="muted tabular">
                심사 {r.judge_score ?? '—'} (심사위원 {r.judge_count}명) · 관객{' '}
                {r.audience_score ?? '—'} ({r.votes}표)
              </span>

              <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
                <label className="btn btn--ghost" style={{ cursor: 'pointer' }}>
                  {r.exhibit.poster_url ? '포스터 교체' : '포스터 등록'}
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    hidden
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) upload.mutate({ exhibitId: r.exhibit.id, file });
                    }}
                  />
                </label>
                <button className="btn btn--ghost" onClick={() => archive.mutate(r.exhibit.id)}>
                  작품 내리기
                </button>
              </div>
            </div>

            <div className="resultrow__score">
              <b className="tabular">{r.final_score ?? '—'}</b>
              <small>최종</small>
            </div>
          </div>
        ))}
      </div>

      {upload.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{upload.error.message}</span>
        </div>
      )}
    </div>
  );
}
