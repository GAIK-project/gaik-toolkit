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
  date?: string | null;
  time?: string | null;
  location?: string | null;
  description?: string | null;
  people_involved?: string[] | string | null;
  injuries?: string | null;
  damages?: string | null;
  actions_taken?: string[] | string | null;
  witnesses?: string[] | string | null;
  [key: string]: unknown;
}

interface IncidentDetailsProps {
  data: unknown[];
  className?: string;
}

export function IncidentDetails({ data, className }: IncidentDetailsProps) {
  if (!Array.isArray(data) || data.length === 0) return null;

  return (
    <div className={cn("space-y-8", className)}>
      {data.map((item, index) => {
        const report = item as IncidentReport;

        // Format date nicely if possible, use today as fallback
        let formattedDate: string;
        const dateFormatter = new Intl.DateTimeFormat("en-US", {
          dateStyle: "long",
        });

        if (report.date) {
          try {
            const d = new Date(report.date);
            formattedDate = !isNaN(d.getTime())
              ? dateFormatter.format(d)
              : dateFormatter.format(new Date());
          } catch {
            formattedDate = dateFormatter.format(new Date());
          }
        } else {
          // No date provided, use today as fallback
          formattedDate = dateFormatter.format(new Date());
        }

        return (
          <div key={index} className="space-y-6">
            {/* Header Section: Date, Time, Location */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="bg-card flex items-start space-x-4 rounded-xl border p-4 shadow-sm">
                <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                  <Calendar className="text-primary h-5 w-5" />
                </div>
                <div>
                  <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                    Date & Time
                  </p>
                  <p className="font-medium">{formattedDate}</p>
                  {report.time && (
                    <p className="text-muted-foreground text-sm">
                      {report.time}
                    </p>
                  )}
                </div>
              </div>
              <div className="bg-card flex items-start space-x-4 rounded-xl border p-4 shadow-sm">
                <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                  <MapPin className="text-primary h-5 w-5" />
                </div>
                <div>
                  <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                    Location
                  </p>
                  <p className="font-medium">{report.location || "N/A"}</p>
                </div>
              </div>
            </div>

            {/* Description */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="bg-primary/10 flex h-8 w-8 items-center justify-center rounded-lg">
                  <FileText className="text-primary h-4 w-4" />
                </div>
                <h3 className="text-lg font-semibold tracking-tight">
                  Incident Description
                </h3>
              </div>
              <div className="bg-muted/30 text-card-foreground rounded-xl border p-5 leading-relaxed shadow-sm">
                {report.description || "No description extraction."}
              </div>
            </div>

            {/* Details Grid */}
            <div className="grid gap-6 md:grid-cols-2">
              {/* People Involved */}
              <div className="bg-card rounded-xl border shadow-sm">
                <div className="flex items-center gap-2 border-b p-4">
                  <Users className="text-muted-foreground h-4 w-4" />
                  <h3 className="font-medium">People Involved</h3>
                </div>
                <div className="p-4">
                  {renderList(
                    report.people_involved,
                    "No extracted information.",
                  )}
                </div>
              </div>

              {/* Injuries & Damages */}
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
                    <div className="text-sm">
                      {report.injuries || "None reported."}
                    </div>
                  </div>
                  {report.damages && (
                    <div>
                      <div className="mb-2 flex items-center gap-2">
                        <span className="rounded-md bg-orange-500/10 px-2 py-0.5 text-xs font-medium text-orange-600 uppercase dark:text-orange-400">
                          Damages
                        </span>
                      </div>
                      <div className="text-sm">{report.damages}</div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Actions Taken */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-green-500/10">
                  <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-500" />
                </div>
                <h3 className="text-lg font-semibold tracking-tight">
                  Actions Taken
                </h3>
              </div>
              <div className="rounded-xl border border-green-200 bg-green-500/5 p-5 dark:border-green-900">
                {renderList(report.actions_taken, "No actions recorded.", true)}
              </div>
            </div>

            {/* Dynamic/Other Fields */}
            {(() => {
              const knownKeys = [
                "date",
                "time",
                "location",
                "description",
                "people_involved",
                "injuries",
                "damages",
                "actions_taken",
                "witnesses",
              ];
              const otherKeys = Object.keys(report).filter(
                (k) =>
                  !knownKeys.includes(k) &&
                  report[k] !== null &&
                  report[k] !== undefined,
              );

              if (otherKeys.length === 0) return null;

              return (
                <div className="space-y-4 border-t pt-6">
                  <h3 className="text-muted-foreground text-sm font-semibold tracking-wider uppercase">
                    Additional Details
                  </h3>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {otherKeys.map((key) => (
                      <div
                        key={key}
                        className="bg-muted/30 rounded-xl border p-4"
                      >
                        <p className="text-muted-foreground mb-2 text-xs font-bold tracking-wide uppercase">
                          {key.replace(/_/g, " ")}
                        </p>
                        <div className="text-sm font-medium">
                          {renderList(report[key] as string | string[], "N/A")}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* Divider if multiple reports (rare but possible) */}
            {index < data.length - 1 && (
              <hr className="border-muted my-8 border-dashed" />
            )}
          </div>
        );
      })}
    </div>
  );
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
