# SEVA-AI — Architecture

Components, authentication, storage, matching engine, backups, and the
password-reset design (§13). The matching algorithm itself is specified in
`docs/AI_ML_METHODOLOGY.md` (Part 2).

## Components

```
frontend/  React 18 + Vite + TS — Tailwind tokens, shadcn/ui primitives,
           feature modules (auth, donor, donations, organizations, admin),
           route guards (RequireAuth / RequireRole), Zod validation.
backend/   FastAPI — routers per resource, services layer (matching, storage,
           audit), SQLAlchemy 2.x models, Alembic migrations, Pydantic schemas.
ml/        Dataset pipeline (fetchers, prepare, train, evaluate, predict) +
           model registry helpers. Torch lives ONLY in ml/.venv.
```

The backend never imports PyTorch: `app/ml/classifier.py` lazily wraps
`ml/src/predict_image.py`. Two runtime environments are intentional:

| Environment | Contents | Classify endpoint |
|---|---|---|
| `backend/.venv` | backend deps only | `model_not_configured` (honest fallback, tested) |
| `ml/.venv` | backend deps + torch CPU | loads `CLASSIFIER_WEIGHTS_PATH` and returns real predictions |

## Authentication and authorization

- JWT access tokens (user id + role only), bcrypt password hashes, slowapi
  rate limiting on register/login/uploads.
- Dependencies in `app/core/deps.py`: `get_current_user` (401),
  `get_current_active_user` (403 for inactive/suspended),
  `require_roles(*roles)` (403). Every protected endpoint goes through these;
  the frontend guards are UI-shaping only.
- M3 role matrix (server-enforced):

| Action | Donor | Organization | Admin |
|---|---|---|---|
| Apply as organization | — | own account, once | — |
| View application details/document | — | own only | any |
| Approve/reject/suspend verification | — | — | ✓ (audited) |
| Create/edit needs, record fulfilment | — | own, verified only | — |
| View own needs / donation matches | own donations | own needs | any (read) |
| Public directory / public needs | ✓ | ✓ | ✓ |

- Unverified organizations receive 403 on need creation and are excluded from
  matching (`organization_not_verified`).
- Cross-tenant access returns **404** (no existence leak): another
  organization's needs, another donor's donations/matches, verification
  documents.

## Storage

`app/services/storage.py` — files live under `STORAGE_DIR` (outside the web
root), random UUID names, magic-byte validation:

- Donation images: JPEG/PNG/WebP ≤ 5 MB, re-encoded (RGB, ≤1600 px, JPEG q85 —
  strips EXIF) → `donations/{id}/`.
- Verification documents (M3): PDF/JPEG/PNG ≤ 10 MB, stored as-is →
  `verification/{org_id}/`.
- Serving: only via authorized endpoints (`GET /api/images/{id}`,
  `GET /api/organizations/{id}/verification-document`) with ownership checks;
  404 for strangers.

## Matching engine (M3)

`app/services/matching.py` — pure rule-based scoring, no ML, deterministic.
Eligibility filter → five weighted factors → deterministic tie-break
(score desc, need created_at asc, organization id asc). Weights and service
radius come from the `settings` table with code fallback. The API exposes it
read-only via `GET /api/donations/{id}/matches`; the offer layer (M4) consumes
it and never duplicates scoring logic.

## Offer workflow (M4)

`app/services/offers.py` — sequential selection per addendum §9:

1. `initiate_offer` re-runs the matching engine and picks the highest-ranked
   candidate that has no prior offer for the donation (a decliner is never
   re-offered). While an offer is `sent`, re-initiation is a no-op.
2. Initiation into `offered` is guarded by a conditional donation UPDATE
   (pending → offered); a decline selects the next candidate with the
   donation remaining `offered` (no duplicate history rows).
3. `accept_offer` atomically performs conditional updates on BOTH the offer
   (sent → accepted) and the donation (offered → accepted); any racing
   decline/accept loses with a 409.
4. When no candidate remains: any lingering active offer is withdrawn, the
   donation returns to `pending`, and the donor is notified.
5. Matching score, factors, weights, distance, and reasons are snapshotted
   into `donation_offers.factor_json` at send time and never recomputed.

**Ordering integrity:** status-history rows and notifications carry a
monotonic per-scope `seq` (migration `b7e2a94c6f10`) because `created_at` has
second-level precision on some platforms — `ORDER BY created_at, seq` is
therefore deterministic. History rows are written BEFORE the bulk status
UPDATEs (which synchronize the ORM identity map — writing them after would
trip the dedupe guard and silently drop the row).

## Pickup and completion (M4)

`app/services/pickup.py` — `accepted → pickup_scheduled → picked_up →
completed`, all transitions server-side. Completion records the ACTUAL
`quantity_received` (validated > 0 and ≤ donated quantity), updates the
linked need inside the same transaction via a conditional UPDATE with
`delta = min(received, remaining)` (never over-fulfils; CHECK constraint
backs it), auto-marks the need `fulfilled`, and is idempotent: a repeated
completion hits the donation status guard and fails with 409.

## Payments (M4 §9 — manual verification only)

No gateway, no automatic verification. Organizations submit UPI ID + optional
QR image (verified orgs only) → `pending_approval` → admin approve/reject →
`approved` UPI details become visible to donors on accepted donations.
Donors submit a transaction reference (6–40 alnum) + optional receipt;
status stays `submitted_unverified` until an admin verifies or rejects with
a reason. Payment decisions never change donation status. Receipts and QR
images live outside the web root and are served only to their owners/admins.

## Backups

- SQLite: stop the server, copy `backend/seva.db` (single file).
- Uploads: copy `backend/storage/` (donation images + verification documents).
- Migrations: `alembic upgrade head` applies pending migrations;
  `alembic downgrade -1` rolls the last one back (verify on a copy first).
- Never back up `.env` with backups; keep `JWT_SECRET` in a secret store.

## Password reset (design only — §6.1)

No email is sent. Design: a `password_reset_tokens` table (token hash, user,
expires_at, used_at), request endpoint issues a one-time token (15-minute
expiry) that in development is printed to the server console; the reset
endpoint consumes the token inside one transaction. Not implemented in this
release.
