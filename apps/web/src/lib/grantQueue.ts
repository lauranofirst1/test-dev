/** 오프라인 우선 지급 큐 — 스펙 §8.1.
 *
 * **축제장 통신은 끊기는 게 기본값입니다.** 수천 명이 모인 야외에서 LTE 가
 * 버티지 못하는 건 예외 상황이 아닙니다. 그래서 지급 경로만큼은 오프라인에서
 * 완결됩니다 — 스태프가 버튼을 누르면 화면은 즉시 성공으로 답하고, 요청은
 * 로컬 큐에 쌓였다가 복구되면 순서대로 나갑니다.
 *
 * ## 왜 이렇게까지 하는가
 *
 * 운영 대시보드는 못 봐도 축제는 굴러갑니다. 지급이 막히면 참여자가 부스 앞에
 * 멈춰 섭니다. 줄이 서 있는데 "전송 중…" 이 돌면 그 부스는 마비됩니다.
 *
 * ## 중복 지급을 막는 것은 서버다
 *
 * 각 항목에 `client_request_id`(UUID)를 **큐에 넣는 순간** 붙입니다. 재전송이
 * 몇 번 일어나도 서버의 `UNIQUE (client_request_id)` 가 두 번째부터 기존 행을
 * 돌려줍니다. 이 파일은 중복을 "막으려" 하지 않습니다 — 클라이언트가 중복을
 * 판단하려 들면 탭이 두 개일 때, 새로고침했을 때, 시계가 어긋났을 때 전부
 * 다르게 틀립니다. 판단은 DB 제약 하나에 맡깁니다.
 *
 * ## queued_at 을 함께 보내는 이유
 *
 * 서버는 `queued_at` 이 있으면 그것을 `completed_at` 으로 씁니다. 안 그러면
 * 통신이 복구된 순간에 완료가 몰려 보이고, 운영 인사이트의 "최근 30분 편중"
 * 판정이 통째로 왜곡됩니다. **현장에서 누른 시각이 진짜 시각입니다.**
 */

import { ApiError, api } from '../api/client';

/** 큐 항목 하나. 이 모양이 바뀌면 STORAGE_VERSION 을 올린다. */
export interface QueuedGrant {
  /** 서버의 중복 방지 키. 큐에 넣을 때 한 번 만들고 재전송해도 바뀌지 않는다. */
  clientRequestId: string;
  festivalId: string;
  boothId: number;
  missionId: number;
  missionTitle: string;
  participantCode: string;
  /** 스태프가 **버튼을 누른** 시각. 도달 시각이 아니다. */
  queuedAt: string;
  attempts: number;
  /** 마지막 실패 이유. 스태프가 읽을 한국어 문장이다. */
  lastError?: string;
  /** 되살릴 수 없는 실패. 자동 재전송을 멈추고 사람에게 넘긴다. */
  dead?: boolean;
}

const STORAGE_VERSION = 1;
const key = (festivalId: string) => `festaflow-grant-queue-v${STORAGE_VERSION}-${festivalId}`;

/** 재전송 간격. 지수 백오프하되 상한을 둔다 —
 *  30초를 넘기면 통신이 돌아온 걸 스태프가 눈으로 보고도 큐가 안 줄어든다. */
const BACKOFF_MS = [0, 1_000, 3_000, 8_000, 20_000, 30_000];

/** 이 횟수를 넘기면 자동 재전송을 포기하고 사람에게 보여준다.
 *  무한히 재시도하면 배터리를 먹고, 무엇이 안 갔는지도 묻히다. */
const MAX_ATTEMPTS = 8;

function read(festivalId: string): QueuedGrant[] {
  try {
    const raw = localStorage.getItem(key(festivalId));
    return raw ? (JSON.parse(raw) as QueuedGrant[]) : [];
  } catch {
    // 저장소가 막혔거나 깨졌다. 큐를 못 읽는다고 화면이 죽으면 안 된다.
    return [];
  }
}

function write(festivalId: string, items: QueuedGrant[]): boolean {
  try {
    localStorage.setItem(key(festivalId), JSON.stringify(items));
    return true;
  } catch {
    // 저장소가 가득 찼다. **이건 조용히 넘길 수 없다** — 지급이 사라진다.
    return false;
  }
}

