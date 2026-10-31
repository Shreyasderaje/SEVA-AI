/** Create-donation form tests: AI suggestion confirmation flow, model-not-
 * configured fallback, validation, and submission payload (M2 requirements 4-7). */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

vi.mock("@/lib/donation-api", () => ({
  listCategories: vi.fn().mockResolvedValue([
    {
      id: "cat-clothing",
      code: "clothing",
      display_name: "Clothing",
      subcategories: [{ id: "sub-men", display_name: "Men's" }],
    },
    {
      id: "cat-other",
      code: "other",
      display_name: "Other",
      subcategories: [{ id: "sub-misc", display_name: "Miscellaneous" }],
    },
  ]),
  classifyImage: vi.fn(),
  createDonation: vi.fn(),
}));

import { classifyImage, createDonation } from "@/lib/donation-api";
import { AuthProvider } from "@/features/auth/auth-context";
import { CreateDonationPage } from "@/features/donations/CreateDonationPage";
import type { DonationDetail } from "@/types/donations";

const classifyMock = vi.mocked(classifyImage);
const createMock = vi.mocked(createDonation);

function makeImageFile(name = "photo.jpg") {
  return new File(["fake-image-bytes"], name, { type: "image/jpeg" });
}

const CREATED: DonationDetail = {
  id: "donation-1",
  reference: "SEVA-2026-000001",
  title: "Winter jackets",
  status: "pending",
  quantity: 5,
  unit: "pieces",
  category_code: "clothing",
  category_display_name: "Clothing",
  subcategory_display_name: null,
  ai_predicted_category: "clothing",
  ai_confidence: 0.91,
  primary_image_url: "/api/images/img1",
  created_at: "2026-10-31T00:00:00",
  description: null,
  condition: "good",
  pickup_area: "Green Park",
  pickup_latitude: null,
  pickup_longitude: null,
  location_consent: false,
  pickup_window_start: null,
  pickup_window_end: null,
  images: [
    { id: "img1", position: 1, mime_type: "image/jpeg", size_bytes: 100, url: "/api/images/img1" },
  ],
  timeline: [],
};

function renderForm() {
  return render(
    <MemoryRouter initialEntries={["/donations/new"]}>
      <AuthProvider>
        <Routes>
          <Route path="/donations/new" element={<CreateDonationPage />} />
          <Route path="/donations/:id" element={<div>donation detail page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Title"), "Winter jackets");
  await user.clear(screen.getByLabelText("Quantity"));
  await user.type(screen.getByLabelText("Quantity"), "5");
  await user.type(screen.getByLabelText("Approximate pickup area"), "Green Park");
}

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom lacks createObjectURL; the component uses it for previews.
  URL.createObjectURL = vi.fn(() => "blob:mock-preview");
  URL.revokeObjectURL = vi.fn();
});

