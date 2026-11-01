# SEVA-AI

**AI-Powered Smart Donation and Charity Resource Management System** — a college
mini project.

SEVA-AI connects public donors with verified ashrams, NGOs, and charitable
organizations. Donors list physical items (clothes, rice, grains, packaged
food, utensils); verified organizations publish their current needs. The system
classifies donated-item photos into five broad categories (transfer learning)
and recommends suitable organizations using a transparent, explainable,
rule-based matching formula. Offers, pickups, completions, and UPI payments
(manual admin verification) complete the workflow.

> **Demo-scope notice:** this is a college mini project. Demo data is synthetic
> and clearly labelled. Payment references are verified manually by admins —
> SEVA-AI never processes payments. The image classifier was trained on public
> benchmark datasets; its metrics are NOT real-world donation accuracy.

## Technology stack

| Area | Choice |
|---|---|
| Frontend | React 18 + Vite + TypeScript, Tailwind CSS + shadcn/ui, Lucide, Recharts |
| Backend | Python FastAPI |
| Database | SQLite (dev), PostgreSQL optional via `DATABASE_URL` |
| ORM / migrations | SQLAlchemy 2.x + Alembic |
| Auth | JWT access tokens, bcrypt password hashing |
| Rate limiting | slowapi (login, registration, uploads) |
| ML | PyTorch + torchvision (MobileNetV2 transfer learning), scikit-learn |

## Architecture summary

```
frontend/  React SPA — Tailwind design tokens, shadcn/ui primitives, feature
           modules per role, route guards, Zod validation, Recharts analytics.
backend/   FastAPI — routers per resource, services layer (matching, offers,
           pickup, notifications, payments, storage, audit), SQLAlchemy 2.x
           models, Alembic migrations. No PyTorch dependency by design.
ml/        Dataset pipeline (Stage-1 public licensed datasets), training/
           evaluation/inference scripts, model registry. Lives in ml/.venv.
docs/      Architecture, database schema, AI/ML methodology, testing report,
           build log.
```

Two backend environments are intentional: `backend/.venv` is PyTorch-free (the
classify endpoint then honestly returns `model_not_configured`), while
`ml/.venv` adds torch for serving the trained classifier. See
`docs/ARCHITECTURE.md`.

## Prerequisites

- Python 3.11+ (Windows: install from python.org, tick "Add to PATH")
- Node.js 18+ / npm 9+
- Git

## Installation (Windows PowerShell)

```powershell
git clone <repository-url> seva-ai
cd seva-ai
```

### Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1            # PowerShell (Git Bash: source .venv/Scripts/activate)
pip install -r requirements.txt

copy .env.example .env                # then edit .env:
#   set JWT_SECRET to a long random string (e.g. python -c "import secrets;print(secrets.token_hex(32))")
#   defaults (SQLite, port 8000) are fine for development

alembic upgrade head                  # create the schema
python scripts\create_admin.py        # seeds the admin account + base reference data
#   prints the generated admin password ONCE — store it (or set SEVA_ADMIN_PASSWORD first)

uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs · health: http://localhost:8000/api/health

### Frontend setup

```powershell
cd frontend                           # from the repository root
npm install
npm run dev                           # http://localhost:5173 (proxies /api to :8000)
```

If port 8000 is taken, run the backend on another port and start the dev
server with `VITE_API_TARGET=http://localhost:<port> npm run dev`.

### Serving the trained classifier (optional)

```powershell
# one-time ML environment setup (torch CPU + pipeline deps):
python -m venv ml\.venv
ml\.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r ml\requirements.txt
pip install -r backend\requirements.txt
deactivate

# then run the backend FROM the ML environment:
cd backend
..\ml\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Without the ML environment (or without trained weights at
`CLASSIFIER_WEIGHTS_PATH`), the classify endpoint returns
`model_not_configured` and donors choose the category manually — fully
supported, never an error state.

## Environment variables (`.env`, created from `.env.example`)

| Variable | Purpose |
|---|---|
| `SEVA_ENV` | Must be `development` for demo seed/reset scripts |
| `DATABASE_URL` | `sqlite:///./seva.db` (default) or a PostgreSQL URL |
| `JWT_SECRET` | Long random string; required outside development |
| `JWT_EXPIRE_MINUTES` | Access-token lifetime (default 60) |
| `CORS_ORIGINS` | Allowed frontend origin (default `http://localhost:5173`) |
| `STORAGE_DIR` | Upload storage (outside the web root) |
| `CLASSIFIER_WEIGHTS_PATH` | Trained weights; resolved against the backend directory |
| `SERVICE_RADIUS_KM` | Matching radius (default 50) |
| `RATE_LIMIT_LOGIN` | slowapi limit for auth endpoints (default 5/minute) |
| `SEVA_ADMIN_EMAIL` / `SEVA_ADMIN_PASSWORD` | Optional admin seed overrides |

