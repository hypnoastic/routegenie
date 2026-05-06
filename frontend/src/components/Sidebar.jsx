import { BookmarkIcon, ClockIcon, UserIcon } from './Icons';

function shortDate(value) {
  if (!value) {
    return '';
  }
  return new Date(value).toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function searchLabel(search) {
  return search.query_text || 'Search';
}

function searchMeta(search) {
  return (search.transcript || search.gemini_response || '').slice(0, 44) || shortDate(search.created_at);
}

export default function Sidebar({
  recentSearches,
  savedTrips,
  onSelectTrip,
  onSelectSearch,
  user,
  preferences,
  isDummySession,
  onLogout,
  onUpdatePreferences,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <div className="sidebar-brand">
          <span className="brand-mark">RG</span>
          <span className="sidebar-brand__wordmark">Route Genie</span>
        </div>
      </div>

      <div className="sidebar-scroll">
        <section className="sidebar-section">
          <div className="section-label">Recent</div>
          {recentSearches.length === 0 ? (
            <div className="empty-inline">No trips yet</div>
          ) : (
            recentSearches.map((search) => (
              <button key={search.id} className="rail-item" onClick={() => onSelectSearch(search)}>
                <span className="rail-item__icon">
                  <ClockIcon className="icon icon--xs" />
                </span>
                <span className="rail-item__content">
                  <strong>{searchLabel(search)}</strong>
                  <small>{searchMeta(search)}</small>
                </span>
              </button>
            ))
          )}
        </section>

        <section className="sidebar-section">
          <div className="section-label">Saved</div>
          {savedTrips.length === 0 ? (
            <div className="empty-inline">No trips yet</div>
          ) : (
            savedTrips.map((trip) => (
              <button key={trip.id} className="rail-item" onClick={() => onSelectTrip(trip)}>
                <span className="rail-item__icon">
                  <BookmarkIcon className="icon icon--xs" />
                </span>
                <span className="rail-item__content">
                  <strong>{trip.title}</strong>
                  <small>{trip.origin_text} → {trip.destination_text}</small>
                </span>
              </button>
            ))
          )}
        </section>
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-profile">
          <span className="sidebar-profile__avatar">
            <UserIcon className="icon icon--sm" />
          </span>
          <div className="sidebar-profile__meta">
            <strong>{user?.name || 'Profile'}</strong>
            <small>{user?.email}</small>
          </div>
        </div>

        <div className="sidebar-settings">
          <label className="toggle-row">
            <span>Personalize</span>
            <input
              type="checkbox"
              checked={Boolean(preferences?.personalization_enabled)}
              onChange={(event) => onUpdatePreferences({ personalization_enabled: event.target.checked })}
            />
          </label>
          <label className="toggle-row">
            <span>Safer</span>
            <input
              type="checkbox"
              checked={Boolean(preferences?.safety_mode)}
              onChange={(event) => onUpdatePreferences({ safety_mode: event.target.checked })}
            />
          </label>
        </div>

        {isDummySession ? <div className="dev-note">Dev only</div> : null}

        <button className="button button--ghost button--full" onClick={onLogout}>
          Sign out
        </button>
      </div>
    </aside>
  );
}
