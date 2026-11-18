"use client";

import { WORKSPACE_SHOW_EVENT, type WorkspacePlace } from "@/lib/chat-events";
import { Icon } from "./icons";

/**
 * A button in a notice that takes the user to the place in the workspace the
 * notice is about (WORKSPACE_SHOW_EVENT), so the notice does not have to tell
 * them where to go and look.
 */
export function ShowInWorkspaceButton({ place, label }: { place: WorkspacePlace; label: string }) {
  return (
    <button
      type="button"
      data-testid={`show-${place}`}
      onClick={() => window.dispatchEvent(new CustomEvent<WorkspacePlace>(WORKSPACE_SHOW_EVENT, { detail: place }))}
      className="btn-inline"
    >
      <Icon name="play" size={14} />
      {label}
    </button>
  );
}
