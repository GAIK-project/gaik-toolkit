// The three knowledge processes the toolkit is organised around, as the docs site
// defines them. The site menu and the home page both group demos by these.
import {
  BookOpenCheck,
  FileInput,
  type LucideIcon,
  Search,
} from "lucide-react";

export const CAPTURE = "Knowledge capture";
export const ACCESS = "Knowledge access";
export const SYNTHESIS = "Knowledge synthesis";

export type KnowledgeProcess =
  | typeof CAPTURE
  | typeof ACCESS
  | typeof SYNTHESIS;

export interface ProcessStyle {
  name: KnowledgeProcess;
  /** One line on what the process does. */
  summary: string;
  icon: LucideIcon;
  /** Icon tile: background and icon colour. */
  tile: string;
  /** Text accent for headings and links. */
  accent: string;
  /** Border colour on hover. */
  hoverBorder: string;
}

export const PROCESSES: readonly ProcessStyle[] = [
  {
    name: CAPTURE,
    summary:
      "Extract the information you need from documents, recordings, images and spreadsheets.",
    icon: FileInput,
    tile: "bg-teal-500/10 text-teal-700 dark:text-teal-300",
    accent: "text-teal-700 dark:text-teal-300",
    hoverBorder: "hover:border-teal-500/50",
  },
  {
    name: ACCESS,
    summary:
      "Ask questions of documents, databases and tables, and get answers you can check.",
    icon: Search,
    tile: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
    accent: "text-sky-700 dark:text-sky-300",
    hoverBorder: "hover:border-sky-500/50",
  },
  {
    name: SYNTHESIS,
    summary:
      "Write reports, audio and evaluations that stay grounded in their sources.",
    icon: BookOpenCheck,
    tile: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
    accent: "text-violet-700 dark:text-violet-300",
    hoverBorder: "hover:border-violet-500/50",
  },
];

export function processStyle(name: KnowledgeProcess): ProcessStyle {
  return PROCESSES.find((p) => p.name === name) ?? PROCESSES[0];
}

/** The home page anchor of a process's component group. */
export const processAnchor = (process: KnowledgeProcess) =>
  `components-${process.toLowerCase().replace(/\s+/g, "-")}`;
