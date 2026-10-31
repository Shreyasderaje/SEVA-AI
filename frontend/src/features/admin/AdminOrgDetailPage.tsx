/** Admin: organization application review — document, approve/reject/suspend. */

import { CheckCircle2, FileText, ShieldAlert, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
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
import { Skeleton, Textarea } from "@/components/ui/form-controls";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import {
  adminGetOrganization,
  adminRejectOrganization,
  adminSuspendOrganization,
  adminVerifyOrganization,
} from "@/lib/organization-api";
import type { AdminOrganizationDetail } from "@/types/organizations";

type Decision = "verify" | "reject" | "suspend";

export function AdminOrgDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [organization, setOrganization] = useState<AdminOrganizationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Decision | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!id) return;
    adminGetOrganization(id)
      .then(setOrganization)
      .catch(() => setError("Organization not found."));
  }, [id]);

  if (error) {
    return (
      <Card className="mx-auto max-w-md">
        <CardContent className="flex items-start gap-3 p-4">
          <ShieldAlert className="mt-0.5 h-5 w-5 text-destructive" aria-hidden />
          <p className="text-sm text-destructive">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!organization) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const submit = async () => {
    if (!id) return;
    if (dialog !== "verify" && reason.trim().length < 3) {
      setReasonError("A reason is required for rejection or suspension.");
      return;
    }
    setBusy(true);
    try {
      const updated =
        dialog === "verify"
          ? await adminVerifyOrganization(id)
          : dialog === "reject"
            ? await adminRejectOrganization(id, reason.trim())
            : await adminSuspendOrganization(id, reason.trim());
      setOrganization(updated);
      toast.success(`Organization ${updated.verification_status.replace("_", " ")}`);
      setDialog(null);
      setReason("");
      setReasonError(null);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Decision failed.");
    } finally {
      setBusy(false);
    }
  };

  const openDecision = (decision: Decision) => {
    setReason("");
    setReasonError(null);
    setDialog(decision);
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs text-muted-foreground">Organization application</p>
          <h1 className="text-2xl font-semibold tracking-tight">{organization.name}</h1>
        </div>
        <Badge
          variant={
            organization.verification_status === "verified"
              ? "success"
              : organization.verification_status === "pending_verification"
                ? "warning"
                : "destructive"
          }
        >
          {organization.verification_status.replace("_", " ")}
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Application details</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <Row label="Type">{organization.org_type ?? "—"}</Row>
          <Row label="Description">{organization.description ?? "—"}</Row>
          <Row label="Address">{organization.address ?? "—"}</Row>
          <Row label="Contact email">{organization.contact_email ?? "—"}</Row>
          <Row label="Contact phone">{organization.contact_phone ?? "—"}</Row>
          <Row label="Representative">{organization.representative_name ?? "—"}</Row>
          <Row label="Coordinates">
            {organization.latitude !== null
              ? `${organization.latitude.toFixed(5)}, ${organization.longitude?.toFixed(5)} (stored with consent)`
              : "Not provided"}
          </Row>
          <Row label="Applied">{new Date(organization.created_at).toLocaleString()}</Row>
          {organization.rejection_reason && (
            <Row label="Previous reason">{organization.rejection_reason}</Row>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4 text-primary" aria-hidden /> Verification document
          </CardTitle>
          <CardDescription>
            Accessible only to admins and the owning organization — never public.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {organization.document_url ? (
            <a
              href={organization.document_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
            >
              <FileText className="h-4 w-4" aria-hidden /> Open document (authorized link)
            </a>
          ) : (
            <p className="text-sm text-muted-foreground">No document on file.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Verification decision</CardTitle>
          <CardDescription>
            Only admins can change verification status; every decision is recorded
            in the audit log.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button onClick={() => openDecision("verify")}>
            <CheckCircle2 aria-hidden /> Approve
          </Button>
          <Button variant="destructive" onClick={() => openDecision("reject")}>
            <XCircle aria-hidden /> Reject
          </Button>
          <Button variant="outline" onClick={() => openDecision("suspend")}>
            Suspend
          </Button>
        </CardContent>
      </Card>

      <Dialog
        open={dialog !== null}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {dialog === "verify"
                ? "Approve this organization?"
                : dialog === "reject"
                  ? "Reject this organization?"
                  : "Suspend this organization?"}
            </DialogTitle>
            <DialogDescription>
              {dialog === "verify"
                ? `${organization.name} will be verified and can publish needs and receive matches.`
                : `${organization.name} will be marked ${dialog}. A clear reason is required and shown to the organization.`}
            </DialogDescription>
          </DialogHeader>
          {dialog !== null && dialog !== "verify" && (
            <div className="flex flex-col gap-2">
              <Label htmlFor="reason">Reason</Label>
              <Textarea
                id="reason"
                aria-invalid={Boolean(reasonError)}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              {reasonError && <p className="text-sm text-destructive">{reasonError}</p>}
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button
              variant={dialog === "verify" ? "default" : "destructive"}
              onClick={submit}
              disabled={busy}
            >
              {busy ? "Working…" : "Confirm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}
