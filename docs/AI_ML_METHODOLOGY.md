# SEVA-AI — AI/ML Methodology and Model Card

This document is the project's AI/ML model card. Every number shown anywhere in
the product or reports must originate from `ml/reports/`; nothing here is
estimated, projected, or invented.

---

## Part 1 — Image classifier (donated-item categories)

### Dataset strategy

**Stage 1 (this release): publicly licensed datasets** — chosen because no
consented real-world collection exists yet. **Stage 2 (planned): photographs
collected by the team during ashram visits**, entering the pipeline as
`dataset_type=consented_original` with mandatory consent references, producing
a new dataset version, a new model version, an independent evaluation, and a
comparison against the Stage-1 baseline (previous versions stay registered for
rollback).

### Stage 1 dataset (public licensed, seed 42)

| SEVA class | Source | Licence (as stated by the host) |
|---|---|---|
| clothing | Apparel Images Gallery (AIG), Mendeley Data v1 (130,014 garment photos) | CC BY 4.0 |
| grains_rice | Rice Image Dataset — Koklu, Cinar & Taspinar (2021), 75,000 grain photos, 5 varieties | CC BY 4.0 |
| packaged_food | Open Food Facts product front photos (contributor-credited) | CC-BY-SA / CC0 per upload |
| utensils | Kitchen Utensils Dataset 13K (10 utensil classes) | MIT |
| other | Wikimedia Commons: toys, dolls, plush toys, books, board games, children's games, school supplies | per-file: CC0 / PD / CC BY / CC BY-SA only |

- **Rejections (documented):** Freiburg Groceries (host unreachable during
  collection; no image licence in the repository), BookCover30 (images
  copyrighted by Amazon; "fair use" only — not a redistribution licence),
  HoloSelecta (archive contains 295 images plus study data, far fewer than its
  title suggests).
- **Curation:** exact-duplicate removal (SHA-256), near-duplicate grouping
  (64-bit average hash, Hamming ≤ 4), per-(class, source) pre-sample cap,
  per-split class balancing, licence metadata per image. Details and rules:
  `ml/data/README.md`.
- **Leakage control:** images from the same duplicate group always share a
  split. One oversized augmented-rice family exceeded 25 % of its class and was
  dissolved into singletons — a small within-family leakage remains possible
  for augmented sources and is recorded as a limitation.
- **Measured distribution (this build, seed 42):** see
  `ml/reports/dataset_distribution.json` / `.png`. Build totals: **6,221
  images** — clothing 1,512 · grains_rice 1,430 · packaged_food 897 ·
  utensils 1,540 · other 842 (train/val/test splits in the report).
- **Known distribution limitation:** `packaged_food` is smaller than the other
  classes because the Open Food Facts public API rate-limited anonymous
  collection at 697 raw images; this is visible in the per-class metrics.

### Model design (unchanged from the M2 architecture)

| Aspect | Decision |
|---|---|
| Model | MobileNetV2 (torchvision), ImageNet backbone, classifier head replaced |
| Classes | Exactly five, fixed: `clothing`, `grains_rice`, `packaged_food`, `utensils`, `other` |
| Input | 224×224, RGB, ImageNet normalization |
| Training | Phase 1: backbone frozen, head trained (Adam, lr 1e-3, 12 epochs). Phase 2: last 3 blocks unfrozen (lr 1e-5, 2 epochs) |
| Seed | 42 for Python, NumPy, and PyTorch; recorded in `model_metadata.json` |
| Model selection | Training + validation splits only; early selection by best validation accuracy |
| Evaluation | Held-out test split touched exactly once: per-class precision/recall/F1, overall accuracy, confusion matrix → `ml/reports/` |

Admin-added display subcategories (e.g. "Men's", "Rice") are UI taxonomy only —
they never become classifier classes and never change model output labels.

### Inference integration

- Canonical inference logic: `ml/src/predict_image.py` (single source of truth).
- The backend wraps it through `backend/app/ml/classifier.py`, imported lazily.
- `CLASSIFIER_WEIGHTS_PATH` resolves against the backend configuration
  directory; the resolved path and file-presence flag are logged at startup.
