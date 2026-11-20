// The screening as data (the skill's screening.json), with the plain-language
// wording the skill's report guide gives every value. The checker has already
// validated a screening before the page shows it; these types only describe it.

export type RiskClass = "unacceptable" | "high" | "limited" | "minimal";
export type Outcome = "classified" | "undetermined" | "not_in_scope";
export type Role = "provider" | "deployer" | "both" | "unknown";
export type Confidence = "high" | "medium" | "low";
export type ActionStatus = "in_place" | "partly" | "missing" | "unknown";

export interface Evidence {
  source: "description" | "answer" | "document";
  locator: string;
  quote: string;
}
export interface Citation {
  ref: string;
  instrument?: string;
}
export interface Finding {
  id: string;
  question: string;
  status: "yes" | "no" | "unknown" | "not_applicable";
  answer: string;
  evidence: Evidence[];
  citations: Citation[];
  reasoning: string;
  confidence: Confidence;
}
export interface ScreeningAction {
  type: "required" | "recommended";
  action: string;
  reason?: string;
  route: "system" | "organisation";
  applies_to?: "provider" | "deployer" | "both";
  applies_from?: string;
  citations?: Citation[];
  based_on: string[];
  status?: ActionStatus;
  status_evidence?: Evidence[];
}
export interface TimelineItem {
  date: string;
  what: string;
  status: "in_force" | "upcoming";
  citations: Citation[];
}
export interface Screening {
  screened_on: string;
  reference_last_verified: string;
  summary: {
    outcome: Outcome;
    risk_class: RiskClass | null;
    role: Role;
    confidence: Confidence;
    mode: "planned" | "existing";
    lifecycle_stage: string;
    screened_use: string;
    one_line: string;
    alternatives?: { if: string; risk_class: RiskClass }[];
    flags: { art_6_3_exempt: boolean; transparency_duties: boolean };
  };
  findings: Finding[];
  actions: ScreeningAction[];
  timeline: TimelineItem[];
  triggers: {
    change: string;
    would_become: RiskClass;
    citations: Citation[];
  }[];
  open_questions: string[];
  adjacent: { flag: string; citations: Citation[]; evidence?: Evidence[] }[];
  disclaimer: string;
}

export interface TierInfo {
  label: string;
  means: string;
}

/** The four tiers of the AI Act, from the most to the least regulated. */
export const TIERS: Record<RiskClass, TierInfo> = {
  unacceptable: {
    label: "Unacceptable risk (prohibited)",
    means:
      "The AI Act bans this practice. It may not be put on the market or used in the EU as described.",
  },
  high: {
    label: "High-risk",
    means:
      "Allowed, but with strict requirements: risk management, documentation, human oversight, logging, accuracy, and information for the people affected.",
  },
  limited: {
    label: "Limited risk (transparency obligations)",
    means:
      "Allowed. People must be told when they deal with an AI system or with AI-generated content.",
  },
  minimal: {
    label: "Minimal or no risk",
    means:
      "Allowed with no requirements specific to this system, beyond giving staff who use AI enough knowledge to use it well (AI literacy).",
  },
};
export const TIER_ORDER: RiskClass[] = [
  "unacceptable",
  "high",
  "limited",
  "minimal",
];

export const ROLES: Record<Role, { label: string; means: string }> = {
  provider: {
    label: "Provider",
    means:
      "You develop the AI system, or have it developed, and offer it or put it into use under your own name. Providers carry most of the duties.",
  },
  deployer: {
    label: "Deployer (user)",
    means:
      "You use an AI system made by someone else in your work. Deployers have fewer duties, mainly about how the system is used.",
  },
  both: {
    label: "Provider and deployer",
    means:
      "You build the system and use it yourselves, so both sets of duties apply.",
  },
  unknown: {
    label: "Not yet known",
    means: "A further answer would settle it.",
  },
};

export const CONFIDENCE: Record<Confidence, { label: string; means: string }> =
  {
    high: {
      label: "High",
      means:
        "Every fact the result rests on comes from your own words or documents.",
    },
    medium: {
      label: "Medium",
      means: "One fact rests on an assumption you have not confirmed.",
    },
    low: { label: "Low", means: "A key fact is unknown." },
  };

export const ACTION_STATUS: Record<ActionStatus, string> = {
  in_place: "In place",
  partly: "Partly in place",
  missing: "Missing",
  unknown: "Not known",
};

export const ROUTE_LABEL = {
  system: "A change to the AI system or how it is used",
  organisation: "Something your organisation does around the system",
} as const;

/** The eight questions, in the plain words the report guide gives them. */
export const FINDING_QUESTIONS: Record<string, string> = {
  F1: "Does the AI Act apply to this system?",
  F2: "What is your role: do you provide the system or use it?",
  F3: "Does it do anything the AI Act bans?",
  F4: "Is it part of, or itself, a product covered by EU product-safety law, such as a medical device or machine?",
  F5: "Is it used in one of the areas the AI Act lists as high-risk?",
  F6: "Does an exception take it out of the high-risk tier?",
  F7: "Must people be told they are dealing with AI, or with AI-generated content?",
  F8: "Which general-purpose AI model does it use, and do you change that model?",
};

export const FINDING_STATUS: Record<Finding["status"], string> = {
  yes: "Yes",
  no: "No",
  unknown: "Not known yet",
  not_applicable: "Does not apply",
};

export function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** True when a required action's date has passed on the screening date. */
export function isCurrentGap(a: ScreeningAction, screenedOn: string): boolean {
  return (
    a.type === "required" &&
    (a.status === "missing" || a.status === "partly") &&
    Boolean(a.applies_from) &&
    (a.applies_from as string) <= screenedOn
  );
}

/**
 * An alternative tier's condition, ready to follow "If ". The model sometimes
 * writes the condition as a sentence of its own ("If the system ranks people.");
 * without this the page printed "If If the system ranks people..".
 */
export function conditionText(condition: string): string {
  return condition
    .trim()
    .replace(/^if\s+/i, "")
    .replace(/[.\s]+$/, "");
}
