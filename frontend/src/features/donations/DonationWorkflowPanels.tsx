/** Donor-facing offer progress + payment section for an accepted donation (M4). */

import { CreditCard, ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
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
import { Skeleton } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import {
  getDonationPaymentInfo,
  initiateOffer,
  listDonationOffers,
  submitPayment,
} from "@/lib/workflow-api";
import type { Offer, PaymentInfo, PaymentRecordView } from "@/types/workflow";

const OFFER_BADGES: Record<string, "warning" | "success" | "destructive" | "muted"> = {
  sent: "warning",
  accepted: "success",
  declined: "destructive",
  withdrawn: "muted",
};

export function DonationOffersSection({
  donationId,
  status,
  unit,
}: {
  donationId: string;
  status: string;
  unit: string;
}) {
  const [offers, setOffers] = useState<Offer[] | null>(null);
  const [initiating, setInitiating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    listDonationOffers(donationId)
      .then((page) => setOffers(page.items))
      .catch(() => setError("Could not load the offer history."));
  };

  useEffect(load, [donationId]);

  const initiate = async () => {
    setInitiating(true);
    try {
      const result = await initiateOffer(donationId);
      toast.success(result.message);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not send the offer.");
    } finally {
      setInitiating(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Offer progress</CardTitle>
        <CardDescription>
          One organization at a time — the highest-ranked eligible organization is
          offered first; a decline automatically selects the next one.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {offers === null && !error && (
          <Skeleton className="h-16 w-full" />
        )}
        {offers !== null && offers.length === 0 && status === "pending" && (
          <div className="flex flex-col items-start gap-3 rounded-md border bg-muted/40 p-4 text-sm text-muted-foreground">
            <p>No offer has been sent yet.</p>
            <Button size="sm" onClick={initiate} disabled={initiating}>
              {initiating ? "Sending…" : "Send offer to the top match"}
            </Button>
          </div>
        )}
        {offers !== null && offers.length === 0 && status !== "pending" && (
          <p className="text-sm text-muted-foreground">
            No offers have been sent for this donation.
          </p>
        )}
        {offers?.map((offer) => (
          <div key={offer.id} className="rounded-md border p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium">{offer.organization_name ?? "Organization"}</p>
              <Badge variant={OFFER_BADGES[offer.status] ?? "secondary"}>{offer.status}</Badge>
            </div>
            {offer.score !== null && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                Match score {offer.score.toFixed(1)} at offer time (snapshot preserved).
              </p>
            )}
            {offer.status === "declined" && offer.decline_reason && (
              <p className="mt-0.5 text-xs text-destructive">
                Declined: {offer.decline_reason}
              </p>
            )}
            {offer.pickup_date && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                Pickup {offer.pickup_date}
                {offer.pickup_window_start != null && offer.pickup_window_end != null
                  ? ` · ${new Date(offer.pickup_window_start).toLocaleTimeString()}–${new Date(offer.pickup_window_end).toLocaleTimeString()}`
                  : ""}
                {offer.pickup_instructions ? ` · ${offer.pickup_instructions}` : ""}
              </p>
            )}
            {offer.quantity_received !== null && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                Received: {offer.quantity_received} {unit}
              </p>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function DonationPaymentSection({ donationId }: { donationId: string }) {
  const [info, setInfo] = useState<PaymentInfo | null>(null);
  const [payments, setPayments] = useState<PaymentRecordView[] | null>(null);
  const [reference, setReference] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [unavailable, setUnavailable] = useState(false);

  const loadPayments = () => {
    import("@/lib/workflow-api").then(({ listMyPayments }) =>
      listMyPayments()
        .then((rows) =>
          setPayments(rows.filter((p) => p.donation_id === donationId)),
        )
        .catch(() => setPayments([])),
    );
  };

  useEffect(() => {
    getDonationPaymentInfo(donationId)
      .then(setInfo)
      .catch(() => setUnavailable(true));
    loadPayments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [donationId]);

  const submit = async () => {
    setError(null);
    if (info === null) return;
    if (!/^[a-zA-Z0-9]{6,40}$/.test(reference.trim())) {
      setError("The transaction reference must be 6–40 letters/digits.");
      return;
    }
    setBusy(true);
    try {
      await submitPayment({
        donation_id: donationId,
        organization_id: info.organization_id,
        transaction_reference: reference.trim(),
        amount: amount ? Number(amount) : undefined,
      });
      toast.success("Payment reference submitted — an admin will verify it manually.");
      setReference("");
      setAmount("");
      loadPayments();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit the payment reference.");
    } finally {
      setBusy(false);
    }
  };

  if (unavailable) return null; // payment not applicable — workflow stays usable

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CreditCard className="h-4 w-4 text-primary" aria-hidden /> Payment (UPI —
          manual verification)
        </CardTitle>
        <CardDescription>
          Payment happens in your own UPI app, outside SEVA-AI. A submitted
          reference is NOT proof of payment — an admin verifies it manually.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {info === null && !unavailable && <Skeleton className="h-16 w-full" />}
        {info && (
          <div className="flex flex-col gap-2 text-sm">
            <p>
              Pay <strong>{info.organization_name}</strong> at UPI ID{" "}
              <strong className="text-primary">{info.upi_id}</strong>
            </p>
            {info.qr_url && (
              <div className="flex items-center gap-3">
                <img
                  src={info.qr_url}
                  alt="Organization UPI QR code"
                  className="h-32 w-32 rounded-md border object-contain"
                />
                <a
                  href={info.qr_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  Open QR <ExternalLink className="h-3 w-3" aria-hidden />
                </a>
              </div>
            )}
            <p className="text-xs leading-relaxed text-muted-foreground">{info.instructions}</p>
          </div>
        )}

        <div className="flex flex-col gap-2 rounded-md border bg-muted/40 p-3">
          <p className="text-sm font-medium">Submit your payment reference</p>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="txn_ref">Transaction reference</Label>
            <Input
              id="txn_ref"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              aria-invalid={Boolean(error)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="txn_amount">Amount (optional)</Label>
            <Input
              id="txn_amount"
              type="number"
              step="any"
              min="0"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <Button onClick={submit} disabled={busy}>
            {busy ? "Submitting…" : "Submit reference for verification"}
          </Button>
        </div>

        {payments !== null && payments.length > 0 && (
          <ul className="flex flex-col gap-1.5 text-xs">
            {payments.map((payment) => (
              <li key={payment.id} className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{payment.transaction_reference}</span>
                <Badge
                  variant={
                    payment.status === "verified"
                      ? "success"
                      : payment.status === "rejected"
                        ? "destructive"
                        : "warning"
                  }
                  className="text-[10px]"
                >
                  {payment.status.replace("_", " ")}
                </Badge>
                {payment.rejection_reason && (
                  <span className="text-destructive">{payment.rejection_reason}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
