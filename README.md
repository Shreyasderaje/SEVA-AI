# SEVA-AI

**AI-Powered Smart Donation and Charity Resource Management System** — a college mini project.

SEVA-AI connects public donors with verified ashrams, NGOs, and charitable organizations.
Donors list physical items (clothes, rice, grains, packaged food, utensils); verified
organizations publish their current needs. The system classifies donated-item photos into
broad categories (transfer learning) and recommends suitable organizations using a
transparent, explainable, rule-based matching formula.

> **Status: Milestone M1 (Foundation) in progress.** Auth, database schema, and app shell
> are being built. Donations, matching, offers, notifications, and payments arrive in
> later milestones. This README grows with the project; full setup/demo instructions land
> in M5.

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
