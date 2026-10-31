# SEVA-AI — Testing report

Commands, results, and known gaps per milestone. Last updated: M3.

## How to run

```bash
cd backend && .venv/Scripts/python.exe -m pytest        # backend suite
cd frontend && npm test                                  # Vitest + RTL suite
cd frontend && npm run build                             # tsc + production build
cd backend && .venv/Scripts/python.exe scripts/smoke_m3.py http://localhost:8010
```

## Current results (after M3)

| Suite | Count | Status |
|---|---|---|
| Backend (pytest) | **104** | all passing |
| Frontend (Vitest + RTL) | **38** | all passing |
| Production build (`tsc + vite build`) | — | clean (454.4 kB JS / 20.6 kB CSS) |

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

### API smoke tests (live server)
- `scripts/smoke_m2.py` — donation lifecycle end to end (direct + via Vite proxy).
- `scripts/smoke_m3.py` — apply (invalid doc 422, valid 201) → unverified need
  blocked 403 → owner/admin document authz → admin verify → need created →
  donation → matches (score 92.0, distance 1.2 km, all five factors, reasons,
  determinism) → fulfil → auto-fulfilled excluded → public directory/needs.
  **All checks passed.**

## Known gaps

- Offer workflows, notifications, pickup/completion, payments: M4 (by design).
- Rate-limit 429 body tested on auth endpoints only; upload endpoints share
  the limiter (engaged during smoke tests).
- Donation `updated_at`/filters compare UTC timestamps with local-date query
  bounds — documented nuance; tests anchor at yesterday to stay robust.
- Stage-1 classifier metrics carry the documented near-duplicate leakage
  caveats (rice 100 %, clothing 41.8 %) — never cite them as real-world
  donation accuracy.
- Password reset is design-only (see `ARCHITECTURE.md`).
