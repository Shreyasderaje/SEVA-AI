# Consented image data — rules, labelling guide, schema

This directory holds the SEVA-AI image dataset. **Nothing in `raw/` or
`processed/` is ever committed to git** (see the root `.gitignore`).

## Consent rules (non-negotiable)

- Use only images the photographer or owner has **consented to share** for
  training this project, or images from licensed public datasets with a
  documented license.
- Record the source of every image (dataset name + license, or the consenting
  person's reference) — this becomes the `source` and `consent_ref` columns.
- **Do not scrape** personal images from the web or social media.
- **Do not include images of people or children** — the classifier sees
  donated items only.
- Never present synthetic or placeholder images as real training data. If you
  generate illustrative demo images for UI development, keep them OUT of this
  pipeline and label them as demo in the UI.

## Directory layout

```
ml/data/raw/
├── consent.csv                  # maps source group → consent reference (required)
└── <source-group>/              # one folder per photo session / dataset batch
    ├── clothing/*.jpg           # folder name = the label
    ├── grains_rice/*.jpg
    ├── packaged_food/*.jpg
    ├── utensils/*.jpg
    └── other/*.jpg
```

`consent.csv` schema (header row required):

```
source_group,consent_ref,notes
my-phone-shoot-2026-01,CONSENT-001,"Photos taken by me, shared with permission"
public-dataset-x,LICENSE-CC-BY-4.0,"Subset used per dataset license"
```

Every image under a `<source-group>` folder inherits that group's consent
reference. `prepare_dataset.py` refuses to run if a group is missing from
`consent.csv`.

## Labelling guide

- Exactly **one label per image**, from the five fixed classes only:
  `clothing`, `grains_rice`, `packaged_food`, `utensils`, `other`.
- Label the **main item** in the photo. The folder the image sits in IS the
  label — `prepare_dataset.py` validates folder names against the five classes
  and fails loudly on anything else.
- If the main item is unclear or mixes several classes, use `other`.
- Each source group acts as the annotation "session"; images from the same
  session are always placed in the same split (leakage protection).

## labels.csv schema (produced by `prepare_dataset.py`)

| Column | Meaning |
|---|---|
| `image_path` | path of the resized copy under `processed/` (relative to `processed/`) |
| `label` | one of the five fixed classes |
| `source` | source group (photo session / dataset batch) |
| `consent_ref` | consent or license reference from `consent.csv` |
| `split` | `train`, `val`, or `test` — stratified by label, grouped by source, seed 42 |
| `annotator` | who assigned the label (from `consent.csv` notes or `unspecified`) |

Splits are created **once** with a fixed random seed (42) and are **never
regenerated silently** — `prepare_dataset.py` refuses to overwrite an existing
`labels.csv` unless `--force` is given, and prints the resulting split sizes
every time it runs.
