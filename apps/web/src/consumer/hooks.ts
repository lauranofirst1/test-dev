import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { ApiError, api } from '../api/client';
import {
  clearParticipant,
  loadParticipant,
  onParticipantChange,
  participantApi,
} from '../api/participant';
import type {
  MyAttendance,
  ParticipantMe,
  ParticipantOverview,
  PublicFestival,
  VotingStatus,
} from '../api/types';
import { adaptFestivalExperiences } from './adapters';
import {
  loadPersonalMoments,
  mergeMoments,
  onPersonalMomentsChange,
} from './moments';

export function useConsumerJourney(festivalId: string, options?: { extras?: boolean }) {
  const [participant, setParticipant] = useState(() => loadParticipant(festivalId));
  const [personal, setPersonal] = useState(() => loadPersonalMoments(festivalId));
  const includeExtras = Boolean(options?.extras);

  useEffect(() => {
    const sync = () => setParticipant(loadParticipant(festivalId));
    sync();
    return onParticipantChange(sync);
  }, [festivalId]);

  useEffect(() => {
    const sync = () => setPersonal(loadPersonalMoments(festivalId));
    sync();
    return onPersonalMomentsChange(sync);
  }, [festivalId]);

  const festival = useQuery({
    queryKey: ['public', festivalId],
    queryFn: () => api.get<PublicFestival>(`/api/festivals/${festivalId}/public`),
    retry: false,
  });
  const me = useQuery({
    queryKey: ['my-progress', festivalId, participant?.code],
    queryFn: () =>
      participantApi.get<ParticipantMe>(festivalId, '/participants/me', participant!.secret),
    enabled: Boolean(participant && !includeExtras),
    retry: false,
    refetchInterval: 10_000,
  });
  const overview = useQuery({
    queryKey: ['my-overview', festivalId, participant?.code],
    queryFn: () =>
      participantApi.get<ParticipantOverview>(
        festivalId,
        '/participants/me/overview',
        participant!.secret,
      ),
    enabled: Boolean(participant && includeExtras),
    retry: false,
    refetchInterval: 10_000,
  });
  const lectures = useQuery({
    queryKey: ['my-lectures', festivalId, participant?.code],
    queryFn: () =>
      participantApi.get<MyAttendance[]>(festivalId, '/lectures/me', participant!.secret),
    enabled: Boolean(participant && festival.data?.has_lectures),
    retry: false,
    refetchInterval: 15_000,
  });
  const exhibition = useQuery({
    queryKey: ['exhibition', festivalId, participant?.code],
    queryFn: () =>
      participantApi.get<VotingStatus>(festivalId, '/exhibition', participant!.secret),
    enabled: Boolean(participant && festival.data?.has_exhibits),
    retry: false,
  });
  const authFailed = [me.error, overview.error, lectures.error, exhibition.error].some(
    (error) => error instanceof ApiError && error.status === 401,
  );
  useEffect(() => {
    if (!authFailed) return;
    clearParticipant(festivalId);
    setParticipant(null);
  }, [authFailed, festivalId]);

  const meData = overview.data?.me ?? me.data;
  const experiences = useMemo(
    () =>
      festival.data
        ? adaptFestivalExperiences(festival.data, {
            missions: participant && meData ? meData.missions : undefined,
            lectures: participant && lectures.data ? lectures.data : undefined,
            exhibits: participant && exhibition.data ? exhibition.data.exhibits : undefined,
          })
        : [],
    [festival.data, participant, meData, lectures.data, exhibition.data],
  );
  const moments = useMemo(() => mergeMoments(experiences, personal), [experiences, personal]);

  return {
    participant,
    festival,
    me: includeExtras ? { ...overview, data: overview.data?.me } : me,
    lectures,
    exhibition,
    board: { ...overview, data: overview.data?.board },
    draw: { ...overview, data: overview.data?.prize_draw },
    experiences,
    moments,
    personal,
    refreshPersonal: () => setPersonal(loadPersonalMoments(festivalId)),
  };
}
