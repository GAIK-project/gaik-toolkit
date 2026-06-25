"use client";

import { useId, useState } from "react";
import type { Blueprint, BlueprintStepType } from "@/lib/mock-sessions";
import type { Dict } from "@/lib/i18n";

const TYPE_STYLE: Record<BlueprintStepType, string> = {
  io: "bg-surface-muted/50 backdrop-blur-sm text-text-secondary border-border border-l-4 border-l-step-io",
  ai: "bg-surface-muted/50 backdrop-blur-sm text-text-secondary border-border border-l-4 border-l-step-ai",
  human_review:
    "bg-surface-muted/50 backdrop-blur-sm text-text-secondary border-border border-l-4 border-l-step-human",
};

type Tab = "flow" | "json" | "poc";
type PocStatus = "idle" | "running" | "success" | "failed";

const TABS: Tab[] = ["flow", "json", "poc"];

export function WorkspacePanel({
  sessionId,
  blueprint,
  t,
}: {
  sessionId: string;
  blueprint: Blueprint;
  t: Dict;
}) {
  const [tab, setTab] = useState<Tab>("flow");
  const [logs, setLogs] = useState<string[]>([]);
  const [pocStatus, setPocStatus] = useState<PocStatus>("idle");
  const baseId = useId();

  const tabLabels: Record<Tab, string> = {
    flow: t.wsTabFlow,
    json: t.wsTabJson,
    poc: t.wsTabPoc,
  };

  const typeLabel: Record<BlueprintStepType, string> = {
    io: t.wsStepIo,
    ai: t.wsStepAi,
    human_review: t.wsStepHuman,
  };

  async function runPoc() {
    setPocStatus("running");
    setLogs([]);
    try {
      const res = await fetch(`/api/sessions/${sessionId}/poc`, {
        method: "POST",
      });
      if (!res.ok || !res.body) throw new Error("poc failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const line = frame.startsWith("data: ") ? frame.slice(6) : frame;
          if (!line.trim()) continue;
          const evt = JSON.parse(line);
          if (evt.log) setLogs((prev) => [...prev, evt.log]);
          if (evt.done)
            setPocStatus(evt.status === "success" ? "success" : "failed");
        }
      }
    } catch {
      setPocStatus("failed");
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div
        role="tablist"
        aria-label={t.workspace}
        className="shrink-0 mb-4 inline-flex items-center gap-0.5 rounded-lg bg-surface-muted border border-border p-0.5"
      >
        {TABS.map((key) => {
          const tabId = `${baseId}-tab-${key}`;
          const panelId = `${baseId}-panel-${key}`;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              id={tabId}
              aria-selected={tab === key}
              aria-controls={panelId}
              onClick={() => setTab(key)}
              className={tab === key ? "tab-btn-active" : "tab-btn-inactive"}
            >
              {tabLabels[key]}
            </button>
          );
        })}
      </div>

      {TABS.map((key) => {
        const tabId = `${baseId}-tab-${key}`;
        const panelId = `${baseId}-panel-${key}`;
        return (
          <div
            key={key}
            role="tabpanel"
            id={panelId}
            aria-labelledby={tabId}
            hidden={tab !== key}
            className="flex-1 min-h-0"
          >
            {key === "flow" && (
              <div className="h-full overflow-auto">
                {blueprint.goal && (
                  <p className="text-sm leading-relaxed text-text-secondary mb-4">
                    <span className="font-medium text-text-strong">
                      {t.wsBlueprintGoal}:
                    </span>{" "}
                    {blueprint.goal}
                  </p>
                )}
                <ol>
                  {blueprint.steps.map((s, i) => (
                    <li key={s.id}>
                      <div
                        className={`rounded-lg border px-3 py-2.5 shadow-xs ${TYPE_STYLE[s.type]}`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium">{s.name}</span>
                          <span className="text-xs font-semibold uppercase tracking-wide opacity-70">
                            {typeLabel[s.type]}
                            {s.component ? ` · ${s.component}` : ""}
                          </span>
                        </div>
                        {s.description && (
                          <p className="text-xs opacity-80 mt-0.5">
                            {s.description}
                          </p>
                        )}
                      </div>
                      {i < blueprint.steps.length - 1 && (
                        <div className="mx-auto h-4 w-px bg-border" aria-hidden />
                      )}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {key === "json" && (
              <pre className="h-full overflow-auto rounded-lg bg-surface-muted border border-border p-3.5 font-mono text-xs leading-5 text-text-secondary whitespace-pre-wrap">
                {JSON.stringify(blueprint, null, 2)}
              </pre>
            )}

            {key === "poc" && (
              <div className="h-full flex flex-col min-h-0">
                <div className="shrink-0 flex items-center gap-3 mb-3">
                  <button
                    type="button"
                    onClick={runPoc}
                    disabled={pocStatus === "running"}
                    className="btn-brand"
                  >
                    {pocStatus === "running"
                      ? t.pocRunning
                      : logs.length > 0
                        ? t.pocRerun
                        : t.pocRun}
                  </button>
                  {pocStatus === "success" && (
                    <span className="badge-success">{t.pocSuccess}</span>
                  )}
                  {pocStatus === "failed" && (
                    <span className="badge bg-danger-bg border-danger-border text-danger-text">
                      {t.pocFailed}
                    </span>
                  )}
                </div>

                {logs.length === 0 && pocStatus === "idle" ? (
                  <p className="text-xs text-text-muted">{t.pocIdle}</p>
                ) : (
                  <div className="flex-1 min-h-0 flex flex-col">
                    <div className="h-7 flex items-center gap-1.5 px-3 bg-term-bar rounded-t-lg shrink-0">
                      <span className="h-2.5 w-2.5 rounded-full bg-white/15" aria-hidden />
                      <span className="h-2.5 w-2.5 rounded-full bg-white/15" aria-hidden />
                      <span className="h-2.5 w-2.5 rounded-full bg-white/15" aria-hidden />
                    </div>
                    <pre className="flex-1 overflow-auto bg-term-bg p-3.5 font-mono text-xs leading-5 text-term-text whitespace-pre-wrap rounded-b-lg ring-1 ring-inset ring-white/5">
                      {logs.map((log, i) => {
                        const lower = log.toLowerCase();
                        const isErr =
                          lower.includes("error") ||
                          lower.includes("fail") ||
                          lower.includes("✗");
                        const isOk =
                          lower.includes("success") ||
                          lower.includes("✓") ||
                          lower.includes(" ok");
                        const cls = isErr
                          ? "text-term-err"
                          : isOk
                            ? "text-term-ok"
                            : "text-term-muted";
                        return (
                          <div key={i} className={cls}>
                            <span className="text-term-accent select-none mr-2">
                              ›
                            </span>
                            {log}
                          </div>
                        );
                      })}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
