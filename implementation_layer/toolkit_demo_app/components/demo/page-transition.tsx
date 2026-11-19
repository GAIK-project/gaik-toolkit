/**
 * PageTransition – a short entrance for a page's content, in CSS only.
 *
 * The animation starts with the first paint of the server HTML and never
 * depends on JavaScript. An earlier version switched to a Framer Motion
 * `initial={{ opacity: 0 }}` after hydration: the page was readable, went
 * blank and faded back in, and stayed dim wherever animation frames do not
 * advance (a background tab, an embedded preview).
 */

import { type CSSProperties, type ReactNode } from "react";
import { cn } from "@/lib/utils";

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
  return (
    <div
      className={cn(
        "animate-in fade-in slide-in-from-bottom-3 duration-300 ease-out motion-reduce:animate-none",
        className,
      )}
      style={style}
    >
      {children}
    </div>
  );
}
