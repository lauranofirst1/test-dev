/**
 * API 클라이언트.
 *
 * 백엔드 오류는 전부 {"error": {code, message, details}} 로 옵니다.
 * message 는 그대로 화면에 보여줄 수 있는 한국어 문장입니다.
 *
 * **세션 토큰을 저장하지 않습니다.** 서버가 httpOnly 쿠키로 내려주고 브라우저가
 * 실어 보냅니다. localStorage 에 두면 XSS 한 번에 전부 털리는데, httpOnly 쿠키는
 * 스크립트가 읽을 수 없습니다.
 */

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface RequestOptions extends RequestInit {
  /** FormData 전송용 — 아래 주석 참고. */
  skipJsonContentType?: boolean;
}

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  let res: Response;
  const { skipJsonContentType, ...rest } = init ?? {};
  try {
    res = await fetch(path, {
      ...rest,
      // 세션은 httpOnly 쿠키로 오간다. 화면이 토큰을 손에 쥐지 않으므로
      // 브라우저가 실어 보내야 한다. 같은 오리진에서만 보낸다 —
      // `include` 로 두면 다른 오리진 요청에도 실려 나간다.
      credentials: 'same-origin',
      headers: skipJsonContentType
        ? (init?.headers as HeadersInit | undefined)
        : { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    // 서버가 안 떠 있을 때 무한 로딩으로 두지 않는다.
    throw new ApiError(
      'NETWORK',
      'API 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해 주세요.',
      0,
    );
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }

  if (!res.ok) {
    // 서버는 모든 오류를 `{"error": {code, message, details}}` 하나로 낸다
    // (main.py 의 예외 핸들러들). `detail` 을 먼저 벗겨 보는 것은 예전 배포나
    // 중간 프록시가 FastAPI 기본 형식(`{"detail": {...}}`)을 그대로 흘릴 때를
    // 위한 것이다 — 지금 서버는 그렇게 내보내지 않는다.
    const envelope = (body as { detail?: unknown })?.detail ?? body;
    const err = (
      envelope as {
        error?: { code: string; message: string; details?: Record<string, unknown> };
      }
    )?.error;
    if (err) {
      throw new ApiError(err.code, err.message, res.status, err.details ?? {});
    }
    // 여기 오는 일은 없다. 다만 예전 배포가 검증 오류 배열을 그대로 흘릴 수
    // 있어 남겨 둔다 — 그때는 영어 문장이 보이지만 아무것도 안 보이는 것보다 낫다.
    const detail = (body as { detail?: Array<{ loc: string[]; msg: string }> })?.detail;
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0];
      const field = first.loc?.[first.loc.length - 1];
      throw new ApiError('VALIDATION_FAILED', `${first.msg}`, res.status, { field });
    }
    throw new ApiError('UNKNOWN', `요청이 실패했습니다 (HTTP ${res.status})`, res.status);
  }

  return body as T;
}

type Headers = Record<string, string>;

/**
 * 파일 업로드. `Content-Type` 을 **직접 지정하지 않는다** —
 * FormData 를 보낼 때는 브라우저가 multipart 경계(boundary)를 포함해 붙여야 하고,
 * 우리가 헤더를 덮어쓰면 경계가 빠져 서버가 본문을 파싱하지 못한다.
 */
export async function upload<T>(path: string, body: FormData): Promise<T> {
  return request<T>(path, { method: 'POST', body, skipJsonContentType: true });
}

export const api = {
  get: <T>(path: string, headers?: Headers) => request<T>(path, { headers }),
  post: <T>(path: string, data?: unknown, headers?: Headers) =>
    request<T>(path, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
      headers,
    }),
  put: <T>(path: string, data: unknown, headers?: Headers) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(data), headers }),
  del: <T>(path: string, headers?: Headers) =>
    request<T>(path, { method: 'DELETE', headers }),
};
