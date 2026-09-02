/** 축제 안에서 쓰는 사이드 레일.
 *
 * ## 왜 축제 안에서만 나오는가
 *
 * 축제 목록과 새 축제 만들기 화면에는 이 메뉴가 없습니다. 축제가 정해지지
 * 않았는데 "부스 관리 / 리포트" 를 띄우면 전부 죽은 링크가 되고, 죽은
 * 링크가 있는 메뉴는 없는 메뉴보다 나쁩니다.
 *
 * ## 순서는 여는 빈도를 따른다
 *
 * 예전에는 기획 → 준비 → 당일 → 사후, 즉 **제품이 스스로를 설명하는 순서**
 * 였습니다. 그 순서는 제품을 설명할 때 맞고, 매일 여는 화면으로는 맞지
 * 않았습니다 — 축제가 열리면 하루 종일 여는 화면이 목록 일곱 번째에 있었고,
 * 기획 단계에 몇 번 하고 마는 사전 진단이 첫 항목이었습니다.
 *
 * 지금은 자주 여는 것을 위로 올리고, 축제 한 번에 두어 번 여는 것
 * (스태프 발급 · 경품 수령)은 **설정** 으로 접었습니다.
 *
 * ## 여기 없는 것
 *
 * **부스 지급**(`/booth/festivals/:id`)은 이 메뉴에서 뺐습니다. 부스 담당자가
 * 여덟 시간 서서 쓰는 화면이라 기획자 껍데기를 쓰지 않는데, 메뉴에 있으면
 * 누르는 순간 레일이 사라지는 다른 세계로 튕겨 나갑니다. 상단바의
 * **현장 화면**(`FieldScreensMenu`)이 새 탭으로 엽니다.
 *
 * ## 접힘 상태는 기억한다
 *
 * 좁은 화면에서 접어 뒀는데 화면을 옮길 때마다 다시 펴지면, 옮길 때마다 다시
 * 접어야 합니다. 그건 금방 "이 메뉴 짜증난다" 가 됩니다.
 */

import { useState } from 'react';
import { Link, NavLink, useLocation, useNavigate, useParams } from 'react-router-dom';

interface Item {
  to: string;
  label: string;
  /** 접었을 때 남는 것. 글자가 사라지므로 이것만으로 구분돼야 한다. */
  icon: string;
  hint: string;
  details?: { label: string; to: string }[];
  /** 정확히 이 경로일 때만 활성. `/festivals/:id` 는 모든 하위 화면의
      접두사라, 이걸 안 주면 어느 화면에 있든 «현황» 이 켜져 있다. */
  end?: boolean;
}

interface Group {
  title: string;
  items: Item[];
}

