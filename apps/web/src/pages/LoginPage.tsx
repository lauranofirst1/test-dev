/** 기관 로그인 · 회원가입.
 *
 * **세션을 화면이 저장하지 않습니다.** 서버가 httpOnly 쿠키로 내려주고 브라우저가
 * 알아서 실어 보냅니다. 토큰을 localStorage 에 두면 XSS 한 번에 전부 털리는데,
 * httpOnly 쿠키는 스크립트가 읽을 수 없습니다.
 *
 * 그래서 이 화면에는 토큰을 다루는 코드가 없습니다 — 로그인하면 `/` 로 보내고,
 * 세션이 살아 있는지는 `GET /api/auth/me` 가 답합니다.
 *
 * 비밀번호 규칙은 **길이로** 갑니다. 대문자·숫자·기호를 강제하면 사람들은
 * `Password1!` 을 만들고, 그건 길고 무작위한 것보다 훨씬 약합니다. 서버가
 * 뻔한 값을 거절하고, 화면은 그 이유를 그대로 보여줍니다.
 */

import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { ApiError, api } from '../api/client';
import type { AccountSession } from '../api/types';

type Mode = 'login' | 'signup';

export function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>('login');
  const [form, setForm] = useState({
    organization_name: '',
    display_name: '',
    email: '',
    password: '',
  });

  const submit = useMutation({
    mutationFn: () =>
      mode === 'signup'
        ? api.post<AccountSession>('/api/auth/signup', {
            organization_name: form.organization_name.trim(),
            display_name: form.display_name.trim(),
            email: form.email.trim(),
            password: form.password,
          })
        : api.post<AccountSession>('/api/auth/login', {
            email: form.email.trim(),
            password: form.password,
          }),
    onSuccess: () => navigate('/', { replace: true }),
  });

  const err = submit.error instanceof ApiError ? submit.error : null;
  // 서버가 어느 칸이 문제인지 알려주면 그 칸 밑에 붙인다.
  const badField = err?.details?.field as string | undefined;

  const ready =
    form.email.trim() &&
    form.password &&
    (mode === 'login' || (form.organization_name.trim() && form.display_name.trim()));

  return (
    <div className="authshell">
      <div className="stack" style={{ gap: 'var(--space-2)', textAlign: 'center' }}>
        <p className="eyebrow">FestaFlow</p>
        <h1 style={{ fontSize: 'var(--text-h1)', fontWeight: 800 }}>
          {mode === 'login' ? '로그인' : '기관 등록'}
        </h1>
        <p className="muted">
          {mode === 'login'
            ? '축제를 만들고 진단하려면 기관 계정이 필요합니다.'
            : '기관을 등록하면 첫 계정이 함께 만들어집니다.'}
        </p>
      </div>

      <form
        className="card stack"
        style={{ gap: 'var(--space-4)' }}
        onSubmit={(e) => {
          e.preventDefault();
          if (ready && !submit.isPending) submit.mutate();
        }}
      >
        {mode === 'signup' && (
          <>
            <div className="field">
              <label htmlFor="org-name">
                기관 이름 <span className="req">*</span>
              </label>
              <input
                id="org-name"
                value={form.organization_name}
                onChange={(e) => setForm({ ...form, organization_name: e.target.value })}
                placeholder="한림대학교 SW중심대학사업단"
                autoComplete="organization"
              />
            </div>
            <div className="field">
              <label htmlFor="display-name">
                담당자 이름 <span className="req">*</span>
              </label>
              <input
                id="display-name"
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                autoComplete="name"
              />
            </div>
          </>
        )}

        <div className="field">
          <label htmlFor="email">
            이메일 <span className="req">*</span>
          </label>
          <input
            id="email"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            autoComplete={mode === 'signup' ? 'username' : 'email'}
            placeholder="sw@hallym.ac.kr"
          />
          {badField === 'email' && <span className="err">{err?.message}</span>}
        </div>

        <div className="field">
          <label htmlFor="password">
            비밀번호 <span className="req">*</span>
          </label>
          <input
            id="password"
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
          />
          {badField === 'password' ? (
            <span className="err">{err?.message}</span>
          ) : (
            mode === 'signup' && (
              <span className="hint">
                10자 이상. 기호를 섞는 것보다 <b>길게</b> 쓰는 편이 훨씬 강합니다 —
                기억하기 쉬운 단어 서너 개를 이어 보세요.
              </span>
            )
          )}
        </div>

        {/* 칸을 특정할 수 없는 오류(자격 불일치·잠금)는 폼 아래에 둔다. */}
        {err && !badField && (
          <div className="notice notice--warn">
            <span>⚠</span>
            <span>{err.message}</span>
          </div>
        )}

        <button className="btn btn--primary btn--lg" type="submit" disabled={!ready || submit.isPending}>
          {submit.isPending ? '확인 중…' : mode === 'login' ? '로그인' : '기관 등록하고 시작'}
        </button>
      </form>

      {mode === 'login' && (
        <Link to="/reset-password-request" className="muted" style={{ textAlign: 'center' }}>
          비밀번호를 잊으셨나요?
        </Link>
      )}

      <button
        type="button"
        className="btn btn--ghost"
        onClick={() => {
          setMode(mode === 'login' ? 'signup' : 'login');
          submit.reset();
        }}
      >
        {mode === 'login' ? '기관이 처음이신가요? 등록하기' : '이미 계정이 있으신가요? 로그인'}
      </button>

      <p className="hint" style={{ textAlign: 'center', maxWidth: '44ch' }}>
        현장 스태프와 심사위원은 이 화면이 아니라 운영자가 준 초대 링크로 들어옵니다.
      </p>
    </div>
  );
}
