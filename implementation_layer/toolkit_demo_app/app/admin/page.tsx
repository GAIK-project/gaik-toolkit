"use client";

import {
  useActionState,
  useEffect,
  useMemo,
  useState,
  useTransition,
} from "react";
import {
  Loader2,
  Check,
  X,
  LogOut,
  Wand2,
  RotateCcw,
  Users,
  Clock,
  FileText,
  Coins,
  Search,
} from "lucide-react";
import {
  verifyAdminPassword,
  adminLogout,
  updateAccessStatus,
  setWizardAccess,
  resetReportUsage,
  setReportLimitOverride,
  getReportWriterMaxReports,
  type AdminResult,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Cap value the UI treats as "Unlimited" (mirrors the route handler / admin action).
const UNLIMITED = 1_000_000;

export type AccessRequest = {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  company: string | null;
  use_case: string | null;
  status: "pending" | "approved" | "rejected";
  wizard_access: boolean;
  reports_count: number;
  report_tokens_used: number;
  report_limit_override: number | null;
  last_report_at: string | null;
  created_at: string;
};

async function isAdminAuthenticated(): Promise<boolean> {
  const res = await fetch("/api/admin/auth", { credentials: "include" });
  const data = await res.json();
  return data.authenticated;
}

async function getAccessRequests(): Promise<AccessRequest[]> {
  const res = await fetch("/api/admin/requests", { credentials: "include" });
  if (!res.ok) return [];
  return res.json();
}

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

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Users;
  label: string;
  value: string | number;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="bg-muted rounded-md p-2">
          <Icon className="text-muted-foreground h-5 w-5" />
        </div>
        <div>
          <p className="text-2xl leading-none font-semibold">{value}</p>
          <p className="text-muted-foreground mt-1 text-xs">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function WizardAccessButton({
  request,
  onUpdate,
}: {
  request: AccessRequest;
  onUpdate: () => void;
}) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const granted = request.wizard_access;

  function toggle(): void {
    setError(null);
    startTransition(async () => {
      const result = await setWizardAccess(request.user_id, !granted);
      if (result.error) {
        setError(result.error);
      } else {
        onUpdate();
      }
    });
  }

  return (
    <div>
      <Button
        size="sm"
        variant={granted ? "default" : "outline"}
        onClick={toggle}
        disabled={isPending}
        title={
          granted
            ? "Revoke Solution Wizard access"
            : "Grant Solution Wizard access"
        }
      >
        {isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : granted ? (
          <>
            <Wand2 className="h-4 w-4" />
            Granted
          </>
        ) : (
          "Grant"
        )}
      </Button>
      {error && <p className="text-destructive mt-1 text-xs">{error}</p>}
    </div>
  );
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
      <td className="px-4 py-3">
        <WizardAccessButton request={request} onUpdate={onUpdate} />
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

/** Per-user Report Writer cap selector (Default / 25 / 100 / Unlimited). */
function LimitSelect({
  request,
  maxReports,
  onUpdate,
}: {
  request: AccessRequest;
  maxReports: number;
  onUpdate: () => void;
}) {
  const [isPending, startTransition] = useTransition();
  const override = request.report_limit_override;
  const current =
    override == null
      ? "default"
      : override >= UNLIMITED
        ? "unlimited"
        : String(override);
  // Surface a non-preset override (e.g. set via SQL) so the Select still shows it.
  const showCustom =
    override != null &&
    override < UNLIMITED &&
    override !== 25 &&
    override !== 100;

  function change(value: string): void {
    const mapped =
      value === "default"
        ? null
        : value === "unlimited"
          ? UNLIMITED
          : Number(value);
    startTransition(async () => {
      const result = await setReportLimitOverride(request.user_id, mapped);
      if (!result.error) onUpdate();
    });
  }

  return (
    <Select value={current} onValueChange={change} disabled={isPending}>
      <SelectTrigger className="h-8 w-[140px] text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="default">Default ({maxReports})</SelectItem>
        <SelectItem value="25">25</SelectItem>
        <SelectItem value="100">100</SelectItem>
        <SelectItem value="unlimited">Unlimited</SelectItem>
        {showCustom && (
          <SelectItem value={String(override)}>{override} (custom)</SelectItem>
        )}
      </SelectContent>
    </Select>
  );
}

function UsageRow({
  request,
  maxReports,
  onUpdate,
}: {
  request: AccessRequest;
  maxReports: number;
  onUpdate: () => void;
}) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const cap = request.report_limit_override ?? maxReports;
  const unlimited = cap >= UNLIMITED;
  const atLimit = !unlimited && request.reports_count >= cap;

  function reset(): void {
    setError(null);
    startTransition(async () => {
      const result = await resetReportUsage(request.user_id);
      if (result.error) setError(result.error);
      else onUpdate();
    });
  }

  return (
    <tr className="border-border/50 border-b">
      <td className="px-4 py-3 text-sm">{request.email}</td>
      <td className="px-4 py-3 text-sm">
        <span className={atLimit ? "text-destructive font-medium" : ""}>
          {request.reports_count} / {unlimited ? "∞" : cap}
        </span>
      </td>
      <td className="px-4 py-3">
        <LimitSelect
          request={request}
          maxReports={maxReports}
          onUpdate={onUpdate}
        />
      </td>
      <td className="px-4 py-3 text-sm">
        {request.report_tokens_used.toLocaleString()}
      </td>
      <td className="text-muted-foreground px-4 py-3 text-sm">
        {request.last_report_at
          ? new Date(request.last_report_at).toLocaleString()
          : "-"}
      </td>
      <td className="px-4 py-3">
        <Button
          size="sm"
          variant="outline"
          onClick={reset}
          disabled={isPending || request.reports_count === 0}
          title="Reset this user's report counter"
        >
          {isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <>
              <RotateCcw className="h-4 w-4" />
              Reset
            </>
          )}
        </Button>
        {error && <p className="text-destructive mt-1 text-xs">{error}</p>}
      </td>
    </tr>
  );
}

