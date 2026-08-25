/**
 * 참여자 자격 보관과 인증 요청.
 *
 * 관객은 로그인하지 않습니다. 발급 응답의 `secret` 을 localStorage 에 두고
 * 이후 조회에 `X-Participant-Secret` 으로 실어 보냅니다 — 계약 §9.
 *
 * `code` 는 부스에서 스태프에게 보여주는 값이라 옆 사람도 봅니다. 그래서 조회
 * 인증에는 쓰지 않고, 서버도 코드로는 열어주지 않습니다.
 */

import { api } from './client';
import type { ParticipantIssued } from './types';

export interface StoredParticipant {
  code: string;
  secret: string;
}

const key = (festivalId: number | string) => `festaflow-participant-${festivalId}`;

/** 참여 자격이 생기거나 사라졌다는 신호.
 *
 * `localStorage` 는 같은 탭에서 바뀔 때 `storage` 이벤트를 내지 않습니다
 * (다른 탭에만 갑니다). 그래서 화면이 저장소를 한 번 읽고 마는 컴포넌트는
 * 참여 직후에도 "아직 참여 안 함" 인 채로 남습니다 — 하단 탭이 실제로 그랬습니다.
 * 저장·삭제 자리에서 직접 알립니다. */
const CHANGED = 'festaflow:participant-changed';

function announce(festivalId: number | string): void {
  try {
    window.dispatchEvent(new CustomEvent(CHANGED, { detail: String(festivalId) }));
  } catch {
    /* 이벤트를 못 내도 저장 자체는 끝났다 */
  }
}

/** 참여 자격이 바뀌면 부른다. 정리 함수를 돌려준다. */
export function onParticipantChange(handler: () => void): () => void {
  window.addEventListener(CHANGED, handler);
  // 다른 탭에서 바뀐 것도 받는다 — 관객이 QR 화면과 보드를 두 탭에 띄우는
  // 일이 실제로 있다.
  window.addEventListener('storage', handler);
  return () => {
    window.removeEventListener(CHANGED, handler);
    window.removeEventListener('storage', handler);
  };
}

export function loadParticipant(festivalId: number | string): StoredParticipant | null {
  try {
    const raw = localStorage.getItem(key(festivalId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredParticipant>;
    if (!parsed.code || !parsed.secret) return null;
    return { code: parsed.code, secret: parsed.secret };
  } catch {
    // 사파리 프라이빗 모드처럼 localStorage 가 막힌 환경에서도 화면은 떠야 한다.
    return null;
  }
}

export function saveParticipant(festivalId: number | string, p: StoredParticipant): void {
  try {
    localStorage.setItem(key(festivalId), JSON.stringify(p));
  } catch {
    /* 저장 못 해도 이번 세션은 메모리 상태로 계속 쓴다 */
  }
  announce(festivalId);
}

export function clearParticipant(festivalId: number | string): void {
  try {
    localStorage.removeItem(key(festivalId));
  } catch {
    /* 무시 */
  }
  announce(festivalId);
}

const auth = (secret: string) => ({ 'X-Participant-Secret': secret });

export const participantApi = {
  /** 학번 축제에서는 `studentNo` 가 필수다. 같은 학번이면 기존 참여를 이어받는다. */
  issue: (festivalId: number | string, studentNo?: string) =>
    api.post<ParticipantIssued>(`/api/festivals/${festivalId}/participants`, {
      student_no: studentNo ?? null,
    }),

  get: <T>(festivalId: number | string, path: string, secret: string) =>
    api.get<T>(`/api/festivals/${festivalId}${path}`, auth(secret)),

  post: <T>(festivalId: number | string, path: string, secret: string, body?: unknown) =>
    api.post<T>(`/api/festivals/${festivalId}${path}`, body, auth(secret)),

  /** 표를 거두는 것처럼 되돌리는 동작에 쓴다. */
  del: <T>(festivalId: number | string, path: string, secret: string) =>
    api.del<T>(`/api/festivals/${festivalId}${path}`, auth(secret)),
};
