/** Shared test fixtures. NOTE: the `@/lib/api` mock must be declared inline in
 * each test file — `vi.mock` is hoisted per test file and cannot delegate its
 * factory to an imported helper without hitting TDZ at hoist time. */

import type { User } from "@/types/auth";

export const DONOR: User = {
  id: "user-donor-1",
  email: "donor@example.com",
  full_name: "Demo Donor",
  role: "donor",
  status: "active",
  created_at: "2026-10-31T00:00:00",
};

export const AUTH_RESPONSE = {
  access_token: "test-access-token",
  token_type: "bearer",
  user: DONOR,
};
