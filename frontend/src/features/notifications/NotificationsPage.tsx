/** Notification center (M4) — list, unread count, mark read. */

import { Bell, CheckCheck } from "lucide-react";
import { toast } from "sonner";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/form-controls";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/workflow-api";
import type { NotificationsPageData } from "@/types/workflow";

export function NotificationsPage() {
  const [data, setData] = useState<NotificationsPageData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    listNotifications()
      .then(setData)
      .catch(() => setError("Could not load notifications."));
  }, []);

  useEffect(load, [load]);

  const markOne = async (id: string) => {
    try {
      await markNotificationRead(id);
      setData((current) =>
        current
          ? {
              ...current,
              unread: Math.max(0, current.unread - 1),
              items: current.items.map((n) => (n.id === id ? { ...n, read: true } : n)),
            }
          : current,
      );
    } catch {
      toast_error();
    }
  };

  const markAll = async () => {
    try {
      await markAllNotificationsRead();
      setData((current) =>
        current ? { ...current, unread: 0, items: current.items.map((n) => ({ ...n, read: true })) } : current,
      );
    } catch {
      toast_error();
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Bell className="h-6 w-6 text-primary" aria-hidden /> Notifications
        </h1>
        {data && data.unread > 0 && (
          <Button variant="outline" size="sm" onClick={markAll}>
            <CheckCheck aria-hidden /> Mark all read ({data.unread})
          </Button>
        )}
      </div>

      {error && (
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-4">
            <p role="alert" className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={load}>Retry</Button>
          </CardContent>
        </Card>
      )}

      {!data && !error && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}

      {data && data.items.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No notifications yet. Workflow updates (offers, pickups, payments) will
            appear here.
          </CardContent>
        </Card>
      )}

      {data && data.items.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <ul className="divide-y">
              {data.items.map((notification) => (
                <li
                  key={notification.id}
                  className={`flex items-start justify-between gap-3 px-4 py-3 ${
                    notification.read ? "" : "bg-accent/30"
                  }`}
                >
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 text-sm font-medium">
                      {notification.title}
                      {!notification.read && (
                        <Badge variant="warning" className="text-[10px]">new</Badge>
                      )}
                    </p>
                    {notification.body && (
                      <p className="mt-0.5 text-xs text-muted-foreground">{notification.body}</p>
                    )}
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      {new Date(notification.created_at).toLocaleString()}
                    </p>
                  </div>
                  {!notification.read && (
                    <Button variant="ghost" size="sm" onClick={() => markOne(notification.id)}>
                      Mark read
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function toast_error() {
  toast.error("The notification action failed. Please try again.");
}
