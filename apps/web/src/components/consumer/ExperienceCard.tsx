import { Link } from 'react-router-dom';

import { experienceMetadata } from '../../consumer/metadata';
import type { ConsumerExperience } from '../../consumer/model';

export type ExperienceOpenContext =
  | 'now'
  | 'featured'
  | 'explore_time'
  | 'explore_place'
  | 'explore_type'
  | 'search'
  | 'shared_link'
  | 'flow';

export function experienceHref(
  festivalId: string,
  experience: Pick<ConsumerExperience, 'sourceType' | 'sourceId'>,
  context: ExperienceOpenContext,
): string {
  const search = new URLSearchParams({ from: context });
  return `/join/${festivalId}/experience/${experience.sourceType}/${experience.sourceId}?${search}`;
}

export function ExperienceCard({
  festivalId,
  experience,
  context,
  featured = false,
}: {
  festivalId: string;
  experience: ConsumerExperience;
  context: ExperienceOpenContext;
  featured?: boolean;
}) {
  const signals = experienceMetadata(experience);

  return (
    <Link
      to={experienceHref(festivalId, experience, context)}
      className={`consumer-experience-card${featured ? ' consumer-experience-card--featured' : ''}`}
    >
      {experience.imageUrl && (
        <img
          className="consumer-experience-card__image"
          src={experience.imageUrl}
          alt=""
          loading={featured ? 'eager' : 'lazy'}
        />
      )}
      <span className="consumer-experience-card__body">
        <span className="consumer-experience-card__kicker">
          {experience.typeLabel}
          {experience.completed === true && <b>내 Flow에 있음</b>}
        </span>
        <strong className="consumer-experience-card__title">{experience.title}</strong>
        {featured && experience.summary && (
          <span className="consumer-experience-card__summary">{experience.summary}</span>
        )}
        {signals.length > 0 && (
          <span className="consumer-experience-card__signals">
            {signals.slice(0, 3).map((signal) => (
              <span key={signal.kind}>{signal.label}</span>
            ))}
          </span>
        )}
      </span>
      <span className="consumer-experience-card__arrow" aria-hidden>
        →
      </span>
    </Link>
  );
}
