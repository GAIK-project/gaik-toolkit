import Image from "next/image";
import { cn } from "@/lib/utils";

interface GitHubIconProps {
  className?: string;
}

export function GitHubIcon({ className }: GitHubIconProps) {
  return (
    <Image
      src="/logos/github-mark-white.svg"
      alt=""
      width={20}
      height={20}
      className={cn("invert dark:invert-0", className)}
    />
  );
}
