# Asynchrony Detection & Notifications

**Modules:** `backend/asynchrony.py` (double-triggering), `backend/ineffective_effort.py`
(ineffective effort), `backend/auto_peep.py` (auto-PEEP — full spec in
[auto-peep.md](../auto-peep.md)), `backend/flow_starvation.py` (flow starvation),
`backend/mechanical_power.py` (mechanical power — per-patient, not a breath-level detector) ·
**Deps:** numpy + pandas (reuse `breath_segment.py` output)
**API:** `backend/server/routers/asynchrony.py` — `GET /api/asynchrony` (one capture,
every breath-level detector), `GET /api/auto-peep` and `GET /api/flow-starvation` (one
capture, single detector each), `GET /api/mechanical-power` and `GET /api/asynchrony-index`
(both per-patient), and `GET /api/notifications` (scans the dataset, paginated, includes
mechanical power and asynchrony-index alerts)
**Pages:**
- **Notifications** (`frontend/src/pages/NotificationsPage.jsx`) — a plain, most-recent-first
  list of every flagged event across the whole dataset, 10 per page, using fixed default
  detection settings, with a type filter (checkboxes). No tunable formula controls here on
  purpose — click a notification to inspect it in the Viewer.
- **Viewer** (`frontend/src/pages/ViewerPage.jsx`) — independently detects and highlights
  **every** flagged breath-level event (all four detectors) for whatever capture is
  currently loaded, using fixed default segmentation/formula params (no tuning controls
  shown to the user — see git history if you need to bring them back). Clicking a
  notification deep-links here with the exact segmentation *and*
  every formula reproduced, so the same event is guaranteed to be found again and marked
  active (brighter band). Mechanical power has no per-breath band to highlight (it's a
  patient-level rolling average, see §5) — clicking its notification lands on the
  patient's most recent capture instead.

