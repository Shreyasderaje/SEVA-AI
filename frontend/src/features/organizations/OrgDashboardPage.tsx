/** Organization dashboard: verification banner + needs management (M3). */

import { Building2, CheckCircle2, Clock, Plus, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/form-controls";
import {
  changeNeedStatus,
  getMyOrganization,
  listMyNeeds,
  recordFulfilment,
} from "@/lib/organization-api";
import type { OrganizationApplication } from "@/types/organizations";
import type { Need } from "@/types/needs";

const STATUS_BADGES: Record<string, { variant: "warning" | "success" | "destructive" | "muted"; label: string }> = {
  pending_verification: { variant: "warning", label: "Pending verification" },
  verified: { variant: "success", label: "Verified" },
  rejected: { variant: "destructive", label: "Rejected" },
  suspended: { variant: "destructive", label: "Suspended" },
};

export function OrgDashboardPage() {
  const [organization, setOrganization] = useState<OrganizationApplication | null>(null);
  const [needs, setNeeds] = useState<Need[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fulfilTarget, setFulfilTarget] = useState<Need | null>(null);
  const [fulfilAmount, setFulfilAmount] = useState("");
  const [fulfilError, setFulfilError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    getMyOrganization()
      .then(setOrganization)
      .catch((err) => {
        // 404 = no application yet -> offer the application form.
        setOrganization(null);
        setError(err?.status === 404 ? null : "Could not load your organization.");
      });
    listMyNeeds({ page: 1, page_size: 50 })
      .then((page) => setNeeds(page.items))
      .catch(() => setNeeds([]));
  }, []);

  useEffect(load, [load]);

  const applyStatus = organization?.verification_status ?? null;

  const pauseOrResume = async (need: Need) => {
    try {
      const updated = await changeNeedStatus(
        need.id,
        need.status === "active" ? "paused" : "active",
      );
      setNeeds((current) =>
        current ? current.map((n) => (n.id === updated.id ? updated : n)) : current,
      );
      toast.success(need.status === "active" ? "Need paused" : "Need resumed");
    } catch {
      toast.error("Could not change the need status.");
    }
  };

  const closeNeed = async (need: Need) => {
    try {
      const updated = await changeNeedStatus(need.id, "closed");
      setNeeds((current) =>
        current ? current.map((n) => (n.id === updated.id ? updated : n)) : current,
      );
      toast.success("Need closed");
    } catch {
      toast.error("Could not close the need.");
    }
  };

  const submitFulfilment = async () => {
    if (!fulfilTarget) return;
    const quantity = Number(fulfilAmount);
    if (!Number.isFinite(quantity) || quantity <= 0) {
      setFulfilError("Enter a quantity greater than zero.");
      return;
    }
    try {
      const updated = await recordFulfilment(fulfilTarget.id, quantity);
      setNeeds((current) =>
        current ? current.map((n) => (n.id === updated.id ? updated : n)) : current,
      );
      setFulfilTarget(null);
      setFulfilAmount("");
      setFulfilError(null);
      toast.success("Fulfilled quantity recorded");
    } catch (err) {
      setFulfilError(err instanceof Error ? err.message : "Could not record fulfilment.");
    }
  };

  if (error) {
    return (
      <Card className="mx-auto max-w-md">
        <CardContent className="flex items-center justify-between gap-4 p-4">
          <p role="alert" className="text-sm text-destructive">{error}</p>
          <Button variant="outline" size="sm" onClick={load}>Retry</Button>
        </CardContent>
      </Card>
    );
  }

  if (!organization) {
    return (
      <div className="flex flex-col items-center gap-6 py-10">
        <Building2 className="h-10 w-10 text-muted-foreground" aria-hidden />
        <div className="text-center">
          <h1 className="text-xl font-semibold">No organization application yet</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Submit your organization for verification to publish needs and receive
            donation matches.
          </p>
        </div>
        <Button asChild size="lg">
          <Link to="/organization/apply">Start application</Link>
        </Button>
      </div>
    );
  }

  const badge = STATUS_BADGES[applyStatus ?? "pending_verification"];

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Building2 className="h-6 w-6 text-primary" aria-hidden /> {organization.name}
          </h1>
          <div className="mt-2">
            <Badge variant={badge.variant}>{badge.label}</Badge>
          </div>
        </div>
        {organization.verification_status === "verified" && (
          <Button asChild size="lg">
            <Link to="/organization/needs/new">
              <Plus aria-hidden /> Create need
            </Link>
          </Button>
        )}
      </div>

      {/* Verification banner */}
      {applyStatus === "pending_verification" && (
        <Card>
          <CardContent className="flex items-start gap-3 p-4">
            <Clock className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden />
            <div className="text-sm">
              <p className="font-medium">Your application is awaiting admin review.</p>
              <p className="mt-1 text-muted-foreground">
                Submitted {new Date(organization.created_at).toLocaleString()}. You will
                be able to publish needs once an admin verifies your organization.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
      {applyStatus === "rejected" && (
        <Card>
          <CardContent className="flex items-start gap-3 p-4">
            <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden />
            <div className="text-sm">
              <p className="font-medium text-destructive">
                Your application was rejected.
              </p>
              <p className="mt-1 text-muted-foreground">
                Reason: {organization.rejection_reason ?? "not given"}
              </p>
            </div>
          </CardContent>
        </Card>
      )}
      {applyStatus === "suspended" && (
        <Card>
          <CardContent className="flex items-start gap-3 p-4">
            <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden />
            <div className="text-sm">
              <p className="font-medium text-destructive">
                Your organization is suspended.
              </p>
              <p className="mt-1 text-muted-foreground">
                Reason: {organization.rejection_reason ?? "not given"}
              </p>
            </div>
          </CardContent>
        </Card>
      )}
      {applyStatus === "verified" && (
        <Card>
          <CardContent className="flex items-start gap-3 p-4">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden />
            <div className="text-sm">
              <p className="font-medium text-success">Organization verified.</p>
              <p className="mt-1 text-muted-foreground">
                You can publish needs and appear in donation matches.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Needs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your needs</CardTitle>
          <CardDescription>
            Active needs appear in donation matching for verified organizations.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {needs === null && (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          )}
          {needs !== null && needs.length === 0 && (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <p className="text-sm text-muted-foreground">No needs published yet.</p>
              {organization.verification_status === "verified" && (
                <Button asChild size="sm">
                  <Link to="/organization/needs/new">Create your first need</Link>
                </Button>
              )}
            </div>
          )}
          {needs !== null && needs.length > 0 && (
            <ul className="divide-y">
              {needs.map((need) => (
                <li key={need.id} className="flex flex-wrap items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/organization/needs/${need.id}/edit`}
                      className="font-medium hover:underline"
                    >
                      {need.title}
                    </Link>
                    <p className="text-xs text-muted-foreground">
                      {need.category_display_name} · {need.quantity_fulfilled}/
                      {need.quantity_required} {need.unit} fulfilled ·{" "}
                      {need.remaining_quantity} remaining
                    </p>
                  </div>
                  <Badge
                    variant={
                      need.status === "active"
                        ? "success"
                        : need.status === "fulfilled"
                          ? "muted"
                          : need.status === "paused"
                            ? "warning"
                            : "secondary"
                    }
                  >
                    {need.status}
                  </Badge>
                  {need.status !== "fulfilled" && need.status !== "closed" && (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setFulfilTarget(need)}
                      >
                        Record fulfilment
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => pauseOrResume(need)}
                      >
                        {need.status === "active" ? "Pause" : "Resume"}
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => closeNeed(need)}>
                        Close
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Fulfilment dialog */}
      <Dialog open={fulfilTarget !== null} onOpenChange={(open) => !open && setFulfilTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Record fulfilled quantity</DialogTitle>
            <DialogDescription>
              {fulfilTarget?.title} — {fulfilTarget?.remaining_quantity}{" "}
              {fulfilTarget?.unit} remaining.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Input
              type="number"
              step="any"
              min="0"
              aria-label="Fulfilled quantity"
              value={fulfilAmount}
              onChange={(event) => setFulfilAmount(event.target.value)}
            />
            {fulfilError && <p className="text-sm text-destructive">{fulfilError}</p>}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setFulfilTarget(null)}>
              Cancel
            </Button>
            <Button onClick={submitFulfilment}>Record</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
