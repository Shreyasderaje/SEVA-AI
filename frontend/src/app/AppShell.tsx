import { Bell, HandHeart, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-context";
import { listNotifications } from "@/lib/workflow-api";

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [unread, setUnread] = useState<number | null>(null);

  // Unread notification badge: polled lightly while signed in (§7 in-app only).
  useEffect(() => {
    if (!user) {
      setUnread(null);
      return;
    }
    let cancelled = false;
    const refresh = () =>
      listNotifications()
        .then((data) => {
          if (!cancelled) setUnread(data.unread);
        })
        .catch(() => undefined);
    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [user, unread === 0]);

  const handleLogout = () => {
    logout();
    navigate("/", { replace: true });
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4">
          <Link
            to="/"
            className="flex items-center gap-2 text-lg font-semibold tracking-tight"
          >
            <HandHeart className="h-6 w-6 text-primary" aria-hidden />
            SEVA-AI
          </Link>
          <nav className="flex items-center gap-2" aria-label="Main navigation">
            {user === null ? (
              <>
                <Button asChild variant="ghost">
                  <Link to="/login">Sign in</Link>
                </Button>
                <Button asChild>
                  <Link to="/register">Register</Link>
                </Button>
              </>
            ) : (
              <>
                <span className="mr-1 hidden text-sm text-muted-foreground sm:inline">
                  {user.full_name}
                </span>
                <Button asChild variant="ghost" aria-label={`Notifications (${unread ?? 0} unread)`}>
                  <Link to="/notifications" className="relative">
                    <Bell className="h-4 w-4" aria-hidden />
                    {unread !== null && unread > 0 && (
                      <span className="absolute -right-1 -top-1 rounded-full bg-destructive px-1.5 text-[10px] font-semibold text-destructive-foreground">
                        {unread}
                      </span>
                    )}
                  </Link>
                </Button>
                <Button asChild variant="ghost">
                  <Link
                    to={
                      user.role === "donor"
                        ? "/dashboard"
                        : user.role === "organization"
                          ? "/organization"
                          : "/admin/organizations"
                    }
                  >
                    {user.role === "donor"
                      ? "Dashboard"
                      : user.role === "organization"
                        ? "Organization"
                        : "Admin"}
                  </Link>
                </Button>
                <Button variant="outline" size="sm" onClick={handleLogout}>
                  <LogOut aria-hidden /> Log out
                </Button>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>

      <footer className="border-t bg-muted/40">
        <div className="mx-auto w-full max-w-6xl px-4 py-6 text-sm text-muted-foreground">
          SEVA-AI — AI-Powered Smart Donation and Charity Resource Management
          System. A college mini project; demo data is synthetic. Payments (in a
          later milestone) happen in your own UPI app — this site does not
          process payments.
        </div>
      </footer>
    </div>
  );
}
