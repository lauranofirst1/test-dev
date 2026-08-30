import type {
  MissionStatus,
  MyAttendance,
  PublicBooth,
  PublicExperienceExhibit,
  PublicFestival,
  PublicLecture,
  PublicExhibit,
} from '../api/types';
import { optionalText, positiveMinutes, scheduledDuration } from './metadata';
import {
  experienceSourceKey,
  type ConsumerExperience,
  type ExperienceMode,
} from './model';

export interface ConsumerParticipantState {
  missions?: MissionStatus[];
  lectures?: MyAttendance[];
  exhibits?: PublicExhibit[];
}

const BOOTH_MODE: Record<string, { label: string; mode: ExperienceMode }> = {
  experience: { label: '직접 해보기', mode: 'participate' },
  food: { label: '먹기', mode: 'explore' },
  performance: { label: '보기·듣기', mode: 'attend' },
  information: { label: '둘러보기', mode: 'explore' },
  local_shop: { label: '둘러보기', mode: 'explore' },
  etc: { label: '둘러보기', mode: 'explore' },
};

function missionExperiences(
  booth: PublicBooth,
  statuses: MissionStatus[] | undefined,
): ConsumerExperience[] {
  const byId = new Map(statuses?.map((status) => [status.mission_id, status]));
  const kind = BOOTH_MODE[booth.booth_type] ?? BOOTH_MODE.etc;
  return booth.missions.map((mission) => {
    const status = byId.get(mission.id);
    const minutes = positiveMinutes(mission.estimated_duration_minutes);
    return {
      key: experienceSourceKey('mission', mission.id),
      sourceType: 'mission',
      sourceId: mission.id,
      title: mission.title,
      summary: optionalText(mission.description),
      typeLabel: optionalText(booth.type_label) ?? kind.label,
      mode: kind.mode,
      duration: minutes ? { minutes, basis: 'estimated' } : undefined,
      placeLabel: optionalText(booth.location),
      tags: [],
      participationAction:
        booth.verify_mode === 'participant_scan'
          ? { kind: 'scan_qr', label: '현장 QR로 기록하기', requiresParticipant: true }
          : {
              kind: 'show_participant_code',
              label: '부스 스태프에게 참여 코드 보여주기',
              requiresParticipant: true,
            },
      availability: 'available',
      completed: statuses === undefined ? null : status?.status === 'granted',
      completedAt: status?.completed_at ?? undefined,
      featured: mission.is_featured,
      reward: mission.points > 0 ? { kind: 'points', points: mission.points } : undefined,
    };
  });
}

function lectureExperience(
  lecture: PublicLecture,
  attendances: MyAttendance[] | undefined,
): ConsumerExperience {
  const attendance = attendances?.find((item) => item.session_id === lecture.id);
  return {
    key: experienceSourceKey('lecture', lecture.id),
    sourceType: 'lecture',
    sourceId: lecture.id,
    title: lecture.title,
    summary: optionalText(lecture.summary),
    typeLabel: '강연·프로그램',
    mode: 'attend',
    startAt: lecture.starts_at,
    endAt: lecture.ends_at,
    duration: scheduledDuration(lecture.starts_at, lecture.ends_at),
    placeLabel: optionalText(lecture.location),
    hostLabel: [optionalText(lecture.speaker), optionalText(lecture.affiliation)]
      .filter(Boolean)
      .join(' · ') || undefined,
    tags: [],
    participationAction: {
      kind: 'lecture_check_in',
      label: '현장 체크인 안내 보기',
      requiresParticipant: true,
    },
    availability: 'available',
    // A checkpoint is evidence for one instant, not a completed lecture. The
    // backend's attendance rule remains the only completion authority.
    completed: attendances === undefined ? null : Boolean(attendance?.is_met),
    completedAt: attendance?.is_met ? attendance.completed_at ?? undefined : undefined,
    featured: lecture.is_featured,
  };
}

function exhibitExperience(
  exhibit: PublicExperienceExhibit,
  participantExhibits: PublicExhibit[] | undefined,
): ConsumerExperience {
  const mine = participantExhibits?.find((item) => item.id === exhibit.id);
  const minutes = positiveMinutes(exhibit.estimated_duration_minutes);
  return {
    key: experienceSourceKey('exhibit', exhibit.id),
    sourceType: 'exhibit',
    sourceId: exhibit.id,
    title: exhibit.title,
    summary: optionalText(exhibit.summary),
    imageUrl: optionalText(exhibit.poster_url),
    typeLabel: '전시·작품',
    mode: 'explore',
    duration: minutes ? { minutes, basis: 'estimated' } : undefined,
    placeLabel: optionalText(exhibit.location),
    hostLabel: optionalText(exhibit.team_name),
    tags: exhibit.tags.filter((tag) => optionalText(tag)),
    participationAction: {
      kind: 'exhibit_vote',
      label: mine?.voted ? '내 투표 확인하기' : '작품 둘러보고 투표하기',
      requiresParticipant: true,
    },
    availability: 'available',
    completed: participantExhibits === undefined ? null : Boolean(mine?.voted),
    completedAt: mine?.voted ? mine.voted_at ?? undefined : undefined,
    featured: exhibit.is_featured,
  };
}

export function adaptFestivalExperiences(
  festival: PublicFestival,
  state: ConsumerParticipantState = {},
): ConsumerExperience[] {
  return [
    ...festival.booths.flatMap((booth) => missionExperiences(booth, state.missions)),
    ...festival.lectures.map((lecture) => lectureExperience(lecture, state.lectures)),
    ...festival.exhibits.map((exhibit) => exhibitExperience(exhibit, state.exhibits)),
  ];
}

export function featuredExperiences(experiences: ConsumerExperience[], limit = 3) {
  const selected = experiences.filter((item) => item.featured).slice(0, limit);
  if (selected.length >= limit) return selected;
  const selectedKeys = new Set(selected.map((item) => item.key));
  return [
    ...selected,
    ...experiences.filter((item) => !selectedKeys.has(item.key)).slice(0, limit - selected.length),
  ];
}
