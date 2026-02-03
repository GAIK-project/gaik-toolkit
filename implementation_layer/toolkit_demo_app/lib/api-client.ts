import toast from "react-hot-toast";

export class RateLimitError extends Error {
  constructor(public resetTime: number) {
    super("Rate limit exceeded");
    this.name = "RateLimitError";
  }
}

/**
 * Fetch wrapper that handles rate limit errors with toast notifications
 */
export async function apiFetch(
  url: string,
  options?: RequestInit,
): Promise<Response> {
  const response = await fetch(url, options);

  if (response.status === 429) {
    const resetTime = parseInt(
      response.headers.get("X-RateLimit-Reset") || "0",
    );
    const secondsLeft = Math.max(1, Math.ceil((resetTime - Date.now()) / 1000));

    toast.error(`Liian monta pyyntöä! Odota ${secondsLeft} sekuntia.`, {
      duration: 5000,
      icon: "⏳",
    });

    throw new RateLimitError(resetTime);
  }

  return response;
}
