# Auto-PEEP (Air Trapping) Asynchrony Detection

**Module:** `backend/auto_peep.py` · **Deps:** numpy, pandas (reuses `breath_segment.py` output + the raw waveform)
**API:** `GET /api/auto-peep` (single capture) and `GET /api/notifications` (scans the
dataset) — both in `backend/server/routers/asynchrony.py`
**Pages:** Notifications (`frontend/src/pages/NotificationsPage.jsx`) lists every flagged
event across the dataset; each renders in `NotificationList.jsx` with its residual
fraction, the PEEP excess (cmH₂O), and a `flow+pressure`/`flow only` badge.

## What it detects
**Auto-PEEP** (intrinsic PEEP / air trapping / dynamic hyperinflation): the lung
does not fully empty before the next breath begins, so gas is trapped and
end-expiratory alveolar pressure sits above the set PEEP. It is the
physiological opposite of the short-`Te` [double trigger](asynchrony.md) — there
expiration is too *short*; here it is too *incomplete*.

Neither waveform alone is specific, so detection requires the two signals to
agree (the **flow + pressure mix**):

- **Flow (air trapping):** expiratory flow fails to return to the zero baseline
  before the next inspiration — persistent end-expiratory flow.
- **Pressure (dynamic hyperinflation):** end-expiratory airway pressure sits
  above the set PEEP.

## Inputs
- **Waveform** (`parser.load_waveform`): per-sample `flow` (L/min) and `pressure`
  (cmH₂O) at 25 Hz.
- **Breath table** (`breath_segment.segment_capture`): `insp_end_idx`,
  `exp_end_idx`, `is_complete`, plus timing/index columns.

Only **complete** breaths are scored — the trailing partial breath's
`exp_end_idx` is the capture edge, not a real end-expiration (see
[breath-segment.md](breath-segment.md), `is_complete=False`). Need ≥2 complete
breaths or the detector returns empty.

## Formula

For each complete breath, take the last expiratory sample `j = exp_end_idx`:
`eef = flow[j]` (end-expiratory flow), `eep = pressure[j]` (end-expiratory
pressure).

**Capture-level reference levels** (data-driven — no absolute calibration):
```
z_ref    = percentile(all eef, 75)     # true-zero flow
set_peep = percentile(all eep, 10)     # set PEEP
```
Breaths that empty completely settle at true zero flow; trapped breaths stay
*below* it — so the high percentile of end-expiratory flow picks the well-emptied
breaths as the zero reference. Symmetrically, the best-emptied breaths reach set
PEEP, so the low percentile of end-expiratory pressure picks it out.

> **Do not** reuse the segmentation onset baseline
> (`breath_segment.estimate_baseline_from_onsets`) as `z_ref`: that is the
> *median* end-expiratory level and would subtract out the very residual this
> test measures.

**Per-breath metrics**, over the expiratory limb `flow[insp_end_idx : exp_end_idx+1]`:
```
peak_exp_flow      = min(exp_limb_flow)              # most negative = peak exp flow
residual           = z_ref − eef                     # >0 ⇒ still expiring at end
peak_mag           = z_ref − peak_exp_flow           # full exp flow magnitude
flow_residual_frac = residual / peak_mag             # fraction still present at end-exp
peep_delta         = eep − set_peep                  # ≈ intrinsic PEEP (cmH₂O)
```

**Decision** — both signatures must hold (the mix):
```
flow  hit:  flow_residual_frac > flow_frac   AND   residual > flow_abs
pressure :  peep_delta > peep_min
flag  = flow_hit AND pressure_flag
```
`flow_abs` is an absolute noise floor so a large *fraction* on a low-flow breath
doesn't trigger on its own. With `require_pressure=false`, only the flow
signature is required (`peep_delta` is still reported for review).

| param | default | meaning |
|-------|---------|---------|
| `flow_frac` | **0.15** | min fraction of expiratory flow still present at end-expiration |
| `flow_abs` | **2.0** | min absolute residual end-expiratory flow (L/min), noise floor |
| `peep_min` | **1.0** | min end-expiratory pressure excess over set PEEP (cmH₂O) |
| `require_pressure` | **true** | require the pressure signature too (the mix) |
| `zero_pct` | **75** | percentile of end-expiratory flow taken as true zero (`z_ref`) |
| `setpeep_pct` | **10** | percentile of end-expiratory pressure taken as set PEEP |

