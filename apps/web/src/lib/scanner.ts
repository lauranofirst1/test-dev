/** QR 스캐너 — 카메라로 참여 코드를 읽는다. 스펙 §8.1.
 *
 * **수동 입력이 항상 함께 있어야 합니다.** 카메라는 현장에서 자주 실패합니다 —
 * 권한 거부, 직사광선, 깨진 화면, 손전등 없는 야간. 스캐너를 유일한 입력으로
 * 두면 그 부스는 그 순간 멈춥니다. 이 모듈은 "되면 좋은 것" 이고, 화면은
 * 스캐너가 없어도 완전히 동작해야 합니다.
 *
 * ── 읽는 방법이 두 가지입니다 ──
 *
 * `BarcodeDetector` 는 크롬 계열에만 있습니다(2026년 기준 사파리 미지원).
 * 그것만 쓰면 **부스 담당자가 아이폰을 들고 온 순간 스캔이 통째로 없어집니다.**
 * 부스 단말을 우리가 고를 수 있다는 보장이 없어서, 없는 브라우저에서는 디코더를
 * **그때 내려받아** 씁니다.
 *
 * 번들에 미리 넣지 않습니다. 이 디코더가 필요한 곳은 부스 지급 화면 하나이고,
 * 관객 수백 명에게 쓰지도 않을 파일을 내려보내는 것은 그 자체로 비용입니다.
 * `import()` 는 그 파일을 따로 떼어 두었다가 **필요한 브라우저에서만** 받습니다.
 */

/** 프레임 한 장에서 QR 을 읽어내는 것. 두 구현이 같은 모양을 쓴다. */
interface Decoder {
  detect(video: HTMLVideoElement): Promise<string | null>;
}

/** 브라우저의 BarcodeDetector. 타입 정의가 표준에 아직 없어 최소한만 선언한다. */
interface DetectedBarcode {
  rawValue: string;
}

interface BarcodeDetectorLike {
  detect(source: CanvasImageSource): Promise<DetectedBarcode[]>;
}

type BarcodeDetectorCtor = new (options?: { formats?: string[] }) => BarcodeDetectorLike;

/** 카메라를 쓸 수 있는 환경인가.
 *
 * **읽는 방법이 아니라 카메라를 기준으로 판단합니다.** 디코더는 없으면 받아오면
 * 되지만 카메라는 대신할 것이 없습니다.
 *
 * `navigator.mediaDevices` 는 HTTPS 가 아닌 곳에서 아예 없습니다. 그래서 평문으로
 * 띄운 서버에서는 이 값이 거짓이 되고, 화면은 스캔 버튼 대신 수동 입력만 보여
 * 줍니다 — 눌러도 안 되는 버튼을 보여주는 것보다 낫습니다.
 */
export function scannerSupported(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
}

/** 읽기를 시도하는 간격.
 *
 * 예전에는 `requestAnimationFrame` 으로 초당 60번 훑었습니다. 사람이 QR 을 갖다
 * 대는 동작에 그만한 빈도가 필요하지 않고, 부스 단말은 이 화면을 몇 시간 켜 둡니다.
 * 초당 몇 번이면 즉시 읽히는 것처럼 느껴지면서 배터리를 훨씬 덜 씁니다.
 */
const NATIVE_INTERVAL_MS = 100;
/** 직접 디코딩하는 쪽은 한 번이 더 무겁다. 조금 더 띄운다. */
const FALLBACK_INTERVAL_MS = 200;
/** 디코딩 전에 줄이는 긴 변의 길이(px). */
const DECODE_MAX_EDGE = 640;
/** 같은 코드를 다시 흘리기까지 두는 시간. */
const REPEAT_GUARD_MS = 2_000;

/** 브라우저가 직접 읽어 주는 경우. 가장 빠르고 가장 정확하다. */
function nativeDecoder(): Decoder | null {
  if (typeof window === 'undefined' || !('BarcodeDetector' in window)) return null;
  const Ctor = (window as unknown as { BarcodeDetector: BarcodeDetectorCtor }).BarcodeDetector;
  const detector = new Ctor({ formats: ['qr_code'] });
  return {
    async detect(video) {
      const found = await detector.detect(video);
      return found[0]?.rawValue?.trim() || null;
    },
  };
}

/** 읽어 주지 않는 브라우저(사파리 등)에서 쓰는 디코더. 필요할 때만 받아온다. */
async function fallbackDecoder(): Promise<Decoder | null> {
  let jsQR: typeof import('jsqr').default;
  try {
    jsQR = (await import('jsqr')).default;
  } catch {
    // 부스 와이파이가 끊겨 파일을 못 받는 경우. 수동 입력으로 떨어진다.
    return null;
  }

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return null;

  return {
    async detect(video) {
      const vw = video.videoWidth;
      const vh = video.videoHeight;
      if (!vw || !vh) return null;

      // 원본 해상도 그대로 훑으면 프레임당 수십 ms 가 든다. QR 한 장을 읽는 데
      // 필요한 해상도는 그보다 훨씬 낮아서, 긴 변을 맞춰 줄이고 본다.
      const scale = Math.min(1, DECODE_MAX_EDGE / Math.max(vw, vh));
      canvas.width = Math.round(vw * scale);
      canvas.height = Math.round(vh * scale);
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const found = jsQR(image.data, image.width, image.height, {
        // 부스 단말은 참여자 폰 화면을 비춘다. 반전 코드가 나올 일이 없다.
        inversionAttempts: 'dontInvert',
      });
      return found?.data?.trim() || null;
    },
  };
}

