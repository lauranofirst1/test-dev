/** 미션 체험 설정 — 부스 QR을 찍은 관객이 무엇을 하게 될지 정하는 곳.
 *
 * 설계 문서 05 §1 의 구조를 그대로 따릅니다. **테마는 부스, 체험은 미션**입니다.
 * 그래서 이 편집기는 미션 하나에 붙습니다.
 *
 * 검증은 **서버가 진실**입니다. 여기서 같은 규칙을 다시 구현하면 반드시 어긋나고,
 * 화면이 통과시킨 설정을 서버가 거절하는 상태가 됩니다. 그래서 이 화면은 저장을
 * 막지 않고, 서버가 돌려준 `details.field` 를 해당 입력 옆에 붙여 보여줍니다.
 *
 * 다만 하나는 화면이 미리 막습니다 — **정답을 고르지 않은 채로 저장**하는 것.
 * 라디오가 비어 있는 상태를 서버 왕복 없이도 볼 수 있고, 이건 규칙이 아니라
 * 입력이 덜 끝난 상태이기 때문입니다.
 */

import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, api } from '../api/client';
import type { ExperienceType, MissionOut } from '../api/types';

const TYPES: { value: ExperienceType; label: string; hint: string }[] = [
  { value: 'stamp', label: '도착 확인', hint: '버튼 한 번으로 지급합니다.' },
  { value: 'quiz', label: '퀴즈', hint: '정답을 맞혀야 지급합니다. 채점은 서버가 합니다.' },
  { value: 'info', label: '안내 읽기', hint: '안내를 읽고 확인하면 지급합니다.' },
  { value: 'survey', label: '설문', hint: '답하면 지급합니다. 틀린 답이 없습니다.' },
];

/** 설문 문항. **자유 서술이 없습니다.**
 *
 * 자유 입력을 열면 사람들이 이름·연락처·민원을 적고, 그 순간 이 기능의 수집
 * 범위가 완전히 달라집니다. 설계 05 §6 이 설문에 대해 "참여 코드와만 연결되며
 * 별도 신원 정보를 수집하지 않습니다" 라고 못박은 것을 지키는 방법이 이것뿐입니다.
 * 서버도 `type: "text"` 를 422 로 거절합니다.
 */
interface SurveyQuestion {
  type: 'rating' | 'choice';
  text: string;
  scale: string;
  choices: string[];
}

interface SurveyDraft {
  questions: SurveyQuestion[];
}

function surveyDraftOf(config: Record<string, unknown>): SurveyDraft {
  const raw = Array.isArray(config.questions) ? (config.questions as Record<string, unknown>[]) : [];
  const questions = raw.map((q) => ({
    type: q.type === 'choice' ? ('choice' as const) : ('rating' as const),
    text: typeof q.text === 'string' ? q.text : '',
    scale: String(q.scale ?? 5),
    choices: Array.isArray(q.choices) ? (q.choices as string[]) : ['', ''],
  }));
  return {
    questions: questions.length
      ? questions
      : [{ type: 'rating', text: '', scale: '5', choices: ['', ''] }],
  };
}

interface QuizDraft {
  question: string;
  choices: string[];
  answer_index: number | null;
  max_attempts: string;
  hint: string;
  explanation: string;
}

interface InfoDraft {
  body: string;
  min_dwell_seconds: string;
  links: { label: string; url: string }[];
}

function quizDraftOf(config: Record<string, unknown>): QuizDraft {
  const choices = Array.isArray(config.choices) ? (config.choices as string[]) : [];
  return {
    question: typeof config.question === 'string' ? config.question : '',
    choices: choices.length >= 2 ? choices : ['', ''],
    answer_index: typeof config.answer_index === 'number' ? config.answer_index : null,
    max_attempts: String(config.max_attempts ?? 3),
    hint: typeof config.hint === 'string' ? config.hint : '',
    explanation: typeof config.explanation === 'string' ? config.explanation : '',
  };
}

