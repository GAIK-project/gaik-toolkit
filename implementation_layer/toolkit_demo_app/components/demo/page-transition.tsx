"use client";

/**
 * PageTransition – a lightweight fade-in wrapper that avoids the
 * Framer Motion SSR hydration mismatch present in React 19 / Next 16.
 *
 * The root cause: `motion.div` with `initial={{ opacity:0 }}` writes
 * inline styles during SSR.  React 19 then throws a hydration warning
 * because the client-side initial state differs from the server HTML.
 * Adding `suppressHydrationWarning` silences the warning but does NOT
 * cause the animation to run, leaving the page invisible.
 *
 * Solution: render children immediately at opacity:1 until the component
 * mounts, then switch to a Framer Motion animation so the fade-in only
 * ever runs client-side and never conflicts with SSR.
 */

import { motion } from "motion/react";
import { useEffect, useState, type ReactNode, type CSSProperties } from "react";

interface PageTransitionProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function PageTransition({
  children,
  className,
  style,
}: PageTransitionProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    // Server render and first client render: visible, no animation.
    // This keeps the SSR HTML and initial client render in sync.
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className={className}
      style={style}
    >
      {children}
    </motion.div>
  );
}
