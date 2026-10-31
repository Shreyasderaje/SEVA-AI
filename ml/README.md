# SEVA-AI — Machine Learning Pipeline

This directory contains the complete, honest ML pipeline for SEVA-AI's two
academic contributions:

1. **Image classification** of donated items (transfer learning on MobileNetV2,
   five fixed classes).
2. **Explainable donation-to-organization matching** (rule-based baseline —
   implemented in `src/matching_baseline.py` in milestone M3, shared with the
   backend; it is NOT machine learning).

## Dataset strategy

**Stage 1 (this release): public licensed datasets.** The five SEVA-AI classes
are trained from verifiably licensed public image sources (see
`ml/data/README.md` for the full registry, licences, sizes, and curation
rules):

| SEVA class | Source | Licence |
|---|---|---|
| clothing | Apparel Images Gallery (AIG), Mendeley Data | CC BY 4.0 |
| grains_rice | Rice Image Dataset (Koklu et al. 2021), HF mirror | CC BY 4.0 |
| packaged_food | Open Food Facts product photos | CC-BY-SA / CC0 per upload |
| utensils | Kitchen Utensils 13K, Hugging Face | MIT |
| other | Wikimedia Commons (books/toys/games), per-file licence check | CC0 / PD / CC BY / CC BY-SA |

**Stage 2 (future): consented original photographs.** The team will collect
real-world donation photos during ashram visits. The registry already supports
`dataset_type=consented_original` with a mandatory `consent_ref`; new data gets
a new dataset version, a retrained model version, an independent evaluation,
and a comparison against this Stage-1 baseline. The previous model stays
registered and active-flagged for rollback (`model_versions.is_active`).

## Setup

ML dependencies are separate from the backend (the backend runs without
PyTorch — see the honest fallback below).

```bash
python -m venv ml/.venv
source ml/.venv/Scripts/activate        # Git Bash on Windows
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r ml/requirements.txt
```

## Workflow (Stage 1, reproducible)

```bash
# 1. Fetch the public datasets (downloaders keep per-image attribution):
ml/.venv/Scripts/python.exe ml/src/fetch_utensils.py --per-class 260
ml/.venv/Scripts/python.exe ml/src/fetch_wikimedia_other.py --per-category 200
ml/.venv/Scripts/python.exe ml/src/fetch_openfoodfacts.py --count 1300
# AIG (879 MB RAR) and the rice ZIP are direct downloads — see ml/data/README.md.
# Extraction: use the bundled bsdtar for RAR: /c/Windows/System32/tar.exe -xf ...

# 2. Curate + split (dedup, near-dup grouping, balance, seed 42):
ml/.venv/Scripts/python.exe ml/src/prepare_dataset.py --force

# 3. Train (frozen head 12 epochs + fine-tune 2 epochs, seed 42):
cd backend && ../ml/.venv/Scripts/python.exe -u ../ml/src/train_image_classifier.py \
    --epochs 12 --fine-tune --ft-epochs 2 --register

# 4. Evaluate ONCE on the held-out test split:
cd backend && ../ml/.venv/Scripts/python.exe ../ml/src/evaluate_image_classifier.py \
    --version v1 --register

# 5. The backend loads the weights via CLASSIFIER_WEIGHTS_PATH
#    (default ../ml/models/image_classifier_v1.pt — already configured).
#    Launch the backend FROM the ML environment so torch is available:
cd backend && ../ml/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
#    (the standard backend/.venv is PyTorch-free and honestly reports
#     model_not_configured — see README.md for the two-environment table)

# CLI inference:
ml/.venv/Scripts/python.exe ml/src/predict_image.py path/to/image.jpg
```

Measured results live in `ml/reports/` and `docs/AI_ML_METHODOLOGY.md`. Run
commands and counts are recorded in `docs/BUILD_LOG.md`.

## Honesty rules (enforced by convention — do not break them)

- Never claim an accuracy figure that is not present in `ml/reports/`.
- Never present synthetic or placeholder images as real training data; every
  training image traces to a documented source and licence.
- The test split is touched exactly once, by `evaluate_image_classifier.py`.
- Model metadata (`model_metadata.json`) records seed, date, label list, split
  sizes, settings, and measured test metrics; reports reference the version.
- If any class has fewer than 20 test images, the evaluation report says so and
  the UI shows a limitation note.
- Public benchmark images are NOT real donation photos: results are a Stage-1
  baseline, never a claim of production readiness. Stage 2 (consented ashram
  photos) exists for that reason.
- The backend's `model_not_configured` fallback and manual category selection
  are always preserved.