function uuid(): string {
  // crypto.randomUUID 는 보안 컨텍스트에서만 있다. 축제장 내부망 http 접속에서는
  // 없을 수 있어 폴백을 둔다. 서버가 UUID 형식을 검사하므로 모양을 맞춘다.
  const webcrypto: Crypto | undefined =
    typeof crypto !== 'undefined' ? (crypto as Crypto) : undefined;
  if (webcrypto?.randomUUID) {
    return webcrypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (webcrypto?.getRandomValues) {
    webcrypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** 이 오류에 재전송이 의미가 있는가.
 *
 * **4xx 를 재전송하면 영원히 실패합니다.** 미션이 비활성이거나 참여 코드가
 * 틀렸다면 백 번을 보내도 같습니다. 그런 건 큐에 쌓아 두는 대신 사람에게
 * 보여줘야 합니다 — 스태프가 코드를 다시 물어보면 되는 일입니다.
 *
 * 반대로 5xx 와 네트워크 오류는 서버나 통신 문제라 시간이 해결합니다.
 * 408·429 는 4xx 지만 "지금 말고 나중에" 라는 뜻이라 재전송합니다.
 */
function isRetryable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  if (error.status === 0) return true; // 네트워크 실패
  if (error.status === 408 || error.status === 429) return true;
  if (error.status >= 500) return true;
  return false;
}

/** 큐가 항목 하나를 처리하고 나서 알려주는 결과.
 *
 * 화면이 이걸 듣고 피드백을 띄웁니다. 클릭 시점에 결과를 기다리지 않기 때문에
 * (기다리면 통신이 느릴 때 버튼이 잠기고 부스가 멈춥니다) 결과는 나중에 옵니다.
 * 보통 온라인에서는 수백 밀리초라 사람이 서 있는 동안 도착합니다.
 */
export interface GrantOutcome {
  item: QueuedGrant;
  kind: 'ok' | 'duplicate' | 'failed';
  message: string;
}

export interface QueueSnapshot {
  pending: QueuedGrant[];
  dead: QueuedGrant[];
  /** 마지막으로 큐가 완전히 비워진 시각. 없으면 아직 한 번도 못 비웠다. */
  lastSyncedAt: string | null;
  online: boolean;
  flushing: boolean;
  /** 저장소에 못 썼다. 이 상태에서는 오프라인 지급을 신뢰할 수 없다. */
  storageBroken: boolean;
}

type Listener = (snapshot: QueueSnapshot) => void;
type OutcomeListener = (outcome: GrantOutcome) => void;

/** 축제 하나의 지급 큐.
 *
 * 화면이 여러 번 마운트돼도 큐는 하나여야 한다 — 두 개가 동시에 flush 하면
 * 같은 항목을 두 번 보내고, 서버가 막아 주긴 하지만 네트워크를 두 배로 쓴다.
 */
export class GrantQueue {
  private items: QueuedGrant[];
  private listeners = new Set<Listener>();
  private outcomeListeners = new Set<OutcomeListener>();
  private flushing = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private lastSyncedAt: string | null = null;
  private storageBroken = false;

  constructor(private readonly festivalId: string) {
    this.items = read(festivalId);
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    fn(this.snapshot());
    return () => this.listeners.delete(fn);
  }

  /** 항목 하나가 처리될 때마다 알려준다. 화면 피드백이 여기서 나온다. */
  onOutcome(fn: OutcomeListener): () => void {
    this.outcomeListeners.add(fn);
    return () => this.outcomeListeners.delete(fn);
  }

  private report(outcome: GrantOutcome): void {
    this.outcomeListeners.forEach((fn) => fn(outcome));
  }

  snapshot(): QueueSnapshot {
    return {
      pending: this.items.filter((i) => !i.dead),
      dead: this.items.filter((i) => i.dead),
      lastSyncedAt: this.lastSyncedAt,
      online: typeof navigator === 'undefined' ? true : navigator.onLine,
      flushing: this.flushing,
      storageBroken: this.storageBroken,
    };
  }

  private emit(): void {
    const snap = this.snapshot();
    this.listeners.forEach((fn) => fn(snap));
  }

  private persist(): void {
    this.storageBroken = !write(this.festivalId, this.items);
  }

  /** 지급을 큐에 넣는다. **즉시 돌아온다** — 줄이 서 있는데 기다리게 하지 않는다. */
  enqueue(input: {
    boothId: number;
    missionId: number;
    missionTitle: string;
    participantCode: string;
  }): QueuedGrant {
    const item: QueuedGrant = {
      clientRequestId: uuid(),
      festivalId: this.festivalId,
      boothId: input.boothId,
      missionId: input.missionId,
      missionTitle: input.missionTitle,
      participantCode: input.participantCode,
      // 현장에서 누른 시각. 서버가 이걸 completed_at 으로 쓴다.
      queuedAt: new Date().toISOString(),
      attempts: 0,
    };
    this.items = [...this.items, item];
    this.persist();
    this.emit();
    void this.flush();
    return item;
  }

  /** 죽은 항목을 다시 살려 보낸다. 스태프가 코드를 고쳐 다시 넣는 대신 쓸 수 있다. */
  retry(clientRequestId: string): void {
    this.items = this.items.map((i) =>
      i.clientRequestId === clientRequestId
        ? { ...i, dead: false, attempts: 0, lastError: undefined }
        : i,
    );
    this.persist();
    this.emit();
    void this.flush();
  }

  /** 포기한다. **사람이 명시적으로 눌러야만** 사라진다 —
   *  자동으로 지우면 "보낸 줄 알았는데 안 갔다" 가 조용히 일어난다. */
  discard(clientRequestId: string): void {
    this.items = this.items.filter((i) => i.clientRequestId !== clientRequestId);
    this.persist();
    this.emit();
  }

  /** 큐를 순서대로 보낸다. 한 번에 하나만 — 순서가 곧 지급 순서다. */
  async flush(): Promise<void> {
    if (this.flushing) return;
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      this.emit();
      return;
    }
    this.flushing = true;
    this.emit();

    try {
      // 매 반복마다 앞에서 다시 찾는다. 보내는 중에 새 항목이 들어올 수 있다.
      for (;;) {
        const next = this.items.find((i) => !i.dead);
        if (!next) break;

        try {
          const result = await api.post<{ was_already_granted: boolean }>(
            `/api/festivals/${this.festivalId}/booths/${next.boothId}/grants`,
            {
              participant_code: next.participantCode,
              mission_id: next.missionId,
              client_request_id: next.clientRequestId,
              queued_at: next.queuedAt,
            },
          );
          // 성공. 서버가 중복이라고 답해도(was_already_granted) 지급 자체는
          // 이루어져 있다. 다만 스태프에게는 구분해 알린다 — 참여자가 "왜 또
          // 안 주냐" 고 물을 때 답할 수 있어야 한다.
          this.items = this.items.filter(
            (i) => i.clientRequestId !== next.clientRequestId,
          );
          this.persist();
          this.emit();
          this.report({
            item: next,
            kind: result?.was_already_granted ? 'duplicate' : 'ok',
            message: result?.was_already_granted
              ? '이미 지급된 미션입니다. 포인트는 그대로입니다.'
              : '지급했습니다.',
          });
        } catch (error) {
          const attempts = next.attempts + 1;
          const message =
            error instanceof ApiError ? error.message : '통신에 실패했습니다.';
          const retryable = isRetryable(error) && attempts < MAX_ATTEMPTS;

          this.items = this.items.map((i) =>
            i.clientRequestId === next.clientRequestId
              ? { ...i, attempts, lastError: message, dead: !retryable }
              : i,
          );
          this.persist();
          this.emit();

          if (!retryable) {
            // 되살릴 수 없다. 사람이 알아야 한다 — 코드를 잘못 받아 적었거나
            // 미션이 중지됐거나, 어느 쪽이든 그 자리에서 손쓸 수 있는 일이다.
            this.report({ item: next, kind: 'failed', message });
            continue;
          }
          // 재전송할 만한 실패다. 뒤로 물러났다가 다시 온다.
          this.scheduleRetry(attempts);
          return;
        }
      }
      if (this.items.every((i) => i.dead)) {
        this.lastSyncedAt = new Date().toISOString();
      }
    } finally {
      this.flushing = false;
      this.emit();
    }
  }

  private scheduleRetry(attempts: number): void {
    if (this.timer) clearTimeout(this.timer);
    const delay = BACKOFF_MS[Math.min(attempts, BACKOFF_MS.length - 1)];
    this.timer = setTimeout(() => void this.flush(), delay);
  }

  /** 브라우저의 온라인 복귀를 듣는다. 이벤트만 믿지 않고 주기적으로도 시도한다 —
   *  `navigator.onLine` 은 "랜선이 꽂혀 있다" 수준이라 실제 도달 가능성과 다르다. */
  listen(): () => void {
    const onOnline = () => void this.flush();
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', () => this.emit());
    const tick = setInterval(() => void this.flush(), 15_000);
    return () => {
      window.removeEventListener('online', onOnline);
      clearInterval(tick);
      if (this.timer) clearTimeout(this.timer);
    };
  }
}

const registry = new Map<string, GrantQueue>();

/** 축제당 큐 하나. 화면이 여러 번 마운트돼도 같은 것을 쓴다. */
export function getGrantQueue(festivalId: string): GrantQueue {
  let q = registry.get(festivalId);
  if (!q) {
    q = new GrantQueue(festivalId);
    registry.set(festivalId, q);
  }
  return q;
}
