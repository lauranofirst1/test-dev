/** 부스 · 미션 관리 — 기획과 현장을 잇는 지점.
 *
 * 진단 화면이 "부스를 등록하면 예정값 대신 실제 구성으로 평가됩니다"라고 권하는데
 * 등록할 곳이 없었습니다. 권고와 행동이 같은 흐름 안에 있어야 합니다.
 *
 * 완성 가능성 경고는 여기서 다시 계산하지 않고 서버가 준 것을 그대로 씁니다.
 * 같은 규칙(조각 수 vs 지급 단위 수)이 화면에도 살면 반드시 어긋납니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type {
  BoothDetail,
  BoothList,
  BoothType,
  BoothVerifyMode,
  FestivalDetail,
  MissionOut,
  StampBoardAdmin,
} from '../api/types';

const BOOTH_TYPES: { value: BoothType; label: string }[] = [
  { value: 'experience', label: '체험' },
  { value: 'food', label: '먹거리' },
  { value: 'performance', label: '공연' },
  { value: 'local_shop', label: '지역상점' },
  { value: 'information', label: '관광안내' },
  { value: 'etc', label: '기타' },
];

const VERIFY_LABEL: Record<BoothVerifyMode, string> = {
  staff_scan: '스태프 확인',
  participant_scan: 'QR 스캔',
};

const EMPTY = {
  name: '',
  booth_type: 'experience' as BoothType,
  type_label: '',
  location: '',
  manager_name: '',
  verify_mode: 'staff_scan' as BoothVerifyMode,
  mission_title: '',
  mission_points: '100',
};

export function BoothsPage() {
  const { id = '' } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [openForm, setOpenForm] = useState(false);

  const festival = useQuery({
    queryKey: ['festival', id],
    queryFn: () => api.get<FestivalDetail>(`/api/festivals/${id}`),
  });

  const booths = useQuery({
    queryKey: ['booths', id],
    queryFn: () => api.get<BoothList>(`/api/festivals/${id}/booths`),
    retry: false,
  });

  const board = useQuery({
    queryKey: ['board', id],
    queryFn: () => api.get<StampBoardAdmin>(`/api/festivals/${id}/stamp-board`),
    retry: false,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['booths', id] });
    qc.invalidateQueries({ queryKey: ['board', id] });
    // 부스 구성이 바뀌면 프로그램 균형 점수의 근거가 바뀐다.
    qc.invalidateQueries({ queryKey: ['diagnosis', id] });
  };

  const create = useMutation({
    mutationFn: () =>
      api.post(`/api/festivals/${id}/booths`, {
        name: form.name,
        booth_type: form.booth_type,
        type_label: form.type_label || null,
        location: form.location || null,
        manager_name: form.manager_name || null,
        verify_mode: form.verify_mode,
        first_mission: form.mission_title
          ? { title: form.mission_title, points: Number(form.mission_points) || 0 }
          : null,
      }),
    onSuccess: () => {
      setForm(EMPTY);
      setOpenForm(false);
      refresh();
    },
  });

  const toggle = useMutation({
    mutationFn: (b: BoothDetail) =>
      api.put(`/api/festivals/${id}/booths/${b.id}`, {
        name: b.name,
        booth_type: b.booth_type,
        type_label: b.type_label,
        location: b.location,
        manager_name: b.manager_name,
        verify_mode: b.verify_mode,
        qr_mode: b.qr_mode,
        use_experience: b.use_experience,
        is_active: !b.is_active,
      }),
    onSuccess: refresh,
  });

  const items = booths.data?.items ?? [];
  const active = items.filter((b) => b.is_active);
  const missionCount = items.reduce((n, b) => n + b.missions.length, 0);
  const joinUrl = `${window.location.origin}/join/${id}`;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        <Link to={`/festivals/${id}/diagnosis`} className="muted">
          ← 사전 진단
        </Link>
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <div className="stack" style={{ gap: 4 }}>
            <p className="eyebrow">부스 · 미션</p>
            <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>
              {festival.data?.name ?? '불러오는 중…'}
            </h1>
            <p className="muted tabular">
              활성 부스 {active.length}개 · 미션 {missionCount}개
            </p>
          </div>
          <button className="btn btn--primary btn--lg" onClick={() => setOpenForm((v) => !v)}>
            {openForm ? '접기' : '＋ 부스 추가'}
          </button>
        </div>
      </div>

      {board.data?.warnings.map((w) => (
        <div className="notice notice--warn" key={String(w.code)}>
          <span>⚠</span>
          <span>{String(w.message)}</span>
        </div>
      ))}

      {openForm && (
        <form
          className="card stack"
          style={{ gap: 'var(--space-5)' }}
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <h2 className="section">새 부스</h2>

          <div className="field">
            <label htmlFor="b-name">
              부스명 <span className="req">*필수</span>
            </label>
            <input
              id="b-name"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="막국수 체험존"
            />
          </div>

          <div className="grid2">
            <div className="field">
              <label htmlFor="b-type">부스 유형</label>
              <select
                id="b-type"
                value={form.booth_type}
                onChange={(e) =>
                  setForm({ ...form, booth_type: e.target.value as BoothType })
                }
              >
                {BOOTH_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              <span className="hint">진단의 "유형 다양성" 점수가 이 값으로 계산됩니다</span>
            </div>
            <div className="field">
              <label htmlFor="b-loc">위치</label>
              <input
                id="b-loc"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder="A구역 3번"
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="b-verify">확인 방식</label>
            <select
              id="b-verify"
              value={form.verify_mode}
              onChange={(e) =>
                setForm({ ...form, verify_mode: e.target.value as BoothVerifyMode })
              }
            >
              <option value="staff_scan">스태프 확인 — 스태프가 참여자 코드를 확인</option>
              <option value="participant_scan">QR 스캔 — 참여자가 부스 QR을 스캔</option>
            </select>
            <span className="hint">
              실제 활동이 있는 부스는 스태프 확인, 순회 스탬프는 QR 스캔이 맞습니다
            </span>
          </div>

          <div className="grid2">
            <div className="field">
              <label htmlFor="m-title">첫 미션</label>
              <input
                id="m-title"
                value={form.mission_title}
                onChange={(e) => setForm({ ...form, mission_title: e.target.value })}
                placeholder="막국수 반죽 체험"
              />
              <span className="hint">미션이 없으면 지급할 것이 없습니다</span>
            </div>
            <div className="field">
              <label htmlFor="m-points">지급 포인트</label>
              <input
                id="m-points"
                type="number"
                min={0}
                className="tabular"
                value={form.mission_points}
                onChange={(e) => setForm({ ...form, mission_points: e.target.value })}
              />
            </div>
          </div>

          {create.error instanceof ApiError && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>{create.error.message}</span>
            </div>
          )}

          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button type="submit" className="btn btn--primary btn--lg" disabled={create.isPending}>
              {create.isPending ? '만드는 중…' : '부스 만들기'}
            </button>
          </div>
        </form>
      )}

      {booths.isLoading && <div className="skeleton" style={{ height: 140 }} />}

      {items.length === 0 && !booths.isLoading && (
        <div className="card state">
          <p className="eyebrow">아직 부스가 없습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            부스를 등록하면 진단이 예정값 대신 <strong>실제 구성</strong>으로 평가되고,
            현장에서 참여를 측정할 수 있습니다.
          </p>
          <button className="btn btn--primary btn--lg" onClick={() => setOpenForm(true)}>
            첫 부스 만들기
          </button>
        </div>
      )}

      {items.map((b) => (
        <BoothCard
          key={b.id}
          booth={b}
          festivalId={id}
          onChanged={refresh}
          onToggle={() => toggle.mutate(b)}
        />
      ))}

      {items.length > 0 && (
        <div className="card card--sunk stack" style={{ gap: 'var(--space-3)' }}>
          <p className="eyebrow">관객 참여 링크</p>
          <p className="muted">
            이 주소를 포스터·안내판의 QR로 만들면 관객이 참여 코드를 받고 조각을 모읍니다.
          </p>
          <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
            <code className="joinurl">{joinUrl}</code>
            <button
              className="btn btn--ghost"
              onClick={() => navigator.clipboard?.writeText(joinUrl)}
            >
              주소 복사
            </button>
            <a className="btn btn--ghost" href={joinUrl} target="_blank" rel="noreferrer">
              관객 화면 열기 ↗
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

function BoothCard({
  booth,
  festivalId,
  onChanged,
  onToggle,
}: {
  booth: BoothDetail;
  festivalId: string;
  onChanged: () => void;
  onToggle: () => void;
}) {
  const [title, setTitle] = useState('');
  const [points, setPoints] = useState('100');

  const addMission = useMutation({
    mutationFn: () =>
      api.post<MissionOut>(`/api/festivals/${festivalId}/missions`, {
        title,
        points: Number(points) || 0,
        booth_id: booth.id,
      }),
    onSuccess: () => {
      setTitle('');
      onChanged();
    },
  });

  return (
    <div className="card stack" style={{ gap: 'var(--space-4)', opacity: booth.is_active ? 1 : 0.6 }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 2 }}>
          <div className="row" style={{ gap: 'var(--space-3)' }}>
            <h3 style={{ fontSize: 'var(--text-h3)' }}>{booth.name}</h3>
            <span className="badge badge--none">{VERIFY_LABEL[booth.verify_mode]}</span>
            {!booth.is_active && <span className="badge badge--risk">중지</span>}
          </div>
          <span className="muted">
            {[booth.type_label, booth.location].filter(Boolean).join(' · ') || '위치 미정'}
          </span>
        </div>
        <button className="btn btn--ghost" onClick={onToggle}>
          {booth.is_active ? '중지' : '재개'}
        </button>
      </div>

      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        {booth.missions.length === 0 && (
          <p className="muted">미션이 없습니다. 하나 이상 있어야 지급할 수 있습니다.</p>
        )}
        {booth.missions.map((m) => (
          <div key={m.id} className="row" style={{ justifyContent: 'space-between' }}>
            <span>{m.title}</span>
            <span className="badge badge--none tabular">{m.points.toLocaleString()}점</span>
          </div>
        ))}
      </div>

      <form
        className="row wrap"
        style={{ gap: 'var(--space-3)' }}
        onSubmit={(e) => {
          e.preventDefault();
          if (title.trim()) addMission.mutate();
        }}
      >
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="미션 추가"
          style={{ flex: '1 1 200px' }}
          aria-label={`${booth.name} 미션 제목`}
        />
        <input
          type="number"
          min={0}
          className="tabular"
          value={points}
          onChange={(e) => setPoints(e.target.value)}
          style={{ width: 100 }}
          aria-label={`${booth.name} 미션 포인트`}
        />
        <button className="btn btn--ghost" type="submit" disabled={addMission.isPending}>
          추가
        </button>
      </form>
    </div>
  );
}
