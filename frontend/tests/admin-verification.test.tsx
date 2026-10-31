/** Admin verification UI tests (M3): approve, reject-with-reason. */

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

const detailMock = vi.fn();
const verifyMock = vi.fn();
const rejectMock = vi.fn();

vi.mock("@/lib/organization-api", () => ({
  adminGetOrganization: (...args: unknown[]) => detailMock(...args),
  adminVerifyOrganization: (...args: unknown[]) => verifyMock(...args),
  adminRejectOrganization: (...args: unknown[]) => rejectMock(...args),
  adminSuspendOrganization: vi.fn(),
  applyOrganization: vi.fn(),
  getMyOrganization: vi.fn(),
  adminListOrganizations: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 }),
  listPublicOrganizations: vi.fn().mockResolvedValue([]),
  listPublicOrgNeeds: vi.fn().mockResolvedValue([]),
  listMyNeeds: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 }),
  changeNeedStatus: vi.fn(),
  recordFulfilment: vi.fn(),
  createNeed: vi.fn(),
  updateNeed: vi.fn(),
  getNeed: vi.fn(),
}));

import { AdminOrgDetailPage } from "@/features/admin/AdminOrgDetailPage";


const PENDING = {
  id: "org-1",
  name: "Hope Charitable Trust",
  org_type: "ngo",
  description: "We serve.",
  address: "12 Seva Road",
  verification_status: "pending_verification",
  rejection_reason: null,
  verified_at: null,
  created_at: "2026-11-01T00:00:00",
  latitude: null,
  longitude: null,
  contact_email: "contact@example.org",
  contact_phone: null,
  representative_name: "Rep Person",
  owner_user_id: "user-1",
  document_id: "doc-1",
  document_url: "/api/organizations/org-1/verification-document",
};

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/admin/organizations/org-1"]}>
      <Routes>
        <Route path="/admin/organizations/:id" element={<AdminOrgDetailPage />} />
        <Route path="/admin/organizations" element={<div>org list</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  detailMock.mockResolvedValue(PENDING);
});

describe("AdminOrgDetailPage", () => {
  it("shows application details and the authorized document link", async () => {
    renderDetail();
    expect(await screen.findByText("Hope Charitable Trust")).toBeInTheDocument();
    const link = screen.getByText(/Open document \(authorized link\)/);
    expect(link.getAttribute("href")).toBe("/api/organizations/org-1/verification-document");
  });

  it("approves without a reason and shows the updated status", async () => {
    const user = userEvent.setup();
    verifyMock.mockResolvedValueOnce({ ...PENDING, verification_status: "verified", verified_at: "2026-11-01T01:00:00" });
    renderDetail();
    await screen.findByText("Hope Charitable Trust");

    await user.click(screen.getByRole("button", { name: /approve/i }));
    await user.click(screen.getByRole("button", { name: /confirm/i }));

    await waitFor(() => expect(verifyMock).toHaveBeenCalledWith("org-1"));
    expect(await screen.findByText("verified")).toBeInTheDocument();
  });

  it("rejects only with a reason", async () => {
    const user = userEvent.setup();
    renderDetail();
    await screen.findByText("Hope Charitable Trust");

    await user.click(screen.getByRole("button", { name: /reject/i }));
    // Confirm WITHOUT a reason -> blocked client-side.
    await user.click(screen.getByRole("button", { name: /confirm/i }));
    expect(
      await screen.findByText(/A reason is required/i),
    ).toBeInTheDocument();
    expect(rejectMock).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Reason"), "Address could not be verified");
    rejectMock.mockResolvedValueOnce({ ...PENDING, verification_status: "rejected", rejection_reason: "Address could not be verified" });
    await user.click(screen.getByRole("button", { name: /confirm/i }));

    await waitFor(() =>
      expect(rejectMock).toHaveBeenCalledWith("org-1", "Address could not be verified"),
    );
  });
});
