/** Explainable match list for a donation (M3) — factors, reasons, distance. */

import { MapPin, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/form-controls";
import { apiFetch } from "@/lib/api";
import type { MatchResult } from "@/types/needs";

const FACTOR_LABELS: Record<string, string> = {
  compatibility: "Category compatibility",
  urgency: "Need urgency",
  distance: "Distance",
  quantity_fit: "Quantity fit",
  timeliness: "Required-by timing",
};

const EXCLUSION_LABELS: Record<string, string> = {
  organization_not_verified: "unverified organizations",
  no_active_need: "no active need",
  need_not_active: "inactive needs",
  need_fully_funded: "fully fulfilled needs",
  category_incompatible: "incompatible need categories",
  outside_service_radius: "outside the service radius",
};

export function DonationMatches({ donationId }: { donationId: string }) {
  const [result, setResult] = useState<MatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiFetch<MatchResult>(`/api/donations/${donationId}/matches`)
      .then((data) => {
        if (!cancelled) setResult(data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load the matching results.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [donationId]);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recommended organizations</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="flex items-center justify-between gap-4 p-4">
          <p role="alert" className="text-sm text-destructive">{error}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-primary" aria-hidden /> Recommended
          organizations
        </CardTitle>
        <CardDescription>
          Rule-based, explainable matching — never machine learning. Scores combine
          compatibility, urgency, distance, quantity fit, and timing.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {result && result.eligible.length === 0 && (
          <div className="rounded-md border bg-muted/40 p-4 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">
              No eligible organizations right now.
            </p>
            <p className="mt-1">
              No verified organization currently has an active, compatible need with
              remaining quantity in your area.
              {result.excluded.length > 0 &&
                ` Considered and excluded: ${result.excluded
                  .map(
                    (entry) =>
                      `${entry.count} ${EXCLUSION_LABELS[entry.reason_code] ?? entry.reason_code}`,
                  )
                  .join(", ")}.`}
            </p>
          </div>
        )}

        {result?.eligible.map((candidate) => (
          <div key={candidate.need_id} className="rounded-md border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="flex items-center gap-2 font-medium">
                  <ShieldCheck className="h-4 w-4 text-success" aria-hidden />
                  {candidate.organization_name}
                  <Badge variant="success" className="text-[10px]">
                    verified
                  </Badge>
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Need: {candidate.need_title} · {candidate.remaining_quantity}{" "}
                  {candidate.unit} remaining
                </p>
              </div>
              <div className="text-right">
                <p className="text-lg font-semibold text-primary">
                  {candidate.score.toFixed(1)}
                </p>
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  match score
                </p>
              </div>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-1.5 text-xs sm:grid-cols-5">
              {Object.entries(candidate.factors).map(([name, factor]) => (
                <div key={name} className="rounded bg-muted/50 px-2 py-1.5">
                  <p className="text-muted-foreground">{FACTOR_LABELS[name] ?? name}</p>
                  <p className="font-medium">
                    {factor.score.toFixed(2)} × {factor.weight.toFixed(2)} ={" "}
                    {factor.weighted.toFixed(2)}
                  </p>
                </div>
              ))}
            </div>

            <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              {candidate.reasons.map((reason) => (
                <li key={reason}>
                  {reason === "Distance could not be calculated." && (
                    <MapPin className="mr-1 inline h-3 w-3" aria-hidden />
                  )}
                  {reason}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
