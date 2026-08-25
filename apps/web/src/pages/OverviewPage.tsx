/** 현황 — 축제에 들어가면 처음 보이는 화면.
 *
 * ## 왜 이 화면이 생겼나
 *
 * 예전에는 축제에 들어가면 **사전 진단**이 먼저 열렸습니다. 메뉴가 기획 →
 * 준비 → 당일 → 사후, 즉 제품이 스스로를 설명하는 순서였기 때문입니다.
 * 그 순서는 제품을 설명할 때 맞고, 매일 여는 화면으로는 맞지 않았습니다 —
 * 진단은 기획 단계에 몇 번 하고 마는 일입니다.
 *
 * 이 화면이 답하는 것은 하나입니다: **지금 무엇이 준비됐고 뭐가 남았나.**
 * "개요" 라고 부르지 않는 이유가 그것입니다 — 개요는 어느 대시보드에나 있는
 * 말이라 무엇의 개요인지 안 알아집니다.
 *
 * ## 막힌 것을 먼저 말한다
 *
 * 준비 현황 표는 **막힌 것 → 진행 중 → 끝난 것** 순으로 정렬합니다. 메뉴
 * 순서대로 두면 다 끝낸 항목을 지나 스크롤해야 막힌 것이 나옵니다. 이 화면을
 * 여는 이유는 "뭐가 남았지" 이지 "뭘 했지" 가 아닙니다.
 *
 * ## 진행은 칸으로 센다
 *
 * 진행바는 비율만 말하고 조각 격자는 개수를 말합니다. 이 제품에서 개수는
 * 실제로 의미가 있습니다 — 부스 수가 곧 조각 수이고, 안 찬 칸 두 개가
 * "QR 미발급 부스 2개" 입니다. 90% 막대로는 그게 둘인지 다섯인지 모릅니다.
 */

import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import { Pips } from '../components/Pips';
import type {
  BoothList,
  Diagnosis,
  ExhibitList,
  FestivalDetail,
  LectureSessionList,
  StaffList,
  StampBoardAdmin,
  VoteCriterion,
} from '../api/types';

type Stand = 'blocked' | 'doing' | 'done' | 'idle';

interface Row {
  key: string;
  title: string;
  detail: string;
  to: string;
  filled: number;
  total: number;
  /** 남은 일. 없으면 `—`. */
  left: string;
  stand: Stand;
}

/** 막힌 것부터. 이 화면을 여는 이유는 "뭐가 남았지" 다. */
const ORDER: Record<Stand, number> = { blocked: 0, doing: 1, idle: 2, done: 3 };

const STAND_LABEL: Record<Stand, string> = {
  blocked: '막힘',
  doing: '진행 중',
  done: '완료',
  idle: '시작 전',
};

const STAND_CLASS: Record<Stand, string> = {
  blocked: 'badge--risk',
  doing: 'badge--caution',
  done: 'badge--stable',
  idle: 'badge--none',
};

/** 개막까지 남은 일수. 축제 기간 중이면 며칠째인지, 끝났으면 끝난 지 며칠인지. */
function countdown(startsOn: string, endsOn: string) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(`${startsOn}T00:00:00`);
  const end = new Date(`${endsOn}T00:00:00`);
  const day = 86_400_000;
  const toStart = Math.round((start.getTime() - today.getTime()) / day);
  const fromEnd = Math.round((today.getTime() - end.getTime()) / day);

  if (toStart > 0) return { value: `D-${toStart}`, label: '개막까지', note: `${startsOn} 개막` };
  if (fromEnd > 0) return { value: `D+${fromEnd}`, label: '폐막 후', note: `${endsOn} 폐막` };
  const nth = Math.round((today.getTime() - start.getTime()) / day) + 1;
  return { value: `${nth}일차`, label: '오늘', note: `${startsOn} ~ ${endsOn}` };
}

