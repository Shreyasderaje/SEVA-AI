/** Need form tests (M3): validation + payload; matches display (factors,
 * distance fallback, empty state). */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
  apiFetch: vi.fn().mockResolvedValue({}),
}));

const createNeedMock = vi.fn();
const getNeedMock = vi.fn();

vi.mock("@/lib/donation-api", () => ({
  listCategories: vi.fn().mockResolvedValue([
    { id: "cat-clothing", code: "clothing", display_name: "Clothing", subcategories: [{ id: "sub-men", display_name: "Men's" }] },
    { id: "cat-other", code: "other", display_name: "Other", subcategories: [] },
  ]),
}));

vi.mock("@/lib/organization-api", () => ({
  createNeed: (...args: unknown[]) => createNeedMock(...args),
  updateNeed: vi.fn(),
  getNeed: (...args: unknown[]) => getNeedMock(...args),
  changeNeedStatus: vi.fn(),
  recordFulfilment: vi.fn(),
  getMyOrganization: vi.fn(),
  applyOrganization: vi.fn(),
  adminListOrganizations: vi.fn(),
  adminGetOrganization: vi.fn(),
  adminVerifyOrganization: vi.fn(),
  adminRejectOrganization: vi.fn(),
  adminSuspendOrganization: vi.fn(),
  listPublicOrganizations: vi.fn().mockResolvedValue([]),
  listPublicOrgNeeds: vi.fn().mockResolvedValue([]),
  listMyNeeds: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 }),
}));

import { apiFetch } from "@/lib/api";
import { NeedFormPage } from "@/features/organizations/NeedFormPage";
import { DonationMatches } from "@/features/donations/DonationMatches";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("NeedFormPage (create)", () => {
  function renderCreate() {
    return render(
      <MemoryRouter initialEntries={["/organization/needs/new"]}>
        <Routes>
          <Route path="/organization/needs/new" element={<NeedFormPage mode="create" />} />
          <Route path="/organization" element={<div>org dashboard</div>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("blocks submission without a category and with an invalid quantity", async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.type(screen.getByLabelText("Title"), "Blankets needed");
    await user.clear(screen.getByLabelText("Required quantity"));
    await user.type(screen.getByLabelText("Required quantity"), "0");
    await user.click(screen.getByRole("button", { name: /publish need/i }));

    expect(await screen.findByText("Choose a category")).toBeInTheDocument();
    expect(
      screen.getByText("Required quantity must be greater than zero"),
    ).toBeInTheDocument();
    expect(createNeedMock).not.toHaveBeenCalled();
  });

  it("submits a valid need with the category id", async () => {
    const user = userEvent.setup();
    createNeedMock.mockResolvedValueOnce({ id: "need-1", status: "active" });
    renderCreate();

    await user.type(screen.getByLabelText("Title"), "Blankets needed");
    await user.selectOptions(screen.getByLabelText("Category"), "clothing");
    await user.clear(screen.getByLabelText("Required quantity"));
    await user.type(screen.getByLabelText("Required quantity"), "20");
    await user.selectOptions(screen.getByLabelText("Urgency"), "high");
    await user.click(screen.getByRole("button", { name: /publish need/i }));

    await waitFor(() => expect(createNeedMock).toHaveBeenCalledTimes(1));
    const payload = createNeedMock.mock.calls[0][0];
    expect(payload.category_id).toBe("cat-clothing");
    expect(payload.quantity_required).toBe(20);
    expect(payload.urgency).toBe("high");
    expect(await screen.findByText("org dashboard")).toBeInTheDocument();
  });
});

describe("DonationMatches", () => {
  it("shows factor scores and reasons for eligible organizations", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      donation_id: "d-1",
      service_radius_km: 50,
      eligible: [
        {
          rank: 1,
          organization_id: "org-1",
          organization_name: "Hope Trust",
          verification_status: "verified",
          need_id: "need-1",
          need_title: "Blankets for winter",
          need_category_code: "clothing",
          remaining_quantity: 12,
          unit: "pieces",
          distance_km: 8.74,
          score: 83.4,
          factors: {
            compatibility: { score: 1, weight: 0.3, weighted: 0.3 },
            urgency: { score: 0.75, weight: 0.25, weighted: 0.1875 },
            distance: { score: 0.8252, weight: 0.2, weighted: 0.165 },
            quantity_fit: { score: 0.5, weight: 0.15, weighted: 0.075 },
            timeliness: { score: 1, weight: 0.1, weighted: 0.1 },
          },
          reasons: [
            "Verified organization with an active need for clothing.",
            "Need urgency is critical.",
            "About 8.7 km away from the pickup area.",
          ],
        },
      ],
      excluded: [{ reason_code: "organization_not_verified", count: 2 }],
    });

    render(
      <MemoryRouter>
        <DonationMatches donationId="d-1" />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Hope Trust")).toBeInTheDocument();
    expect(screen.getByText("83.4")).toBeInTheDocument();
    expect(screen.getByText(/1\.00 × 0\.30 = 0\.30/)).toBeInTheDocument();
    expect(screen.getByText(/About 8\.7 km away/i)).toBeInTheDocument();
    expect(screen.queryByText(/Distance could not be calculated/i)).not.toBeInTheDocument();
  });

  it("shows the explicit fallback when distance cannot be calculated", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      donation_id: "d-1",
      service_radius_km: 50,
      eligible: [
        {
          rank: 1,
          organization_id: "org-1",
          organization_name: "Neutral Org",
          verification_status: "verified",
          need_id: "need-1",
          need_title: "Need without distance",
          need_category_code: "other",
          remaining_quantity: 5,
          unit: "kg",
          distance_km: null,
          score: 55.0,
          factors: {
            compatibility: { score: 1, weight: 0.3, weighted: 0.3 },
            urgency: { score: 0.5, weight: 0.25, weighted: 0.125 },
            distance: { score: 0.5, weight: 0.2, weighted: 0.1 },
            quantity_fit: { score: 0.5, weight: 0.15, weighted: 0.075 },
            timeliness: { score: 0.5, weight: 0.1, weighted: 0.05 },
          },
          reasons: ["Distance could not be calculated."],
        },
      ],
      excluded: [],
    });

    render(
      <MemoryRouter>
        <DonationMatches donationId="d-1" />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/Distance could not be calculated\./),
    ).toBeInTheDocument();
    expect(screen.getByText(/0\.50 × 0\.20 = 0\.10/)).toBeInTheDocument();
    expect(screen.queryByText(/km away/)).not.toBeInTheDocument();
  });

  it("shows a meaningful empty state when nothing is eligible", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      donation_id: "d-1",
      service_radius_km: 50,
      eligible: [],
      excluded: [
        { reason_code: "organization_not_verified", count: 3 },
        { reason_code: "category_incompatible", count: 1 },
      ],
    });

    render(
      <MemoryRouter>
        <DonationMatches donationId="d-1" />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/No eligible organizations right now\./),
    ).toBeInTheDocument();
    expect(screen.getByText(/3 unverified organizations/)).toBeInTheDocument();
    expect(screen.getByText(/1 incompatible need categories/)).toBeInTheDocument();
  });
});
