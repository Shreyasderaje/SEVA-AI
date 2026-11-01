/** Admin: organization applications list (M3). */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select, Skeleton } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { adminListOrganizations } from "@/lib/organization-api";
import type { AdminOrganizationListItem } from "@/types/organizations";
import type { Page } from "@/types/donations";

const STATUS_VARIANTS: Record<string, "warning" | "success" | "destructive" | "muted"> = {
  pending_verification: "warning",
  verified: "success",
  rejected: "destructive",
  suspended: "destructive",
};

export function AdminOrgListPage() {
  const [pageData, setPageData] = useState<Page<AdminOrganizationListItem> | null>(null);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    adminListOrganizations({ status: status || undefined, q: search || undefined, page })
      .then(setPageData)
      .catch(() => setError("Could not load organizations."));
  }, [page, status, search]);

  const totalPages = pageData
    ? Math.max(1, Math.ceil(pageData.total / pageData.page_size))
    : 1;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Organizations</h1>
        <Link to="/admin" className="text-sm font-medium text-primary hover:underline">
          Analytics
        </Link>
        <Input
          placeholder="Search organizations…"
          aria-label="Search organizations"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          className="max-w-56"
        />
        <Select
          aria-label="Filter by verification status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
          className="max-w-60"
        >
          <option value="">All statuses</option>
          <option value="pending_verification">Pending verification</option>
          <option value="verified">Verified</option>
          <option value="rejected">Rejected</option>
          <option value="suspended">Suspended</option>
        </Select>
      </div>

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
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}

      {pageData && pageData.items.length === 0 && (
        <Card>
          <CardContent className="p-6 text-center text-sm text-muted-foreground">
            No organizations match this filter.
          </CardContent>
        </Card>
      )}

      {pageData && pageData.items.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <ul className="divide-y">
              {pageData.items.map((org) => (
                <li key={org.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <Link
                      to={`/admin/organizations/${org.id}`}
                      className="font-medium hover:underline"
                    >
                      {org.name}
                    </Link>
                    <p className="text-xs text-muted-foreground">
                      {org.org_type ?? "organization"} · applied{" "}
                      {new Date(org.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <Badge variant={STATUS_VARIANTS[org.verification_status] ?? "secondary"}>
                    {org.verification_status.replace("_", " ")}
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
            Page {pageData.page} of {totalPages} · {pageData.total} organizations
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
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
