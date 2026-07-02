# Feature Extraction

**Module:** `backend/features.py` · **Deps:** pandas (reuses `breath_segment.py`)

Aggregates the per-breath table from [breath segmentation](breath-segment.md)
into **one summary row per capture** — the standard monitored ventilator
parameters, as mean + std across that capture's breaths.

## Features
Each maps to a column in the breath table; the module emits `<name>_mean` and
`<name>_std` (population std, ddof=0, so a single breath gives std 0).

| Feature | Meaning | Breath-table source |
|---------|---------|---------------------|
| `ti`   | inspiratory time (s)        | `ti_sec` |
| `te`   | expiratory time (s)         | `te_sec` |
| `rr`   | respiratory rate (bpm)      | `rr_bpm` |
| `ie`   | I:E ratio (Ti/Te)           | `ie_ratio` |
| `vt`   | tidal volume (mL)           | `tidal_volume_ml` |
| `pip`  | peak inspiratory pressure (cmH₂O) | `peak_pressure` |
| `peep` | end-expiratory pressure (cmH₂O)   | `peep` |

## Public API
| Function | Purpose |
|----------|---------|
| `extract_features(breaths, complete_only=True)` | Aggregate a breath table → per-capture feature table |
| `features_from_dataset(data_dir, complete_only=True, **seg_kwargs)` | Segment a directory then extract (passes `min_breath_sec`/`baseline`/`hysteresis` to `segment_dataset`) |
| `save_features(df, path)` | Persist (Parquet/CSV by extension; delegates to `save_breaths`) |

## Output schema (one row per capture)
`patient_id`, `raw_data`, `n_breaths`, then `<feature>_mean` / `<feature>_std`
for each of the 7 features above (17 columns total).

## Details worth knowing
- **Complete breaths only by default.** The trailing partial breath of a capture
  (`is_complete=False`) has unreliable RR/I:E, so it's dropped before aggregating.
  Pass `complete_only=False` (CLI `--all-breaths`) to keep it. A capture whose
  only breath is partial therefore produces no feature row.
- **Grouping** is by `(patient_id, raw_data)` — one capture CSV = one row.
- `ie_mean` is Ti/Te; on this inspiration-dominated sample it is often ≫ 1
  (inverted I:E), reflecting the raw signal — see the caveat in `breath-segment.md`.
- Segmentation settings flow straight through, so pair `baseline="auto"`/`"patient"`
  with a `hysteresis` band just as in breath segmentation.

## Usage
```bash
python3 backend/features.py [data_dir] [--out FILE] [--min-breath-sec N] \
    [--baseline zero|auto|patient|<num>] [--hysteresis L/min] [--all-breaths]
# default: reads ../smart_icu_data, writes backend/output/features.csv
# recommended: --baseline auto --hysteresis 3   (matches offset/noisy captures)
```
```python
from features import features_from_dataset, save_features
feats = features_from_dataset("smart_icu_data", baseline="auto", hysteresis=3)
save_features(feats, "backend/output/features.csv")
```
