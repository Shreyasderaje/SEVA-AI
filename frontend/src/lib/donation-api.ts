/** Typed API calls for donations, categories, and classification. */

import { apiFetch } from "@/lib/api";
import type {
  DonationCategory,
  DonationDetail,
  DonationSummary,
  DonationSummaryCounts,
  Page,
} from "@/types/donations";

export interface DonationListQuery {
  page?: number;
  page_size?: number;
  status?: string;
  category_id?: string;
  date_from?: string;
  date_to?: string;
  q?: string;
}

export function listMyDonations(query: DonationListQuery = {}): Promise<Page<DonationSummary>> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const suffix = params.toString();
  return apiFetch<Page<DonationSummary>>(`/api/donations${suffix ? `?${suffix}` : ""}`);
}

export function getDonation(id: string): Promise<DonationDetail> {
  return apiFetch<DonationDetail>(`/api/donations/${id}`);
}

export function donationSummary(): Promise<DonationSummaryCounts> {
  return apiFetch<DonationSummaryCounts>("/api/donations/summary");
}

export function listCategories(): Promise<DonationCategory[]> {
  return apiFetch<DonationCategory[]>("/api/categories");
}

export function cancelDonation(id: string): Promise<DonationDetail> {
  return apiFetch<DonationDetail>(`/api/donations/${id}/cancel`, { method: "POST" });
}

export interface ClassifyResult {
  status: "ok" | "model_not_configured";
  predicted_category?: string;
  confidence?: number;
  top_alternatives?: { category: string; probability: number }[];
}

export function classifyImage(file: File): Promise<ClassifyResult> {
  const form = new FormData();
  form.append("image", file);
  return apiFetch<ClassifyResult>("/api/classify", {
    method: "POST",
    body: form,
    json: false,
  });
}

export interface CreateDonationPayload {
  title: string;
  description?: string;
  category_id: string;
  subcategory_id?: string;
  quantity: number;
  unit: string;
  condition?: string;
  pickup_area: string;
  pickup_latitude?: number;
  pickup_longitude?: number;
  location_consent: boolean;
  pickup_window_start?: string;
  pickup_window_end?: string;
  ai_predicted_category?: string;
  ai_confidence?: number;
  images: File[];
}

export function createDonation(payload: CreateDonationPayload): Promise<DonationDetail> {
  const form = new FormData();
  form.append("title", payload.title);
  if (payload.description) form.append("description", payload.description);
  form.append("category_id", payload.category_id);
  if (payload.subcategory_id) form.append("subcategory_id", payload.subcategory_id);
  form.append("quantity", String(payload.quantity));
  form.append("unit", payload.unit);
  if (payload.condition) form.append("condition", payload.condition);
  form.append("pickup_area", payload.pickup_area);
  if (payload.pickup_latitude !== undefined && payload.pickup_longitude !== undefined) {
    form.append("pickup_latitude", String(payload.pickup_latitude));
    form.append("pickup_longitude", String(payload.pickup_longitude));
    form.append("location_consent", String(payload.location_consent));
  }
  if (payload.pickup_window_start) form.append("pickup_window_start", payload.pickup_window_start);
  if (payload.pickup_window_end) form.append("pickup_window_end", payload.pickup_window_end);
  if (payload.ai_predicted_category) {
    form.append("ai_predicted_category", payload.ai_predicted_category);
    form.append("ai_confidence", String(payload.ai_confidence ?? 0));
  }
  // Order matters: the FIRST image is the primary classification image.
  payload.images.forEach((file) => form.append("images", file));

  return apiFetch<DonationDetail>("/api/donations", {
    method: "POST",
    body: form,
    json: false,
  });
}
