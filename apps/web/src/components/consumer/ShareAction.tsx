import { useId, useState } from 'react';

import {
  performShare,
  shareFallbackText,
  type ShareOutcome,
  type ShareRequest,
} from '../../lib/share';

interface ShareActionProps extends ShareRequest {
  label: string;
  className?: string;
}

export function ShareAction({ data, fallbackText, label, className = 'btn btn--ghost' }: ShareActionProps) {
  const [pending, setPending] = useState(false);
  const [outcome, setOutcome] = useState<ShareOutcome | null>(null);
  const manualCopyId = useId();
  const request = { data, fallbackText };

  const share = () => {
    if (pending) return;
    setOutcome(null);
    setPending(true);
    // Do not put an await before this call: navigator.share must retain the click gesture.
    void performShare(request)
      .then((result) => setOutcome(result.kind === 'cancelled' ? null : result))
      .catch(() => setOutcome({ kind: 'failed', fallbackText: shareFallbackText(request) }))
      .finally(() => setPending(false));
  };

  return (
    <div className="consumer-share-action">
      <button
        type="button"
        className={className}
        onClick={share}
        disabled={pending}
        aria-busy={pending}
      >
        {pending ? '공유 처리 중…' : label}
      </button>

      {outcome?.kind === 'shared' && (
        <div className="notice notice--ok" role="status"><span aria-hidden="true">✓</span><span>공유했어요.</span></div>
      )}
      {outcome?.kind === 'copied' && (
        <div className="notice notice--ok" role="status"><span aria-hidden="true">✓</span><span>링크를 복사했어요.</span></div>
      )}
      {outcome?.kind === 'failed' && (
        <div className="notice notice--warn consumer-share-fallback" role="alert">
          <span aria-hidden="true">!</span>
          <div>
            <label htmlFor={manualCopyId}>자동 공유를 사용할 수 없어요. 아래 내용을 길게 눌러 복사해 주세요.</label>
            <textarea
              id={manualCopyId}
              value={outcome.fallbackText}
              readOnly
              rows={3}
              onFocus={(event) => event.currentTarget.select()}
              onClick={(event) => event.currentTarget.select()}
            />
          </div>
        </div>
      )}
    </div>
  );
}
