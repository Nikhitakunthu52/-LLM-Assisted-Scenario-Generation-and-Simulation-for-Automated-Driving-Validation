#!/usr/bin/env python3
"""Convert an NHTSA Crash Viewer export (CIREN / CISS .xlsx) into a crash2sim report JSON.

  python scripts/ciren_to_report.py path/to/CrashExport.xlsx --id CIREN_8392
  python scripts/ciren_to_report.py export.xlsx --id CISS_A1 --out data/reports/CISS_A1.json

PRIVACY: exports also contain medical, injury, demographic and alcohol/drug data.
This script copies ONLY an allowlist of crash-, roadway- and vehicle-level fields plus
EDR pre-crash time series. Keep the raw .xlsx out of git (data/raw/ is gitignored).
"""
from __future__ import annotations

import argparse
import re
import json
from pathlib import Path

import pandas as pd

CRASH_FIELDS = ["CASENUMBER", "CRASHYEAR", "CRASHMONTH", "VEHICLES", "MANCOLLTEXT"]
VEHICLE_FIELDS = [  # GV sheet - roadway / pre-crash / kinematics only
    "MODELYRTEXT", "MAKETEXT", "MODELTEXT", "BODYTYPETEXT", "CURBWTTEXT", "SPEEDLIMITTEXT",
    "TRAFFLOWTEXT", "INITLANETEXT", "ALIGNMENTTEXT", "PROFILETEXT", "SURFCONDTEXT", "LIGHTCONDTEXT",
    "WEATHERTEXT", "TRAFDEVTEXT", "RELTOJUNCTTEXT", "PREMOVETEXT", "CRITCATTEXT", "CRITEVENTTEXT",
    "MANEUVERTEXT", "PRESTABTEXT", "PRELOCTEXT", "CRASHCATTEXT", "CRASHCONFTEXT", "CRASHTYPETEXT",
    "DAMPLANETEXT", "DVTOTALTEXT", "DVLONGTEXT", "DVLATTEXT", "DVCONFTEXT", "DISTRACTTEXT",
]
EDR_SIGNALS = {"Vehicle Speed (kmph)": "speed_kph", "Service Brake": "service_brake",
               "Accelerator Pedal (% full)": "accelerator_pct", "Steering Input (deg)": "steering_deg"}


PERSONAL_KEYWORDS = ("injur", "transported", "hospital", "treatment", "airbag", "air bag",
                     "belt", "restrain", "occupant", "trauma", "medical", "fatal")


def scrub_narrative(text: str) -> str:
    """Keep only paragraphs describing roadway, vehicles and crash sequence."""
    paras = [p.strip() for p in str(text).split("\n") if p.strip()]
    keep = [p for p in paras if not any(k in p.lower() for k in PERSONAL_KEYWORDS)]
    keep = [re.sub(r"\s*\((?:CIREN|CISS)? ?case subject\)", "", p, flags=re.I) for p in keep]
    keep = [re.sub(r"\b\d{1,3}-year-old,?\s*(?:(?:male|female),?\s*)?", "", p, flags=re.I) for p in keep]
    return "\n\n".join(keep)


def _clean(v):
    if pd.isna(v):
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v.item() if hasattr(v, "item") else v


def convert(xlsx: Path, report_id: str) -> dict:
    x = pd.ExcelFile(xlsx)
    crash = pd.read_excel(x, "CRASH").iloc[0]
    coded = {k.replace("TEXT", "").lower(): _clean(crash[k]) for k in CRASH_FIELDS if k in crash}

    if "GV" in x.sheet_names:
        gv = pd.read_excel(x, "GV")
        for _, row in gv.iterrows():
            vn = int(row["VEHNO"])
            for f in VEHICLE_FIELDS:
                if f in gv.columns:
                    coded[f"V{vn}_{f.replace('TEXT', '').lower()}"] = _clean(row[f])

    if "PRE_FHE" in x.sheet_names:
        pre = pd.read_excel(x, "PRE_FHE")
        for _, row in pre.iterrows():
            coded[f"V{int(row['VEHNO'])}_pre_event"] = _clean(row.get("PREEVENTTEXT"))

    edr = {}
    if "EDRPRECRASH" in x.sheet_names:
        e = pd.read_excel(x, "EDRPRECRASH")
        for (vn, sig), grp in e.groupby(["VEHNO", "PCODETEXT"]):
            if sig in EDR_SIGNALS:
                edr.setdefault(f"V{int(vn)}", {})[EDR_SIGNALS[sig]] = [
                    [float(t), _clean(v)] for t, v in zip(grp.PTIME, grp.PVALUETEXT)]

    return {
        "report_id": report_id,
        "source_type": "NHTSA CIREN/CISS in-depth investigation (Crash Viewer export)",
        "synthetic": False,
        "case_id": str(coded.get("casenumber")),
        "narrative": scrub_narrative(crash.get("SUMMARY", "")),
        "coded_fields": coded,
        "edr_precrash": edr,   # {vehicle: {signal: [[t_rel_to_impact_s, value], ...]}}
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--id", required=True, help="report_id, e.g. CIREN_8392")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    out = a.out or Path(__file__).resolve().parents[1] / "data" / "reports" / f"{a.id}.json"
    rep = convert(a.xlsx, a.id)
    out.write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    print(f"wrote {out}  ({len(rep['coded_fields'])} coded fields, EDR vehicles: {list(rep['edr_precrash'])})")


if __name__ == "__main__":
    main()
