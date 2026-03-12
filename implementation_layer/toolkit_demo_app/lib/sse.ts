/**
 * Server-Sent Events (SSE) parsing utilities
 */

export interface SSEStepDetails {
  type: "schema" | "code" | "extraction";
  title: string;
  content: string;
}

export interface SSEStep {
  step: number;
  name: string;
  status: "pending" | "in_progress" | "completed" | "error";
  message?: string;
  details?: SSEStepDetails;
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
export function parseSSEEvents(text: string): { events: SSEEvent[]; remaining: string } {
  const events: SSEEvent[] = [];

  // Only parse complete events (terminated by \n\n)
  const lastBoundary = text.lastIndexOf("\n\n");
  if (lastBoundary === -1) {
    return { events: [], remaining: text };
  }

  const completePart = text.slice(0, lastBoundary);
  const remaining = text.slice(lastBoundary + 2);

  const lines = completePart.split("\n");
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

  // Handle last event in complete part (may not end with empty line)
  if (currentEvent.type && currentEvent.data) {
    try {
      events.push({
        type: currentEvent.type,
        data: JSON.parse(currentEvent.data),
      });
    } catch {
      // Skip invalid JSON
    }
  }

  return { events, remaining };
}

/**
 * Callback handlers for SSE stream processing
 */
export interface SSEStreamHandlers<TResult> {
  onSteps?: (steps: SSEStep[]) => void;
  onStepUpdate?: (step: SSEStep) => void;
  onResult?: (result: TResult) => void;
  onError?: (message: string) => void;
  /** Handle custom event types not covered by standard handlers */
  onCustomEvent?: (event: SSEEvent) => void;
}

/**
 * Process an SSE response stream with standardized event handling
 *
 * Handles common event types: steps, step_update, result, error
 * Custom events can be handled via onCustomEvent callback
 */
export async function processSSEStream<TResult>(
  response: Response,
  handlers: SSEStreamHandlers<TResult>,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const { events, remaining } = parseSSEEvents(buffer);
    buffer = remaining;

    for (const event of events) {
      switch (event.type) {
        case "steps":
          handlers.onSteps?.(event.data.steps as unknown as SSEStep[]);
          break;
        case "step_update":
          handlers.onStepUpdate?.(event.data as unknown as SSEStep);
          break;
        case "result":
          handlers.onResult?.(event.data as unknown as TResult);
          break;
        case "error":
          handlers.onError?.((event.data.message as string) || "Processing failed");
          break;
        default:
          handlers.onCustomEvent?.(event);
      }
    }
  }
}
