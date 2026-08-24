/** 현장 공지 배달 — 관객·스태프 화면 공통.
 *
 * 공지는 **화면 껍데기에 답니다.** 개별 페이지에 붙이면 어느 화면에 있느냐에
 * 따라 우천 중단 공지를 보기도 하고 못 보기도 합니다. 안전 안내가 라우팅에
 * 의존하면 안 됩니다.
 *
 * ## 긴급 덮개를 미루는 이유
 *
 * 부스 QR 을 찍고 미션을 고르는 순간에 덮개가 뜨면 그 스캔은 날아갑니다.
 * QR 토큰은 30~60초짜리라 다시 줄을 서야 할 수도 있습니다. 그래서 **끊기면
 * 손해가 나는 동작이 진행 중이면 덮개를 미룹니다.**
 *
 * 미루되 **감추지는 않습니다** — 미루는 동안 "중요 공지" 알약을 띄우고, 동작이
 * 끝나는 즉시 덮개를 올립니다. 조용히 삼키면 안내하지 않은 것과 같습니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { api } from '../../api/client';
import { loadParticipant } from '../../api/participant';
import type { LiveAnnouncement, LiveAnnouncementList } from '../../api/types';

/** 폴링 주기. 우천 중단이 10초 안에 뜨면 현장에서는 충분히 빠릅니다.
 *  더 짧게 잡으면 축제 당일 수천 대의 폰이 서버를 두드립니다. */
const POLL_MS = 10_000;

type Channel = 'audience' | 'staff';

export interface AnnouncementFeed {
  /** 배너로 그릴 공지 — 일반이거나, 이미 확인한 긴급. */
  banners: LiveAnnouncement[];
  /** 지금 덮개로 띄울 긴급 공지. 없으면 null. */
  urgent: LiveAnnouncement | null;
  /** 덮개를 미루는 중인가. 알약을 띄울지 정한다. */
  deferred: boolean;
  dismiss: (id: number) => void;
  acknowledge: (id: number) => void;
  acking: boolean;
  /** 끊기면 손해가 나는 동작이 진행 중이라고 알린다. 정리 함수를 호출해야 한다. */
  defer: () => () => void;
}

const EMPTY: AnnouncementFeed = {
  banners: [],
  urgent: null,
  deferred: false,
  dismiss: () => {},
  acknowledge: () => {},
  acking: false,
  defer: () => () => {},
};

const FeedContext = createContext<AnnouncementFeed>(EMPTY);

export const useAnnouncements = () => useContext(FeedContext);

/** 지급·체크인처럼 **끊기면 손해가 나는 동작** 중에 긴급 덮개를 미룬다.
 *
 *     const grant = useMutation(...);
 *     useDeferUrgent(grant.isPending);
 */
export function useDeferUrgent(active: boolean): void {
  const { defer } = useAnnouncements();
  useEffect(() => {
    if (!active) return;
    return defer();
  }, [active, defer]);
}

/** 닫은 일반 공지를 기억한다.
 *
 * 서버에 남기지 않는 이유는 이게 **읽음 표시가 아니라 화면 정리**이기 때문입니다.
 * 일반 공지는 안내라 누가 닫았는지 운영자가 알 필요가 없고, 알 수 있게 만들면
 * 그 숫자가 도달률처럼 읽힙니다. 도달률은 긴급 공지에서만 의미가 있습니다.
 */
const dismissKey = (festivalId: string | number) => `festaflow-notice-dismissed-${festivalId}`;

/** 서버에 확인을 남기지 못한 긴급 공지.
 *
 * **덮개는 무슨 일이 있어도 닫혀야 합니다.** 참여 코드를 아직 못 받았거나,
 * 네트워크가 끊겼거나, 서버가 확인을 거절하면 확인 버튼이 아무 일도 하지 않고
 * 사람은 화면에 갇힙니다. 축제장에서 폰이 먹통이 되는 것과 같습니다.
 *
 * 공지를 등록 없이 보여주기로 한 이상, 닫는 것도 등록 없이 돼야 합니다.
 * 여기 남은 것은 서버 확인 인원에 잡히지 않습니다 — 그래서 운영자 화면은
 * 그 숫자를 도달률이 아니라 "확인 인원" 으로만 부릅니다.
 */
const localAckKey = (festivalId: string | number) => `festaflow-notice-acked-${festivalId}`;

function loadIds(key: string): number[] {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as number[]) : [];
  } catch {
    // 사파리 프라이빗 모드에서도 공지는 보여야 한다.
    return [];
  }
}

function saveIds(key: string, ids: number[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(ids));
  } catch {
    /* 저장 못 해도 이번 세션은 유지된다 */
  }
}

