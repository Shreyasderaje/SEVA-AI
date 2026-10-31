/** Login form tests: validation and successful submit (frontend §15 coverage). */

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

import { ApiError, apiFetch } from "@/lib/api";
import { AuthProvider } from "@/features/auth/auth-context";
import { LoginPage } from "@/features/auth/LoginPage";
import { AUTH_RESPONSE } from "./helpers";

const apiFetchMock = vi.mocked(apiFetch);

function renderLogin() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows validation messages for empty fields and does not call the API", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("rejects an invalid email address", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.type(screen.getByLabelText("Password"), "Whatever123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("submits valid credentials to /api/auth/login", async () => {
    const user = userEvent.setup();
    apiFetchMock.mockResolvedValueOnce(AUTH_RESPONSE);
    renderLogin();

    await user.type(screen.getByLabelText("Email"), "donor@example.com");
    await user.type(screen.getByLabelText("Password"), "S3curePass!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(
        "/api/auth/login",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const [, options] = apiFetchMock.mock.calls[0];
    expect((options as { body: unknown }).body).toEqual({
      email: "donor@example.com",
      password: "S3curePass!",
    });
    // Token persisted for subsequent requests.
    expect(localStorage.getItem("seva_token")).toBe("test-access-token");
  });

  it("surfaces backend error messages (e.g. wrong password) as an alert", async () => {
    const user = userEvent.setup();
    apiFetchMock.mockRejectedValueOnce(
      new ApiError(401, "Incorrect email or password"),
    );
    renderLogin();

    await user.type(screen.getByLabelText("Email"), "donor@example.com");
    await user.type(screen.getByLabelText("Password"), "WrongPass123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Incorrect email or password",
    );
  });
});