function infoDraftOf(config: Record<string, unknown>): InfoDraft {
  return {
    body: typeof config.body === 'string' ? config.body : '',
    min_dwell_seconds: String(config.min_dwell_seconds ?? 0),
    links: Array.isArray(config.links) ? (config.links as InfoDraft['links']) : [],
  };
}

export function ExperienceEditor({
  festivalId,
  mission,
  onSaved,
  onClose,
}: {
  festivalId: string;
  mission: MissionOut;
  onSaved: () => void;
  onClose: () => void;
}) {
  const [type, setType] = useState<ExperienceType>(mission.experience_type);
  const [quiz, setQuiz] = useState(() => quizDraftOf(mission.experience_config));
  const [info, setInfo] = useState(() => infoDraftOf(mission.experience_config));
  const [survey, setSurvey] = useState(() => surveyDraftOf(mission.experience_config));
  const [localError, setLocalError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      api.put<MissionOut>(`/api/festivals/${festivalId}/missions/${mission.id}`, {
        // PUT 은 전체 교체다. 안 보낸 필드는 기본값으로 덮인다.
        title: mission.title,
        description: mission.description,
        points: mission.points,
        is_active: mission.is_active,
        experience_type: type,
        experience_config: buildConfig(),
      }),
    onSuccess: () => {
      onSaved();
      onClose();
    },
  });

  function buildConfig(): Record<string, unknown> {
    if (type === 'quiz') {
      return {
        question: quiz.question,
        choices: quiz.choices,
        answer_index: quiz.answer_index,
        max_attempts: Number(quiz.max_attempts) || 3,
        hint: quiz.hint || undefined,
        explanation: quiz.explanation || undefined,
      };
    }
    if (type === 'info') {
      return {
        body: info.body,
        min_dwell_seconds: Number(info.min_dwell_seconds) || 0,
        links: info.links.filter((l) => l.label.trim() && l.url.trim()),
      };
    }
    if (type === 'survey') {
      return {
        questions: survey.questions.map((q) =>
          q.type === 'rating'
            ? { type: 'rating', text: q.text, scale: Number(q.scale) || 5 }
            : {
                type: 'choice',
                text: q.text,
                choices: q.choices.filter((c) => c.trim()),
              },
        ),
      };
    }
    return {};
  }

  function submit() {
    setLocalError(null);
    if (type === 'quiz' && quiz.answer_index === null) {
      setLocalError('정답을 골라 주세요. 보기 왼쪽의 동그라미를 누르면 됩니다.');
      return;
    }
    save.mutate();
  }

  const err = save.error instanceof ApiError ? save.error : null;
  const badField = err?.details?.field as string | undefined;

  return (
    <div className="expedit stack" style={{ gap: 'var(--space-4)' }}>
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <p className="eyebrow">체험 설정 — {mission.title}</p>
        <button className="btn btn--ghost" onClick={onClose} type="button">
          닫기
        </button>
      </div>

      <div className="exptypes">
        {TYPES.map((t) => (
          <button
            key={t.value}
            type="button"
            className={`exptype${type === t.value ? ' exptype--on' : ''}`}
            aria-pressed={type === t.value}
            onClick={() => setType(t.value)}
          >
            <b>{t.label}</b>
            <small>{t.hint}</small>
          </button>
        ))}
      </div>

      {type === 'quiz' && <QuizFields draft={quiz} onChange={setQuiz} badField={badField} />}
      {type === 'info' && <InfoFields draft={info} onChange={setInfo} badField={badField} />}
      {type === 'survey' && <SurveyFields draft={survey} onChange={setSurvey} />}
      {type === 'stamp' && (
        <p className="muted">
          설정할 것이 없습니다. 부스 QR을 찍으면 확인 버튼 하나가 뜹니다.
        </p>
      )}

      {(localError || err) && (
        <div className="notice notice--warn">
          <span>⚠</span>
          <span>{localError ?? err!.message}</span>
        </div>
      )}

      <button className="btn btn--primary btn--lg" onClick={submit} disabled={save.isPending}>
        {save.isPending ? '저장 중…' : '체험 저장'}
      </button>
    </div>
  );
}

