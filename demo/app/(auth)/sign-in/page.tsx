"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { useAuthForm } from "../hooks/use-auth-form";
import { AuthShell } from "../components/auth-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel } from "@/components/ui/field";

export default function SignInPage() {
  const { isSubmitting, isDone, handleSubmit } = useAuthForm(900);

  return (
    <AuthShell
      title="Welcome back"
      description="Sign in to access the GAIK Toolkit demo workspace."
      footer={
        <>
          Need access?{" "}
          <Link href="/sign-up" className="text-white hover:underline">
            Request an invite
          </Link>
        </>
      }
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
        {isDone && (
          <Alert className="border-primary/20 bg-primary/5">
            <AlertTitle>Sign-in is almost ready</AlertTitle>
            <AlertDescription>
              Auth wiring is coming next. We will connect this flow to the
              database soon.
            </AlertDescription>
          </Alert>
        )}

        <Field>
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            required
            disabled={isSubmitting}
          />
        </Field>

        <Field>
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder="********"
            required
            disabled={isSubmitting}
          />
        </Field>

        <Button className="w-full" type="submit" disabled={isSubmitting}>
          {isSubmitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Signing in...
            </>
          ) : (
            "Sign in"
          )}
        </Button>

        <p className="text-center text-xs text-muted-foreground">
          Demo access is reviewed manually. We will notify you by email.
        </p>
      </form>
    </AuthShell>
  );
}
