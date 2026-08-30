import { isExperienceSourceType, type ConsumerExperience, type ExperienceSourceType } from './model';

export interface ConsumerMoment {
  key: string;
  sourceType: ExperienceSourceType;
  sourceId: number;
  title: string;
  typeLabel: string;
  occurredAt?: string;
  personal: boolean;
  verified: boolean;
}

export interface PersonalMomentRecord {
  source_type: ExperienceSourceType;
  source_id: number;
  title: string;
  type_label: string;
  created_at: string;
}

const storageKey = (festivalId: string | number) =>
  `festaflow-personal-moments-${festivalId}`;
const CHANGED = 'festaflow:personal-moments-changed';

function validRecord(value: unknown): value is PersonalMomentRecord {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<PersonalMomentRecord>;
  return (
    isExperienceSourceType(item.source_type) &&
    typeof item.source_id === 'number' &&
    item.source_id > 0 &&
    typeof item.title === 'string' &&
    item.title.trim().length > 0 &&
    typeof item.type_label === 'string' &&
    typeof item.created_at === 'string' &&
    Number.isFinite(Date.parse(item.created_at))
  );
}

export function loadPersonalMoments(festivalId: string | number): PersonalMomentRecord[] {
  try {
    const raw = localStorage.getItem(storageKey(festivalId));
    const values: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(values) ? values.filter(validRecord) : [];
  } catch {
    return [];
  }
}

function persist(festivalId: string | number, records: PersonalMomentRecord[]) {
  try {
    localStorage.setItem(storageKey(festivalId), JSON.stringify(records));
  } catch {
    return;
  }
  window.dispatchEvent(new CustomEvent(CHANGED, { detail: String(festivalId) }));
}

export function savePersonalMoment(
  festivalId: string | number,
  experience: ConsumerExperience,
  now = new Date(),
): PersonalMomentRecord[] {
  const current = loadPersonalMoments(festivalId);
  if (
    current.some(
      (item) => item.source_type === experience.sourceType && item.source_id === experience.sourceId,
    )
  ) {
    return current;
  }
  const next = [
    ...current,
    {
      source_type: experience.sourceType,
      source_id: experience.sourceId,
      title: experience.title,
      type_label: experience.typeLabel,
      created_at: now.toISOString(),
    },
  ];
  persist(festivalId, next);
  return next;
}

export function removePersonalMoment(
  festivalId: string | number,
  sourceType: ExperienceSourceType,
  sourceId: number,
) {
  const next = loadPersonalMoments(festivalId).filter(
    (item) => item.source_type !== sourceType || item.source_id !== sourceId,
  );
  persist(festivalId, next);
  return next;
}

export function onPersonalMomentsChange(handler: () => void) {
  window.addEventListener(CHANGED, handler);
  window.addEventListener('storage', handler);
  return () => {
    window.removeEventListener(CHANGED, handler);
    window.removeEventListener('storage', handler);
  };
}

export function mergeMoments(
  experiences: ConsumerExperience[],
  personalRecords: PersonalMomentRecord[],
): ConsumerMoment[] {
  const verified = experiences
    .filter((experience) => experience.completed === true)
    .map<ConsumerMoment>((experience) => ({
      key: experience.key,
      sourceType: experience.sourceType,
      sourceId: experience.sourceId,
      title: experience.title,
      typeLabel: experience.typeLabel,
      occurredAt: experience.completedAt,
      personal: false,
      verified: true,
    }));
  const verifiedKeys = new Set(verified.map((moment) => moment.key));
  const personal = personalRecords
    .filter((record) => !verifiedKeys.has(`${record.source_type}:${record.source_id}`))
    .map<ConsumerMoment>((record) => ({
      key: `${record.source_type}:${record.source_id}`,
      sourceType: record.source_type,
      sourceId: record.source_id,
      title: record.title,
      typeLabel: record.type_label,
      occurredAt: record.created_at,
      personal: true,
      verified: false,
    }));
  return [...verified, ...personal].sort((a, b) => {
    if (!a.occurredAt && !b.occurredAt) return a.title.localeCompare(b.title, 'ko');
    if (!a.occurredAt) return 1;
    if (!b.occurredAt) return -1;
    return Date.parse(b.occurredAt) - Date.parse(a.occurredAt);
  });
}
