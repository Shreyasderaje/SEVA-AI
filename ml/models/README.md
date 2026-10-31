# Model artifacts

Trained weights live here. **Nothing large is committed to git** — `.gitignore`
excludes `*.pt` / `*.pth`.

## Naming and versioning

- Weights file: `image_classifier_v<N>.pt` (e.g. `image_classifier_v1.pt`).
- Next to each weights file, `train_image_classifier.py` writes
  `image_classifier_v<N>_metadata.json` containing: model version, training
  date, random seed (42), the label list, dataset sizes per split, training
  settings (epochs, learning rates, frozen/unfrozen blocks), and — once
  evaluated — the measured test metrics copied from `ml/reports/`.
- The backend resolves `CLASSIFIER_WEIGHTS_PATH` against the backend directory
  (default `../ml/models/image_classifier_v1.pt`) and reports the resolved path
  plus whether the file exists in its startup diagnostics.
- If the weights file (or PyTorch) is absent, the backend honestly reports
  `model_not_configured` and manual category selection remains fully
  functional.

## What may be committed

- ✅ `model_metadata.json` files (small, text)
- ✅ `ml/reports/` metrics JSON, summary markdown, confusion-matrix PNG
- ❌ weights files (`*.pt`, `*.pth`) — retrain locally; never commit binaries
- ❌ anything under `ml/data/`
