/** 축제 안에서 쓰는 사이드바 메뉴.
 *
 * ## 왜 축제 안에서만 나오는가
 *
 * 축제 목록과 새 축제 만들기 화면에는 이 메뉴가 없습니다. 축제가 정해지지
 * 않았는데 "부스 관리 / 사후 리포트" 를 띄우면 전부 죽은 링크가 되고, 죽은
 * 링크가 있는 메뉴는 없는 메뉴보다 나쁩니다.
 *
 * ## 메뉴 순서는 제품의 흐름을 따른다
 *
 * 기획 → 준비 → 당일 → 사후. 이건 이 제품이 스스로 설명하는 순서이고
 * (README 첫 줄), 운영자가 실제로 겪는 순서이기도 합니다. 알파벳순이나
 * 사용 빈도순으로 두면 "지금 어디쯤 와 있는가" 를 메뉴가 알려주지 못합니다.
 *
 * ## 접힘 상태는 기억한다
 *
 * 좁은 화면에서 접어 뒀는데 화면을 옮길 때마다 다시 펴지면, 옮길 때마다 다시
 * 접어야 합니다. 그건 금방 "이 메뉴 짜증난다" 가 됩니다.
 */

import { NavLink, useParams } from 'react-router-dom';

interface Item {
  to: string;
  label: string;
  /** 접었을 때 남는 것. 글자가 사라지므로 이것만으로 구분돼야 한다. */
  icon: string;
  hint: string;
}

interface Group {
  title: string;
  items: Item[];
}

/** 기획 → 준비 → 당일 → 사후. 제품이 스스로 설명하는 순서다. */
function groupsFor(id: string): Group[] {
  return [
    {
      title: '기획',
      items: [
        { to: `/festivals/${id}/diagnosis`, label: '사전 진단', icon: '◎', hint: '관광 데이터로 기획을 점검합니다' },
        { to: `/festivals/${id}/edit`, label: '기획 수정', icon: '✎', hint: '고치고 다시 진단하면 점수가 달라집니다' },
      ],
    },
    {
      title: '준비',
      items: [
        { to: `/festivals/${id}/booths`, label: '부스 · 미션', icon: '▤', hint: '부스와 미션, 조각 보드를 만듭니다' },
        { to: `/festivals/${id}/lectures`, label: '특강 출결', icon: '✓', hint: '공결이 걸린 특강의 체크인을 엽니다' },
        { to: `/festivals/${id}/exhibits`, label: '전시 심사', icon: '★', hint: '작품과 심사 항목을 관리합니다' },
        { to: `/festivals/${id}/staff`, label: '스태프', icon: '⚿', hint: '부스 담당자와 심사위원을 발급합니다' },
      ],
    },
    {
      title: '당일',
      items: [
        { to: `/festivals/${id}/dashboard`, label: '운영 대시보드', icon: '◈', hint: '참여 편중, 공지, 한시 추가 포인트' },
        { to: `/booth/festivals/${id}`, label: '부스 지급', icon: '◇', hint: '참여 코드를 받아 스탬프를 지급합니다' },
        { to: `/festivals/${id}/claim`, label: '경품 수령', icon: '⊞', hint: '당첨된 관객에게 실물을 건넵니다' },
      ],
    },
    {
      title: '사후',
      items: [
        { to: `/festivals/${id}/report`, label: '성과 리포트', icon: '▦', hint: '목표 대비 실제와 다음 축제 개선안' },
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

  return (
    <nav className="snav" aria-label="축제 메뉴">
      {groupsFor(id).map((group) => (
        <div key={group.title} className="snav__group">
          {/* 접으면 제목이 사라진다. 대신 구분선이 그 자리를 대신한다 —
              아이콘만 남은 목록이 한 덩어리면 어디가 어디인지 알 수 없다. */}
          {collapsed ? (
            <hr className="snav__rule" aria-hidden />
          ) : (
            <p className="snav__title">{group.title}</p>
          )}
          {group.items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className="snav__item"
              onClick={onNavigate}
              // 접었을 때는 글자가 없으므로 이름을 여기서 준다.
              title={collapsed ? `${item.label} — ${item.hint}` : item.hint}
              aria-label={collapsed ? item.label : undefined}
            >
              <span className="snav__icon" aria-hidden>
                {item.icon}
              </span>
              {!collapsed && <span className="snav__label">{item.label}</span>}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  );
}
