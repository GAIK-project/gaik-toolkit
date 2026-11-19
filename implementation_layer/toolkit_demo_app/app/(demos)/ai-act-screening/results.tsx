"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { BlurFade } from "@/components/ui/blur-fade";
import { BorderBeam } from "@/components/ui/border-beam";
import { NumberTicker } from "@/components/ui/number-ticker";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { downloadBlob } from "@/lib/download";
import { screeningToMarkdown } from "@/lib/ai-act-screening/export";
import {
  ACTION_STATUS,
  CONFIDENCE,
  type Citation,
  conditionText,
  FINDING_QUESTIONS,
  FINDING_STATUS,
  formatDate,
  isCurrentGap,
  type RiskClass,
  ROLES,
  ROUTE_LABEL,
  type Screening,
  type ScreeningAction,
  TIER_ORDER,
  TIERS,
} from "@/lib/ai-act-screening/types";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Download,
  FileJson,
  HelpCircle,
  Lightbulb,
  MessageSquare,
  RotateCcw,
  Scale,
  Quote,
} from "lucide-react";
import { motion } from "motion/react";
import { useMemo, useState } from "react";

const TIER_STYLE: Record<
  RiskClass,
  { rung: string; active: string; dot: string }
> = {
  unacceptable: {
    rung: "border-red-500/30",
    active: "border-red-500 bg-red-500/10 text-red-700 dark:text-red-300",
    dot: "bg-red-500",
  },
  high: {
    rung: "border-amber-500/30",
    active:
      "border-amber-500 bg-amber-500/10 text-amber-800 dark:text-amber-300",
    dot: "bg-amber-500",
  },
  limited: {
    rung: "border-sky-500/30",
    active: "border-sky-500 bg-sky-500/10 text-sky-800 dark:text-sky-300",
    dot: "bg-sky-500",
  },
  minimal: {
    rung: "border-emerald-500/30",
    active:
      "border-emerald-500 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300",
    dot: "bg-emerald-500",
  },
};

const TIER_BEAM: Record<RiskClass, string> = {
  unacceptable: "#ef4444",
  high: "#f59e0b",
  limited: "#0ea5e9",
  minimal: "#10b981",
};

const STATUS_STYLE: Record<string, string> = {
  in_place: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  partly: "bg-amber-500/10 text-amber-800 dark:text-amber-300",
  missing: "bg-red-500/10 text-red-700 dark:text-red-300",
  unknown: "bg-muted text-muted-foreground",
};

function Cites({ list }: { list?: Citation[] }) {
  if (!list?.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {list.map((c) => (
        <span
          key={`${c.instrument ?? "AI Act"}-${c.ref}`}
          className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium"
        >
          <Scale className="size-3" />
          {c.instrument && c.instrument !== "AI Act" ? `${c.instrument} ` : ""}
          {c.ref}
        </span>
      ))}
    </span>
  );
}

function TierLadder({ screening }: { screening: Screening }) {
  const { summary } = screening;
  const alt = new Map(
    (summary.alternatives ?? []).map((a) => [
      a.risk_class,
      conditionText(a.if),
    ]),
  );
  return (
    <ol className="space-y-2" aria-label="The four AI Act risk tiers">
      {TIER_ORDER.map((tier, i) => {
        const active = summary.risk_class === tier;
        const possible = alt.has(tier);
        const style = TIER_STYLE[tier];
        return (
          <motion.li
            key={tier}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.08 * i }}
            aria-current={active ? "true" : undefined}
            className={cn(
              "rounded-xl border px-4 py-3 transition-colors",
              active ? style.active : cn(style.rung, "opacity-70"),
              possible && !active && "border-dashed opacity-100",
            )}
          >
            <div className="flex items-center gap-2 text-sm font-semibold">
              <span className={cn("size-2.5 rounded-full", style.dot)} />
              {TIERS[tier].label}
              {active && (
                <Badge className="ml-auto" variant="default">
                  This use case
                </Badge>
              )}
              {possible && !active && (
                <Badge className="ml-auto" variant="outline">
                  Possible
                </Badge>
              )}
            </div>
            {(active || possible) && (
              <p className="mt-1.5 text-sm">
                {possible && !active ? `If ${alt.get(tier)}. ` : ""}
                {TIERS[tier].means}
              </p>
            )}
          </motion.li>
        );
      })}
    </ol>
  );
}

