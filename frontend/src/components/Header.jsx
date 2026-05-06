export default function Header({ isLoggedIn, onOpenAuth }) {
  return (
    <header className="topbar">
      {!isLoggedIn ? (
        <div className="topbar-actions">
          <button className="button button--primary" onClick={() => onOpenAuth('login')}>
            Login / Sign up
          </button>
        </div>
      ) : null}
    </header>
  );
}
