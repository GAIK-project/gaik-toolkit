"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useRef, useState, type ReactNode } from "react";

export interface ConfirmRequest {
  /** The question, naming what is about to happen: "Load the example?" */
  title: string;
  /** What going on replaces or removes. */
  description: string;
  /** The button that goes on: "Load example". */
  action: string;
}

/**
 * Asks before a result on the page is replaced, in a dialog of the page.
 *
 * It stands in for window.confirm, which stops the page's main thread until it is
 * answered. A tab in the background cannot show that dialog, and a browser-driving agent
 * does not see it, so the page then answers nothing: no clicks, no reads, no screenshots.
 *
 * Render `confirmDialog` once in the page. `confirm` resolves to true when the user goes
 * on, and to false on Cancel, Escape or a second question asked meanwhile.
 */
export function useConfirm(): {
  confirm: (request: ConfirmRequest) => Promise<boolean>;
  confirmDialog: ReactNode;
} {
  // The request stays after the answer, so the text does not empty while the dialog closes.
  const [request, setRequest] = useState<ConfirmRequest | null>(null);
  const [open, setOpen] = useState(false);
  const answer = useRef<((ok: boolean) => void) | null>(null);
  // What had the focus when the question was asked: it gets the focus back on Cancel.
  const asker = useRef<HTMLElement | null>(null);

  function settle(ok: boolean) {
    answer.current?.(ok);
    answer.current = null;
    setOpen(false);
  }

  function confirm(next: ConfirmRequest): Promise<boolean> {
    return new Promise((resolve) => {
      answer.current?.(false);
      answer.current = resolve;
      asker.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      setRequest(next);
      setOpen(true);
    });
  }

  const confirmDialog = (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) settle(false);
      }}
    >
      <AlertDialogContent
        onCloseAutoFocus={(event) => {
          // The dialog has no trigger of its own to return the focus to.
          event.preventDefault();
          asker.current?.focus();
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>{request?.title}</AlertDialogTitle>
          <AlertDialogDescription>
            {request?.description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={() => settle(true)}>
            {request?.action}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return { confirm, confirmDialog };
}
