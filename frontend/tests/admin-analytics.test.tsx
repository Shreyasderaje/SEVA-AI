/** M5 frontend tests: analytics page render/filter/empty/error + demo badges. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const analyticsMocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  TOKEN_STORAGE_KEY: "seva_token",
  getStoredToken: () => localStorage.getItem("seva_token"),
  setStoredToken: () => {},
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  apiFetch: (...args: unknown[]) => analyticsMocks.apiFetch(...args),
}));

import { AdminAnalyticsPage } from "@/features/admin/AdminAnalyticsPage";

const FULL_ANALYTICS = {
  range_days: 30,
  generated_at: "2026-11-01T00:00:00",
  cards: {
    total_donors: 3, total_organizations: 2, verified_organizations: 1,
    pending_organizations: 1, total_donations: 2, pending_donations: 1,
    completed_donations: 1, active_needs: 2, fulfilled_needs: 0,
    offers_sent: 1, offers_accepted: 0,
    payments_awaiting_verification: 1,
  },
  donations_over_time: [{ week: "2026-W44", count: 2 }],
  donation_status: [{ status: "pending", count: 1 }, { status: "completed", count: 1 }],
  donation_category: [{ category: "clothing", count: 2 }],
  org_verification: [
    { status: "verified", count: 1 },
    { status: "pending_verification", count: 1 },
  ],
  offer_outcomes: [{ status: "declined", count: 1 }],
  needs_status: [{ status: "active", count: 2 }],
  demo_data: { users: 3, donations: 2, organizations: 2, payments: 1 },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminAnalyticsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AdminAnalyticsPage", () => {
  it("renders summary cards and chart sections from DB-backed data", async () => {
    analyticsMocks.apiFetch.mockResolvedValueOnce(FULL_ANALYTICS);
    renderPage();

    expect(await screen.findByText("Analytics overview")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument(); // donors card
    expect(screen.getByText("Donations over time")).toBeInTheDocument();
    expect(screen.getByText("Donation status distribution")).toBeInTheDocument();
    expect(screen.getByText("Organization verification")).toBeInTheDocument();
    // Range selector reflects the applied filter.
    expect(screen.getByLabelText("Date range")).toHaveValue("30");
  });

  it("re-queries when the date range changes", async () => {
    const user = userEvent.setup();
    analyticsMocks.apiFetch.mockResolvedValue(FULL_ANALYTICS);
    renderPage();
    await screen.findByText("Donations over time");

    await user.selectOptions(screen.getByLabelText("Date range"), "7");
    await waitFor(() => {
      expect(analyticsMocks.apiFetch).toHaveBeenCalledWith("/api/admin/analytics?days=7");
    });
  });

  it("shows zero-valued metrics for an empty database", async () => {
    analyticsMocks.apiFetch.mockResolvedValueOnce({
      range_days: null,
      generated_at: "2026-11-01T00:00:00",
      cards: Object.fromEntries(
        Object.keys(FULL_ANALYTICS.cards).map((key) => [key, 0]),
      ),
      donations_over_time: [],
      donation_status: [],
      donation_category: [],
      org_verification: [],
      offer_outcomes: [],
      needs_status: [],
      demo_data: { users: 0, donations: 0, organizations: 0, payments: 0 },
    });
    renderPage();

    expect(await screen.findByText("No donations in this period.")).toBeInTheDocument();
    expect(screen.getAllByText(/No data in this period\./).length).toBeGreaterThan(0);
    expect(screen.getByText("No demo data in this database")).toBeInTheDocument();
  });

  it("shows an error state with retry on API failure", async () => {
    const user = userEvent.setup();
    analyticsMocks.apiFetch.mockRejectedValueOnce(new Error("network down"));
    renderPage();

    expect(
      await screen.findByText(/Could not load the analytics overview\./),
    ).toBeInTheDocument();

    analyticsMocks.apiFetch.mockResolvedValueOnce(FULL_ANALYTICS);
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("Donations over time")).toBeInTheDocument();
  });

  it("labels demo-data aggregates with DEMO badges", async () => {
    analyticsMocks.apiFetch.mockResolvedValueOnce(FULL_ANALYTICS);
    renderPage();
    expect(await screen.findByText("DEMO donations: 2")).toBeInTheDocument();
    expect(screen.getByText("DEMO users: 3")).toBeInTheDocument();
  });
});
