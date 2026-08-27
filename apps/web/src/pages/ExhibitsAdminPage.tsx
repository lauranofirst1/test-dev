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

import { Drawer } from '../components/Drawer';
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
  /** 작품 목록과 심사 설정은 여는 시점이 다르다 — 작품은 계속 들어오고,
   *  항목·가중치는 행사 전에 한 번 정하고 만다. 한 화면에 세로로 쌓으면
   *  매번 설정을 지나 스크롤해야 작품이 나온다. */
  const [tab, setTab] = useState<'works' | 'judging'>('works');
  /** 열려 있는 작품. id 로 든다 — 포스터를 올린 뒤 목록이 갱신돼야 한다. */
  const [openId, setOpenId] = useState<number | null>(null);

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
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <div className="stack" style={{ gap: 4 }}>
            <p className="eyebrow">전시 심사</p>
            <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>
              {festival.data?.name ?? '불러오는 중…'}
            </h1>
          </div>
          <Link to={`/festivals/${id}/judging`} className="btn btn--soft" target="_blank">
            심사표 열기 ↗
          </Link>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="전시 심사">
        <button
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={tab === 'works'}
          onClick={() => setTab('works')}
        >
          작품
          {results.data && (
            <b className="tabs__num tabular">{results.data.items.length}</b>
          )}
        </button>
        <button
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={tab === 'judging'}
          onClick={() => setTab('judging')}
        >
          심사 설정
        </button>
      </div>

      {/* 심사 항목이 없으면 심사위원이 열 화면이 비어 있다. 작품 탭에서도
          보이게 둔다 — 설정 탭에 들어가야만 보이면 아무도 모른 채 행사일이
          온다. */}
      {tab === 'works' && (criteria.data?.length ?? 0) === 0 && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>
            <strong>심사 항목이 없습니다.</strong> 항목을 만들어야 심사위원이 점수를
            매길 수 있습니다.{' '}
            <button className="linkish" onClick={() => setTab('judging')}>
              심사 설정으로
            </button>
          </span>
        </div>
      )}

      {tab === 'judging' && results.data && (
        <Settings festivalId={id} results={results.data} onChanged={reload} />
      )}

      {tab === 'judging' && (
        <Criteria festivalId={id} items={criteria.data ?? []} onChanged={reload} />
      )}

      {/* 작품 등록 */}
      {tab === 'works' && (
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
      )}

      {tab === 'works' && results.data && (
        <Results
          festivalId={id}
          results={results.data}
          onChanged={reload}
          openId={openId}
          onOpen={setOpenId}
        />
      )}
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
        <p className="eyebrow" data-tour="exhibit-criteria">심사 항목</p>
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

      {/* 추가가 실패하면(권한 없음·중복 이름) 반드시 말해야 한다. 조용히 삼키면
          입력값은 그대로 남고 목록만 안 늘어나 "눌러도 아무 일이 없다" 가 된다. */}
      {create.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{create.error.message}</span>
        </div>
      )}

      <form
        className="row wrap"
        style={{ gap: 'var(--space-3)', alignItems: 'flex-end' }}
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.label.trim()) create.mutate();
        }}
      >
        {/* 숫자 칸에 보이는 라벨을 준다. 5 와 1 만 놓여 있으면 무엇을 넣는
            칸인지 화면만 보고는 알 수 없다 — aria-label 은 눈으로 못 읽는다. */}
        <div className="field" style={{ flex: '2 1 200px' }}>
          <label htmlFor="crit-label">항목 이름</label>
          <input
            id="crit-label"
            value={draft.label}
            onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            placeholder="창의성"
          />
        </div>
        <div className="field" style={{ width: 116 }}>
          <label htmlFor="crit-max">만점</label>
          <input
            id="crit-max"
            type="number"
            min={1}
            max={100}
            className="tabular"
            value={draft.max_score}
            onChange={(e) => setDraft({ ...draft, max_score: e.target.value })}
          />
        </div>
        <div className="field" style={{ width: 116 }}>
          <label htmlFor="crit-weight">가중치</label>
          <input
            id="crit-weight"
            type="number"
            min={1}
            className="tabular"
            value={draft.weight}
            onChange={(e) => setDraft({ ...draft, weight: e.target.value })}
          />
        </div>
        <button className="btn btn--ghost" type="submit" disabled={create.isPending}>
          {create.isPending ? '추가 중…' : '추가'}
        </button>
      </form>
    </div>
  );
}

