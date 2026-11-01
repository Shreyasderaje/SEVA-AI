/** Admin analytics overview (M5 §3) — DB-backed cards + charts + date filter. */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Select, Skeleton } from "@/components/ui/form-controls";
import { apiFetch } from "@/lib/api";

interface Analytics {
  range_days: number | null;
  generated_at: string;
  cards: Record<string, number>;
  donations_over_time: { week: string; count: number }[];
  donation_status: { status: string; count: number }[];
  donation_category: { category: string; count: number }[];
  org_verification: { status: string; count: number }[];
  offer_outcomes: { status: string; count: number }[];
  needs_status: { status: string; count: number }[];
  demo_data: Record<string, number>;
}

const CARD_LABELS: [string, string][] = [
  ["total_donors", "Donors"],
  ["total_organizations", "Organizations"],
  ["verified_organizations", "Verified orgs"],
  ["pending_organizations", "Pending applications"],
  ["total_donations", "Donations"],
  ["pending_donations", "Pending donations"],
  ["completed_donations", "Completed donations"],
  ["active_needs", "Active needs"],
  ["fulfilled_needs", "Fulfilled needs"],
  ["offers_sent", "Offers sent"],
  ["offers_accepted", "Offers accepted"],
  ["payments_awaiting_verification", "Payments awaiting verification"],
];

export function AdminAnalyticsPage() {
  const [range, setRange] = useState<string>("30");
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const query = range === "all" ? "" : `?days=${range}`;
    apiFetch<Analytics>(`/api/admin/analytics${query}`)
      .then(setData)
      .catch(() => setError("Could not load the analytics overview."))
      .finally(() => setLoading(false));
  }, [range]);

  useEffect(load, [load]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Analytics overview</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Database-backed statistics — aggregates include any demo records
            (counted separately below the charts).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            aria-label="Date range"
            value={range}
            onChange={(event) => setRange(event.target.value)}
            className="max-w-44"
          >
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="all">All time</option>
          </Select>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw aria-hidden /> Refresh
          </Button>
        </div>
      </div>

      {error && (
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-4">
            <p role="alert" className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={load}>Retry</Button>
          </CardContent>
        </Card>
      )}

      {loading && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {CARD_LABELS.map(([key]) => (
            <Skeleton key={key} className="h-20 w-full" />
          ))}
        </div>
      )}

      {!loading && data && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {CARD_LABELS.map(([key, label]) => (
              <Card key={key}>
                <CardHeader className="pb-1">
                  <CardDescription className="text-xs">{label}</CardDescription>
                  <CardTitle className="text-2xl">{data.cards[key] ?? 0}</CardTitle>
                </CardHeader>
              </Card>
            ))}
          </div>

          {/* Donations over time */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Donations over time</CardTitle>
              <CardDescription>Weekly counts (ISO weeks)</CardDescription>
            </CardHeader>
            <CardContent>
              {data.donations_over_time.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  No donations in this period.
                </p>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data.donations_over_time}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="week" fontSize={11} />
                      <YAxis allowDecimals={false} fontSize={11} />
                      <Tooltip />
                      <Line type="monotone" dataKey="count" stroke="#17635B" strokeWidth={2} name="Donations" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Donation status */}
            <ChartCard title="Donation status distribution" data={data.donation_status} nameKey="status" valueKey="count" />
            {/* Category distribution */}
            <ChartCard title="Donations by category" data={data.donation_category} nameKey="category" valueKey="count" />
            {/* Org verification */}
            <ChartCard title="Organization verification" data={data.org_verification} nameKey="status" valueKey="count" />
            {/* Offer outcomes */}
            <ChartCard title="Offer outcomes (accepted vs declined)" data={data.offer_outcomes} nameKey="status" valueKey="count" />
            {/* Needs status */}
            <ChartCard title="Needs status distribution" data={data.needs_status} nameKey="status" valueKey="count" />
            {/* Demo transparency card */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Demo data in these aggregates</CardTitle>
                <CardDescription>
                  Demo records are synthetic and included where present — they are
                  never real user activity.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {Object.entries(data.demo_data).every(([, count]) => count === 0) ? (
                  <Badge variant="muted">No demo data in this database</Badge>
                ) : (
                  Object.entries(data.demo_data).map(([name, count]) => (
                    <Badge key={name} variant="warning">
                      DEMO {name}: {count}
                    </Badge>
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function ChartCard({ title, data, nameKey, valueKey }: {
  title: string;
  data: Record<string, unknown>[];
  nameKey: string;
  valueKey: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No data in this period.</p>
        ) : (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey={nameKey} fontSize={11} />
                <YAxis allowDecimals={false} fontSize={11} />
                <Tooltip />
                <Bar dataKey={valueKey} fill="#17635B" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
