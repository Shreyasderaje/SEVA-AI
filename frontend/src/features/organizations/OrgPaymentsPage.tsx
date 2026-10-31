/** Organization UPI payment setup (M4 §9) — pending admin approval. */

import { useCallback, useEffect, useRef, useState } from "react";
import { CreditCard } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { getUpiSetup, submitUpiSetup } from "@/lib/workflow-api";
import type { UpiSetupStatus } from "@/types/workflow";

const STATUS_BADGES: Record<string, { variant: "warning" | "success" | "destructive" | "muted"; label: string }> = {
  none: { variant: "muted", label: "Not configured" },
  pending_approval: { variant: "warning", label: "Pending admin approval" },
  approved: { variant: "success", label: "Approved — visible to donors" },
  rejected: { variant: "destructive", label: "Rejected" },
};

export function OrgPaymentsPage() {
  const [status, setStatus] = useState<UpiSetupStatus | null>(null);
  const [upiId, setUpiId] = useState("");
  const [qrFile, setQrFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    getUpiSetup()
      .then((data) => {
        setStatus(data);
        setUpiId(data.upi_id ?? "");
      })
      .catch(() => setStatus({ upi_id: null, upi_status: "none", has_qr: false }));
  }, []);

  useEffect(load, [load]);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      const updated = await submitUpiSetup(upiId.trim(), qrFile ?? undefined);
      setStatus(updated);
      setQrFile(null);
      toast.success("Payment details submitted for admin approval.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit payment details.");
    } finally {
      setBusy(false);
    }
  };

  const badge = STATUS_BADGES[status?.upi_status ?? "none"];

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
        <CreditCard className="h-6 w-6 text-primary" aria-hidden /> Payment setup (UPI)
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Donors pay in their own UPI app — SEVA-AI never processes payments. Your
        details are shown to donors only after an admin approves them.
      </p>

      {status && (
        <div className="mt-4">
          <Badge variant={badge.variant}>{badge.label}</Badge>
          {status.upi_status === "rejected" && status.rejection_reason && (
            <p className="mt-2 text-sm text-destructive">Reason: {status.rejection_reason}</p>
          )}
        </div>
      )}

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Your UPI details</CardTitle>
          <CardDescription>
            Re-submitting replaces the current details and resets approval to
            pending.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="upi_id">UPI ID</Label>
            <Input
              id="upi_id"
              placeholder="organization@bank"
              value={upiId}
              onChange={(event) => setUpiId(event.target.value)}
              aria-invalid={Boolean(error)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="qr_image">QR image (optional)</Label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,image/jpeg,image/png"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null;
                event.target.value = "";
                setQrFile(file);
              }}
            />
            <Button variant="outline" onClick={() => fileInputRef.current?.click()}>
              {qrFile ? qrFile.name : "Choose QR image (JPEG/PNG)"}
            </Button>
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <Button onClick={submit} disabled={busy}>
            {busy ? "Submitting…" : "Submit for approval"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