## Database migrations

```powershell
cd backend
alembic upgrade head        # apply all
alembic current             # show current revision
alembic downgrade -1        # roll back the last one (verify on a copy first)
```

## Admin account setup

```powershell
cd backend
python scripts\create_admin.py
```

Idempotent. Prints the generated admin password once (or uses
`SEVA_ADMIN_PASSWORD`). Also seeds the five fixed donation categories, example
display subcategories, related-category matching pairs, and default matching
settings.

## Demo data seeding (development only)

```powershell
cd backend
$env:SEVA_ENV = "development"
python scripts\seed_demo.py
```

Creates clearly-labelled demo records (`is_demo_data=true`): 3 demo donors,
2 verified + 1 pending demo organizations ("Demo …" names), active needs,
donations across categories with generated placeholder photos, offers in
sequential states, notifications, and payment records. Demo login password:
`DemoOnlyPass1` (development-only). Demo emails end with `@demo.seva`.

## Demo data reset (development only)

```powershell
cd backend
$env:SEVA_ENV = "development"
python scripts\reset_demo.py --yes
```

Deletes ONLY rows marked `is_demo_data=true`, child records first, in one
transaction (rolled back on failure). Non-demo records (including the admin)
are never touched. Safe to run repeatedly.

## Running tests

```powershell
cd backend
.venv\Scripts\python.exe -m pytest          # 157 tests (all milestones)
cd ..\frontend
npm test                                     # 55 tests (Vitest + RTL)
npm run build                                # tsc + production build
```

Live smoke scripts (backend running on the given port):

```powershell
cd backend
.venv\Scripts\python.exe scripts\smoke_m2.py http://localhost:8000
.venv\Scripts\python.exe scripts\smoke_m3.py http://localhost:8000
.venv\Scripts\python.exe scripts\smoke_m4.py http://localhost:8010
```

## Production build

```powershell
cd frontend
npm run build        # outputs dist/
npm run preview      # serve the built bundle locally
```

## API documentation

FastAPI Swagger UI at **http://localhost:8000/docs** — every endpoint with
request/response schemas and auth requirements.

## User guide (short)

1. **Donor:** register → create a donation with 1–3 photos → confirm the AI
   category suggestion (or choose manually) → view recommended organizations
   with per-factor matching explanations → send the offer to the top match →
   follow pickup/completion → optionally submit a UPI payment reference for
   admin verification.
2. **Organization:** register → submit the application with a verification
   document → after admin verification, publish needs → receive offers
   (accept/decline with reason) → schedule pickup → mark picked up → complete
   with the actual received quantity → optionally submit UPI details for admin
   approval.
3. **Admin:** review organization applications and payment references (with
   authorized document/receipt access), manage users, view the analytics
   overview (`/admin`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `401 Unauthorized` right after login | `JWT_SECRET` changed or tokens expired — sign in again |
| Port 8000/5173 busy | use another port (`--port 8010` / `VITE_API_TARGET=...`) |
| `model_not_configured` | expected without the ML venv or trained weights — manual category selection works |
| Demo seed refuses to run | set `$env:SEVA_ENV = "development"` first |
| Demo reset deletes nothing | no demo records exist (or they were already reset) |
| DB locked (SQLite) | stop other backend processes before reset/delete |

## Known limitations

- Five broad classifier classes only; Stage-1 metrics are public-benchmark
  results with documented near-duplicate leakage — not real-world donation
  accuracy (see `docs/AI_ML_METHODOLOGY.md`).
- Matching is a rule-based formula validated only against the design, not real
  outcomes.
- Payments are manual admin verification; no gateway, no bank integration.
- Notifications are in-app only.
- Password reset is design-only (see `docs/ARCHITECTURE.md`).
- No automatic offer expiry (addendum decision).

## Documentation

- `docs/ARCHITECTURE.md` — components, auth, storage, offer engine, payments
- `docs/DATABASE_SCHEMA.md` — all tables, constraints, status machines, migrations
- `docs/AI_ML_METHODOLOGY.md` — classifier model card + matching specification
- `docs/TESTING_REPORT.md` — commands, counts, coverage, known gaps
- `docs/BUILD_LOG.md` — decisions and progress per milestone