- When the weights file is missing — or PyTorch is unavailable — the endpoint
  returns `{"status": "model_not_configured"}` with HTTP 200, and manual
  category selection keeps working. No auto-download at startup; no fabricated
  predictions.

### Measured results (Stage 1 model `v1`, held-out test split)

Copied verbatim from `ml/reports/image_classifier_v1_metrics.json` /
`image_classifier_v1_summary.md` (evaluated 2026-10-31, 866 test images,
touched once, seed 42):

- **Overall accuracy: 0.9896**
- Best validation accuracy during training: 0.9909 (frozen-head epoch 7)
- Per class:

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| clothing | 0.9955 | 0.9955 | 0.9955 | 220 |
| grains_rice | 1.0000 | 1.0000 | 1.0000 | 163 |
| packaged_food | 0.9926 | 0.9926 | 0.9926 | 136 |
| utensils | 0.9954 | 0.9773 | 0.9862 | 220 |
| other | 0.9542 | 0.9843 | 0.9690 | 127 |

- Confusion matrix (rows = actual, columns = predicted; 9 errors in total):
  clothing→other 1, packaged_food→clothing 1, utensils→other 5,
  other→packaged_food 1, other→utensils 1. The confusion is concentrated in
  "utensils"/"other" — the two classes whose public sources are the most
  semantically diffuse.
- All classes have ≥ 127 test images, so no small-class limitation note is
  triggered (threshold: 20).
- Training/validation curves: `ml/reports/loss_curves.png`; per-epoch history:
  `ml/reports/training_history.json`; confusion-matrix figure:
  `ml/reports/image_classifier_v1_confusion_matrix.png`.
- Registry: `model_versions` row `seva_image_classifier v1`
  (id `1a6602ea-4b08-46ea-bb6b-016a8b8a6af2`, active) and `model_evaluations`
  row (id `8d0eadce-f8b1-40ec-9748-7d37749ae6f2`, split "test") in the dev
  database. Weights: `ml/models/image_classifier_v1.pt` (gitignored; metadata
  JSON committed).

### Limitations (stated plainly)

- **Public benchmark images are not real donation photographs.** AIG is
  studio-style apparel, rice images are flat-lay grain scans, and Wikimedia
  images are encyclopedic photos. The 0.9896 test accuracy describes
  performance on THIS distribution only and must never be read as production
  readiness on real donation photos — expect a substantial drop on Stage-2
  real-world images, which is exactly why that stage is planned.
- Class distributions are domain-skewed: "clothing" is garment-type classes,
  "grains_rice" is rice-variety scans, and "other" is encyclopedic miscellany.
- `packaged_food` is under-represented (897 images; Open Food Facts API rate
  limits stopped anonymous collection) — visible as the smallest test support.
- The classifier sees only the primary photograph; supporting photos are not
  processed in this release.
- Augmented-source families may retain minor within-family leakage after
  oversized-group dissolution (documented above).
- No training-time augmentation was used (honest, simple pipeline); the
  Koklu rice images are already augmented upstream, which inflates that
  class's apparent separability relative to natural photographs.
- Any class with fewer than 20 test images triggers an explicit limitation
  note in the evaluation summary and the UI.

---

## Part 2 — Explainable matching (rule-based, NOT machine learning)

The donation-to-organization matching engine is a **deterministic, rule-based
scoring formula** — it is not a trained model and must never be described as
machine learning in the UI or documentation.

_Implemented in milestone M3; the formula, weights, factor definitions, unit
compatibility table, and determinism tests will be documented here then._

### Unit compatibility (normative for M3)

Donation units and need units must match directly for a candidate need to be
eligible; quantities are never silently converted between units in this
release. Compatible set: `kg` ↔ `kg`, `pieces` ↔ `pieces`, `packets` ↔
`packets`, `sets` ↔ `sets`, `litres` ↔ `litres`. (A documented compatibility
table with related-category allowances ships with M3.)

### Acceptance-prediction extension (optional, §9.4)

`train_acceptance_model.py` may run only when at least 60 genuine resolved
offers with at least 20 of each outcome exist. With demo seed data, anything
trained on it must be labelled "trained on demo data — not for real decisions".
Not implemented in this release.
