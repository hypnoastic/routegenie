import { BookmarkMiniIcon, ShareIcon } from './Icons';

function activeOption(routeData, activeComparisonId) {
  if (!routeData) {
    return null;
  }
  return (
    routeData.comparison_options?.find((option) => option.id === activeComparisonId)
    || routeData.comparison_options?.[0]
    || null
  );
}

export default function RouteSummaryCard({
  routeData,
  activeComparisonId,
  onSelectComparison,
  onSaveTrip,
  onShareTrip,
  saving,
  sharing,
}) {
  if (!routeData) {
    return null;
  }

  const selected = activeOption(routeData, activeComparisonId);
  const routeTag = selected?.label || 'Route';
  const stopCount = routeData.stops?.length || 0;

  return (
    <section className="route-summary">
      <div className="route-summary__line">
        <span className="route-summary__path">
          {routeData.origin} <span aria-hidden="true">→</span> {routeData.destination}
        </span>
        <span className="summary-tag">{routeTag}</span>
      </div>

      {routeData.comparison_options?.length ? (
        <div className="summary-options" role="tablist" aria-label="Route options">
          {routeData.comparison_options.map((option) => (
            <button
              key={option.id}
              className={`summary-option ${selected?.id === option.id ? 'summary-option--active' : ''}`}
              onClick={() => onSelectComparison(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}

      <div className="summary-metrics">
        <div>
          <span className="metric-label">ETA</span>
          <strong>{selected?.duration_text || routeData.duration_text}</strong>
        </div>
        <div>
          <span className="metric-label">Distance</span>
          <strong>{selected?.distance_text || routeData.distance_text}</strong>
        </div>
        <div>
          <span className="metric-label">Stops</span>
          <strong>{stopCount}</strong>
        </div>
      </div>

      <div className="summary-actions">
        <button className="button button--primary" onClick={onSaveTrip} disabled={saving}>
          <BookmarkMiniIcon className="icon icon--sm" />
          <span>{saving ? 'Saving' : 'Save'}</span>
        </button>
        <button className="button button--ghost" onClick={onShareTrip} disabled={sharing}>
          <ShareIcon className="icon icon--sm" />
          <span>{sharing ? 'Sharing' : 'Share'}</span>
        </button>
      </div>
    </section>
  );
}
