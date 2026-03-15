"use client";

import { cn } from "@/lib/utils";
import {
  Activity,
  Calendar,
  CheckCircle2,
  FileText,
  MapPin,
  Users,
} from "lucide-react";

interface IncidentReport {
  [key: string]: unknown;
}

interface IncidentDetailsProps {
  data: unknown[];
  className?: string;
}

type FieldResolution = {
  key: string | null;
  value: unknown;
};

const FIELD_ALIASES = {
  date: ["date", "incident_date", "incident_datetime"],
  time: ["time", "incident_time"],
  location: ["location", "incident_location"],
  description: ["description", "incident_description", "brief_description", "what_happened"],
  people: ["people_involved", "people", "persons_involved", "involved_people"],
  injuries: ["injuries", "injury", "injuries_reported"],
  damages: ["damages", "damage", "damages_reported", "property_damage"],
  actions: ["actions_taken", "immediate_actions_taken", "actions", "immediate_actions"],
  witnesses: ["witnesses", "witness_information", "witness_info"],
} as const;

export function IncidentDetails({ data, className }: IncidentDetailsProps) {
  if (!Array.isArray(data) || data.length === 0) return null;

  return (
    <div className={cn("space-y-8", className)}>
      {data.map((item, index) => {
        const report = item as IncidentReport;
        const displayedKeys = new Set<string>();

        const date = resolveField(report, FIELD_ALIASES.date, displayedKeys);
        const time = resolveField(report, FIELD_ALIASES.time, displayedKeys);
        const location = resolveField(report, FIELD_ALIASES.location, displayedKeys);
        const description = resolveField(report, FIELD_ALIASES.description, displayedKeys);
        const people = resolveField(report, FIELD_ALIASES.people, displayedKeys);
        const injuries = resolveField(report, FIELD_ALIASES.injuries, displayedKeys);
        const damages = resolveField(report, FIELD_ALIASES.damages, displayedKeys);
        const actions = resolveField(report, FIELD_ALIASES.actions, displayedKeys);
        const witnesses = resolveField(report, FIELD_ALIASES.witnesses, displayedKeys);

        const formattedDate = formatIncidentDate(date.value);
        const otherKeys = Object.keys(report).filter(
          (key) => !displayedKeys.has(key) && hasContent(report[key]),
        );

        return (
          <div key={index} className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="bg-card flex items-start space-x-4 rounded-xl border p-4 shadow-sm">
                <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                  <Calendar className="text-primary h-5 w-5" />
                </div>
                <div>
                  <p className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
                    Date & Time
                  </p>
                  <p className="font-medium">{formattedDate}</p>
                  {hasContent(time.value) && (
                    <p className="text-muted-foreground text-sm">{String(time.value)}</p>
                  )}
                </div>
              </div>
              <div className="bg-card flex items-start space-x-4 rounded-xl border p-4 shadow-sm">
                <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                  <MapPin className="text-primary h-5 w-5" />
                </div>
                <div>
                  <p className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
                    Location
                  </p>
                  <p className="font-medium">{valueOrNA(location.value)}</p>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="bg-primary/10 flex h-8 w-8 items-center justify-center rounded-lg">
                  <FileText className="text-primary h-4 w-4" />
                </div>
                <h3 className="text-lg font-semibold tracking-tight">Incident Description</h3>
              </div>
              <div className="bg-muted/30 text-card-foreground rounded-xl border p-5 leading-relaxed shadow-sm">
                {renderList(description.value, "No description extracted.")}
              </div>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <div className="bg-card rounded-xl border shadow-sm">
                <div className="flex items-center gap-2 border-b p-4">
                  <Users className="text-muted-foreground h-4 w-4" />
                  <h3 className="font-medium">People Involved</h3>
                </div>
                <div className="p-4">{renderList(people.value, "No extracted information.")}</div>
              </div>

              <div className="bg-card rounded-xl border shadow-sm">
                <div className="flex items-center gap-2 border-b p-4">
                  <Activity className="text-muted-foreground h-4 w-4" />
                  <h3 className="font-medium">Injuries & Damages</h3>
                </div>
                <div className="space-y-4 p-4">
                  <div>
                    <div className="mb-2 flex items-center gap-2">
                      <span className="bg-destructive/10 text-destructive rounded-md px-2 py-0.5 text-xs font-medium uppercase">
                        Injuries
                      </span>
                    </div>
                    <div className="text-sm">{valueOrFallback(injuries.value, "None reported.")}</div>
                  </div>
                  <div>
                    <div className="mb-2 flex items-center gap-2">
                      <span className="rounded-md bg-orange-500/10 px-2 py-0.5 text-xs font-medium uppercase text-orange-600 dark:text-orange-400">
                        Damages
                      </span>
                    </div>
                    <div className="text-sm">{valueOrFallback(damages.value, "None reported.")}</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-green-500/10">
                  <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-500" />
                </div>
                <h3 className="text-lg font-semibold tracking-tight">Actions Taken</h3>
              </div>
              <div className="rounded-xl border border-green-200 bg-green-500/5 p-5 dark:border-green-900">
                {renderList(actions.value, "No actions recorded.", true)}
              </div>
            </div>

            <div className="bg-card rounded-xl border shadow-sm">
              <div className="flex items-center gap-2 border-b p-4">
                <Users className="text-muted-foreground h-4 w-4" />
                <h3 className="font-medium">Witnesses</h3>
              </div>
              <div className="p-4">{renderList(witnesses.value, "No witness information recorded.")}</div>
            </div>

            {otherKeys.length > 0 && (
              <div className="space-y-4 border-t pt-6">
                <h3 className="text-muted-foreground text-sm font-semibold uppercase tracking-wider">
                  Additional Details
                </h3>
                <div className="grid gap-4 sm:grid-cols-2">
                  {otherKeys.map((key) => (
                    <div key={key} className="bg-muted/30 rounded-xl border p-4">
                      <p className="text-muted-foreground mb-2 text-xs font-bold uppercase tracking-wide">
                        {formatFieldName(key)}
                      </p>
                      <div className="text-sm font-medium">{renderList(report[key], "N/A")}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {index < data.length - 1 && <hr className="border-muted my-8 border-dashed" />}
          </div>
        );
      })}
    </div>
  );
}

function resolveField(report: IncidentReport, aliases: readonly string[], displayedKeys: Set<string>): FieldResolution {
  for (const key of aliases) {
    const value = report[key];
    if (hasContent(value)) {
      displayedKeys.add(key);
      return { key, value };
    }
  }
  for (const key of aliases) {
    if (key in report) {
      displayedKeys.add(key);
      return { key, value: report[key] };
    }
  }
  return { key: null, value: null };
}

function formatIncidentDate(value: unknown): string {
  const dateFormatter = new Intl.DateTimeFormat("en-US", { dateStyle: "long" });
  if (!hasContent(value)) return dateFormatter.format(new Date());
  try {
    const d = new Date(String(value));
    return !Number.isNaN(d.getTime()) ? dateFormatter.format(d) : String(value);
  } catch {
    return String(value);
  }
}

function hasContent(content: unknown): boolean {
  if (content === null || content === undefined) return false;
  if (Array.isArray(content)) return content.some((item) => hasContent(item));
  if (typeof content === "string") return content.trim().length > 0;
  return true;
}

function valueOrNA(content: unknown): string {
  return hasContent(content) ? String(content) : "N/A";
}

function valueOrFallback(content: unknown, fallback: string): string {
  return hasContent(content) ? String(content) : fallback;
}

function formatFieldName(key: string): string {
  const labels: Record<string, string> = {
    incident_description: "Incident Description",
    brief_description: "Brief Description",
    what_happened: "What Happened",
    people_involved: "People Involved",
    immediate_actions_taken: "Actions Taken",
    witness_information: "Witness Information",
    witness_info: "Witness Information",
    injuries_reported: "Injuries",
    damages_reported: "Damages",
    property_damage: "Damages",
  };
  return labels[key] || key.replace(/_/g, " ");
}

function renderList(content: unknown, fallback: string, isChecklist = false) {
  if (!hasContent(content)) {
    return <p className="text-muted-foreground text-sm italic">{fallback}</p>;
  }

  if (Array.isArray(content)) {
    return (
      <ul className="space-y-3">
        {content.map((item, i) => (
          <li key={i} className="flex items-start gap-3 text-sm leading-relaxed">
            {isChecklist ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-500" />
            ) : (
              <div className="bg-primary/40 mt-2 h-1.5 w-1.5 shrink-0 rounded-full" />
            )}
            <span className="text-foreground/90">{String(item)}</span>
          </li>
        ))}
      </ul>
    );
  }

  if (typeof content === "object") {
    return (
      <pre className="text-muted-foreground bg-muted max-w-full overflow-x-auto rounded-md p-2 font-mono text-xs whitespace-pre-wrap">
        {JSON.stringify(content, null, 2)}
      </pre>
    );
  }

  return <p className="text-foreground/90 text-sm leading-relaxed">{String(content)}</p>;
}
