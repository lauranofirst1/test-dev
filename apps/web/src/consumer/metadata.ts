import type { ConsumerExperience, ExperienceDuration } from './model';

const MINUTE_MS = 60_000;
const EXPLICIT_DATE_TIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;

export function optionalText(value: string | null | undefined): string | undefined {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

/** Unknown, zero, negative, and non-finite duration values are all omitted. */
export function positiveMinutes(value: number | null | undefined): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return undefined;
  return Math.ceil(value);
}

/**
 * Keeps only a parseable value that contains an explicit clock time. A date-only
 * value must never accidentally become a midnight schedule.
 */
export function explicitDateTime(value: string | null | undefined): string | undefined {
  const text = optionalText(value);
  if (!text || !EXPLICIT_DATE_TIME.test(text) || !Number.isFinite(Date.parse(text))) {
    return undefined;
  }
  return text;
}

export function scheduledDuration(
  startAt: string | null | undefined,
  endAt: string | null | undefined,
): ExperienceDuration | undefined {
  const start = explicitDateTime(startAt);
  const end = explicitDateTime(endAt);
  if (!start || !end) return undefined;

  const milliseconds = Date.parse(end) - Date.parse(start);
  if (milliseconds <= 0) return undefined;
  return { minutes: Math.ceil(milliseconds / MINUTE_MS), basis: 'scheduled' };
}

export type TimeContext =
  | {
      phase: 'upcoming';
      startAt: string;
      endAt: string;
      minutesUntilStart: number;
    }
  | {
      phase: 'happening';
      startAt: string;
      endAt: string;
      minutesUntilEnd: number;
    }
  | {
      phase: 'ended';
      startAt: string;
      endAt: string;
    };

export interface TimeRange {
  startAt?: string | null;
  endAt?: string | null;
}

/**
 * Derives relative state only when both ends of a valid schedule are present.
 * With one missing boundary we can show the raw known value elsewhere, but we
 * cannot honestly call the experience upcoming, happening, or ended.
 */
export function deriveTimeContext(
  range: TimeRange,
  now: Date | number = Date.now(),
): TimeContext | null {
  const startAt = explicitDateTime(range.startAt);
  const endAt = explicitDateTime(range.endAt);
  if (!startAt || !endAt) return null;

  const start = Date.parse(startAt);
  const end = Date.parse(endAt);
  const current = typeof now === 'number' ? now : now.getTime();
  if (!Number.isFinite(current) || end <= start) return null;

  if (current < start) {
    return {
      phase: 'upcoming',
      startAt,
      endAt,
      minutesUntilStart: Math.max(1, Math.ceil((start - current) / MINUTE_MS)),
    };
  }
  if (current < end) {
    return {
      phase: 'happening',
      startAt,
      endAt,
      minutesUntilEnd: Math.max(1, Math.ceil((end - current) / MINUTE_MS)),
    };
  }
  return { phase: 'ended', startAt, endAt };
}

export interface TimeContextFormatOptions {
  locale?: string;
  timeZone?: string;
  soonWindowMinutes?: number;
}

function clockLabel(value: string, options: TimeContextFormatOptions): string {
  return new Intl.DateTimeFormat(options.locale ?? 'ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    ...(options.timeZone ? { timeZone: options.timeZone } : {}),
  }).format(new Date(value));
}

export function formatTimeContext(
  context: TimeContext,
  options: TimeContextFormatOptions = {},
): string {
  const soonWindow = positiveMinutes(options.soonWindowMinutes) ?? 60;
  if (context.phase === 'upcoming') {
    return context.minutesUntilStart <= soonWindow
      ? `${context.minutesUntilStart}분 뒤 시작`
      : `${clockLabel(context.startAt, options)} 시작`;
  }
  if (context.phase === 'happening') {
    return context.minutesUntilEnd <= soonWindow
      ? `${context.minutesUntilEnd}분 뒤 종료`
      : `${clockLabel(context.endAt, options)}까지`;
  }
  return '종료됨';
}

export function formatDuration(duration: ExperienceDuration): string {
  const hours = Math.floor(duration.minutes / 60);
  const minutes = duration.minutes % 60;
  if (hours === 0) return `${minutes}분`;
  if (minutes === 0) return `${hours}시간`;
  return `${hours}시간 ${minutes}분`;
}

export type ExperienceMetadataSignal =
  | { kind: 'time'; label: string; context: TimeContext }
  | { kind: 'duration'; label: string; duration: ExperienceDuration }
  | { kind: 'place'; label: string };

/** Returns only source-backed signals; it never manufactures placeholder metadata. */
export function experienceMetadata(
  experience: ConsumerExperience,
  now: Date | number = Date.now(),
  formatOptions: TimeContextFormatOptions = {},
): ExperienceMetadataSignal[] {
  const signals: ExperienceMetadataSignal[] = [];
  const time = deriveTimeContext(experience, now);
  if (time) {
    signals.push({ kind: 'time', label: formatTimeContext(time, formatOptions), context: time });
  }
  if (experience.duration) {
    signals.push({
      kind: 'duration',
      label: formatDuration(experience.duration),
      duration: experience.duration,
    });
  }
  if (experience.placeLabel) {
    signals.push({ kind: 'place', label: experience.placeLabel });
  }
  return signals;
}
