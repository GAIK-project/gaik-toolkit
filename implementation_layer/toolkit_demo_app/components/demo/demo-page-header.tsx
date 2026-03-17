"use client";

import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface DemoPageHeaderProps {
  icon: LucideIcon;
  iconClassName?: string;
  title: string;
  description?: string;
  children?: ReactNode;
  className?: string;
}

export function DemoPageHeader({
  icon: Icon,
  iconClassName,
  title,
  description,
  children,
  className = "mb-6",
}: DemoPageHeaderProps) {
  const router = useRouter();

  return (
    <header className={className}>
      <Button
        variant="ghost"
        className="mb-2 -ml-3 gap-2"
        onClick={() => router.push("/")}
      >
        <ArrowLeft className="h-4 w-4" />
        Back
      </Button>
      <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
        <Icon className={iconClassName ?? "h-8 w-8"} />
        {title}
      </h1>
      {description && (
        <p className="text-muted-foreground mt-2">{description}</p>
      )}
      {children}
    </header>
  );
}
