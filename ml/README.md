# SEVA-AI — Machine Learning Pipeline

This directory contains the complete, honest ML pipeline for SEVA-AI's two
academic contributions:

1. **Image classification** of donated items (transfer learning on MobileNetV2,
   five fixed classes).
2. **Explainable donation-to-organization matching** (rule-based baseline —
   implemented in `src/matching_baseline.py` in milestone M3, shared with the
   backend; it is NOT machine learning).

## Current status (honest)

- **No trained model exists.** No consented dataset has been collected yet, so
  no training or evaluation has been run, and no metrics exist. Nothing in
  `reports/` should be read as a measured result until a real dataset is
  provided and the pipeline is executed on it.
- ImageNet-pretrained MobileNetV2 weights are **not** a trained SEVA-AI
  classifier. They are only the starting backbone for transfer learning once a
  labelled dataset exists.
- Until a trained weights file exists at the configured path, the backend
  classify endpoint returns `model_not_configured` and donors choose the
  category manually. Manual selection is a first-class path, not an error.

## Layout

```
ml/
├── README.md                      # this file
├── data/
│   ├── README.md                  # consent rules, labelling guide, CSV schema
│   ├── raw/.gitkeep               # consented images only; never committed
│   └── processed/.gitkeep         # split CSVs and resized copies; never committed
├── src/
│   ├── prepare_dataset.py         # validate images, build labels.csv, make splits
│   ├── train_image_classifier.py  # MobileNetV2 transfer learning, saves weights + metadata
│   ├── evaluate_image_classifier.py  # held-out test metrics, confusion matrix
│   ├── predict_image.py           # canonical inference logic (also used by the backend)
│   └── matching_baseline.py       # (M3) rule-based matching, shared with backend tests
├── models/
│   └── README.md                  # naming, versioning, what goes in git (nothing large)
└── reports/                       # metrics JSON, confusion matrix PNG, summary markdown
```

## Setup

ML dependencies are deliberately **separate** from the backend (the backend
runs fine without PyTorch — see the honest fallback below).

```bash
python -m venv ml/.venv          # or reuse the backend venv if you prefer
source ml/.venv/Scripts/activate # Git Bash on Windows
pip install -r ml/requirements.txt
```

`ml/requirements.txt` pins CPU builds of PyTorch; see the file for the exact
install command.

## Workflow

```bash
# 1. Collect CONSENTED images into ml/data/raw/<source-group>/<label>/*.jpg
#    (see ml/data/README.md for consent + labelling rules)

# 2. Validate, resize, split (stratified by label, grouped by source, seed 42)
python ml/src/prepare_dataset.py

# 3. Train (freezes the backbone; optional fine-tuning of later blocks)
python ml/src/train_image_classifier.py --epochs 15

# 4. Evaluate ONCE on the held-out test split
python ml/src/evaluate_image_classifier.py

# 5. Point the backend at the trained weights
#    CLASSIFIER_WEIGHTS_PATH=../ml/models/image_classifier_v1.pt  (already the default)

# CLI inference (also the canonical logic used by the backend):
python ml/src/predict_image.py path/to/image.jpg
```

## Honesty rules (enforced by convention — do not break them)

- Never claim an accuracy figure that is not present in `ml/reports/`.
- Never present synthetic or placeholder images as real training data.
- The test split is touched exactly once, by `evaluate_image_classifier.py`.
- Model metadata (`model_metadata.json`) records seed, date, label list, split
  sizes, and settings next to the weights; reports reference the model version.
- If any class has fewer than 20 test images, the evaluation report says so and
  the UI shows a limitation note.
