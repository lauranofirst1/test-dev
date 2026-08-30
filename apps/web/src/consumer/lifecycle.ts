export type EventPhase = 'upcoming' | 'active' | 'ended' | 'unknown';

export interface EventPhaseInput {
  status?: string | null;
  startsOn?: string | null;
  endsOn?: string | null;
}

function calendarDate(value: string | null | undefined): string | null {
  if (typeof value !== 'string') return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return null;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }
  return `${match[1]}-${match[2]}-${match[3]}`;
}

function currentCalendarDate(now: Date, timeZone?: string): string | null {
  if (!Number.isFinite(now.getTime())) return null;
  if (!timeZone) {
    const year = String(now.getFullYear()).padStart(4, '0');
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  try {
    const parts = new Intl.DateTimeFormat('en', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(now);
    const part = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find((candidate) => candidate.type === type)?.value;
    const year = part('year');
    const month = part('month');
    const day = part('day');
    return year && month && day ? `${year}-${month}-${day}` : null;
  } catch {
    return null;
  }
}

/**
 * A closed status wins immediately. A passed date-only end is also conclusive on
 * the following calendar day, even if an operator forgot to advance a stale
 * status. This never invents an end clock time on the final event date.
 */
export function resolveEventPhase(
  event: EventPhaseInput,
  now: Date = new Date(),
  timeZone?: string,
): EventPhase {
  const status = event.status?.trim().toLowerCase();
  const today = currentCalendarDate(now, timeZone);
  const startsOn = calendarDate(event.startsOn);
  const endsOn = calendarDate(event.endsOn);
  if (status === 'closed') return 'ended';
  if (!today) return 'unknown';
  if (startsOn && endsOn && endsOn < startsOn) return 'unknown';

  if (endsOn && today > endsOn) return 'ended';
  if (startsOn && today < startsOn) return 'upcoming';
  if (status === 'live') return 'active';
  if (startsOn && endsOn) return 'active';
  if (status === 'draft' || status === 'planning' || status === 'ready') {
    return 'upcoming';
  }
  return 'unknown';
}

export type ParticipantActionContext = 'scan' | 'check_in' | 'vote' | 'experience';

export type ParticipantLifecycle =
  | 'visitor'
  | 'new_participant'
  | 'active_participant'
  | 'action_context'
  | 'post_action'
  | 'post_event';

export interface ParticipantLifecycleInput {
  hasParticipant: boolean;
  momentCount: number;
  eventPhase: EventPhase;
  actionContext?: ParticipantActionContext | null;
  /** True only for the immediate success state after a verified transaction. */
  postAction?: boolean;
}

export function resolveParticipantLifecycle(
  input: ParticipantLifecycleInput,
): ParticipantLifecycle {
  if (!input.hasParticipant) return 'visitor';
  if (input.postAction) return 'post_action';
  if (input.actionContext) return 'action_context';
  if (input.eventPhase === 'ended') return 'post_event';
  return input.momentCount > 0 ? 'active_participant' : 'new_participant';
}

export type ConsumerEntrySurface = 'arrive' | 'now' | 'action' | 'remember';

export function entrySurfaceForLifecycle(lifecycle: ParticipantLifecycle): ConsumerEntrySurface {
  if (lifecycle === 'visitor') return 'arrive';
  if (lifecycle === 'post_event') return 'remember';
  if (lifecycle === 'action_context' || lifecycle === 'post_action') return 'action';
  return 'now';
}
