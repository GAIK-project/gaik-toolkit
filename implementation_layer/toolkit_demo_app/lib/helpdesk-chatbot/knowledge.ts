// The Helpdesk Chatbot demo's knowledge: a fictional regional AI hub with a
// service catalogue, FAQ articles and support teams. All of it is synthetic.
//
// A real deployment keeps the same three shapes in a database and searches them
// with SQL (full-text search, or pgvector for semantic search); the demo keeps
// them in memory so it runs without one.

export const ORGANISATION = "Lakeside AI Hub";

export const SERVICE_CATEGORIES = [
  "advisory",
  "proof-of-concept",
  "training",
  "funding",
  "technology-testing",
] as const;
export type ServiceCategory = (typeof SERVICE_CATEGORIES)[number];

export const AUDIENCES = ["sme", "startup", "public-sector"] as const;
export type Audience = (typeof AUDIENCES)[number];

export const TEAMS = {
  advisory: { name: "AI Advisory team", responseTime: "2 working days" },
  projects: { name: "Proof-of-concept team", responseTime: "3 working days" },
  training: { name: "Training team", responseTime: "2 working days" },
  funding: { name: "Funding desk", responseTime: "1 working day" },
  general: { name: "Customer service", responseTime: "1 working day" },
} as const;
export type TeamId = keyof typeof TEAMS;

export interface Service {
  id: string;
  name: string;
  category: ServiceCategory;
  audiences: Audience[];
  summary: string;
  details: string;
  price: string;
  duration: string;
  team: TeamId;
  tags: string[];
}

export interface Article {
  id: string;
  title: string;
  body: string;
  tags: string[];
}

export const SERVICES: Service[] = [
  {
    id: "ai-readiness-check",
    name: "AI Readiness Check",
    category: "advisory",
    audiences: ["sme", "startup"],
    summary:
      "A two-hour session that maps where AI could save time in your business and what to try first.",
    details:
      "An advisor interviews you about your daily work, looks at where time goes and lists 3–5 places where AI could help, ranked by effort and benefit. You get a one-page written summary.",
    price: "Free",
    duration: "2 hours",
    team: "advisory",
    tags: ["getting started", "assessment", "first step", "advice"],
  },
  {
    id: "ai-roadmap-workshop",
    name: "AI Roadmap Workshop",
    category: "advisory",
    audiences: ["sme", "public-sector"],
    summary:
      "Two half-day workshops that turn a list of AI ideas into a costed, prioritised plan.",
    details:
      "For organisations that already know where AI could help. Together we estimate cost, data needs and risk for each idea, and agree the order to do them in.",
    price: "Free for SMEs; €1,200 for public-sector organisations",
    duration: "2 × half a day",
    team: "advisory",
    tags: ["plan", "strategy", "prioritise", "workshop"],
  },
  {
    id: "rapid-poc",
    name: "Rapid Proof-of-Concept",
    category: "proof-of-concept",
    audiences: ["sme", "startup"],
    summary:
      "A small working prototype built on your own data in four weeks, to see if AI really fits the problem.",
    details:
      "We pick one narrow problem, build a prototype with your data and measure the result against today's way of working. You keep the code and a short report on whether to continue.",
    price: "€2,500 (the rest is covered by public funding)",
    duration: "4 weeks",
    team: "projects",
    tags: ["prototype", "pilot", "test", "own data", "poc"],
  },
  {
    id: "document-automation-pilot",
    name: "Document Automation Pilot",
    category: "proof-of-concept",
    audiences: ["sme", "public-sector"],
    summary:
      "Automates reading of invoices, orders or forms into structured data, tested on 100 of your own documents.",
    details:
      "We set up extraction for one document type, run it on a sample of your documents and report accuracy field by field, so you can decide with numbers.",
    price: "€3,000",
    duration: "6 weeks",
    team: "projects",
    tags: [
      "documents",
      "invoices",
      "orders",
      "extraction",
      "automation",
      "pdf",
    ],
  },
  {
    id: "genai-basics-course",
    name: "Generative AI Basics for Staff",
    category: "training",
    audiences: ["sme", "startup", "public-sector"],
    summary:
      "A hands-on half-day course on using AI assistants safely and well in everyday work.",
    details:
      "Covers writing good prompts, checking answers, what not to paste into an AI tool, and data protection basics. Run online or at your premises for up to 20 people.",
    price: "€40 per person",
    duration: "Half a day",
    team: "training",
    tags: ["course", "staff", "chatgpt", "prompts", "skills", "training"],
  },
  {
    id: "ai-act-briefing",
    name: "EU AI Act Briefing",
    category: "training",
    audiences: ["sme", "public-sector"],
    summary:
      "A 90-minute briefing on what the EU AI Act means for an organisation that uses or builds AI.",
    details:
      "Explains risk classes, the obligations for each, and what to check first. It is general guidance, not legal advice.",
    price: "Free",
    duration: "90 minutes",
    team: "training",
    tags: ["regulation", "ai act", "law", "compliance", "risk"],
  },
  {
    id: "funding-navigator",
    name: "Funding Navigator",
    category: "funding",
    audiences: ["sme", "startup"],
    summary:
      "Help finding public funding for an AI project and preparing the application.",
    details:
      "We match your project to suitable national and EU funding programmes, explain the conditions and review your application before you send it.",
    price: "Free",
    duration: "1–3 meetings",
    team: "funding",
    tags: ["grant", "financing", "money", "application", "funding"],
  },
  {
    id: "test-lab",
    name: "AI Test Lab",
    category: "technology-testing",
    audiences: ["sme", "startup"],
    summary:
      "Try AI tools and models on your own data in a safe test environment before you buy anything.",
    details:
      "Book the lab for a day. Our engineers help you compare two or three tools on the same task and write down the results.",
    price: "€300 per day",
    duration: "1–5 days",
    team: "projects",
    tags: ["test before invest", "compare tools", "lab", "try", "evaluate"],
  },
];

