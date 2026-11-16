"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { Icon } from "@/components/icons";
import { runWarningsFor, subscribeResultStale } from "@/lib/poc-result-state";

/**
 * The finished solution's banner: the heading, the two things to do with the
 * solution and what the package leaves out.
 *
 * It is drawn here, not by the page, because of one thing the page cannot
 * know: whether the run the workspace shows finished with warnings. The page
 * has the run's id and not its output; the workspace under the banner reads
 * the output and says here what it found. With warnings the banner agrees
 * with the workspace: the warning tone in place of the success box, the line
 * about them first, and trying the solution ahead of taking the package.
 * The server draws it without warnings, so a session that has none is never
 * shown the other order.
 */
export function SolutionDoneBanner({
  sessionId,
  hasRun,
  labels,
  children,
}: {
  sessionId: string;
  /** wizard_api has a successful run on record: there is a package to take. */
  hasRun: boolean;
  labels: {
    title: string;
    download: string;
    tryCases: string;
    packageLine: string;
    warningsLine: string;
    noRun: string;
  };
  children?: ReactNode;
}) {
  const told = useSyncExternalStore(
    subscribeResultStale,
    () => runWarningsFor(sessionId),
    () => false,
  );
  const warnings = told && hasRun;
  const download = (
    <a
      href={`/api/sessions/${sessionId}/poc/deployable`}
      download
      className={warnings ? "btn-secondary" : "btn-brand"}
      data-testid="solution-done-download"
    >
      <Icon name="download" size={16} />
      {labels.download}
    </a>
  );
  const tryCases = (
    <a
      href={`/sessions/${sessionId}/cases`}
      className={warnings ? "btn-brand" : "btn-secondary"}
      data-testid="solution-done-try"
    >
      <Icon name="users" size={16} />
      {labels.tryCases}
    </a>
  );
  return (
    <section
      role="status"
      aria-labelledby="solution-done-title"
      data-testid="solution-done"
      data-tone={warnings ? "warning" : "success"}
      className={`mx-4 mt-4 shrink-0 rounded-lg border px-4 py-3 sm:mx-6 ${
        warnings ? "border-warning-border bg-warning-bg" : "border-success-border bg-success-bg"
      }`}
    >
      <h3 id="solution-done-title" className="flex items-center gap-2 text-sm font-semibold text-text">
        <Icon
          name={warnings ? "circleAlert" : "circleCheck"}
          size={18}
          className={`shrink-0 ${warnings ? "text-warning-text" : "text-success-text"}`}
        />
        {labels.title}
      </h3>
      {warnings && (
        <p className="mt-1 text-sm text-text" data-testid="solution-done-warnings">
          {labels.warningsLine}
        </p>
      )}
      {hasRun ? (
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-2">
          {warnings ? tryCases : download}
          {warnings ? download : tryCases}
          <p className="text-xs text-text-secondary">{labels.packageLine}</p>
        </div>
      ) : (
        <p className="mt-1 text-sm text-text-secondary">{labels.noRun}</p>
      )}
      {children}
    </section>
  );
}
