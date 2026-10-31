import { LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";
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
import { useAuth } from "@/features/auth/auth-context";
import type { AccountStatus, UserRole } from "@/types/auth";

const ROLE_LABELS: Record<UserRole, string> = {
  donor: "Donor",
  organization: "Organization",
  admin: "Administrator",
};

const STATUS_VARIANTS: Record<
  AccountStatus,
  "success" | "warning" | "destructive"
> = {
  active: "success",
  inactive: "warning",
  suspended: "destructive",
};

/** Minimal authenticated home for M1. Role dashboards (donor, organization,
 * admin) arrive in M2–M5 and replace this page's content per milestone. */
export function AccountPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (!user) return null;

  const handleLogout = () => {
    logout();
    toast.success("Signed out");
    navigate("/", { replace: true });
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Hello, {user.full_name}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your account is active and signed in.
          </p>
        </div>
        <Button variant="outline" onClick={handleLogout}>
          <LogOut aria-hidden /> Log out
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>Details of your SEVA-AI account.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Email</span>
            <span className="font-medium">{user.email}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Role</span>
            <Badge variant="secondary">{ROLE_LABELS[user.role]}</Badge>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Status</span>
            <Badge variant={STATUS_VARIANTS[user.status]}>{user.status}</Badge>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>What comes next</CardTitle>
          <CardDescription>
            This milestone (M1) delivers accounts, sign-in, and role-based
            access. The next milestones add the working features for your role.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {user.role === "donor" && (
            <p>
              M2 adds donation creation with photos and AI category suggestions;
              M3 shows recommended organizations for your donations.
            </p>
          )}
          {user.role === "organization" && (
            <p>
              M2/M3 add the organization application and admin verification;
              after verification you can publish needs and receive offers.
            </p>
          )}
          {user.role === "admin" && (
            <p>
              M3 adds the verification queue for organization applications;
              M5 adds the admin overview dashboard.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
