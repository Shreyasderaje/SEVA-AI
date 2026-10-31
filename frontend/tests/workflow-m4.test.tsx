/** M4 frontend tests: notifications page, org offer actions, donor payment panel. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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

const NOTIFICATIONS = {
  items: [
    { id: "n1", type: "offer_received", title: "New donation offer: Jackets", body: "10 pieces — match score 92.0.", link: "/organization/offers", read: false, created_at: "2026-11-01T00:00:00" },
    { id: "n2", type: "offer_sent", title: "Offer sent", body: null, link: "/donations/d1", read: true, created_at: "2026-11-01T00:00:00" },
  ],
  total: 2,
  unread: 1,
  page: 1,
  page_size: 10,
};

const listNotificationsMock = vi.fn().mockResolvedValue(NOTIFICATIONS);
const markOneMock = vi.fn().mockResolvedValue({ message: "ok" });
const markAllMock = vi.fn().mockResolvedValue({ message: "ok" });
const acceptMock = vi.fn();
const declineMock = vi.fn();

const workflowMocks = vi.hoisted(() => ({
  listMyOffers: vi.fn(),
  getDonationPaymentInfo: vi.fn(),
  submitPayment: vi.fn(),
  listMyPayments: vi.fn(),
}));

vi.mock("@/lib/workflow-api", () => ({
  listNotifications: (...args: unknown[]) => listNotificationsMock(...args),
  markNotificationRead: (...args: unknown[]) => markOneMock(...args),
  markAllNotificationsRead: (...args: unknown[]) => markAllMock(...args),
  initiateOffer: vi.fn(),
  listMyOffers: (...args: unknown[]) => workflowMocks.listMyOffers(...args),
  listDonationOffers: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 }),
  acceptOffer: (...args: unknown[]) => acceptMock(...args),
  declineOffer: (...args: unknown[]) => declineMock(...args),
  schedulePickup: vi.fn(),
  markPickedUp: vi.fn(),
  completeOffer: vi.fn(),
  submitUpiSetup: vi.fn(),
  getUpiSetup: vi.fn().mockResolvedValue({ upi_id: null, upi_status: "none", has_qr: false }),
  getDonationPaymentInfo: (...args: unknown[]) =>
    workflowMocks.getDonationPaymentInfo(...args),
  submitPayment: (...args: unknown[]) => workflowMocks.submitPayment(...args),
  listMyPayments: (...args: unknown[]) => workflowMocks.listMyPayments(...args),
  adminListPayments: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 }),
  adminVerifyPayment: vi.fn(),
  adminRejectPayment: vi.fn(),
}));

import { NotificationsPage } from "@/features/notifications/NotificationsPage";
import { OrgOffersPage } from "@/features/organizations/OrgOffersPage";
import { DonationPaymentSection } from "@/features/donations/DonationWorkflowPanels";
import { AuthProvider } from "@/features/auth/auth-context";

beforeEach(() => {
  vi.clearAllMocks();
  listNotificationsMock.mockResolvedValue(NOTIFICATIONS);
});

describe("NotificationsPage", () => {
  it("lists notifications with unread count and marks one read", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AuthProvider>
          <NotificationsPage />
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("New donation offer: Jackets")).toBeInTheDocument();
    expect(screen.getByText(/Mark all read \(1\)/)).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: /mark read$/i })[0]);
    await waitFor(() => expect(markOneMock).toHaveBeenCalledWith("n1"));
  });

  it("marks all notifications read", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AuthProvider>
          <NotificationsPage />
        </AuthProvider>
      </MemoryRouter>,
    );
    await screen.findByText("New donation offer: Jackets");
    await user.click(screen.getByRole("button", { name: /mark all read/i }));
    await waitFor(() => expect(markAllMock).toHaveBeenCalled());
  });
});

describe("OrgOffersPage", () => {
  it("shows an incoming offer with the matching snapshot and accepts it", async () => {
    const user = userEvent.setup();
    workflowMocks.listMyOffers.mockResolvedValue({
      items: [{
        id: "offer-1", donation_id: "d-1", organization_id: "org-1",
        organization_name: "Hope Trust", status: "sent", score: 92,
        rank_at_offer: 1,
        factor_snapshot: {
          factors: { compatibility: { score: 1, weight: 0.3, weighted: 0.3 } },
          reasons: ["Verified organization with an active need for clothing."],
          service_radius_km: 50, distance_km: null,
        },
        reason_text: "Verified organization with an active need for clothing.",
        decline_reason: null, quantity_received: null,
        pickup_date: null, pickup_window_start: null, pickup_window_end: null,
        pickup_instructions: null, responded_at: null, created_at: "2026-11-01T00:00:00",
        donation_title: "Winter jackets", donation_reference: "SEVA-2026-000009",
        donation_quantity: 10, donation_unit: "pieces",
      }],
      total: 1, page: 1, page_size: 10,
    });
    acceptMock.mockResolvedValueOnce({ id: "offer-1", status: "accepted", score: 92, factor_snapshot: null });
    render(
      <MemoryRouter initialEntries={["/organization/offers"]}>
        <AuthProvider>
          <OrgOffersPage />
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Winter jackets")).toBeInTheDocument();
    expect(screen.getByText(/Match score/)).toBeInTheDocument();
    expect(screen.getByText(/Verified organization with an active need/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /accept/i }));
    await waitFor(() => expect(acceptMock).toHaveBeenCalledWith("offer-1"));
  });

  it("asks for an optional reason when declining", async () => {
    workflowMocks.listMyOffers.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });
    render(
      <MemoryRouter initialEntries={["/organization/offers"]}>
        <AuthProvider>
          <OrgOffersPage />
        </AuthProvider>
      </MemoryRouter>,
    );
    await screen.findByText(/No offers yet/);
    expect(screen.queryByRole("button", { name: /accept/i })).not.toBeInTheDocument();
  });
});

describe("DonationPaymentSection", () => {
  it("hides itself when payment details are not available (404)", async () => {
    workflowMocks.getDonationPaymentInfo.mockRejectedValue(new Error("not available"));
    workflowMocks.listMyPayments.mockResolvedValue([]);
    render(
      <MemoryRouter>
        <DonationPaymentSection donationId="d-1" />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.queryByText(/UPI ID/i)).not.toBeInTheDocument());
  });

  it("shows approved UPI details, the disclaimer, and submits the reference", async () => {
    const user = userEvent.setup();
    workflowMocks.getDonationPaymentInfo.mockResolvedValue({
      organization_id: "org-1",
      organization_name: "Hope Trust",
      upi_id: "hopetrust@okbank",
      qr_url: null,
      instructions: "Payment happens in your own UPI app, outside SEVA-AI.",
    });
    workflowMocks.submitPayment.mockResolvedValue({ id: "p1", status: "submitted_unverified" });
    workflowMocks.listMyPayments.mockResolvedValue([]);
    render(<DonationPaymentSection donationId="d-1" />);

    expect(await screen.findByText("hopetrust@okbank")).toBeInTheDocument();
    expect(screen.getByText(/outside SEVA-AI/, { selector: "p" })).toBeInTheDocument();

    await user.type(screen.getByLabelText("Transaction reference"), "REF12345678");
    await user.click(screen.getByRole("button", { name: /submit reference/i }));
    await waitFor(() => {
      expect(workflowMocks.submitPayment).toHaveBeenCalled();
    });
    expect(workflowMocks.submitPayment).toHaveBeenCalledWith(
      expect.objectContaining({ transaction_reference: "REF12345678", organization_id: "org-1" }),
    );
  });

  it("validates the transaction reference format", async () => {
    const user = userEvent.setup();
    workflowMocks.getDonationPaymentInfo.mockResolvedValue({
      organization_id: "org-1", organization_name: "Hope Trust",
      upi_id: "hopetrust@okbank", qr_url: null, instructions: "Pay outside.",
    });
    workflowMocks.listMyPayments.mockResolvedValue([]);
    render(<DonationPaymentSection donationId="d-1" />);
    await screen.findByText("hopetrust@okbank");
    await user.type(screen.getByLabelText("Transaction reference"), "AB1");
    await user.click(screen.getByRole("button", { name: /submit reference/i }));
    expect(await screen.findByText(/6–40 letters\/digits/i)).toBeInTheDocument();
  });
});