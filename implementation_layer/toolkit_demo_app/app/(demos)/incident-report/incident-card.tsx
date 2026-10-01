"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  NotFound,
  ValueView,
} from "@/components/demo/extraction/extraction-results";
import type { RecordCardProps } from "@/components/demo/extraction/config";
import {
  hasContent,
  isSeverityKey,
  labelOf,
  severityOf,
  valueStrings,
  type Tone,
} from "@/components/demo/extraction/format";
import { cn } from "@/lib/utils";
import { AlertTriangle, Calendar, Clock, MapPin } from "lucide-react";

const TONE_CLASSES: Record<Tone, string> = {
  low: "border-green-300 bg-green-50 text-green-800",
  medium: "border-amber-300 bg-amber-50 text-amber-800",
  high: "border-orange-300 bg-orange-100 text-orange-900",
  critical: "border-red-300 bg-red-100 text-red-900",
};

const WHEN_KEY = /^(incident_)?(date|time|datetime)$/i;
const WHERE_KEY = /^(incident_)?location$/i;
const WHAT_KEY = /^(incident_|brief_)?description$/i;

export function IncidentCard({
  report,
  index,
  total,
  active,
  onPick,
}: RecordCardProps) {
  // Every field of the schema is shown, also those that the report did not mention.
  const keys = Object.keys(report);
  const filled = keys.filter((key) => hasContent(report[key])).length;
  const when = keys.filter((key) => WHEN_KEY.test(key));
  const where = keys.filter((key) => WHERE_KEY.test(key));
  const what = keys.find((key) => WHAT_KEY.test(key));
  const severityKey = keys.find(isSeverityKey);
  const tone = severityKey ? severityOf(report[severityKey]) : null;
  const shown = new Set([...when, ...where, what, severityKey]);
  const rest = keys.filter((key) => !shown.has(key));

  return (
    <Card className="overflow-hidden shadow-sm">
      <div className="bg-muted/40 flex flex-wrap items-center gap-2 border-b px-5 py-3">
        <AlertTriangle className="size-4 text-amber-500" />
        <h4 className="font-semibold">
          {total > 1 ? `Incident ${index + 1} of ${total}` : "Incident"}
        </h4>
        <span className="text-muted-foreground ml-auto text-xs">
          {filled} of {keys.length} fields found
        </span>
        {severityKey && (
          <Badge
            variant="outline"
            className={cn(
              tone && TONE_CLASSES[tone],
              !tone && "text-muted-foreground",
            )}
          >
            {labelOf(severityKey)}:{" "}
            {valueStrings(report[severityKey])[0] ?? "not found"}
          </Badge>
        )}
      </div>
      <CardContent className="space-y-4 p-5">
        {(when.length > 0 || where.length > 0) && (
          <div className="flex flex-wrap gap-2">
            {when.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => onPick(valueStrings(report[key])[0] ?? "")}
                className="bg-card hover:border-primary/60 flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm"
              >
                {/time/i.test(key) && !/date/i.test(key) ? (
                  <Clock className="text-primary size-4" />
                ) : (
                  <Calendar className="text-primary size-4" />
                )}
                {hasContent(report[key]) ? (
                  valueStrings(report[key]).join(" ")
                ) : (
                  <NotFound label={labelOf(key)} />
                )}
              </button>
            ))}
            {where.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => onPick(valueStrings(report[key])[0] ?? "")}
                className="bg-card hover:border-primary/60 flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm"
              >
                <MapPin className="text-primary size-4" />
                {hasContent(report[key]) ? (
                  valueStrings(report[key]).join(" ")
                ) : (
                  <NotFound label={labelOf(key)} />
                )}
              </button>
            ))}
          </div>
        )}

        {what && (
          <div>
            <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
              {labelOf(what)}
            </p>
            {hasContent(report[what]) ? (
              <ValueView value={report[what]} active={active} onPick={onPick} />
            ) : (
              <NotFound />
            )}
          </div>
        )}

        {rest.length > 0 && (
          <dl className="divide-y rounded-lg border">
            {rest.map((key) => (
              <div
                key={key}
                className="grid gap-1 px-3 py-2 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-3"
              >
                <dt className="text-muted-foreground text-sm font-medium">
                  {labelOf(key)}
                </dt>
                <dd>
                  {hasContent(report[key]) ? (
                    <ValueView
                      value={report[key]}
                      active={active}
                      onPick={onPick}
                    />
                  ) : (
                    <NotFound />
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
