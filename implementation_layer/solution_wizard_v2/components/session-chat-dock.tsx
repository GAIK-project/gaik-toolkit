"use client";

import { useSyncExternalStore, type ComponentProps } from "react";
import { ChatDock } from "@/components/chat-dock";
import { gate3Waits, packageReadFor, resultStaleFor, subscribeResultStale } from "@/lib/poc-result-state";
import { GATE_STEPS } from "@/lib/wizard-state-machine";

/**
 * The session page's chat. The approval the wizard's reply carries is the same
 * decision as the bar's under the workspace, so it waits with it: Gate 3 is
 * not offered under a reply while the test result on the PoC tab is, or may
 * be, an earlier package's (lib/poc-result-state). The bar says why.
 */
export function SessionChatDock({
  packageChanged = false,
  ...props
}: ComponentProps<typeof ChatDock> & {
  /** As the page read it: the package has changed since the test run that passed. */
  packageChanged?: boolean;
}) {
  const resultStale = useSyncExternalStore(
    subscribeResultStale,
    () => resultStaleFor(props.sessionId),
    () => false,
  );
  const packageRead = useSyncExternalStore(
    subscribeResultStale,
    () => packageReadFor(props.sessionId),
    () => false,
  );
  const waits =
    props.gateAction?.gateStep === GATE_STEPS[2] &&
    gate3Waits({ stale: resultStale, packageRead }, packageChanged);
  return <ChatDock {...props} gateAction={waits ? undefined : props.gateAction} />;
}
