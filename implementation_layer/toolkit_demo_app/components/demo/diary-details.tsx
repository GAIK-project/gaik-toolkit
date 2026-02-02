"use client";
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
  kohde?: string | null;
  laatija?: string | null;
  paivamaara?: string | null;
  tyoviikko?: number | string | null;
  saa?: string | null;
  resurssit_henkilosto?: string | null;
  paivan_tyot_omat_tyot?: string[] | string | null;
  paivan_tapahtumat?: string | null;
  liitteet?: string | null;
  valvojan_huomiot?: string | null;
  paivan_poikkeamat?: string | null;
  aloitetut_tyovaiheet?: string[] | string | null;
  kaynnissa_olevat_tyovai?: string[] | string | null;
  paattyneet_tyovai?: string[] | string | null;
  keskeytyneet_tyovai?: string[] | string | null;
  pyydetyt_lisaajat?: string | null;
  tehdyt_katselmukset?: string | null;
  valvojan_huomautukset?: string | null;
  valvojan_allekirjoitus?: string | null;
  vastaavan_allekirjoitus?: string | null;
  [key: string]: unknown;
}

interface DiaryDetailsProps {
  data: unknown[];
  className?: string;
}

export function DiaryDetails({ data, className }: DiaryDetailsProps) {
  if (!Array.isArray(data) || data.length === 0) return null;

  return (
    <div className={cn("space-y-8", className)}>
      {data.map((item, index) => {
        const entry = item as DiaryEntry;

        return (
          <div key={index} className="space-y-6">
            {/* Header Section: Date first, then Project & Author */}
            <div className="space-y-4">
              {/* Date & Week - Full width on top */}
              <div className="bg-card flex items-center gap-4 rounded-xl border p-4 shadow-sm">
                <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                  <Calendar className="text-primary h-5 w-5" />
                </div>
                <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
                  <div>
                    <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                      Date
                    </p>
                    <p className="font-medium">{entry.paivamaara || "N/A"}</p>
                  </div>
                  {entry.tyoviikko && (
                    <div>
                      <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                        Week
                      </p>
                      <p className="font-medium">{entry.tyoviikko}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Project & Author - Two columns below */}
              <div className="grid gap-4 sm:grid-cols-2">
                {/* Project (Kohde) */}
                <div className="bg-card flex items-start space-x-4 rounded-xl border p-4 shadow-sm">
                  <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                    <HardHat className="text-primary h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                      Project
                    </p>
                    <p className="truncate font-medium" title={entry.kohde || undefined}>
                      {entry.kohde || "N/A"}
                    </p>
                  </div>
                </div>

                {/* Author (Laatija) */}
                <div className="bg-card flex items-start space-x-4 rounded-xl border p-4 shadow-sm">
                  <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                    <FileText className="text-primary h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                      Author
                    </p>
                    <p className="truncate font-medium" title={entry.laatija || undefined}>
                      {entry.laatija || "N/A"}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Weather */}
            {entry.saa && (
              <div className="bg-card flex items-start space-x-4 rounded-xl border p-4 shadow-sm">
                <div className="bg-blue-500/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                  <Cloud className="h-5 w-5 text-blue-500" />
                </div>
                <div>
                  <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                    Weather
                  </p>
                  <p className="font-medium">{entry.saa}</p>
                </div>
              </div>
            )}

            {/* Personnel (Resurssit - Henkilöstö) */}
            {entry.resurssit_henkilosto && (
              <div className="bg-card rounded-xl border shadow-sm">
                <div className="flex items-center gap-2 border-b p-4">
                  <Users className="text-muted-foreground h-4 w-4" />
                  <h3 className="font-medium">Personnel</h3>
                </div>
                <div className="p-4">
                  <p className="text-foreground/90 text-sm leading-relaxed whitespace-pre-line">
                    {entry.resurssit_henkilosto}
                  </p>
                </div>
              </div>
            )}

            {/* Day's Work (Päivän työt) */}
            {entry.paivan_tyot_omat_tyot && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="bg-primary/10 flex h-8 w-8 items-center justify-center rounded-lg">
                    <CheckCircle2 className="text-primary h-4 w-4" />
                  </div>
                  <h3 className="text-lg font-semibold tracking-tight">
                    Today's Work
                  </h3>
                </div>
                <div className="bg-muted/30 text-card-foreground rounded-xl border p-5 leading-relaxed shadow-sm">
                  {renderList(entry.paivan_tyot_omat_tyot, "No work recorded", true)}
                </div>
              </div>
            )}

            {/* Work Phases Grid */}
            <div className="grid gap-4 md:grid-cols-2">
              {/* Started Work Phases (Aloitetut työvaiheet) */}
              {entry.aloitetut_tyovaiheet && hasContent(entry.aloitetut_tyovaiheet) && (
                <div className="bg-card rounded-xl border shadow-sm">
                  <div className="flex items-center gap-2 border-b p-4">
                    <PlayCircle className="h-4 w-4 text-green-600 dark:text-green-500" />
                    <h3 className="font-medium">Started Phases</h3>
                  </div>
                  <div className="p-4">
                    {renderList(entry.aloitetut_tyovaiheet, "None")}
                  </div>
                </div>
              )}

              {/* Ongoing Work Phases (Käynnissä olevat) */}
              {entry.kaynnissa_olevat_tyovai && hasContent(entry.kaynnissa_olevat_tyovai) && (
                <div className="bg-card rounded-xl border shadow-sm">
                  <div className="flex items-center gap-2 border-b p-4">
                    <Play className="h-4 w-4 text-blue-600 dark:text-blue-500" />
                    <h3 className="font-medium">Ongoing Phases</h3>
                  </div>
                  <div className="p-4">
                    {renderList(entry.kaynnissa_olevat_tyovai, "None")}
                  </div>
                </div>
              )}

              {/* Completed Work Phases (Päättyneet) */}
              {entry.paattyneet_tyovai && hasContent(entry.paattyneet_tyovai) && (
                <div className="bg-card rounded-xl border shadow-sm">
                  <div className="flex items-center gap-2 border-b p-4">
                    <StopCircle className="h-4 w-4 text-gray-600 dark:text-gray-400" />
                    <h3 className="font-medium">Completed Phases</h3>
                  </div>
                  <div className="p-4">
                    {renderList(entry.paattyneet_tyovai, "None")}
                  </div>
                </div>
              )}

              {/* Interrupted Work Phases (Keskeytyneet) */}
              {entry.keskeytyneet_tyovai && hasContent(entry.keskeytyneet_tyovai) && (
                <div className="bg-card rounded-xl border shadow-sm">
                  <div className="flex items-center gap-2 border-b p-4">
                    <Pause className="h-4 w-4 text-orange-600 dark:text-orange-500" />
                    <h3 className="font-medium">Interrupted Phases</h3>
                  </div>
                  <div className="p-4">
                    {renderList(entry.keskeytyneet_tyovai, "None")}
                  </div>
                </div>
              )}
            </div>

            {/* Events and Deviations */}
            <div className="grid gap-4 md:grid-cols-2">
              {/* Day's Events (Päivän tapahtumat) */}
              {entry.paivan_tapahtumat && (
                <div className="bg-card rounded-xl border shadow-sm">
                  <div className="flex items-center gap-2 border-b p-4">
                    <MapPin className="text-muted-foreground h-4 w-4" />
                    <h3 className="font-medium">Day's Events</h3>
                  </div>
                  <div className="p-4">
                    <p className="text-foreground/90 text-sm leading-relaxed">
                      {entry.paivan_tapahtumat}
                    </p>
                  </div>
                </div>
              )}

              {/* Deviations (Päivän poikkeamat) */}
              {entry.paivan_poikkeamat && (
                <div className="rounded-xl border border-orange-200 bg-orange-500/5 shadow-sm dark:border-orange-900">
                  <div className="flex items-center gap-2 border-b border-orange-200 p-4 dark:border-orange-900">
                    <span className="rounded-md bg-orange-500/10 px-2 py-0.5 text-xs font-medium text-orange-600 uppercase dark:text-orange-400">
                      Deviations
                    </span>
                  </div>
                  <div className="p-4">
                    <p className="text-foreground/90 text-sm leading-relaxed">
                      {entry.paivan_poikkeamat}
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Supervisor Observations */}
            {(entry.valvojan_huomiot || entry.valvojan_huomautukset) && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/10">
                    <FileText className="h-4 w-4 text-amber-600 dark:text-amber-500" />
                  </div>
                  <h3 className="text-lg font-semibold tracking-tight">
                    Supervisor Observations
                  </h3>
                </div>
                <div className="rounded-xl border border-amber-200 bg-amber-500/5 p-5 dark:border-amber-900">
                  {entry.valvojan_huomiot && (
                    <div className="mb-3">
                      <p className="text-muted-foreground mb-1 text-xs font-medium uppercase">
                        Observations
                      </p>
                      <p className="text-foreground/90 text-sm leading-relaxed">
                        {entry.valvojan_huomiot}
                      </p>
                    </div>
                  )}
                  {entry.valvojan_huomautukset && (
                    <div>
                      <p className="text-muted-foreground mb-1 text-xs font-medium uppercase">
                        Remarks
                      </p>
                      <p className="text-foreground/90 text-sm leading-relaxed">
                        {entry.valvojan_huomautukset}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Additional Fields */}
            {(() => {
              const knownKeys = [
                "kohde",
                "laatija",
                "paivamaara",
                "tyoviikko",
                "saa",
                "resurssit_henkilosto",
                "paivan_tyot_omat_tyot",
                "paivan_tapahtumat",
                "liitteet",
                "valvojan_huomiot",
                "paivan_poikkeamat",
                "aloitetut_tyovaiheet",
                "kaynnissa_olevat_tyovai",
                "paattyneet_tyovai",
                "keskeytyneet_tyovai",
                "pyydetyt_lisaajat",
                "tehdyt_katselmukset",
                "valvojan_huomautukset",
                "valvojan_allekirjoitus",
                "vastaavan_allekirjoitus",
              ];
              const otherKeys = Object.keys(entry).filter(
                (k) =>
                  !knownKeys.includes(k) &&
                  entry[k] !== null &&
                  entry[k] !== undefined &&
                  entry[k] !== "",
              );

              // Also include known keys that weren't displayed above
              const additionalKnown = [
                "liitteet",
                "pyydetyt_lisaajat",
                "tehdyt_katselmukset",
                "valvojan_allekirjoitus",
                "vastaavan_allekirjoitus",
              ].filter(
                (k) =>
                  entry[k] !== null &&
                  entry[k] !== undefined &&
                  entry[k] !== "",
              );

              const allAdditional = [...additionalKnown, ...otherKeys];
              if (allAdditional.length === 0) return null;

              return (
                <div className="space-y-4 border-t pt-6">
                  <h3 className="text-muted-foreground text-sm font-semibold tracking-wider uppercase">
                    Additional Details
                  </h3>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {allAdditional.map((key) => (
                      <div
                        key={key}
                        className="bg-muted/30 rounded-xl border p-4"
                      >
                        <p className="text-muted-foreground mb-2 text-xs font-bold tracking-wide uppercase">
                          {formatFieldName(key)}
                        </p>
                        <div className="text-sm font-medium">
                          {renderList(entry[key] as string | string[], "N/A")}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* Divider if multiple entries */}
            {index < data.length - 1 && (
              <hr className="border-muted my-8 border-dashed" />
            )}
          </div>
        );
      })}
    </div>
  );
}

function hasContent(content: unknown): boolean {
  if (!content) return false;
  if (Array.isArray(content)) return content.length > 0;
  if (typeof content === "string") return content.trim().length > 0;
  return true;
}

function formatFieldName(key: string): string {
  const fieldNames: Record<string, string> = {
    liitteet: "Attachments",
    pyydetyt_lisaajat: "Requested Extensions",
    tehdyt_katselmukset: "Completed Inspections",
    valvojan_allekirjoitus: "Supervisor Signature",
    vastaavan_allekirjoitus: "Manager Signature",
    kaynnissa_olevat_tyovai: "Ongoing Phases",
    paattyneet_tyovai: "Completed Phases",
  };
  return fieldNames[key] || key.replace(/_/g, " ");
}

function renderList(content: unknown, fallback: string, isChecklist = false) {
  if (!content)
    return <p className="text-muted-foreground text-sm italic">{fallback}</p>;

  if (Array.isArray(content)) {
    if (content.length === 0)
      return <p className="text-muted-foreground text-sm italic">{fallback}</p>;
    return (
      <ul className="space-y-3">
        {content.map((item, i) => (
          <li
            key={i}
            className="flex items-start gap-3 text-sm leading-relaxed"
          >
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

  return (
    <p className="text-foreground/90 text-sm leading-relaxed">
      {String(content)}
    </p>
  );
}