export const ARTICLES: Article[] = [
  {
    id: "who-we-are",
    title: "What is Lakeside AI Hub?",
    body: "Lakeside AI Hub is a publicly funded regional centre that helps small and medium-sized companies, start-ups and public organisations start using AI. Most services are free or partly funded. We are a cooperation of two universities and the regional development agency.",
    tags: ["about", "organisation", "who"],
  },
  {
    id: "how-to-start",
    title: "How do I get started?",
    body: "Most customers start with the free AI Readiness Check. Book it through the contact form or by asking this chatbot to connect you with the advisory team. After the check you get a written summary and, if useful, a suggestion for the next service.",
    tags: ["start", "first step", "book", "apply"],
  },
  {
    id: "who-can-use",
    title: "Who can use the services?",
    body: "Companies with fewer than 250 employees, start-ups and public-sector organisations in the Lakeside region can use the services. Larger companies can join training courses but not the funded services.",
    tags: ["eligibility", "who can", "requirements", "region", "size"],
  },
  {
    id: "pricing",
    title: "Why are the services free or cheap?",
    body: "The hub is funded by the EU and the national government to lower the threshold for trying AI. Funding rules limit each company to services worth €30,000 over three years. The price list of each service shows what the customer pays.",
    tags: ["price", "cost", "free", "funding", "state aid", "de minimis"],
  },
  {
    id: "data-protection",
    title: "What happens to our data?",
    body: "Data you share for a proof-of-concept is used only for that project, stored in the EU and deleted when the project ends unless you ask us to keep it. We sign a data processing agreement before any personal data is shared.",
    tags: ["privacy", "gdpr", "data", "security", "confidential"],
  },
  {
    id: "opening-hours",
    title: "Opening hours and location",
    body: "The hub is open Monday to Friday 9–16. Visits are by appointment at the Innovation House, Harbour Street 5. Most meetings can also be held online.",
    tags: ["hours", "address", "visit", "location", "contact"],
  },
  {
    id: "after-poc",
    title: "What happens after a proof-of-concept?",
    body: "If the prototype works, we help you plan the next step: building it yourself, buying a ready product or hiring a supplier. We can introduce suppliers but do not build production systems ourselves.",
    tags: ["next step", "production", "supplier", "after"],
  },
  {
    id: "events",
    title: "Events and webinars",
    body: "We run a free monthly webinar on practical AI topics and an AI breakfast for local companies every quarter. Recordings of past webinars are available on request.",
    tags: ["webinar", "event", "breakfast", "meetup"],
  },
  {
    id: "languages",
    title: "In which languages are services offered?",
    body: "All services are available in Finnish and English. Training courses can also be held in Swedish on request.",
    tags: ["language", "finnish", "english", "swedish"],
  },
  {
    id: "chatbot-itself",
    title: "About this chatbot",
    body: "This chatbot is an AI assistant. It answers from the hub's own service catalogue and FAQ, shows which entries it used, and can pass your question to a person. It can make mistakes, so check important details with the team.",
    tags: ["chatbot", "ai assistant", "how it works", "accuracy"],
  },
];
