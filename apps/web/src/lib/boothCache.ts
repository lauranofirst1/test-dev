/** 부스·미션 로컬 캐시 — 오프라인 지급의 **입구**.
 *
 * 큐(lib/grantQueue.ts)는 통신이 끊겨도 지급을 쌓아 둡니다. 그런데 지급 화면을
 * 새로 띄우는 순간 부스 목록을 서버에서 못 받으면 **미션 버튼이 하나도 안 뜨고,
 * 큐에 넣을 입구 자체가 사라집니다.** 큐를 아무리 잘 만들어도 그 앞이 막히면
 * 소용이 없습니다.
 *
 * 스펙 §8.1 의 1단계가 이것입니다 — "스태프 화면이 부스·미션 정보를 미리 받아
 * 로컬에 캐시합니다."
 *
 * ## 완전한 오프라인만의 문제가 아니다
 *
 * 화면이 `retry: false` 라 요청 **하나만** 실패해도 같은 상태가 됩니다. LTE 가
 * 살아 있다 죽었다 하는 축제장에서는 흔한 일입니다.
 *
 * ## 서비스워커를 쓰지 않는 이유
 *
 * "몇 건이 안 갔는가" 의 진실이 두 곳에 생기고, Background Sync 는 iOS 에
 * 없어서 **아이폰 스태프만 조용히 다르게 동작합니다.** 여기서 필요한 것은
 * 목록 한 벌을 기억하는 것뿐이라 localStorage 로 충분합니다.
 */

import type { BoothDetail } from '../api/types';

const KEY = (festivalId: string) => `festaflow-booths-v1-${festivalId}`;

interface Cached {
  at: string;
  items: BoothDetail[];
}

/** 서버에서 받은 목록을 저장한다. 실패해도 조용히 넘어간다 —
 *  캐시를 못 써도 온라인에서는 화면이 돈다. */
export function saveBooths(festivalId: string, items: BoothDetail[]): void {
  try {
    localStorage.setItem(
      KEY(festivalId),
      JSON.stringify({ at: new Date().toISOString(), items } satisfies Cached),
    );
  } catch {
    /* 저장소가 막혔다. 온라인이면 화면은 그대로 돈다 */
  }
}

/** 마지막으로 본 목록. 없으면 null.
 *
 * **오래됐다고 버리지 않습니다.** 만료를 두면 통신이 끊긴 채로 만료 시각이
 * 지나는 순간 화면이 텅 비는데, 그때가 바로 캐시가 가장 필요한 순간입니다.
 * 대신 언제 받은 것인지를 함께 돌려주고, 화면이 그 사실을 밝힙니다.
 */
export function loadBooths(festivalId: string): { items: BoothDetail[]; at: string } | null {
  try {
    const raw = localStorage.getItem(KEY(festivalId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Cached>;
    if (!Array.isArray(parsed.items) || !parsed.items.length) return null;
    return { items: parsed.items, at: parsed.at ?? '' };
  } catch {
    return null;
  }
}
