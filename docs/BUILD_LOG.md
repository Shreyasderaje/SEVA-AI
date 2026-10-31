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

---

## Milestone M2 — Donations and Classifier (2026-10-31)

### Built

**Donor donation workflow (backend)**
- `POST /api/donations` (donor-only, rate-limited, multipart): 1–3 photographs,
  donor-confirmed `category_id` (required), optional `subcategory_id` validated against the
  chosen category, quantity/unit/condition, pickup area, optional coordinates **stored only
  with explicit consent** and range-validated, optional pickup window (end after start),
  optional `ai_predicted_category` + `ai_confidence` echoed from `/api/classify` (stored
  separately from the confirmed category; both-or-neither).
- Image hardening (§6.5, §11): magic-byte sniffing (JPEG/PNG/WebP, never the client MIME or
  filename), 5 MB cap enforced on actual bytes, uploaded filenames discarded, UUID hex
  filenames under `STORAGE_DIR/donations/{id}/`, Pillow re-encode (RGB, ≤1600 px long edge,
  JPEG q85) which strips EXIF/metadata. On any upload failure the whole request rolls back —
  no orphan files, no partial rows.
- `GET /api/donations` — own donations with server-side search (title), status/category/date
  filters, pagination. `GET /api/donations/{id}` — owner or admin (404 for strangers, no
  existence leak). `POST /api/donations/{id}/cancel` — donor, only while `pending`/`offered`
  (addendum §1/§7), 409 otherwise. `GET /api/donations/summary` — dashboard counts
  (active = pending+offered, accepted = accepted+pickup_scheduled+picked_up, completed).
- `GET /api/categories` (public): 5 fixed classes + active display subcategories.
- `GET /api/images/{id}` — files live outside the web root; served only to the owning donor
  or admin (404 for others).
- Status history is **append-only**; creation writes exactly one row (None→pending);
  `record_status_transition` refuses to write a second row when the overall status has not
  changed (addendum §1). Audit rows for donation.create / donation.cancel.
- Reference format `SEVA-2026-000001` (per-year sequence, unique constraint).

**Classifier (honest by construction)**
- Canonical inference in `ml/src/predict_image.py`; the backend wraps it via
  `app/ml/classifier.py` with lazy torch imports — the backend venv has **no torch
  dependency**. `POST /api/classify` (donor, rate-limited) returns the real prediction when
  a trained weights file exists, or `{"status": "model_not_configured"}` (HTTP 200) when it
  does not. No auto-download, no fabricated predictions, ImageNet weights never presented
  as a trained SEVA-AI model.
- Full pipeline implemented in `ml/src/`: `prepare_dataset.py` (consent.csv enforcement,
  label validation, resize/metadata-strip, stratified splits grouped by source session,
  seed 42, `--force` guard), `train_image_classifier.py` (frozen-head + optional
  fine-tune, seeds, metadata JSON, optional `--register` into `model_versions`),
  `evaluate_image_classifier.py` (test split touched once; metrics JSON + confusion-matrix
  PNG + summary markdown; explicit small-class warnings). ML deps isolated in
  `ml/requirements.txt` — **not installed on this machine**; scripts are compile-checked
  and the split logic is simulation-verified (no leakage, stratified, deterministic).

**Donor frontend**
- Donor dashboard (`/dashboard`): real DB-backed summary cards, five most recent donations,
  create CTA, loading skeletons, empty state, error state with retry.
- Create donation page: 1–3 photo picker with Primary/Supporting badges and remove actions,
  automatic classify of the primary photo, suggestion card with confidence + clickable
  alternatives, **explicit "Use this suggestion" confirmation** (suggestion never
  auto-selects), `model_not_configured` banner, always-available manual select, consent
  checkbox for coordinates, full Zod validation, toast + redirect to detail.
- Donation detail: photos with primary badge, AI-vs-confirmed display, append-only timeline,
  cancel with confirmation dialog (only while pending).
- Donations list: server-side search/status/category/date filters + pagination.
- Landing "Donate items" CTA is role-aware; header shows Dashboard for donors.

