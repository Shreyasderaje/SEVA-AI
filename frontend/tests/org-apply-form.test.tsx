/** Organization application form tests (M3). */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const applyMock = vi.fn();

vi.mock("@/lib/organization-api", () => ({
  applyOrganization: (...args: unknown[]) => applyMock(...args),
  getMyOrganization: vi.fn(),
  adminListOrganizations: vi.fn(),
  adminGetOrganization: vi.fn(),
  adminVerifyOrganization: vi.fn(),
  adminRejectOrganization: vi.fn(),
  adminSuspendOrganization: vi.fn(),
  listPublicOrganizations: vi.fn().mockResolvedValue([]),
  listPublicOrgNeeds: vi.fn().mockResolvedValue([]),
  listMyNeeds: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 }),
  changeNeedStatus: vi.fn(),
  recordFulfilment: vi.fn(),
  createNeed: vi.fn(),
  updateNeed: vi.fn(),
  getNeed: vi.fn(),
}));


import { AuthProvider } from "@/features/auth/auth-context";
import { OrgApplyPage } from "@/features/organizations/OrgApplyPage";


function makePdf(name = "registration.pdf") {
  return new File(["%PDF-1.4 fake"], name, { type: "application/pdf" });
}

function renderForm() {
  return render(
    <MemoryRouter initialEntries={["/organization/apply"]}>
      <AuthProvider>
        <Routes>
          <Route path="/organization/apply" element={<OrgApplyPage />} />
          <Route path="/organization" element={<div>org dashboard</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Organization name"), "Hope Charitable Trust");
  await user.type(screen.getByLabelText("Address"), "12 Seva Road, Springfield");
  await user.type(screen.getByLabelText("Contact email"), "contact@example.org");
  await user.type(screen.getByLabelText("Representative"), "Rep Person");
}

beforeEach(() => {
  vi.clearAllMocks();
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
});

describe("OrgApplyPage", () => {
  it("blocks submission without a verification document", async () => {
    const user = userEvent.setup();
    renderForm();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /submit application/i }));

    expect(
      await screen.findByText(/Attach a verification document/i),
    ).toBeInTheDocument();
    expect(applyMock).not.toHaveBeenCalled();
  });

  it("submits a complete application with the document and consent fields", async () => {
    const user = userEvent.setup();
    applyMock.mockResolvedValueOnce({ id: "org-1", verification_status: "pending_verification" });
    const { container } = renderForm();

    await fillValidForm(user);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makePdf()] } });

    await user.click(screen.getByLabelText(/provide exact map coordinates/i));
    await user.type(screen.getByLabelText("Latitude"), "12.9716");
    await user.type(screen.getByLabelText("Longitude"), "77.5946");
    await user.click(screen.getByLabelText(/consent to SEVA-AI storing these coordinates/i));

    await user.click(screen.getByRole("button", { name: /submit application/i }));

    await waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1));
    const payload = applyMock.mock.calls[0][0] as {
      name: string;
      latitude?: number;
      location_consent: boolean;
      document: File;
    };
    expect(payload.name).toBe("Hope Charitable Trust");
    expect(payload.latitude).toBe(12.9716);
    expect(payload.location_consent).toBe(true);
    expect(payload.document).toBeInstanceOf(File);
    expect(await screen.findByText("org dashboard")).toBeInTheDocument();
  });

  it("requires both coordinates and consent together", async () => {
    const user = userEvent.setup();
    const { container } = renderForm();
    await fillValidForm(user);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makePdf()] } });

    await user.click(screen.getByLabelText(/provide exact map coordinates/i));
    await user.type(screen.getByLabelText("Latitude"), "12.9716");
    await user.type(screen.getByLabelText("Longitude"), "77.5946");
    // Consent NOT ticked.
    await user.click(screen.getByRole("button", { name: /submit application/i }));

    expect(
      await screen.findByText(/consent box to store them/i),
    ).toBeInTheDocument();
    expect(applyMock).not.toHaveBeenCalled();
  });
});
