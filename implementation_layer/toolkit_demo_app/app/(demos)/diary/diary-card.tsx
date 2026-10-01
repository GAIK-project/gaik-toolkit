"use client";

import type { RecordCardProps } from "@/components/demo/extraction/config";
import {
  NotFound,
  ValueView,
} from "@/components/demo/extraction/extraction-results";
import {
  hasContent,
  labelOf,
  valueStrings,
} from "@/components/demo/extraction/format";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  Building2,
  Calendar,
  CalendarDays,
  Cloud,
  HardHat,
  User,
  type LucideIcon,
} from "lucide-react";

// Names of the fields that become chips under the title, in Finnish too.
const HEADER_FIELDS: { key: RegExp; icon: LucideIcon; prefix?: string }[] = [
  { key: /^(diary_)?(date|p[äa]iv[äa]m[äa][äa]r[äa])$/i, icon: Calendar },
  {
    key: /^(work_?)?(week|week_number|ty[öo]viikko|viikko)$/i,
    icon: CalendarDays,
    prefix: "Week ",
  },
  { key: /^(project|project_name|site|kohde)$/i, icon: Building2 },
  { key: /^(author|laatija|kirjaaja)$/i, icon: User },
  { key: /^(weather|s[äa][äa])$/i, icon: Cloud },
];

/** One diary day: the header facts as chips, then every other field. */
export function DiaryCard({
  report,
  index,
  total,
  active,
  onPick,
}: RecordCardProps) {
  // Every field of the schema is shown, also those that the diary did not mention.
  const keys = Object.keys(report);
  const filled = keys.filter((key) => hasContent(report[key])).length;
  const header = HEADER_FIELDS.flatMap(({ key, icon, prefix }) => {
    const found = keys.find((name) => key.test(name));
    return found ? [{ key: found, icon, prefix }] : [];
  });
  const shown = new Set(header.map((item) => item.key));
  const rest = keys.filter((key) => !shown.has(key));

  return (
    <Card className="overflow-hidden shadow-sm">
      <div className="bg-muted/40 flex flex-wrap items-center gap-2 border-b px-5 py-3">
        <HardHat className="size-4 text-amber-500" />
        <h4 className="font-semibold">
          {total > 1 ? `Day ${index + 1} of ${total}` : "Diary entry"}
        </h4>
        <span className="text-muted-foreground ml-auto text-xs">
          {filled} of {keys.length} fields found
        </span>
      </div>
      <CardContent className="space-y-4 p-5">
        {header.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {header.map(({ key, icon: Icon, prefix }) => (
              <button
                key={key}
                type="button"
                onClick={() => onPick(valueStrings(report[key])[0] ?? "")}
                className={cn(
                  "bg-card hover:border-primary/60 flex items-center gap-2 rounded-lg border px-3 py-1.5 text-left text-sm",
                  !hasContent(report[key]) && "text-muted-foreground",
                )}
              >
                <Icon className="text-primary size-4 shrink-0" />
                {hasContent(report[key]) ? (
                  `${prefix ?? ""}${valueStrings(report[key]).join(" · ")}`
                ) : (
                  <NotFound label={labelOf(key)} />
                )}
              </button>
            ))}
          </div>
        )}

        {rest.length > 0 && (
          <dl className="divide-y rounded-lg border">
            {rest.map((key) => (
              <div
                key={key}
                className="grid gap-1 px-3 py-2 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-3"
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
