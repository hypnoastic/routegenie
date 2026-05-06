import { useEffect, useRef, useState } from 'react';
import { loadGoogleIdentityScript } from '../lib/googleAuth';
import { CloseIcon } from './Icons';

export default function AuthModal({
  open,
  mode,
  onClose,
  onSubmit,
  onGoogleAuth,
  onDummyLogin,
  dummyEnabled,
  error,
  loading,
}) {
  const [activeMode, setActiveMode] = useState(mode || 'login');
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const googleButtonRef = useRef(null);
  const clientId = import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID;

  useEffect(() => {
    setActiveMode(mode || 'login');
  }, [mode]);

  useEffect(() => {
    if (!open || !clientId || !googleButtonRef.current) {
      return;
    }
    let cancelled = false;
    loadGoogleIdentityScript()
      .then((google) => {
        if (cancelled || !google?.accounts?.id) {
          return;
        }
        google.accounts.id.initialize({
          client_id: clientId,
          callback: async (response) => {
            if (response.credential) {
              await onGoogleAuth(response.credential);
            }
          },
        });
        googleButtonRef.current.innerHTML = '';
        const width = Math.max(280, Math.round(googleButtonRef.current.getBoundingClientRect().width || 0));
        google.accounts.id.renderButton(googleButtonRef.current, {
          theme: 'outline',
          size: 'large',
          width,
          text: 'continue_with',
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [clientId, onGoogleAuth, open]);

  if (!open) {
    return null;
  }

  const submit = (event) => {
    event.preventDefault();
    onSubmit(activeMode, form);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="auth-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-frame__top">
          <div className="modal-label">Access</div>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            <CloseIcon className="icon icon--sm" />
          </button>
        </div>

        <div className="segmented-control">
          <button className={activeMode === 'login' ? 'is-active' : ''} onClick={() => setActiveMode('login')}>
            Login
          </button>
          <button className={activeMode === 'signup' ? 'is-active' : ''} onClick={() => setActiveMode('signup')}>
            Sign up
          </button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          {activeMode === 'signup' ? (
            <label className="field field--compact">
              <span>Name</span>
              <input
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              />
            </label>
          ) : null}

          <label className="field field--compact">
            <span>Email</span>
            <input
              type="email"
              value={form.email}
              onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
            />
          </label>

          <label className="field field--compact">
            <span>Password</span>
            <input
              type="password"
              value={form.password}
              onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
            />
          </label>

          {error ? <div className="inline-error">{error}</div> : null}

          <button className="button button--primary button--full" type="submit" disabled={loading}>
            {loading ? 'Working' : 'Continue'}
          </button>
        </form>

        {clientId ? (
          <div className="auth-block">
            <div className="divider-label">Google</div>
            <div className="google-auth-target" ref={googleButtonRef} />
          </div>
        ) : null}

        {dummyEnabled ? (
          <div className="auth-block auth-block--dev">
            <div className="dev-note">Dev only</div>
            <button className="button button--ghost button--full" onClick={onDummyLogin}>
              Use dev profile
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
