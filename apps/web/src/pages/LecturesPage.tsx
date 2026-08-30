/** 특강 관리 — 공결이 걸린 강의의 출결을 운영하는 화면.
 *
 * **이 화면의 핵심 동작은 "지금 체크인" 버튼 하나입니다.** 강의 중 예고 없이
 * 누르면 90초 동안 열리고, 그 사이에 자리에 있는 사람만 찍을 수 있습니다.
 * 언제 누를지 알려주지 않는 것이 이 장치의 전부라, 화면 어디에도 다음 체크인
 * 예정 시각을 두지 않습니다 — 두는 순간 그 시각에만 앉아 있으면 됩니다.
 *
 * 명단은 여기서 봅니다. 학번이 나오는 유일한 화면이며, 그래서 운영자 경로에만
 * 있습니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Drawer } from '../components/Drawer';
import { Pips } from '../components/Pips';
import { useState } from 'react';
import { useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type {
  CheckpointToken,
  FestivalDetail,
  LectureSessionDetail,
  LectureSessionList,
  Roster,
} from '../api/types';

const EMPTY = {
  title: '',
  summary: '',
  speaker: '',
  affiliation: '',
  location: '',
  starts_at: '',
  ends_at: '',
  required_checkins: '2',
  grants_excused_absence: true,
  is_featured: false,
};

export function LecturesPage() {
  const { id = '' } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [adding, setAdding] = useState(false);

  const festival = useQuery({
    queryKey: ['festival', id],
    queryFn: () => api.get<FestivalDetail>(`/api/festivals/${id}`),
  });

  const lectures = useQuery({
    queryKey: ['lectures', id],
    queryFn: () => api.get<LectureSessionList>(`/api/festivals/${id}/lectures`),
    retry: false,
    // 체크인이 열려 있는 동안 찍은 사람 수가 늘어난다. 강의 중에는 자주 본다.
    refetchInterval: 10_000,
  });

  const reload = () => qc.invalidateQueries({ queryKey: ['lectures', id] });

  const create = useMutation({
    mutationFn: () =>
      api.post(`/api/festivals/${id}/lectures`, {
        title: form.title.trim(),
        summary: form.summary.trim() || null,
        speaker: form.speaker.trim() || null,
        affiliation: form.affiliation.trim() || null,
        location: form.location.trim() || null,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
        required_checkins: Number(form.required_checkins) || 2,
        grants_excused_absence: form.grants_excused_absence,
        is_featured: form.is_featured,
        is_active: true,
      }),
    onSuccess: () => {
      setForm(EMPTY);
      setAdding(false);
      reload();
    },
  });

  const items = lectures.data?.items ?? [];
  /** 열려 있는 특강. **id 로 들고 있는다** — 객체를 들면 체크인을 연 뒤
   *  목록이 갱신돼도 드로어는 옛 숫자를 계속 보여준다. */
  const [openId, setOpenId] = useState<number | null>(null);
  const openSession = items.find((s) => s.id === openId) ?? null;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <div className="stack" style={{ gap: 4 }}>
            <p className="eyebrow">특강 출결</p>
            <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>
              {festival.data?.name ?? '불러오는 중…'}
            </h1>
            <p className="muted">
              강의 중 예고 없이 체크인을 열면 그때 자리에 있는 사람만 찍을 수 있습니다.
            </p>
          </div>
          <button className="btn btn--primary btn--lg" onClick={() => setAdding((v) => !v)}>
            {adding ? '닫기' : '＋ 특강 추가'}
          </button>
        </div>
      </div>

      {adding && (
        <form
          className="card stack"
          style={{ gap: 'var(--space-4)' }}
          onSubmit={(e) => {
            e.preventDefault();
            if (form.title.trim() && form.starts_at && form.ends_at) create.mutate();
          }}
        >
          <div className="field">
            <label htmlFor="lec-title">
              주제 <span className="req">*</span>
            </label>
            <input
              id="lec-title"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="인공지능, 무엇이고 어디로 가고 있는가?"
            />
          </div>

          <div className="field">
            <label htmlFor="lec-summary">참가자는 이 강연에서 무엇을 듣게 되나요?</label>
            <textarea
              id="lec-summary"
              value={form.summary}
              maxLength={2000}
              onChange={(e) => setForm({ ...form, summary: e.target.value })}
              placeholder="강연을 선택하는 데 필요한 내용을 짧게 알려주세요."
            />
          </div>

          <div className="grid2">
            <div className="field">
              <label htmlFor="lec-speaker">강사</label>
              <input
                id="lec-speaker"
                value={form.speaker}
                onChange={(e) => setForm({ ...form, speaker: e.target.value })}
                placeholder="정송"
              />
            </div>
            <div className="field">
              <label htmlFor="lec-aff">소속</label>
              <input
                id="lec-aff"
                value={form.affiliation}
                onChange={(e) => setForm({ ...form, affiliation: e.target.value })}
                placeholder="KAIST"
              />
            </div>
          </div>

          <div className="grid2">
            <div className="field">
              <label htmlFor="lec-start">
                시작 <span className="req">*</span>
              </label>
              <input
                id="lec-start"
                type="datetime-local"
                value={form.starts_at}
                onChange={(e) => setForm({ ...form, starts_at: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="lec-end">
                종료 <span className="req">*</span>
              </label>
              <input
                id="lec-end"
                type="datetime-local"
                value={form.ends_at}
                onChange={(e) => setForm({ ...form, ends_at: e.target.value })}
              />
            </div>
          </div>

          <div className="grid2">
            <div className="field">
              <label htmlFor="lec-place">장소</label>
              <input
                id="lec-place"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder="공학관 1163호"
              />
            </div>
            <div className="field field--inline">
              <label htmlFor="lec-req">출석 인정 기준</label>
              <input
                id="lec-req"
                type="number"
                min={1}
                max={20}
                className="tabular"
                value={form.required_checkins}
                onChange={(e) => setForm({ ...form, required_checkins: e.target.value })}
              />
              <span className="unit">회</span>
              <span className="hint">
                열린 체크인 전부를 요구하지 마세요. 화장실·통신 문제로 한 번 놓치는 사람이
                반드시 생기고, 그때 공결이 날아가면 결국 손으로 예외를 만들게 됩니다.
              </span>
            </div>
          </div>

          <label className="row" style={{ gap: 'var(--space-2)' }}>
            <input
              type="checkbox"
              checked={form.grants_excused_absence}
              onChange={(e) =>
                setForm({ ...form, grants_excused_absence: e.target.checked })
              }
              style={{ width: 20, height: 20 }}
            />
            <span className="muted">공결 대상 강의 — 명단을 학교에 제출합니다.</span>
          </label>

          <label className="row" style={{ gap: 'var(--space-2)' }}>
            <input
              type="checkbox"
              checked={form.is_featured}
              onChange={(e) => setForm({ ...form, is_featured: e.target.checked })}
              style={{ width: 20, height: 20 }}
            />
            <span className="muted">처음 온 참가자에게 보여주기</span>
          </label>

          {create.error instanceof ApiError && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>{create.error.message}</span>
            </div>
          )}

          <button className="btn btn--primary btn--lg" type="submit" disabled={create.isPending}>
            {create.isPending ? '만드는 중…' : '특강 만들기'}
          </button>
        </form>
      )}

      {lectures.isLoading && <div className="skeleton" style={{ height: 160 }} />}

      {items.length === 0 && !lectures.isLoading && !adding && (
        <div className="card state">
          <p className="eyebrow">아직 특강이 없습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            특강을 만들면 강의 중 체크인을 열어 출석을 확인할 수 있습니다.
          </p>
        </div>
      )}

      {/* 카드를 세로로 쌓던 자리다. 특강이 여섯 개면 "어느 강의가 체크포인트가
          모자라지" 를 알려면 여섯 장을 다 읽어야 했다. 표는 한 열만 훑으면
          된다. */}
      {items.length > 0 && (
        <div className="card" style={{ padding: 'var(--space-4)' }}>
          <div className="tablewrap">
            <table className="table table--wrap">
              <thead>
                <tr>
                  <th>특강</th>
                  <th>일시</th>
                  <th>체크인</th>
                  <th className="num">찍은 사람</th>
                  <th className="num">출석 인정</th>
                  <th className="num"> </th>
                </tr>
              </thead>
              <tbody>
                {items.map((s) => {
                  const when = new Date(s.starts_at);
                  return (
                    <tr key={s.id}>
                      <td>
                        <button
                          type="button"
                          className="rowlink"
                          onClick={() => setOpenId(s.id)}
                        >
                          {s.title}
                        </button>
                        <span className="rowsub">
                          {[s.speaker, s.location].filter(Boolean).join(' · ') || '강사 미정'}
                          {s.grants_excused_absence ? ' · 공결 대상' : ''}
                        </span>
                      </td>
                      <td className="muted tabular">
                        {when.toLocaleString('ko-KR', {
                          month: 'numeric',
                          day: 'numeric',
                          weekday: 'short',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </td>
                      <td>
                        {/* 출튀를 잡는 자리다. 열린 체크인이 인정 기준에 못
                            미치면 그 강의는 아무도 출석으로 인정받지 못한다.
                            칸은 **인정 기준**이 총량이다 — 기준을 넘겨 연
                            체크인은 채울 칸이 없으므로 아래 줄에 따로 쓴다. */}
                        <Pips
                          filled={s.opened_checkpoints}
                          total={s.required_checkins}
                          tone={
                            s.opened_checkpoints >= s.required_checkins ? 'done' : 'caution'
                          }
                          label={`${s.title} 인정 기준 ${s.required_checkins}회 중 ${Math.min(
                            s.opened_checkpoints,
                            s.required_checkins,
                          )}회 열림`}
                        />
                        {s.opened_checkpoints > s.required_checkins && (
                          <span className="rowsub tabular">
                            열린 체크인 {s.opened_checkpoints}회
                          </span>
                        )}
                      </td>
                      <td className="num tabular">{s.attendee_count}</td>
                      <td className="num tabular">{s.met_count}</td>
                      <td className="num">
                        <button
                          className="btn btn--soft"
                          onClick={() => setOpenId(s.id)}
                        >
                          열기
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Drawer
        open={openSession != null}
        title={openSession?.title ?? ''}
        subtitle={
          openSession
            ? [
                openSession.speaker,
                openSession.location,
                openSession.grants_excused_absence ? '공결 대상' : null,
              ]
                .filter(Boolean)
                .join(' · ')
            : undefined
        }
        onClose={() => setOpenId(null)}
      >
        {openSession && (
          <LecturePanel
            key={openSession.id}
            festivalId={id}
            session={openSession}
            onChanged={reload}
          />
        )}
      </Drawer>
    </div>
  );
}

/** 드로어 안의 특강 패널. 체크인을 열고 명단을 본다.
 *
 * 예전에는 이 내용이 목록에 카드로 펼쳐져 있었고, 명단은 카드 아래로 다시
 * 펼쳐졌습니다. 특강 여섯 개에 명단을 둘만 펼쳐도 화면이 스크롤 지옥이
 * 됐습니다.
 */
function LecturePanel({
  festivalId,
  session,
  onChanged,
}: {
  festivalId: string;
  session: LectureSessionDetail;
  onChanged: () => void;
}) {
  const open = useMutation({
    mutationFn: () =>
      api.post<CheckpointToken>(
        `/api/festivals/${festivalId}/lectures/${session.id}/checkpoints`,
      ),
    onSuccess: (cp) => {
      onChanged();
      // 스크린에 띄울 QR 을 새 창으로 연다. 강의실 프로젝터가 그 창을 띄운다.
      window.open(
        `/festivals/${festivalId}/lectures/${session.id}/checkin/${cp.checkpoint_id}`,
        '_blank',
        'noopener,noreferrer',
      );
    },
  });

  const roster = useQuery({
    queryKey: ['roster', festivalId, session.id],
    queryFn: () => api.get<Roster>(`/api/festivals/${festivalId}/lectures/${session.id}/roster`),
    retry: false,
  });

  const when = new Date(session.starts_at);

  return (
    <div className="stack" style={{ gap: 'var(--space-4)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <span className="muted tabular">
          {when.toLocaleString('ko-KR', {
            month: 'long',
            day: 'numeric',
            weekday: 'short',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>

        {/* 강의 중 예고 없이 누른다. 이 버튼이 이 패널의 전부다. */}
        <button
          className="btn btn--primary btn--lg"
          onClick={() => open.mutate()}
          disabled={open.isPending}
        >
          {open.isPending ? '여는 중…' : '⚡ 지금 체크인'}
        </button>
      </div>

      <div className="lecstats">
        <div>
          <b className="tabular">{session.opened_checkpoints}</b>
          <small>열린 체크인</small>
        </div>
        <div>
          <b className="tabular">{session.attendee_count}</b>
          <small>한 번이라도 찍음</small>
        </div>
        <div>
          <b className="tabular">{session.met_count}</b>
          <small>{session.required_checkins}회 채움</small>
        </div>
      </div>

      <LectureConsumerMetadata
        festivalId={festivalId}
        session={session}
        onChanged={onChanged}
      />

      {open.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{open.error.message}</span>
        </div>
      )}

      {/* 드로어 안에서는 접을 이유가 없다. 이 패널을 여는 이유의 절반이
          명단이고, 한 번 더 눌러야 나오면 그 절반이 숨는다. */}
      {roster.isLoading && <div className="skeleton" style={{ height: 120 }} />}
      {roster.data && <RosterTable roster={roster.data} />}
    </div>
  );
}

function LectureConsumerMetadata({
  festivalId,
  session,
  onChanged,
}: {
  festivalId: string;
  session: LectureSessionDetail;
  onChanged: () => void;
}) {
  const [summary, setSummary] = useState(session.summary ?? '');
  const [featured, setFeatured] = useState(session.is_featured);

  const save = useMutation({
    mutationFn: () =>
      api.put(`/api/festivals/${festivalId}/lectures/${session.id}`, {
        title: session.title,
        summary: summary.trim() || null,
        speaker: session.speaker,
        affiliation: session.affiliation,
        location: session.location,
        starts_at: session.starts_at,
        ends_at: session.ends_at,
        required_checkins: session.required_checkins,
        grants_excused_absence: session.grants_excused_absence,
        is_featured: featured,
        is_active: session.is_active,
      }),
    onSuccess: onChanged,
  });

  return (
    <div className="card card--sunk stack" style={{ gap: 'var(--space-3)' }}>
      <p className="eyebrow">참가자 화면</p>
      <div className="field">
        <label htmlFor={`lecture-summary-${session.id}`}>강연 한 줄 소개</label>
        <textarea
          id={`lecture-summary-${session.id}`}
          value={summary}
          maxLength={2000}
          onChange={(event) => setSummary(event.target.value)}
          placeholder="모르면 비워 두어도 됩니다."
        />
      </div>
      <label className="row" style={{ gap: 'var(--space-2)' }}>
        <input
          type="checkbox"
          checked={featured}
          onChange={(event) => setFeatured(event.target.checked)}
          style={{ width: 20, height: 20 }}
        />
        <span className="muted">처음 온 참가자에게 보여주기</span>
      </label>
      {save.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{save.error.message}</span>
        </div>
      )}
      <button
        type="button"
        className="btn btn--ghost"
        onClick={() => save.mutate()}
        disabled={save.isPending}
      >
        {save.isPending ? '저장 중…' : '참가자 정보 저장'}
      </button>
    </div>
  );
}

/** 공결 명단. **학번이 나오는 유일한 화면이다.** */
function RosterTable({ roster }: { roster: Roster }) {
  if (roster.rows.length === 0) {
    return (
      <p className="muted">
        아직 아무도 찍지 않았습니다. 체크인을 열면 여기에 쌓입니다.
      </p>
    );
  }

  return (
    <div className="stack" style={{ gap: 'var(--space-3)' }}>
      <p className="hint">
        체크인을 한 번도 하지 않은 사람은 나오지 않습니다 — 이 강의에 온 적이 없다는
        뜻이고, 0회로 올리면 "왔는데 못 찍은 사람"과 구분되지 않습니다.
      </p>
      <div className="chart__table">
        <table>
          <thead>
            <tr>
              <th scope="col">학번</th>
              <th scope="col">참여 코드</th>
              <th scope="col">체크인</th>
              <th scope="col">출석</th>
              <th scope="col">재발급</th>
            </tr>
          </thead>
          <tbody>
            {roster.rows.map((r) => (
              <tr key={r.participant_code}>
                <th scope="row" className="tabular">
                  {r.student_no ?? '—'}
                </th>
                <td className="tabular">{r.participant_code}</td>
                <td className="tabular">
                  {r.checked} / {r.required}
                </td>
                <td>
                  <span className={`badge badge--${r.is_met ? 'stable' : 'risk'}`}>
                    <i />
                    {r.is_met ? '인정' : '미달'}
                  </span>
                </td>
                <td className="tabular">
                  {/* 남의 학번을 넣어 가로채려는 시도가 이 숫자로 드러난다. */}
                  {r.recovery_attempts > 0 ? `${r.recovery_attempts}회` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted tabular">
        {roster.met_count} / {roster.total}명 인정 · 열린 체크인 {roster.opened_checkpoints}회
      </p>
    </div>
  );
}