function Results({
  festivalId,
  results,
  onChanged,
  openId,
  onOpen,
}: {
  festivalId: string;
  results: ExhibitionResults;
  onChanged: () => void;
  openId: number | null;
  onOpen: (id: number | null) => void;
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

  const open = results.items.find((r) => r.exhibit.id === openId) ?? null;

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
        <p className="eyebrow" data-tour="exhibit-award">시상 집계</p>
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

      {/* 작품마다 카드를 세로로 쌓던 자리다. 31점이면 31장이었고, 1위와 5위의
          최종 점수를 비교하려면 그 사이를 다 지나야 했다. 표는 점수 열이
          세로로 서므로 눈이 한 번에 훑는다. */}
      <div className="tablewrap">
        <table className="table table--wrap">
          <thead>
            <tr>
              <th className="num">순위</th>
              {/* 표의 남는 폭은 이 칸이 가져간다 — 나머지는 내용만큼만. */}
              <th className="wide">작품</th>
              <th className="num">심사</th>
              <th className="num">관객</th>
              <th className="num">최종</th>
              <th className="num">포스터</th>
            </tr>
          </thead>
          <tbody>
            {results.items.map((r, i) => (
              <tr key={r.exhibit.id}>
                <td className="num tabular">{i + 1}</td>
                <td className="wide">
                  <button type="button" className="rowlink" onClick={() => onOpen(r.exhibit.id)}>
                    <span className="exhibit__no tabular">{r.exhibit.entry_no}</span>
                    {r.exhibit.title}
                  </button>
                  <span className="rowsub">
                    {r.exhibit.team_name || '팀명 없음'}
                    {r.exhibit.location ? ` · ${r.exhibit.location}` : ''}
                  </span>
                </td>
                <td className="num tabular">
                  {r.judge_score ?? '—'}
                  <span className="rowsub">{r.judge_count}명</span>
                </td>
                <td className="num tabular">
                  {r.audience_score ?? '—'}
                  <span className="rowsub">{r.votes}표</span>
                </td>
                <td className="num tabular">
                  <strong>{r.final_score ?? '—'}</strong>
                  {/* 한쪽만으로 낸 점수는 그렇다고 말한다. 심사 0명인데 최종
                      100 이 그냥 놓여 있으면 만점으로 읽히지만, 실제로는
                      관객 표 하나가 최다 득표라 100 이 된 것이다. */}
                  {r.final_score !== null && r.judge_score === null && (
                    <span className="rowsub">관객 점수만</span>
                  )}
                  {r.final_score !== null && r.audience_score === null && (
                    <span className="rowsub">심사 점수만</span>
                  )}
                </td>
                <td className="num">
                  {r.exhibit.poster_url ? (
                    <span className="badge badge--stable">
                      <i aria-hidden />
                      있음
                    </span>
                  ) : (
                    <span className="badge badge--none">
                      <i aria-hidden />
                      없음
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Drawer
        open={open != null}
        title={open ? `${open.exhibit.entry_no} ${open.exhibit.title}` : ''}
        subtitle={open?.exhibit.team_name ?? undefined}
        onClose={() => onOpen(null)}
      >
        {open && (
          <div className="stack" style={{ gap: 'var(--space-4)' }}>
            {/* 항목별 근거. 이게 없으면 최종 점수는 선언이다. */}
            <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
              {open.criteria.map((c) => (
                <span key={c.criterion_id} className="critchip">
                  {c.label}{' '}
                  <b className="tabular">{c.average === null ? '—' : c.average}</b>
                  <span className="muted">/{c.max_score}</span>
                </span>
              ))}
            </div>

            <p className="muted tabular">
              심사 {open.judge_score ?? '—'} (심사위원 {open.judge_count}명) · 관객{' '}
              {open.audience_score ?? '—'} ({open.votes}표) · 최종{' '}
              <strong>{open.final_score ?? '—'}</strong>
            </p>

            {open.exhibit.summary && <p>{open.exhibit.summary}</p>}

            {open.exhibit.poster_url && (
              <img
                src={open.exhibit.poster_url}
                alt={`${open.exhibit.title} 포스터`}
                className="posterthumb"
              />
            )}

            <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
              <label className="btn btn--soft" style={{ cursor: 'pointer' }}>
                {open.exhibit.poster_url ? '포스터 교체' : '포스터 등록'}
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  hidden
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) upload.mutate({ exhibitId: open.exhibit.id, file });
                  }}
                />
              </label>
              <button
                className="btn btn--ghost"
                onClick={() => {
                  archive.mutate(open.exhibit.id);
                  onOpen(null);
                }}
              >
                작품 내리기
              </button>
            </div>
          </div>
        )}
      </Drawer>

      {upload.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{upload.error.message}</span>
        </div>
      )}
    </div>
  );
}
