"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function AccessPolling() {
  const router = useRouter();

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch("/api/access-status");
        const data = await res.json();
        if (data.status === "approved") {
          clearInterval(interval);
          router.push("/classifier");
        }
      } catch {
        // ignore fetch errors
      }
    }, 10_000);

    return () => clearInterval(interval);
  }, [router]);

  return null;
}
