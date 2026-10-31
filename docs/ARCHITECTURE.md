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
read-only via `GET /api/donations/{id}/matches`; offers are created only from
M4.

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
