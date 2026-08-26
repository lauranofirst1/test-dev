/** 오른쪽에서 밀려 나오는 편집 패널.
 *
 * ## 왜 드로어인가
 *
 * 목록을 표로 바꾸면 한 행이 한 줄이 되지만, 편집할 것들은 그 한 줄에 안
 * 들어갑니다. 예전처럼 카드마다 편집 폼을 펼쳐 두면 부스 스무 개에 폼 스무
 * 개가 세로로 쌓여, 1번 부스와 20번 부스를 비교하려면 스무 번 스크롤해야
 * 합니다.
 *
 * 드로어는 **목록을 남겨 둔 채** 편집합니다. 닫으면 보던 자리 그대로입니다 —
 * 별도 화면으로 보내면 돌아왔을 때 스크롤 위치도, 걸어 둔 필터도 잃습니다.
 *
 * ## 닫는 길을 여러 개 둔다
 *
 * ESC · 바깥 클릭 · 닫기 버튼. 편집 도중 갇히는 느낌이 이 패턴에서 가장 흔한
 * 짜증이고, 여기서 실수로 닫혀도 잃는 것은 저장 안 한 입력뿐입니다 —
 * 긴급 공지 덮개와 달리 닫히면 안 되는 이유가 없습니다.
 *
 * ## 열려 있는 동안 뒤는 스크롤하지 않는다
 *
 * 뒤가 따라 움직이면 드로어가 아니라 떠 있는 카드입니다. 닫을 때 원래 값을
 * 되돌려 놓습니다 — `''` 로 덮으면 다른 곳에서 걸어 둔 잠금이 풀립니다.
 */

import { useEffect, useRef } from 'react';

export function Drawer({
  open,
  title,
  subtitle,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;

    // 열기 전에 어디에 있었는지 기억한다. 닫고 나서 포커스가 문서 맨 위로
    // 튕기면 키보드 사용자는 목록의 그 자리를 다시 찾아 내려와야 한다.
    returnTo.current = document.activeElement as HTMLElement | null;
    panel.current?.focus();

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);

    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
      returnTo.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="drawer" role="presentation">
      {/* 바깥을 눌러도 닫힌다. 버튼이 아니라 판이므로 키보드로는 잡히지 않고,
          키보드에는 ESC 와 닫기 버튼이 있다. */}
      <div className="drawer__scrim" onClick={onClose} aria-hidden />

      <div
        className="drawer__panel"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={panel}
      >
        <header className="drawer__head">
          <div className="stack" style={{ gap: 2 }}>
            <h2 className="drawer__title">{title}</h2>
            {subtitle && <p className="muted">{subtitle}</p>}
          </div>
          <button
            type="button"
            className="iconbtn"
            onClick={onClose}
            aria-label="닫기"
          >
            ✕
          </button>
        </header>

        <div className="drawer__body">{children}</div>

        {footer && <footer className="drawer__foot">{footer}</footer>}
      </div>
    </div>
  );
}
