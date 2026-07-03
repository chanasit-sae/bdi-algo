# Double-Triggering Asynchrony Detection

**Module:** `backend/asynchrony.py` · **Deps:** pandas (reuses `breath_segment.py` output)
**API:** `GET /api/double-triggers` (single capture) and `GET /api/notifications` (scans the
dataset) — both in `backend/server/routers/asynchrony.py`
**Pages:**
- Notifications (`frontend/src/pages/NotificationsPage.jsx`) — lists every flagged
  event across the whole dataset.
- Viewer (`frontend/src/pages/ViewerPage.jsx`) — independently detects and highlights
  **every** flagged event for whatever capture is currently loaded (its own
  Ratio/Ti-ref/stacking controls, same as Notifications), listed in the aside and
  shaded on every chart. Clicking a notification deep-links here with the same
  segmentation *and* formula reproduced, so the same event is guaranteed to be
  found again and marked active (brighter band).

## What it detects
**Double triggering**: the patient's neural inspiratory effort continues past
the ventilator's inspiratory termination, so a second breath is triggered
almost immediately after the first — an abnormally short expiratory pause
between two consecutive breaths.

## Formula
```
Te(i) < ratio × Ti_ref
```
per **Thille AW, Rodriguez P, Cabello B, Lellouche F, Brochard L. "Patient-ventilator
asynchrony during assisted mechanical ventilation." *Intensive Care Med.*
2006;32(10):1515–1522** — the standard clinical definition ("two consecutive
cycles separated by a very short expiratory time, less than one half of the
mean inspiratory time").

| term | meaning |
|------|---------|
| `Te(i)` | `te_sec` of breath *i* — the expiratory gap before breath *i+1* begins. `te_sec = t_exp_end − t_insp_end`, and `t_exp_end` **is** breath *i+1*'s `t_insp_start` (see [breath-segment.md](breath-segment.md)), so this is exactly the inter-breath gap — no separate computation needed. |
| `ratio` | cutoff, default **0.5** ("less than one half"). |
| `Ti_ref` | the inspiratory-time reference the short `Te` is judged against — configurable via `ti_ref`. |

`ti_ref` modes:
- **`"pair"`** (default) — `mean(Ti(i), Ti(i+1))`: the pair's own average Ti.
  Robust to one noisy breath, adapts across a drifting session, no
  whole-capture baseline needed.
- **`"capture"`** — mean Ti over the capture's complete breaths. Closest to
  Thille's original "mean Ti of the recording".
- **`"self"`** — `Ti(i)` alone: the simplest, purely local comparison.

## Optional secondary check — volume stacking
Double-triggered breaths typically deliver close to double the tidal volume
of a normal breath pair — the actual clinical harm (volutrauma risk; **Pohlman
MC et al. "Excessive tidal volume from breath stacking during
lung-protective ventilation for acute lung injury." *Crit Care Med.*
2008;36(11):3019–23**).

`require_stacking=true` additionally requires
```
Vt(i) + Vt(i+1)  >  stack_ratio × 2 × median(Vt)
```
over the capture's complete breaths (`stack_ratio` default **1.5**), tightening
the criterion to timing events that also stacked volume. **Off by default**
so the detector matches the plain Thille timing definition; `vt_ratio` is
always reported on flagged pairs so it can be reviewed either way.

## Edge case: the trailing partial breath
A capture's last breath has no successor, so `te_sec` for it is an artifact
of where the recording was cut off, not a real inter-breath gap (see
[breath-segment.md](breath-segment.md) — `is_complete=False`). The detector
never uses it as the *first* breath of a pair (the pair loop only runs
`i in 0..len(breaths)-2`), so it cannot produce a false positive.

## On the sample dataset
Under the app's recommended segmentation (`baseline="slope"`, default slope
params) and the clinical default `ratio=0.5`, **this sample dataset produces
zero flagged pairs** — the ~68 captures are short (few breaths each) and
mostly controlled ventilation, so spontaneous-effort double-triggering may
genuinely not appear here. Loosening `baseline="zero"`, `hysteresis=5`,
`ratio=0.9` does produce flagged pairs (e.g. 47 across 23 captures), useful
for exercising the detector, but the looser ratio no longer reflects the
clinical definition — treat those as a sanity check, not a diagnosis.

