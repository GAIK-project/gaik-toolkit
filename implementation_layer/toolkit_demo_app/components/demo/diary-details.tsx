"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import {
  Calendar,
  CheckCircle2,
  Cloud,
  FileText,
  HardHat,
  MapPin,
  Pause,
  Play,
  PlayCircle,
  StopCircle,
  Users,
} from "lucide-react";

interface DiaryEntry {
  [key: string]: unknown;
}

interface DiaryDetailsProps {
  data: unknown[];
  className?: string;
}

type FieldResolution = {
  key: string | null;
  value: unknown;
};

const FIELD_ALIASES = {
  project: ["kohde", "project", "project_or_site_name", "project_name", "site_name"],
  author: ["laatija", "author", "author_or_supervisor_name", "supervisor_name"],
  date: ["paivamaara", "date"],
  week: ["tyoviikko", "week", "week_number"],
  weather: ["saa", "weather", "weather_conditions"],
  personnel: ["resurssit_henkilosto", "personnel_and_subcontractors", "personnel", "subcontractors"],
  work: ["paivan_tyot_omat_tyot", "days_work_tasks", "days_work_tasks", "todays_work", "work_tasks"],
  events: ["paivan_tapahtumat", "days_events", "days_events", "events"],
  attachments: ["liitteet", "attachments"],
  observations: ["valvojan_huomiot", "supervisor_observations", "observations"],
  deviations: ["paivan_poikkeamat", "days_deviations", "deviations"],
  started: ["aloitetut_tyovaiheet", "started_work_phases", "started_phases"],
  ongoing: ["kaynnissa_olevat_tyovai", "ongoing_work_phases", "ongoing_phases"],
  completed: ["paattyneet_tyovai", "completed_work_phases", "completed_phases"],
  interrupted: ["keskeytyneet_tyovai", "interrupted_work_phases", "interrupted_phases"],
  extensions: ["pyydetyt_lisaajat", "requested_extensions"],
  inspections: ["tehdyt_katselmukset", "completed_inspections", "inspections"],
  remarks: ["valvojan_huomautukset", "supervisor_remarks", "remarks"],
  supervisorSignature: ["valvojan_allekirjoitus", "supervisor_signature"],
  responsibleSignature: ["vastaavan_allekirjoitus", "responsible_signature", "manager_signature"],
} as const;

