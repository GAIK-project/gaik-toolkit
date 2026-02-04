import toast from "react-hot-toast";

export class RateLimitError extends Error {
  readonly resetTime: number;

  constructor(resetTime: number) {
    super("Rate limit exceeded");
    this.name = "RateLimitError";
    this.resetTime = resetTime;
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
    const resetHeader = response.headers.get("X-RateLimit-Reset");
    const resetTime = resetHeader ? parseInt(resetHeader, 10) : 0;
    const secondsLeft = Math.max(1, Math.ceil((resetTime - Date.now()) / 1000));

    toast.error(`Too many requests! Please wait ${secondsLeft} seconds.`, {
      duration: 5000,
      icon: "hourglass",
    });

    throw new RateLimitError(resetTime);
  }

  return response;
}
