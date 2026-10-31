/** Donor donation history: search, filters, pagination — all server-side. */

import { Search } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select, Skeleton } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { listCategories, listMyDonations } from "@/lib/donation-api";
import type { DonationCategory, DonationSummary, Page } from "@/types/donations";

const STATUSES = [
  "pending",
  "offered",
  "accepted",
  "pickup_scheduled",
  "picked_up",
  "completed",
  "cancelled",
];

const STATUS_VARIANTS: Record<string, "warning" | "success" | "secondary" | "destructive" | "muted"> = {
  pending: "warning",
  offered: "secondary",
  accepted: "success",
  pickup_scheduled: "success",
  picked_up: "success",
  completed: "muted",
  cancelled: "destructive",
};

export function DonationsListPage() {
  const [pageData, setPageData] = useState<Page<DonationSummary> | null>(null);
  const [categories, setCategories] = useState<DonationCategory[]>([]);
  const [status, setStatus] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    setError(null);
    listMyDonations({
      page,
      page_size: 10,
      status: status || undefined,
      category_id: categoryId || undefined,
      q: query || undefined,
      date_from: dateFrom || undefined,
    })
      .then(setPageData)
      .catch(() => setError("Could not load your donations. Please try again."));
  }, [page, status, categoryId, query, dateFrom]);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setPage(1);
  };

  const totalPages = pageData ? Math.max(1, Math.ceil(pageData.total / pageData.page_size)) : 1;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">My donations</h1>

      <Card>
        <CardContent className="p-4">
          <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="relative lg:col-span-2">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
              <Input
                className="pl-8"
                placeholder="Search by title…"
                aria-label="Search donations by title"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <Select aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s.replace("_", " ")}</option>
              ))}
            </Select>
            <Select aria-label="Filter by category" value={categoryId} onChange={(e) => { setCategoryId(e.target.value); setPage(1); }}>
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.display_name}</option>
              ))}
            </Select>
            <Input
              type="date"
              aria-label="Created from"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
            />
          </form>
        </CardContent>
      </Card>

      {error && (
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-4">
            <p role="alert" className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={() => setPage(1)}>Retry</Button>
          </CardContent>
        </Card>
      )}

      {!pageData && !error && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      )}

      {pageData && pageData.items.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
            <p className="text-sm text-muted-foreground">
              No donations match these filters.
            </p>
            <Button asChild size="sm">
              <Link to="/donations/new">Create a donation</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {pageData && pageData.items.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <ul className="hidden text-xs font-medium text-muted-foreground sm:grid sm:grid-cols-[1fr_140px_110px_90px] sm:gap-3 sm:border-b sm:px-4 sm:py-2">
              <span>Donation</span>
              <span>Category</span>
              <span>Created</span>
              <span>Status</span>
            </ul>
            <ul className="divide-y">
              {pageData.items.map((donation) => (
                <li
                  key={donation.id}
                  className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_140px_110px_90px] sm:items-center sm:gap-3"
                >
                  <div className="flex items-center gap-3">
                    {donation.primary_image_url ? (
                      <img
                        src={donation.primary_image_url}
                        alt=""
                        className="h-10 w-10 rounded-md border object-cover"
                      />
                    ) : (
                      <div className="h-10 w-10 rounded-md border bg-muted" aria-hidden />
                    )}
                    <div className="min-w-0">
                      <Link to={`/donations/${donation.id}`} className="font-medium hover:underline">
                        {donation.title}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {donation.reference} · {donation.quantity} {donation.unit}
                      </p>
                    </div>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {donation.category_display_name}
                    {donation.subcategory_display_name
                      ? ` · ${donation.subcategory_display_name}`
                      : ""}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {new Date(donation.created_at).toLocaleDateString()}
                  </span>
                  <Badge variant={STATUS_VARIANTS[donation.status] ?? "secondary"}>
                    {donation.status.replace("_", " ")}
                  </Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {pageData && pageData.total > pageData.page_size && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {pageData.page} of {totalPages} · {pageData.total} donations
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
