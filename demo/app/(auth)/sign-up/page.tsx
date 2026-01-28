"use client";

import Link from "next/link";
import { useActionState } from "react";
import { Loader2 } from "lucide-react";
import { signUp, type AuthResult } from "../actions";
import { AuthShell } from "../components/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, FieldLabel, FieldGroup } from "@/components/ui/field";
import { PrivacyDialog } from "../components/privacy-dialog";

const initialState: AuthResult = {};

export default function SignUpPage() {
  const [state, formAction, isPending] = useActionState(signUp, initialState);

  return (
    <AuthShell
      title="Request access"
      description="Tell us who you are and we will enable your GAIK Toolkit demo."
      footer={
        <>
          Already have access?{" "}
          <Link href="/sign-in" className="text-white hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form className="space-y-5" action={formAction}>
        {state.error && (
          <p className="text-destructive text-sm">{state.error}</p>
        )}

        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="name">Full name</FieldLabel>
            <Input
              id="name"
              name="name"
              type="text"
              autoComplete="name"
              placeholder="Ava Johnson"
              required
              disabled={isPending}
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="email">Work email</FieldLabel>
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="ava@company.com"
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
              autoComplete="new-password"
              placeholder="Create a password"
              required
              minLength={6}
              disabled={isPending}
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="company">
              Company <span className="text-muted-foreground">(optional)</span>
            </FieldLabel>
            <Input
              id="company"
              name="company"
              type="text"
              autoComplete="organization"
              placeholder="Company name"
              disabled={isPending}
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="use-case">
              Use case <span className="text-muted-foreground">(optional)</span>
            </FieldLabel>
            <Textarea
              id="use-case"
              name="useCase"
              placeholder="Tell us what you want to build with GAIK Toolkit."
              rows={3}
              className="max-h-32 resize-none overflow-y-auto"
              disabled={isPending}
            />
          </Field>
        </FieldGroup>

        <Button className="w-full" type="submit" disabled={isPending}>
          {isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Sending request...
            </>
          ) : (
            "Request access"
          )}
        </Button>

        <p className="text-muted-foreground text-center text-xs">
          By requesting access, you agree to our{" "}
          <PrivacyDialog>
            <button
              type="button"
              className="hover:text-foreground cursor-pointer underline"
            >
              Privacy Policy
            </button>
          </PrivacyDialog>
          .
        </p>
      </form>
    </AuthShell>
  );
}
