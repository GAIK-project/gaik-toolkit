// SSE streaming endpoint for the mock chat reply.
// Streams the reply as text/event-stream, token by token. Mock: the reply is
// phase-aware and in the user's language (i18n cookie).

import { NextRequest } from "next/server";
import { getI18n } from "@/lib/i18n";
import { getSession, postMessage } from "@/lib/mock-sessions";

export const dynamic = "force-dynamic";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await req.json().catch(() => ({}));
  const userMessage = ((body?.message as string) ?? "").trim();

  if (!userMessage) {
    return new Response("Empty message", { status: 400 });
  }

  const session = getSession(id);
  if (!session) {
    return new Response("Session not found", { status: 404 });
  }

  // Build the mock reply in the user's language, referencing the current phase.
  const { t } = await getI18n();
  const phase = t.phases[session.step - 1];
  const fullReply = `${t.chatMockReplyPre}"${phase}"${t.chatMockReplyPost}`;

  // Split into tokens (word + trailing space) for streaming.
  const tokens = fullReply.match(/\S+\s*/g) ?? [fullReply];

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const token of tokens) {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ delta: token })}\n\n`),
        );
        await sleep(45);
      }
      // Persist the conversation to the mock store (read by the server render).
      postMessage(id, userMessage, fullReply);
      controller.enqueue(encoder.encode(`data: ${JSON.stringify({ done: true })}\n\n`));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
