"use client";

import { useActionState, useEffect, useState, useTransition } from "react";
import { Loader2, Check, X, LogOut } from "lucide-react";
import {
  verifyAdminPassword,
  isAdminAuthenticated,
  adminLogout,
  getAccessRequests,
  updateAccessStatus,
  type AdminResult,
  type AccessRequest,
} from "./actions";
import { AuthShell } from "../(auth)/components/auth-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";

const initialState: AdminResult = {};

function LoginForm() {
  const [state, formAction, isPending] = useActionState(
    verifyAdminPassword,
    initialState,
  );

  useEffect(() => {
    if (state.success) {
      window.location.reload();
    }
  }, [state.success]);

  return (
    <AuthShell
      title="Admin Access"
      description="Enter the admin password to manage access requests."
      variant="light"
    >
      <form className="space-y-5" action={formAction}>
        {state.error && (
          <Alert variant="destructive">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{state.error}</AlertDescription>
          </Alert>
        )}

        <Field>
          <FieldLabel htmlFor="password">Admin Password</FieldLabel>
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
              Verifying...
            </>
          ) : (
            "Sign in"
          )}
        </Button>
      </form>
    </AuthShell>
  );
}

function StatusBadge({ status }: { status: AccessRequest["status"] }) {
  const variants: Record<
    AccessRequest["status"],
    { variant: "default" | "secondary" | "destructive"; label: string }
  > = {
    pending: { variant: "secondary", label: "Pending" },
    approved: { variant: "default", label: "Approved" },
    rejected: { variant: "destructive", label: "Rejected" },
  };

  const { variant, label } = variants[status];
  return <Badge variant={variant}>{label}</Badge>;
}

function AccessRequestRow({
  request,
  onUpdate,
}: {
  request: AccessRequest;
  onUpdate: () => void;
}) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleAction(status: "approved" | "rejected"): void {
    setError(null);
    startTransition(async () => {
      const result = await updateAccessStatus(request.user_id, status);
      if (result.error) {
        setError(result.error);
      } else {
        onUpdate();
      }
    });
  }

  return (
    <tr className="border-border/50 border-b">
      <td className="px-4 py-3 text-sm">{request.email}</td>
      <td className="px-4 py-3 text-sm">{request.full_name}</td>
      <td className="px-4 py-3 text-sm">{request.company || "-"}</td>
      <td className="max-w-xs truncate px-4 py-3 text-sm">
        {request.use_case || "-"}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={request.status} />
      </td>
      <td className="text-muted-foreground px-4 py-3 text-sm">
        {new Date(request.created_at).toLocaleDateString()}
      </td>
      <td className="px-4 py-3">
        {request.status === "pending" && (
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="default"
              onClick={() => handleAction("approved")}
              disabled={isPending}
              title="Approve"
            >
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => handleAction("rejected")}
              disabled={isPending}
              title="Reject"
            >
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <X className="h-4 w-4" />
              )}
            </Button>
          </div>
        )}
        {error && <p className="text-destructive mt-1 text-xs">{error}</p>}
      </td>
    </tr>
  );
}

function Dashboard() {
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [loggingOut, startLogout] = useTransition();

  async function loadRequests(): Promise<void> {
    setLoading(true);
    try {
      const data = await getAccessRequests();
      setRequests(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRequests();
  }, []);

  function handleLogout(): void {
    startLogout(async () => {
      await adminLogout();
      window.location.reload();
    });
  }

  const pendingCount = requests.filter((r) => r.status === "pending").length;

  return (
    <div className="bg-background min-h-screen">
      <header className="border-b">
        <div className="container mx-auto flex items-center justify-between px-4 py-4">
          <h1 className="text-xl font-semibold">GAIK Admin</h1>
          <Button
            variant="outline"
            size="sm"
            onClick={handleLogout}
            disabled={loggingOut}
          >
            {loggingOut ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <LogOut className="h-4 w-4" />
            )}
            <span className="ml-2">Logout</span>
          </Button>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <Card>
          <CardHeader>
            <CardTitle>Access Requests</CardTitle>
            <CardDescription>
              {pendingCount > 0
                ? `${pendingCount} pending request${pendingCount > 1 ? "s" : ""}`
                : "No pending requests"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
              </div>
            ) : requests.length === 0 ? (
              <p className="text-muted-foreground py-8 text-center">
                No access requests yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b">
                      <th className="text-muted-foreground px-4 py-3 text-left text-sm font-medium">
                        Email
                      </th>
                      <th className="text-muted-foreground px-4 py-3 text-left text-sm font-medium">
                        Name
                      </th>
                      <th className="text-muted-foreground px-4 py-3 text-left text-sm font-medium">
                        Company
                      </th>
                      <th className="text-muted-foreground px-4 py-3 text-left text-sm font-medium">
                        Use Case
                      </th>
                      <th className="text-muted-foreground px-4 py-3 text-left text-sm font-medium">
                        Status
                      </th>
                      <th className="text-muted-foreground px-4 py-3 text-left text-sm font-medium">
                        Created
                      </th>
                      <th className="text-muted-foreground px-4 py-3 text-left text-sm font-medium">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {requests.map((request) => (
                      <AccessRequestRow
                        key={request.id}
                        request={request}
                        onUpdate={loadRequests}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

export default function AdminPage() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    isAdminAuthenticated().then(setIsAuthenticated);
  }, []);

  if (isAuthenticated === null) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginForm />;
  }

  return <Dashboard />;
}