const TH =
  "text-muted-foreground px-4 py-3 text-left text-sm font-medium whitespace-nowrap";

function Dashboard() {
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [maxReports, setMaxReports] = useState(5);
  const [query, setQuery] = useState("");
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

  useEffect(() => {
    getReportWriterMaxReports().then(setMaxReports);
  }, []);

  function handleLogout(): void {
    startLogout(async () => {
      await adminLogout();
      window.location.reload();
    });
  }

  const stats = useMemo(() => {
    return {
      total: requests.length,
      pending: requests.filter((r) => r.status === "pending").length,
      reports: requests.reduce((n, r) => n + (r.reports_count || 0), 0),
      tokens: requests.reduce((n, r) => n + (r.report_tokens_used || 0), 0),
    };
  }, [requests]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return requests;
    return requests.filter(
      (r) =>
        r.email.toLowerCase().includes(q) ||
        (r.full_name || "").toLowerCase().includes(q),
    );
  }, [requests, query]);

  return (
    <div className="bg-background min-h-screen">
      <header className="border-b">
        <div className="container mx-auto flex items-center justify-between px-4 py-4">
          <div>
            <h1 className="text-xl font-semibold">GAIK Admin</h1>
            <p className="text-muted-foreground text-sm">
              Access requests &amp; Report Writer usage
            </p>
          </div>
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
        {/* Summary stats */}
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard icon={Users} label="Users" value={stats.total} />
          <StatCard icon={Clock} label="Pending" value={stats.pending} />
          <StatCard
            icon={FileText}
            label="Reports generated"
            value={stats.reports}
          />
          <StatCard
            icon={Coins}
            label="Tokens used"
            value={stats.tokens.toLocaleString()}
          />
        </div>

        {/* Search */}
        <div className="relative mb-4 max-w-sm">
          <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
          <Input
            placeholder="Filter by email or name…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        <Tabs defaultValue="requests">
          <TabsList className="mb-4">
            <TabsTrigger value="requests">Access Requests</TabsTrigger>
            <TabsTrigger value="usage">Report Writer Usage</TabsTrigger>
          </TabsList>

          <TabsContent value="requests">
            <Card>
              <CardHeader>
                <CardTitle>Access Requests</CardTitle>
                <CardDescription>
                  {stats.pending > 0
                    ? `${stats.pending} pending request${stats.pending > 1 ? "s" : ""}`
                    : "No pending requests"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
                  </div>
                ) : filtered.length === 0 ? (
                  <p className="text-muted-foreground py-8 text-center">
                    {requests.length === 0
                      ? "No access requests yet."
                      : "No users match your filter."}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className={TH}>Email</th>
                          <th className={TH}>Name</th>
                          <th className={TH}>Company</th>
                          <th className={TH}>Use Case</th>
                          <th className={TH}>Status</th>
                          <th className={TH}>Wizard</th>
                          <th className={TH}>Created</th>
                          <th className={TH}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((request) => (
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
          </TabsContent>

          <TabsContent value="usage">
            <Card>
              <CardHeader>
                <CardTitle>Report Writer Usage</CardTitle>
                <CardDescription>
                  Per-user report counts and token spend. Raise a user&apos;s
                  Limit (e.g. for demo/team accounts) or Reset their counter to
                  give the allowance back.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
                  </div>
                ) : filtered.length === 0 ? (
                  <p className="text-muted-foreground py-8 text-center">
                    {requests.length === 0
                      ? "No users yet."
                      : "No users match your filter."}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className={TH}>Email</th>
                          <th className={TH}>Reports</th>
                          <th className={TH}>Limit</th>
                          <th className={TH}>Tokens used</th>
                          <th className={TH}>Last report</th>
                          <th className={TH}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((request) => (
                          <UsageRow
                            key={request.id}
                            request={request}
                            maxReports={maxReports}
                            onUpdate={loadRequests}
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
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
