import Image from "next/image";
import {
  ClaudeIcon,
  CodexIcon,
  CopilotIcon,
  CursorIcon,
} from "./provider-icons";

const agents = {
  claudeCode: { name: "Claude Code", icon: <ClaudeIcon className="size-4" /> },
  codex: { name: "Codex", icon: <CodexIcon className="size-4" /> },
  gemini: {
    name: "Gemini CLI",
    icon: (
      <Image
        src="/icons/gemini.svg"
        alt=""
        width={16}
        height={16}
        unoptimized
        className="size-4"
      />
    ),
  },
  copilot: { name: "GitHub Copilot", icon: <CopilotIcon className="size-4" /> },
  cursor: { name: "Cursor", icon: <CursorIcon className="size-4" /> },
};

/** A muted line of agent marks; each keeps its name as text. */
export function AgentLogos({
  lead,
  which,
}: {
  lead: string;
  which: (keyof typeof agents)[];
}) {
  return (
    <p className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
      <span>{lead}</span>
      {which.map((key) => (
        <span key={key} className="flex items-center gap-1.5">
          {agents[key].icon}
          {agents[key].name}
        </span>
      ))}
    </p>
  );
}
