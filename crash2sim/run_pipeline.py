#!/usr/bin/env python3
"""crash2sim - crash report -> LLM -> OpenSCENARIO -> esmini -> metrics & figures.

Examples
  python run_pipeline.py --backend ollama                 # LLM (local, default llama3.1:8b)
  python run_pipeline.py --backend ollama --model qwen2.5:7b
  python run_pipeline.py --backend openai                 # any OpenAI-compatible API (.env)
  python run_pipeline.py --backend rules                  # no-LLM baseline
  python run_pipeline.py --backend ground_truth --video   # hand-built specs (manual recreation)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from crash2sim import analyze, build, extract, schema, simulate  # noqa: E402


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default="ollama", choices=["ollama", "openai", "rules", "ground_truth"])
    ap.add_argument("--model", default=None, help="model name for ollama/openai backends")
    ap.add_argument("--reports", default="data/reports/*.json")
    ap.add_argument("--video", action="store_true", help="also render an mp4 with the esmini viewer")
    args = ap.parse_args()
    load_env()

    tag = args.backend if not args.model else f"{args.backend}-{args.model.replace(':', '-').replace('/', '-')}"
    out_root = ROOT / "outputs" / tag
    xosc_dir = ROOT / "scenarios" / "generated" / tag
    rows = []

    for rp in sorted(ROOT.glob(args.reports)):
        report = json.loads(rp.read_text())
        rid = report["report_id"]
        print(f"\n=== {rid}  ({report['source_type']})")
        out = out_root / rid
        out.mkdir(parents=True, exist_ok=True)
        row = {"report_id": rid, "source": report["source_type"], "backend": tag}

        # 1) report -> spec
        truth_path = ROOT / "data" / "ground_truth" / f"{rid}.json"
        truth = json.loads(truth_path.read_text()) if truth_path.exists() else None
        try:
            if args.backend == "ground_truth":
                raw, secs = truth, 0.0
            else:
                raw, secs = extract.extract(report, args.backend, args.model)
        except Exception as e:  # noqa: BLE001
            print(f"  extraction failed: {e}")
            rows.append(dict(row, status=f"extract_failed: {e}"))
            continue
        row["llm_seconds"] = round(secs, 1)
        errs = schema.validate(raw)
        (out / "spec_raw.json").write_text(json.dumps(raw, indent=2))
        if errs:
            print("  schema errors:", errs)
            rows.append(dict(row, status="schema_invalid", errors="; ".join(errs)))
            continue
        spec, notes = schema.sanitize(raw)
        (out / "spec.json").write_text(json.dumps(spec, indent=2))
        print(f"  type={spec['scenario_type']}  ego={spec['ego']['speed_kph']} km/h  "
              f"other={spec['other']['maneuver']}  confidence={spec['confidence']}")

        # 2) spec -> xosc
        xosc = build.build_xosc(spec, rid, xosc_dir)

        # 3) simulate
        sim = simulate.run(xosc, out)
        if not sim["ok"]:
            print("  esmini failed:", sim["errors"][:3])
            rows.append(dict(row, status="sim_failed", errors="; ".join(sim["errors"][:3])))
            continue
        other = "Lead" if spec["scenario_type"] == "rear_end" else "NPC"
        m = analyze.metrics(sim["csv"], other, sim["collision_time"])
        m["reproduces_report"] = m["sim_collision"] == spec["collision_reported"]
        (out / "metrics.json").write_text(json.dumps(m, indent=2))
        print(f"  sim collision={m['sim_collision']}  reported={spec['collision_reported']}  "
              f"-> reproduces report: {m['reproduces_report']}")

        # 4) figures / video
        nice = {"rear_end": "Rear-end", "ltap_od": "Left turn across path"}[spec["scenario_type"]]
        title = f"{rid} · {nice} · {tag}"
        analyze.scenario_figure(sim["csv"], other, spec, m, title, out / "scenario.png")
        if args.video:
            v = simulate.record_video(xosc, out / "scenario.mp4")
            print("  video:", v.relative_to(ROOT) if v else "not rendered (needs a display or xvfb + ffmpeg)")

        # 5) score vs ground truth
        if truth and args.backend != "ground_truth":
            sc = analyze.score(spec, truth)
            (out / "score_vs_ground_truth.json").write_text(json.dumps(sc, indent=2))
            row["field_accuracy"] = sc["accuracy"]
            print(f"  field accuracy vs ground truth: {sc['accuracy']:.0%}")

        rows.append(dict(row, status="ok", scenario_type=spec["scenario_type"], confidence=spec["confidence"],
                         n_assumptions=len(spec["assumptions"]), xosc=str(xosc.relative_to(ROOT)), **m))

    import pandas as pd
    df = pd.DataFrame(rows)
    out_root.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_root / "summary.csv", index=False)
    print(f"\nSummary -> {(out_root / 'summary.csv').relative_to(ROOT)}")
    cols = [c for c in ["report_id", "status", "scenario_type", "sim_collision", "reproduces_report",
                        "field_accuracy", "n_assumptions"] if c in df]
    print(df[cols].to_string(index=False))


if __name__ == "__main__":
    main()