### Decisions recorded
1. **Backend stays torch-free** — torch imports are lazy inside the classifier wrapper;
   `model_not_configured` covers both "weights missing" and "torch unavailable" (both mean
   the classifier cannot run here; documented in `AI_ML_METHODOLOGY.md`).
2. `ai_predicted_category`/`ai_confidence` on create are client-echoed from `/api/classify`
   and are non-authoritative; the donor-confirmed `category_id` is operative. Validated
   against the five fixed codes; both-or-neither.
3. Only the primary photo is classified (client sends it to `/api/classify`); supporting
   photos are never processed in the MVP (addendum §4).
4. Re-encode normalises everything to JPEG q85 ≤1600 px — uniform storage, guaranteed
   metadata strip.
5. Dashboard count groupings: active = pending+offered; accepted = accepted+pickup_scheduled
   +picked_up; completed = completed (documented in the schema).
6. Donor donation editing is out of scope this release (master §5.2 lists creation; no edit
   requirement) — cancellation exists.
7. Dataset-pipeline honesty: no dataset, no weights, no metrics — pipeline exists,
   compile-checked, split logic simulation-verified; limitations documented in
   `AI_ML_METHODOLOGY.md`.
8. Frontend tests caught **two real bugs** which were fixed in the app, not the tests:
   (a) selecting photos never triggered classification; (b) the condition "Not applicable"
   option submitted `""` which failed Zod silently, making the whole form un-submittable
   (empty lat/lng inputs had the same silent-coercion trap — both now preprocess "" →
   undefined).

