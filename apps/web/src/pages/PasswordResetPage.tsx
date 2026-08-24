/** 비밀번호 재설정 — 요청과 확인 두 화면.
 *
 * **요청 화면은 가입 여부를 알려주지 않습니다.** 가입된 이메일이든 아니든 같은
 * 문장을 보여줍니다. 응답이 갈리면 이 화면이 곧 "이 이메일이 가입돼 있나" 를
 * 확인해 주는 도구가 됩니다.
 *
 * **링크는 화면에 나오지 않습니다.** 남의 이메일을 넣은 사람에게 링크가 나가면
 * 계정 탈취가 요청 한 번으로 끝납니다.
 *
 * 메일 발송기가 아직 없다는 사실은 숨기지 않습니다. 서버가 그 사실을 문장으로
 * 내려주고 화면은 그대로 보여줍니다 — 조용히 성공한 척하면 운영자는 메일이
 * 갔다고 믿고 사용자는 영원히 기다립니다.
 */

import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { PasswordResetAccepted } from '../api/types';

export function PasswordResetRequestPage() {
  const [email, setEmail] = useState('');

  const ask = useMutation({
    mutationFn: () =>
      api.post<PasswordResetAccepted>('/api/auth/password/reset-request', {
        email: email.trim(),
      }),
  });

  return (
    <div className="authshell">
      <div className="stack" style={{ gap: 'var(--space-2)', textAlign: 'center' }}>
        <p className="eyebrow">FestaFlow</p>
        <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>비밀번호 재설정</h1>
      </div>

      {ask.data ? (
        <div className="card stack" style={{ gap: 'var(--space-4)' }}>
          <div className="notice notice--ok">
            <span>✓</span>
            {/* 가입 여부와 무관하게 같은 문장이다. */}
            <span>{ask.data.message}</span>
          </div>
          {ask.data.delivery_note && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>{ask.data.delivery_note}</span>
            </div>
          )}
          <Link to="/login" className="btn btn--ghost">
            로그인으로
          </Link>
        </div>
      ) : (
        <form
          className="card stack"
          style={{ gap: 'var(--space-4)' }}
          onSubmit={(e) => {
            e.preventDefault();
            if (email.trim() && !ask.isPending) ask.mutate();
          }}
        >
          <div className="field">
            <label htmlFor="reset-email">가입한 이메일</label>
            <input
              id="reset-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              placeholder="sw@hallym.ac.kr"
            />
            <span className="hint">
              링크는 30분 동안만 쓸 수 있고, 한 번 쓰면 사라집니다.
            </span>
          </div>

          {ask.error instanceof ApiError && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>{ask.error.message}</span>
            </div>
          )}

          <button className="btn btn--primary btn--lg" type="submit" disabled={!email.trim() || ask.isPending}>
            {ask.isPending ? '보내는 중…' : '재설정 링크 받기'}
          </button>
        </form>
      )}

      <Link to="/login" className="muted" style={{ textAlign: 'center' }}>
        ← 로그인으로 돌아가기
      </Link>
    </div>
  );
}

export function PasswordResetConfirmPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('t') ?? '';
  const [password, setPassword] = useState('');

  const reset = useMutation({
    mutationFn: () =>
      api.post('/api/auth/password/reset', { token, new_password: password }),
    onSuccess: () => navigate('/login', { replace: true }),
  });

  const err = reset.error instanceof ApiError ? reset.error : null;

  if (!token) {
    return (
      <div className="authshell">
        <div className="card state">
          <p className="eyebrow">링크가 올바르지 않습니다</p>
          <p className="lede" style={{ textAlign: 'center' }}>
            메일로 받은 링크를 그대로 열어 주세요.
          </p>
          <Link to="/reset-password-request" className="btn btn--primary btn--lg">
            재설정 다시 요청하기
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="authshell">
      <div className="stack" style={{ gap: 'var(--space-2)', textAlign: 'center' }}>
        <p className="eyebrow">FestaFlow</p>
        <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>새 비밀번호</h1>
      </div>

      <form
        className="card stack"
        style={{ gap: 'var(--space-4)' }}
        onSubmit={(e) => {
          e.preventDefault();
          if (password && !reset.isPending) reset.mutate();
        }}
      >
        <div className="field">
          <label htmlFor="new-password">새 비밀번호</label>
          <input
            id="new-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
          {err && err.details?.field === 'password' ? (
            <span className="err">{err.message}</span>
          ) : (
            <span className="hint">
              10자 이상. 기호를 섞는 것보다 <b>길게</b> 쓰는 편이 훨씬 강합니다.
            </span>
          )}
        </div>

        {/* 링크가 죽은 경우. 다시 요청하는 길을 같은 화면에 둔다. */}
        {err && err.code === 'RESET_TOKEN_INVALID' && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span className="stack" style={{ gap: 'var(--space-3)' }}>
              <span>{err.message}</span>
              <Link to="/reset-password-request" className="btn btn--ghost">
                재설정 다시 요청하기
              </Link>
            </span>
          </div>
        )}

        {err && err.code !== 'RESET_TOKEN_INVALID' && !err.details?.field && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>{err.message}</span>
          </div>
        )}

        <button className="btn btn--primary btn--lg" type="submit" disabled={!password || reset.isPending}>
          {reset.isPending ? '바꾸는 중…' : '비밀번호 바꾸기'}
        </button>

        <p className="hint">
          바꾸면 <b>기존 로그인이 전부 끊깁니다.</b> 재설정하는 이유가 탈취면,
          공격자의 세션이 살아 있는 한 바꾼 의미가 없기 때문입니다.
        </p>
      </form>
    </div>
  );
}
