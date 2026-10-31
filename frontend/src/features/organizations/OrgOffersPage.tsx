/** Organization incoming offers (M4): accept/decline + pickup lifecycle. */

import { CheckCircle2, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import {
  acceptOffer,
  completeOffer,
  declineOffer,
  listMyOffers,
  markPickedUp,
  schedulePickup,
} from "@/lib/workflow-api";
import type { Offer } from "@/types/workflow";

const OFFER_BADGES: Record<string, "warning" | "success" | "destructive" | "muted"> = {
  sent: "warning",
  accepted: "success",
  declined: "destructive",
  withdrawn: "muted",
};

export function OrgOffersPage() {
  const [offers, setOffers] = useState<Offer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [declineTarget, setDeclineTarget] = useState<Offer | null>(null);
  const [declineReason, setDeclineReason] = useState("");
  const [scheduleTarget, setScheduleTarget] = useState<Offer | null>(null);
  const [completeTarget, setCompleteTarget] = useState<Offer | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setError(null);
    listMyOffers()
      .then((page) => setOffers(page.items))
      .catch(() => setError("Could not load your offers."));
  }, []);

  useEffect(load, [load]);

  const replace = (updated: Offer) =>
    setOffers((current) =>
      current ? current.map((o) => (o.id === updated.id ? updated : o)) : current,
    );

  const act = async (action: () => Promise<Offer>, success: string) => {
    setBusy(true);
    try {
      const updated = await action();
      replace(updated);
      toast.success(success);
      return updated;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "The action failed.");
      return null;
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Incoming offers</h1>

      {error && (
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-4">
            <p role="alert" className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={load}>Retry</Button>
          </CardContent>
        </Card>
      )}

      {!offers && !error && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {offers !== null && offers.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No offers yet. When a donor's donation matches one of your active needs,
            the offer appears here with its matching explanation.
          </CardContent>
        </Card>
      )}

      {offers?.map((offer) => (
        <Card key={offer.id}>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <CardTitle className="text-base">{offer.donation_title ?? "Donation"}</CardTitle>
                <CardDescription>
                  {offer.donation_reference} · {offer.donation_quantity}{" "}
                  {offer.donation_unit} offered
                </CardDescription>
              </div>
              <Badge variant={OFFER_BADGES[offer.status] ?? "secondary"}>{offer.status}</Badge>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {offer.score !== null && (
              <p className="text-sm">
                Match score <strong className="text-primary">{offer.score.toFixed(1)}</strong>
                {offer.rank_at_offer !== null && (
                  <span className="text-muted-foreground"> · rank {offer.rank_at_offer} at offer time</span>
                )}
              </p>
            )}
            {offer.factor_snapshot && (
              <div className="grid grid-cols-2 gap-1.5 text-xs sm:grid-cols-5">
                {Object.entries(offer.factor_snapshot.factors).map(([name, factor]) => (
                  <div key={name} className="rounded bg-muted/50 px-2 py-1.5">
                    <p className="text-muted-foreground capitalize">{name.replace("_", " ")}</p>
                    <p className="font-medium">
                      {factor.score.toFixed(2)} × {factor.weight.toFixed(2)}
                    </p>
                  </div>
                ))}
              </div>
            )}
            {offer.reason_text && (
              <p className="text-xs leading-relaxed text-muted-foreground">{offer.reason_text}</p>
            )}
            {offer.decline_reason && (
              <p className="text-xs text-destructive">Declined: {offer.decline_reason}</p>
            )}
            {offer.pickup_date && (
              <p className="text-xs text-muted-foreground">
                Pickup {offer.pickup_date}{" "}
                {offer.pickup_window_start && offer.pickup_window_end && (
                  <>
                    · {new Date(offer.pickup_window_start).toLocaleTimeString()} –{" "}
                    {new Date(offer.pickup_window_end).toLocaleTimeString()}
                  </>
                )}
                {offer.pickup_instructions ? ` · ${offer.pickup_instructions}` : ""}
              </p>
            )}
            {offer.quantity_received !== null && (
              <p className="text-xs text-muted-foreground">
                Received: {offer.quantity_received} {offer.donation_unit}
              </p>
            )}

            {offer.status === "sent" && (
              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() =>
                    act(() => acceptOffer(offer.id), "Offer accepted — schedule the pickup.")
                  }
                  disabled={busy}
                >
                  <CheckCircle2 aria-hidden /> Accept
                </Button>
                <Button variant="destructive" onClick={() => setDeclineTarget(offer)} disabled={busy}>
                  <XCircle aria-hidden /> Decline
                </Button>
              </div>
            )}
            {offer.status === "accepted" && (
              <Button variant="outline" onClick={() => setScheduleTarget(offer)}>
                Schedule pickup
              </Button>
            )}
            {offer.pickup_date && offer.status === "accepted" && (
              <Button variant="outline" onClick={() => act(() => markPickedUp(offer.id), "Marked as picked up")} disabled={busy}>
                Mark picked up
              </Button>
            )}
            {offer.status === "accepted" && offer.pickup_date && (
              <Button variant="outline" onClick={() => setCompleteTarget(offer)} disabled={busy}>
                Mark completed
              </Button>
            )}
          </CardContent>
        </Card>
      ))}

      {/* Decline dialog */}
      <Dialog open={declineTarget !== null} onOpenChange={(open) => !open && setDeclineTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Decline this offer?</DialogTitle>
            <DialogDescription>
              Only this offer is declined — the donation continues to the next
              eligible organization. Your reason is shared with the donor.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            aria-label="Decline reason (optional)"
            placeholder="Reason (optional)"
            value={declineReason}
            onChange={(e) => setDeclineReason(e.target.value)}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeclineTarget(null)}>Cancel</Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={async () => {
                if (!declineTarget) return;
                const declined = await act(
                  async () => {
                    await declineOffer(declineTarget.id, declineReason.trim() || undefined);
                    return declineTarget;
                  },
                  "Offer declined — the next candidate is being selected.",
                );
                if (declined) {
                  setDeclineTarget(null);
                  setDeclineReason("");
                  load(); // refresh with the next offer
                }
              }}
            >
              Decline
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Pickup scheduling dialog */}
      <PickupDialog
        offer={scheduleTarget}
        busy={busy}
        onClose={() => setScheduleTarget(null)}
        onSubmit={async (payload) => {
          if (!scheduleTarget) return;
          const updated = await act(() => schedulePickup(scheduleTarget.id, payload), "Pickup scheduled.");
          if (updated) setScheduleTarget(null);
        }}
      />

      {/* Completion dialog */}
      <CompleteDialog
        offer={completeTarget}
        busy={busy}
        onClose={() => setCompleteTarget(null)}
        onSubmit={async (quantity) => {
          if (!completeTarget) return;
          const updated = await act(() => completeOffer(completeTarget.id, quantity), "Donation completed.");
          if (updated) setCompleteTarget(null);
        }}
      />
    </div>
  );
}

