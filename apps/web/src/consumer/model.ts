/**
 * The participant-facing interpretation of the existing transactional domains.
 *
 * This is deliberately a view model, not a new backend entity. Source identity is
 * retained so every participant action still returns to the domain that owns it.
 */

export const EXPERIENCE_SOURCE_TYPES = ['mission', 'lecture', 'exhibit'] as const;

export type ExperienceSourceType = (typeof EXPERIENCE_SOURCE_TYPES)[number];

export type ExperienceMode = 'participate' | 'attend' | 'explore';

export type ExperienceAvailability = 'available' | 'unavailable' | 'unknown';

export type ParticipationActionKind =
  | 'scan_qr'
  | 'show_participant_code'
  | 'lecture_check_in'
  | 'exhibit_vote'
  | 'view_only'
  | 'none';

export interface ParticipationAction {
  kind: ParticipationActionKind;
  label: string | null;
  requiresParticipant: boolean;
}

export interface ExperienceDuration {
  minutes: number;
  /** `scheduled` is calculated only from an explicit start and end time. */
  basis: 'estimated' | 'scheduled';
}

export interface ExperienceReward {
  kind: 'points';
  points: number;
}

export interface ConsumerExperience {
  /** Stable key within an event and across refreshed DTO instances. */
  key: string;
  sourceType: ExperienceSourceType;
  sourceId: number;

  title: string;
  summary?: string;
  imageUrl?: string;
  typeLabel: string;
  mode: ExperienceMode;

  /** Exact source timestamps. Adapters omit invalid or absent timestamps. */
  startAt?: string;
  endAt?: string;
  duration?: ExperienceDuration;
  /** A source item's own location; never a festival-wide venue fallback. */
  placeLabel?: string;
  hostLabel?: string;
  tags: string[];

  participationAction: ParticipationAction;
  /** `unknown` means the server has not exposed enough state to make the claim. */
  availability: ExperienceAvailability;
  /** `null` means participant-specific completion state was not supplied. */
  completed: boolean | null;
  /** Transaction timestamp only when the source API exposes one. */
  completedAt?: string;
  featured: boolean;
  reward?: ExperienceReward;
}

export function experienceSourceKey(
  sourceType: ExperienceSourceType,
  sourceId: number,
): string {
  return `${sourceType}:${sourceId}`;
}

export function isExperienceSourceType(value: unknown): value is ExperienceSourceType {
  return (
    typeof value === 'string' &&
    (EXPERIENCE_SOURCE_TYPES as readonly string[]).includes(value)
  );
}
