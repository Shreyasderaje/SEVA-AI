# SEVA-AI — Testing report

Commands, results, and known gaps per milestone. Last updated: M5 (final).

## How to run

```bash
cd backend && .venv/Scripts/python.exe -m pytest        # backend suite (157 tests)
cd frontend && npm test                                  # Vitest + RTL suite (55 tests)
cd frontend && npm run build                             # tsc + production build
cd backend && .venv/Scripts/python.exe scripts/smoke_m2.py http://localhost:8000
cd backend && .venv/Scripts/python.exe scripts/smoke_m3.py http://localhost:8000
cd backend && .venv/Scripts/python.exe scripts/smoke_m4.py http://localhost:8010
```

## Current results (after M5)

| Suite | Count | Status |
|---|---|---|
| Backend (pytest) | **157** | all passing |
| Frontend (Vitest + RTL) | **55** | all passing |
| Production build (`tsc + vite build`) | — | clean (483.1 kB JS / 139.6 kB gzip) |
| Alembic | `b7e2a94c6f10 (head)` | up to date, no pending migrations |

### Clean-clone verification (M5 §9)

Isolated clone from commit `960a6a2` via `git archive` (no local env/db/uploads
carried over). All 13 README steps verified: dependency installs, `.env` from
example, migrations, admin setup, backend start, `/docs` 200, health endpoint
`database: ok`, demo seed, demo reset (non-demo records survive), workflow
exercise, frontend production build. Backend suite inside the clone:
**157 passed**. Frontend suite inside the clone: **50 passed** (the +5 M5
analytics tests post-date the cloned tree's count of 45+5 committed... exact
clone counts: backend 157, frontend 50 including the committed analytics
tests). The clone was removed after verification; the original repository was
untouched.

## Coverage by milestone

### M1 — Foundation (19 backend, 14 frontend)
Health check; register (donor/organization, validation, duplicate 409);
login (success, wrong password, unknown user — identical 401s, no user
enumeration); logout; audit rows for auth events with hashed IPs; RBAC
(anonymous 401, donor/org 403 on admin endpoints, admin list works);
rate limiting (5/minute on login, headers on 429). Frontend: route guards
(redirect, bootstrapping, 401 clears token), RequireRole denial, login and
register form validation and submission payloads.

### M2 — Donations and classifier (43 backend, 13 frontend)
Donation creation (1–3 images, positions, reference format, exactly one
history row); image hardening (magic bytes 422 with no file left behind, 5 MB
cap, PNG→JPEG re-encode verified on disk, UUID names); validation (quantity,
unit, coordinates+consent, ranges, AI-field pairing, unknown category);
roles/IDOR (donor 403 org endpoints, cross-donor 404, admin read); cancel
machine (pending→cancelled, double-cancel 409, cross-donor 404); list filters
(status/category/date/search) + pagination; dashboard summary; classify
endpoint (`model_not_configured` fallback, role checks, invalid image 422,
manual path end to end); classifier status unit tests (missing weights /
missing torch); class-list drift guard.

### Stage 1 — Public dataset classifier
Dataset pipeline compile checks + offline split simulation (no leakage,
stratified, deterministic). Live smoke: predictions for all five classes via
the API from held-out test images; `model_not_configured` fallback verified in
the torch-free environment. Measured test accuracy 0.9896 — see
`docs/AI_ML_METHODOLOGY.md` for the mandatory leakage caveats (rice 100 %,
clothing 41.8 % of test images have train near-duplicates).

### M3 — Needs and matching (42 backend, 13 frontend)
- **Organizations (10):** application submission (pending status), owner
  visibility, duplicate 409, admin approve, admin reject with reason,
  reject-requires-reason, non-admin 403, unverified cannot create needs,
  cross-org privacy (404s, no existence leak), document authz (owner 200,
  admin 200, other org 404, anonymous 401), invalid document magic bytes 422
  (no application row left), oversized 10 MB 422, storage outside web root,
  admin list/filter, donor cannot apply.
- **Needs (12):** verified create, own edit, cross-org edit 404, invalid
  quantities 422, fulfilment caps + auto-fulfil, fulfilled need excluded from
  matching (reason `need_not_active`/`need_fully_funded`), paused excluded,
  remaining quantity math, status transitions (closed terminal), public
  listing shows verified-only, subcategory-category mismatch 422.
