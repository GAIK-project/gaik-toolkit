import { createAgentUIStreamResponse, smoothStream } from "ai";
import { NextRequest, NextResponse } from "next/server";
import {
  createHelpdeskAgent,
  helpdeskConfigured,
} from "@/lib/helpdesk-chatbot/agent";
import { ratelimit } from "@/lib/rate-limit";
import { getAccessState } from "@/lib/supabase/proxy";
import { accessRefusal } from "@/lib/api-access";
import { takeTrialRun } from "@/lib/trial";

/**
 * Helpdesk Chatbot demo. The only demo whose model runs in Next.js rather than
 * the FastAPI backend, so proxy.ts leaves it to this handler, which applies the
 * same rules: a signed-in, approved user (or a pending one within the trial
 * allowance) and the per-IP rate limit.
 */
export const maxDuration = 60;

const MAX_MESSAGES = 40;
const MAX_BODY_BYTES = 200_000;

// The router appends the real client address last; earlier entries are
// whatever the client sent.
function clientIp(request: NextRequest): string {
  const forwarded = request.headers.get("x-forwarded-for");
  return (
    forwarded?.split(",").at(-1)?.trim() ||
    request.headers.get("x-real-ip") ||
    "anonymous"
  );
}

export async function POST(request: NextRequest) {
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
  if (!helpdeskConfigured()) {
    return NextResponse.json(
      { error: "The chatbot is not configured." },
      { status: 503 },
    );
  }

  if (ratelimit) {
    try {
      const { success } = await ratelimit.limit(
        `helpdesk:${clientIp(request)}`,
      );
      if (!success) {
        return NextResponse.json(
          { error: "Too many requests. Try again in a minute." },
          { status: 429 },
        );
      }
    } catch (error) {
      console.warn("[helpdesk-chat] rate limit unavailable:", error);
    }
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

  return createAgentUIStreamResponse({
    // Whatever this returns reaches the browser: log the provider error here
    // and send a fixed sentence, never error.message.
    onError: (error) => {
      console.error("[helpdesk-chat]", error);
      return "The assistant could not answer. Please try again.";
    },
    agent: createHelpdeskAgent(),
    uiMessages: messages,
    abortSignal: request.signal,
    // Rahti does not enforce maxDuration, so bound the call here.
    timeout: { totalMs: maxDuration * 1000, toolMs: 10_000 },
    experimental_transform: smoothStream({ chunking: "word", delayInMs: 10 }),
  });
}
