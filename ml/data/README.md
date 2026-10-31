# Image data — sources, licences, curation rules, schema

This directory holds the SEVA-AI dataset. **Nothing in `raw/` or `processed/`
is ever committed to git** (root `.gitignore`).

## Stage 1: public licensed datasets

### Directory layout

```
ml/data/raw/
├── datasets.csv                  # source registry: licence, source_url, label mapping
├── _downloads/                   # original archives (gitignored)
├── aig_mendeley/<garment>/*.jpg  # AIG — mapped to "clothing" via registry
├── rice_koklu/<variety>/*.jpg    # Koklu rice — mapped to "grains_rice"
├── utensils_13k/<utensil>/*.jpg  # Kitchen Utensils 13K — mapped to "utensils"
├── openfoodfacts/packaged_food/  # Open Food Facts product fronts
│   └── _attribution.csv
└── wikimedia_other/other/        # books/toys/games, per-file licence verified
    └── _attribution.csv
```

### Sources and licences (verified against the actual hosts)

| source_group | Source | Licence (as stated by the host) | Fetcher |
|---|---|---|---|
| `aig_mendeley` | Apparel Images Gallery (AIG), Mendeley Data v1 — 130,014 images, 13 garment classes, 224×224 | **CC BY 4.0** (dataset page) | direct: `https://data.mendeley.com/public-files/datasets/pxkbgkydrp/files/4a7549a3-8034-455f-b580-2407d26bcb18/file_downloaded` (879 MB RAR; extract with `/c/Windows/System32/tar.exe -xf`) |
| `rice_koklu` | Rice Image Dataset — Koklu, Cinar & Taspinar (2021), "Classification of rice varieties with deep learning methods", Computers and Electronics in Agriculture; 75,000 grain images, 5 varieties (Arborio, Basmati, Ipsala, Jasmine, Karacadag) | **CC0: Public Domain** — as stated on the authors' official distribution (`kaggle.com/datasets/muratkokludataset/rice-image-dataset`, owner `muratokludataset`); the Hugging Face mirror used for download carries no licence tag of its own, so the authors' upstream statement governs. Note: the image dataset licence is independent of any repository CODE licence (e.g. analysis repos' Apache/MIT files do not cover the images). Cite the paper regardless of CC0 | mirror: `https://huggingface.co/datasets/miladfa7/Rice-Image-Dataset/resolve/main/Rice%20Image%20Dataset.zip` |
| `utensils_13k` | Kitchen Utensils Dataset 13K — 10 utensil classes | **MIT** (dataset tag) | `ml/src/fetch_utensils.py` |
| `openfoodfacts` | Open Food Facts product front photos | **CC-BY-SA / CC0 per upload**, contributor credited per photo | `ml/src/fetch_openfoodfacts.py` |

### Open Food Facts count reconciliation (audit note)

The final dataset contains **897** OFF images, built from two collection runs:
run 1 saved 497 images (the public API then rate-limited), and the top-up run
saved 400 new images. The top-up's `_attribution.csv` initially contained only
its own 697 rows (297 re-encountered + 400 new), leaving 200 run-1 files
without sidecar rows. Repaired during the Stage-1 audit: the sidecar was
regenerated deterministically from the filenames — an OFF filename **is** the
product code, so every image's per-product source URL
(`https://world.openfoodfacts.org/product/<code>`) is reconstructible without
any re-download. Verified after repair: 897/897 files have attribution rows
with per-product URLs, and every `labels.csv` OFF row traces to an existing
raw file and sidecar row.
| `wikimedia_other` | Wikimedia Commons — Toys, Dolls, Plush toys, Books, Board games, Children's games, School supplies | **per file**: only CC0 / Public Domain / CC BY / CC BY-SA kept; artist + licence + source URL captured per image | `ml/src/fetch_wikimedia_other.py` |

**Rejections documented:** the candidate "Freiburg Groceries Dataset" could not
be used — its host server (`aisdatasets.informatik.uni-freiburg.de`) was
unreachable during collection and the repository states no image licence of
its own. "BookCover30" was rejected because its images are copyrighted by
Amazon with only a "fair use for academic purposes" note — not a clear
redistribution licence. HoloSelecta (Mendeley) was set aside: its archive
contains only 295 vending-machine images plus study data, far fewer than its
title suggests. Substitutions above are licence-verified.

### Label mapping

Raw source folders map into the five fixed SEVA classes through
`datasets.csv`'s `label_mapping` column (`*=clothing` maps every subfolder of
the group). No source folder is ever relabelled silently — the mapping is a
registered, reviewable rule. The five classes stay fixed:
`clothing`, `grains_rice`, `packaged_food`, `utensils`, `other`.

## Curation rules (applied by `prepare_dataset.py`)

- **Exclusions**: unreadable files, images smaller than 32 px on a side,
  anything without a documented licence.
- **Exact duplicates**: dropped by SHA-256 of the file bytes.
- **Near-duplicates**: 64-bit average hash; images within Hamming distance ≤ 4
  are unioned into duplicate groups.
- **Leakage control**: images from the same duplicate group always land in the
  same split. A group holding more than 25 % of its class is dissolved into
  singletons first (otherwise one augmented family — e.g. the Koklu rice
  augmentations — would put a whole class into one split); this is logged as a
  limitation in the run output.
- **Balancing**: deterministic per-(class, source) pre-sample cap (2500) before
  analysis, then per-split per-class caps (default train 1100 / val 220 /
  test 220) by dropping whole duplicate groups first, then single images.
- **Splits**: stratified by class, grouped by duplicate group, seed 42,
  created once and never regenerated silently (`--force` required).

## labels.csv schema (produced by `prepare_dataset.py`)

| Column | Meaning |
|---|---|
| `image_path` | resized copy under `processed/`, relative to `processed/` |
| `label` | one of the five fixed classes |
| `source` | human-readable dataset name |
| `source_url` | where the dataset (or the individual image) came from |
| `licence` | licence of the image as documented by the source host |
| `dataset_type` | `public_licensed` (Stage 1) or `consented_original` (Stage 2, ashram visits) |
| `consent_ref` | required for `consented_original`; empty for licensed public data |
| `annotator` | original contributor/annotator record |
| `split` | `train`, `val`, or `test` |

Enforcement: `public_licensed` rows must carry `source` + `licence`;
`consented_original` rows must carry a `consent_ref` — `prepare_dataset.py`
refuses to build the dataset otherwise, so future ashram photography cannot
enter the pipeline undocumented.

## Stage 2 (future): consented original photographs

Add a new source group (e.g. `ashram_visit_2026_q1`) to `datasets.csv` with
`dataset_type=consented_original` and a real `consent_ref`, drop the photos
under `raw/<group>/<class>/`, then re-run `prepare_dataset.py --force`
(new dataset version), retrain a new model version, evaluate independently,
and compare against the Stage-1 baseline in `ml/reports/`. The previous model
version stays registered (`model_versions`) for rollback.
