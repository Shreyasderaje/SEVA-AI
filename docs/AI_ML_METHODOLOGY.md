# SEVA-AI — AI/ML Methodology and Model Card

This document is the project's AI/ML model card. Every number shown anywhere in
the product or reports must originate from `ml/reports/`; nothing here is
estimated, projected, or invented.

---

## Part 1 — Image classifier (donated-item categories)

### Honest current status

> **The SEVA-AI classifier is NOT trained.** No consented dataset has been
> collected yet, so no training run, no evaluation, and no measured metrics
> exist. The backend therefore runs in the documented `model_not_configured`
> mode: donors choose the category manually, which is a first-class workflow,
> not an error state.
>
> **ImageNet-pretrained MobileNetV2 weights are not a SEVA-AI classifier.**
> They are only the transfer-learning starting point for the backbone once a
> real labelled dataset exists. This project will never present pretrained
> ImageNet weights as a trained five-class donation classifier.

### Design

| Aspect | Decision |
|---|---|
| Model | MobileNetV2 (torchvision), ImageNet backbone, classifier head replaced |
| Classes | Exactly five, fixed: `clothing`, `grains_rice`, `packaged_food`, `utensils`, `other` |
| Input | 224×224, RGB, ImageNet normalization |
| Training | Phase 1: backbone frozen, head trained (Adam, lr 1e-3). Phase 2 (optional): last 3 blocks unfrozen, lr 1e-5 |
| Seed | 42 for Python, NumPy, and PyTorch; recorded in `model_metadata.json` |
| Splits | Stratified by label, grouped by source session, created once with seed 42; the test split is touched exactly once, by `evaluate_image_classifier.py` |
| Evaluation | Per-class precision/recall/F1, overall accuracy, confusion matrix → `ml/reports/` |
| Known-size guard | Any class with fewer than 20 test images triggers an explicit limitation note in the report and the UI |

Admin-added display subcategories (e.g. "Men's", "Rice") are UI taxonomy only —
they never become classifier classes and never change model output labels.

### Inference integration

- Canonical inference logic: `ml/src/predict_image.py` (single source of truth).
- The backend wraps it through `backend/app/ml/classifier.py`, imported lazily
  so the backend runs without PyTorch installed.
- `CLASSIFIER_WEIGHTS_PATH` is resolved against the backend configuration
  directory (never the terminal CWD); the resolved path and file-presence flag
  are logged in startup diagnostics without secrets.
- When the weights file is missing — or PyTorch is unavailable — the classify
  endpoint returns `{"status": "model_not_configured"}` with HTTP 200. Manual
  category selection and every other feature continue to work.
- No automatic model download happens at application startup. No fabricated
  prediction is ever returned.

### Dataset status

- **Collected: 0 images.** `ml/data/raw/` is empty; no consent references exist.
- The full pipeline (`prepare_dataset.py` → `train_image_classifier.py` →
  `evaluate_image_classifier.py` → `predict_image.py`) is implemented and
  compile-checked; the split logic is verified to be deterministic (seed 42),
  stratified per class, and free of source-session leakage (verified by an
  offline simulation; see `docs/BUILD_LOG.md`, M2).
- When a dataset is collected under the consent rules in `ml/data/README.md`,
  the pipeline produces the weights and the measured metrics that will fill
  the "Measured results" table below.

### Measured results

_None. No evaluation has been run — there is no dataset. When an evaluation
exists, its per-class precision/recall/F1, overall accuracy, and confusion
matrix will be copied here **from `ml/reports/`** with the model version._

### Limitations (of the design, independent of training)

- Five broad classes only; fine-grained items (e.g. rice vs. wheat) are left to
  the donor-confirmed display subcategory.
- Classification quality will depend entirely on the size, breadth, and quality
  of the consented dataset; small datasets will produce weak, high-variance
  classifiers, and the evaluation report will say so.
- The classifier sees only the primary photograph; supporting photos are not
  processed in this release.
- Preview thumbnails and the classifier assume real photographs of items;
  adversarial or unrelated images fall back to the `other` class at best.

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
