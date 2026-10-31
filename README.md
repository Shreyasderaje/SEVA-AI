# SEVA-AI

**AI-Powered Smart Donation and Charity Resource Management System** — a college mini project.

SEVA-AI connects public donors with verified ashrams, NGOs, and charitable organizations.
Donors list physical items (clothes, rice, grains, packaged food, utensils); verified
organizations publish their current needs. The system classifies donated-item photos into
broad categories (transfer learning) and recommends suitable organizations using a
transparent, explainable, rule-based matching formula.

> **Status: Milestone M3 complete (Needs and Matching).** Delivered so far:
> accounts/RBAC (M1), donations + image classification with the honest
> `model_not_configured` fallback (M2 + Stage-1 public-dataset classifier),
> organization applications and admin verification, needs management with
> fulfilment tracking, and the explainable rule-based donation matching engine
> (M3). Offers, notifications, pickup/completion, and payments are later
> milestones. This README grows with the project.

## Tech stack

| Area | Choice |
|---|---|
| Frontend | React + Vite + TypeScript, Tailwind CSS + shadcn/ui, Lucide icons, Recharts |
| Backend | Python FastAPI |
| Database | SQLite (dev), PostgreSQL optional via `DATABASE_URL` |
| ORM / migrations | SQLAlchemy 2.x + Alembic |
| Auth | JWT access tokens, bcrypt password hashing |
| Rate limiting | slowapi (login, registration, uploads) |
| ML | PyTorch + torchvision (MobileNetV2 transfer learning), scikit-learn |

## Classifier status

Stage 1 of the dataset strategy trains the five-class MobileNetV2 classifier on
**publicly licensed datasets** (AIG apparel — CC BY 4.0; Koklu rice varieties —
CC BY 4.0; Open Food Facts product photos — CC-BY-SA/CC0; Kitchen Utensils 13K
— MIT; Wikimedia Commons household items — per-file licence verified). See
`ml/README.md` for sources and reproducible commands, and
`docs/AI_ML_METHODOLOGY.md` for the model card and measured metrics. These
public benchmark images are a Stage-1 baseline — **not** real donation photos;
collecting consented photographs at local ashrams is the planned Stage 2, and
the pipeline already supports it (`dataset_type=consented_original`).

If the trained weights file is absent (or PyTorch is not installed), the
backend honestly reports `model_not_configured` and donors choose the category
manually — manual selection is a first-class workflow, never an error state.

## Quick start (development)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate        # Git Bash on Windows
# .venv\Scripts\activate             # PowerShell
pip install -r requirements.txt

cp .env.example .env                 # then set JWT_SECRET to a long random value
alembic upgrade head                 # create schema
python scripts/create_admin.py      # seeds admin account + base reference data (idempotent)

uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs — health check: http://localhost:8000/api/health

### Running the backend WITH the trained classifier

There are two intentionally different backend environments:

| Environment | What it is | Classify endpoint behaviour |
|---|---|---|
| `backend/.venv` (standard) | **PyTorch-free** by design — small install, runs everything except inference | `POST /api/classify` returns `{"status": "model_not_configured"}`; donors choose the category manually (a first-class workflow) |
| `ml/.venv` (ML environment) | backend requirements **plus** torch/torchvision CPU | loads the trained weights from `CLASSIFIER_WEIGHTS_PATH` and returns real predictions |

To serve the trained classifier, launch the backend from the ML environment
(from the repository root):

```bash
cd backend
../ml/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

Both environments use the same `backend/.env`, database, and migrations; the
fallback behaviour never changes — if the weights file is missing, the ML
environment also reports `model_not_configured`. The standard `pytest` suite
runs in the PyTorch-free environment and keeps that contract tested.

## What exists (after M3)

- **Donors** register, create donations with 1–3 photos (AI category
  suggestion or manual choice), view explainable organization matches with
  per-factor scores, and track donation timelines.
- **Organizations** apply with a verification document, get verified by an
  admin, then publish and manage needs (quantities, urgency, fulfilment
  tracking).
- **Admins** review applications (authorized document access), approve/reject
  with audited reasons, and manage users.
- **Matching** is a deterministic, rule-based scoring engine — never machine
  learning — with published weights, Haversine distance, a 50 km service
  radius, neutral distance fallback, and human-readable explanations.

### Frontend

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173 (proxies /api to :8000)
```

If port 8000 is taken on your machine, run the backend on another port and point the
proxy at it: `VITE_API_TARGET=http://localhost:8010 npm run dev`.

### Tests

```bash
cd backend && .venv/Scripts/python.exe -m pytest
cd frontend && npm test
```

## Security notes

- Never commit `.env`. Secrets come from environment variables only.
- Demo credentials are documented **only** as development-only seed output; they are
  never valid for production use.
- Uploaded files are stored outside the web root and served only through authorized
  endpoints (later milestones).

## Documentation

See `docs/` — `ARCHITECTURE.md`, `DATABASE_SCHEMA.md`, `AI_ML_METHODOLOGY.md`,
`TESTING_REPORT.md`, and `BUILD_LOG.md` (progress and decisions per milestone).