export function AnnouncementProvider({
  festivalId,
  channel,
  children,
}: {
  festivalId: string;
  channel: Channel;
  children: React.ReactNode;
}) {
  const qc = useQueryClient();
  const [dismissed, setDismissed] = useState<number[]>(() =>
    loadIds(dismissKey(festivalId)),
  );
  // 서버에 못 남긴 확인. 덮개를 닫는 것과 서버에 기록하는 것은 별개다.
  const [localAcked, setLocalAcked] = useState<number[]>(() =>
    loadIds(localAckKey(festivalId)),
  );
  const [deferCount, setDeferCount] = useState(0);

  const path =
    channel === 'audience'
      ? `/api/festivals/${festivalId}/announcements/live`
      : `/api/festivals/${festivalId}/announcements/staff-live`;

  const feed = useQuery({
    queryKey: ['announcements', channel, festivalId],
    queryFn: () => {
      // 참여자 secret 이 있으면 확인 여부까지 받아온다. 없어도 공지는 나온다 —
      // 참여 코드를 아직 못 받은 사람도 우천 공지는 봐야 한다.
      const stored = channel === 'audience' ? loadParticipant(festivalId) : null;
      return api.get<LiveAnnouncementList>(
        path,
        stored ? { 'X-Participant-Secret': stored.secret } : undefined,
      );
    },
    refetchInterval: POLL_MS,
    // 공지를 못 불러왔다고 화면 전체가 깨지면 안 된다. 조용히 비운다.
    retry: false,
    enabled: Boolean(festivalId),
  });

  /** 서버에 확인을 남긴다. **실패해도 덮개는 닫힌다.**
   *
   * 확인 버튼이 아무 일도 하지 않는 상태를 만들지 않는 것이 우선입니다.
   * 서버 기록은 운영자에게 도달 규모를 알려주는 부가 정보이고, 사람을 화면에
   * 가두지 않는 것이 기능 자체입니다.
   */
  const ack = useMutation({
    mutationFn: (id: number) => {
      const suffix = channel === 'audience' ? 'ack' : 'staff-ack';
      const stored = channel === 'audience' ? loadParticipant(festivalId) : null;
      if (channel === 'audience' && !stored) {
        // 참여 코드를 아직 못 받았다. 서버는 누구인지 알 수 없으므로 기록하지
        // 않고, 이 브라우저에서만 확인으로 친다.
        return Promise.resolve(null);
      }
      return api.post(
        `/api/festivals/${festivalId}/announcements/${id}/${suffix}`,
        undefined,
        stored ? { 'X-Participant-Secret': stored.secret } : undefined,
      );
    },
    onSettled: () =>
      qc.invalidateQueries({ queryKey: ['announcements', channel, festivalId] }),
  });

  const dismiss = useCallback(
    (id: number) => {
      setDismissed((prev) => {
        const next = prev.includes(id) ? prev : [...prev, id];
        saveIds(dismissKey(festivalId), next);
        return next;
      });
    },
    [festivalId],
  );

  const ackMutate = ack.mutate;
  const acknowledge = useCallback(
    (id: number) => {
      // 덮개를 먼저 닫는다. 서버 기록은 그다음이고, 실패해도 되돌리지 않는다 —
      // 되돌리면 덮개가 다시 씌워지고 사람은 갇힌다.
      setLocalAcked((prev) => {
        const next = prev.includes(id) ? prev : [...prev, id];
        saveIds(localAckKey(festivalId), next);
        return next;
      });
      ackMutate(id);
    },
    [festivalId, ackMutate],
  );

  const defer = useCallback(() => {
    setDeferCount((n) => n + 1);
    return () => setDeferCount((n) => Math.max(0, n - 1));
  }, []);

  const items = feed.data?.items;

  const value = useMemo<AnnouncementFeed>(() => {
    const list = items ?? [];
    // 확인하지 않은 긴급이 덮개 후보다. 여럿이면 **첫 건 하나만** 띄운다 —
    // 덮개를 쌓으면 확인 버튼을 연타하게 되고, 그건 아무것도 안 읽는 것과 같다.
    const pending =
      list.find((a) => a.level === 'urgent' && !a.acked && !localAcked.includes(a.id)) ??
      null;
    const deferring = deferCount > 0;
    return {
      banners: list.filter((a) => a.id !== pending?.id && !dismissed.includes(a.id)),
      urgent: deferring ? null : pending,
      deferred: deferring && pending !== null,
      dismiss,
      acknowledge,
      acking: ack.isPending,
      defer,
    };
  }, [items, dismissed, localAcked, deferCount, dismiss, defer, acknowledge, ack.isPending]);

  return <FeedContext.Provider value={value}>{children}</FeedContext.Provider>;
}
