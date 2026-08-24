/** 경품 수령대 — 당첨된 관객에게 실물을 건네는 화면.
 *
 * 관객이 참여 코드를 보여주면 스태프가 그것으로 찾아 건네고 확인을 찍습니다.
 * 당첨자 목록을 스크롤해 찾는 방식은 현장에서 쓸 수 없습니다 — 줄이 서 있고,
 * 당첨자가 수백 명이면 그 방식은 멈춥니다.
 *
 * **줄을 세우는 화면이라 한 사람을 끝내면 즉시 다음 사람으로 돌아갑니다.**
 * 확인을 찍은 뒤 결과를 붙잡아 두면 스태프가 매번 손으로 지워야 하고,
 * 그 몇 초가 줄 길이가 됩니다. 대신 방금 처리한 건을 아래에 남겨,
 * "찍었나?" 를 다시 조회하지 않고도 확인할 수 있게 합니다.
 *
 * 건넬 수 없는 경우(꽝·기수령·미뽑기)를 오류로 취급하지 않습니다. 전부 스태프가
 * 읽고 안내해야 하는 사실이고, 서버가 그 문장을 그대로 내려줍니다.
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { PrizeClaimLookup, PrizeDrawRow } from '../api/types';

/** 참여 코드 표기 정규화. 서버도 흡수하지만 화면에서 먼저 보여준다. */
function tidy(raw: string): string {
  const body = raw.toUpperCase().replace(/[^0-9A-Z]/g, '').replace(/^FF/, '');
  return body ? `FF-${body.slice(0, 8)}` : '';
}

export function PrizeClaimPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [params, setParams] = useSearchParams();

  // QR 이나 링크로 코드를 들고 올 수 있게 열어 둔다.
  const [input, setInput] = useState(() => tidy(params.get('code') ?? ''));
  const [query, setQuery] = useState(() => tidy(params.get('code') ?? ''));
  const [done, setDone] = useState<PrizeDrawRow[]>([]);
  const box = useRef<HTMLInputElement>(null);

  const lookup = useQuery({
    queryKey: ['claim-lookup', id, query],
    queryFn: () =>
      api.get<PrizeClaimLookup>(
        `/api/festivals/${id}/prize-draws/lookup?code=${encodeURIComponent(query)}`,
      ),
    enabled: query.length === 11,
    retry: false,
  });

  const claim = useMutation({
    mutationFn: (drawId: number) =>
      api.post<PrizeDrawRow>(`/api/festivals/${id}/prize-draws/${drawId}/claim`),
    onSuccess: (row) => {
      setDone((prev) => [row, ...prev].slice(0, 8));
      reset();
    },
  });

  function reset() {
    setInput('');
    setQuery('');
    setParams({}, { replace: true });
    box.current?.focus();
  }

  // 줄이 서 있는 화면이다. 항상 입력칸에 커서가 있어야 다음 사람을 바로 받는다.
  useEffect(() => {
    box.current?.focus();
  }, []);

  const found = lookup.data;
  const notFound = lookup.error instanceof ApiError ? lookup.error : null;

  return (
    <div className="shell stack" style={{ gap: 'var(--space-6)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 4 }}>
          <p className="eyebrow">경품 수령대</p>
          <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>참여 코드로 찾기</h1>
          <p className="muted">관객이 보여주는 코드를 입력하면 무엇을 뽑았는지 나옵니다.</p>
        </div>
        <Link to={`/festivals/${id}/booths`} className="btn btn--ghost">
          ← 부스 관리
        </Link>
      </div>

      <form
        className="card stack"
        style={{ gap: 'var(--space-3)' }}
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(tidy(input));
        }}
      >
        <label className="eyebrow" htmlFor="claim-code">
          참여 코드
        </label>
        <input
          id="claim-code"
          ref={box}
          className="claimcode tabular"
          value={input}
          onChange={(e) => setInput(tidy(e.target.value))}
          placeholder="FF-XXXXXXXX"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          aria-describedby="claim-hint"
        />
        <p className="hint" id="claim-hint">
          공백과 대소문자는 알아서 처리합니다. 코드에는 0·O·1·I 가 쓰이지 않습니다.
        </p>
        <button className="btn btn--primary btn--lg" type="submit" disabled={input.length !== 11}>
          찾기
        </button>
      </form>

      {notFound && (
        <div className="card state">
          <p className="eyebrow">없는 코드입니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>{notFound.message}</p>
          <p className="muted" style={{ textAlign: 'center' }}>
            관객 화면 맨 위의 티켓에 적힌 코드를 다시 확인해 주세요.
          </p>
        </div>
      )}

      {found && <Found found={found} pending={claim.isPending} onClaim={claim.mutate} onSkip={reset} />}

      {claim.error instanceof ApiError && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{claim.error.message}</span>
        </div>
      )}

      {done.length > 0 && (
        <div className="card stack" style={{ gap: 'var(--space-2)' }}>
          <p className="eyebrow">방금 건넨 것</p>
          <div className="rcpt">
            {done.map((d) => (
              <div key={d.id} className="rcpt__row">
                <span className="rcpt__name">
                  <strong className="tabular">{d.participant_code}</strong>
                  <span>{d.prize_name}</span>
                </span>
                <span className="rcpt__lead" aria-hidden="true" />
                <span className="rcpt__value rcpt__value--done">✓ 수령</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Found({
  found,
  pending,
  onClaim,
  onSkip,
}: {
  found: PrizeClaimLookup;
  pending: boolean;
  onClaim: (drawId: number) => void;
  onSkip: () => void;
}) {
  return (
    <div className="card state">
      <p className="eyebrow tabular">{found.participant_code}</p>

      {found.draw?.prize_name ? (
        <p className="claimprize">{found.draw.prize_name}</p>
      ) : (
        <p className="claimprize claimprize--none">뽑기 기록 없음</p>
      )}

      {found.claimable ? (
        <>
          <p className="lede" style={{ textAlign: 'center' }}>
            경품을 건네고 아래 버튼을 눌러 주세요.
          </p>
          <button
            className="btn btn--primary btn--lg"
            disabled={pending}
            onClick={() => onClaim(found.draw!.id)}
          >
            {pending ? '기록 중…' : '건넸습니다 — 수령 확인'}
          </button>
        </>
      ) : (
        <>
          {/* 왜 못 건네는지는 서버가 문장으로 준다. 화면이 다시 판정하지 않는다. */}
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>{found.reason}</span>
          </div>
          {found.draw?.claimed_at && (
            <p className="muted tabular">
              수령 시각 {new Date(found.draw.claimed_at).toLocaleString('ko-KR')}
            </p>
          )}
        </>
      )}

      <button className="btn btn--ghost" onClick={onSkip}>
        다음 사람
      </button>
    </div>
  );
}
