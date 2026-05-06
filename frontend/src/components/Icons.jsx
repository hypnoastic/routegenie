function iconProps(className) {
  return {
    className,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: '1.8',
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': 'true',
  };
}

export function SparkIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M12 2 14.4 9.6 22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4L12 2Z" />
    </svg>
  );
}

export function MicIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M12 15a3 3 0 0 0 3-3V7a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" />
      <path d="M19 12a7 7 0 0 1-14 0" />
      <path d="M12 19v3" />
    </svg>
  );
}

export function MenuIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h16" />
    </svg>
  );
}

export function CloseIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <path d="m6 6 12 12" />
      <path d="m18 6-12 12" />
    </svg>
  );
}

export function ChevronLeftIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

export function ChevronRightIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

export function UserIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M20 21a8 8 0 0 0-16 0" />
      <circle cx="12" cy="8" r="4" />
    </svg>
  );
}

export function SearchIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

export function ClockIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

export function BookmarkIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M7 4h10v16l-5-3-5 3V4Z" />
    </svg>
  );
}

export function ShareIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      <path d="m8.6 13.5 6.8 4" />
      <path d="m15.4 6.5-6.8 4" />
    </svg>
  );
}

export function BookmarkMiniIcon({ className = 'icon' }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M8 5h8v14l-4-2.6L8 19V5Z" />
    </svg>
  );
}
