/** 공지가 실제로 보이는 곳 — 배너 · 긴급 덮개 · 미룸 알약.
 *
 * ## 접근성이 여기서 갈립니다
 *
 * 긴급 덮개는 화면을 가로막는 장치라, 잘못 만들면 **키보드·스크린리더 사용자가
 * 갇힙니다.** 그래서:
 *
 * - `role="alertdialog"` 로 알리고 제목·본문을 `aria-labelledby`/`describedby` 로 묶는다
 * - 열리는 순간 확인 버튼에 포커스를 준다
 * - Tab 이 덮개 밖으로 나가지 않게 가둔다(뒤에 있는 것은 지금 조작할 수 없다)
 * - 배경 스크롤을 잠근다
 * - **배경 클릭·ESC 로 닫히지 않는다.** 안전 공지를 실수로 닫는 쪽이 훨씬 위험하다
 *
 * ## 색만으로 알리지 않습니다
 *
 * 긴급을 빨간색으로만 표시하면 색각 이상 사용자와 직사광선 아래 화면에서
 * 사라집니다. 아이콘 · "긴급" 글자 · 색을 **함께** 씁니다.
 */

import { useEffect, useRef } from 'react';

import { useAnnouncements } from './AnnouncementProvider';

export function AnnouncementSurface() {
  const { banners, urgent, deferred, dismiss, acknowledge, acking } = useAnnouncements();

  return (
    <>
      {/* 미루는 중임을 감추지 않는다. 동작이 끝나면 곧바로 덮개가 올라온다. */}
      {deferred && (
        <div className="noticepill" role="status">
          <span aria-hidden>⚠</span> 중요 공지가 있습니다 — 지금 동작을 마치면 보여드립니다
        </div>
      )}

      {banners.length > 0 && (
        <div className="notices">
          {banners.map((a) => (
            <div
              key={a.id}
              className="notice-item"
              data-level={a.level}
              // 폴링으로 새 공지가 들어오면 스크린리더가 읽어야 한다.
              role="status"
            >
              <div className="notice-item__text">
                <strong>
                  {/* 색이 아니라 글자로도 등급을 알린다. */}
                  {a.level === 'urgent' && <span className="notice-item__tag">긴급</span>}
                  {a.title}
                </strong>
                <span>{a.body}</span>
              </div>
              <button
                className="notice-item__close"
                onClick={() => dismiss(a.id)}
                // 아이콘만 있는 버튼은 스크린리더에서 "버튼" 으로만 읽힌다.
                aria-label={`${a.title} 공지 닫기`}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {urgent && (
        <UrgentOverlay
          title={urgent.title}
          body={urgent.body}
          busy={acking}
          onAcknowledge={() => acknowledge(urgent.id)}
        />
      )}
    </>
  );
}

function UrgentOverlay({
  title,
  body,
  busy,
  onAcknowledge,
}: {
  title: string;
  body: string;
  busy: boolean;
  onAcknowledge: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const confirm = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // 열리자마자 확인 버튼으로 포커스를 옮긴다. 그러지 않으면 스크린리더
    // 사용자는 덮개가 떴다는 것만 듣고 어디를 눌러야 할지 알 수 없다.
    confirm.current?.focus();

    // 배경 스크롤 잠금. 덮개 뒤가 움직이면 덮개가 아니다.
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // 포커스를 덮개 안에 가둔다. 뒤에 있는 것은 지금 조작할 수 없어야 한다.
    const onKeyDown = (e: KeyboardEvent) => {
      // ESC 로 닫지 않는다. 안전 공지를 실수로 닫는 쪽이 훨씬 위험하다.
      if (e.key === 'Escape') {
        e.preventDefault();
        confirm.current?.focus();
        return;
      }
      if (e.key !== 'Tab' || !panel.current) return;
      const focusable = panel.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.body.style.overflow = previous;
    };
  }, []);

  return (
    <div className="urgent" role="presentation">
      <div
        ref={panel}
        className="urgent__panel"
        // alertdialog 는 "지금 답해야 하는 알림" 이다. dialog 보다 강하게 읽힌다.
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="urgent-title"
        aria-describedby="urgent-body"
      >
        <span className="urgent__icon" aria-hidden>
          ⚠
        </span>
        <p className="urgent__tag">긴급 공지</p>
        <h2 id="urgent-title" className="urgent__title">
          {title}
        </h2>
        <p id="urgent-body" className="urgent__body">
          {body}
        </p>
        {/* 확인 버튼은 화면 아래쪽에 둔다 — 축제장에서는 한 손으로 잡고
            엄지로 누른다. 위쪽에 두면 폰을 고쳐 잡아야 한다. */}
        <button
          ref={confirm}
          className="btn btn--primary btn--lg urgent__confirm"
          onClick={onAcknowledge}
          disabled={busy}
        >
          {busy ? '기록하는 중…' : '확인했습니다'}
        </button>
      </div>
    </div>
  );
}
