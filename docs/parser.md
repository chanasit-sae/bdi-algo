# Parser — metadata & waveform loader

**Module:** `backend/parser.py` · **Deps:** stdlib + pandas

Turns the raw SMART-ICU sample into analysis-ready data: parses the free-text
patient metadata (JSON) and loads the ventilator waveform signals (CSV).

## Why it exists
The dataset stores patient info as human-written strings
(`"BW/HT 45 kg / 170 cm BMI 15.57 kg/m2"`, `"ช 47 ปี"`), not typed fields.
This module flattens them into clean columns and loads waveforms consistently.

## Public API
| Function | Purpose |
|----------|---------|
| `parse_patient_file(path)` | Parse one patient JSON → list of `PatientDay` |
| `load_dataset(dir)` | Parse every `*.json` in a directory |
| `metadata_frame(records)` | Flatten to a tidy DataFrame, one row per capture |
| `load_waveform(path)` | Load a WaveformExport CSV → DataFrame |

## Data model
`PatientDay` (one per day per patient) with `Diagnosis` and `Capture` children.
Fields: `patient_id, day, age, sex, bw_kg, ht_cm, bmi, diagnosis(primary/
primary_icd/secondary/secondary_icd), operation, ven, captures[]`.

`metadata_frame` emits one row per capture (or one row per day if no captures),
columns: `patient_id, day, age, sex, bw_kg, ht_cm, bmi, pdx, pdx_icd, sdx,
sdx_icd, operation, ven, capture_time, raw_data`.

## Field extraction rules
| Source field | Parsed into | Rule |
|--------------|-------------|------|
| `bed` `"<hash>, 4 วัน"` | `patient_id`, `day` | split on comma, int day |
| `patient` `"ช 47 ปี"` | `sex`, `age` | ช→M, ญ→F; first integer = age |
| `demographic` | `bw_kg, ht_cm, bmi` | regex; `-` → None |
| `diagnosis` `"PDx … SDx …"` | primary/secondary + ICD | first `(A00.0)` code per part |
| `operation` | `operation` | strip `HxSx`; `ไม่ระบุ`/`-` → None |

## Waveform loading
`load_waveform` handles the file quirks: UTF-8 **BOM** and the **blank line**
between header and data. Renames columns to `flow` / `pressure` / `volume`,
drops all-empty rows, and (default) inserts `t_sec = index / 25 Hz`.

## Details worth knowing
- ICD text keeps its parenthetical (e.g. `Hemoptysis (R04.2)`); the bare code
  is also extracted separately into `pdx_icd` / `sdx_icd`.
- Some source `SDx` strings are truncated (missing closing paren); the ICD regex
  tolerates this, and some yield no code (`sdx_icd` = None).
- Each CSV is a ~10 s snapshot (~250 rows @ 25 Hz), not a continuous recording.
- Missing values (`-`, `ไม่ระบุ`) become None/NaN.

## Usage
```bash
python3 backend/parser.py [data_dir]   # demo; defaults to ../smart_icu_data
```
```python
from parser import load_dataset, metadata_frame, load_waveform
df = metadata_frame(load_dataset("smart_icu_data"))
wf = load_waveform("smart_icu_data/<file>.csv")   # t_sec, flow, pressure, volume
```
