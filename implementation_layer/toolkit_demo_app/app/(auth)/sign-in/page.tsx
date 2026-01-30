"use client";

import Link from "next/link";
import { useActionState } from "react";
import { Loader2 } from "lucide-react";
import { signIn, type AuthResult } from "../actions";
import { AuthShell } from "../components/auth-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel } from "@/components/ui/field";

const initialState: AuthResult = {};

export default function SignInPage() {
  const [state, formAction, isPending] = useActionState(signIn, initialState);

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
      <form className="space-y-5" action={formAction}>
        {state.error && (
          <Alert variant="destructive">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{state.error}</AlertDescription>
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
            disabled={isPending}
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
            disabled={isPending}
          />
        </Field>

        <Button className="w-full" type="submit" disabled={isPending}>
          {isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Signing in...
            </>
          ) : (
            "Sign in"
          )}
        </Button>

        <p className="text-muted-foreground text-center text-xs">
          Demo access is reviewed manually. We will notify you by email.
        </p>
      </form>
    </AuthShell>
  );
}