function Verdict({ screening }: { screening: Screening }) {
  const { summary } = screening;
  const tier = summary.risk_class;
  const headline =
    summary.outcome === "not_in_scope"
      ? "Outside the AI Act"
      : tier
        ? TIERS[tier].label
        : "Not yet determined";
  const style = tier ? TIER_STYLE[tier].active : "border-border bg-muted/40";
  const required = screening.actions.filter((a) => a.type === "required");
  const recommended = screening.actions.length - required.length;
  const gaps = screening.actions.filter((a) =>
    isCurrentGap(a, screening.screened_on),
  ).length;
  const beam = tier ? TIER_BEAM[tier] : "#94a3b8";
  return (
    <div
      className={cn("relative overflow-hidden rounded-2xl border p-5", style)}
    >
      <BorderBeam size={160} duration={8} colorFrom={beam} colorTo="#ffffff" />
      <p className="text-xs font-medium tracking-wide uppercase opacity-80">
        Preliminary result
      </p>
      <h2 className="mt-1 font-serif text-2xl font-semibold">{headline}</h2>
      <p className="mt-2 text-sm">{summary.one_line}</p>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs opacity-70">Your role</dt>
          <dd className="font-medium">{ROLES[summary.role].label}</dd>
        </div>
        <div>
          <dt className="text-xs opacity-70">How certain</dt>
          <dd className="font-medium">
            {CONFIDENCE[summary.confidence].label}
          </dd>
        </div>
        <div>
          <dt className="text-xs opacity-70">Stage</dt>
          <dd className="font-medium">
            {summary.mode === "planned" ? "Planned" : "In use"} ·{" "}
            {summary.lifecycle_stage}
          </dd>
        </div>
      </dl>
      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-current/15 pt-4">
        {[
          { n: required.length, label: "required actions" },
          { n: recommended, label: "recommendations" },
          { n: gaps, label: "current gaps" },
        ].map((x) => (
          <div key={x.label}>
            <p className="font-serif text-3xl leading-none font-semibold tabular-nums">
              <NumberTicker value={x.n} />
            </p>
            <p className="mt-1 text-xs opacity-70">{x.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

type ActionFilter = "all" | "required" | "recommended";

function Actions({ screening }: { screening: Screening }) {
  const existing = screening.summary.mode === "existing";
  const [filter, setFilter] = useState<ActionFilter>("all");
  const [route, setRoute] = useState<"all" | "system" | "organisation">("all");
  const [done, setDone] = useState<Set<number>>(new Set());

  const indexed = useMemo(
    () => screening.actions.map((a, i) => ({ a, i })),
    [screening.actions],
  );
  const required = indexed.filter(({ a }) => a.type === "required");
  const shown = indexed.filter(
    ({ a }) =>
      (filter === "all" || a.type === filter) &&
      (route === "all" || a.route === route),
  );
  const doneRequired = required.filter(({ i }) => done.has(i)).length;

  function toggle(i: number) {
    setDone((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  if (indexed.length === 0)
    return (
      <p className="text-muted-foreground text-sm">
        The screening lists no actions for this result.
      </p>
    );

  return (
    <div className="space-y-4">
      {required.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="font-medium">
              Required actions you have ticked off
            </span>
            <span className="text-muted-foreground">
              {doneRequired} of {required.length}
            </span>
          </div>
          <Progress value={(doneRequired / required.length) * 100} />
        </div>
      )}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filters">
        {(["all", "required", "recommended"] as const).map((f) => (
          <Button
            key={f}
            size="sm"
            variant={filter === f ? "default" : "outline"}
            onClick={() => setFilter(f)}
            className="rounded-full capitalize"
          >
            {f === "all" ? "All" : f}
          </Button>
        ))}
        <span className="bg-border mx-1 hidden w-px sm:block" />
        {(["all", "system", "organisation"] as const).map((r) => (
          <Button
            key={r}
            size="sm"
            variant={route === r ? "secondary" : "ghost"}
            onClick={() => setRoute(r)}
            className="rounded-full"
          >
            {r === "all"
              ? "Any route"
              : r === "system"
                ? "System change"
                : "Organisation"}
          </Button>
        ))}
      </div>
      <ul className="space-y-3">
        {shown.map(({ a, i }) => (
          <ActionCard
            key={i}
            action={a}
            existing={existing}
            screenedOn={screening.screened_on}
            checked={done.has(i)}
            onToggle={() => toggle(i)}
          />
        ))}
        {shown.length === 0 && (
          <li className="text-muted-foreground text-sm">
            No actions match these filters.
          </li>
        )}
      </ul>
    </div>
  );
}

function ActionCard({
  action: a,
  existing,
  screenedOn,
  checked,
  onToggle,
}: {
  action: ScreeningAction;
  existing: boolean;
  screenedOn: string;
  checked: boolean;
  onToggle: () => void;
}) {
  const gap = isCurrentGap(a, screenedOn);
  const required = a.type === "required";
  return (
    <li
      className={cn(
        "rounded-xl border p-4",
        gap && "border-red-500/40 bg-red-500/5",
        checked && "opacity-60",
      )}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          aria-label={`Mark done: ${a.action}`}
          className="accent-primary mt-1 size-4 shrink-0"
        />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={required ? "default" : "secondary"}>
              {required ? "Required" : "Recommended"}
            </Badge>
            {gap && <Badge variant="destructive">Current gap</Badge>}
            {required && existing && a.status && (
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  STATUS_STYLE[a.status],
                )}
              >
                {ACTION_STATUS[a.status]}
              </span>
            )}
            <span className="text-muted-foreground text-xs">
              {ROUTE_LABEL[a.route]}
            </span>
          </div>
          <p className={cn("font-medium", checked && "line-through")}>
            {a.action}
          </p>
          {a.reason && (
            <p className="text-muted-foreground text-sm">
              {a.reason} <em>This is a suggestion, not a legal requirement.</em>
            </p>
          )}
          {a.applies_from && (
            <p className="text-sm">
              <CalendarClock className="mr-1 inline size-3.5" />
              {a.applies_from <= screenedOn
                ? `In force since ${formatDate(a.applies_from)}`
                : `Applies from ${formatDate(a.applies_from)}`}
              {a.applies_to ? ` · applies to the ${a.applies_to}` : ""}
            </p>
          )}
          <Cites list={a.citations} />
          {a.status_evidence?.map((e) => (
            <blockquote
              key={e.quote}
              className="text-muted-foreground border-l-2 pl-3 text-sm italic"
            >
              “{e.quote}”
            </blockquote>
          ))}
        </div>
      </div>
    </li>
  );
}

function Timeline({ screening }: { screening: Screening }) {
  const items = [...screening.timeline].sort((x, y) =>
    x.date.localeCompare(y.date),
  );
  if (items.length === 0)
    return (
      <p className="text-muted-foreground text-sm">No dates apply here.</p>
    );
  return (
    <ol className="border-border relative ml-3 space-y-6 border-l">
      {items.map((t) => (
        <li key={`${t.date}-${t.what}`} className="pl-6">
          <span
            className={cn(
              "ring-background absolute -left-[7px] mt-1.5 size-3.5 rounded-full ring-4",
              t.status === "in_force" ? "bg-emerald-500" : "bg-amber-500",
            )}
          />
          <p className="text-sm font-semibold">{formatDate(t.date)}</p>
          <p className="text-sm">{t.what}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Badge variant={t.status === "in_force" ? "secondary" : "outline"}>
              {t.status === "in_force" ? "In force" : "Upcoming"}
            </Badge>
            <Cites list={t.citations} />
          </div>
        </li>
      ))}
    </ol>
  );
}

function Findings({ screening }: { screening: Screening }) {
  return (
    <Accordion type="multiple" className="rounded-xl border px-4">
      {screening.findings.map((f) => (
        <AccordionItem key={f.id} value={f.id}>
          <AccordionTrigger className="gap-3 text-left">
            <span className="flex flex-1 flex-wrap items-center gap-2">
              <span className="text-sm font-medium">
                {FINDING_QUESTIONS[f.id] ?? f.question}
              </span>
              <Badge
                variant={f.status === "yes" ? "default" : "outline"}
                className="ml-auto"
              >
                {FINDING_STATUS[f.status]}
              </Badge>
            </span>
          </AccordionTrigger>
          <AccordionContent className="space-y-3">
            <p className="text-sm font-medium">{f.answer}</p>
            <p className="text-sm">{f.reasoning}</p>
            {f.evidence.map((e) => (
              <blockquote
                key={e.quote}
                className="text-muted-foreground flex gap-2 border-l-2 pl-3 text-sm italic"
              >
                <Quote className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  “{e.quote}”
                  <span className="ml-1 not-italic opacity-70">
                    {e.source === "description"
                      ? "(your description)"
                      : e.source === "answer"
                        ? "(your answer)"
                        : `(${e.locator})`}
                  </span>
                </span>
              </blockquote>
            ))}
            <div className="flex flex-wrap items-center gap-2">
              <Cites list={f.citations} />
              <span className="text-muted-foreground text-xs">
                Confidence: {CONFIDENCE[f.confidence].label.toLowerCase()}
              </span>
            </div>
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}

function Change({ screening }: { screening: Screening }) {
  const { triggers, open_questions: open, adjacent } = screening;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel icon={Lightbulb} title="What would change the result">
        {triggers.length === 0 ? (
          <Empty />
        ) : (
          triggers.map((t) => (
            <li key={t.change} className="space-y-1">
              <p className="text-sm">
                If {t.change}, it would become{" "}
                <strong>{TIERS[t.would_become].label}</strong>.
              </p>
              <Cites list={t.citations} />
            </li>
          ))
        )}
      </Panel>
      <Panel icon={HelpCircle} title="Open questions">
        {open.length === 0 ? (
          <Empty />
        ) : (
          open.map((q) => (
            <li key={q} className="text-sm">
              {q}
            </li>
          ))
        )}
      </Panel>
      <Panel
        icon={Scale}
        title="Related rules to check"
        className="md:col-span-2"
      >
        {adjacent.length === 0 ? (
          <Empty />
        ) : (
          adjacent.map((a) => (
            <li key={a.flag} className="space-y-1">
              <p className="text-sm">{a.flag}</p>
              <Cites list={a.citations} />
            </li>
          ))
        )}
      </Panel>
    </div>
  );
}

function Empty() {
  return <li className="text-muted-foreground text-sm">Nothing to report.</li>;
}

function Panel({
  icon: Icon,
  title,
  children,
  className,
}: {
  icon: typeof Lightbulb;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-xl border p-4", className)}>
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Icon className="size-4" />
        {title}
      </h3>
      <ul className="space-y-3">{children}</ul>
    </section>
  );
}

export function ScreeningResults({
  screening,
  name,
  onBackToChat,
  onRestart,
}: {
  screening: Screening;
  name: string;
  onBackToChat: () => void;
  onRestart: () => void;
}) {
  const gaps = screening.actions.filter((a) =>
    isCurrentGap(a, screening.screened_on),
  );
  const required = screening.actions.filter((a) => a.type === "required");
  const slug =
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "screening";

  return (
    <div className="space-y-6" data-testid="screening-results">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground text-sm">
          Screening of <strong className="text-foreground">{name}</strong> ·{" "}
          {formatDate(screening.screened_on)}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onBackToChat}
            className="gap-1.5"
          >
            <MessageSquare className="size-3.5" />
            Back to the conversation
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() =>
              downloadBlob(
                screeningToMarkdown(screening, name),
                `ai-act-screening-${slug}.md`,
                "text/markdown",
              )
            }
          >
            <Download className="size-3.5" />
            Report (.md)
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() =>
              downloadBlob(
                JSON.stringify(screening, null, 2),
                `ai-act-screening-${slug}.json`,
                "application/json",
              )
            }
          >
            <FileJson className="size-3.5" />
            Data (.json)
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRestart}
            className="gap-1.5"
          >
            <RotateCcw className="size-3.5" />
            Screen another
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <BlurFade className="space-y-4">
          <Verdict screening={screening} />
          {gaps.length > 0 && (
            <div
              role="alert"
              className="flex gap-3 rounded-xl border border-red-500/40 bg-red-500/5 p-4 text-sm"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-red-600" />
              <div>
                <p className="font-semibold">
                  {gaps.length} current gap{gaps.length > 1 ? "s" : ""}
                </p>
                <ul className="mt-1 list-disc pl-4">
                  {gaps.map((g) => (
                    <li key={g.action}>{g.action}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
          {screening.summary.flags.art_6_3_exempt && (
            <p className="flex gap-2 rounded-xl border p-4 text-sm">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" />A high-risk
              exception applies, but the provider must still document why and
              register the system (Article 6(4) and Article 49(2)).
            </p>
          )}
          {screening.summary.flags.transparency_duties && (
            <p className="flex gap-2 rounded-xl border p-4 text-sm">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
              People must be told they deal with AI or AI-generated content
              (Article 50), whatever the tier.
            </p>
          )}
          <section className="rounded-xl border p-4">
            <h3 className="mb-1 text-sm font-semibold">What was assessed</h3>
            <p className="text-sm">{screening.summary.screened_use}</p>
          </section>
        </BlurFade>
        <BlurFade delay={0.15}>
          <TierLadder screening={screening} />
        </BlurFade>
      </div>

      <Tabs defaultValue="actions">
        <TabsList className="flex h-auto flex-wrap">
          <TabsTrigger value="actions">What to do</TabsTrigger>
          <TabsTrigger value="timeline">Dates</TabsTrigger>
          <TabsTrigger value="why">How we got here</TabsTrigger>
          <TabsTrigger value="change">What could change it</TabsTrigger>
        </TabsList>
        <TabsContent value="actions" className="pt-4">
          <Actions screening={screening} />
        </TabsContent>
        <TabsContent value="timeline" className="pt-4">
          <Timeline screening={screening} />
        </TabsContent>
        <TabsContent value="why" className="pt-4">
          <Findings screening={screening} />
        </TabsContent>
        <TabsContent value="change" className="pt-4">
          <Change screening={screening} />
        </TabsContent>
      </Tabs>

      <p className="text-muted-foreground text-xs">
        {screening.disclaimer} Based on a summary of the law checked on{" "}
        {formatDate(screening.reference_last_verified)}.
      </p>
    </div>
  );
}
