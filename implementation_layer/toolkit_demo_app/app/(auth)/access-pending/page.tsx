import { redirect } from "next/navigation";
import { signOut } from "@/app/(auth)/actions";
import { getAccessStatus } from "@/data/auth";
import { AuthShell } from "../components/auth-shell";
import { Button } from "@/components/ui/button";
import dynamic from "next/dynamic";
import { AccessPolling } from "../components/access-polling";

const SuccessAnimation = dynamic(() =>
  import("../components/success-animation").then(
    (mod) => mod.SuccessAnimation,
  ),
);

export default async function AccessPendingPage() {
  const { isLoggedIn, status, email } = await getAccessStatus();

  // Redirect to sign-in if not logged in
  if (!isLoggedIn) {
    redirect("/sign-in");
  }

  // Redirect to home if already approved
  if (status === "approved") {
    redirect("/");
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
          Your request will be reviewed shortly. We'll send you an email when
          your access has been approved.
        </p>

        <form action={signOut}>
          <Button variant="outline" className="w-full" type="submit">
            Sign out and return later
          </Button>
        </form>
      </div>
    </AuthShell>
  );
}
