/**
 * API 클라이언트.
 *
 * 백엔드 오류는 전부 {"error": {code, message, details}} 로 옵니다.
 * message 는 그대로 화면에 보여줄 수 있는 한국어 문장입니다.
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
    // FastAPI 는 HTTPException 의 detail 을 한 겹 감싼다.
    const envelope = (body as { detail?: unknown })?.detail ?? body;
    const err = (
      envelope as {
        error?: { code: string; message: string; details?: Record<string, unknown> };
      }
    )?.error;
    if (err) {
      throw new ApiError(err.code, err.message, res.status, err.details ?? {});
    }
    // pydantic 검증 오류
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
};
