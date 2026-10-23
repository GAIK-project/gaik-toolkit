import "server-only";

import { createAzure } from "@ai-sdk/azure";
import {
  defaultSettingsMiddleware,
  type InferAgentUIMessage,
  isStepCount,
  ToolLoopAgent,
  tool,
  wrapLanguageModel,
} from "ai";
import { z } from "zod";
import {
  ARTICLES,
  AUDIENCES,
  ORGANISATION,
  SERVICE_CATEGORIES,
  SERVICES,
  TEAMS,
} from "./knowledge";
import { searchArticles, searchServices, toServiceCard } from "./search";

// The Next.js server calls Azure OpenAI directly, on the same resource as the
// demo API. Chat Completions on that resource is served at deployment-scoped
// paths with a dated api-version.
function azureBaseUrl(): string | undefined {
  const endpoint = process.env.AZURE_ENDPOINT?.trim();
  if (!endpoint) return undefined;
  const url = new URL(endpoint);
  url.pathname = `${url.pathname.replace(/\/+$/, "").replace(/\/openai$/, "")}/openai`;
  return url.toString().replace(/\/+$/, "");
}

export function helpdeskConfigured(): boolean {
  return Boolean(process.env.AZURE_ENDPOINT && process.env.AZURE_API_KEY);
}

const deployment = process.env.HELPDESK_CHAT_DEPLOYMENT ?? "gpt-6-sol";

function chatModel() {
  const azure = createAzure({
    apiKey: process.env.AZURE_API_KEY,
    baseURL: azureBaseUrl(),
    apiVersion: process.env.HELPDESK_AZURE_API_VERSION ?? "2025-04-01-preview",
    useDeploymentBasedUrls: true,
  });
  // GPT-6 Sol answers fastest with reasoning off, and supports it with tools.
  return wrapLanguageModel({
    model: azure.chat(deployment),
    middleware: defaultSettingsMiddleware({
      settings: { providerOptions: { openai: { reasoningEffort: "none" } } },
    }),
  });
}

const tools = {
  searchServices: tool({
    description:
      "List the hub's services. Filter by category and audience when the question names them; the optional query only orders the results. Returns every matching service, so an empty list means the hub has no such service.",
    inputSchema: z.object({
      category: z.enum(SERVICE_CATEGORIES).optional(),
      audience: z.enum(AUDIENCES).optional(),
      query: z
        .string()
        .max(200)
        .optional()
        .describe("A few English keywords from the question"),
    }),
    execute: async (filters) => ({
      services: searchServices(filters).map(toServiceCard),
    }),
  }),
  searchKnowledge: tool({
    description:
      "Search the hub's FAQ articles: who we are, eligibility, pricing rules, data protection, opening hours, events, languages, what happens after a pilot.",
    inputSchema: z.object({
      query: z.string().max(200).describe("A few English keywords"),
    }),
    execute: async ({ query }) => ({
      articles: searchArticles(query).map(({ id, title, body }) => ({
        id,
        title,
        body,
      })),
    }),
  }),
  requestHumanHandoff: tool({
    description:
      "Open a contact form addressed to the right team, prefilled with a summary of the conversation. The user is asked to approve first. Use it when the user asks for a person, wants to book a service, or the knowledge does not answer the question.",
    inputSchema: z.object({
      team: z.enum(Object.keys(TEAMS) as [keyof typeof TEAMS]),
      topic: z
        .string()
        .max(120)
        .describe("A short phrase in the user's language, shown to the user"),
      summary: z
        .string()
        .max(600)
        .describe(
          "The user's message to the team, written in the first person as the user (\"We are a 12-person machine shop and would like ...\"), in the user's language, two or three sentences. The user edits and sends it",
        ),
    }),
    // Demo: nothing is sent. A real helpdesk would create the ticket here and
    // mail the team; the card in the chat says so.
    execute: async ({ team, topic, summary }) => ({
      ticketId: `DEMO-${Math.floor(1000 + Math.random() * 9000)}`,
      team: TEAMS[team].name,
      responseTime: TEAMS[team].responseTime,
      topic,
      summary,
    }),
  }),
};

const INSTRUCTIONS = `You are the helpdesk assistant of ${ORGANISATION}, a publicly funded regional centre that helps small companies, start-ups and public organisations start using AI.

## Grounding — absolute
- Name a service, price, duration or rule only if it appeared in a tool result in this conversation. Call a tool first, even when you think you know.
- The knowledge is in English: write tool queries in English, whatever language the user writes in.
- If the tools return nothing relevant, say so plainly and offer to pass the question to a person. Never fill the gap from general knowledge.
- General advice that names nothing of ${ORGANISATION} ("start with one narrow problem") needs no tool.

## Tools
- searchServices: services, prices, durations. Use category/audience filters when the question implies them (e.g. "training for our staff" → category "training"). The list is complete: if a service is not in it, the hub does not offer it.
- searchKnowledge: everything else about the hub (eligibility, pricing rules, data protection, hours, events, languages, next steps).
- requestHumanHandoff: when the user wants a person, wants to book or apply, or you cannot answer. Choose the team that owns the topic. The user is asked to approve; if they decline, acknowledge it and do not ask again. After approval, tell the user in one sentence to fill in the contact form, which appears ABOVE your reply (never say "below"). Do not list the form fields or claim anything was sent yet.

## Style
- Answer in the user's language (Finnish or English).
- Plain words for non-experts; short paragraphs; a list only for 3+ items.
- Mention at most three services per answer, the best fit first, each with its price.
- Stay on ${ORGANISATION} and practical AI adoption. Politely decline unrelated requests and say what you can help with.
- You are an AI assistant; say so if asked.

Catalogue at a glance (for routing only, not for quoting): ${SERVICES.length} services in categories ${SERVICE_CATEGORIES.join(", ")}; ${ARTICLES.length} FAQ articles.`;

export function createHelpdeskAgent() {
  return new ToolLoopAgent({
    model: chatModel(),
    instructions: INSTRUCTIONS,
    tools,
    toolApproval: { requestHumanHandoff: "user-approval" },
    stopWhen: isStepCount(6),
    maxOutputTokens: 1200,
  });
}

export type HelpdeskUIMessage = InferAgentUIMessage<
  ReturnType<typeof createHelpdeskAgent>
>;
