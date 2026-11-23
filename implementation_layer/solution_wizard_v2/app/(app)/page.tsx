import { StartView } from "@/components/start-view";
import { getI18n } from "@/lib/i18n";

/**
 * The start: one field. A session is created by the first message sent from
 * here (app/actions.ts), so nothing exists before the user has said what they
 * want to solve. The user's earlier sessions are in the sidebar beside it.
 */
export default async function StartPage() {
  const { t } = await getI18n();
  return (
    <main
      id="main-content"
      className="scroll-thin relative flex min-h-0 flex-1 flex-col overflow-y-auto bg-surface"
    >
      <StartView
        labels={{
          panel: t.chatActivity.panel,
          inputLabel: t.chatInputLabel,
          send: t.chatSend,
          aiNotice: t.chatAiNotice,
          tooLong: t.chatErrors.tooLong,
          failed: t.startFailed,
          sessionLimit: t.sessionLimit,
        }}
      />
    </main>
  );
}
