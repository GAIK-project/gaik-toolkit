// A scripted conversation that plays through the real chat UI, step by step,
// for presenting the demo. It calls no model and no API, so it runs the same
// every time and for visitors who are not signed in. Tool outputs come from the
// same catalogue and search the live tools use, over the knowledge of the
// helpdesk being played; the conversation itself is that example's `demo`.

import type { HelpdeskUIMessage } from "@/lib/helpdesk-chatbot/agent";
import type { HelpdeskExample } from "@/lib/helpdesk-chatbot/examples";
import {
  searchArticles,
  searchServices,
  toServiceCard,
} from "@/lib/helpdesk-chatbot/search";

type Msg = HelpdeskUIMessage;
type AnyPart = Msg["parts"][number];

export interface PlaybackIO {
  setMessages: (messages: Msg[]) => void;
  setInput: (text: string) => void;
  setCaption: (caption: { step: number; text: string } | null) => void;
  /** Index of the assistant message that is "generating", or null. */
  setStreamingId: (id: string | null) => void;
  /** Ask the contact form to fill itself in and send. */
  setDemoFill: (fill: { name: string; email: string } | null) => void;
  signal: AbortSignal;
}

export const DEMO_STEPS = 6;

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason);
    const t = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(t);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

export async function playDemo(
  io: PlaybackIO,
  example: HelpdeskExample,
): Promise<void> {
  const { knowledge, demo: script } = example;
  if (!script) return; // a helpdesk without a scripted conversation
  const { signal } = io;
  const wait = (ms: number) => sleep(ms, signal);
  let messages: Msg[] = [];
  const commit = () => io.setMessages([...messages]);
  const setParts = (id: string, parts: AnyPart[]) => {
    messages = messages.map((m) => (m.id === id ? { ...m, parts } : m));
    commit();
  };

  async function type(text: string) {
    for (let i = 1; i <= text.length; i++) {
      io.setInput(text.slice(0, i));
      await wait(28);
    }
    await wait(450);
    io.setInput("");
    messages = [
      ...messages,
      {
        id: `demo-user-${messages.length}`,
        role: "user",
        parts: [{ type: "text", text }],
      },
    ];
    commit();
  }

  async function stream(id: string, before: AnyPart[], text: string) {
    const words = text.split(/(\s+)/);
    for (let i = 1; i <= words.length; i += 2) {
      setParts(id, [
        ...before,
        { type: "text", text: words.slice(0, i).join(""), state: "streaming" },
      ]);
      await wait(40);
    }
    setParts(id, [...before, { type: "text", text, state: "done" }]);
  }

  // 1 — the visitor asks
  io.setCaption({
    step: 1,
    text: "A visitor asks in their own words, in English or Finnish",
  });
  await wait(900);
  await type(script.question1);

  // 2 — the model picks tools
  const a1 = "demo-assistant-1";
  messages = [...messages, { id: a1, role: "assistant", parts: [] }];
  commit();
  io.setStreamingId(a1);
  io.setCaption({
    step: 2,
    text: "The AI model decides what to look up: it searches the service catalogue…",
  });
  await wait(900);
  const servicesInput = script.servicesInput;
  const servicesCall = {
    type: "tool-searchServices",
    toolCallId: "demo-call-1",
    input: servicesInput,
  } as const;
  setParts(a1, [{ ...servicesCall, state: "input-available" }]);
  await wait(1400);
  const servicesDone: AnyPart = {
    ...servicesCall,
    state: "output-available",
    output: {
      services: searchServices(knowledge, servicesInput).map((s) =>
        toServiceCard(knowledge, s),
      ),
    },
  };
  setParts(a1, [servicesDone]);

  io.setCaption({
    step: 2,
    text: `…and the FAQ, for ${script.faqPurpose}`,
  });
  await wait(700);
  const faqCall = {
    type: "tool-searchKnowledge",
    toolCallId: "demo-call-2",
    input: { query: script.faqQuery },
  } as const;
  setParts(a1, [servicesDone, { ...faqCall, state: "input-available" }]);
  await wait(1300);
  const faqDone: AnyPart = {
    ...faqCall,
    state: "output-available",
    output: {
      articles: searchArticles(knowledge, faqCall.input.query).map(
        ({ id, title, body }) => ({ id, title, body }),
      ),
    },
  };

  // 3 — grounded answer
  io.setCaption({
    step: 3,
    text: "It answers only from what the tools returned, and names its prices",
  });
  await stream(a1, [servicesDone, faqDone], script.answer1);
  io.setStreamingId(null);

  // 4 — provenance
  io.setCaption({
    step: 4,
    text: "Under the answer: which knowledge it used, and the sources to open",
  });
  await wait(3200);

  // 5 — hand-off with approval
  io.setCaption({
    step: 5,
    text: "When a person is needed, the bot asks before it does anything",
  });
  await type(script.question2);
  const a2 = "demo-assistant-2";
  messages = [...messages, { id: a2, role: "assistant", parts: [] }];
  commit();
  io.setStreamingId(a2);
  await wait(900);
  const handoffInput = script.handoff;
  const handoffTeam = knowledge.teams[handoffInput.team];
  const handoffCall = {
    type: "tool-requestHumanHandoff",
    toolCallId: "demo-call-3",
    input: handoffInput,
  } as const;
  setParts(a2, [{ ...handoffCall, state: "input-available" }]);
  await wait(900);
  setParts(a2, [
    {
      ...handoffCall,
      state: "approval-requested",
      approval: { id: "demo-approval" },
    },
  ]);
  await wait(2600);
  setParts(a2, [
    {
      ...handoffCall,
      state: "approval-responded",
      approval: { id: "demo-approval", approved: true },
    },
  ]);
  await wait(900);
  const handoffDone: AnyPart = {
    ...handoffCall,
    state: "output-available",
    approval: { id: "demo-approval", approved: true },
    output: {
      ticketId: "DEMO-1024",
      team: handoffTeam.name,
      responseTime: handoffTeam.responseTime,
      topic: handoffInput.topic,
      summary: handoffInput.summary,
    },
  };
  setParts(a2, [handoffDone]);
  await wait(500);
  await stream(a2, [handoffDone], script.answer2);
  io.setStreamingId(null);

  // 6 — contact form, prefilled from the conversation
  io.setCaption({
    step: 6,
    text: "The contact form arrives prefilled from the conversation; the visitor sends it",
  });
  await wait(1200);
  io.setDemoFill(script.contact);
  await wait(5200);
  io.setCaption({
    step: DEMO_STEPS,
    text: "Done. Ask your own question to try it live.",
  });
}
