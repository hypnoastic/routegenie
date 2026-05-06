import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiFetch } from '../lib/api';
import MapCanvas from './MapCanvas';
import RouteSummaryCard from './RouteSummaryCard';

export default function SharedTripPage() {
  const { slug } = useParams();
  const [trip, setTrip] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    apiFetch(`/api/share/${slug}`)
      .then((payload) => setTrip(payload))
      .catch((err) => setError(err.message));
  }, [slug]);

  const routeData = trip?.route_payload_json || null;
  const activeId = routeData?.comparison_options?.[0]?.id;

  return (
    <div className="app-shell">
      <MapCanvas routeData={routeData} activeComparisonId={activeId} />

      <div className="app-overlay">
        <div className="shared-topbar">
          <div className="status-pill">Shared route</div>
          <Link className="button button--ghost" to="/">
            Open app
          </Link>
        </div>

        <div className="panel-stack">
          {error ? (
            <div className="shared-error">{error}</div>
          ) : (
            <RouteSummaryCard
              routeData={routeData}
              activeComparisonId={activeId}
              onSelectComparison={() => {}}
              onSaveTrip={() => {}}
              onShareTrip={() => {}}
              saving={false}
            />
          )}
        </div>
      </div>
    </div>
  );
}
