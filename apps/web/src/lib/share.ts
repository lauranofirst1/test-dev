export interface ShareRequest {
  data: ShareData;
  /** Text placed on the clipboard when native sharing is unavailable. */
  fallbackText?: string;
}

export interface ShareRuntime {
  share?: (data: ShareData) => Promise<void>;
  canShare?: (data: ShareData) => boolean;
  copyText: (value: string) => Promise<boolean>;
}

export type ShareOutcome =
  | { kind: 'shared' }
  | { kind: 'copied' }
  | { kind: 'cancelled' }
  | { kind: 'failed'; fallbackText: string };

function encodedSegment(value: string | number): string {
  return encodeURIComponent(String(value));
}

export function buildExperienceShareUrl(
  origin: string,
  festivalId: string | number,
  sourceType: string,
  sourceId: string | number,
): string {
  const url = new URL(
    `/join/${encodedSegment(festivalId)}/experience/${encodedSegment(sourceType)}/${encodedSegment(sourceId)}`,
    origin,
  );
  url.searchParams.set('from', 'shared_link');
  return url.toString();
}

export function buildFlowShareUrl(origin: string, festivalId: string | number): string {
  return new URL(`/join/${encodedSegment(festivalId)}/flow`, origin).toString();
}

export function shareFallbackText(request: ShareRequest): string {
  if (request.fallbackText !== undefined) return request.fallbackText;
  return [request.data.title, request.data.text, request.data.url]
    .filter((value): value is string => Boolean(value))
    .join('\n');
}

function isAbortError(error: unknown): boolean {
  return Boolean(
    error
      && typeof error === 'object'
      && 'name' in error
      && error.name === 'AbortError',
  );
}

function shareDataWithoutFiles(data: ShareData): ShareData {
  const shareData: ShareData = {};
  if (data.title !== undefined) shareData.title = data.title;
  if (data.text !== undefined) shareData.text = data.text;
  if (data.url !== undefined) shareData.url = data.url;
  return shareData;
}

function nativeShareData(data: ShareData, runtime: ShareRuntime): ShareData {
  const withoutFiles = shareDataWithoutFiles(data);
  if (!data.files?.length || !runtime.canShare) return withoutFiles;

  try {
    return runtime.canShare({ files: data.files })
      ? { ...withoutFiles, files: data.files }
      : withoutFiles;
  } catch {
    return withoutFiles;
  }
}

function legacyCopyText(value: string): boolean {
  if (typeof document === 'undefined' || !document.body || typeof document.execCommand !== 'function') {
    return false;
  }

  const textarea = document.createElement('textarea');
  const activeElement = document.activeElement as HTMLElement | null;
  textarea.value = value;
  textarea.readOnly = true;
  textarea.tabIndex = -1;
  textarea.style.position = 'fixed';
  textarea.style.inset = '0 auto auto 0';
  textarea.style.width = '1px';
  textarea.style.height = '1px';
  textarea.style.padding = '0';
  textarea.style.border = '0';
  textarea.style.opacity = '0';
  textarea.style.fontSize = '16px';
  document.body.appendChild(textarea);

  let copied = false;
  try {
    textarea.focus({ preventScroll: true });
    textarea.select();
    textarea.setSelectionRange(0, value.length);
    copied = document.execCommand('copy');
  } catch {
    copied = false;
  } finally {
    textarea.remove();
    activeElement?.focus({ preventScroll: true });
  }
  return copied;
}

async function copyText(value: string): Promise<boolean> {
  const secureContext = typeof window !== 'undefined' && window.isSecureContext !== false;
  if (secureContext && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // Permission denial is recoverable while the original click is still active.
    }
  }
  return legacyCopyText(value);
}

function browserShareRuntime(): ShareRuntime {
  const secureContext = typeof window !== 'undefined' && window.isSecureContext !== false;
  const browserNavigator = typeof navigator !== 'undefined' ? navigator : null;

  return {
    share: secureContext && typeof browserNavigator?.share === 'function'
      ? browserNavigator.share.bind(browserNavigator)
      : undefined,
    canShare: secureContext && typeof browserNavigator?.canShare === 'function'
      ? browserNavigator.canShare.bind(browserNavigator)
      : undefined,
    copyText,
  };
}

/**
 * Starts native sharing synchronously from the caller's click stack, before the
 * first await. This preserves transient user activation on mobile browsers.
 */
export async function performShare(
  request: ShareRequest,
  runtime: ShareRuntime = browserShareRuntime(),
): Promise<ShareOutcome> {
  const fallbackText = shareFallbackText(request);

  if (runtime.share) {
    try {
      await runtime.share(nativeShareData(request.data, runtime));
      return { kind: 'shared' };
    } catch (error) {
      if (isAbortError(error)) return { kind: 'cancelled' };
    }
  }

  if (fallbackText) {
    try {
      if (await runtime.copyText(fallbackText)) return { kind: 'copied' };
    } catch {
      // The manual-copy result below is the final, visible fallback.
    }
  }

  return { kind: 'failed', fallbackText };
}
