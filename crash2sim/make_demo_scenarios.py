#!/usr/bin/env python3
"""Build daylight copies of the ground-truth scenarios into scenarios/demo/ for live viewing in esmini.

Same crash (speeds, timing, friction) as scenarios/generated/ground_truth/, but daytime + clear sky
so the scene is visible. Launch them with play/Play Scenarios.command (Mac) or play/play.bat (Windows).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from crash2sim import build, schema  # noqa: E402

for p in sorted((ROOT / "data" / "ground_truth").glob("*.json")):
    spec = {k: v for k, v in json.loads(p.read_text()).items() if k != "validation_targets"}
    clean, _ = schema.sanitize(spec)
    out = build.build_xosc(clean, p.stem, ROOT / "scenarios" / "demo", daylight=True)
    print("wrote", out.relative_to(ROOT))
