"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function AccessPolling() {
  const router = useRouter();

  useEffect(() => {
    const interval = setInterval(() => {
      try {
        router.refresh();
      } catch (error) {
        console.error("Access polling failed:", error);
      }
    }, 5_000);

    return () => clearInterval(interval);
  }, [router]);

  return null;
}
