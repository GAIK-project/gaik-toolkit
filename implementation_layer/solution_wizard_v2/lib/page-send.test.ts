import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CHAT_REPLYING_EVENT,
  CHAT_SEND_DELIVERED_EVENT,
  CHAT_SEND_EVENT,
  CHAT_SEND_FAILED_EVENT,
} from "@/lib/chat-events";
import { SETTLE_MS, followPageSends, type PageSendState } from "@/lib/page-send";

/** A page: the events the chat and a sending field exchange, and what the field was told. */
function page() {
  const events = new EventTarget();
  const states: PageSendState[] = [];
  const sent: string[] = [];
  events.addEventListener(CHAT_SEND_EVENT, (e) => sent.push((e as CustomEvent<string>).detail));
  const sends = followPageSends(events, { state: (s) => states.push(s), replying: () => {} });
  const chat = {
    delivered: (text: string) => events.dispatchEvent(new CustomEvent(CHAT_SEND_DELIVERED_EVENT, { detail: text })),
    failed: (text: string) => events.dispatchEvent(new CustomEvent(CHAT_SEND_FAILED_EVENT, { detail: text })),
    replying: (now: boolean) => events.dispatchEvent(new CustomEvent(CHAT_REPLYING_EVENT, { detail: now })),
  };
  /** The wizard takes the message and finishes its reply. */
  const answer = (text: string) => {
    chat.delivered(text);
    chat.replying(true);
    chat.replying(false);
  };
  return { sends, states, sent, chat, answer, state: () => states.at(-1) ?? "idle" };
}

describe("a message a field on the page sends through the chat", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("is sent by its trimmed text and is on its way until a moment after the reply has ended", () => {
    const p = page();
    p.sends.send("  Lisää tarkastusvaihe.  ");
    expect(p.sent).toEqual(["Lisää tarkastusvaihe."]);
    expect(p.state()).toBe("sent");

    p.answer("Lisää tarkastusvaihe.");
    // The page's new data is still arriving.
    vi.advanceTimersByTime(SETTLE_MS - 1);
    expect(p.state()).toBe("sent");
    vi.advanceTimersByTime(1);
    expect(p.state()).toBe("idle");
  });

  it("sent within that moment is not called done by the message before it", () => {
    const p = page();
    p.sends.send("Ensimmäinen");
    p.answer("Ensimmäinen");
    vi.advanceTimersByTime(SETTLE_MS / 2);

    // The next one goes out before the first has settled.
    p.sends.send("Toinen");
    expect(p.state()).toBe("sent");
    // The first message's wait would have ended here: the second is still on its way.
    vi.advanceTimersByTime(SETTLE_MS);
    expect(p.state()).toBe("sent");

    p.answer("Toinen");
    vi.advanceTimersByTime(SETTLE_MS);
    expect(p.state()).toBe("idle");
    expect(p.states).toEqual(["sent", "sent", "idle"]);
  });

  it("that never reached the wizard is failed, and only its own failure counts", () => {
    const p = page();
    p.sends.send("Lisää tarkastusvaihe.");
    p.chat.failed("Jokin muu viesti");
    expect(p.state()).toBe("sent");
    p.chat.failed("Lisää tarkastusvaihe.");
    expect(p.state()).toBe("failed");

    p.sends.reset();
    expect(p.state()).toBe("idle");
  });

  it("given up on within that moment stays idle", () => {
    const p = page();
    p.sends.send("Ensimmäinen");
    p.answer("Ensimmäinen");
    p.sends.reset();
    vi.advanceTimersByTime(SETTLE_MS);
    expect(p.states).toEqual(["sent", "idle"]);
  });

  it("is not followed by a reply to another turn, and says nothing once stopped", () => {
    const p = page();
    p.sends.send("Lisää tarkastusvaihe.");
    // The wizard ends a reply to something else: this message was not taken yet.
    p.chat.replying(true);
    p.chat.replying(false);
    vi.advanceTimersByTime(SETTLE_MS);
    expect(p.state()).toBe("sent");

    p.answer("Lisää tarkastusvaihe.");
    p.sends.stop();
    vi.advanceTimersByTime(SETTLE_MS);
    expect(p.state()).toBe("sent");
    expect(p.sends.send("  ")).toBeUndefined();
  });
});