describe("CreateDonationPage — AI suggestion flow", () => {
  it("shows the model_not_configured banner and allows manual selection", async () => {
    const user = userEvent.setup();
    classifyMock.mockResolvedValue({ status: "model_not_configured" });
    const { container } = renderForm();

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeImageFile()] } });

    expect(
      await screen.findByText(/AI model not configured/i, { selector: "p" }),
    ).toBeInTheDocument();

    // Manual category selection still works end to end.
    await fillRequiredFields(user);
    await user.selectOptions(screen.getByLabelText("Confirmed category"), "other");
    createMock.mockResolvedValueOnce(CREATED);
    await user.click(screen.getByRole("button", { name: /submit donation/i }));

    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    const payload = createMock.mock.calls[0][0];
    expect(payload.category_id).toBe("cat-other");
    expect(payload.ai_predicted_category).toBeUndefined(); // no suggestion was used
    expect(await screen.findByText("donation detail page")).toBeInTheDocument();
  });

  it("requires explicit confirmation — the suggestion never auto-selects", async () => {
    classifyMock.mockResolvedValue({
      status: "ok",
      predicted_category: "clothing",
      confidence: 0.91,
      top_alternatives: [{ category: "other", probability: 0.05 }],
    });
    renderForm();

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeImageFile()] } });

    const suggestion = await screen.findByText(/Suggested:/, { selector: "span" });
    expect(suggestion).toHaveTextContent("clothing");
    expect(screen.getByRole("button", { name: /use this suggestion/i })).toBeInTheDocument();

    const select = screen.getByLabelText("Confirmed category") as HTMLSelectElement;
    expect(select.value).toBe(""); // NOT auto-selected — explicit confirmation required

    fireEvent.click(screen.getByRole("button", { name: /use this suggestion/i }));
    expect(select.value).toBe("clothing");
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
  });

  it("re-classifies when the primary (first) image is removed", async () => {
    classifyMock
      .mockResolvedValueOnce({
        status: "ok",
        predicted_category: "clothing",
        confidence: 0.9,
        top_alternatives: [],
      })
      .mockResolvedValueOnce({ status: "model_not_configured" });

    const { container } = renderForm();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [makeImageFile("first.jpg"), makeImageFile("second.jpg")] },
    });
    await screen.findByText(/Suggested:/, { selector: "span" });
    expect(screen.getByText("Primary")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Remove photo 1/i }));
    await waitFor(() => expect(classifyMock).toHaveBeenCalledTimes(2));
    expect(
      await screen.findByText(/AI model not configured/i, { selector: "p" }),
    ).toBeInTheDocument();
  });

  it("supports confirming an alternative category from the suggestion card", async () => {
    const user = userEvent.setup();
    classifyMock.mockResolvedValue({
      status: "ok",
      predicted_category: "clothing",
      confidence: 0.6,
      top_alternatives: [{ category: "other", probability: 0.3 }],
    });
    renderForm();

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeImageFile()] } });
    await screen.findByText(/Suggested:/, { selector: "span" });

    await user.click(screen.getByRole("button", { name: /other · 30\.0%/i }));
    const select = screen.getByLabelText("Confirmed category") as HTMLSelectElement;
    expect(select.value).toBe("other");
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
  });
});

describe("CreateDonationPage — validation", () => {
  it("blocks submission without at least one photograph", async () => {
    const user = userEvent.setup();
    renderForm();
    await fillRequiredFields(user);
    await user.selectOptions(screen.getByLabelText("Confirmed category"), "other");
    await user.click(screen.getByRole("button", { name: /submit donation/i }));

    expect(
      await screen.findByText(/Attach at least one photograph/i, { selector: "p" }),
    ).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("blocks submission without a confirmed category", async () => {
    const user = userEvent.setup();
    classifyMock.mockResolvedValue({ status: "model_not_configured" });
    renderForm();

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeImageFile()] } });
    await screen.findByText(/AI model not configured/i, { selector: "p" });

    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /submit donation/i }));

    expect(
      await screen.findByText(/Confirm a category before submitting/i, { selector: "p" }),
    ).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("enforces the 1–3 photo limit", async () => {
    renderForm();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [makeImageFile("1.jpg"), makeImageFile("2.jpg"), makeImageFile("3.jpg"), makeImageFile("4.jpg")] },
    });
    expect(await screen.findByText(/at most 3 photographs/i, { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText("3/3 selected")).toBeInTheDocument();
  });

  it("shows the primary badge on the first photo and supporting on the rest", async () => {
    renderForm();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [makeImageFile("1.jpg"), makeImageFile("2.jpg")] },
    });
    expect(await screen.findByText("Primary")).toBeInTheDocument();
    expect(screen.getByText("Supporting")).toBeInTheDocument();
  });
});

describe("CreateDonationPage — coordinates consent", () => {
  it("requires the consent checkbox when coordinates are provided", async () => {
    const user = userEvent.setup();
    classifyMock.mockResolvedValue({ status: "model_not_configured" });
    const { container } = renderForm();

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeImageFile()] } });
    await screen.findByText(/AI model not configured/i, { selector: "p" });

    await fillRequiredFields(user);
    await user.selectOptions(screen.getByLabelText("Confirmed category"), "other");
    await user.click(screen.getByLabelText(/provide exact map coordinates/i));
    await user.type(screen.getByLabelText("Latitude"), "12.97");
    await user.type(screen.getByLabelText("Longitude"), "77.59");
    await user.click(screen.getByRole("button", { name: /submit donation/i }));

    expect(
      await screen.findByText(/consent box to store them/i, { selector: "p" }),
    ).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });
});
