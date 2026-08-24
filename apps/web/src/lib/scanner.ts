/** QR 스캐너 — 카메라로 참여 코드를 읽는다. 스펙 §8.1.
 *
 * **수동 입력이 항상 함께 있어야 합니다.** 카메라는 현장에서 자주 실패합니다 —
 * 권한 거부, 직사광선, 깨진 화면, 손전등 없는 야간, 구형 브라우저. 스캐너를
 * 유일한 입력으로 두면 그 부스는 그 순간 멈춥니다. 이 모듈은 "되면 좋은 것"
 * 이고, 화면은 스캐너가 없어도 완전히 동작해야 합니다.
 *
 * `BarcodeDetector` 는 크롬 계열에만 있습니다(2026년 기준 사파리 미지원).
 * 폴리필을 번들에 넣지 않는 이유는, 부스 스태프 단말은 대개 안드로이드이고
 * 아이폰 사용자는 수동 입력으로 충분히 빠르기 때문입니다. 300KB 짜리 디코더를
 * 모두에게 내려보내는 쪽이 더 나쁩니다.
 */

/** 브라우저의 BarcodeDetector. 타입 정의가 표준에 아직 없어 최소한만 선언한다. */
interface DetectedBarcode {
  rawValue: string;
}

interface BarcodeDetectorLike {
  detect(source: CanvasImageSource): Promise<DetectedBarcode[]>;
}

type BarcodeDetectorCtor = new (options?: { formats?: string[] }) => BarcodeDetectorLike;

export function scannerSupported(): boolean {
  return typeof window !== 'undefined' && 'BarcodeDetector' in window;
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
    onError('이 브라우저는 카메라 스캔을 지원하지 않습니다. 코드를 직접 입력해 주세요.');
    return { stop: () => {} };
  }

  let stream: MediaStream | null = null;
  let stopped = false;
  let raf = 0;
  // 같은 코드를 연달아 흘리지 않기 위한 기억. 다른 코드가 오면 즉시 풀린다.
  let lastCode = '';
  let lastAt = 0;

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

  const Detector = (window as unknown as { BarcodeDetector: BarcodeDetectorCtor })
    .BarcodeDetector;
  const detector = new Detector({ formats: ['qr_code'] });

  const tick = async () => {
    if (stopped) return;
    try {
      const found = await detector.detect(video);
      const raw = found[0]?.rawValue?.trim();
      if (raw) {
        const now = Date.now();
        // 같은 코드는 2초 안에 다시 흘리지 않는다.
        if (raw !== lastCode || now - lastAt > 2_000) {
          lastCode = raw;
          lastAt = now;
          onCode(raw);
        }
      }
    } catch {
      // 한 프레임 실패는 정상이다(흔들림, 초점). 다음 프레임에서 다시 본다.
    }
    raf = requestAnimationFrame(() => void tick());
  };
  raf = requestAnimationFrame(() => void tick());

  return {
    stop: () => {
      stopped = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
      video.srcObject = null;
    },
  };
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
