/** Donation detail: photos, AI-vs-confirmed categories, append-only timeline,
 * and cancellation (donor, while pending/offered) with a confirmation dialog. */

import { ArrowRight, MapPin, ShieldQuestion } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
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
import { Skeleton } from "@/components/ui/form-controls";
import { ApiError } from "@/lib/api";
import { cancelDonation, getDonation } from "@/lib/donation-api";
import { DonationMatches } from "@/features/donations/DonationMatches";
import {
  DonationOffersSection,
  DonationPaymentSection,
} from "@/features/donations/DonationWorkflowPanels";
import type { DonationDetail, DonationStatus } from "@/types/donations";

const STATUS_VARIANTS: Record<DonationStatus, "warning" | "success" | "secondary" | "destructive" | "muted"> = {
  pending: "warning",
  offered: "secondary",
  accepted: "success",
  pickup_scheduled: "success",
  picked_up: "success",
  completed: "muted",
  cancelled: "destructive",
};

export function DonationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [donation, setDonation] = useState<DonationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    if (!id) return;
    setError(null);
    getDonation(id)
      .then(setDonation)
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Donation not found."
            : "Could not load this donation.",
        ),
      );
  }, [id]);

  if (error) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldQuestion className="h-5 w-5 text-destructive" aria-hidden />
            {error}
          </CardTitle>
          <CardDescription>
            The donation may not exist or may belong to another account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="outline">
            <Link to="/donations">Back to my donations</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!donation) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const handleCancel = async () => {
    if (!id) return;
    setCancelling(true);
    try {
      const updated = await cancelDonation(id);
      setDonation(updated);
      setConfirmOpen(false);
      toast.success("Donation cancelled");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not cancel the donation.");
      setConfirmOpen(false);
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs text-muted-foreground">{donation.reference}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{donation.title}</h1>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={STATUS_VARIANTS[donation.status]}>
            {donation.status.replace("_", " ")}
          </Badge>
          {donation.status === "pending" && (
            <Button variant="outline" onClick={() => setConfirmOpen(true)}>
              Cancel donation
            </Button>
          )}
        </div>
      </div>

      {/* Photos */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Photographs</CardTitle>
          <CardDescription>
            The first photo is the primary image used for the AI suggestion;
            the rest are supporting photographs.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-3">
            {donation.images.map((image) => (
              <div key={image.id} className="relative overflow-hidden rounded-md border">
                <img
                  src={image.url}
                  alt={`Donation photo ${image.position}`}
                  className="aspect-square w-full object-cover"
                />
                {image.position === 1 ? (
                  <Badge className="absolute left-1 top-1">Primary</Badge>
                ) : (
                  <Badge variant="muted" className="absolute left-1 top-1">
                    Supporting
                  </Badge>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Details */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <Row label="Category">
            {donation.category_display_name}
            {donation.subcategory_display_name
              ? ` · ${donation.subcategory_display_name}`
              : ""}
          </Row>
          <Row label="Quantity">{`${donation.quantity} ${donation.unit}`}</Row>
          <Row label="Condition">{donation.condition ?? "—"}</Row>
          <Row label="Description">{donation.description ?? "—"}</Row>
          <Row label="Pickup area">
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" aria-hidden /> {donation.pickup_area ?? "—"}
            </span>
          </Row>
          <Row label="Exact coordinates">
            {donation.location_consent && donation.pickup_latitude !== null
              ? `${donation.pickup_latitude.toFixed(5)}, ${donation.pickup_longitude?.toFixed(5)} (stored with consent)`
              : "Not stored"}
          </Row>
          {donation.pickup_window_start && donation.pickup_window_end && (
            <Row label="Preferred window">
              {new Date(donation.pickup_window_start).toLocaleString()} —{" "}
              {new Date(donation.pickup_window_end).toLocaleString()}
            </Row>
          )}
          <Row label="AI suggestion">
            {donation.ai_predicted_category
              ? `${donation.ai_predicted_category} (${((donation.ai_confidence ?? 0) * 100).toFixed(1)}%) — confirmed by you as ${donation.category_display_name}`
              : "No AI suggestion used (manual category)"}
          </Row>
        </CardContent>
      </Card>

      {/* Append-only timeline */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Status timeline</CardTitle>
          <CardDescription>
            Every status change is recorded permanently — history cannot be
            edited or deleted.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="flex flex-col gap-0">
            {donation.timeline.map((entry, index) => (
              <li key={entry.id} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span
                    className="mt-1 h-2.5 w-2.5 rounded-full bg-primary"
                    aria-hidden
                  />
                  {index < donation.timeline.length - 1 && (
                    <span className="w-px flex-1 bg-border" aria-hidden />
                  )}
                </div>
                <div className="pb-5">
                  <p className="text-sm font-medium">
                    {entry.from_status ? (
                      <>
                        {entry.from_status.replace("_", " ")}{" "}
                        <ArrowRight className="inline h-3.5 w-3.5 text-muted-foreground" aria-hidden />{" "}
                        {entry.to_status.replace("_", " ")}
                      </>
                    ) : (
                      <>Created as {entry.to_status.replace("_", " ")}</>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(entry.created_at).toLocaleString()}
                    {entry.note ? ` · ${entry.note}` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      {/* Explainable matching (M3) — shown while the donation is unmatched */}
      {donation.status === "pending" && <DonationMatches donationId={donation.id} />}

      {/* Offer progress + payment workflow (M4) */}
      <DonationOffersSection
        donationId={donation.id}
        status={donation.status}
        unit={donation.unit}
      />
      {["accepted", "pickup_scheduled", "picked_up", "completed"].includes(
        donation.status,
      ) && <DonationPaymentSection donationId={donation.id} />}

      {/* Cancel confirmation */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel this donation?</DialogTitle>
            <DialogDescription>
              {donation.title} ({donation.reference}) will be marked cancelled.
              This cannot be undone. Organizations will no longer be matched
              with this listing.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              Keep donation
            </Button>
            <Button variant="destructive" onClick={handleCancel} disabled={cancelling}>
              {cancelling ? "Cancelling…" : "Cancel donation"}
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
