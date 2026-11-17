import { createAgentUIStreamResponse } from "ai";
import { NextRequest, NextResponse } from "next/server";
import {
  createScreeningAgent,
  screeningConfigured,
} from "@/lib/ai-act-screening/agent";
import { userTextsOf } from "@/lib/ai-act-screening/verify";
import { clientIp } from "@/lib/client-ip";
import { checkRateLimit, ratelimit } from "@/lib/rate-limit";
import { getAccessState } from "@/lib/supabase/proxy";
import { accessRefusal } from "@/lib/api-access";
import { takeTrialRun } from "@/lib/trial";

/**
 * EU AI Act screening demo. Its model runs in Next.js (like the helpdesk chat),
 * so proxy.ts leaves it to this handler, which applies the same rules: a
 * signed-in, approved user (or a pending one within the trial allowance) and
 * the per-IP rate limit. The screening it produces is checked by the skill's
 * own checker in the FastAPI backend (/ai-act-screening/check).
 */
export const maxDuration = 120;

const MAX_MESSAGES = 40;
// One user message is at most MAX_USER_CHARS; a whole conversation stays small.
const MAX_USER_CHARS = 8000;
const MAX_BODY_BYTES = 300_000;

export async function POST(request: NextRequest) {
  const limited = await checkRateLimit(
    ratelimit,
    `ai-act-screening:${clientIp(request.headers)}`,
    "Too many requests. Try again in a minute.",
    "[ai-act-screening]",
  );
  if (limited) {
    return NextResponse.json(
      { error: limited.error },
      { status: limited.status, headers: limited.headers },
    );
  }

  const refusal = await accessRefusal(
    await getAccessState(request),
    takeTrialRun,
  );
  if (refusal) {
    return NextResponse.json(
      { error: refusal.error },
      { status: refusal.status },
    );
  }
  if (!screeningConfigured()) {
    return NextResponse.json(
      { error: "The screening is not configured." },
      { status: 503 },
    );
  }

  if (Number(request.headers.get("content-length") ?? 0) > MAX_BODY_BYTES) {
    return NextResponse.json(
      { error: "The conversation is too long. Start a new one." },
      { status: 413 },
    );
  }

  let messages: unknown;
  try {
    ({ messages } = await request.json());
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }
  if (!Array.isArray(messages) || messages.length === 0) {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }
  if (messages.length > MAX_MESSAGES) {
    return NextResponse.json(
      { error: "The conversation is too long. Start a new one." },
      { status: 413 },
    );
  }
  const userTexts = userTextsOf(messages);
  if (userTexts.some((t) => t.length > MAX_USER_CHARS)) {
    return NextResponse.json(
      { error: "A message is too long. Shorten it and try again." },
      { status: 413 },
    );
  }

  return createAgentUIStreamResponse({
    // Whatever this returns reaches the browser: log the provider error here
    // and send a fixed sentence, never error.message.
    onError: (error) => {
      console.error("[ai-act-screening]", error);
      return "The screening could not continue. Please try again.";
    },
    agent: createScreeningAgent(userTexts),
    uiMessages: messages,
    abortSignal: request.signal,
    // Rahti does not enforce maxDuration, so bound the call here.
    timeout: { totalMs: maxDuration * 1000, toolMs: 30_000 },
  });
}