function PickupDialog({
  offer,
  busy,
  onClose,
  onSubmit,
}: {
  offer: Offer | null;
  busy: boolean;
  onClose: () => void;
  onSubmit: (payload: { pickup_date: string; pickup_window_start: string; pickup_window_end: string; instructions?: string }) => Promise<void>;
}) {
  const [pickupDate, setPickupDate] = useState("2026-11-15");
  const [start, setStart] = useState("2026-11-15T10:00");
  const [end, setEnd] = useState("2026-11-15T12:00");
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <Dialog open={offer !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Schedule pickup</DialogTitle>
          <DialogDescription>
            Propose a date and time window — the donor is notified instantly.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pickup_date">Pickup date</Label>
            <Input id="pickup_date" type="date" value={pickupDate} onChange={(e) => setPickupDate(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="window_start">Window start</Label>
              <Input id="window_start" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="window_end">Window end</Label>
              <Input id="window_end" type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="instructions">Instructions (optional)</Label>
            <Textarea id="instructions" value={instructions} onChange={(e) => setInstructions(e.target.value)} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            disabled={busy}
            onClick={async () => {
              if (new Date(end) <= new Date(start)) {
                setError("The window end must be after its start.");
                return;
              }
              setError(null);
              await onSubmit({
                pickup_date: pickupDate,
                pickup_window_start: start,
                pickup_window_end: end,
                instructions: instructions || undefined,
              });
            }}
          >
            {busy ? "Scheduling…" : "Schedule"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CompleteDialog({
  offer,
  busy,
  onClose,
  onSubmit,
}: {
  offer: Offer | null;
  busy: boolean;
  onClose: () => void;
  onSubmit: (quantity: number) => Promise<void>;
}) {
  const [quantity, setQuantity] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <Dialog open={offer !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Mark donation completed</DialogTitle>
          <DialogDescription>
            Record the quantity ACTUALLY received — it updates the need's
            fulfilled quantity and cannot exceed the donated amount.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          <Input
            type="number"
            step="any"
            min="0"
            aria-label="Quantity received"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            disabled={busy}
            onClick={async () => {
              const value = Number(quantity);
              if (!Number.isFinite(value) || value <= 0) {
                setError("Enter a quantity greater than zero.");
                return;
              }
              setError(null);
              await onSubmit(value);
            }}
          >
            {busy ? "Completing…" : "Complete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
