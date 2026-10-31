/** Registration form tests: role toggle, validation, successful submit. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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

import { apiFetch } from "@/lib/api";
import { AuthProvider } from "@/features/auth/auth-context";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { AUTH_RESPONSE } from "./helpers";

const apiFetchMock = vi.mocked(apiFetch);

function renderRegister() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <RegisterPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("RegisterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders both role choices with donor preselected", () => {
    renderRegister();

    const donorRadio = screen.getByRole("radio", { name: "Donor" }) as HTMLInputElement;
    const orgRadio = screen.getByRole("radio", { name: "Organization" }) as HTMLInputElement;
    expect(donorRadio.checked).toBe(true);
    expect(orgRadio.checked).toBe(false);
  });

  it("allows switching to the organization role", async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.click(screen.getByRole("radio", { name: "Organization" }));
    const orgRadio = screen.getByRole("radio", { name: "Organization" }) as HTMLInputElement;
    expect(orgRadio.checked).toBe(true);
  });

  it("blocks submission when passwords do not match", async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText("Full name"), "Demo Donor");
    await user.type(screen.getByLabelText("Email"), "donor@example.com");
    await user.type(screen.getByLabelText(/^Password$/), "S3curePass!");
    await user.type(screen.getByLabelText("Confirm password"), "Different1!");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("blocks submission with a short password", async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText("Full name"), "Demo Donor");
    await user.type(screen.getByLabelText("Email"), "donor@example.com");
    await user.type(screen.getByLabelText(/^Password$/), "short");
    await user.type(screen.getByLabelText("Confirm password"), "short");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(
      await screen.findByText("Password must be at least 8 characters"),
    ).toBeInTheDocument();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("submits a valid donor registration to /api/auth/register", async () => {
    const user = userEvent.setup();
    apiFetchMock.mockResolvedValueOnce(AUTH_RESPONSE);
    renderRegister();

    await user.type(screen.getByLabelText("Full name"), "Demo Donor");
    await user.type(screen.getByLabelText("Email"), "donor@example.com");
    await user.type(screen.getByLabelText(/^Password$/), "S3curePass!");
    await user.type(screen.getByLabelText("Confirm password"), "S3curePass!");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(
        "/api/auth/register",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const [, options] = apiFetchMock.mock.calls[0];
    expect((options as { body: unknown }).body).toEqual({
      email: "donor@example.com",
      password: "S3curePass!",
      full_name: "Demo Donor",
      role: "donor",
    });
    expect(localStorage.getItem("seva_token")).toBe("test-access-token");
  });
});
