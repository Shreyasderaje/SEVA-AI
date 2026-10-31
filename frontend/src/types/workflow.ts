/** M4 types: notifications, offers, payments. */

export interface AppNotification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  link: string | null;
  read: boolean;
  created_at: string;
}

export interface NotificationsPageData {
  items: AppNotification[];
  total: number;
  unread: number;
  page: number;
  page_size: number;
}

export interface MatchFactorSnapshot {
  factors: Record<string, { score: number; weight: number; weighted: number }>;
  reasons: string[];
  service_radius_km: number;
  distance_km: number | null;
}

export type OfferStatus = "sent" | "accepted" | "declined" | "withdrawn";

export interface Offer {
  id: string;
  donation_id: string;
  organization_id: string;
  organization_name: string | null;
  status: OfferStatus;
  score: number | null;
  rank_at_offer: number | null;
  factor_snapshot: MatchFactorSnapshot | null;
  reason_text: string | null;
  decline_reason: string | null;
  quantity_received: number | null;
  pickup_date: string | null;
  pickup_window_start: string | null;
  pickup_window_end: string | null;
  pickup_instructions: string | null;
  responded_at: string | null;
  created_at: string;
  donation_title?: string | null;
  donation_reference?: string | null;
  donation_quantity?: number | null;
  donation_unit?: string | null;
}

export interface PaymentInfo {
  organization_id: string;
  organization_name: string;
  upi_id: string;
  qr_url: string | null;
  instructions: string;
}

export interface PaymentRecordView {
  id: string;
  donation_id: string | null;
  donor_id: string;
  organization_id: string;
  amount: number | null;
  transaction_reference: string;
  status: "submitted_unverified" | "verified" | "rejected";
  rejection_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  has_receipt: boolean;
  receipt_url: string | null;
  created_at: string;
}

export interface UpiSetupStatus {
  upi_id: string | null;
  upi_status: "none" | "pending_approval" | "approved" | "rejected" | null;
  has_qr: boolean;
  rejection_reason?: string | null;
}
