/**
 * The RAG Builder example: two documents of one fictional company. The files
 * live in public/rag-example/ and are indexed by the backend's
 * `/api/rag/load-example` (api/routers/rag.py, EXAMPLE_DOCUMENTS); keep the
 * file names in step with it.
 */

export interface RagExampleDocument {
  /** The file name, as the backend lists it after indexing. */
  filename: string;
  title: string;
  url: string;
  pages: number;
  /** What kind of document it is. */
  kind: string;
  description: string;
  /** What it holds, as short phrases. */
  topics: string[];
}

export const RAG_EXAMPLE_PREFIX = "example-demo";

/** True for the collection the backend builds for the example. */
export function isExampleCollection(collectionId: string | null): boolean {
  return Boolean(collectionId?.startsWith(RAG_EXAMPLE_PREFIX));
}

export const RAG_EXAMPLE_DOCUMENTS: RagExampleDocument[] = [
  {
    filename: "halden_employee_handbook.pdf",
    title: "Employee Handbook",
    url: "/rag-example/halden_employee_handbook.pdf",
    pages: 25,
    kind: "Policy handbook",
    description:
      "The rules of employment: numbered sections and clauses, tables, exceptions and appendices.",
    topics: [
      "Working time and overtime",
      "Pay, bonus and benefits",
      "Leave and sick pay",
      "Remote work",
      "Travel and expenses",
      "IT, security and AI tools",
      "Conduct and leaving",
    ],
  },
  {
    filename: "halden_workplace_onboarding_guide.pdf",
    title: "Workplace and Onboarding Guide",
    url: "/rag-example/halden_workplace_onboarding_guide.pdf",
    pages: 13,
    kind: "Practical guide",
    description:
      "How things work day to day: offices, starting at the company, tools, IT help and the 2026 calendar.",
    topics: [
      "Offices and facilities",
      "First day and first week",
      "Tools and IT service levels",
      "2026 paydays and public holidays",
      "Safety and emergencies",
      "Contacts",
    ],
  },
];

export const RAG_EXAMPLE_ORGANISATION = "Halden Technologies";

/** Four questions to start with: one that needs both documents, three that need passages of one. */
export const RAG_EXAMPLE_STARTERS: string[] = [
  "When is the salary paid in June 2026, and is anything extra paid with it?",
  "I start on Monday 2 March 2026. What happens on my first day and in my first week?",
  "How many days of annual leave does someone with 7 years of service get?",
  "I'm on an 11-hour day trip to Germany and lunch is provided. What daily allowance do I get?",
];

export interface RagQuestionType {
  title: string;
  text: string;
  example: string;
}

export const RAG_EXAMPLE_QUESTION_TYPES: RagQuestionType[] = [
  {
    title: "Look up a fact",
    text: "A number, a rule or a name that sits in one place.",
    example: "What is the hotel limit per night in Tallinn?",
  },
  {
    title: "Combine both documents",
    text: "The rule is in the handbook and the date or the how-to is in the guide.",
    example:
      "Which public holidays do I get in Tallinn in 2026, and how many leave days do I earn in a year?",
  },
  {
    title: "Work something out",
    text: "Apply a rule or a table to your own situation.",
    example: "I worked 3 hours of overtime in one day. How is it paid?",
  },
  {
    title: "Check an exception or a limit",
    text: "What is allowed, until when, and what needs approval.",
    example: "Can I work from Spain for a month?",
  },
  {
    title: "Ask about something that is not there",
    text: "A good answer says the documents do not cover it.",
    example: "Does Halden offer pet insurance?",
  },
];
