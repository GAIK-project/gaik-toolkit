"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { useAuthForm } from "../hooks/use-auth-form";
import { AuthShell } from "../components/auth-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, FieldLabel, FieldGroup } from "@/components/ui/field";

export default function SignUpPage() {
  const { isSubmitting, isDone, handleSubmit } = useAuthForm(1100);

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
      <form className="space-y-5" onSubmit={handleSubmit}>
        {isDone && (
          <Alert className="border-primary/20 bg-primary/5">
            <AlertTitle>Request received</AlertTitle>
            <AlertDescription>
              We will review your access request and reach out by email.
            </AlertDescription>
          </Alert>
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
              disabled={isSubmitting}
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
              disabled={isSubmitting}
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
              disabled={isSubmitting}
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
              disabled={isSubmitting}
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
              disabled={isSubmitting}
            />
          </Field>
        </FieldGroup>

        <Button className="w-full" type="submit" disabled={isSubmitting}>
          {isSubmitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Sending request...
            </>
          ) : (
            "Request access"
          )}
        </Button>

        <p className="text-center text-xs text-muted-foreground">
          By requesting access, you agree that we can contact you about GAIK
          Toolkit.
        </p>
      </form>
    </AuthShell>
  );
}
