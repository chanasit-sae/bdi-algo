# Visualization Server

**Module:** `backend/viz_server.py` · **Deps:** stdlib only (reuses `parser.py`)

An interactive dashboard for internal testing: pick a patient → pick a capture →
see the Flow / Pressure / Volume traces and that capture's metadata side by side.
Zero pip installs, no CDN, runs offline.

## Usage
```bash
python3 backend/viz_server.py [--port 8000] [--data DIR]
# open http://localhost:8000
```
Binds to `127.0.0.1` only. Uses `ThreadingHTTPServer` (fine for single-user).

## Endpoints
| Route | Returns |
|-------|---------|
| `GET /` | Dashboard HTML/JS (embedded in the module) |
| `GET /api/index` | All patients grouped, each with captures + metadata; every capture carries a `connected` flag (flat trace → False) |
| `GET /api/waveform?file=<csv>` | `{t_sec, flow, pressure, volume}` arrays |
| `GET /api/breaths?file=<csv>&hysteresis=<n>&baseline=<zero\|auto\|num>` | `{breaths: [...], baseline: <float>}` — breath table for that capture (from `breath_segment.segment_capture`); `hysteresis` optional, defaults 0, bad values → 0; `baseline` optional, defaults `zero` — `auto`, a numeric offset, or anything unparseable → `zero`; `baseline` in the response is the resolved numeric offset |

## Frontend
- Three dropdowns: **patient → capture → breath**.
- Three hand-drawn `<canvas>` line charts (Flow/Pressure/Volume): grid lines,
  y-axis labels, zero line, x-axis in seconds, HiDPI-aware, redraw on resize.
- **Breath overlay:** faint vertical lines mark every inspiration onset on each
  chart. The breath dropdown lists each detected breath (`— whole capture —`
  default). Selecting one highlights it in place — shading its inspiration (blue)
  and expiration (orange) phases across the full-capture view (no zoom).
- Two metadata panels: **patient/capture** (sex/age, BW/HT, BMI, ventilator, day,
  time, PDx/SDx, operation) and **breath** (Ti, Te, I:E, tidal volume, peak flow,
  peak/mean pressure, PEEP, rate) for the selected breath.
- Captures with no zero-crossings show `0 breaths` and only the whole-capture view.
- **Baseline selector** (`zero` default / `auto` / `manual`) + **Offset** field:
  `auto` uses the per-capture low-percentile offset
  (`breath_segment.estimate_baseline`) so captures with a positive DC bias that
  never cross zero (normal breath shape, e.g. `bd4963…_1_090205`) still segment;
  `manual` uses the numeric **Offset** input (L/min) so you can dial the crossing
  baseline by hand. Changing either re-runs segmentation live. Pair a non-zero
  baseline with hysteresis — see the caveat in `breath-segment.md`. The resolved
  offset is returned as `baseline` in `/api/breaths` and drawn on the Flow chart
  as a dashed orange line labelled with its L/min value, so the crossing level
  moves visibly as you change mode/offset.
- **Hysteresis input** (L/min, default 0): a dead-band around the baseline for
  crossing detection. Changing it re-runs segmentation on the current capture and
  refreshes the breath list/overlays — lets you tune noise rejection live.

## Important details
- **Disconnected captures hidden by default, toggleable.** `build_index` tags
  each capture `connected = flow range (max − min) ≥ MIN_FLOW_RANGE` (5 L/min) —
  a flat trace means the ventilator isn't on a patient (28 of 68 on this sample;
  threshold sits in a wide natural gap: flat ≤ 1.82 L/min, real ≥ 9.96). All
  captures stay in the index and the path-traversal whitelist. The frontend
  **Show disconnected** checkbox (default off) filters the patient/capture
  dropdowns: off → connected only (2 patients / 40 captures); on → all (3
  patients / 68), with flat ones labelled `· disconnected`. A patient with no
  visible captures drops out of the patient dropdown (`5ea4aaf…` when off).
- **Valid JSON only.** Responses go through `_denan()` (float NaN → null) and
  `json.dumps(..., allow_nan=False)`. Missing values (patients without BW/HT or
  diagnosis) would otherwise emit bare `NaN`, which the browser's strict
  `JSON.parse` rejects — that previously left the patient dropdown empty.
- **Path-traversal guard.** `/api/waveform` and `/api/breaths` only serve
  filenames present in the parsed capture set; anything else → 404
  (e.g. `../parser.py` → 404).

## Testing
```bash
# API smoke test (use STRICT parse — plain json.load tolerates NaN and hides bugs)
curl -s localhost:8000/api/index | python3 -c "import sys,json; \
  json.loads(sys.stdin.read(), parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x))); \
  print('valid JSON')"
curl -s "localhost:8000/api/waveform?file=<csv>" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['t_sec']),'samples')"
curl -s -o /dev/null -w '%{http_code}\n' "localhost:8000/api/waveform?file=../parser.py"  # 404
```
Then verify in a real browser: dropdowns populate, all three traces draw, status
shows `N samples · Ns @ 25Hz`, metadata updates, charts redraw on resize.

> Note: curl + plain `json.load` is too lenient to catch browser-invalid JSON.
> Smoke tests must parse strictly (reject `NaN`/`Infinity`) or run in a browser.

## Known limitations
- Charts are static (no zoom/pan). Revisit Streamlit/Plotly if richer interaction
  is needed.