export function DiaryDetails({ data, className }: DiaryDetailsProps) {
  if (!Array.isArray(data) || data.length === 0) return null;

  return (
    <div className={cn("space-y-8", className)}>
      {data.map((item, index) => {
        const entry = item as DiaryEntry;
        const displayedKeys = new Set<string>();

        const project = resolveField(entry, FIELD_ALIASES.project, displayedKeys);
        const author = resolveField(entry, FIELD_ALIASES.author, displayedKeys);
        const date = resolveField(entry, FIELD_ALIASES.date, displayedKeys);
        const week = resolveField(entry, FIELD_ALIASES.week, displayedKeys);
        const weather = resolveField(entry, FIELD_ALIASES.weather, displayedKeys);
        const personnel = resolveField(entry, FIELD_ALIASES.personnel, displayedKeys);
        const work = resolveField(entry, FIELD_ALIASES.work, displayedKeys);
        const events = resolveField(entry, FIELD_ALIASES.events, displayedKeys);
        const attachments = resolveField(entry, FIELD_ALIASES.attachments, displayedKeys);
        const observations = resolveField(entry, FIELD_ALIASES.observations, displayedKeys);
        const deviations = resolveField(entry, FIELD_ALIASES.deviations, displayedKeys);
        const started = resolveField(entry, FIELD_ALIASES.started, displayedKeys);
        const ongoing = resolveField(entry, FIELD_ALIASES.ongoing, displayedKeys);
        const completed = resolveField(entry, FIELD_ALIASES.completed, displayedKeys);
        const interrupted = resolveField(entry, FIELD_ALIASES.interrupted, displayedKeys);
        const extensions = resolveField(entry, FIELD_ALIASES.extensions, displayedKeys);
        const inspections = resolveField(entry, FIELD_ALIASES.inspections, displayedKeys);
        const remarks = resolveField(entry, FIELD_ALIASES.remarks, displayedKeys);
        const supervisorSignature = resolveField(entry, FIELD_ALIASES.supervisorSignature, displayedKeys);
        const responsibleSignature = resolveField(entry, FIELD_ALIASES.responsibleSignature, displayedKeys);

        const additionalKeys = Object.keys(entry).filter(
          (key) => !displayedKeys.has(key) && hasContent(entry[key]),
        );

        return (
          <div key={index} className="space-y-6">
            <div className="space-y-4">
              <div className="bg-card flex items-center gap-4 rounded-xl border p-4 shadow-sm">
                <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                  <Calendar className="text-primary h-5 w-5" />
                </div>
                <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
                  <div>
                    <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                      Date
                    </p>
                    <p className="font-medium">{valueOrNA(date.value)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                      Week
                    </p>
                    <p className="font-medium">{valueOrNA(week.value)}</p>
                  </div>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="bg-card flex items-start space-x-4 rounded-xl border p-4 shadow-sm">
                  <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                    <HardHat className="text-primary h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                      Project
                    </p>
                    <p className="font-medium" title={stringValue(project.value) || undefined}>
                      {valueOrNA(project.value)}
                    </p>
                  </div>
                </div>

                <div className="bg-card flex items-start space-x-4 rounded-xl border p-4 shadow-sm">
                  <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                    <FileText className="text-primary h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                      Author
                    </p>
                    <p className="font-medium" title={stringValue(author.value) || undefined}>
                      {valueOrNA(author.value)}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <DetailCard title="Weather" icon={<Cloud className="h-5 w-5 text-blue-500" />} iconClassName="bg-blue-500/10">
              {renderList(weather.value, "N/A")}
            </DetailCard>

            <DetailCard title="Personnel" icon={<Users className="text-muted-foreground h-4 w-4" />} bordered>
              {renderList(personnel.value, "N/A")}
            </DetailCard>

            <SectionCard title="Today's Work" icon={<CheckCircle2 className="text-primary h-4 w-4" />} iconClassName="bg-primary/10">
              {renderList(work.value, "No work recorded", true)}
            </SectionCard>

            <div className="grid gap-4 md:grid-cols-2">
              <PhaseCard title="Started Phases" icon={<PlayCircle className="h-4 w-4 text-green-600 dark:text-green-500" />} value={started.value} />
              <PhaseCard title="Ongoing Phases" icon={<Play className="h-4 w-4 text-blue-600 dark:text-blue-500" />} value={ongoing.value} />
              <PhaseCard title="Completed Phases" icon={<StopCircle className="h-4 w-4 text-gray-600 dark:text-gray-400" />} value={completed.value} />
              <PhaseCard title="Interrupted Phases" icon={<Pause className="h-4 w-4 text-orange-600 dark:text-orange-500" />} value={interrupted.value} />
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <DetailCard title="Day's Events" icon={<MapPin className="text-muted-foreground h-4 w-4" />} bordered>
                {renderList(events.value, "N/A")}
              </DetailCard>
              <div className="rounded-xl border border-orange-200 bg-orange-500/5 shadow-sm dark:border-orange-900">
                <div className="flex items-center gap-2 border-b border-orange-200 p-4 dark:border-orange-900">
                  <span className="rounded-md bg-orange-500/10 px-2 py-0.5 text-xs font-medium uppercase text-orange-600 dark:text-orange-400">
                    Deviations
                  </span>
                </div>
                <div className="p-4">{renderList(deviations.value, "N/A")}</div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/10">
                  <FileText className="h-4 w-4 text-amber-600 dark:text-amber-500" />
                </div>
                <h3 className="text-lg font-semibold tracking-tight">Supervisor Observations</h3>
              </div>
              <div className="rounded-xl border border-amber-200 bg-amber-500/5 p-5 dark:border-amber-900">
                <div className="mb-3">
                  <p className="text-muted-foreground mb-1 text-xs font-medium uppercase">Observations</p>
                  {renderList(observations.value, "N/A")}
                </div>
                <div>
                  <p className="text-muted-foreground mb-1 text-xs font-medium uppercase">Remarks</p>
                  {renderList(remarks.value, "N/A")}
                </div>
              </div>
            </div>

            <div className="space-y-4 border-t pt-6">
              <h3 className="text-muted-foreground text-sm font-semibold uppercase tracking-wider">
                Additional Details
              </h3>
              <div className="grid gap-4 sm:grid-cols-2">
                <AdditionalCard title="Attachments">{renderList(attachments.value, "N/A")}</AdditionalCard>
                <AdditionalCard title="Requested Extensions">{renderList(extensions.value, "N/A")}</AdditionalCard>
                <AdditionalCard title="Completed Inspections">{renderList(inspections.value, "N/A")}</AdditionalCard>
                <AdditionalCard title="Supervisor Signature">{renderList(supervisorSignature.value, "N/A")}</AdditionalCard>
                <AdditionalCard title="Responsible Signature">{renderList(responsibleSignature.value, "N/A")}</AdditionalCard>
                {additionalKeys.map((key) => (
                  <AdditionalCard key={key} title={formatFieldName(key)}>
                    {renderList(entry[key], "N/A")}
                  </AdditionalCard>
                ))}
              </div>
            </div>

            {index < data.length - 1 && <hr className="border-muted my-8 border-dashed" />}
          </div>
        );
      })}
    </div>
  );
}

function resolveField(entry: DiaryEntry, aliases: readonly string[], displayedKeys: Set<string>): FieldResolution {
  for (const key of aliases) {
    const value = entry[key];
    if (hasContent(value)) {
      displayedKeys.add(key);
      return { key, value };
    }
  }
  for (const key of aliases) {
    if (key in entry) {
      displayedKeys.add(key);
      return { key, value: entry[key] };
    }
  }
  return { key: null, value: null };
}

function hasContent(content: unknown): boolean {
  if (content === null || content === undefined) return false;
  if (Array.isArray(content)) return content.some((item) => hasContent(item));
  if (typeof content === "string") return content.trim().length > 0;
  return true;
}

function stringValue(content: unknown): string {
  if (content === null || content === undefined) return "";
  if (Array.isArray(content)) return content.map(String).join(", ");
  if (typeof content === "object") return JSON.stringify(content);
  return String(content);
}

function valueOrNA(content: unknown): string {
  return hasContent(content) ? stringValue(content) : "N/A";
}

function formatFieldName(key: string): string {
  const fieldNames: Record<string, string> = {
    liitteet: "Attachments",
    attachments: "Attachments",
    pyydetyt_lisaajat: "Requested Extensions",
    requested_extensions: "Requested Extensions",
    tehdyt_katselmukset: "Completed Inspections",
    completed_inspections: "Completed Inspections",
    valvojan_allekirjoitus: "Supervisor Signature",
    supervisor_signature: "Supervisor Signature",
    vastaavan_allekirjoitus: "Responsible Signature",
    responsible_signature: "Responsible Signature",
    manager_signature: "Responsible Signature",
    kaynnissa_olevat_tyovai: "Ongoing Phases",
    ongoing_work_phases: "Ongoing Phases",
    paattyneet_tyovai: "Completed Phases",
    completed_work_phases: "Completed Phases",
    keskeytyneet_tyovai: "Interrupted Phases",
    interrupted_work_phases: "Interrupted Phases",
    aloitetut_tyovaiheet: "Started Phases",
    started_work_phases: "Started Phases",
    paivan_tapahtumat: "Day's Events",
    days_events: "Day's Events",
    paivan_poikkeamat: "Deviations",
    days_deviations: "Deviations",
    paivan_tyot_omat_tyot: "Today's Work",
    days_work_tasks: "Day's Work Tasks",
    days_work_tasks: "Day's Work Tasks",
    resurssit_henkilosto: "Personnel",
    personnel_and_subcontractors: "Personnel and Subcontractors",
    kohde: "Project",
    project_or_site_name: "Project or Site Name",
    laatija: "Author",
    author_or_supervisor_name: "Author or Supervisor Name",
    paivamaara: "Date",
    saa: "Weather",
    valvojan_huomiot: "Supervisor Observations",
    supervisor_observations: "Supervisor Observations",
    valvojan_huomautukset: "Supervisor Remarks",
    supervisor_remarks: "Supervisor Remarks",
  };
  return fieldNames[key] || key.replace(/_/g, " ");
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

function DetailCard({ title, icon, iconClassName = "bg-primary/10", bordered = false, children }: { title: string; icon: ReactNode; iconClassName?: string; bordered?: boolean; children: ReactNode }) {
  const body = (
    <>
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${iconClassName}`}>
        {icon}
      </div>
      <div>
        <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">{title}</p>
        <div className="mt-1">{children}</div>
      </div>
    </>
  );

  if (bordered) {
    return (
      <div className="bg-card rounded-xl border shadow-sm">
        <div className="flex items-center gap-2 border-b p-4">
          {icon}
          <h3 className="font-medium">{title}</h3>
        </div>
        <div className="p-4">{children}</div>
      </div>
    );
  }

  return <div className="bg-card flex items-start space-x-4 rounded-xl border p-4 shadow-sm">{body}</div>;
}

function SectionCard({ title, icon, iconClassName, children }: { title: string; icon: ReactNode; iconClassName: string; children: ReactNode }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${iconClassName}`}>{icon}</div>
        <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
      </div>
      <div className="bg-muted/30 text-card-foreground rounded-xl border p-5 leading-relaxed shadow-sm">{children}</div>
    </div>
  );
}

function PhaseCard({ title, icon, value }: { title: string; icon: ReactNode; value: unknown }) {
  return (
    <div className="bg-card rounded-xl border shadow-sm">
      <div className="flex items-center gap-2 border-b p-4">
        {icon}
        <h3 className="font-medium">{title}</h3>
      </div>
      <div className="p-4">{renderList(value, "None")}</div>
    </div>
  );
}

function AdditionalCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="bg-muted/30 rounded-xl border p-4">
      <p className="text-muted-foreground mb-2 text-xs font-bold uppercase tracking-wide">{title}</p>
      <div className="text-sm font-medium">{children}</div>
    </div>
  );
}