## Worked example
The one hit on the sample dataset
(`bd49632138fb4b75d505156379f25fb9_0_170204`, breath 0):
```
eef = 18.95,  peak_exp_flow = −21.61,  z_ref = 31.41
residual = 31.41 − 18.95 = 12.46
peak_mag = 31.41 − (−21.61) = 53.02
flow_residual_frac = 12.46 / 53.02 = 0.235      (> 0.15 ✓,  residual 12.46 > 2 ✓)
eep = 3.87,  set_peep = 2.11
peep_delta = 3.87 − 2.11 = 1.76                  (> 1.0 ✓)
→ both agree → flagged
```

## Edge cases & limitations
- **Trailing partial breath** — never scored (`is_complete=False`); its
  `exp_end_idx` is the recording cut-off, not an end-expiration.
- **All breaths trapped** — `z_ref`/`set_peep` are estimated from the same
  breaths being tested, so if *every* breath traps, the references shift toward
  the trapped level and the detector under-flags. It is designed to find trapped
  breaths *relative to* the capture's best-emptied ones, not to measure absolute
  intrinsic PEEP (which needs an expiratory-hold maneuver).
- **Degenerate expiratory limb** — breaths with `peak_mag ≤ 0` are skipped.

## On the sample dataset
Under the app's recommended segmentation (`baseline="slope"`) and the defaults
above, the flow + pressure mix flags **1 breath across 40 captures**; the
flow-only screen (`require_pressure=false`) flags **4 across 3** — the pressure
gate is what adds specificity. Loosen `flow_frac`/`peep_min` for higher
sensitivity when exercising the detector.

## API
```
GET /api/auto-peep?file=<capture.csv>
    &baseline=zero|auto|slope|<num>&hysteresis=&slope=&sdelta=&swin=&srefr=&sguard=&speak=
    &flow_frac=0.15&flow_abs=2.0&peep_min=1.0&require_pressure=true
```
Segmentation params are identical to `/api/breaths` and `/api/double-triggers`.
Response:
```json
{
  "events": [ { "breath_idx": 0, "t_insp_start": 0.96, "t_exp_end": 2.24,
                "eef": 18.95, "peak_exp_flow": -21.61, "z_ref": 31.41,
                "flow_residual_frac": 0.235, "eep": 3.87, "set_peep": 2.11,
                "peep_delta": 1.76, "pressure_flag": true, ... } ],
  "n_breaths": 4,
  "baseline": 19.86,
  "formula": { "criterion": "flow_residual_frac > flow_frac (+ peep_delta > peep_min)",
               "flow_frac": 0.15, "flow_abs": 2.0, "peep_min": 1.0,
               "require_pressure": true }
}
```

## Notifications: scanning the whole dataset
`GET /api/notifications` runs this detector alongside double-triggering on every
capture and flattens the hits into the same list, with `type: "auto_peep"`. It
accepts the auto-PEEP params (`flow_frac`, `flow_abs`, `peep_min`,
`require_pressure`) and returns a separate `auto_peep_formula` block. Each
notification echoes the exact `segmentation` params used and sets
`breath_idx_a = breath_idx` so it deep-links into the Viewer the same way a
double-trigger does:
```json
{ "type": "auto_peep", "patient_id": "...", "raw_data": "....csv",
  "day": 0, "time": "17:02:04", "breath_idx_a": 0, "breath_idx": 0,
  "t_insp_start": 0.96, "t_exp_end": 2.24, "ti_sec": 0.76, "te_sec": 0.52,
  "flow_residual_frac": 0.235, "peep_delta": 1.76, "eef": 18.95, "z_ref": 31.41,
  "pressure_flag": true, "segmentation": { "baseline": "slope", ... } }
```

## CLI
```bash
python3 backend/auto_peep.py [data_dir] [--baseline slope] [--hysteresis N] \
    [--flow-frac 0.15] [--flow-abs 2.0] [--peep-min 1.0] [--flow-only]
```