function groupsFor(id: string): Group[] {
  return [
    {
      // 그룹 제목이 없는 첫 항목. 축제에 들어가면 여기가 열립니다.
      title: '',
      items: [
        {
          to: `/festivals/${id}`,
          label: '현황',
          icon: '▦',
          hint: '지금 무엇이 준비됐고 뭐가 남았는지',
          end: true,
        },
      ],
    },
    {
      title: '준비',
      items: [
        {
          to: `/festivals/${id}/diagnosis`,
          label: '사전 진단',
          icon: '◎',
          hint: '관광 데이터로 기획을 점검하고 고칩니다',
          details: [
            { label: '점수', to: `/festivals/${id}/diagnosis?tab=score` },
            { label: '기획 수정', to: `/festivals/${id}/diagnosis?tab=plan` },
          ],
        },
        {
          to: `/festivals/${id}/booths`,
          label: '부스 · 미션',
          icon: '▤',
          hint: '부스와 미션, 조각 보드를 만듭니다',
          details: [
            { label: '부스', to: `/festivals/${id}/booths?tab=booths` },
            { label: '조각 보드', to: `/festivals/${id}/booths?tab=board` },
            { label: '경품', to: `/festivals/${id}/booths?tab=prizes` },
          ],
        },
        {
          to: `/festivals/${id}/lectures`,
          label: '특강 출결',
          icon: '✓',
          hint: '공결이 걸린 특강의 체크인을 엽니다',
        },
        {
          to: `/festivals/${id}/exhibits`,
          label: '전시 심사',
          icon: '★',
          hint: '작품과 심사 항목을 관리합니다',
          details: [
            { label: '작품', to: `/festivals/${id}/exhibits?tab=works` },
            { label: '심사 설정', to: `/festivals/${id}/exhibits?tab=judging` },
          ],
        },
      ],
    },
    {
      title: '당일',
      items: [
        {
          to: `/festivals/${id}/dashboard`,
          label: '오늘',
          icon: '⚡',
          hint: '지금 참여가 어디로 몰리는지, 공지와 한시 포인트',
        },
      ],
    },
    {
      title: '마무리',
      items: [
        {
          to: `/festivals/${id}/report`,
          label: '리포트',
          icon: '▧',
          hint: '목표 대비 실제와 다음 축제 개선안',
        },
      ],
    },
    {
      // «설정» 이라는 한 화면을 따로 만들려다 그만뒀다. 정리하고 나니 남는
      // 것이 스태프 하나뿐이었기 때문이다 — 축제 정보는 사전 진단의
      // «기획 수정» 탭으로, 경품 설정은 부스·미션의 «경품» 탭으로, 심사
      // 항목은 전시 심사의 «심사 설정» 탭으로 갔다. 하나짜리 설정 화면은
      // 한 번 더 눌러야 닿는 자리를 만들 뿐이다.
      //
      // 경품 **수령대**(`/claim`)도 여기 없다. 수령대에 앉아 띄워 두는
      // 화면이라 상단바의 «현장 화면» 이 새 탭으로 연다.
      title: '설정',
      items: [
        {
          to: `/festivals/${id}/staff`,
          label: '스태프',
          icon: '⚿',
          hint: '부스 담당자와 심사위원을 발급합니다',
        },
      ],
    },
  ];
}

export function FestivalNav({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  /** 모바일 서랍에서 항목을 누르면 서랍이 닫혀야 한다. */
  onNavigate?: () => void;
}) {
  const { id = '' } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const items = groupsFor(id).flatMap((group) => group.items);

  return (
    <nav className="snav" aria-label="축제 메뉴">
      {items.map((item) => (
        <div
          key={item.to}
          className={`snav__group${item.details ? ' snav__group--menu' : ''}`}
          data-open={openGroup === item.to}
          onMouseEnter={() => item.details && setOpenGroup(item.to)}
          onMouseLeave={() => item.details && setOpenGroup(null)}
        >
          {item.details ? (
            <>
            <button
              type="button"
              className="snav__title snav__trigger"
              aria-haspopup="menu"
              aria-expanded={openGroup === item.to}
              onClick={() => {
                const first = item.details?.[0];
                if (first) navigate(first.to);
                setOpenGroup(null);
                onNavigate?.();
              }}
            >
              <span className="snav__icon" aria-hidden>{item.icon}</span>
              <span>{item.label}</span>
              <span className="snav__chevron" aria-hidden>⌄</span>
            </button>
              {item.details.map((detail) => (
                <Link
                  key={detail.to}
                  to={detail.to}
                  className="snav__item snav__detail"
                  data-current={`${location.pathname}${location.search}` === detail.to}
                  onClick={() => setOpenGroup(null)}
                >
                  <span className="snav__icon" aria-hidden>{item.icon}</span>
                  <span className="snav__label">{detail.label}</span>
                </Link>
              ))}
            </>
          ) : (
            <NavLink
              to={item.to}
              end={item.end}
              className="snav__item"
              onClick={() => {
                setOpenGroup(null);
                onNavigate?.();
              }}
              // 접었을 때는 글자가 없으므로 이름을 여기서 준다.
              title={collapsed ? `${item.label} — ${item.hint}` : item.hint}
              aria-label={collapsed ? item.label : undefined}
            >
              <span className="snav__icon" aria-hidden>
                {item.icon}
              </span>
              {!collapsed && (
                <span className="snav__copy">
                  <span className="snav__label">{item.label}</span>
                  <span className="snav__hint">{item.hint}</span>
                </span>
              )}
            </NavLink>
          )}
        </div>
      ))}
    </nav>
  );
}
