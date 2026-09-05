/** 상단바의 **다른 사람 화면** 메뉴.
 *
 * FestaFlow 에는 기관 계정으로 로그인하는 운영자 말고도 여러 역할이 각자의
 * 화면을 씁니다. 관객, 부스 담당자, 심사위원, 공결을 확인하는 교수,
 * 강의실 스크린. 이 사람들은 대부분 **행사 당일 그 화면을 처음 엽니다.**
 *
 * 그래서 운영자가 미리 열어볼 수 있어야 합니다. 운영자가 이 화면들의 주인이자
 * 유일한 점검자이고, 미리 못 보면 잘못된 설정이 현장에서 발견됩니다.
 *
 * ## 전부 새 탭으로 연다
 *
 * 현장 화면은 오가는 화면이 아니라 **띄워 두는 화면**입니다. 부스 담당자는
 * 여덟 시간 서서 지급 화면을 보고, 강의실 스크린에는 체크인 QR 이 하루 종일
 * 떠 있습니다. 새 탭으로 열면 운영자도 자기 작업을 잃지 않습니다.
 *
 * ## 인증이 필요한 화면을 감추지 않는다
 *
 * 심사표와 부스 지급은 스태프 접근 코드가 필요합니다. 그렇다고 링크를 빼면
 * 운영자는 그 화면의 존재조차 잊습니다. 링크는 두고 **무엇이 더 필요한지**를
 * 함께 적습니다 — 코드는 «스태프» 화면에서 발급합니다.
 */

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

interface Screen {
  to: string;
  label: string;
  hint: string;
  /** 스태프 접근 코드가 있어야 열리는 화면. 감추지 않고 표시만 한다. */
  needsCode?: boolean;
}

interface Group {
  who: string;
  screens: Screen[];
}

function groupsFor(id: string): Group[] {
  return [
    {
      who: '관객 · 학생',
      screens: [
        {
          to: `/join/${id}`,
          label: '참여 화면',
          hint: '참여 코드를 받고 조각 보드를 채웁니다. 포스터 QR 이 여기로 옵니다',
        },
        {
          to: `/join/${id}/exhibition`,
          label: '전시 투표',
          hint: '작품을 보고 표를 던집니다',
        },
        {
          to: `/join/${id}/lectures`,
          label: '내 출결',
          hint: '학생이 자기 특강 출석을 확인합니다',
        },
      ],
    },
    {
      who: '부스 담당자',
      screens: [
        {
          to: `/booth/festivals/${id}`,
          label: '부스 지급',
          hint: '참여 코드를 확인하고 조각을 지급합니다',
          needsCode: true,
        },
        {
          to: `/festivals/${id}/booths/poster?all=1`,
          label: '부스 안내문',
          hint: '종이에 뽑아 부스에 붙입니다',
        },
      ],
    },
    {
      who: '심사위원',
      screens: [
        {
          to: `/festivals/${id}/judging`,
          label: '심사표',
          hint: '작품마다 항목별로 점수를 매깁니다',
          needsCode: true,
        },
      ],
    },
    {
      who: '운영 데스크',
      screens: [
        {
          to: `/festivals/${id}/claim`,
          label: '경품 수령대',
          hint: '당첨된 관객에게 실물을 건네고 수령을 기록합니다',
        },
      ],
    },
  ];
}

export function FieldScreensMenu({
  festivalId,
  who,
}: {
  festivalId: string;
  /** 역할 화면 안에서는 그 역할의 화면만 보여 준다. */
  who?: string;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const groups = groupsFor(festivalId).filter((group) => !who || group.who === who);

  // 바깥을 누르거나 ESC 를 누르면 닫힌다. 메뉴가 열린 채로 남아 아래 내용을
  // 가리는 것이 이 메뉴에서 가장 흔한 짜증이다.
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

  return (
    <div className="fieldmenu" ref={box}>
      <button
        type="button"
        className="fieldmenu__btn"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
      >
        {who ?? '다른 사람 화면'}
        <span aria-hidden>▾</span>
      </button>

      {open && (
        <div className="fieldmenu__pop" role="menu">
          <p className="fieldmenu__note">
            {who
              ? `${who} 화면 안에서 이동합니다.`
              : '행사 당일 이 사람들이 볼 화면입니다. 모두 새 탭에서 열립니다.'}
          </p>

          {groups.map((g) => (
            <div key={g.who} className="fieldmenu__group">
              <p className="fieldmenu__who">{g.who}</p>
              {g.screens.map((s) => (
                <Link
                  key={s.to}
                  to={s.to}
                  target={who ? undefined : '_blank'}
                  rel={who ? undefined : 'noreferrer'}
                  role="menuitem"
                  className="fieldmenu__item"
                  onClick={() => setOpen(false)}
                >
                  <strong>
                    {s.label}
                    {s.needsCode && <span className="fieldmenu__lock">접근 코드 필요</span>}
                  </strong>
                  <span>{s.hint}</span>
                </Link>
              ))}
            </div>
          ))}

          {/* 강의실 스크린은 여기서 못 연다. 체크인을 열어야 그 화면이
              생기기 때문이다 — 링크만 두면 눌러도 아무 데도 닿지 않는다. */}
          {!who && <p className="fieldmenu__note">
            강의실 체크인 스크린은 «특강 출결» 에서 체크인을 열 때 함께 뜹니다.{' '}
            <Link to={`/festivals/${festivalId}/staff`} onClick={() => setOpen(false)}>
              접근 코드 발급 →
            </Link>
          </p>}
        </div>
      )}
    </div>
  );
}
