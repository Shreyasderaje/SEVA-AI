/** API clients for offers, notifications, and payments (M4). */

import { apiFetch } from "@/lib/api";
import type {
  NotificationsPageData,
  Offer,
  PaymentInfo,
  PaymentRecordView,
  UpiSetupStatus,
} from "@/types/workflow";
import type { Page } from "@/types/donations";

// ------------------------------------------------------------------ offers

export function initiateOffer(donationId: string): Promise<{
  donation_id: string;
  status: string;
  offer: Offer | null;
  message: string;
}> {
  return apiFetch(`/api/offers/initiate/${donationId}`, { method: "POST" });
}

export function listMyOffers(page = 1): Promise<Page<Offer>> {
  return apiFetch<Page<Offer>>(`/api/offers/mine?page=${page}`);
}

export function listDonationOffers(donationId: string, page = 1): Promise<Page<Offer>> {
  return apiFetch<Page<Offer>>(`/api/offers/donation/${donationId}?page=${page}`);
}

export function acceptOffer(offerId: string): Promise<Offer> {
  return apiFetch<Offer>(`/api/offers/${offerId}/accept`, { method: "POST" });
}

export function declineOffer(offerId: string, reason?: string): Promise<{
  offer: Offer;
  next: { status: string; offer: Offer | null; message: string };
}> {
  return apiFetch(`/api/offers/${offerId}/decline`, {
    method: "POST",
    body: { reason: reason ?? null },
  });
}

export interface PickupPayload {
  pickup_date: string;
  pickup_window_start: string;
  pickup_window_end: string;
  instructions?: string;
}

export function schedulePickup(offerId: string, payload: PickupPayload): Promise<Offer> {
  return apiFetch<Offer>(`/api/offers/${offerId}/pickup`, { method: "POST", body: payload });
}

export function markPickedUp(offerId: string): Promise<Offer> {
  return apiFetch<Offer>(`/api/offers/${offerId}/picked-up`, { method: "POST" });
}

export function completeOffer(offerId: string, quantityReceived: number): Promise<Offer> {
  return apiFetch<Offer>(`/api/offers/${offerId}/complete`, {
    method: "POST",
    body: { quantity_received: quantityReceived },
  });
}

// ----------------------------------------------------------- notifications

export function listNotifications(page = 1): Promise<NotificationsPageData> {
  return apiFetch<NotificationsPageData>(`/api/notifications?page=${page}`);
}

export function markNotificationRead(id: string): Promise<{ message: string }> {
  return apiFetch(`/api/notifications/${id}/read`, { method: "POST" });
}

export function markAllNotificationsRead(): Promise<{ message: string }> {
  return apiFetch("/api/notifications/read-all", { method: "POST" });
}

// ---------------------------------------------------------------- payments

export function submitUpiSetup(upiId: string, qrFile?: File): Promise<UpiSetupStatus> {
  const form = new FormData();
  form.append("upi_id", upiId);
  if (qrFile) form.append("qr_image", qrFile);
  return apiFetch<UpiSetupStatus>("/api/payments/setup", {
    method: "POST",
    body: form,
    json: false,
  });
}

export function getUpiSetup(): Promise<UpiSetupStatus> {
  return apiFetch<UpiSetupStatus>("/api/payments/setup");
}

export function getDonationPaymentInfo(donationId: string): Promise<PaymentInfo> {
  return apiFetch<PaymentInfo>(`/api/donations/${donationId}/payment-info`);
}

export interface PaymentSubmissionPayload {
  donation_id: string;
  organization_id: string;
  transaction_reference: string;
  amount?: number;
  receipt?: File;
}

export function submitPayment(payload: PaymentSubmissionPayload): Promise<PaymentRecordView> {
  const form = new FormData();
  form.append("donation_id", payload.donation_id);
  form.append("organization_id", payload.organization_id);
  form.append("transaction_reference", payload.transaction_reference);
  if (payload.amount !== undefined) form.append("amount", String(payload.amount));
  if (payload.receipt) form.append("receipt", payload.receipt);
  return apiFetch<PaymentRecordView>("/api/payments", {
    method: "POST",
    body: form,
    json: false,
  });
}

export function listMyPayments(): Promise<PaymentRecordView[]> {
  return apiFetch<PaymentRecordView[]>("/api/payments/mine");
}

export function adminListPayments(params: {
  status?: string;
  page?: number;
}): Promise<Page<PaymentRecordView>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  query.set("page", String(params.page ?? 1));
  return apiFetch<Page<PaymentRecordView>>(`/api/payments/admin/all?${query.toString()}`);
}

export function adminVerifyPayment(id: string): Promise<PaymentRecordView> {
  return apiFetch<PaymentRecordView>(`/api/payments/admin/${id}/verify`, { method: "POST" });
}

export function adminRejectPayment(id: string, reason: string): Promise<PaymentRecordView> {
  return apiFetch<PaymentRecordView>(`/api/payments/admin/${id}/reject`, {
    method: "POST",
    body: { reason },
  });
}
