export interface FlowMomentView {
  key: string;
  title: string;
  typeLabel: string;
  occurredAt?: string;
  personal: boolean;
  sourceType: 'mission' | 'lecture' | 'exhibit';
  sourceId: number;
}

const SOURCE_MARK: Record<FlowMomentView['sourceType'], string> = {
  mission: '●',
  lecture: '◆',
  exhibit: '■',
};

function timeLabel(value?: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

export function FlowTimeline({ moments, compact = false }: { moments: FlowMomentView[]; compact?: boolean }) {
  const shown = compact ? moments.slice(0, 3) : moments;

  if (shown.length === 0) {
    return (
      <div className="consumer-flow-empty">
        <span className="consumer-flow-empty__node" aria-hidden />
        <p>첫 순간을 기다리고 있어요.</p>
      </div>
    );
  }

  return (
    <div className={`consumer-flow${compact ? ' consumer-flow--compact' : ''}`}>
      <div className="consumer-flow__graphic" aria-hidden>
        {shown.map((moment, index) => (
          <span
            key={moment.key}
            className="consumer-flow__graphic-node"
            data-source={moment.sourceType}
            style={{ ['--flow-index' as string]: index }}
          >
            {SOURCE_MARK[moment.sourceType]}
          </span>
        ))}
      </div>

      <ol className="consumer-flow__timeline">
        {shown.map((moment) => {
          const when = timeLabel(moment.occurredAt);
          return (
            <li key={moment.key}>
              <span className="consumer-flow__dot" data-source={moment.sourceType} aria-hidden />
              <span className="consumer-flow__moment">
                <strong>{moment.title}</strong>
                <span>
                  {when && <time dateTime={moment.occurredAt}>{when}</time>}
                  <span>{moment.typeLabel}</span>
                  {moment.personal && <span>직접 남김</span>}
                </span>
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
