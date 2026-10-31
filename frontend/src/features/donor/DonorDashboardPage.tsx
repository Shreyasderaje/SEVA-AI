/** Donor dashboard: DB-backed summary cards, recent donations, quick actions. */

import { HandHeart, PackageCheck, PackageOpen, Plus, Truck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

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
import { useAuth } from "@/features/auth/auth-context";
import {
  listMyDonations,
  donationSummary,
} from "@/lib/donation-api";
import type { DonationSummary, DonationSummaryCounts } from "@/types/donations";

const STATUS_VARIANTS: Record<string, "warning" | "success" | "secondary" | "destructive" | "muted"> = {
  pending: "warning",
  offered: "secondary",
  accepted: "success",
  pickup_scheduled: "success",
  picked_up: "success",
  completed: "muted",
  cancelled: "destructive",
};

export function DonorDashboardPage() {
  const { user } = useAuth();
  const [counts, setCounts] = useState<DonationSummaryCounts | null>(null);
  const [recent, setRecent] = useState<DonationSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const load = () => {
    setError(null);
    setRetrying(true);
    Promise.all([donationSummary(), listMyDonations({ page: 1, page_size: 5 })])
      .then(([summary, page]) => {
        setCounts(summary);
        setRecent(page.items);
      })
      .catch(() => setError("Could not load your dashboard. Please try again."))
      .finally(() => setRetrying(false));
  };

  useEffect(load, []);

  const cards = [
    { key: "active", label: "Active", icon: PackageOpen, tone: "text-warning" },
    { key: "accepted", label: "Accepted", icon: PackageCheck, tone: "text-success" },
    { key: "completed", label: "Completed", icon: Truck, tone: "text-primary" },
  ] as const;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <HandHeart className="h-6 w-6 text-primary" aria-hidden />
            Hello, {user?.full_name}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Track your donations and their journey to organizations in need.
          </p>
        </div>
        <Button asChild size="lg">
          <Link to="/donations/new">
            <Plus aria-hidden /> Create donation
          </Link>
        </Button>
      </div>

      {error && (
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-4">
            <p role="alert" className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={load} disabled={retrying}>
              Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Summary cards — real database-backed counts */}
      <div className="grid gap-4 sm:grid-cols-3">
        {cards.map((card) => (
          <Card key={card.key}>
            <CardHeader className="pb-2">
              <CardDescription className="flex items-center gap-2">
                <card.icon className={`h-4 w-4 ${card.tone}`} aria-hidden />
                {card.label}
              </CardDescription>
              <CardTitle className="text-3xl">
                {counts ? counts[card.key] : <Skeleton className="h-8 w-12" />}
              </CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>

      {/* Recent activity */}
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="text-base">Recent donations</CardTitle>
            <CardDescription>Your five most recent listings.</CardDescription>
          </div>
          <Button asChild variant="ghost" size="sm">
            <Link to="/donations">View all</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {recent === null && !error && (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          )}
          {recent !== null && recent.length === 0 && (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <PackageOpen className="h-8 w-8 text-muted-foreground" aria-hidden />
              <p className="text-sm text-muted-foreground">
                You have not created any donations yet.
              </p>
              <Button asChild size="sm">
                <Link to="/donations/new">Create your first donation</Link>
              </Button>
            </div>
          )}
          {recent !== null && recent.length > 0 && (
            <ul className="flex flex-col divide-y">
              {recent.map((donation) => (
                <li key={donation.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <Link
                      to={`/donations/${donation.id}`}
                      className="font-medium hover:underline"
                    >
                      {donation.title}
                    </Link>
                    <p className="truncate text-xs text-muted-foreground">
                      {donation.reference} · {donation.category_display_name} ·{" "}
                      {new Date(donation.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <Badge variant={STATUS_VARIANTS[donation.status] ?? "secondary"}>
                    {donation.status.replace("_", " ")}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
