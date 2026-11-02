// The helpdesks the Helpdesk Chatbot demo can play: each is a fictional
// organisation (its knowledge), the questions offered at the start, and the
// scripted conversation of "Watch a demo conversation". Plain data, so both the
// server (the agent) and the browser (the chat) can import it.

import { HUB_KNOWLEDGE, type Knowledge } from "./knowledge";
import { IT_KNOWLEDGE } from "./knowledge-it";

/** The conversation the scripted demo plays: a question answered from the
 *  catalogue and the FAQ, then a hand-off to a person with approval. The tool
 *  results are produced by the real search over the example's knowledge. */
export interface DemoScript {
  question1: string;
  answer1: string;
  servicesInput: { category?: string; audience?: string; query?: string };
  faqQuery: string;
  /** Caption while the FAQ is searched, after "…and the FAQ, for ". */
  faqPurpose: string;
  question2: string;
  answer2: string;
  handoff: { team: string; topic: string; summary: string };
  contact: { name: string; email: string };
}

export interface HelpdeskExample {
  id: string;
  /** Card title. */
  title: string;
  /** Card description. */
  summary: string;
  /** Small labels on the card. */
  tags: string[];
  knowledge: Knowledge;
  welcomeText: string;
  /** Questions offered at the start. */
  starters: string[];
  /** The scripted conversation. Without one there is no "Watch a demo conversation". */
  demo?: DemoScript;
}

const HUB: HelpdeskExample = {
  id: HUB_KNOWLEDGE.id,
  title: "FAIR Helpdesk Chatbot",
  summary:
    "Provides tailored answers about FAIR services and consultancies. Hands off to the right expert or team.",
  tags: [
    "Services",
    "Consultancies",
    "Prices",
    "Support",
    "Expertise",
    "Finnish and English",
  ],
  knowledge: HUB_KNOWLEDGE,
  welcomeText:
    "Ask about services, prices or how to get started, in English or Finnish. Answers come from the hub's own catalogue, and a person can take over when needed.",
  starters: [
    "We are a 12-person machine shop. Where should we start with AI?",
    "Do you have training for our staff?",
    "Mitä tapahtuu yrityksemme datalle pilotissa?",
    "I'd like to talk to someone about funding.",
  ],
  demo: {
    question1:
      "We are a 12-person machine shop. Where should we start with AI?",
    answer1:
      "A good first step is the free **AI Readiness Check**: in a two-hour session an advisor looks at your daily work and lists a few places where AI could save time, ranked by effort and benefit. You get a one-page summary afterwards.\n\nIf one idea stands out, a **Rapid Proof-of-Concept** (€2,500, 4 weeks) builds a small prototype on your own data to show whether it really works. As a company under 250 employees you can use the hub's funded services.\n\nWould you like me to put you in touch with the advisory team?",
    servicesInput: { audience: "sme", query: "getting started" },
    faqQuery: "who can use services eligibility",
    faqPurpose: "who can use the services",
    question2: "Yes please, I'd like to book the Readiness Check.",
    answer2:
      "Great, please fill in the contact form above and the AI Advisory team will get back to you.",
    handoff: {
      team: "advisory",
      topic: "Booking the AI Readiness Check",
      summary:
        "We are a 12-person machine shop and would like to book the free AI Readiness Check to find out where AI could save us time.",
    },
    contact: { name: "Maija Example", email: "maija@example.com" },
  },
};

const IT: HelpdeskExample = {
  id: IT_KNOWLEDGE.id,
  title: "Internal IT and HR helpdesk",
  summary:
    "A company's helpdesk for its own employees: accounts, devices, software, security and HR questions, with a ticket to the right team.",
  tags: [
    "Requests and policies",
    "Ticket with approval",
    "English and Finnish",
  ],
  knowledge: IT_KNOWLEDGE,
  welcomeText:
    "Ask about accounts, devices, software, security or HR matters, in English or Finnish. Answers come from the helpdesk's own service list and FAQ, and a person can take over when needed.",
  starters: [
    "I start on Monday. What do I need to sort out for my laptop and accounts?",
    "My VPN keeps disconnecting when I work from home.",
    "Miten nollaan salasanani?",
    "Can I get a standing desk reimbursed?",
  ],
  demo: {
    question1:
      "I start on Monday. What do I need to sort out for my laptop and accounts?",
    answer1:
      "Your manager normally orders the **New-hire equipment kit** at least 10 working days before you start, so the laptop, phone, headset and accounts are ready on your first day. On the first day, sign in with your temporary password and set up **multi-factor authentication**; allow about an hour for the account setup. HR has also sent you a first-week plan with a buddy.\n\nIf the kit was ordered late, a standard laptop takes 5 working days. The service desk is open Monday to Friday 7–17.\n\nWould you like me to ask the IT Service Desk to check that your kit has been ordered?",
    servicesInput: { audience: "new-hire", query: "laptop accounts equipment" },
    faqQuery: "first day new hire account",
    faqPurpose: "what happens on the first day",
    question2: "Yes please, I'd like them to check my kit.",
    answer2:
      "Please fill in the contact form above and the IT Service Desk will get back to you.",
    handoff: {
      team: "it-service-desk",
      topic: "Checking my new-hire kit",
      summary:
        "I start on Monday and would like to check that my laptop, phone and accounts have been ordered and will be ready on my first day.",
    },
    contact: { name: "Eero Example", email: "eero@example.com" },
  },
};

export const HELPDESK_EXAMPLES: HelpdeskExample[] = [HUB, IT];

export function getHelpdeskExample(id: unknown): HelpdeskExample | undefined {
  return HELPDESK_EXAMPLES.find((example) => example.id === id);
}
