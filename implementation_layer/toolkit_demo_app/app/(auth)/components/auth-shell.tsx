"use client";

import { StarsBackground } from "@/components/stars";
import { motion } from "motion/react";
import Image from "next/image";
import type { ReactNode } from "react";

const fadeUp = {
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
};

type AuthBackdropProps = {
  children: ReactNode;
};

export function AuthBackdrop({ children }: AuthBackdropProps) {
  return (
    <StarsBackground
      className="min-h-screen text-white"
      factor={0.03}
      speed={80}
      starColor="rgba(255,255,255,0.8)"
    >
      {/* Gradient overlays for depth */}
      <div
        className="pointer-events-none absolute inset-0 z-1 bg-[radial-gradient(circle_at_top,rgba(45,212,191,0.15),transparent_55%)]"
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute top-24 -left-32 z-1 h-64 w-64 rounded-full bg-[radial-gradient(circle,rgba(59,130,246,0.18),transparent_60%)] blur-3xl"
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute -right-24 -bottom-24 z-1 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(20,184,166,0.22),transparent_65%)] blur-3xl"
        aria-hidden="true"
      />
      <div className="relative z-10 min-h-screen">{children}</div>
    </StarsBackground>
  );
}

type AuthShellProps = {
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
  variant?: "dark" | "light";
};

export function AuthShell({
  title,
  description,
  children,
  footer,
  variant = "dark",
}: AuthShellProps) {
  const isDark = variant === "dark";

  return (
    <div className="pointer-events-none flex min-h-screen items-center justify-center px-6 py-16">
      <motion.div
        initial="initial"
        animate="animate"
        variants={fadeUp}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="pointer-events-auto w-full max-w-sm"
      >
        <div className="flex flex-col items-center text-center">
          <Image
            src={
              isDark
                ? "/logos/SVG/gaik_logo_fullwhite.svg"
                : "/logos/SVG/gaik_logo_fullblack.svg"
            }
            alt="GAIK Toolkit - Generative AI-Enhanced Knowledge Management in Business"
            width={320}
            height={160}
            className="h-20 w-auto sm:h-24"
            priority
          />
          <h1
            className={`mt-6 font-serif text-3xl font-semibold tracking-tight sm:text-4xl ${isDark ? "" : "text-slate-900"}`}
          >
            {title}
          </h1>
          <p
            className={`mt-2 text-sm sm:text-base ${isDark ? "text-white/70" : "text-slate-600"}`}
          >
            {description}
          </p>
        </div>

        <div
          className={`mt-8 rounded-3xl border p-6 text-slate-900 shadow-2xl backdrop-blur sm:p-8 ${isDark ? "border-white/15 bg-white/95" : "border-slate-200 bg-white"}`}
        >
          {children}
        </div>

        {footer && (
          <div
            className={`mt-6 text-center text-sm ${isDark ? "text-white/70" : "text-slate-600"}`}
          >
            {footer}
          </div>
        )}
      </motion.div>
    </div>
  );
}