Every event, regardless of which detector produced it, carries a `type` plus two
generalized fields computed by the router: **`t0`/`t1`** (the span to highlight on a
chart) and **`detail`** (a short human-readable summary). The frontend (highlighting,
notification cards, the Viewer's asynchrony list) works entirely off these three fields
and never branches on type-specific columns — adding a detector means adding it to
`_scan_capture()` in the router; nothing else changes.

---

## 1. Double triggering

The patient's neural inspiratory effort continues past the ventilator's inspiratory
termination, so a second breath is triggered almost immediately after the first — an
abnormally short expiratory pause between two consecutive breaths.

### Formula
```
Te(i) < ratio × Ti_ref
```
per **Thille AW, Rodriguez P, Cabello B, Lellouche F, Brochard L. "Patient-ventilator
asynchrony during assisted mechanical ventilation." *Intensive Care Med.* 2006;32(10):1515–1522**
— the standard clinical definition ("two consecutive cycles separated by a very short
expiratory time, less than one half of the mean inspiratory time").

| term | meaning |
|------|---------|
| `Te(i)` | `te_sec` of breath *i* — the expiratory gap before breath *i+1* begins. `te_sec = t_exp_end − t_insp_end`, and `t_exp_end` **is** breath *i+1*'s `t_insp_start` (see [breath-segment.md](breath-segment.md)), so this is exactly the inter-breath gap. |
| `ratio` | cutoff, default **0.5**. |
| `Ti_ref` | the inspiratory-time reference the short `Te` is judged against — `ti_ref="pair"` (default, mean of the pair's own Ti), `"capture"` (mean over the capture's complete breaths), or `"self"` (Ti(i) alone). |

**Optional secondary check — volume stacking.** Double-triggered breaths typically
deliver close to double the tidal volume of a normal breath pair — the actual clinical
harm (volutrauma risk; **Pohlman MC et al., Crit Care Med. 2008;36(11):3019–23**).
`require_stacking=true` additionally requires `Vt(i)+Vt(i+1) > stack_ratio × 2 × median(Vt)`
(default `stack_ratio=1.5`). Off by default so the detector matches the plain Thille
timing definition; `vt_ratio` is always reported so it can be reviewed either way.

**Edge case.** A capture's last breath has no successor, so its `te_sec` is an artifact
of where the recording was cut off, not a real gap (`is_complete=False`). The pair loop
never uses it as the *first* breath of a pair, so it can't produce a false positive.

---

## 2. Ineffective effort

The patient's inspiratory muscles contract, but the ventilator's trigger threshold is
never cleared, so **no breath is delivered**. Unlike double-triggering, this can never
appear as a row in the breath table — it has to be found as a sub-threshold deflection
inside an already-recorded **expiratory** window.

⚠️ **Unlike double-triggering, there is no single agreed closed-form formula for this.**
The gold-standard reference signal is esophageal pressure, which this dataset doesn't
have; with only Flow/Pressure/Volume, detection has to work off a surrogate signature.
The approach below — **require a concordant deflection in both Flow and Pressure** — is a
deliberately conservative heuristic (fewer false positives, at the risk of missing effort
that only shows clearly on one signal), in the spirit of how automated-asynchrony-detection
literature (e.g. Younes et al.; Chen et al.'s review of automated methods) frames
flow/pressure-only detection when esophageal pressure is unavailable. **Treat the
thresholds below as a tunable starting point, not a validated clinical cutoff.**

### Signature, per breath's own expiratory window (`insp_end_idx` → `exp_end_idx`)

- **Flow**: expiratory flow normally decays smoothly toward baseline. An effort creates a
  transient **bump** — a local rise before the decay resumes — that never clears the real
  trigger band (if it did, it would already be a separate breath). Flagged if the bump's
  **prominence** (rise from the *nearest preceding* local minimum, looking back at most
  `bump_lookback_sec`) clears `flow_prominence` (default **25 L/min**) but stays below
  `flow_prominence_max` (default **60 L/min**, matching the app's own slope-mode `PeakMin`
  default): a bump that large almost certainly means segmentation missed an actual breath
  (e.g. refractory suppression), not a genuinely failed effort, so it's excluded rather
  than flagged.
- **Pressure**: concurrently, the patient tugging against the circuit produces a small
  negative **dip** in airway pressure. Flagged if its prominence (fall from the nearest
  preceding local maximum, same bounded lookback) clears `pressure_prominence` (default
  **1.5 cmH₂O**) and its trough sits within `concurrent_tol_sec` (default **0.3 s**) of the
  flow bump's peak.

Only pairs where **both** signals independently clear their threshold **and** occur close
together in time are flagged. Both signals are lightly smoothed first (3-sample moving
average) to suppress single-sample noise before looking for local extrema.

#### Why `bump_lookback_sec` exists — a bug that made the first version fire on noise
Prominence must be measured against a *recent* reference point, not "the lowest/highest
value anywhere earlier in this multi-second expiratory window." The first version of this
detector measured prominence as `value_at_peak - min(everything from the window's start
up to the peak)` — so a late, tiny wiggle got credited with the *entire earlier decay
curve* as its "rise," wildly inflating prominence for things that were just normal decay,
not effort. Measured against this dataset's real per-breath expiratory windows:

| | flow candidates clearing old default (8 L/min, unbounded) | pressure candidates clearing old default (1.0 cmH₂O, unbounded) |
|---|---|---|
| **before fix** | 98.1% (411/419) | 42.9% (247/576) |

i.e. the detector was firing on essentially any expiratory window, which is exactly "it
catches noise." Bounding the lookback to `bump_lookback_sec` (default **0.4 s** — a
plausible timescale for an effort's own rise/fall) and recalibrating thresholds against
the *corrected* distribution (roughly its 90th percentile, so only the genuinely unusual
tail is flagged) fixed it:

| | flow prominence (bounded, 0.4s lookback) | pressure prominence (bounded, 0.4s lookback) |
|---|---|---|
| 50th pctl | 5.5 L/min | 0.42 cmH₂O |
| 90th pctl | 27.5 L/min | 1.42 cmH₂O |
| 99th pctl | 41.2 L/min | 14.0 cmH₂O |

New defaults (25 L/min, 1.5 cmH₂O) sit just above the 90th percentile of the corrected
distribution.

### On the sample dataset
At the corrected default thresholds, this heuristic flags **16 events across 7 captures**
(via the CLI) — down from 36/24 before the fix, and now comfortably clear of the measured
noise floor. Still **not validated against ground truth**; there's no reference/expert
labeling in this dataset to check against. Treat results as a starting point to review
visually in the Viewer, not a diagnosis.

---

## 3. Auto-PEEP (air trapping)

Full spec, formula derivation, and the worked example this implementation is validated
against: **[auto-peep.md](../auto-peep.md)**. Summary: the lung doesn't fully empty before
the next breath, so end-expiratory flow doesn't return to baseline (air trapping) and
end-expiratory pressure sits above set PEEP (dynamic hyperinflation) — the physiological
opposite of double-triggering's too-*short* Te; here expiration is too *incomplete*.
Requires the flow signature (`flow_residual_frac > flow_frac` and `residual > flow_abs`)
and, by default, the pressure signature too (`peep_delta > peep_min`) — `require_pressure=false`
flags on flow alone. Both capture-level references (`z_ref`, `set_peep`) are estimated
from the capture's own best-emptied breaths, so this finds breaths trapped *relative to*
that capture, not absolute intrinsic PEEP. Only complete breaths are scored. Verified
against `auto-peep.md`'s worked example (`bd4963...0_170204`, breath 0) field-for-field.

On the sample dataset: **1 breath across 40 scanned captures** with the default
flow+pressure mix; loosening to flow-only (`require_pressure=false`) finds **4 across 3**
— the pressure gate is what adds specificity.

---

## 4. Flow starvation

In **volume-controlled ventilation with constant (square-wave) flow**, the machine
delivers a fixed flow rate regardless of patient demand. If the patient's own inspiratory
drive exceeds that fixed flow, they keep pulling against the circuit — and since flow
*can't* respond (it's locked by the ventilator setting), the mismatch shows up on
**pressure** instead: the pressure-time curve, which should rise in a smooth, convex arc
toward peak, gets pulled down mid-rise into a concave dip — a "scoop" or "scalloped" notch
— before continuing up to peak inspiratory pressure. This is the classic bedside sign of
flow starvation.

⚠️ Same caveat as ineffective effort: **no single agreed closed-form formula** — the
literature describes this qualitatively ("scalloped/concave pressure waveform"), not as a
specific threshold algorithm. This is a heuristic calibrated against this dataset's own
inspiratory pressure noise floor, not an arbitrary guess.

Unlike the other three detectors, this looks at the **inspiratory** phase (double-triggering
and ineffective effort both key off expiration; auto-PEEP scores complete breaths only —
this one scores every breath, including the trailing partial one, since
`insp_start_idx`/`insp_end_idx` are always well-defined).

### Signature, per breath's inspiratory window (`insp_start_idx` → `insp_end_idx`)
A **rise-dip-recovery notch** in pressure: a local minimum with a real rise both *before*
it and *after* it, each measured with a **bounded lookback** (at most `lookback_sec` in
either direction — the same fix ineffective-effort needed, so prominence is a local
measure, not "the highest/lowest point anywhere else in the window"). Flagged if **both**
the preceding rise and the following rise clear `dip_prominence` (default **2.0 cmH₂O**,
calibrated to sit just above the ~97th percentile of this dataset's real
`min(rise_before, rise_after)` distribution — 50th/90th/95th/99th percentiles measured as
0.39 / 1.28 / 1.50 / 2.47 cmH₂O).

**Optional secondary gate** `require_constant_flow` (default **off**): this signature
specifically means something in *constant-flow* delivery. If enabled, also requires the
inspiratory flow trace's own range to stay below `flow_range_max` (default **20 L/min**),
filtering out cases where flow itself naturally varies (e.g. pressure-support's
decelerating flow) — same "mix is optional, primary signal stands alone" pattern as
auto-PEEP's `require_pressure`.

On the sample dataset: **2 notches in 1 capture** at the default threshold (magnitudes
3.3–4.6 cmH₂O, comfortably clear of the noise floor); loosening to `dip_prominence=1.0`
finds 19 across 9 captures, confirming the detector responds smoothly rather than being
stuck or exploding.

---

## 5. Mechanical power

Unlike the four detectors above, this isn't a per-breath event — it's a **per-patient
rolling-average exposure metric**. A single unusually energetic breath doesn't mean much
on its own; a *sustained* elevated delivery of energy to the lung is the actual
ventilator-induced lung injury (VILI) risk. Popularized as a unifying VILI-risk framework
by **Gattinoni L, Tonetti T, Cressoni M, et al. "Ventilator-related causes of lung injury:
the mechanical power." *Intensive Care Med.* 2016;42(10):1567–1575**. A large ICU
meta-analysis — **Serpa Neto A, Deliberato RO, Johnson AEW, et al. "Mechanical power of
ventilation is associated with mortality in critically ill patients: an individual patient
data meta-analysis." *Crit Care Med.* 2018;46(2):200–207** — found mortality risk rising
above roughly **17–19 J/min**, the range this module's default threshold (**17.0 J/min**)
sits at.

### Formula — direct pressure-volume loop integration
```
energy_joules(breath) = 0.0980665 × ∫ pressure d(volume_in_liters)     [inspiratory limb only]
mp_j_per_min(breath)  = energy_joules(breath) × rr_bpm
avg_mp_j_per_min(patient) = mean(mp_j_per_min over every breath in the trailing window)
```
`0.0980665` J per (cmH₂O·L) is the standard conversion (1 cmH₂O = 98.0665 Pa; 1 Pa·m³ = 1 J;
1 L = 10⁻³ m³). The integral is taken over each breath's own `insp_start_idx → insp_end_idx`
(the area of that breath's P-V loop) — this works for **any** breath shape or ventilator
mode and needs no detected end-inspiratory plateau, unlike Gattinoni's algebraic
"simplified equation" (`0.098 × RR × VT(L) × (PIP − 0.5×driving_pressure)`), which needs a
plateau that isn't present on every breath. The direct integral isn't an approximation of
the simplified equation — it's the more general form the simplified equation is itself
derived from, for the specific case of constant-flow volume control with a plateau (see
`mechanical_power.py`'s `--compare` CLI flag for a cross-check between the two on breaths
where a plateau is available; they agree closely there, as expected).

**Only complete breaths are used** (`is_complete=True`) — the trailing partial breath's
`rr_bpm` is computed the same as any other breath's (never `None`/`NaN`) but is a
known-unreliable artifact of where the recording happened to cut off, and multiplying real
per-breath energy by that bogus rate produces wildly inflated MP values. (This was a real
bug during development: an uncorrected run flagged two patients at 62.02 and 18.39 J/min;
filtering to complete breaths corrected them to 49.51 — still flagged — and 12.15 — correctly
not flagged.)

### Rolling window
`avg_mp_j_per_min` is the mean over every complete breath from every one of a patient's
captures whose timestamp falls within `window_hours` (default **24h**) of their single most
recent capture. Captures don't carry an absolute calendar date, so `day`/`capture_time` are
combined into a synthetic per-patient timeline (`day×24 + time-of-day`) purely for ordering
and windowing within that one patient — never compared across patients.

### On the sample dataset
Of 3 patients, **1** (`2a7b9f18...`) is flagged: avg **49.51 J/min** over 7 complete breaths
across its most recent 2 captures within the 24h window. The other 2 patients sit well
below threshold (e.g. `bd496321...` at 12.15 J/min).

---

## 6. Asynchrony index alert

The simplest of the six: a per-patient alert on the **asynchrony index** itself (§ above the
API section describes the metric — total flagged-event seconds / total waveform seconds
across a patient's connected captures). Flagged once that ratio reaches `ai_threshold`
(default **10%**). Like mechanical power, this is patient-level, not per-capture, so it has
no `t0`/`t1` span and no breath to select — its notification links to the patient's most
recent capture with nothing pre-selected.

Note the query param is `ai_threshold`, not `threshold` — `mp_params` already owns
`threshold` (mechanical power's), and since both dependencies are combined on the same
`/api/notifications`/`/api/asynchrony` endpoints, FastAPI binds same-named query params from
different `Depends()` to the same key. Verified this was a real collision (`?threshold=5` was
silently setting both MP's and AI's threshold at once) before aliasing AI's to `ai_threshold`.

On the sample dataset: **1** patient (`2a7b9f18...`) flagged at 10.7%, matching the same
patient already flagged for mechanical power -- consistent with it also being the one with
the most ineffective-effort events.

---

## On the sample dataset (double-triggering)
Under the app's recommended segmentation (`baseline="slope"`) and the clinical default
`ratio=0.5`, double-triggering produces **zero** flagged pairs on this sample — the ~68
captures are short and mostly controlled ventilation, so spontaneous-effort
double-triggering may genuinely not appear here. Loosening `baseline="zero"`,
`hysteresis=5`, `ratio=0.9` does produce pairs (e.g. 47 across 23 captures), useful for
exercising the detector, but the looser ratio no longer reflects the clinical definition.

---

## API

### `GET /api/asynchrony` — one capture, every detector
```
GET /api/asynchrony?file=<capture.csv>
    &baseline=zero|auto|slope|<num>&hysteresis=&slope=&sdelta=&swin=&srefr=&sguard=&speak=
    &ratio=0.5&ti_ref=pair|capture|self&require_stacking=false&stack_ratio=1.5
    &flow_prominence=25&flow_prominence_max=60&pressure_prominence=1.5
    &concurrent_tol_sec=0.3&bump_lookback_sec=0.4
    &flow_frac=0.15&flow_abs=2.0&peep_min=1.0&require_pressure=true
    &dip_prominence=2.0&lookback_sec=0.4&require_constant_flow=false&flow_range_max=20.0
```
Segmentation params are identical to `/api/breaths`. Response:
```json
{
  "events": [
    { "type": "double_trigger", "t0": 0.56, "t1": 6.0, "detail": "Te/Ti 0.05",
      "breath_idx_a": 0, "breath_idx_b": 1, "te_gap": 0.28, "ti_ref": 2.44,
      "te_ti_ratio": 0.047, "vt_pair": 936.2, "vt_ratio": 1.0, "stacked": false },
    { "type": "ineffective_effort", "t0": 1.02, "t1": 1.67, "detail": "flow +32 L/min · pressure -3.0 cmH2O",
      "breath_idx_a": 0, "breath_idx_b": 1, "t_flow_peak": 1.32, "t_pressure_trough": 1.52,
      "flow_prominence": 32.4, "pressure_prominence": 2.96, "dt_sec": 0.2 },
    { "type": "auto_peep", "t0": 1.72, "t1": 2.24, "detail": "residual 24% · PEEP +1.8 cmH2O · flow+pressure",
      "breath_idx_a": 0, "flow_residual_frac": 0.235, "peep_delta": 1.76, "eef": 18.95,
      "z_ref": 31.41, "eep": 3.87, "set_peep": 2.11, "residual": 12.46, "peak_mag": 53.02,
      "pressure_flag": true },
    { "type": "flow_starvation", "t0": 5.0, "t1": 5.92, "detail": "pressure scoop -3.3 cmH2O",
      "breath_idx_a": 1, "dip_pressure": 13.74, "prominence_before": 3.33,
      "prominence_after": 4.56, "flow_range": 40.4 }
  ],
  "n_breaths": 6,
  "baseline": 0.0,
  "formula": {
    "double_trigger": { "criterion": "te_gap < ratio * ti_ref", "ratio": 0.5, "ti_ref": "pair", ... },
    "ineffective_effort": { "criterion": "concordant flow-bump + pressure-dip within concurrent_tol_sec",
                             "flow_prominence": 25.0, "flow_prominence_max": 60.0,
                             "pressure_prominence": 1.5, "bump_lookback_sec": 0.4, ... },
    "auto_peep": { "criterion": "flow_residual_frac > flow_frac (+ peep_delta > peep_min)",
                   "flow_frac": 0.15, "flow_abs": 2.0, "peep_min": 1.0, "require_pressure": true },
    "flow_starvation": { "criterion": "rise-dip-rise notch in inspiratory pressure, both sides >= dip_prominence",
                          "dip_prominence": 2.0, "lookback_sec": 0.4,
                          "require_constant_flow": false, "flow_range_max": 20.0 }
  }
}
```

### `GET /api/auto-peep`, `GET /api/flow-starvation` — one capture, single detector
Same shape as `/api/double-triggers` (superseded by `/api/asynchrony` above) but for one
detector each — `/api/auto-peep` mirrors [auto-peep.md](../auto-peep.md)'s own API section
exactly; `/api/flow-starvation` is the equivalent for flow starvation. Both are for callers
that only want one detector without running the other three.

### `GET /api/mechanical-power` — per-patient, not per-capture
```
GET /api/mechanical-power?<segmentation params>&threshold=17.0&window_hours=24.0
    &patient_id=<optional>&include_disconnected=false
```
With `patient_id`: that one patient's status (returned even if below threshold):
```json
{ "patient_id": "2a7b9f18...", "above_threshold": true, "threshold": 17.0, "window_hours": 24.0,
  "status": { "avg_mp_j_per_min": 49.51, "n_breaths": 7, "n_captures_total": 2,
              "latest_day": 14, "latest_time": "11:18:25", "latest_raw_data": "....csv" },
  "formula": { "criterion": "trailing rolling-average mp_j_per_min >= threshold", ... } }
```
Without it: every patient currently at/above threshold, in the same shape
`/api/notifications` uses for `type: "mechanical_power"`. Each patient's raw rolling-average
computation is cached in `ds.mp_cache` keyed by `(patient_id, segmentation, window_hours,
include_disconnected)` — **not** by threshold, so checking the same patient against a
different threshold (or via `/api/notifications`, which uses its own threshold) reuses the
same cached number rather than re-integrating every P-V loop again. Computing it walks that
patient's own captures most-recent-first and stops as soon as one falls more than
`window_hours` before the latest — the same early-exit bounding idea as `NotificationScan`,
just scoped to one patient's window instead of the whole dataset.

### `GET /api/notifications` — incremental scan + paginate
```
GET /api/notifications?<same params as above>
    &patient_id=<optional, restrict to one patient>
    &include_disconnected=false  # disconnected (flat-flow) captures can't produce real
                                  # events, so they're skipped by default for speed
    &page=1&page_size=10
```
Backed by a `NotificationScan` (`backend/server/dataset.py`), one per distinct combination
of every param that affects the result. On first use for a given param set, captures are
sorted most-recent-first **once** (metadata only, no waveform loading — cheap regardless of
dataset size) into a pending queue. From there the scan is **lazy and incremental**: a
request only claims and processes pending captures, one at a time, until it has found at
least `page * page_size` events, then stops — it never scans the whole dataset just to
answer page 1. Each event found is appended straight to the scan's shared `results` list the
moment it's found, so a capture is never re-processed for the same params, whether by a
later page request or the background warmup below. Concurrent callers (e.g. a live request
racing the warmup) claim different captures under a lock but do the actual
load-and-detect work outside it, so they don't block each other for long.

Mechanical power can't share that scan (it's patient-level, not per-capture — a single
capture is never "done" for MP until the whole patient's rolling window has been walked),
so it gets its **own** `NotificationScan` instance (the class doesn't care whether a
"pending item" is a capture or a whole patient) over `ds.patients` instead of captures.
`get_notifications()` advances it with the exact same bound as the capture scan — stop once
`page * page_size` patients have been found at/above threshold, or every patient's been
checked — so a page request never waits on every patient's rolling window either, only on
`_patient_mp_raw()`'s own per-patient cache. The two scans' results are merged into one list
before the final sort + page slice, so mechanical-power notifications appear inline with
everything else, most-recent-first, and `scan_complete` reflects both scans together.

A background task started in `main.py`'s lifespan (`asyncio.to_thread`, so it doesn't
block the app from accepting requests) advances the *default* param combination — the only
one the Notifications page ever asks for, since it has no tunable controls — all the way to
completion for **both** scans. In practice this means the
first real visitor rarely waits on a cold scan at all, and every request after that is an
instant slice of an already-built list.

Response adds a `scanned_captures` count and a `scan_complete` flag (false if the scan
hasn't reached the end of its pending queue yet — `total`/`total_pages` are accurate as far
as scanned so far, but may still grow):
```json
{
  "notifications": [ { "type": "ineffective_effort", "patient_id": "...", "raw_data": "....csv",
                        "day": 14, "time": "11:18:25", "t0": ..., "t1": ..., "detail": "...",
                        "breath_idx_a": 0, "breath_idx_b": 1, ...,
                        "segmentation": { "baseline": "slope", "hysteresis": 0.0, ... } } ],
  "page": 1, "page_size": 10, "total": 18, "total_pages": 2,
  "scanned_captures": 40, "scan_complete": true,
  "formula": { "double_trigger": {...}, "ineffective_effort": {...}, "auto_peep": {...} }
}
```
Verified on the local sample: a `page_size=1` request on a fresh (unwarmed) param
combination scanned just **1** capture before returning; asking the same scan for more
(`page_size=10`) resumed and scanned only **2 more** (not from scratch); forcing full
completion (`page_size=100`) scanned all **68** and set `scan_complete: true`; five
concurrent requests against a fresh scan all returned identical, consistent counts (no
duplicate work, no corruption).

### The Viewer deep link
The Notifications page builds, per card:
```
/?file=<raw_data>&breath=<breath_idx_a>&<...segmentation>
    &ratio=&ti_ref=&require_stacking=&stack_ratio=
    &flow_prominence=&flow_prominence_max=&pressure_prominence=&concurrent_tol_sec=&bump_lookback_sec=
    &flow_frac=&flow_abs=&peep_min=&require_pressure=
    &dip_prominence=&lookback_sec=&require_constant_flow=&flow_range_max=
    &threshold=&window_hours=&ai_threshold=
```
The Viewer reads this once on mount: selects the owning patient/capture, applies the same
segmentation and **every** formula, and selects `breath_idx_a` in the breath dropdown. It
then runs its **own** `/api/asynchrony` fetch for that capture (this happens on every
capture the Viewer ever loads, not just deep-linked ones) and highlights every event it
finds, marking whichever one matches the `breath` param as active (brighter band). Passing
the exact formula params the notification was generated with guarantees that event
reappears in the Viewer's fresh scan — deriving the highlight from a live per-capture
fetch (rather than storing raw `t0`/`t1` seconds from the notification itself) means
switching capture/patient can never leave a stale band on the wrong waveform.

A `type: "mechanical_power"` or `type: "asynchrony_index"` notification's link omits `breath`
entirely (there's no single breath to select) — `n.breath_idx_a` is absent on both
notification types, and `NotificationList.jsx`'s `viewerLink()` only sets the `breath` param
when it's present. Both still land on `raw_data` = the patient's most recent capture, just
with no breath pre-selected and nothing highlighted, since neither is part of
`/api/asynchrony`'s `events` (see §5/§6 — both are patient-level). `threshold`/`window_hours`/
`ai_threshold` still round-trip through the link for consistency even though the Viewer
doesn't currently act on them.

## CLI
```bash
python3 backend/asynchrony.py [data_dir] [--baseline slope] [--hysteresis N] \
    [--ratio 0.5] [--ti-ref pair|capture|self] [--require-stacking] [--stack-ratio 1.5]

python3 backend/ineffective_effort.py [data_dir] [--baseline slope] [--hysteresis N] \
    [--flow-prominence 25] [--pressure-prominence 1.5] [--concurrent-tol-sec 0.3] \
    [--bump-lookback-sec 0.4]

python3 backend/auto_peep.py [data_dir] [--baseline slope] [--hysteresis N] \
    [--flow-frac 0.15] [--flow-abs 2.0] [--peep-min 1.0] [--flow-only]

python3 backend/flow_starvation.py [data_dir] [--baseline slope] [--hysteresis N] \
    [--dip-prominence 2.0] [--lookback-sec 0.4] [--require-constant-flow] [--flow-range-max 20.0]
# --calibrate prints the dataset's real notch-prominence percentiles instead of detecting,
# useful for re-checking the threshold if the dataset changes

python3 backend/mechanical_power.py [data_dir] [--baseline slope] [--hysteresis N] \
    [--threshold 17.0] [--window-hours 24.0]
# --compare cross-checks the direct P-V integral against Gattinoni's simplified equation
# on breaths where a plateau was detected, instead of running the per-patient threshold scan
```