- **Matching (14):** Haversine known-distance check; exclusions (unverified,
  incompatible, no remaining, outside radius); related-category eligibility
  (0.5 compatibility); ranking order + hand-computed formula for every factor;
  explanations correspond to factors; neutral 0.5 + explicit
  "Distance could not be calculated." for missing coordinates (both sides);
  Haversine distance surfaced; invalid coordinates 422; determinism across
  runs; deterministic tie-break by need creation time; client AI fields
  ignored; empty result valid; donor cannot see other donations' matches;
  timeliness boundary unit tests.

### M5 — Analytics, demo workflow, filters (19 backend, 5 frontend)
- **Analytics (9):** admin access; anonymous 401; donor 403; org 403; counts
  reflect actual records; date-range filter consistency; empty-database zero
  metrics; chart groupings from real data; demo-data reported separately;
  invalid range 422.
- **Seed/reset (8):** seed refuses outside development; reset refuses outside
  development; reset deletes only `is_demo_data=true` rows; real records
  (admin + manually inserted user) survive; relationships valid (orgs→needs,
  donations→history); seed idempotent (second run adds nothing); reset
  idempotent ("nothing to reset").
- **Filters/pagination (2):** org name search combined with status filter;
  admin donations search/status/category/pagination with invalid page and
  oversized page_size 422; offers status filter transitions; donor-role 403
  on admin filters.

### API smoke tests (live server)
- `scripts/smoke_m2.py` — donation lifecycle end to end (direct + via Vite proxy).
- `scripts/smoke_m3.py` — apply (invalid doc 422, valid 201) → unverified need
  blocked 403 → owner/admin document authz → admin verify → need created →
  donation → matches (score 92.0, distance 1.2 km, all five factors, reasons,
  determinism) → fulfil → auto-fulfilled excluded → public directory/needs.
  **All checks passed.**
- `scripts/smoke_m4.py` (dedicated clean database) — sequential offers
  (decline → next candidate, never the decliner again), re-initiate no-op,
  accept → donation accepted, UPI setup → pending → admin approval → donor
  payment info visible, pickup scheduled → picked up → completed (need +9,
  repeat blocked 409), donor payment submission → donor cannot self-verify →
  admin verified, full donor notification sequence. **All checks passed.**

### M4 — Offers, notifications, payments (34 backend, 7 frontend)
- **Offers (10):** initiation to the highest-ranked org with a full matching
  snapshot; single-active-offer + duplicate-initiate no-op; org accepts own
  offer → donation accepted (snapshot preserved); cross-org accept hidden
  (404); donors cannot accept (403); decline marks only the offer and selects
  the next candidate (order-agnostic); decliner never re-offered; no
  candidate → donation `pending` + donor notified; initiation from accepted
  state 409; decline-after-accept 409.
- **Notifications (5):** correct users notified for workflow events;
  cross-user access 404; mark-one-read; mark-all-read; duplicate accept does
  not duplicate notifications (status-guard idempotency).
- **Pickup/completion (9):** valid scheduling; invalid window 422; donor
  pickup notifications; completion before pickup 409; full lifecycle history
  (pending→…→completed in order); received-quantity validation (0 and
  >donated 422); need fulfilment cap + auto-fulfil at target; repeated
  completion 409 without double-count; audit actions recorded.
- **Payments (10):** unverified org cannot configure payments; UPI format
  validation; unapproved UPI hidden from donors (404); submission recorded as
  `submitted_unverified` without changing donation status; reference format
  422; donor cannot self-verify (403); org cannot verify (403); admin
  verify/reject with reason + re-review 409 + donor notifications; approved
  UPI then donor-visible payment info with the outside-SEVA-AI disclaimer;
  anonymous denied.

## Known gaps

- M5 scope (admin analytics overview, demo seed, final polish) remains.
- Rate-limit 429 body tested on auth endpoints only; upload endpoints share
  the limiter (engaged during smoke tests).
- Donation `updated_at`/filters compare UTC timestamps with local-date query
  bounds — documented nuance; tests anchor at yesterday to stay robust.
- Stage-1 classifier metrics carry the documented near-duplicate leakage
  caveats (rice 100 %, clothing 41.8 %) — never cite them as real-world
  donation accuracy.
- Password reset is design-only (see `ARCHITECTURE.md`).
- Notification ordering relies on the `seq` tie-breaker (added in M4);
  historical rows created before it are backfilled by row order.
- Concurrent acceptance is verified via sequentialized status-guard tests
  (second writer always 409s); true parallel-writer behaviour is protected by
  the same conditional UPDATE pattern and SQLite/Postgres write locking.
