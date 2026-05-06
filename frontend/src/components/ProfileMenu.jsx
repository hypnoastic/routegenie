import { useMemo, useState } from 'react';
import { UserIcon } from './Icons';

export default function ProfileMenu({ user, preferences, isDummySession, onLogout, onUpdatePreferences }) {
  const [open, setOpen] = useState(false);
  const initials = useMemo(() => {
    const source = user?.name || user?.email || 'RG';
    return source
      .split(' ')
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('');
  }, [user]);

  const handleToggle = async (field, value) => {
    await onUpdatePreferences({ [field]: value });
  };

  return (
    <div className="profile-menu">
      <button className="avatar-button" onClick={() => setOpen((value) => !value)} aria-label="Open profile menu">
        <span>{initials || <UserIcon className="icon icon--sm" />}</span>
      </button>

      {open ? (
        <div className="profile-card">
          <div className="profile-card__user">
            <strong>{user?.name || 'Profile'}</strong>
            <span>{user?.email}</span>
            {isDummySession ? <em>Dev only</em> : null}
          </div>

          <div className="profile-card__settings">
            <label className="toggle-row">
              <span>Personalize</span>
              <input
                type="checkbox"
                checked={Boolean(preferences?.personalization_enabled)}
                onChange={(event) => handleToggle('personalization_enabled', event.target.checked)}
              />
            </label>
            <label className="toggle-row">
              <span>Safer</span>
              <input
                type="checkbox"
                checked={Boolean(preferences?.safety_mode)}
                onChange={(event) => handleToggle('safety_mode', event.target.checked)}
              />
            </label>
          </div>

          <button className="button button--ghost button--full" onClick={onLogout}>
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
