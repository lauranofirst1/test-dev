/** 공지 띄우기 — 운영자 화면.
 *
 * ## 여기서 막아야 하는 것은 남용입니다
 *
 * 긴급 공지는 모든 관객의 화면을 덮습니다. 편하다는 이유로 전부 긴급으로 올리면
 * 확인 버튼은 사람들에게 그냥 "닫기" 가 되고, 정작 진짜 긴급할 때 아무도 읽지
 * 않습니다. 늑대소년은 기능 결함이 아니라 **마찰이 없어서** 생깁니다.
 *
 * 그래서 긴급을 고르면 무엇이 일어나는지 그 자리에서 보여주고 한 번 더 확인을
 * 받습니다. 막지는 않습니다 — 진짜 우천 중단일 때 운영자를 방해하면 안 됩니다.
 *
 * ## 미리보기를 두는 이유
 *
 * 운영자는 자기가 띄운 것이 관객 화면에서 어떻게 보이는지 모른 채 발행합니다.
 * 제목이 잘리는지, 본문이 너무 긴지는 보내고 나서야 압니다. 그때는 이미
 * 수천 명이 봤습니다.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, api } from '../api/client';
import type {
  Announcement,
  AnnouncementChannel,
  AnnouncementLevel,
  AnnouncementList,
} from '../api/types';

const CHANNELS: { value: AnnouncementChannel; label: string; hint: string }[] = [
  { value: 'audience', label: '관객', hint: '참여 화면을 보는 모든 사람' },
  { value: 'staff', label: '스태프', hint: '관객에게는 보이지 않습니다' },
  { value: 'both', label: '양쪽', hint: '관객과 스태프 모두' },
];

const EMPTY = {
  channel: 'audience' as AnnouncementChannel,
  level: 'normal' as AnnouncementLevel,
  title: '',
  body: '',
};

export function AnnouncementAdmin({ festivalId }: { festivalId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  // 긴급으로 올리기 직전 한 번 더 받는 확인. 막는 것이 아니라 보여주는 것이다.
  const [confirmingUrgent, setConfirmingUrgent] = useState(false);

  const list = useQuery({
    queryKey: ['announcements-admin', festivalId],
    queryFn: () => api.get<AnnouncementList>(`/api/festivals/${festivalId}/announcements`),
    // 확인 인원이 실시간으로 늘어난다. 우천 공지를 띄운 직후에 이걸 본다.
    refetchInterval: 10_000,
    retry: false,
  });

  const reload = () => {
    qc.invalidateQueries({ queryKey: ['announcements-admin', festivalId] });
    qc.invalidateQueries({ queryKey: ['announcements'] });
  };

  const post = useMutation({
    mutationFn: () =>
      api.post(`/api/festivals/${festivalId}/announcements`, {
        channel: form.channel,
        level: form.level,
        title: form.title.trim(),
        body: form.body.trim(),
      }),
    onSuccess: () => {
      setForm(EMPTY);
      setConfirmingUrgent(false);
      setOpen(false);
      reload();
    },
  });

  const stop = useMutation({
    mutationFn: (id: number) => api.del(`/api/festivals/${festivalId}/announcements/${id}`),
    onSuccess: reload,
  });

  const items = list.data?.items ?? [];
  const live = items.filter((a) => a.is_live);
  const past = items.filter((a) => !a.is_live);
  const ready = form.title.trim() && form.body.trim();

  const submit = () => {
    if (form.level === 'urgent' && !confirmingUrgent) {
      setConfirmingUrgent(true);
      return;
    }
    post.mutate();
  };

  return (
    <section className="card stack" style={{ gap: 'var(--space-4)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <div className="stack" style={{ gap: 4 }}>
          <h2 className="section">공지</h2>
          <p className="muted">지금 현장에 알려야 하는 것을 띄웁니다.</p>
        </div>
        <button
          className="btn btn--ghost"
          onClick={() => {
            setOpen((v) => !v);
            setConfirmingUrgent(false);
          }}
        >
          {open ? '닫기' : '공지 띄우기'}
        </button>
      </div>

      {open && (
        <div className="card card--sunk stack" style={{ gap: 'var(--space-3)' }}>
          <fieldset className="field">
            <legend>누구에게</legend>
            <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
              {CHANNELS.map((c) => (
                <label key={c.value} className="pickr" data-on={form.channel === c.value}>
                  <input
                    type="radio"
                    name="channel"
                    value={c.value}
                    checked={form.channel === c.value}
                    onChange={() => setForm({ ...form, channel: c.value })}
                  />
                  <span>
                    <strong>{c.label}</strong>
                    <small>{c.hint}</small>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="field">
            <legend>얼마나 급한가</legend>
            <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
              <label className="pickr" data-on={form.level === 'normal'}>
                <input
                  type="radio"
                  name="level"
                  checked={form.level === 'normal'}
                  onChange={() => {
                    setForm({ ...form, level: 'normal' });
                    setConfirmingUrgent(false);
                  }}
                />
                <span>
                  <strong>일반</strong>
                  <small>상단 배너. 닫을 수 있습니다</small>
                </span>
              </label>
              <label className="pickr" data-on={form.level === 'urgent'}>
                <input
                  type="radio"
                  name="level"
                  checked={form.level === 'urgent'}
                  onChange={() => setForm({ ...form, level: 'urgent' })}
                />
                <span>
                  <strong>긴급</strong>
                  <small>화면을 덮고 확인을 받습니다</small>
                </span>
              </label>
            </div>
          </fieldset>

          <div className="field">
            <label htmlFor="a-title">제목</label>
            <input
              id="a-title"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="우천으로 야외 부스가 중단됐습니다"
              maxLength={120}
            />
            {/* 관객은 제목만 읽고 지나간다. 남은 글자 수가 아니라 그 사실을 알린다. */}
            <small className="muted">제목 하나로 뜻이 통해야 합니다. 관객은 대개 여기까지만 읽습니다.</small>
          </div>

          <div className="field">
            <label htmlFor="a-body">내용</label>
            <textarea
              id="a-body"
              rows={3}
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
              placeholder="실내 전시장으로 이동해 주세요. 스탬프는 그대로 유지됩니다."
              maxLength={1000}
            />
          </div>

          {/* 발행 전에 관객이 볼 모양 그대로 보여준다. */}
          {ready && (
            <div className="stack" style={{ gap: 6 }}>
              <p className="eyebrow">관객에게 이렇게 보입니다</p>
              <div className="notice-item" data-level={form.level}>
                <div className="notice-item__text">
                  <strong>
                    {form.level === 'urgent' && <span className="notice-item__tag">긴급</span>}
                    {form.title}
                  </strong>
                  <span>{form.body}</span>
                </div>
              </div>
            </div>
          )}

          {/* 남용을 막는 마찰. 막지는 않는다 — 진짜 우천 중단일 때 방해하면 안 된다. */}
          {confirmingUrgent && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>
                <strong>긴급 공지는 모든 화면을 덮습니다.</strong> 지금 부스 QR 을 찍고
                있던 사람도 하던 일이 멈춥니다. 자주 쓰면 확인 버튼은 그냥 "닫기" 가 되고,
                정작 필요할 때 아무도 읽지 않습니다. 그래도 띄우시겠습니까?
              </span>
            </div>
          )}

          {post.error instanceof ApiError && (
            <div className="notice notice--warn">
              <span>⚠</span>
              <span>{post.error.message}</span>
            </div>
          )}

          <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
            <button
              className="btn btn--primary"
              disabled={!ready || post.isPending}
              onClick={submit}
            >
              {post.isPending
                ? '띄우는 중…'
                : confirmingUrgent
                  ? '네, 긴급으로 띄웁니다'
                  : '지금 띄우기'}
            </button>
            {confirmingUrgent && (
              <button
                className="btn btn--ghost"
                onClick={() => {
                  setForm({ ...form, level: 'normal' });
                  setConfirmingUrgent(false);
                }}
              >
                일반으로 바꾸기
              </button>
            )}
          </div>
        </div>
      )}

      {live.length === 0 && !open && <p className="muted">지금 떠 있는 공지가 없습니다.</p>}

      {live.map((a) => (
        <Row key={a.id} item={a} onStop={() => stop.mutate(a.id)} stopping={stop.isPending} />
      ))}

      {past.length > 0 && (
        <details>
          <summary className="muted">내린 공지 {past.length}건</summary>
          <div className="stack" style={{ gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
            {past.map((a) => (
              <Row key={a.id} item={a} />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function Row({
  item,
  onStop,
  stopping,
}: {
  item: Announcement;
  onStop?: () => void;
  stopping?: boolean;
}) {
  const channel = CHANNELS.find((c) => c.value === item.channel)?.label ?? item.channel;
  return (
    <div className="camprow" data-live={item.is_live} data-level={item.level}>
      <div className="row wrap" style={{ justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <div className="stack" style={{ gap: 4 }}>
          <span className="camprow__title">
            <span aria-hidden>{item.level === 'urgent' ? '⚠' : 'ℹ'}</span>
            {item.title}
          </span>
          <span className="muted">
            {channel} · {item.level === 'urgent' ? '긴급' : '일반'}
            {/* 띄운 것과 전달된 것은 다르다. 긴급에서만 셀 수 있다. */}
            {item.level === 'urgent' && ` · ${item.ack_count}명 확인`}
            {!item.is_live && ' · 내려감'}
          </span>
        </div>
        {onStop && (
          <button className="btn btn--ghost" onClick={onStop} disabled={stopping}>
            내리기
          </button>
        )}
      </div>
    </div>
  );
}