// ── 퀴즈 ────────────────────────────────────────────────────────────────────

function QuizFields({
  draft,
  onChange,
  badField,
}: {
  draft: QuizDraft;
  onChange: (d: QuizDraft) => void;
  badField?: string;
}) {
  const set = (patch: Partial<QuizDraft>) => onChange({ ...draft, ...patch });

  function setChoice(i: number, value: string) {
    const choices = [...draft.choices];
    choices[i] = value;
    set({ choices });
  }

  function removeChoice(i: number) {
    const choices = draft.choices.filter((_, n) => n !== i);
    // 정답 뒤의 보기를 지우면 정답 번호가 밀린다. 같이 옮겨 준다 —
    // 안 옮기면 조용히 다른 보기가 정답이 된다.
    let answer = draft.answer_index;
    if (answer !== null) {
      if (answer === i) answer = null;
      else if (answer > i) answer -= 1;
    }
    set({ choices, answer_index: answer });
  }

  return (
    <div className="stack" style={{ gap: 'var(--space-4)' }}>
      <div className="field">
        <label htmlFor="quiz-q">문제</label>
        <input
          id="quiz-q"
          value={draft.question}
          onChange={(e) => set({ question: e.target.value })}
          placeholder="춘천 막국수의 주재료는?"
        />
        {badField === 'question' && <span className="err">문제를 입력해 주세요.</span>}
      </div>

      <div className="field">
        <label>보기 — 왼쪽 동그라미가 정답입니다</label>
        <div className="stack" style={{ gap: 'var(--space-2)' }}>
          {draft.choices.map((c, i) => (
            <div key={i} className="row" style={{ gap: 'var(--space-3)' }}>
              <input
                type="radio"
                name="quiz-answer"
                checked={draft.answer_index === i}
                onChange={() => set({ answer_index: i })}
                aria-label={`${i + 1}번 보기를 정답으로`}
                style={{ width: 22, height: 22, flex: 'none' }}
              />
              <input
                value={c}
                onChange={(e) => setChoice(i, e.target.value)}
                placeholder={`보기 ${i + 1}`}
                style={{ flex: 1 }}
                aria-label={`${i + 1}번 보기`}
              />
              {draft.choices.length > 2 && (
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => removeChoice(i)}
                  aria-label={`${i + 1}번 보기 삭제`}
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
        {badField === 'choices' && <span className="err">보기를 2개 이상 채워 주세요.</span>}
        {badField === 'answer_index' && <span className="err">정답을 골라 주세요.</span>}
        {draft.choices.length < 6 && (
          <button
            type="button"
            className="btn btn--ghost"
            style={{ alignSelf: 'flex-start', marginTop: 'var(--space-2)' }}
            onClick={() => set({ choices: [...draft.choices, ''] })}
          >
            ＋ 보기 추가
          </button>
        )}
      </div>

      <div className="grid2">
        <div className="field field--inline">
          <label htmlFor="quiz-attempts">시도 횟수</label>
          <input
            id="quiz-attempts"
            type="number"
            min={1}
            max={10}
            className="tabular"
            value={draft.max_attempts}
            onChange={(e) => set({ max_attempts: e.target.value })}
          />
          <span className="hint">소진하면 스태프에게 문의하라고 안내합니다.</span>
        </div>
        <div className="field">
          <label htmlFor="quiz-hint">힌트 (선택)</label>
          <input
            id="quiz-hint"
            value={draft.hint}
            onChange={(e) => set({ hint: e.target.value })}
            placeholder="겨울에 잘 자라는 곡물입니다"
          />
          <span className="hint">한 번 틀린 사람에게만 보입니다.</span>
        </div>
      </div>

      <div className="field">
        <label htmlFor="quiz-explanation">해설 (선택)</label>
        <textarea
          id="quiz-explanation"
          value={draft.explanation}
          onChange={(e) => set({ explanation: e.target.value })}
          placeholder="춘천 막국수는 메밀가루로 반죽해 만듭니다."
        />
        {/* 해설은 정답을 설명하는 글이라 사실상 정답이다. 공개 시점을 서버가
            정한다는 사실을 여기서 분명히 말해 둬야, 운영자가 "왜 안 보이지"
            하지 않는다. */}
        <span className="hint">
          <b>맞힌 뒤</b>, 또는 <b>시도 횟수를 다 쓴 뒤</b>에만 보입니다. 시도가 남아 있을 때는
          내려가지 않습니다 — 해설에 정답이 적혀 있어 남은 시도가 공짜가 되기 때문입니다.
        </span>
        {badField === 'explanation' && <span className="err">해설이 너무 깁니다.</span>}
      </div>
    </div>
  );
}

// ── 안내 ────────────────────────────────────────────────────────────────────

function InfoFields({
  draft,
  onChange,
  badField,
}: {
  draft: InfoDraft;
  onChange: (d: InfoDraft) => void;
  badField?: string;
}) {
  const set = (patch: Partial<InfoDraft>) => onChange({ ...draft, ...patch });

  function setLink(i: number, patch: Partial<InfoDraft['links'][number]>) {
    const links = draft.links.map((l, n) => (n === i ? { ...l, ...patch } : l));
    set({ links });
  }

  return (
    <div className="stack" style={{ gap: 'var(--space-4)' }}>
      <div className="field">
        <label htmlFor="info-body">안내 내용</label>
        <textarea
          id="info-body"
          value={draft.body}
          onChange={(e) => set({ body: e.target.value })}
          placeholder="춘천 소양강 스카이워크는 도보 15분 거리입니다…"
        />
        {badField === 'body' && <span className="err">안내 내용을 입력해 주세요.</span>}
      </div>

      <div className="field field--inline">
        <label htmlFor="info-dwell">최소 열람 시간</label>
        <input
          id="info-dwell"
          type="number"
          min={0}
          max={120}
          className="tabular"
          value={draft.min_dwell_seconds}
          onChange={(e) => set({ min_dwell_seconds: e.target.value })}
        />
        <span className="unit">초</span>
        <span className="hint">
          이 시간이 지나야 확인 버튼이 열립니다. 서버도 스캔 시각으로 함께 확인합니다.
        </span>
      </div>

      <div className="field">
        <label>링크 (선택, 최대 5개)</label>
        <div className="stack" style={{ gap: 'var(--space-2)' }}>
          {draft.links.map((l, i) => (
            <div key={i} className="row" style={{ gap: 'var(--space-2)' }}>
              <input
                value={l.label}
                onChange={(e) => setLink(i, { label: e.target.value })}
                placeholder="관광 코스 보기"
                style={{ flex: '1 1 140px' }}
                aria-label={`${i + 1}번 링크 이름`}
              />
              <input
                value={l.url}
                onChange={(e) => setLink(i, { url: e.target.value })}
                placeholder="https://…"
                style={{ flex: '2 1 200px' }}
                aria-label={`${i + 1}번 링크 주소`}
              />
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => set({ links: draft.links.filter((_, n) => n !== i) })}
                aria-label={`${i + 1}번 링크 삭제`}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        {badField === 'links' && (
          <span className="err">링크 주소는 http:// 또는 https:// 로 시작해야 합니다.</span>
        )}
        {draft.links.length < 5 && (
          <button
            type="button"
            className="btn btn--ghost"
            style={{ alignSelf: 'flex-start', marginTop: 'var(--space-2)' }}
            onClick={() => set({ links: [...draft.links, { label: '', url: '' }] })}
          >
            ＋ 링크 추가
          </button>
        )}
      </div>
    </div>
  );
}

// ── 설문 ────────────────────────────────────────────────────────────────────

/** 최대 5문항. 부스 앞에 서서 답하는 설문이라 길면 아무도 끝내지 않고,
 *  중간에 그만두면 참여 자체가 완료되지 않는다. 서버도 같은 상한을 건다. */
const MAX_QUESTIONS = 5;

function SurveyFields({
  draft,
  onChange,
}: {
  draft: SurveyDraft;
  onChange: (next: SurveyDraft) => void;
}) {
  const set = (index: number, patch: Partial<SurveyQuestion>) =>
    onChange({
      questions: draft.questions.map((q, i) => (i === index ? { ...q, ...patch } : q)),
    });

  return (
    <div className="stack" style={{ gap: 'var(--space-4)' }}>
      {draft.questions.map((q, i) => (
        <div key={i} className="card card--sunk stack" style={{ gap: 'var(--space-3)' }}>
          <div className="row wrap" style={{ justifyContent: 'space-between' }}>
            <p className="eyebrow">{i + 1}번 문항</p>
            {draft.questions.length > 1 && (
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() =>
                  onChange({ questions: draft.questions.filter((_, x) => x !== i) })
                }
              >
                문항 삭제
              </button>
            )}
          </div>

          <div className="field">
            <label htmlFor={`sq-${i}`}>질문</label>
            <input
              id={`sq-${i}`}
              value={q.text}
              onChange={(e) => set(i, { text: e.target.value })}
              placeholder="부스 만족도"
              maxLength={200}
            />
          </div>

          <div className="row wrap" style={{ gap: 'var(--space-2)' }}>
            <label className="pickr" data-on={q.type === 'rating'}>
              <input
                type="radio"
                name={`sqt-${i}`}
                checked={q.type === 'rating'}
                onChange={() => set(i, { type: 'rating' })}
              />
              <span>
                <strong>평점</strong>
                <small>1~N 중에 고릅니다</small>
              </span>
            </label>
            <label className="pickr" data-on={q.type === 'choice'}>
              <input
                type="radio"
                name={`sqt-${i}`}
                checked={q.type === 'choice'}
                onChange={() => set(i, { type: 'choice' })}
              />
              <span>
                <strong>선택</strong>
                <small>보기 중에 고릅니다</small>
              </span>
            </label>
          </div>

          {q.type === 'rating' ? (
            <div className="field" style={{ maxWidth: 200 }}>
              <label htmlFor={`ss-${i}`}>척도 (2~7)</label>
              <input
                id={`ss-${i}`}
                type="number"
                min={2}
                max={7}
                value={q.scale}
                onChange={(e) => set(i, { scale: e.target.value })}
              />
              {/* 왜 7 이 상한인지 밝힌다. 숫자만 두면 임의로 보인다. */}
              <small className="muted">
                7 을 넘으면 사람이 구간을 구분하지 못해 답이 가운데로 몰립니다.
              </small>
            </div>
          ) : (
            <div className="stack" style={{ gap: 6 }}>
              {q.choices.map((c, j) => (
                <input
                  key={j}
                  value={c}
                  placeholder={`${j + 1}번 보기`}
                  onChange={(e) =>
                    set(i, {
                      choices: q.choices.map((x, y) => (y === j ? e.target.value : x)),
                    })
                  }
                />
              ))}
              {q.choices.length < 6 && (
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => set(i, { choices: [...q.choices, ''] })}
                >
                  보기 추가
                </button>
              )}
            </div>
          )}
        </div>
      ))}

      {draft.questions.length < MAX_QUESTIONS && (
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() =>
            onChange({
              questions: [
                ...draft.questions,
                { type: 'rating', text: '', scale: '5', choices: ['', ''] },
              ],
            })
          }
        >
          문항 추가 ({draft.questions.length}/{MAX_QUESTIONS})
        </button>
      )}

      {/* 이 약속을 화면에도 적는다. 운영자가 "자유 서술은 왜 없지" 를
          물어보기 전에 답해야 한다. */}
      <p className="muted">
        자유 서술 문항은 만들 수 없습니다. 이름·연락처 같은 개인정보가 섞이면 설문의
        수집 범위가 완전히 달라지기 때문입니다. 응답은 참여 코드와만 연결됩니다.
      </p>
    </div>
  );
}
