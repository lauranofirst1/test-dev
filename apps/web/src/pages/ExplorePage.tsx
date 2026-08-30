import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { ExperienceCard, type ExperienceOpenContext } from '../components/consumer/ExperienceCard';
import { useConsumerJourney } from '../consumer/hooks';
import { deriveTimeContext } from '../consumer/metadata';
import type { ConsumerExperience } from '../consumer/model';

type Lens = 'time' | 'place' | 'type';

export function ExplorePage() {
  const { id = '' } = useParams<{ id: string }>();
  const { experiences, festival } = useConsumerJourney(id);
  const [lens, setLens] = useState<Lens>('time');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const searched = useMemo(() => {
    const query = search.trim().toLocaleLowerCase('ko');
    if (!query) return [];
    return experiences.filter((item) =>
      [item.title, item.summary, item.placeLabel, item.hostLabel, ...item.tags]
        .filter(Boolean)
        .some((value) => value!.toLocaleLowerCase('ko').includes(query)),
    );
  }, [experiences, search]);

  if (festival.isLoading) return <div className="shell"><div className="skeleton" style={{ height: 240 }} /></div>;

  return (
    <main className="shell consumer-page consumer-explore stack">
      <header className="consumer-page-head">
        <p className="eyebrow">Explore</p>
        <h1>무엇을 만나볼까요?</h1>
        <p className="muted">한 번에 작은 범위만 펼쳐 보여드려요.</p>
      </header>
      <div className="field consumer-search">
        <label className="sr-only" htmlFor="experience-search">행사 경험 검색</label>
        <input id="experience-search" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="경험, 장소, 팀 이름 검색" />
      </div>

      {search.trim() ? (
        <ExperienceSlice title={`검색 결과 ${searched.length}개`} items={searched} festivalId={id} context="search" expanded />
      ) : (
        <>
          <div className="consumer-lenses" role="tablist" aria-label="둘러보기 기준">
            {([['time', '지금'], ['place', '장소'], ['type', '종류']] as const).map(([value, label]) => (
              <button key={value} type="button" role="tab" aria-selected={lens === value} onClick={() => { setLens(value); setExpanded(null); }}>{label}</button>
            ))}
          </div>
          {lens === 'time' && <TimeLens festivalId={id} experiences={experiences} expanded={expanded} onExpanded={setExpanded} />}
          {lens === 'place' && <GroupedLens festivalId={id} experiences={experiences.filter((item) => item.placeLabel)} group={(item) => item.placeLabel!} context="explore_place" expanded={expanded} onExpanded={setExpanded} empty="장소 정보가 있는 경험이 아직 없어요." />}
          {lens === 'type' && <GroupedLens festivalId={id} experiences={experiences} group={(item) => item.typeLabel} context="explore_type" expanded={expanded} onExpanded={setExpanded} empty="둘러볼 경험이 아직 없어요." />}
        </>
      )}
    </main>
  );
}

function TimeLens({ festivalId, experiences, expanded, onExpanded }: { festivalId: string; experiences: ConsumerExperience[]; expanded: string | null; onExpanded: (key: string | null) => void }) {
  const useful = experiences.filter((item) => {
    const context = deriveTimeContext(item);
    return context && context.phase !== 'ended';
  });
  return <ExperienceSlice title="시간이 있는 경험" items={useful} festivalId={festivalId} context="explore_time" expanded={expanded === 'time'} onExpanded={() => onExpanded(expanded === 'time' ? null : 'time')} empty="시간 정보가 있는 경험이 지금은 없어요." />;
}

function GroupedLens({ festivalId, experiences, group, context, expanded, onExpanded, empty }: { festivalId: string; experiences: ConsumerExperience[]; group: (item: ConsumerExperience) => string; context: ExperienceOpenContext; expanded: string | null; onExpanded: (key: string | null) => void; empty: string }) {
  const groups = new Map<string, ConsumerExperience[]>();
  experiences.forEach((item) => groups.set(group(item), [...(groups.get(group(item)) ?? []), item]));
  if (groups.size === 0) return <p className="consumer-quiet-state">{empty}</p>;
  return <div className="stack" style={{ gap: 'var(--space-6)' }}>{[...groups.entries()].map(([label, items]) => <ExperienceSlice key={label} title={label} items={items} festivalId={festivalId} context={context} expanded={expanded === label} onExpanded={() => onExpanded(expanded === label ? null : label)} />)}</div>;
}

function ExperienceSlice({ title, items, festivalId, context, expanded = false, onExpanded, empty }: { title: string; items: ConsumerExperience[]; festivalId: string; context: ExperienceOpenContext; expanded?: boolean; onExpanded?: () => void; empty?: string }) {
  if (items.length === 0) return <p className="consumer-quiet-state">{empty ?? '해당하는 경험이 없어요.'}</p>;
  const shown = expanded ? items : items.slice(0, 4);
  return <section className="stack" style={{ gap: 'var(--space-3)' }}><div className="consumer-section-head"><h2>{title}</h2>{items.length > 4 && onExpanded && <button className="consumer-text-link" type="button" onClick={onExpanded}>{expanded ? '접기' : `${items.length}개 모두 보기`}</button>}</div><div className="consumer-experience-list">{shown.map((item) => <ExperienceCard key={item.key} festivalId={festivalId} experience={item} context={context} />)}</div></section>;
}
