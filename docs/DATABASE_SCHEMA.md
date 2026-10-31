# SEVA-AI — Database schema

SQLAlchemy 2.x models + Alembic migrations. UUID primary keys stored as
String(36). Enum-like columns are `String` + named CHECK constraints.
`created_at`/`updated_at` on mutable tables. Migrations:

- `04b1dafc7f5e` — initial schema (18 tables, all constraints + §10.2 indexes)
- `3cb71d79fa42` — M3: `organizations.description`, `organization_needs.subcategory_id`
- `a7c31f9d21b4` — M3 defect fix: `organization_documents.uploaded_at` server
  default was the string `'CURRENT_TIMESTAMP'` (readable rows broke); replaced
  with the SQL keyword and rows repaired
- `c4d85e01a9b7` — M4: `donation_offers.pickup_date/pickup_window_start/
  pickup_window_end/pickup_instructions` (organization's confirmed pickup plan)
- `e91b7f3c5d20` — M4: `payment_records.donation_id`, `payment_records.rejection_reason`
- `b7e2a94c6f10` — M4: monotonic `seq` columns on `donation_status_history`
  (per donation) and `notifications` (per user) — deterministic ordering when
  `created_at` ties (second-level precision on some platforms)

## Tables (18)

| Table | Purpose / key columns |
|---|---|
| `users` | id, email (unique), password_hash, full_name, role `donor/organization/admin` (CK), status `active/inactive/suspended` (CK), is_demo_data |
| `donor_profiles` | user_id (PK, FK), phone, preferred_area |
| `organizations` | id, owner_user_id (FK, unique), name, org_type, description (M3), address, latitude/longitude (range CK), contact_email/phone, representative_name, verification_status `pending_verification/verified/rejected/suspended` (CK), rejection_reason, upi_id, upi_qr_path, upi_status (CK), verified_at, is_demo_data |
| `organization_documents` | id, organization_id (FK), document_type, stored_path, uploaded_at (default `CURRENT_TIMESTAMP` — fixed in `a7c31f9d21b4`), is_demo_data |
| `donation_categories` | id, code (unique, 5 fixed classifier classes), display_name, is_active |
| `donation_subcategories` | id, category_id (FK), display_name, is_active, sort_order — admin-managed DISPLAY data, never classifier labels |
| `donation_compatibility` | (donation_category_id, need_category_id) composite PK, factor `exact/related` (CK) — matching engine input |
| `donations` | id, reference (unique, `SEVA-YYYY-NNNNNN`), donor_id (FK), category_id (FK — the DONOR-CONFIRMED category), subcategory_id (FK, nullable), title, description, quantity (>0 CK), unit (CK 5 values), condition (CK, nullable), pickup_area, pickup_latitude/longitude (range CK), location_consent, pickup_window_start/end, ai_predicted_category (raw model output, non-authoritative), ai_confidence, status (CK, below), flagged, flag_reason, is_demo_data |
| `donation_images` | id, donation_id (FK), stored_path, mime_type, size_bytes, position (unique per donation), is_demo_data |
| `organization_needs` | id, organization_id (FK), category_id (FK), subcategory_id (FK, M3), title, description, unit (CK), quantity_required (>0 CK), quantity_fulfilled (0 ≤ f ≤ required CK), urgency (CK), required_by, status `active/paused/closed/fulfilled` (CK), notes, is_demo_data |
| `donation_offers` | id, donation_id (FK), organization_id (FK), need_id (FK), status `sent/accepted/declined/withdrawn` (CK), score, rank_at_offer, factor_json (matching snapshot at send time), reason_text, decline_reason, quantity_received (actual, ≤ donated), responded_at, pickup_date/pickup_window_start/pickup_window_end/pickup_instructions (M4), UNIQUE (donation_id, organization_id), is_demo_data |
| `donation_status_history` | id, donation_id (FK), actor_user_id (FK, nullable=system), from_status, to_status, note, seq (monotonic per donation — stable ordering), — append-only |
| `notifications` | id, user_id (FK), type, title, body, link, read_at, seq (monotonic per user), is_demo_data |
| `payment_records` | id, donor_id (FK), organization_id (FK), donation_id (M4, nullable), amount (nullable, >0 CK), transaction_reference, receipt_path, status (CK), rejection_reason (M4), reviewed_by (FK), reviewed_at, is_demo_data |
| `audit_logs` | id, actor_user_id (FK, nullable), action, target_type, target_id, note, ip_hash — append-only |
| `model_versions` | id, model_name, version, kind `image_classifier/acceptance_model` (CK), artifact_path, seed, metadata_json, is_active |
| `model_evaluations` | id, model_version_id (FK), split, metrics_json, report_path, is_demo_data |
| `settings` | key (PK), value_json, updated_by (FK), updated_at — `matching_weights`, `service_radius_km` |

## Status machines

- **Donation** (M2; M4 adds offer-driven transitions):
  `pending → offered → accepted → pickup_scheduled → picked_up → completed`;
  donor `cancel` allowed only from `pending`/`offered` → `cancelled`. No
  automatic expiry (addendum §7).
- **Organization verification** (M3): `pending_verification → verified |
  rejected` (admin); `verified ⇄ suspended` (admin); reject/suspend require a
  reason; every decision audited.
- **Need** (M3): created `active`; `active ⇄ paused`; `active|paused → closed`
  (terminal); `active → fulfilled` automatically when
  `quantity_fulfilled ≥ quantity_required` via the fulfilment endpoint.
- **Offer** (M4 — not yet written): `sent → accepted | declined | withdrawn`.

## Quantity rules (needs, M3)

- `quantity_required > 0` (CK), `0 ≤ quantity_fulfilled ≤ quantity_required` (CK).
- Fulfilment uses a **conditional UPDATE**
  (`SET quantity_fulfilled = quantity_fulfilled + :delta WHERE … + :delta ≤ quantity_required`)
  — over-fulfilment is impossible even under concurrent requests; the CHECK
  constraint is the second line of defence.
- `remaining_quantity` = `quantity_required − quantity_fulfilled`, floored at 0,
  computed consistently server-side.

## Indexes (§10.2)

`donations(status)`, `donations(category_id)`, `donations(donor_id, created_at)`,
`organization_needs(organization_id, status)`,
`organization_needs(category_id, status)`,
`donation_offers(organization_id, status)`,
`donation_status_history(donation_id, created_at)`,
`notifications(user_id, read_at)`, `audit_logs(created_at)`,
`payment_records(organization_id, status)`.
