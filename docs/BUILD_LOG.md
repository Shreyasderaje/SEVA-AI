# SEVA-AI Build Log

Concise progress notes and recorded decisions per milestone.

---

## Phase 0 — Planning (2026-10-31)

- Inspected repository: `D:\MINI Project (seva)` was empty (no git history, no prior code) → greenfield build.
- Toolchain verified: Python 3.11.9, Node v24.21.0, npm 11.19.0, git 2.55.0.
- Produced the implementation plan from the Master Build Prompt + Technical Corrections Addendum (addendum authoritative where it overrides).
- All 10 addendum corrections folded into the design (sequential offers, `is_demo_data`, display subcategories, primary-image classification, `quantity_received`, location fallback, no auto-expiry, verification-document limits, sequential offer selection, weights-path resolution).
- User amendments applied: repository root is `D:\MINI Project (seva)` itself (no nested `seva-ai/`); `docs/` contains exactly five files, with `README.md` as the sixth documentation file at the root.
- User approved the plan; Phase 1 (M1) started.

## Milestone M1 — Foundation (2026-10-31)

### Built

**Backend (FastAPI, port 8000)**
- Full corrected schema in **migration 001** (18 tables): `is_demo_data` on all 12 seedable
  tables from day one, `quantity_received` on `donation_offers`, `donation_subcategories`
  with FK to fixed parent categories, `location_consent` + lat/long check constraints,
  all §10.2 indexes. Verified: `alembic upgrade head` on a clean DB produces all 18 tables.
- Auth: register (donor/organization), login, `/me`, logout — bcrypt hashes, JWT access
  tokens (user id + role only, 60 min), account-status checks, consistent safe error shape.
- RBAC dependencies (`get_current_user`, `get_current_active_user`, `require_roles`) used by
  every protected route; admin-only `GET /api/admin/users` (real endpoint, used by M5 UI).
- Append-only audit log for register / login success / login failed / login blocked, with
  hashed IPs (no plaintext IPs stored).
- slowapi rate limiting on register + login (in-memory, `5/minute`), headers enabled.
- Startup diagnostics log env, database kind, storage dir, and the **resolved classifier
  weights path** (`CLASSIFIER_WEIGHTS_PATH` resolves against the backend directory, not the
  terminal CWD — addendum §10); missing weights file does not affect startup.
- `scripts/create_admin.py`: idempotent base seed — admin account, 5 fixed classifier
  categories, 13 example display subcategories, self-compatibility rows, matching-weight
  and service-radius settings. Run twice → verified idempotent.

**Frontend (Vite + React + TS, port 5173)**
- Design tokens per §8.1 (warm off-white surfaces, charcoal-navy text, deep teal primary,
  muted status colours), shadcn-style primitives (Button, Input, Label, Card, Badge).
- App shell (header/footer, responsive nav), landing page (hero, 4-step how-it-works,
  accepted categories, trust & privacy), 404 page with action.
- Auth: `AuthProvider` (localStorage token, boot via `/me`, 401 → token cleared), Login and
  Register pages with react-hook-form + Zod validation and sonner toasts; register page has
  a donor/organization role toggle.
- Route guards: `RequireAuth` (redirects to /login, preserves `from`), `RequireRole`
  (honest access-denied card). Guards are UI-shaping only; the backend remains the
  authorization source of truth.

### Decisions recorded
1. **Whole schema shipped in migration 001** — addendum columns present from day one; no
   retrofit migrations needed later.
2. `donation_offers.status` enum is `{sent, accepted, declined, withdrawn}` — `expired`
   dropped because nothing can set it (no scheduler exists; addendum §7).
3. `donations.category_id` holds the **donor-confirmed** category; `ai_predicted_category`
   / `ai_confidence` are stored separately and never used without confirmation (addendum §4).
4. `donations.subcategory_id` → FK to `donation_subcategories` (addendum §3; display
   subcategories are managed rows, not free text).
5. The admin account is created by `create_admin.py` and is **not** marked `is_demo_data`,
   so the M5 demo reset can never delete it.
6. Development JWT fallback with a loud startup warning; **production refuses to start**
   without a real `JWT_SECRET`.
7. `Float` used for quantities and payment amounts (SQLite has no decimal type; acceptable
   for this MVP, documented in `DATABASE_SCHEMA.md` at M5).
8. Tests use `Base.metadata.create_all` for speed; real databases use Alembic. The
   clean-clone migration path is verified separately on a temp DB.
9. slowapi 0.1.10 quirk (found + fixed): rate-limited endpoints must return a Starlette
   `Response` (FastAPI's dict serialization breaks slowapi's header injection). Rate-limit
   headers appear on 429 responses only — verified empirically and tested as such.
10. Vite proxy target overridable via `VITE_API_TARGET` (default `http://localhost:8000`).
11. Test fixtures that create helper users are idempotent (register-or-login) because the
    test DB persists for the whole pytest session.

### Commands and results
| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest` (in `backend/`) | **19 passed** |
| Frontend tests | `npm test` (in `frontend/`) | **14 passed** (3 files) |
| Type check + build | `npm run build` | clean, 341.9 kB JS / 14.6 kB CSS |
| Migration from clean clone | `DATABASE_URL=sqlite:///./migration_check.db alembic upgrade head` | 18 tables created |
| Live smoke (uvicorn + curl) | health / register / me / RBAC / rate limit | 200 / 201 / 200 / 403+401 / 429 — all correct |
| Live admin login + endpoint | seeded admin → `/api/admin/users` | 200, paginated list |
| FE→BE integration | `npm run dev` (proxy) → register + `/me` via `localhost:5173/api/...` | 201 / 200 through the proxy |

### Known issues / limitations after M1
1. **Port 8000 is occupied on this machine** by a zombie `python.exe` (PID 24028) left over
   from the interrupted previous session; it answers with a foreign 404 shape. Free it with
   `taskkill //PID 24028 //F` if desired, or run the backend on another port and set
   `VITE_API_TARGET=http://localhost:<port>` before `npm run dev`. All project defaults
   remain 8000.
2. `AccountPage` is an honest M1 staging page (real account data, no fake stats); role
   dashboards replace it in M2–M5.
3. The landing page's "Find organizations" hero action is deferred to M3, when the
   verified-organization directory API exists — no dead buttons are shipped.
4. `StarletteDeprecationWarning` from `fastapi.testclient` (third-party, harmless).
5. Python 3.11.9 / Node 24 confirmed compatible; exact dependency versions pinned in
   `backend/requirements.txt` and `frontend/package.json`.

