/** 부스 · 미션 관리 — 기획과 현장을 잇는 지점.
 *
 * 진단 화면이 "부스를 등록하면 예정값 대신 실제 구성으로 평가됩니다"라고 권하는데
 * 등록할 곳이 없었습니다. 권고와 행동이 같은 흐름 안에 있어야 합니다.
 *
 * 완성 가능성 경고는 여기서 다시 계산하지 않고 서버가 준 것을 그대로 씁니다.
 * 같은 규칙(조각 수 vs 지급 단위 수)이 화면에도 살면 반드시 어긋납니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Drawer } from '../components/Drawer';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ApiError, api, upload as uploadFile } from '../api/client';
import { ExperienceEditor } from '../components/ExperienceEditor';
import {
  type Grid,
  GridPlanPicker,
  gridBasisHint,
  useGridOptions,
} from '../components/GridPicker';
import { PrizeSettings } from '../components/PrizeSettings';
import type {
  BoardStyle,
  BoothDetail,
  BoothQrMode,
  BoothList,
  BoothType,
  BoothVerifyMode,
  FestivalDetail,
  GrantUnit,
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

const QR_MODES: { value: BoothQrMode; label: string; hint: string }[] = [
  {
    value: 'printed',
    label: '인쇄 QR',
    hint: '한 번 뽑아 붙이면 끝. 바뀌지 않습니다. 태블릿이 없는 부스의 기본값입니다.',
  },
  {
    value: 'rotating',
    label: '회전 QR',
    hint: '30초마다 바뀝니다. 현장에 와야만 찍을 수 있지만 태블릿·전원이 필요합니다.',
  },
];

const BOARD_STYLES: { value: BoardStyle; label: string; hint: string }[] = [
  { value: 'grid', label: '그림 퍼즐', hint: '그림 한 장을 격자로 쪼갭니다. 다 모으면 그림이 완성됩니다.' },
  { value: 'trail', label: '스탬프 지도', hint: '점선으로 이어진 길을 따라 도장을 찍습니다. 그림은 쓰지 않습니다.' },
];

const EXPERIENCE_LABEL: Record<string, string> = {
  stamp: '도착 확인',
  quiz: '퀴즈',
  info: '안내',
  photo: '사진',
  survey: '설문',
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

  /** 열려 있는 부스. 표에서 한 행을 누르면 드로어가 그 부스로 열린다. */
  const [openBoothId, setOpenBoothId] = useState<number | null>(null);

  /** 부스 · 조각 보드 · 경품은 서로 다른 일이라 한 화면에 세로로 쌓으면
   *  스크롤이 길어지기만 한다. 다만 **같은 축제의 같은 준비 작업**이라
   *  메뉴로 가르지는 않는다 — 탭이 맞는 자리다. */
  const [tab, setTab] = useState<'booths' | 'board' | 'prizes'>('booths');

  const items = booths.data?.items ?? [];
  const active = items.filter((b) => b.is_active);
  const missionCount = items.reduce((n, b) => n + b.missions.length, 0);
  // 지급 단위가 mission 이면 조각 수를 이 값과 견줘야 한다.
  const activeMissions = active.reduce(
    (n, b) => n + b.missions.filter((m) => m.is_active).length,
    0,
  );
  const joinUrl = `${window.location.origin}/join/${id}`;
  // 목록이 갱신되면 드로어도 새 값을 본다. id 만 들고 있는 이유다 —
  // 객체를 들고 있으면 저장한 값이 드로어에 반영되지 않는다.
  const openBooth = items.find((b) => b.id === openBoothId) ?? null;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="stack" style={{ gap: 'var(--space-2)' }}>
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

      <div className="tabs" role="tablist" aria-label="부스 준비">
        <button
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={tab === 'booths'}
          onClick={() => setTab('booths')}
        >
          부스<b className="tabs__num tabular">{items.length}</b>
        </button>
        <button
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={tab === 'board'}
          onClick={() => setTab('board')}
        >
          조각 보드
          {board.data && <b className="tabs__num tabular">{board.data.total_tiles}</b>}
        </button>
        <button
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={tab === 'prizes'}
          onClick={() => setTab('prizes')}
        >
          경품
        </button>
      </div>

      {tab === 'booths' && booths.isLoading && (
        <div className="skeleton" style={{ height: 140 }} />
      )}

      {tab === 'booths' && items.length === 0 && !booths.isLoading && (
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

      {/* 카드를 세로로 쌓던 자리다. 표는 열을 맞춰 주므로 "미션 없는 부스"
          같은 것이 한 열만 훑으면 보인다. */}
      {tab === 'booths' && items.length > 0 && (
        <div className="card" style={{ padding: 'var(--space-4)' }}>
          <div className="tablewrap">
            <table className="table table--wrap">
              <thead>
                <tr>
                  <th>부스</th>
                  <th>확인 방식</th>
                  <th>미션</th>
                  <th className="num">포인트</th>
                  <th className="num">상태</th>
                </tr>
              </thead>
              <tbody>
                {items.map((b) => {
                  const live = b.missions.filter((m) => m.is_active);
                  const points = live.reduce((n, m) => n + m.points, 0);
                  return (
                    <tr key={b.id} data-off={!b.is_active || undefined}>
                      <td>
                        <button
                          type="button"
                          className="rowlink"
                          onClick={() => setOpenBoothId(b.id)}
                        >
                          {b.name}
                        </button>
                        <span className="rowsub">
                          {b.location || '위치 미정'}
                          {b.manager_name ? ` · ${b.manager_name}` : ''}
                        </span>
                      </td>
                      <td className="muted">{VERIFY_LABEL[b.verify_mode]}</td>
                      <td>
                        {live.length === 0 ? (
                          // 미션이 없으면 이 부스는 지급할 것이 없다. 0 이라고만
                          // 쓰면 그 사실이 숫자에 묻힌다.
                          <span className="badge badge--risk">
                            <i aria-hidden />
                            지급할 것 없음
                          </span>
                        ) : (
                          <span className="tabular">{live.length}개</span>
                        )}
                      </td>
                      <td className="num tabular">{points}</td>
                      <td className="num">
                        {b.is_active ? (
                          <span className="badge badge--stable">
                            <i aria-hidden />
                            운영 중
                          </span>
                        ) : (
                          <span className="badge badge--none">
                            <i aria-hidden />
                            중지
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'board' && board.data && (
        <BoardSettings
          festivalId={id}
          board={board.data}
          boothCount={active.length}
          missionCount={activeMissions}
          onChanged={refresh}
        />
      )}

      {/* 뽑기는 조각 보드를 다 채운 관객이 돌린다. */}
      {tab === 'prizes' &&
        (items.length > 0 ? (
          <PrizeSettings festivalId={id} />
        ) : (
          <div className="card state">
            <p className="eyebrow">부스가 먼저입니다</p>
            <p className="lede" style={{ textAlign: 'center' }}>
              경품은 조각 보드를 다 채운 관객이 뽑습니다. 채울 보드가 없으면
              아무도 뽑기에 닿지 못합니다.
            </p>
          </div>
        ))}

      <Drawer
        open={openBooth != null}
        title={openBooth?.name ?? ''}
        subtitle={
          openBooth
            ? [
                VERIFY_LABEL[openBooth.verify_mode],
                openBooth.location,
                openBooth.is_active ? null : '중지됨',
              ]
                .filter(Boolean)
                .join(' · ')
            : undefined
        }
        onClose={() => setOpenBoothId(null)}
      >
        {openBooth && (
          <BoothPanel
            booth={openBooth}
            festivalId={id}
            onChanged={refresh}
            onToggle={() => toggle.mutate(openBooth)}
          />
        )}
      </Drawer>

      {tab === 'booths' && items.length > 0 && (
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

/** 드로어 안의 부스 편집 패널.
 *
 * 예전에는 이 내용이 목록에 카드로 펼쳐져 있었습니다. 부스 스무 개면 편집
 * 폼 스무 개가 세로로 쌓여, 1번과 20번을 비교하려면 스무 번 스크롤해야
 * 했습니다. 목록은 표가 되고 편집은 여기로 들어옵니다.
 */
function BoothPanel({
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
  const [editing, setEditing] = useState<number | null>(null);

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
    <div className="stack" style={{ gap: 'var(--space-4)' }}>
      {/* 확인 방식·위치는 드로어 머리말이 이미 말한다. 여기서는 같은 말을
          되풀이하지 않고, 이 자리에서만 할 수 있는 일(운영 중지)만 남긴다. */}
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <span className="muted">
          {[booth.type_label, booth.location].filter(Boolean).join(' · ') || '위치 미정'}
        </span>
        <button className="btn btn--ghost" onClick={onToggle}>
          {booth.is_active ? '부스 중지' : '부스 재개'}
        </button>
      </div>

      <div className="stack" style={{ gap: 'var(--space-2)' }}>
        {booth.missions.length === 0 && (
          <p className="muted">미션이 없습니다. 하나 이상 있어야 지급할 수 있습니다.</p>
        )}
        {booth.missions.map((m) => (
          <div key={m.id} className="stack" style={{ gap: 'var(--space-2)' }}>
            <div className="row wrap" style={{ justifyContent: 'space-between' }}>
              <div className="row" style={{ gap: 'var(--space-2)' }}>
                <span>{m.title}</span>
                <span className="badge badge--none">
                  {EXPERIENCE_LABEL[m.experience_type] ?? m.experience_type}
                </span>
              </div>
              <div className="row" style={{ gap: 'var(--space-2)' }}>
                <span className="badge badge--none tabular">
                  {m.points.toLocaleString()}점
                </span>
                <button
                  className="btn btn--ghost"
                  onClick={() => setEditing(editing === m.id ? null : m.id)}
                >
                  {editing === m.id ? '닫기' : '체험 설정'}
                </button>
              </div>
            </div>
            {editing === m.id && (
              <ExperienceEditor
                festivalId={festivalId}
                mission={m}
                onSaved={onChanged}
                onClose={() => setEditing(null)}
              />
            )}
          </div>
        ))}
      </div>

      {booth.verify_mode === 'participant_scan' && (
        <BoothQrSettings booth={booth} festivalId={festivalId} onChanged={onChanged} />
      )}

      {/* 체험은 참여자가 QR을 찍었을 때만 뜬다. 스태프 확인 부스에 설정해 두면
          아무도 보지 못하는 설정이 된다 — 저장은 되지만 그 사실을 말해 준다. */}
      {booth.verify_mode === 'staff_scan' &&
        booth.missions.some((m) => m.experience_type !== 'stamp') && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>
              이 부스는 스태프 확인 방식이라 체험 화면이 뜨지 않습니다. 관객이 직접 QR을
              찍게 하려면 확인 방식을 QR 스캔으로 바꾸세요.
            </span>
          </div>
        )}

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


/** 부스 QR 설정 — 인쇄냐 회전이냐. 기획서 E4.
 *
 * **인쇄가 기본입니다.** 지역 축제 천막 부스에 태블릿도 상시 전원도 없는 경우가
 * 대부분이라, 보안을 이유로 장비를 강요하면 그 기능은 안 쓰입니다.
 *
 * 대신 인쇄 QR 은 **현장 방문을 증명하지 않습니다.** 사진 한 장이면 어디서든
 * 같은 값이라 집에서도 지급받을 수 있습니다. 이 사실을 화면에서 분명히 말합니다 —
 * 운영자가 모르고 고르면 그 위에 운영 계획이 세워집니다.
 */
function BoothQrSettings({
  booth,
  festivalId,
  onChanged,
}: {
  booth: BoothDetail;
  festivalId: string;
  onChanged: () => void;
}) {
  const [confirmRotate, setConfirmRotate] = useState(false);

  const setMode = useMutation({
    mutationFn: (qr_mode: BoothQrMode) =>
      api.put<BoothDetail>(`/api/festivals/${festivalId}/booths/${booth.id}`, {
        name: booth.name,
        booth_type: booth.booth_type,
        type_label: booth.type_label,
        location: booth.location,
        manager_name: booth.manager_name,
        is_active: booth.is_active,
        verify_mode: booth.verify_mode,
        qr_mode,
        use_experience: booth.use_experience,
        experience_theme: {},
      }),
    onSuccess: onChanged,
  });

  const reissue = useMutation({
    mutationFn: () =>
      api.post(`/api/festivals/${festivalId}/booths/${booth.id}/qr/rotate`),
    onSuccess: () => {
      setConfirmRotate(false);
      onChanged();
    },
  });

  const printed = booth.qr_mode === 'printed';

  return (
    <div className="card card--sunk stack" style={{ gap: 'var(--space-4)' }}>
      <p className="eyebrow">부스 QR</p>

      <div className="exptypes">
        {QR_MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            className={`exptype${booth.qr_mode === m.value ? ' exptype--on' : ''}`}
            aria-pressed={booth.qr_mode === m.value}
            disabled={setMode.isPending}
            onClick={() => setMode.mutate(m.value)}
          >
            <b>{m.label}</b>
            <small>{m.hint}</small>
          </button>
        ))}
      </div>

      {/* 무엇을 포기하는지 고른 뒤에 말한다. 고르기 전 경고는 읽히지 않는다. */}
      {printed && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>
            인쇄 QR은 <b>현장에 왔다는 것을 증명하지 못합니다.</b> QR 사진이 돌면 축제장
            밖에서도 지급받을 수 있습니다. 경품이 걸린 축제라면 스태프 확인을 함께 두거나,
            사진이 돈다는 걸 알게 됐을 때 아래 <b>QR 다시 발행</b>으로 인쇄물을 무효화하세요.
          </span>
        </div>
      )}

      <div className="row wrap" style={{ gap: 'var(--space-3)' }}>
        <Link
          to={`/festivals/${festivalId}/booths/${booth.id}/qr`}
          className="btn btn--soft"
          target="_blank"
        >
          QR 화면 열기 ↗
        </Link>
        {printed && (
          <Link
            to={`/festivals/${festivalId}/booths/${booth.id}/poster`}
            className="btn btn--ghost"
            target="_blank"
          >
            인쇄용 안내문 ↗
          </Link>
        )}
        <button className="btn btn--ghost" onClick={() => setConfirmRotate(true)}>
          QR 다시 발행
        </button>
      </div>

      {confirmRotate && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span className="stack" style={{ gap: 'var(--space-3)' }}>
            <span>
              다시 발행하면 <b>이미 붙여 둔 인쇄물이 그 순간 무효가 됩니다.</b> 되돌릴 수
              없습니다. 새 안내문을 뽑아 붙여야 관객이 지급받을 수 있습니다.
            </span>
            <span className="row" style={{ gap: 'var(--space-3)' }}>
              <button
                className="btn btn--primary"
                onClick={() => reissue.mutate()}
                disabled={reissue.isPending}
              >
                {reissue.isPending ? '발행 중…' : '알겠습니다, 다시 발행'}
              </button>
              <button className="btn btn--ghost" onClick={() => setConfirmRotate(false)}>
                취소
              </button>
            </span>
          </span>
        </div>
      )}
    </div>
  );
}


/** 조각 보드 설정 — 그림 등록과 격자 선택.
 *
 * 격자를 바꾸면 타일 집합이 새로 생기고 참여자의 수집 진행이 초기화됩니다.
 * 되돌릴 수 없으므로 서버가 409 로 확인을 요구하고, 이 화면은 그 숫자를 그대로
 * 보여준 뒤에만 다시 보냅니다 — "정말?" 만 묻고 몇 명이 잃는지 말하지 않으면
 * 확인이 아니라 요식입니다.
 *
 * 그림만 바꾸는 것은 되돌릴 수 있어 확인 없이 즉시 반영합니다.
 */
function BoardSettings({
  festivalId,
  board,
  boothCount,
  missionCount,
  onChanged,
}: {
  festivalId: string;
  board: StampBoardAdmin;
  boothCount: number;
  missionCount: number;
  onChanged: () => void;
}) {
  const [grid, setGrid] = useState<Grid>({ rows: board.rows, cols: board.cols });
  const [grantUnit, setGrantUnit] = useState<GrantUnit>(board.grant_unit);
  const [style, setStyle] = useState<BoardStyle>(board.board_style);
  const [confirming, setConfirming] = useState<{ participants: number; revealed: number } | null>(
    null,
  );

  // 지급 기준을 바꾸면 후보의 근거가 되는 단위 수 자체가 달라진다. 화면에서 다시
  // 계산하지 않고 서버에 그 수로 다시 묻는다.
  const unitChanged = grantUnit !== board.grant_unit;
  const unitCount = grantUnit === 'booth' ? boothCount : missionCount;
  const unitLabel = grantUnit === 'booth' ? '부스' : '미션';
  const fetched = useGridOptions(unitCount);
  const options = fetched.data ?? board.grid_options;

  const changed =
    grid.rows !== board.rows ||
    grid.cols !== board.cols ||
    grantUnit !== board.grant_unit ||
    style !== board.board_style;

  const save = useMutation({
    mutationFn: (confirm: boolean) =>
      api.put(
        `/api/festivals/${festivalId}/stamp-board${confirm ? '?confirm=true' : ''}`,
        {
          rows: grid.rows,
          cols: grid.cols,
          reveal_mode: board.reveal_mode,
          grant_unit: grantUnit,
          board_style: style,
          image_url: board.image_url,
          complete_message: board.complete_message,
        },
      ),
    onSuccess: () => {
      setConfirming(null);
      onChanged();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'BOARD_RESET_REQUIRES_CONFIRMATION') {
        setConfirming({
          participants: Number(e.details.affected_participants ?? 0),
          revealed: Number(e.details.revealed_count ?? 0),
        });
      }
    },
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append('file', file);
      return uploadFile(`/api/festivals/${festivalId}/stamp-board/image`, body);
    },
    onSuccess: onChanged,
  });

  return (
    <div className="card stack" style={{ gap: 'var(--space-5)' }}>
      <div className="stack" style={{ gap: 4 }}>
        <p className="eyebrow">조각 보드</p>
        <h3 style={{ fontSize: 'var(--text-h3)' }}>관객이 모을 그림</h3>
        <p className="muted">{gridBasisHint(unitLabel, unitCount)}</p>
      </div>

      {/* 보여주는 방식 — 구조가 아니라 표현이라 바꿔도 진행이 초기화되지 않는다.
          그림 등록보다 **위**에 둔다. 지도를 골랐는데 그림 업로드가 먼저 보이면
          올린 그림이 어디에 쓰이는지 오해한다. */}
      <div className="field">
        <label>보여주는 방식</label>
        <div className="exptypes">
          {BOARD_STYLES.map((o) => (
            <button
              key={o.value}
              type="button"
              className={`exptype${style === o.value ? ' exptype--on' : ''}`}
              aria-pressed={style === o.value}
              onClick={() => setStyle(o.value)}
            >
              <b>{o.label}</b>
              <small>{o.hint}</small>
            </button>
          ))}
        </div>
        <span className="hint">
          같은 조각을 다르게 그릴 뿐입니다. 바꿔도 참여자의 수집 진행은 그대로입니다.
        </span>
      </div>

      {/* 지도를 골랐으면 그림은 쓰이지 않는다. 업로드 칸을 숨기지는 않는다 —
          이미 올린 그림이 사라진 것처럼 보이고, 되돌리려면 다시 올려야 한다고
          오해한다. 쓰이지 않는다는 사실만 말한다. */}
      {style === 'trail' && (
        <div className="notice notice--info">
          <span>ℹ</span>
          <span>
            스탬프 지도에서는 아래 그림이 화면에 나오지 않습니다. 등록해 둔 그림은
            그대로 남아 있어, 그림 퍼즐로 되돌리면 다시 쓰입니다.
          </span>
        </div>
      )}

      {/* 그림 등록 */}
      <div className="boardimg">
        <img className="boardimg__thumb" src={board.image_url} alt="현재 조각 보드 그림" />
        <div className="stack" style={{ gap: 'var(--space-2)' }}>
          <label className="btn btn--ghost" style={{ alignSelf: 'flex-start' }}>
            그림 등록
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) upload.mutate(file);
                e.target.value = '';
              }}
            />
          </label>
          <span className="hint">
            PNG · JPG · WEBP, 5MB 이하. 정사각형에 가까운 그림이 조각으로 잘 나뉩니다.
          </span>
          {upload.isPending && <span className="muted">올리는 중…</span>}
          {upload.error instanceof ApiError && (
            <span style={{ color: 'var(--color-danger)' }}>{upload.error.message}</span>
          )}
        </div>
      </div>

      {/* 격자 후보 */}
      <div className="stack" style={{ gap: 'var(--space-3)' }}>
        <p className="eyebrow">
          {style === 'trail' ? '몇 곳을 돌지 고르세요' : '몇 조각으로 나눌지 고르세요'}
        </p>
        <GridPlanPicker
          options={options}
          value={grid}
          onChange={setGrid}
          // 지도 모드에서는 그림을 넘기지 않는다. 미리보기가 화면에 나오지도 않을
          // 그림을 잘라 보여주면, 방금 "그림은 쓰지 않는다"고 한 말과 어긋난다.
          imageUrl={style === 'trail' ? undefined : board.image_url}
          unitLabel={unitLabel}
          unitCount={unitCount}
        />
      </div>

      <div className="field">
        <label htmlFor="grant-unit">조각을 주는 기준</label>
        <select
          id="grant-unit"
          value={grantUnit}
          onChange={(e) => setGrantUnit(e.target.value as GrantUnit)}
        >
          <option value="booth">부스당 1조각 — 여러 부스를 돌게 유도합니다</option>
          <option value="mission">미션마다 1조각 — 한 부스에서도 여러 조각을 줍니다</option>
        </select>
        {unitChanged && (
          <span className="hint">
            기준을 바꾸면 후보도 달라집니다. 저장하면 새 기준으로 다시 계산됩니다.
          </span>
        )}
      </div>

      {confirming && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>
            <strong>참여자 {confirming.participants}명</strong>이 모은 조각{' '}
            {confirming.revealed}개가 초기화됩니다. 기록은 이전 보드 버전으로 남지만 현재
            진행에는 반영되지 않습니다.
          </span>
        </div>
      )}

      {save.error instanceof ApiError &&
        save.error.code !== 'BOARD_RESET_REQUIRES_CONFIRMATION' && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>{save.error.message}</span>
          </div>
        )}

      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <span className="muted tabular">
          현재 {board.rows}×{board.cols} · {board.total_tiles}조각 (v{board.version})
          {changed && ` → ${grid.rows}×${grid.cols} · ${grid.rows * grid.cols}조각`}
        </span>
        <div className="row" style={{ gap: 'var(--space-3)' }}>
          {confirming && (
            <button
              className="btn btn--ghost"
              onClick={() => {
                setGrid({ rows: board.rows, cols: board.cols });
                setGrantUnit(board.grant_unit);
                setStyle(board.board_style);
                setConfirming(null);
              }}
            >
              취소
            </button>
          )}
          <button
            className="btn btn--primary"
            disabled={!changed || save.isPending}
            onClick={() => save.mutate(confirming !== null)}
          >
            {save.isPending ? '바꾸는 중…' : confirming ? '초기화하고 바꾸기' : '보드 바꾸기'}
          </button>
        </div>
      </div>
    </div>
  );
}
