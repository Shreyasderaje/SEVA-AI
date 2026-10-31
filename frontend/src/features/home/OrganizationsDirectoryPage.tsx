/** Public directory: verified organizations + their active needs (M3, §8.3). */

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
import { listPublicOrganizations, listPublicOrgNeeds } from "@/lib/organization-api";
import type { OrganizationPublic, PublicNeed } from "@/types/organizations";

interface Entry extends OrganizationPublic {
  needs: PublicNeed[] | null;
}

export function OrganizationsDirectoryPage() {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPublicOrganizations()
      .then(async (orgs) => {
        const withNeeds = await Promise.all(
          orgs.map(async (org) => {
            try {
              return { ...org, needs: await listPublicOrgNeeds(org.id) };
            } catch {
              return { ...org, needs: null };
            }
          }),
        );
        setEntries(withNeeds);
      })
      .catch(() => setError("Could not load the organization directory."));
  }, []);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Verified organizations</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every organization here has been verified by a SEVA-AI admin. Their active
          needs are shown below their profile.
        </p>
      </div>

      {error && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive" role="alert">
            {error}
          </CardContent>
        </Card>
      )}

      {!entries && !error && (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {entries && entries.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
            <p className="text-sm text-muted-foreground">
              No verified organizations yet. Check back soon.
            </p>
            <Button asChild size="sm" variant="outline">
              <Link to="/register">Register your organization</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {entries &&
        entries.map((org) => (
          <Card key={org.id}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                {org.name}
                <Badge variant="success" className="text-[10px]">
                  verified
                </Badge>
              </CardTitle>
              <CardDescription>
                {org.org_type ?? "Organization"}
                {org.address ? ` · ${org.address}` : ""}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {org.description && (
                <p className="text-sm text-muted-foreground">{org.description}</p>
              )}
              {org.needs && org.needs.length > 0 ? (
                <ul className="flex flex-col gap-1.5 text-sm">
                  {org.needs.map((need) => (
                    <li key={need.id} className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{need.title}</span>
                      <Badge
                        variant={
                          need.urgency === "critical"
                            ? "destructive"
                            : need.urgency === "high"
                              ? "warning"
                              : "secondary"
                        }
                        className="text-[10px]"
                      >
                        {need.urgency}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        needs {need.remaining_quantity} {need.unit}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">No active needs right now.</p>
              )}
            </CardContent>
          </Card>
        ))}
    </div>
  );
}
