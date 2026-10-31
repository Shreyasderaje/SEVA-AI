/** Route guards. Backend authorization remains the source of truth; these
 * guards only shape the UI (§5: hiding a button is not authorization). */

import { Loader2, ShieldAlert } from "lucide-react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/features/auth/auth-context";
import type { UserRole } from "@/types/auth";

export function FullScreenSpinner() {
  return (
    <div
      className="flex min-h-[50vh] items-center justify-center"
      role="status"
      aria-label="Loading"
    >
      <Loader2 className="h-6 w-6 animate-spin text-primary" />
    </div>
  );
}

/** Allows any authenticated user through; redirects anonymous visitors to login. */
export function RequireAuth() {
  const { user, initializing } = useAuth();
  const location = useLocation();

  if (initializing) return <FullScreenSpinner />;
  if (!user) {
    return (
      <Navigate to="/login" replace state={{ from: location.pathname }} />
    );
  }
  return <Outlet />;
}

/** Blocks users whose role is not in `roles` with an honest 403-style card. */
export function RequireRole({
  roles,
  children,
}: {
  roles: UserRole[];
  children?: ReactNode;
}) {
  const { user } = useAuth();

  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-destructive" aria-hidden />
            Access denied
          </CardTitle>
          <CardDescription>
            This area is available to {roles.join(" or ")} accounts only. You are
            signed in as a {user.role}.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="outline">
            <a href="/">Go to the home page</a>
          </Button>
        </CardContent>
      </Card>
    );
  }
  return <>{children}</>;
}
