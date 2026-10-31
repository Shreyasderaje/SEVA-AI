/** Donation-related types mirroring backend schemas (app/schemas/donation.py). */

import type { AccountStatus, UserRole } from "@/types/auth";

export type DonationStatus =
  | "pending"
  | "offered"
  | "accepted"
  | "pickup_scheduled"
  | "picked_up"
  | "completed"
  | "cancelled";

export const DONATION_UNITS = ["kg", "pieces", "packets", "sets", "litres"] as const;
export type DonationUnit = (typeof DONATION_UNITS)[number];

export const DONATION_CONDITIONS = ["new", "good", "fair"] as const;
export type DonationCondition = (typeof DONATION_CONDITIONS)[number];

export const CLASSIFIER_CLASSES = [
  "clothing",
  "grains_rice",
  "packaged_food",
  "utensils",
  "other",
] as const;
export type ClassifierClass = (typeof CLASSIFIER_CLASSES)[number];

export interface Subcategory {
  id: string;
  display_name: string;
}

export interface DonationCategory {
  id: string;
  code: string;
  display_name: string;
  subcategories: Subcategory[];
}

export interface DonationImage {
  id: string;
  position: number;
  mime_type: string;
  size_bytes: number;
  url: string;
}

export interface DonationHistoryEntry {
  id: string;
  from_status: string | null;
  to_status: DonationStatus;
  note: string | null;
  created_at: string;
}

export interface DonationSummary {
  id: string;
  reference: string;
  title: string;
  status: DonationStatus;
  quantity: number;
  unit: string;
  category_code: string;
  category_display_name: string;
  subcategory_display_name: string | null;
  ai_predicted_category: string | null;
  ai_confidence: number | null;
  primary_image_url: string | null;
  created_at: string;
}

export interface DonationDetail extends DonationSummary {
  description: string | null;
  condition: string | null;
  pickup_area: string | null;
  pickup_latitude: number | null;
  pickup_longitude: number | null;
  location_consent: boolean;
  pickup_window_start: string | null;
  pickup_window_end: string | null;
  images: DonationImage[];
  timeline: DonationHistoryEntry[];
}

export interface DonationSummaryCounts {
  active: number;
  accepted: number;
  completed: number;
  total: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type { AccountStatus, UserRole };
