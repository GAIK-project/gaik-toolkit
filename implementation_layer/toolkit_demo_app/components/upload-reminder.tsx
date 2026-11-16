import Link from "next/link";
import { cn } from "@/lib/utils";

/** What not to upload to the demo. The privacy notice repeats it under Uploads. */
export const UPLOAD_REMINDER_TEXT =
  "Use synthetic or anonymised material. Do not upload special categories of personal data (such as health data), personal identity numbers, card or bank account numbers, passwords or keys, or real customer or confidential documents.";

/** Shown once by each upload box. Kept outside the box's label, so the link does not open the file picker. */
export function UploadReminder({ className }: { className?: string }) {
  return (
    <p
      data-testid="upload-reminder"
      className={cn("text-muted-foreground mt-2 text-xs", className)}
    >
      {UPLOAD_REMINDER_TEXT}{" "}
      <Link href="/privacy#uploads" className="hover:text-foreground underline">
        How uploads are handled
      </Link>
    </p>
  );
}
