"use client";

import { cn } from "@/lib/utils";
import { type CSSProperties, type ElementType, memo, useMemo } from "react";

export interface TextShimmerProps {
  children: string;
  as?: ElementType;
  className?: string;
  duration?: number;
  spread?: number;
  /** CSS color value or variable for the base text color. Defaults to muted-foreground */
  color?: string;
  /** CSS color value or variable for the shimmer highlight. Defaults to background */
  shimmerColor?: string;
}

const ShimmerComponent = ({
  children,
  as: Component = "p",
  className,
  duration = 2,
  spread = 2,
  color = "var(--color-muted-foreground)",
  shimmerColor = "var(--color-background)",
}: TextShimmerProps) => {
  const dynamicSpread = useMemo(
    () => (children?.length ?? 0) * spread,
    [children, spread],
  );

  return (
    <Component
      className={cn(
        "relative inline-block bg-[length:250%_100%,auto] bg-clip-text text-transparent",
        "[background-repeat:no-repeat,padding-box] [--bg:linear-gradient(90deg,#0000_calc(50%-var(--spread)),var(--shimmer-color),#0000_calc(50%+var(--spread)))]",
        className,
      )}
      style={
        {
          "--spread": `${dynamicSpread}px`,
          "--shimmer-color": shimmerColor,
          backgroundImage: `var(--bg), linear-gradient(${color}, ${color})`,
          animation: `text-shimmer ${duration}s linear infinite`,
        } as CSSProperties
      }
    >
      {children}
    </Component>
  );
};

export const Shimmer = memo(ShimmerComponent);
