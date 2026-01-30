/**
 * Server-Sent Events (SSE) parsing utilities
 */

export interface SSEStep {
  step: number;
  name: string;
  status: "pending" | "in_progress" | "completed" | "error";
  message?: string;
}

export interface SSEEvent {
  type: string;
  data: Record<string, unknown>;
}

/**
 * Parse SSE events from a text buffer
 *
 * SSE format:
 * ```
 * event: eventType
 * data: {"json":"data"}
 *
 * ```
 */
export function parseSSEEvents(text: string): SSEEvent[] {
  const events: SSEEvent[] = [];
  const lines = text.split("\n");
  let currentEvent: { type?: string; data?: string } = {};

  for (const line of lines) {
    if (line.startsWith("event: ")) {
      currentEvent.type = line.slice(7);
    } else if (line.startsWith("data: ")) {
      currentEvent.data = line.slice(6);
    } else if (line === "" && currentEvent.type && currentEvent.data) {
      try {
        events.push({
          type: currentEvent.type,
          data: JSON.parse(currentEvent.data),
        });
      } catch {
        // Skip invalid JSON
      }
      currentEvent = {};
    }
  }
  return events;
}