export interface ScannerHandle {
  stop: () => void;
}

/** 카메라를 열고 QR 을 계속 읽는다.
 *
 * 같은 코드를 연속으로 흘려보내지 않습니다 — 카메라는 초당 여러 장을 읽으므로
 * 한 번 비춘 QR 이 열 번 지급 요청이 됩니다. 서버가 막아 주긴 하지만 화면이
 * 열 번 깜빡이면 스태프는 무슨 일이 일어났는지 알 수 없습니다.
 */
export async function startScanner(
  video: HTMLVideoElement,
  onCode: (code: string) => void,
  onError: (message: string) => void,
): Promise<ScannerHandle> {
  if (!scannerSupported()) {
    onError('이 브라우저에서는 카메라를 쓸 수 없습니다. 코드를 직접 입력해 주세요.');
    return { stop: () => {} };
  }

  let stream: MediaStream | null = null;
  let stopped = false;
  let timer = 0;
  // 같은 코드를 연달아 흘리지 않기 위한 기억. 다른 코드가 오면 즉시 풀린다.
  let lastCode = '';
  let lastAt = 0;

  const cleanup = () => {
    stopped = true;
    window.clearTimeout(timer);
    stream?.getTracks().forEach((t) => t.stop());
    video.srcObject = null;
  };

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      // 후면 카메라. 부스 스태프는 참여자 폰을 향해 든다.
      video: { facingMode: 'environment' },
      audio: false,
    });
  } catch {
    // 권한 거부와 카메라 없음을 구분하지 않는다 — 스태프가 할 일은 어느 쪽이든
    // 같다(수동 입력). 원인을 캐물으면 화면만 복잡해진다.
    onError('카메라를 열 수 없습니다. 코드를 직접 입력해 주세요.');
    return { stop: () => {} };
  }

  video.srcObject = stream;
  video.setAttribute('playsinline', 'true');
  await video.play().catch(() => {});

  // 카메라를 먼저 열고 디코더를 정합니다 — 내려받는 동안에도 화면에는 이미
  // 영상이 나오므로, 스태프는 "켜지는 중" 을 보지 빈 화면을 보지 않습니다.
  const native = nativeDecoder();
  const decoder = native ?? (await fallbackDecoder());
  const interval = native ? NATIVE_INTERVAL_MS : FALLBACK_INTERVAL_MS;

  if (stopped) {
    cleanup();
    return { stop: () => {} };
  }

  if (!decoder) {
    cleanup();
    onError('이 브라우저에서는 QR 을 읽을 수 없습니다. 코드를 직접 입력해 주세요.');
    return { stop: () => {} };
  }

  const tick = async () => {
    if (stopped) return;
    try {
      const raw = await decoder.detect(video);
      if (raw) {
        const now = Date.now();
        if (raw !== lastCode || now - lastAt > REPEAT_GUARD_MS) {
          lastCode = raw;
          lastAt = now;
          onCode(raw);
        }
      }
    } catch {
      // 한 프레임 실패는 정상이다(흔들림, 초점). 다음 차례에 다시 본다.
    }
    if (!stopped) timer = window.setTimeout(() => void tick(), interval);
  };
  timer = window.setTimeout(() => void tick(), interval);

  return { stop: cleanup };
}

/** 스캔 결과에서 참여 코드를 뽑는다.
 *
 * 참여자 화면은 코드를 QR 로 그대로 그리지만, 사람이 다른 QR 을 비출 수도 있고
 * 우리 링크(`/join/5`)를 비출 수도 있습니다. 서버가 코드 형식을 검사하므로
 * 여기서는 **꺼낼 수 있으면 꺼내고, 아니면 그대로 넘깁니다** — 여기서 막으면
 * 형식이 바뀔 때마다 두 곳을 고쳐야 합니다.
 */
export function extractParticipantCode(raw: string): string {
  const trimmed = raw.trim();
  // URL 이면 마지막 경로 조각이나 code 쿼리를 본다.
  try {
    const url = new URL(trimmed);
    const q = url.searchParams.get('code');
    if (q) return q.trim().toUpperCase();
  } catch {
    /* URL 이 아니다. 그냥 코드로 본다 */
  }
  const match = trimmed.match(/FF-[0-9A-Z]{8}/i);
  return (match ? match[0] : trimmed).toUpperCase();
}
