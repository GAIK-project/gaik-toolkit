import { redirect } from "next/navigation";
import { signOut } from "../actions";
import { getAccessStatus } from "@/data/auth";
import { AuthShell } from "../components/auth-shell";
import { Button } from "@/components/ui/button";
import { SuccessAnimation } from "../components/success-animation";
import { AccessPolling } from "../components/access-polling";

export default async function AccessPendingPage() {
  const { isLoggedIn, status, email } = await getAccessStatus();

  // Redirect to sign-in if not logged in
  if (!isLoggedIn) {
    redirect("/sign-in");
  }

  // Redirect to demo if already approved
  if (status === "approved") {
    redirect("/classifier");
  }

  return (
    <AuthShell
      title="Access pending"
      description="Your request is being reviewed by our team."
    >
      <div className="space-y-6 text-center">
        <SuccessAnimation />
        <AccessPolling />

        <div className="space-y-2">
          <p className="text-muted-foreground text-sm">
            We received your access request for
          </p>
          <p className="font-medium">{email}</p>
        </div>

        <p className="text-muted-foreground text-sm">
          We review requests manually to ensure quality access. You will receive
          an email once your request has been processed.
        </p>

        <form action={signOut}>
          <Button variant="outline" className="w-full" type="submit">
            Sign out
          </Button>
        </form>
      </div>
    </AuthShell>
  );
}
