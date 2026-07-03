"""Parse SMART-ICU ventilator metadata (JSON) and waveform signals (CSV).

The metadata JSON files store patient info as free-text strings, so the fields
below are extracted with regexes. Missing values are recorded as `-` or the
Thai `ไม่ระบุ` ("not specified") in the source and become None here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pandas as pd

SAMPLE_RATE_HZ = 25
WAVEFORM_COLUMNS = ["flow", "pressure", "volume"]

_SEX_MAP = {"ช": "M", "ญ": "F"}


@dataclass
class Capture:
    raw_data: str
    time: str  # HH:MM:SS


@dataclass
class Diagnosis:
    primary: str | None = None
    primary_icd: str | None = None
    secondary: str | None = None
    secondary_icd: str | None = None


@dataclass
class PatientDay:
    """One daily record for a patient (mirrors one object in the JSON array)."""

    patient_id: str
    day: int | None
    age: int | None
    sex: str | None  # "M" / "F"
    bw_kg: float | None
    ht_cm: float | None
    bmi: float | None
    diagnosis: Diagnosis
    operation: str | None
    ven: str | None
    captures: list[Capture] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _to_float(token: str) -> float | None:
    try:
        return float(token)
    except (TypeError, ValueError):
        return None


def _parse_bed(bed: str) -> tuple[str, int | None]:
    """`"<hash>, 4 วัน"` -> ("<hash>", 4)."""
    parts = bed.split(",", 1)
    patient_id = parts[0].strip()
    day = None
    if len(parts) > 1:
        m = re.search(r"(\d+)", parts[1])
        if m:
            day = int(m.group(1))
    return patient_id, day


def _parse_patient(patient: str) -> tuple[str | None, int | None]:
    """`"ช 47 ปี"` -> ("M", 47)."""
    sex = None
    for th, code in _SEX_MAP.items():
        if th in patient:
            sex = code
            break
    m = re.search(r"(\d+)", patient)
    age = int(m.group(1)) if m else None
    return sex, age


def _parse_demographic(demo: str) -> tuple[float | None, float | None, float | None]:
    """`"BW/HT 45 kg / 170 cm BMI 15.57 kg/m2"` -> (45.0, 170.0, 15.57)."""
    bw = ht = bmi = None
    m = re.search(r"BW/HT\s+([\d.]+)\s*kg\s*/\s*([\d.]+)\s*cm", demo)
    if m:
        bw, ht = _to_float(m.group(1)), _to_float(m.group(2))
    m = re.search(r"BMI\s+([\d.]+)", demo)
    if m:
        bmi = _to_float(m.group(1))
    return bw, ht, bmi


def _parse_diagnosis(dx: str) -> Diagnosis:
    """Split "PDx <text> SDx <text>" and pull the first ICD code from each."""
    diag = Diagnosis()
    pm = re.search(r"PDx\s+(.*?)(?:\s+SDx\s+|$)", dx)
    sm = re.search(r"SDx\s+(.*)$", dx)

    def _clean(text: str | None) -> tuple[str | None, str | None]:
        if not text:
            return None, None
        text = text.strip()
        if text in ("ไม่ระบุ", "-", ""):
            return None, None
        icd = None
        icd_m = re.search(r"\(([A-Z]\d{2}(?:\.\d+)?)\)?", text)
        if icd_m:
            icd = icd_m.group(1)
        return text, icd

    diag.primary, diag.primary_icd = _clean(pm.group(1) if pm else None)
    diag.secondary, diag.secondary_icd = _clean(sm.group(1) if sm else None)
    return diag


def _clean_operation(op: str | None) -> str | None:
    if not op:
        return None
    op = re.sub(r"^\s*HxSx\s*", "", op).strip()
    return None if op in ("ไม่ระบุ", "-", "") else op


def parse_patient_file(path: str | Path) -> list[PatientDay]:
    """Parse one patient JSON file into a list of PatientDay records."""
    path = Path(path)
    records = json.loads(path.read_text(encoding="utf-8"))
    out: list[PatientDay] = []
    for rec in records:
        patient_id, day = _parse_bed(rec.get("bed", ""))
        sex, age = _parse_patient(rec.get("patient", ""))
        bw, ht, bmi = _parse_demographic(rec.get("demographic", ""))
        captures = [
            Capture(raw_data=c.get("raw_data", ""), time=c.get("time", ""))
            for c in rec.get("captures", [])
        ]
        out.append(
            PatientDay(
                patient_id=patient_id,
                day=day,
                age=age,
                sex=sex,
                bw_kg=bw,
                ht_cm=ht,
                bmi=bmi,
                diagnosis=_parse_diagnosis(rec.get("diagnosis", "")),
                operation=_clean_operation(rec.get("operation")),
                ven=rec.get("ven"),
                captures=captures,
            )
        )
    return out


def load_dataset(data_dir: str | Path) -> list[PatientDay]:
    """Parse every `*.json` patient file in a directory."""
    data_dir = Path(data_dir)
    records: list[PatientDay] = []
    for jf in sorted(data_dir.glob("*.json")):
        records.extend(parse_patient_file(jf))
    return records


def metadata_frame(records: list[PatientDay]) -> pd.DataFrame:
    """Flatten PatientDay records into one row per capture (or per day if none)."""
    rows = []
    for r in records:
        base = {
            "patient_id": r.patient_id,
            "day": r.day,
            "age": r.age,
            "sex": r.sex,
            "bw_kg": r.bw_kg,
            "ht_cm": r.ht_cm,
            "bmi": r.bmi,
            "pdx": r.diagnosis.primary,
            "pdx_icd": r.diagnosis.primary_icd,
            "sdx": r.diagnosis.secondary,
            "sdx_icd": r.diagnosis.secondary_icd,
            "operation": r.operation,
            "ven": r.ven,
        }
        if r.captures:
            for c in r.captures:
                rows.append({**base, "capture_time": c.time, "raw_data": c.raw_data})
        else:
            rows.append({**base, "capture_time": None, "raw_data": None})
    return pd.DataFrame(rows)


def load_waveform(path: str | Path, add_time: bool = True) -> pd.DataFrame:
    """Load a WaveformExport CSV.

    Handles the UTF-8 BOM and the blank line between header and data. Returns
    columns flow/pressure/volume, plus a `t_sec` column derived from 25 Hz.
    """
    df = pd.read_csv(path, skip_blank_lines=True, encoding="utf-8-sig")
    df.columns = WAVEFORM_COLUMNS
    # Some captures in the full dataset have a stray non-numeric value in one
    # of these columns (e.g. a repeated header row, a text artifact), which
    # makes pandas infer the whole column as strings instead of floats and
    # breaks every downstream numeric op. Coerce explicitly so any such value
    # becomes NaN (handled by the existing np.nanmax/nanmin calls) rather than
    # silently turning the column into object dtype.
    for col in WAVEFORM_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(how="all").reset_index(drop=True)
    if add_time:
        df.insert(0, "t_sec", df.index / SAMPLE_RATE_HZ)
    return df


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parent.parent
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "smart_icu_data"

    recs = load_dataset(data_dir)
    meta = metadata_frame(recs)
    patients = meta["patient_id"].nunique()
    n_captures = meta["raw_data"].notna().sum()
    print(f"parsed {len(recs)} patient-day records across {patients} patients")
    print(f"{n_captures} waveform captures referenced\n")
    print(meta.dropna(subset=["raw_data"]).head(10).to_string(index=False))

    sample = meta.dropna(subset=["raw_data"]).iloc[0]["raw_data"]
    wf = load_waveform(data_dir / sample)
    print(f"\nsample waveform {sample}: {wf.shape[0]} rows "
          f"({wf['t_sec'].iloc[-1]:.1f}s @ {SAMPLE_RATE_HZ}Hz)")
    print(wf.head().to_string(index=False))
