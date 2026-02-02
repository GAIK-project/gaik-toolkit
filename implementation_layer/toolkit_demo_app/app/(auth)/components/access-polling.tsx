"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function AccessPolling() {
  const router = useRouter();

  useEffect(() => {
    const interval = setInterval(() => {
      router.refresh();
    }, 5_000);

    return () => clearInterval(interval);
  }, [router]);

  return null;
}
