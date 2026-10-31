/** Organization + verification types (mirrors backend schemas). */

export type VerificationStatus =
  | "pending_verification"
  | "verified"
  | "rejected"
  | "suspended";

export interface OrganizationApplication {
  id: string;
  name: string;
  org_type: string | null;
  description: string | null;
  address: string | null;
  verification_status: VerificationStatus;
  rejection_reason: string | null;
  verified_at: string | null;
  created_at: string;
  latitude: number | null;
  longitude: number | null;
  contact_email: string | null;
  contact_phone: string | null;
  representative_name: string | null;
  owner_user_id: string;
}

export interface OrganizationPublic {
  id: string;
  name: string;
  org_type: string | null;
  description: string | null;
  address: string | null;
  verified_at: string | null;
}

export interface AdminOrganizationListItem {
  id: string;
  name: string;
  org_type: string | null;
  verification_status: VerificationStatus;
  created_at: string;
}

export interface AdminOrganizationDetail extends OrganizationApplication {
  document_id: string | null;
  document_url: string | null;
}

export interface PublicNeed {
  id: string;
  title: string;
  category_id: string;
  unit: string;
  quantity_required: number;
  quantity_fulfilled: number;
  remaining_quantity: number;
  urgency: string;
  required_by: string | null;
}