### Commands and results
| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest` | **62 passed** (19 M1 + 43 M2; M1 untouched and green) |
| Frontend tests | `npm test` | **27 passed** (13 M1 + 14 M2) |
| Type check + build | `npm run build` | clean — 415.5 kB JS / 20.0 kB CSS |
| ML scripts compile | `py_compile` on all four `ml/src/*.py` | OK |
| Split-logic simulation | offline run of `make_splits` | no session leakage, stratified, deterministic |
| Live smoke (direct + via Vite proxy) | `scripts/smoke_m2.py` | ALL CHECKS PASSED — honest fallback, PNG→JPEG re-encode, primary/supporting positions, consent-gated coords, timeline, cancel machine (409 on double cancel), IDOR 404, rate limiter active |

### Known issues / limitations after M2
1. No trained classifier and no dataset — manual category selection is the working path
   (`model_not_configured` verified end to end). ML deps not installed on this machine;
   follow `ml/README.md` when a consented dataset exists.
2. `ai_*` fields are client-echoed (non-authoritative); server-side re-inference on create
   would double inference cost for no integrity gain in this MVP.
3. Organization access to donation images (offers) arrives with M4; admins + owners only
   for now.
4. Donor editing of a donation is not implemented (cancellation only) — documented scope
   decision, revisit if the guide requires it.
5. Port 8000 / zombie process note from M1 still applies on this machine.

---

## Dataset Stage 1 — Public licensed datasets + trained classifier (2026-10-31)

User decision: train the initial SEVA-AI MobileNetV2 classifier on publicly
available image datasets (Stage 1); consented real-world photographs from
ashram visits will follow as Stage 2.

### Dataset acquisition (licence-verified per source)

| SEVA class | Source | Licence | Raw images |
|---|---|---|---|
| clothing | Apparel Images Gallery (AIG), Mendeley Data v1 | CC BY 4.0 | 130,098 |
| grains_rice | Rice Image Dataset — Koklu, Cinar & Taspinar (2021), HF mirror | CC BY 4.0 | 75,000 |
| packaged_food | Open Food Facts product fronts | CC-BY-SA / CC0 per upload | 697 |
| utensils | Kitchen Utensils 13K, Hugging Face | MIT | 1,861 |
| other | Wikimedia Commons (toys/dolls/plush/books/board games/children's games/school supplies) | per-file CC0/PD/CC BY/CC BY-SA only | 844 |

**Documented rejections/substitutions:** Freiburg Groceries — host server
unreachable during collection and no image licence in its repository;
BookCover30 — images copyrighted by Amazon ("fair use" only); HoloSelecta —
archive holds 295 images plus study data despite its title. Wikimedia Commons
was chosen for "other" because every file's licence, artist, and source URL
are captured per image via the Commons API.

### Dataset preparation (`ml/src/prepare_dataset.py`, rewritten)

- New `labels.csv` schema: `image_path, label, source, source_url, licence,
  dataset_type, consent_ref, annotator, split` — `dataset_type` distinguishes
  `public_licensed` (Stage 1) from `consented_original` (Stage 2, consent_ref
  mandatory; enforced by the script).
- Source registry `ml/data/raw/datasets.csv` carries licence/source/mapping per
  group; per-image overrides come from `_attribution.csv` sidecars (Open Food
  Facts, Wikimedia).
- Curation: SHA-256 exact-dedup (54 removed), near-duplicate grouping via
  64-bit average hash (Hamming ≤ 4; 501 groups), deterministic pre-sample cap
  2,500 per (class, source) before analysis, per-split class balancing.
- Leakage control: duplicate groups share a split; ONE oversized augmented-rice
  family (>25 % of its class) was dissolved into singletons — documented as a
  minor residual-leakage limitation.
- **Final Stage-1 dataset: 6,221 images (seed 42)** — clothing 1,512 (1100/192/220),
  grains_rice 1,430 (1063/204/163), packaged_food 897 (627/134/136),
  utensils 1,540 (1100/220/220), other 842 (589/126/127).
  Distribution report: `ml/reports/dataset_distribution.json` / `.png`.

### Training (architecture unchanged from M2)

MobileNetV2, ImageNet backbone, fresh 5-class head; 224×224, ImageNet
normalization; seed 42 everywhere; 12 frozen-head epochs (Adam lr 1e-3) + 2
fine-tune epochs (last 3 blocks, lr 1e-5); model selection on validation only;
test split untouched until evaluation. Hardware inspected first: i5-12450HX
(8C/12T), 11.7 GB RAM, 219 GB free on D:. ML venv: torch 2.15.0+cpu.
Commands in `ml/README.md`. Best validation accuracy: **0.9909** (epoch 7).

### Evaluation (held-out test, touched once)

**Overall accuracy 0.9896 on 866 test images.** Per-class P/R/F1: clothing
0.9955/0.9955/0.9955 · grains_rice 1.0000/1.0000/1.0000 · packaged_food
0.9926/0.9926/0.9926 · utensils 0.9954/0.9773/0.9862 · other
0.9542/0.9843/0.9690. Confusion concentrated in utensils↔other (6 of 9
errors). All reports in `ml/reports/`: metrics JSON, confusion-matrix PNG,
summary MD, loss curves PNG, training history JSON, dataset distribution
JSON+PNG. No small-class limitation triggered (min support 127).

### Integration

- `model_versions` row `seva_image_classifier v1` (active) and
  `model_evaluations` row registered in the dev database via the new
  `ml/src/registry.py`.
- Weights at `ml/models/image_classifier_v1.pt` — exactly the existing
  `CLASSIFIER_WEIGHTS_PATH` default; no backend code change needed. Weights
  are gitignored; metadata JSON is committed.
- Live API test (`ml/src/test_classify_api.py`, backend served from the ML
  venv): real predictions returned for all five classes from held-out test
  images — clothing 1.000, grains_rice 1.000, packaged_food 0.998, utensils
  MISS (predicted `other` 0.916 — consistent with utensils recall 0.977),
  other MISS (packaged_food 0.547 vs other 0.45 on an ambiguous board-game
  photo). Invalid uploads still 422. The upload rate limiter correctly
  engaged during repeated runs.
- **Fallback preserved:** in the standard backend venv (no torch),
  `classifier_status` honestly reports "weights exist but PyTorch/torchvision
  are not installed" → `model_not_configured`; manual category selection and
  all M1/M2 behaviour unchanged.

### Test results after integration

Backend `pytest` **62 passed** · frontend `vitest` **27 passed** · production
build clean (415.5 kB JS). M1/M2 functionality and API contracts untouched
(only additive ML-side changes; one backend-venv-free fix in `registry.py`).

### Known limitations / notes for Stage 2

1. **Public-benchmark images ≠ real donation photos.** 0.9896 describes this
   distribution only; expect a substantial drop on real ashram-collected
   photos. Never present Stage-1 metrics as production readiness.
2. packaged_food under-represented (OFF API rate limits).
3. Minor within-family leakage possible for dissolved augmented-rice groups.
4. No training-time augmentation in our pipeline (upstream augmentation exists
   only for rice — inflates that class's separability).
5. Stage 2 wiring is ready: add a `consented_original` group with consent_ref
   → re-run prepare (`--force`) → train a new version → evaluate → compare in
   reports; previous model stays registered for rollback.

---

## Stage 1 review audit (2026-10-31) — read-only verification before M3

Five checks requested by the reviewer. No retraining, no split changes, no
application-code changes, no M3 work.

**1. Rice dataset leakage — MEASURED, material.** Re-analysis (average hash,
Hamming ≤ 4, the pipeline's own criterion) found that **100 % of rice test
images (163/163) have a near-duplicate in the train split**; clothing 41.8 %
(92/220) and utensils 15.0 % (33/220) also leak; packaged_food 2.2 % and
other 3.1 % are near-clean. Root cause: the Koklu source is one augmented
family per variety (filenames are bulk counters 1–15,000 with no family
marker), the near-duplicate grouping detected the giant family, and the
>25 %-of-class dissolution rule split it across splits; clothing/utensils
leakage comes from near-duplicate pairs across different duplicate groups
(visually recurrent studio/encyclopedic imagery). **The grains_rice F1 1.0000
and the other affected per-class numbers are potentially optimistic and are
now labelled as such in `docs/AI_ML_METHODOLOGY.md`, together with the full
leakage table.** The reported metrics are preserved unchanged as the
historical Stage-1 baseline. Recommended (not applied): full transitive
near-dup clustering + atomic families + per-family down-sampling in the next
dataset version; obtain non-augmented rice originals from upstream if
possible.

**2. Open Food Facts 697 vs 897 reconciled; provenance gap found and repaired.**
The final dataset contains **897** OFF images from two runs: run 1 saved 497
(public API then rate-limited), the top-up saved 400 new. The top-up's sidecar
overwrote run 1's rows and re-encountered only 297 of run 1's codes (OFF API
ordering shifts between calls) → **200 files lacked per-image attribution**
(the distribution report's 897 is the true on-disk count; the "697" was run
2's handled-count). Repair (dataset metadata only — no code, model, or split
changes): an OFF filename **is** the product code, so `_attribution.csv` was
regenerated deterministically with per-product source URLs for all files.
Verified after repair: **897/897 files have attribution rows with per-product
URLs; every `labels.csv` OFF row traces to an existing raw file and sidecar
row (0 failures).** Earlier-run images confirmed as genuine OFF product photos
with the same group licence.

**3. Original rice licence verified upstream.** The Hugging Face mirror
(`miladfa7/Rice-Image-Dataset`) carries no licence tag of its own. Upstream
evidence: the authors' official distribution
(`kaggle.com/datasets/muratkokludataset/rice-image-dataset`, owner
`muratokludataset`) states **"CC0: Public Domain"**; the dataset is documented
by the authors' paper (Koklu, Cinar & Taspinar 2021, Computers and Electronics
in Agriculture, S0168169921003021). Several search-suggested Mendeley DOIs
were checked and do NOT resolve (404) — they are recorded as unreliable. The
IMAGE licence (CC0) is explicitly distinct from any repository CODE licence
(e.g. Apache/MIT files in analysis repos do not govern the images).
Attribution/redistribution requirements for every source are documented in
`ml/data/README.md` (CC0 needs none but the paper is cited anyway; CC BY 4.0
attribution via the registry; CC-BY-SA per-photo credit via `_attribution.csv`).

**4. Runtime instructions verified and documented.** `ml/.venv` contains the
backend requirements PLUS torch (verified importable) — launching
`cd backend && ../ml/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`
serves the trained classifier (this exact command was used for the live
five-class API test). The standard `backend/.venv` is **intentionally
PyTorch-free** (verified: `import torch` fails there) →
`model_not_configured`; all contracts unchanged. README now explains both
environments in a dedicated subsection.

**5. Frontend test count discrepancy explained — no test harmed.** Git
history: commit `19b99aa` (M1) contains exactly **14** frontend tests
(route-guards 5, login 4, register 5); the same three files at HEAD still
contain exactly 5+4+5 with an empty test-case diff — no deletion, weakening,
or replacement. M2 added 13 new tests (create-donation 9 + donor dashboard 4)
→ 27 total. The M2 report's "13 M1 + 14 M2" was a transposed-typing error;
correct statement: **14 preserved M1 tests + 13 new M2 tests = 27**.

### Post-audit verification

Backend `pytest` **62 passed** · frontend `vitest` **27 passed** · production
build clean. Files changed by the audit: documentation only
(`README.md`, `ml/README.md`, `ml/data/README.md`,
`docs/AI_ML_METHODOLOGY.md`, `docs/BUILD_LOG.md`) plus the regenerated OFF
`_attribution.csv` (gitignored dataset metadata).

---

## Milestone M3 — Needs and Matching (2026-11-01)

Git state verified before starting: `main` at `4aca0e3`, clean tree. All
M1/M2/Stage-1 commits untouched; no history rewritten.

### Built

**Organizations (application + verification)**
- `POST /api/organizations/apply` (org role, once per account, multipart):
  name/type/description/address/contacts/representative + coordinates only
  with consent (range-validated) + verification document (PDF/JPEG/PNG,
  magic-byte checked, ≤10 MB, UUID name, stored outside the web root). A 422
  on the document leaves no application row and no orphan file.
- `GET /api/organizations/me` + `GET /api/organizations/{id}/verification-document`
  (owner or admin only; 404 for others — no existence leak).
- Admin: `GET /api/organizations/admin/all` (status filter, pagination),
  `GET /admin/{id}` (details + authorized document URL),
  `POST /admin/{id}/verify|reject|suspend` — reject/suspend require a reason;
  every decision audited (`organization.verify|rejected|suspended` with
  previous→new status).
- Public: `GET /api/organizations` (verified only, no contact details) and
  `GET /api/organizations/{id}/public-needs` (active needs of a verified org).

**Needs (verified organizations only)**
- `POST /api/needs`, `GET /api/needs/mine`, `GET/PATCH /api/needs/{id}`,
  `POST /api/needs/{id}/status` (active⇄paused, →closed terminal),
  `POST /api/needs/{id}/fulfilment` (race-safe conditional UPDATE —
  over-fulfilment impossible; auto-`fulfilled` at the target, audited),
  `GET /api/needs/public` (guest-accessible active needs of verified orgs).
- Remaining quantity computed server-side; CHECK constraints bound
  fulfilled ≤ required; subcategory must belong to the need's category.

**Matching engine (`app/services/matching.py`)** — rule-based, deterministic,
no ML: eligibility filter with reason codes (`organization_not_verified`,
`no_active_need`, `need_not_active`, `need_fully_funded`,
`category_incompatible`, `outside_service_radius`) → five weighted factors
(compatibility 0.30 exact/0.5 related, urgency 0.25, Haversine distance 0.20
with neutral 0.5 + explicit "Distance could not be calculated." when missing,
quantity_fit 0.15, timeliness 0.10) → deterministic order (score desc, need
created_at asc, organization id asc). Weights/radius from the `settings`
table with approved defaults. Client AI fields never consulted. Exposed
read-only via `GET /api/donations/{id}/matches` (owner donor or admin);
no offers created in M3.

**Frontend**
- Organization: application form (`/organization/apply`), dashboard with
  verification banner + needs management (create via `/organization/needs/new`,
  edit, pause/resume/close, fulfilment dialog with remaining-quantity display).
- Admin: applications list with status filter (`/admin/organizations`), review
  page (`/admin/organizations/:id`) with authorized document link and
  approve/reject/suspend dialogs (reason required for reject/suspend).
- Donor: `DonationMatches` component on pending donation details — ranked
  organizations, verified badges, per-factor score×weight breakdown, reasons,
  distance (or the explicit fallback sentence), meaningful empty state with
  exclusion summary.
- Public directory `/organizations` (closes the M1-deferred "Find
  organizations" CTA) + public needs display.

### Database changes

- `3cb71d79fa42`: `organizations.description`,
  `organization_needs.subcategory_id` (FK).
- `a7c31f9d21b4`: **defect fix** — `organization_documents.uploaded_at` had a
  string server default (`'CURRENT_TIMESTAMP'` stored as TEXT, rows unreadable);
  replaced with the SQL keyword via batch alter + defensive row repair.
  Discovered by the new M3 tests; the table was never read by M1/M2.
- `create_admin.py` now seeds the related-category compatibility pairs
  (packaged_food↔grains_rice, clothing↔other, utensils↔other, both directions).

### Defects found and fixed during M3

1. `organization_documents.uploaded_at` string server default (migration
   `a7c31f9d21b4`) — latent M1 schema bug surfaced by M3 tests.
2. M2 `test_list_date_range_filter` timezone flake: local-date filters vs UTC
   `created_at` broke between local midnight and 05:30 — test anchored at
   yesterday (filter semantics unchanged, UTC storage is correct).

### Commands and results

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest` | **104 passed** (62 preserved + 42 new) |
| Frontend tests | `npm test` | **38 passed** (14 M1 + 13 M2 + 11 M3) |
| Production build | `npm run build` | clean (454.4 kB JS / 20.6 kB CSS) |
| Migration check | `alembic upgrade head` (002, 003) + column/DDL verification | OK |
| API smoke | `scripts/smoke_m3.py` | ALL PASSED — invalid doc 422, apply 201, unverified block 403, doc authz (owner/admin 200, donor 404), verify 200, need 201, matches (score 92.0, distance 1.2 km, 5 factors, reasons, determinism), fulfil → auto-fulfilled → excluded, public endpoints |

### Known limitations / notes

1. No offers, notifications, pickup/completion, or payments — M4 scope.
2. Admin cannot manually adjust `quantity_fulfilled` (org fulfilment endpoint
   only); M4 wires offers/completion to fulfilment.
3. Matching is O(orgs × needs) in Python — fine for MVP scale; the public
   needs listing caps at 100 rows.
4. Needs list endpoints are authenticated (owner/admin); public exposure is
   the dedicated `/api/needs/public`.
5. The timeliness factor treats overdue required-by dates as fully urgent
   (documented in `AI_ML_METHODOLOGY.md`).

---

## Milestone M4 — Offers, Notifications, Payments (2026-11-01)

Git state verified before starting: `main` at `f18366b`, clean tree. All
previous commits untouched.

### Built

**Sequential offer engine (`app/services/offers.py`)**
- `initiate_offer`: re-runs the M3 matching engine (no duplicated scoring),
  skips organizations with any prior offer for the donation (decliners never
  re-offered), and creates ONE offer for the highest-ranked remaining
  candidate with a complete snapshot (score, rank, factors, weights, reasons,
  distance → `factor_json`).
- Initiation while an offer is `sent` is a no-op (same offer returned);
  initiation into `offered` is guarded by a conditional donation UPDATE.
- `accept_offer`: atomic conditional updates on offer (sent→accepted) AND
  donation (offered→accepted); any race loses with 409. Preserves the
  snapshot.
- `decline_offer`: conditional sent→declined with reason; donation stays
  `offered`; next candidate selected automatically (never the decliner);
  no candidate → lingering offers withdrawn, donation back to `pending`,
  donor notified.
- No `expired` status anywhere; donation and offer states remain separate.

**Pickup and completion (`app/services/pickup.py`)**
- `accepted → pickup_scheduled → picked_up → completed`, all server-side;
  scheduling captures date/window/instructions (migration `c4d85e01a9b7`).
- Completion records the ACTUAL `quantity_received` (validated >0, ≤ donated)
  on the offer and updates the linked need in the SAME transaction with
  `delta = min(received, remaining)` via a conditional UPDATE — no
  over-fulfilment, no double-counting (repeat hits the donation status guard
  → 409), auto-`fulfilled` at the target.

**Notifications (`app/services/notifications.py`, `app/api/notifications.py`)**
- In-app only; created transactionally within each workflow; per-user list
  with unread count, mark-one-read, mark-all-read; strict per-user
  authorization. Events: offer_received, offer_sent, offer_accepted,
  offer_declined, no_candidate, pickup_scheduled, picked_up,
  donation_completed, upi_setup_submitted, payment_submitted,
  payment_verified, payment_rejected.

**Payments (`app/api/payments.py`)** — manual verification only, no gateway
- Verified orgs submit UPI ID (format-validated) + optional QR image
  (magic-byte checked, ≤10 MB, stored outside web root) →
  `pending_approval`; admins approve/reject (reason required); `approved`
  details become donor-visible on accepted donations.
- Donors submit transaction reference (6–40 alnum) + optional receipt
  (PDF/JPEG/PNG ≤5 MB, authorized access) → `submitted_unverified`; admins
  verify/reject with reason; donor notified; donation status never changes
  from payment events.

**Frontend**
- Notification center (`/notifications`) + header bell with unread badge
  (30-second polling).
- Donation detail: offer progress/history with matching snapshots, "send
  offer to top match" action, accepted-org pickup details, completion state,
  payment instructions (QR/UPI + disclaimer) and reference submission with
  per-payment statuses.
- Organization: incoming-offers page (accept/decline with reason dialog,
  matching snapshot display, pickup scheduling dialog, picked-up/complete
  actions) and payment setup page (status badges, resubmission resets
  approval).
- Admin: payment verification queue (status filter, authorized receipt links,
  verify/reject with reason).

### Database changes

- `c4d85e01a9b7`: offer pickup columns (date/window/instructions).
- `e91b7f3c5d20`: `payment_records.donation_id` + `rejection_reason`.
- `b7e2a94c6f10`: monotonic `seq` columns (status history per donation,
  notifications per user) + backfill — created_at ties (second precision on
  Windows) made `ORDER BY created_at` non-deterministic.

### Defects found and fixed during M4

1. **Silent history-row loss**: bulk status UPDATEs synchronize the ORM
   identity map BEFORE `record_transition`, whose dedupe guard then saw the
   new status and skipped the append-only history row (offer/accept/complete
   paths). Fixed by writing history BEFORE the guarded bulk update in all
   three paths; the row rolls back with everything else if the guard fails.
2. **Non-deterministic ordering**: `created_at` ties (second precision on
   Windows) made `history[-1]`/notification order unstable — fixed with the
   `seq` tie-breakers (migration `b7e2a94c6f10`).
3. **No-candidate notification gap**: a fresh `pending` donation with no
   eligible organization never notified the donor — the notify call was inside
   the `offered`-only branch; now always notified (spec §5).
4. M2 `record_status_transition` lacked the seq tie-breaker (cancel test
   ordering flake) — aligned with the M4 implementation.

### Commands and results

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest` | **138 passed** (104 preserved + 34 new) |
| Frontend tests | `npm test` | **45 passed** (38 preserved + 7 new) |
| Production build | `npm run build` | clean (483.1 kB JS / 21.4 kB CSS) |
| Migrations | `alembic upgrade head` (004, 005, 006) | OK |
| E2E smoke | `scripts/smoke_m4.py` (dedicated clean DB, seeded admin) | ALL PASSED — sequential offers, decline→next, re-initiate no-op, accept, UPI approval → donor payment info, pickup → picked up → completed (need +9, repeat 409), payment submission → donor 403 → admin verified, full notification sequence |

### Known limitations / notes

1. M5 scope (admin analytics overview, demo seed script, final polish, clean-
   clone README verification) remains.
2. Concurrent acceptance is enforced by conditional UPDATEs with status
   guards; tests verify the second writer always 409s. True parallel-writer
   races are protected by the same pattern plus SQLite/Postgres write locking.
3. `quantity_received` above the need's remaining amount is capped for the
   need increment (the offer still records the full received quantity) —
   documented in `AI_ML_METHODOLOGY.md` §9 relationship notes.
4. Notification bell polls every 30 seconds (no websockets by design).
5. Payment references are opaque strings; no bank integration exists or is
   planned (manual verification only).

