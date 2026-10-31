/** Route guard tests: RequireAuth and RequireRole (frontend half of §12.1/§12.4). */

import { render, screen, waitFor } from "@testing-library/react";
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

import { apiFetch } from "@/lib/api";
import { AuthProvider } from "@/features/auth/auth-context";
import { RequireAuth, RequireRole } from "@/routes/guards";
import { AUTH_RESPONSE, DONOR } from "./helpers";

const apiFetchMock = vi.mocked(apiFetch);

function renderWithRouter(ui: React.ReactElement, initialPath = "/account") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects anonymous visitors to /login and never renders protected content", async () => {
    renderWithRouter(
      <Routes>
        <Route element={<RequireAuth />}>
          <Route path="/account" element={<div>secret content</div>} />
        </Route>
        <Route path="/login" element={<div>login page</div>} />
      </Routes>,
    );

    await waitFor(() => {
      expect(screen.getByText("login page")).toBeInTheDocument();
    });
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    // No /me call is made without a stored token.
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("renders protected content for an authenticated user", async () => {
    localStorage.setItem("seva_token", "stored-token");
    apiFetchMock.mockResolvedValueOnce(DONOR);

    renderWithRouter(
      <Routes>
        <Route element={<RequireAuth />}>
          <Route path="/account" element={<div>secret content</div>} />
        </Route>
        <Route path="/login" element={<div>login page</div>} />
      </Routes>,
    );

    expect(await screen.findByText("secret content")).toBeInTheDocument();
    expect(screen.queryByText("login page")).not.toBeInTheDocument();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/auth/me");
  });

  it("clears the stored token and redirects when /me rejects (401)", async () => {
    localStorage.setItem("seva_token", "expired-token");
    apiFetchMock.mockRejectedValueOnce(new Error("401"));

    renderWithRouter(
      <Routes>
        <Route element={<RequireAuth />}>
          <Route path="/account" element={<div>secret content</div>} />
        </Route>
        <Route path="/login" element={<div>login page</div>} />
      </Routes>,
    );

    await waitFor(() => {
      expect(screen.getByText("login page")).toBeInTheDocument();
    });
    expect(localStorage.getItem("seva_token")).toBeNull();
  });
});

describe("RequireRole", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders children for a user with an allowed role", async () => {
    localStorage.setItem("seva_token", "stored-token");
    apiFetchMock.mockResolvedValueOnce(AUTH_RESPONSE.user);

    renderWithRouter(
      <RequireRole roles={["donor"]}>
        <div>donor area</div>
      </RequireRole>,
    );

    expect(await screen.findByText("donor area")).toBeInTheDocument();
  });

  it("denies a user whose role is not allowed", async () => {
    localStorage.setItem("seva_token", "stored-token");
    apiFetchMock.mockResolvedValueOnce(DONOR);

    renderWithRouter(
      <RequireRole roles={["admin"]}>
        <div>admin only content</div>
      </RequireRole>,
    );

    expect(await screen.findByText(/access denied/i)).toBeInTheDocument();
    expect(screen.queryByText("admin only content")).not.toBeInTheDocument();
  });
});
