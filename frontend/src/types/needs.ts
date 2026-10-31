/** Need types (mirrors backend schemas). */

import type { Page } from "@/types/donations";

export type NeedStatus = "active" | "paused" | "closed" | "fulfilled";
export type Urgency = "low" | "medium" | "high" | "critical";

export const URGENCIES: Urgency[] = ["low", "medium", "high", "critical"];

export interface Need {
  id: string;
  organization_id: string;
  organization_name: string | null;
  category_id: string;
  category_code: string | null;
  category_display_name: string | null;
  subcategory_id: string | null;
  subcategory_display_name: string | null;
  title: string;
  description: string | null;
  unit: string;
  quantity_required: number;
  quantity_fulfilled: number;
  remaining_quantity: number;
  urgency: Urgency;
  required_by: string | null;
  status: NeedStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export type NeedsPage = Page<Need>;

export interface MatchFactor {
  score: number;
  weight: number;
  weighted: number;
}

export interface MatchCandidate {
  rank: number;
  organization_id: string;
  organization_name: string;
  verification_status: string;
  need_id: string;
  need_title: string;
  need_category_code: string;
  remaining_quantity: number;
  unit: string;
  distance_km: number | null;
  score: number;
  factors: Record<string, MatchFactor>;
  reasons: string[];
}

export interface MatchResult {
  donation_id: string;
  service_radius_km: number;
  eligible: MatchCandidate[];
  excluded: { reason_code: string; count: number }[];
}
