import type { CSSProperties } from "react";

// Robot mascot (SVG, currentColor). Used in the chat
// greeting hero and as the assistant message avatar.
export function RobotMascot({
  className,
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      stroke="currentColor"
      strokeWidth={3}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      aria-hidden
    >
      {/* antenna */}
      <line x1="32" y1="8" x2="32" y2="15" />
      <circle cx="32" cy="6" r="2.6" fill="currentColor" stroke="none" />
      {/* head */}
      <rect x="14" y="15" width="36" height="27" rx="9" />
      {/* ears */}
      <rect x="7" y="24" width="5" height="10" rx="2.5" />
      <rect x="52" y="24" width="5" height="10" rx="2.5" />
      {/* eyes */}
      <circle cx="25" cy="27" r="3.2" fill="currentColor" stroke="none" />
      <circle cx="39" cy="27" r="3.2" fill="currentColor" stroke="none" />
      {/* smile */}
      <path d="M25 34 q7 6 14 0" />
      {/* body hint */}
      <path d="M23 42 v3 a4 4 0 0 0 4 4 h10 a4 4 0 0 0 4 -4 v-3" />
    </svg>
  );
}

// Robot mascot in a gold hexagon (avatar / hero).
export function RobotHex({ px = 28 }: { px?: number }) {
  return (
    <span
      className="relative inline-flex shrink-0 items-center justify-center drop-shadow-[0_0_5px_rgba(214,184,120,0.3)]"
      style={{ width: px, height: Math.round(px * 1.13) }}
    >
      <span className="hex absolute inset-0 bg-gold" />
      <span className="hex absolute inset-[1.5px] bg-surface-muted" />
      <RobotMascot
        className="relative z-[1] text-brand-strong"
        style={{ width: px * 0.6, height: px * 0.6 }}
      />
    </span>
  );
}

// User avatar: initial in a circle.
export function UserAvatar({ initial }: { initial: string }) {
  return (
    <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border-strong bg-surface-muted text-[11px] font-semibold text-text-muted">
      {initial}
    </span>
  );
}