## API
```
GET /api/double-triggers?file=<capture.csv>
    &baseline=zero|auto|slope|<num>&hysteresis=&slope=&sdelta=&swin=&srefr=&sguard=&speak=
    &ratio=0.5&ti_ref=pair|capture|self&require_stacking=false&stack_ratio=1.5
```
Segmentation params are identical to `/api/breaths` (the pair timing comes
directly from the chosen breath boundaries). Response:
```json
{
  "events": [ { "breath_idx_a": 0, "breath_idx_b": 1, "te_gap": 0.04,
                "ti_ref": 0.86, "te_ti_ratio": 0.047,
                "vt_pair": 858.7, "vt_ratio": 1.18, "stacked": false, ... } ],
  "n_breaths": 6,
  "baseline": 0.0,
  "formula": { "criterion": "te_gap < ratio * ti_ref", "ratio": 0.5, ... }
}
```

## Notifications: scanning the whole dataset

```
GET /api/notifications
    &baseline=zero|auto|slope|<num>&hysteresis=&slope=&sdelta=&swin=&srefr=&sguard=&speak=
    &ratio=0.5&ti_ref=pair|capture|self&require_stacking=false&stack_ratio=1.5
    &patient_id=<optional, restrict to one patient>
    &include_disconnected=false  # captures flagged disconnected (flat flow) can't produce
                                  # real events, so they're skipped by default for speed
```
Loops every capture (or one patient's), runs the same segmentation + detector as
`/api/double-triggers`, and flattens all flagged pairs into one list. Each
notification carries a `type` (only `"double_trigger"` exists today — new
asynchrony types can be added here without changing the response shape) and
echoes the exact `segmentation` params used, so a client can reproduce the
identical breath boundaries elsewhere:
```json
{
  "notifications": [ { "type": "double_trigger", "patient_id": "...", "raw_data": "....csv",
                        "day": 4, "time": "10:23:36", "breath_idx_a": 0, "breath_idx_b": 1,
                        "t_insp_start_a": 0.56, "t_exp_end_b": 6.0, "te_gap": 0.28,
                        "ti_ref": 2.44, "te_ti_ratio": 0.115, "vt_pair": 936.2,
                        "vt_ratio": 1.0, "stacked": false,
                        "segmentation": { "baseline": "zero", "hysteresis": 5.0, ... } } ],
  "scanned_captures": 40,
  "formula": { "criterion": "te_gap < ratio * ti_ref", "ratio": 0.5, ... }
}
```

The Notifications page (`frontend/src/pages/NotificationsPage.jsx`) renders
this list; clicking a notification builds a Viewer deep link:
```
/?file=<raw_data>&breath=<breath_idx_a>&<...segmentation>&ratio=&ti_ref=&require_stacking=&stack_ratio=
```
The Viewer (`ViewerPage.jsx`) reads this once on mount: selects the owning
patient/capture, applies the same segmentation *and* formula params, and
selects `breath_idx_a` in the breath dropdown. It then runs its **own**
`/api/double-triggers` fetch for that capture (independent of the deep link —
this happens on every capture the Viewer ever loads, not just deep-linked
ones) and highlights **every** flagged pair it finds, marking whichever one
matches the `breath` param as active (brighter band). Passing the exact same
`ratio`/`ti_ref`/`require_stacking`/`stack_ratio` the notification was
generated with guarantees that event reappears in the Viewer's fresh scan —
an earlier version passed raw `t0`/`t1` seconds instead, which went stale (wrong
region highlighted, or none) the moment the user switched to a different
capture; deriving the highlight from a live per-capture fetch instead of
stored seconds removes that failure mode structurally.

## CLI
```bash
python3 backend/asynchrony.py [data_dir] [--baseline slope] [--hysteresis N] \
    [--ratio 0.5] [--ti-ref pair|capture|self] [--require-stacking] [--stack-ratio 1.5]
```