export function OverviewPage() {
  const { id = '' } = useParams<{ id: string }>();

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
    queryKey: ['stamp-board', id],
    queryFn: () => api.get<StampBoardAdmin>(`/api/festivals/${id}/stamp-board`),
    retry: false,
  });
  const lectures = useQuery({
    queryKey: ['lectures', id],
    queryFn: () => api.get<LectureSessionList>(`/api/festivals/${id}/lectures`),
    retry: false,
  });
  const exhibits = useQuery({
    queryKey: ['exhibits', id],
    queryFn: () => api.get<ExhibitList>(`/api/festivals/${id}/exhibits`),
    retry: false,
  });
  const criteria = useQuery({
    queryKey: ['criteria', id],
    queryFn: () => api.get<VoteCriterion[]>(`/api/festivals/${id}/criteria`),
    retry: false,
  });
  const staff = useQuery({
    queryKey: ['staff', id],
    queryFn: () => api.get<StaffList>(`/api/festivals/${id}/staff`),
    retry: false,
  });
  const diagnosis = useQuery({
    queryKey: ['diagnosis-latest', id],
    queryFn: () => api.get<Diagnosis>(`/api/festivals/${id}/diagnoses/latest`),
    retry: false,
  });

  if (festival.error instanceof ApiError) {
    return (
      <div className="shell">
        <div className="card state">
          <p className="eyebrow">축제를 불러오지 못했습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>{festival.error.message}</p>
          <Link to="/" className="btn btn--primary">내 축제로</Link>
        </div>
      </div>
    );
  }

  if (!festival.data) {
    return (
      <div className="shell stack" style={{ gap: 'var(--space-4)' }}>
        <div className="skeleton" style={{ height: 92 }} />
        <div className="skeleton" style={{ height: 132 }} />
        <div className="skeleton" style={{ height: 260 }} />
      </div>
    );
  }

  const f = festival.data;
  const clock = countdown(f.starts_on, f.ends_on);

  const boothItems = booths.data?.items ?? [];
  const activeBooths = boothItems.filter((b) => b.is_active);
  const boothsWithoutMission = activeBooths.filter(
    (b) => b.missions.filter((m) => m.is_active).length === 0,
  );
  const tiles = board.data?.total_tiles ?? 0;

  const sessions = lectures.data?.items ?? [];
  const readySessions = sessions.filter((s) => s.opened_checkpoints >= s.required_checkins);

  const exhibitCount = exhibits.data?.total ?? 0;
  const criteriaCount = criteria.data?.length ?? 0;
  const staffCount = staff.data?.total ?? 0;

  const rawRows: Row[] = [
    {
      key: 'booths',
      title: '부스 · 미션',
      detail: tiles > 0 ? `${tiles}조각 보드 · ${board.data?.rows}×${board.data?.cols}` : '조각 보드 없음',
      to: `/festivals/${id}/booths`,
      filled: activeBooths.length,
      total: Math.max(tiles, activeBooths.length),
      left:
        boothsWithoutMission.length > 0
          ? `미션 없는 부스 ${boothsWithoutMission.length}개`
          : tiles > activeBooths.length
            ? `조각 ${tiles - activeBooths.length}칸이 빈 채로 남습니다`
            : '—',
      stand:
        activeBooths.length === 0
          ? 'blocked'
          : boothsWithoutMission.length > 0 || tiles > activeBooths.length
            ? 'doing'
            : 'done',
    },
    {
      key: 'lectures',
      title: '특강 출결',
      detail:
        sessions.length === 0
          ? '등록된 특강 없음'
          : `공결 대상 ${sessions.filter((s) => s.grants_excused_absence).length}개 세션`,
      to: `/festivals/${id}/lectures`,
      filled: readySessions.length,
      total: sessions.length,
      left:
        sessions.length === 0
          ? '—'
          : sessions.length - readySessions.length > 0
            ? `체크포인트 부족 ${sessions.length - readySessions.length}개`
            : '—',
      stand:
        sessions.length === 0
          ? 'idle'
          : readySessions.length === sessions.length
            ? 'done'
            : 'doing',
    },
    {
      key: 'exhibits',
      title: '전시 심사',
      detail:
        exhibitCount === 0 ? '등록된 작품 없음' : `작품 ${exhibitCount}점 · 심사 항목 ${criteriaCount}개`,
      to: `/festivals/${id}/exhibits`,
      filled: criteriaCount > 0 ? exhibitCount : 0,
      total: exhibitCount,
      // 작품이 0점이면 아직 시작 전이다. 이때 "심사 항목이 없다" 를 띄우면
      // 상태 알약(시작 전)과 문장이 서로 다른 말을 한다 — 먼저 할 일은
      // 항목 만들기가 아니라 작품 등록이다.
      left:
        exhibitCount === 0
          ? '작품이 등록되면 여기서 심사 준비를 확인합니다'
          : criteriaCount === 0
            ? '심사 항목이 없어 점수를 매길 수 없습니다'
            : '—',
      stand: exhibitCount === 0 ? 'idle' : criteriaCount === 0 ? 'blocked' : 'done',
    },
    {
      key: 'staff',
      title: '스태프',
      detail:
        staffCount === 0
          ? '발급된 스태프 없음'
          : `부스 담당 · 심사위원 합계 ${staffCount}명`,
      to: `/festivals/${id}/staff`,
      filled: staffCount,
      total: Math.max(staffCount, activeBooths.length),
      left:
        activeBooths.length > staffCount
          ? `부스 ${activeBooths.length}개에 스태프 ${staffCount}명`
          : '—',
      stand: staffCount === 0 ? 'blocked' : activeBooths.length > staffCount ? 'doing' : 'done',
    },
  ];
  const rows = [...rawRows].sort((a, b) => ORDER[a.stand] - ORDER[b.stand]);

  const score = diagnosis.data?.total_score;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">현황</p>
          <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>{f.name}</h1>
          <p className="muted">
            {f.region} · {f.venue} · {f.starts_on} ~ {f.ends_on}
          </p>
        </div>
        <Link to={`/festivals/${id}/dashboard`} className="btn btn--primary">
          오늘 화면 열기
        </Link>
      </div>

      {/* ── 스탯 넷 ── 표 위에 요약이 먼저 온다. 표부터 읽게 하면 매번 다 읽어야 한다. */}
      <div className="grid2">
        <Stat label={clock.label} value={clock.value} note={clock.note} />
        <Stat
          label="활성 부스"
          value={`${activeBooths.length}`}
          unit={tiles > 0 ? `/ ${tiles}조각` : undefined}
          note={boothItems.length > activeBooths.length ? `중지된 부스 ${boothItems.length - activeBooths.length}개` : '전부 운영 중'}
        />
        <Stat
          label="등록 작품"
          value={`${exhibitCount}`}
          unit="점"
          note={criteriaCount === 0 ? '심사 항목 미확정' : `심사 항목 ${criteriaCount}개`}
        />
        <Stat
          label="발급 스태프"
          value={`${staffCount}`}
          unit="명"
          note={staffCount === 0 ? '아직 아무도 못 들어옵니다' : '초대 링크 발급됨'}
        />
      </div>

      {/* ── 준비 현황 ── */}
      <section className="card stack" style={{ gap: 'var(--space-4)' }}>
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <h2 className="section">준비 현황</h2>
          <span className="muted">막힌 것부터 위에 옵니다</span>
        </div>

        <div className="tablewrap">
          <table className="table table--wrap">
            <thead>
              <tr>
                <th>항목</th>
                <th>진행</th>
                <th>남은 일</th>
                <th style={{ textAlign: 'right' }}>상태</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td>
                    <Link to={r.to} className="rowlink">
                      {r.title}
                    </Link>
                    <span className="rowsub">{r.detail}</span>
                  </td>
                  <td>
                    {r.total === 0 ? (
                      // 셀 것이 아직 없다. 빈 칸 하나를 그리면 "1개 중 0개" 로
                      // 읽혀서, 있지도 않은 목표가 있는 것처럼 보인다.
                      <span className="muted">—</span>
                    ) : (
                      <Pips
                        filled={r.filled}
                        total={r.total}
                        tone={r.stand === 'blocked' ? 'risk' : r.stand === 'done' ? 'done' : 'act'}
                        label={`${r.title} ${r.total}칸 중 ${r.filled}칸`}
                      />
                    )}
                  </td>
                  <td className="muted">{r.left}</td>
                  <td style={{ textAlign: 'right' }}>
                    <span className={`badge ${STAND_CLASS[r.stand]}`}>
                      <i aria-hidden />
                      {STAND_LABEL[r.stand]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── 진단 ── 점수 하나와 들어가는 문 하나. 자세한 것은 그 화면이 한다. */}
      <section className="card row wrap" style={{ justifyContent: 'space-between', gap: 'var(--space-4)' }}>
        <div className="stack" style={{ gap: 4 }}>
          <h2 className="section">사전 진단</h2>
          <p className="muted">
            {score == null
              ? '아직 진단하지 않았습니다. 한국관광공사 데이터로 기획 준비도를 매깁니다.'
              : '부스를 등록하면 예정값 대신 실제 구성으로 다시 매겨집니다.'}
          </p>
        </div>
        <div className="row" style={{ gap: 'var(--space-4)' }}>
          {score != null && (
            <p className="overview__score tabular">
              {score.toFixed(1)}
              <small>/ 100</small>
            </p>
          )}
          <Link to={`/festivals/${id}/diagnosis`} className="btn btn--soft">
            {score == null ? '진단하기' : '진단 열기'}
          </Link>
        </div>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
  note,
}: {
  label: string;
  value: string;
  unit?: string;
  note: string;
}) {
  return (
    <div className="card kpi">
      <p className="kpi__label">{label}</p>
      <p className="kpi__value tabular">
        {value}
        {unit && <small>{unit}</small>}
      </p>
      <p className="kpi__note muted">{note}</p>
    </div>
  );
}
