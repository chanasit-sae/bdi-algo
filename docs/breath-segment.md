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
- **Inspiration onset** (breath boundary): flow rises above `baseline + hysteresis`
  **and** the local rise rate has reached `slope_threshold`. Both conditions must
  hold at the same sample, so the onset lands where flow is genuinely accelerating
  upward, not merely drifting across the band.
- **Expiration onset** (end of inspiration): flow drops below `baseline − hysteresis`.
- A breath spans consecutive inspiration onsets. The trailing segment after the
  last onset runs to end-of-capture and is flagged `is_complete=False`.
- A crossing index `i` is the first sample of the new phase.

With `baseline="zero"`, `hysteresis=0` and `slope_threshold=0` (the defaults) this
reduces to pure zero-crossing.

### Slope gate
`slope_threshold` (L/min **per second**) requires the flow to be rising fast enough
at the onset, as a second condition alongside the band. The slope is a centered
derivative, `np.gradient(flow) * SAMPLE_RATE_HZ`.

- **Why 30 L/min/s (recommended).** Flow-trigger literature (ventilator patents)
  fires inspiration on a flow change of ~6–10 L/min, which over a ~0.2–0.3 s trigger
  window is ~20–50 L/min/s. On this sample, true inspiratory onsets have a rise rate
  of ~105 L/min/s (median, p25 ~69) at the crossing, while flat/noise captures sit
  around ~9 L/min/s. A threshold of **30** keeps ~88% of real onsets and clears the
  noise floor by a wide margin. It is a no-op on the clean zero-baseline breaths here
  (91 breaths at both 0 and 30), i.e. non-destructive.
- **What it fixes.** The gate rejects slow baseline drift that clears the band without
  a real breath. This matters most with `auto`/`patient` baselines, whose crossings
  sit near the expiratory trough: `auto` alone over-segments to **748 breaths / 68
  captures**, and `auto` + `slope_threshold=30` collapses that to **120 / 39** — the
  same noise-rejection job as a hysteresis band, but on rise-rate instead of amplitude.
- A spike-only slope (some flat captures spike to ~800 L/min/s) does **not** create a
  breath, because it must also coincide with an upward band crossing — that is the
  reason both conditions are required.

### `baseline="slope"` — adaptive slope-change onset detection
A **level-agnostic** onset detector (`_detect_slope_onsets`) that needs no baseline
crossing at all, so it segments captures whose flow is offset high and never crosses
zero (the main failure mode of level crossing). At each sample it compares the current
slope to the **trend of the previous `slope_window_sec` of slopes** (their mean) and
flags a breath start when the jump exceeds `slope_delta`:

- **`slope_window_sec`** (default **0.32 s** ≈ 8 samples) — trailing trend window. On
  this data, true onsets jump ~278 L/min/s (p25 ~198) above this trend, while flat
  captures sit at ~8, so the window cleanly separates real efforts from noise.
- **`slope_delta`** (default **100 L/min/s**) — the jump above trend that flags an onset.
- **`slope_refractory_sec`** (default **1.0 s**) — minimum spacing between onsets.
  *Required*: a slope-only detector fires **twice** per breath — once at the inspiratory
  onset and once at the expiratory recovery back to baseline (~0.68 s later on this
  data), since both are upward slope jumps. A 1.0 s refractory suppresses the second
  flag (and caps detectable rate at 60 bpm). At the default it reproduces the
  zero-crossing breath count on cycling captures (13 = 13) and recovers 6 offset-high
  captures that zero-crossing misses.
- **`slope_exp_guard`** (default **100 L/min/s**, 0 = off) — drops candidates that sit
  on the **expiratory limb**. A real inspiratory onset is preceded by the near-flat
  end-expiratory pause (min slope over the trailing window ≥ ~−26 on this data); an
  expiratory / noise onset is preceded by a steep flow *decrease* (min slope ≤ ~−300).
  If the pre-onset min slope drops below `−slope_exp_guard`, the point is a fall
  into / recovery out of expiration, not a breath start, so it is skipped. It is a
  *magnitude* so plateau noise dipping slightly negative is not mistaken for
  expiration. On this sample the guard removes **92** such false onsets (**207 → 115
  breaths**, 39 captures unchanged) — almost all noise wobble on the flat `bd4963…`
  captures — while leaving the real cycling breaths intact.
- **`slope_peak_min`** (default **60 L/min**, 0 = off) — drops candidates whose rise
  never reaches a real inspiratory **peak flow**. From the onset it walks forward while
  flow keeps rising and takes the value at the **first descending point** (the peak of
  that inspiratory limb, `_first_peak_flow`, capped at `slope_refractory_sec`); if that
  peak is below `slope_peak_min` the candidate is a low-amplitude wobble, not a breath,
  and is skipped. A normal adult inspiratory peak is ~60–90 L/min. On this sample the
  real cycling onsets (`2a7b9f…`) peak ~91–93 L/min, while the onsets that survive the
  exp-guard have a peak median ~78 (p25 ~65, p10 ~59); a **60** cut keeps ~87% (100/115)
  of them and clears the residual low-amplitude noise. Pass **`"mean"`** instead of a
  number to use the **whole-capture average flow** as the threshold — an adaptive,
  capture-relative floor for signals whose absolute scale is offset (a real breath's
  peak sits well above the capture mean, while noise wobble does not).

In this mode expiration onsets (`insp_end`) still come from the level crossing of the
per-capture `auto` baseline, so `ti`/`te` and the volume/pressure metrics stay defined.
The level-mode knobs (`hysteresis`, `slope_threshold`) do not apply.

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
| `segment_capture(wf, patient_id, raw_data, min_breath_sec=0.0, baseline="zero", hysteresis=0.0, slope_threshold=0.0, slope_window_sec=0.32, slope_delta=100.0, slope_refractory_sec=1.0, slope_exp_guard=100.0, slope_peak_min=60.0)` | Segment one `load_waveform` DataFrame → breath table |
| `segment_dataset(data_dir, min_breath_sec=0.0, baseline="zero", hysteresis=0.0, slope_threshold=0.0, slope_window_sec=0.32, slope_delta=100.0, slope_refractory_sec=1.0, slope_exp_guard=100.0, slope_peak_min=60.0)` | Segment every referenced capture → one combined table |
| `estimate_baseline(flow, q=5.0)` | Low-percentile (end-expiratory) baseline estimate |
| `save_breaths(df, path)` | Persist the breath table (Parquet or CSV by extension) |

`min_breath_sec` drops breaths shorter than the threshold. `baseline` / `hysteresis`
/ `slope_threshold` control crossing detection (see below); defaults reproduce pure
zero-crossing.

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
    [--baseline zero|auto|<num>] [--hysteresis L/min] [--slope-threshold L/min-per-s]
# default: reads ../smart_icu_data, writes backend/output/breaths.csv (pure zero-crossing)
# recommended for noisy flow: --hysteresis 5 --slope-threshold 30
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
