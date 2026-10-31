/** API clients for organizations and needs (M3). */

import { apiFetch } from "@/lib/api";
import type {
  AdminOrganizationDetail,
  AdminOrganizationListItem,
  OrganizationApplication,
  OrganizationPublic,
} from "@/types/organizations";
import type { Need, NeedsPage } from "@/types/needs";
import type { PublicNeed } from "@/types/organizations";
import type { Page } from "@/types/donations";

export function getMyOrganization(): Promise<OrganizationApplication> {
  return apiFetch<OrganizationApplication>("/api/organizations/me");
}

export interface ApplyPayload {
  name: string;
  org_type?: string;
  description?: string;
  address?: string;
  contact_email?: string;
  contact_phone?: string;
  representative_name?: string;
  latitude?: number;
  longitude?: number;
  location_consent: boolean;
  document: File;
}

export function applyOrganization(payload: ApplyPayload): Promise<OrganizationApplication> {
  const form = new FormData();
  form.append("name", payload.name);
  if (payload.org_type) form.append("org_type", payload.org_type);
  if (payload.description) form.append("description", payload.description);
  if (payload.address) form.append("address", payload.address);
  if (payload.contact_email) form.append("contact_email", payload.contact_email);
  if (payload.contact_phone) form.append("contact_phone", payload.contact_phone);
  if (payload.representative_name) {
    form.append("representative_name", payload.representative_name);
  }
  if (payload.latitude !== undefined && payload.longitude !== undefined) {
    form.append("latitude", String(payload.latitude));
    form.append("longitude", String(payload.longitude));
    form.append("location_consent", String(payload.location_consent));
  }
  form.append("document", payload.document);
  return apiFetch<OrganizationApplication>("/api/organizations/apply", {
    method: "POST",
    body: form,
    json: false,
  });
}

export function adminListOrganizations(params: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<Page<AdminOrganizationListItem>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.page_size ?? 10));
  return apiFetch<Page<AdminOrganizationListItem>>(
    `/api/organizations/admin/all?${query.toString()}`,
  );
}

export function adminGetOrganization(id: string): Promise<AdminOrganizationDetail> {
  return apiFetch<AdminOrganizationDetail>(`/api/organizations/admin/${id}`);
}

export function adminVerifyOrganization(id: string): Promise<AdminOrganizationDetail> {
  return apiFetch<AdminOrganizationDetail>(`/api/organizations/admin/${id}/verify`, {
    method: "POST",
  });
}

export function adminRejectOrganization(
  id: string,
  reason: string,
): Promise<AdminOrganizationDetail> {
  return apiFetch<AdminOrganizationDetail>(`/api/organizations/admin/${id}/reject`, {
    method: "POST",
    body: { reason },
  });
}

export function adminSuspendOrganization(
  id: string,
  reason: string,
): Promise<AdminOrganizationDetail> {
  return apiFetch<AdminOrganizationDetail>(`/api/organizations/admin/${id}/suspend`, {
    method: "POST",
    body: { reason },
  });
}

export function listPublicOrganizations(): Promise<OrganizationPublic[]> {
  return apiFetch<OrganizationPublic[]>("/api/organizations");
}

export function listPublicOrgNeeds(orgId: string): Promise<PublicNeed[]> {
  return apiFetch<PublicNeed[]>(`/api/organizations/${orgId}/public-needs`);
}

// ------------------------------------------------------------------- needs

export function listMyNeeds(params: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<NeedsPage> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  query.set("page", String(params.page ?? 1));
  if (params.page_size) query.set("page_size", String(params.page_size));
  return apiFetch<NeedsPage>(`/api/needs/mine?${query.toString()}`);
}

export function getNeed(id: string): Promise<Need> {
  return apiFetch<Need>(`/api/needs/${id}`);
}

export interface NeedPayload {
  category_id: string;
  subcategory_id?: string;
  title: string;
  description?: string;
  unit: string;
  quantity_required: number;
  urgency: string;
  required_by?: string;
  notes?: string;
}

export function createNeed(payload: NeedPayload): Promise<Need> {
  return apiFetch<Need>("/api/needs", { method: "POST", body: payload });
}

export function updateNeed(id: string, payload: Partial<NeedPayload>): Promise<Need> {
  return apiFetch<Need>(`/api/needs/${id}`, { method: "PATCH", body: payload });
}

export function changeNeedStatus(
  id: string,
  status: "active" | "paused" | "closed",
): Promise<Need> {
  return apiFetch<Need>(`/api/needs/${id}/status`, {
    method: "POST",
    body: { status },
  });
}

export function recordFulfilment(id: string, quantity: number): Promise<Need> {
  return apiFetch<Need>(`/api/needs/${id}/fulfilment`, {
    method: "POST",
    body: { quantity },
  });
}

export function listPublicNeeds(params: {
  category_id?: string;
  urgency?: string;
}): Promise<Need[]> {
  const query = new URLSearchParams();
  if (params.category_id) query.set("category_id", params.category_id);
  if (params.urgency) query.set("urgency", params.urgency);
  const suffix = query.toString();
  return apiFetch<Need[]>(`/api/needs/public${suffix ? `?${suffix}` : ""}`);
}
