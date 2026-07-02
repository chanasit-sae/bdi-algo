# Breath Segmentation

**Module:** `backend/breath_segment.py` · **Deps:** numpy + pandas (reuses `parser.py`)

Splits a ventilator waveform into individual breaths using **zero-crossing of the
Flow signal**, and emits one row of metrics per breath.

## Method
Convention: Flow > baseline = inspiration, Flow < baseline = expiration.

```
insp_start ──inspiration──> insp_end(=exp_start) ──expiration──> exp_end(next insp_start)
  Flow ↑                        Flow ↓                              Flow ↑
```
Detection is a hysteresis state machine (`_detect_crossings`):
- **Inspiration onset** (breath boundary): flow rises above `baseline + hysteresis`.
- **Expiration onset** (end of inspiration): flow drops below `baseline − hysteresis`.
- A breath spans consecutive inspiration onsets. The trailing segment after the
  last onset runs to end-of-capture and is flagged `is_complete=False`.
- A crossing index `i` is the first sample of the new phase.

With `baseline="zero"` and `hysteresis=0` (the defaults) this reduces to pure
zero-crossing.

### Baseline & hysteresis
Real flow may not return exactly to zero at the inspiration→expiration transition
(sensor bias, leaks) and is noisy near the crossing. Two levers address this:

- **`hysteresis`** — a dead-band (L/min) around the baseline; flow must clear the
  band to switch phase. This is the effective knob: it rejects noise-driven false
  crossings. On this sample, `hysteresis=5` around zero keeps the correct breath
  count on cycling captures **and** drops flat/noise-only captures from 37 spurious
  breaths to 0 (91 → 76 breaths overall, 33 → 28 captures).
- **`baseline`** — `"zero"` (default), `"auto"` (per-capture low percentile),
  `"patient"` (per-patient low percentile), or a numeric offset.
  - `"auto"` estimates a baseline from each capture's own flow, as the **5th
    percentile** of flow (`estimate_baseline`). The true baseline is the
    end-expiratory point — the *low* end of the range — so a low percentile
    tracks the expiratory trough even when the whole signal is offset positive
    and never crosses zero (e.g. capture `bd4963…_1_090205`: normal breath shape,
    trough ~7–8 L/min, plateau ~28–33, so pure zero-crossing finds 0 breaths but
    `auto`+hysteresis finds them). A mean/median/histogram-mode would instead
    land on the inspiratory plateau (~90% of samples) and mis-segment.
  - `"patient"` pools **all of a patient's captures** and estimates one shared
    baseline (resolved in `segment_dataset`, which then passes the number to each
    capture). More stable/comparable across a patient's breaths, but assumes the
    offset is roughly constant across the admission. If `"patient"` is passed
    straight to `segment_capture` (single capture, no patient context) it degrades
    to `"auto"`.
  - ⚠️ **Pair `auto`/`patient` with a hysteresis band.** The offset alone sits
    just above the expiratory trough, so on noisy/flat captures the signal
    oscillates across it and over-segments (766 spurious breaths at hyst=0). A
    band wider than the flat-capture noise amplitude (~1 L/min) zeroes those back
    out: `auto`+`hysteresis=3` → 99 breaths / 39 captures (vs zero-mode 91 / 33),
    recovering positive-DC-offset captures without firing on flat ones.

## Public API
| Function | Purpose |
|----------|---------|
| `segment_capture(wf, patient_id, raw_data, min_breath_sec=0.0, baseline="zero", hysteresis=0.0)` | Segment one `load_waveform` DataFrame → breath table |
| `segment_dataset(data_dir, min_breath_sec=0.0, baseline="zero", hysteresis=0.0)` | Segment every referenced capture → one combined table |
| `estimate_baseline(flow, q=5.0)` | Low-percentile (end-expiratory) baseline estimate |
| `save_breaths(df, path)` | Persist the breath table (Parquet or CSV by extension) |

`min_breath_sec` drops breaths shorter than the threshold. `baseline` / `hysteresis`
control crossing detection (see below); defaults reproduce pure zero-crossing.

## Persistence
`save_breaths(df, path)` writes the table, choosing format by extension:
- `.parquet` if a parquet engine (pyarrow/fastparquet) is installed;
- otherwise **CSV** (also the fallback if `.parquet` is requested but no engine
  is available — currently the case in this env, so output is CSV).

The CLI saves automatically. Default output: **`backend/output/breaths.csv`**
(the dir is created if missing). Override with `--out`.

## Output schema (one row per breath)
| column | meaning |
|--------|---------|
| `patient_id`, `raw_data` | patient / source capture CSV |
| `breath_idx` | index of the rising crossing within the capture |
| `insp_start_idx`, `insp_end_idx`, `exp_end_idx` | sample indices |
| `t_insp_start`, `t_insp_end`, `t_exp_end` | seconds (idx / 25 Hz) |
| `ti_sec`, `te_sec` | inspiratory / expiratory duration |
| `ie_ratio` | Ti:Te (None if Te = 0) |
| `tidal_volume_ml` | max − min Volume within the breath |
| `peak_flow`, `peak_pressure`, `mean_pressure`, `peep` | per-breath waveform stats |
| `rr_bpm` | instantaneous rate = 60 / breath period |
| `is_complete` | False for the trailing partial breath of a capture |

## Usage
```bash
python3 backend/breath_segment.py [data_dir] [--out FILE] [--min-breath-sec N] \
    [--baseline zero|auto|<num>] [--hysteresis L/min]
# default: reads ../smart_icu_data, writes backend/output/breaths.csv (pure zero-crossing)
# recommended for noisy flow: --hysteresis 5
```
```python
from breath_segment import segment_dataset, segment_capture, save_breaths
breaths = segment_dataset("smart_icu_data")     # combined breath table
save_breaths(breaths, "backend/output/breaths.csv")
```

## Important details & limitations
- **Flat-flow captures yield zero breaths.** Some captures (patients `bd4963…`,
  `5ea4…`) have Flow pinned high with no negative excursion (e.g. range 72.9–73.6),
  so there are no zero-crossings and no breaths are detected. On the current
  sample only 33 of 68 captures segment. This is inherent to the zero-crossing
  method, not a bug — those signals need a different approach (baseline removal,
  volume-derivative, or resp-rate priors) to segment.
- **Noise near the crossing** produces spurious short breaths in pure zero-crossing
  mode. Use `hysteresis` (dead-band) and/or `min_breath_sec` to suppress them.
- **I:E can look inverted** on this sample (e.g. Ti ≫ Te) because some captures are
  ~90% positive-flow — that reflects the raw signal, not a labeling error.
- The trailing partial breath has no next onset, so `exp_end` = last sample and
  `rr_bpm`/`ie_ratio` are unreliable; filter on `is_complete` for clean metrics.
