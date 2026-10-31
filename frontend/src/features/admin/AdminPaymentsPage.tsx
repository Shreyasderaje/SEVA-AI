/** Admin payment review queue (M4 §9) — verify/reject with reasons. */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, Skeleton, Textarea } from "@/components/ui/form-controls";
import { ApiError } from "@/lib/api";
import {
  adminListPayments,
  adminRejectPayment,
  adminVerifyPayment,
} from "@/lib/workflow-api";
import type { PaymentRecordView } from "@/types/workflow";

const STATUS_VARIANTS: Record<string, "warning" | "success" | "destructive" | "muted"> = {
  submitted_unverified: "warning",
  verified: "success",
  rejected: "destructive",
};

export function AdminPaymentsPage() {
  const [payments, setPayments] = useState<PaymentRecordView[] | null>(null);
  const [status, setStatus] = useState("submitted_unverified");
  const [error, setError] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<PaymentRecordView | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setError(null);
    adminListPayments({ status: status || undefined })
      .then((page) => setPayments(page.items))
      .catch(() => setError("Could not load the payment queue."));
  };

  useEffect(() => {
    setError(null);
    adminListPayments({ status: status || undefined })
      .then((page) => setPayments(page.items))
      .catch(() => setError("Could not load the payment queue."));
  }, [status]);

  const verify = async (payment: PaymentRecordView) => {
    setBusy(true);
    try {
      const updated = await adminVerifyPayment(payment.id);
      setPayments((current) =>
        current ? current.filter((p) => p.id !== updated.id) : current,
      );
      toast.success("Payment verified.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Verification failed.");
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!rejectTarget) return;
    if (reason.trim().length < 3) {
      setReasonError("A reason is required to reject a payment.");
      return;
    }
    setBusy(true);
    try {
      const updated = await adminRejectPayment(rejectTarget.id, reason.trim());
      setPayments((current) =>
        current ? current.filter((p) => p.id !== updated.id) : current,
      );
      toast.success("Payment rejected.");
      setRejectTarget(null);
      setReason("");
      setReasonError(null);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Rejection failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Payment verification</h1>
        <Select
          aria-label="Filter by payment status"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="max-w-60"
        >
          <option value="submitted_unverified">Pending verification</option>
          <option value="verified">Verified</option>
          <option value="rejected">Rejected</option>
        </Select>
      </div>

      {error && (
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-4">
            <p role="alert" className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={load}>Retry</Button>
          </CardContent>
        </Card>
      )}

      {!payments && !error && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      )}

      {payments && payments.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No payments with this status.
          </CardContent>
        </Card>
      )}

      {payments &&
        payments.map((payment) => (
          <Card key={payment.id}>
            <CardContent className="flex flex-col gap-3 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium">{payment.transaction_reference}</p>
                  <p className="text-xs text-muted-foreground">
                    {payment.amount !== null ? `₹${payment.amount.toFixed(2)} · ` : ""}
                    submitted {new Date(payment.created_at).toLocaleString()}
                    {payment.rejection_reason ? ` · reason: ${payment.rejection_reason}` : ""}
                  </p>
                </div>
                <Badge variant={STATUS_VARIANTS[payment.status] ?? "secondary"}>
                  {payment.status.replace("_", " ")}
                </Badge>
              </div>
              {payment.organization_id && (
                <p className="text-xs text-muted-foreground">
                  For organization {payment.organization_id}
                  {payment.donation_id ? (
                    <>
                      {" · donation "}
                      <Link
                        to={`/donations/${payment.donation_id}`}
                        className="text-primary hover:underline"
                      >
                        {payment.donation_id.slice(0, 8)}…
                      </Link>
                    </>
                  ) : null}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-3">
                {payment.has_receipt && payment.receipt_url && (
                  <a
                    href={payment.receipt_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium text-primary hover:underline"
                  >
                    Open receipt (authorized)
                  </a>
                )}
                {payment.status === "submitted_unverified" && (
                  <>
                    <Button size="sm" onClick={() => verify(payment)} disabled={busy}>
                      Verify payment
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => setRejectTarget(payment)}
                      disabled={busy}
                    >
                      Reject
                    </Button>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        ))}

      {/* Reject dialog */}
      <Dialog open={rejectTarget !== null} onOpenChange={(open) => !open && setRejectTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject this payment?</DialogTitle>
            <DialogDescription>
              The donor is notified with your reason. The donation workflow is not
              affected by payment decisions.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            aria-label="Rejection reason"
            placeholder="e.g. Reference not found in the organization's statement"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          {reasonError && <p className="text-sm text-destructive">{reasonError}</p>}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRejectTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={reject} disabled={busy}>
              {busy ? "Rejecting…" : "Reject payment"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
