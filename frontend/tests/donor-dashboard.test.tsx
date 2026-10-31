/** Donor dashboard tests: DB-backed cards, recent list, empty and error states. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  TOKEN_STORAGE_KEY: "seva_token",
  getStoredToken: () => localStorage.getItem("seva_token"),
  setStoredToken: (token: string | null) => {
    if (token) localStorage.setItem("seva_token", token);
    else localStorage.removeItem("seva_token");
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  apiFetch: vi.fn(),
}));

const SUMMARY = { active: 2, accepted: 1, completed: 3, total: 6 };

const DONATION: DonationSummary = {
  id: "d-1",
  reference: "SEVA-2026-000042",
  title: "Winter jackets",
  status: "accepted",
  quantity: 5,
  unit: "pieces",
  category_code: "clothing",
  category_display_name: "Clothing",
  subcategory_display_name: null,
  ai_predicted_category: null,
  ai_confidence: null,
  primary_image_url: null,
  created_at: "2026-10-31T00:00:00",
};

vi.mock("@/lib/donation-api", () => ({
  donationSummary: vi.fn(),
  listMyDonations: vi.fn(),
  listCategories: vi.fn().mockResolvedValue([]),
  createDonation: vi.fn(),
  cancelDonation: vi.fn(),
  getDonation: vi.fn(),
  classifyImage: vi.fn(),
}));

import { donationSummary, listMyDonations } from "@/lib/donation-api";
import { AuthProvider } from "@/features/auth/auth-context";
import { DonorDashboardPage } from "@/features/donor/DonorDashboardPage";
import type { DonationSummary } from "@/types/donations";

const summaryMock = vi.mocked(donationSummary);
const listMock = vi.mocked(listMyDonations);

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <AuthProvider>
        <Routes>
          <Route path="/dashboard" element={<DonorDashboardPage />} />
          <Route path="/donations" element={<div>donations list page</div>} />
          <Route path="/donations/new" element={<div>create page</div>} />
          <Route path="/login" element={<div>login page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  // No token in localStorage: AuthProvider skips its /me boot call, which the
  // dashboard tests don't exercise anyway.
  summaryMock.mockResolvedValue(SUMMARY);
});

describe("DonorDashboardPage", () => {
  it("shows real database-backed summary counts and recent donations", async () => {
    listMock.mockResolvedValue({
      items: [DONATION],
      total: 6,
      page: 1,
      page_size: 5,
    });
    renderDashboard();

    // Cards show the exact counts from the API (no hard-coded values).
    // Count titles live in .text-3xl elements — one per summary card.
    await screen.findByText("2", { selector: ".text-3xl" });
    expect(screen.getByText("1", { selector: ".text-3xl" })).toBeInTheDocument();
    expect(screen.getByText("3", { selector: ".text-3xl" })).toBeInTheDocument();

    expect(await screen.findByText("Winter jackets")).toBeInTheDocument();
    expect(screen.getByText(/SEVA-2026-000042/)).toBeInTheDocument();
    expect(screen.getByText("accepted")).toBeInTheDocument();
  });

  it("shows an actionable empty state for a new donor", async () => {
    listMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 5 });
    renderDashboard();

    expect(
      await screen.findByText(/donations yet/i, { selector: "p" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /create your first donation/i }),
    ).toBeInTheDocument();
  });

  it("shows an error state with retry when the API fails", async () => {
    summaryMock.mockRejectedValueOnce(new Error("network down"));
    listMock.mockRejectedValueOnce(new Error("network down"));
    renderDashboard();

    expect(
      await screen.findByText(/could not load your dashboard/i),
    ).toBeInTheDocument();

    summaryMock.mockResolvedValue(SUMMARY);
    listMock.mockResolvedValue({ items: [DONATION], total: 1, page: 1, page_size: 5 });
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => {
      expect(screen.getByText("Winter jackets")).toBeInTheDocument();
    });
  });

  it("links to the full history page", async () => {
    listMock.mockResolvedValue({ items: [DONATION], total: 6, page: 1, page_size: 5 });
    renderDashboard();
    await screen.findByText("Winter jackets");

    const link = screen.getByRole("link", { name: /view all/i });
    expect(link.getAttribute("href")).toBe("/donations");
  });
});
