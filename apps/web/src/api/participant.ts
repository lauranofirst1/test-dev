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
}

export function clearParticipant(festivalId: number | string): void {
  try {
    localStorage.removeItem(key(festivalId));
  } catch {
    /* 무시 */
  }
}

const auth = (secret: string) => ({ 'X-Participant-Secret': secret });

export const participantApi = {
  issue: (festivalId: number | string) =>
    api.post<ParticipantIssued>(`/api/festivals/${festivalId}/participants`),

  get: <T>(festivalId: number | string, path: string, secret: string) =>
    api.get<T>(`/api/festivals/${festivalId}${path}`, auth(secret)),

  post: <T>(festivalId: number | string, path: string, secret: string, body?: unknown) =>
    api.post<T>(`/api/festivals/${festivalId}${path}`, body, auth(secret)),
};
