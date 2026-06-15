import { parseSSEEvents, type SSEEvent } from "@/lib/sse";

export interface ReportUsageInfo {
  sawResult: boolean;
  totalTokens: number;
}

/**
 * Fold result-event token usage out of a batch of parsed SSE events. Pass the
 * previous result to accumulate across streamed chunks.
 */
export function pickUsageFromEvents(
  events: SSEEvent[],
  prev: ReportUsageInfo = { sawResult: false, totalTokens: 0 },
): ReportUsageInfo {
  let { sawResult, totalTokens } = prev;
  for (const ev of events) {
    if (ev.type === "result") {
      sawResult = true;
      const t = (ev.data as { usage?: { total_tokens?: number } }).usage
        ?.total_tokens;
      if (typeof t === "number") totalTokens = t;
    }
  }
  return { sawResult, totalTokens };
}

/**
 * Parse a complete SSE text buffer and report whether a result event was seen
 * and how many tokens it reported.
 */
export function extractReportUsage(sseText: string): ReportUsageInfo {
  const { events } = parseSSEEvents(`${sseText}\n\n`);
  return pickUsageFromEvents(events);
}
