#!/usr/bin/env python3
"""Build the demo summary figures from data/coverage.csv and outputs/*/summary.csv.

  outputs/data_coverage.png   - which scenario elements each crash report provides
  outputs/results_matrix.png  - does each backend's scenario reproduce the reported crash?
  outputs/SUMMARY.md          - tables for the slides / README
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from crash2sim.analyze import INK, INK2, SURF, plt  # noqa: E402  (shared style)

LEVEL = {"stated": 2, "partial": 1, "missing": 0}
FILL = {2: "#2a78d6", 1: "#86b6ef", 0: "#ecebe7"}
TEXT = {2: "#ffffff", 1: INK, 0: INK2}
LABEL = {2: "stated", 1: "partial", 0: "missing"}


def coverage_figure():
    df = pd.read_csv(ROOT / "data" / "coverage.csv")
    cols = [c for c in df.columns if c not in ("report_id", "source")]
    fig, ax = plt.subplots(figsize=(12, 0.65 * len(df) + 1.8))
    ax.set_xlim(0, len(cols)); ax.set_ylim(len(df), 0)
    for i, row in df.iterrows():
        for j, c in enumerate(cols):
            lv = LEVEL[row[c]]
            ax.add_patch(plt.Rectangle((j + 0.03, i + 0.05), 0.94, 0.9, color=FILL[lv], lw=0))
            ax.text(j + 0.5, i + 0.5, LABEL[lv], ha="center", va="center", fontsize=8.5, color=TEXT[lv])
    ax.set_xticks([j + 0.5 for j in range(len(cols))])
    ax.set_xticklabels([c.replace("_", "\n") for c in cols], fontsize=8.5)
    ax.xaxis.tick_top()
    ax.set_yticks([i + 0.5 for i in range(len(df))])
    ax.set_yticklabels(df.report_id)
    ax.grid(False); ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    score = df[cols].replace(LEVEL).sum(axis=1) / (2 * len(cols))
    for i, v in enumerate(score):
        ax.text(len(cols) + 0.1, i + 0.5, f"{v:.0%}", va="center", fontsize=10, color=INK, clip_on=False)
    ax.text(len(cols) + 0.1, -0.15, "coverage", fontsize=8.5, color=INK2, clip_on=False)
    fig.suptitle("Can a crash report drive a simulation? Scenario elements per report",
                 x=0.01, y=1.06, ha="left", fontsize=13, fontweight="bold")
    fig.savefig(ROOT / "outputs" / "data_coverage.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return df, score


def results_matrix():
    frames = [pd.read_csv(p) for p in sorted((ROOT / "outputs").glob("*/summary.csv"))]
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    order = ["ground_truth"] + sorted(b for b in df.backend.unique() if b not in ("ground_truth", "rules")) + \
            (["rules"] if "rules" in set(df.backend) else [])
    reports = sorted(df.report_id.unique())
    fig, ax = plt.subplots(figsize=(2.3 * len(order) + 2, 0.7 * len(reports) + 1.6))
    ax.set_xlim(0, len(order)); ax.set_ylim(len(reports), 0)
    for i, r in enumerate(reports):
        for j, b in enumerate(order):
            sel = df[(df.report_id == r) & (df.backend == b)]
            if sel.empty:
                txt, fill, col = "not run", "#f6f5f2", INK2
            else:
                s = sel.iloc[0]
                if s.status != "ok":
                    txt, fill, col = f"✗ {s.status.split(':')[0]}", "#f6f5f2", INK
                else:
                    ok = bool(s.reproduces_report)
                    acc = s.get("field_accuracy")
                    acc_txt = f"  ·  fields {acc:.0%}" if pd.notna(acc) else ""
                    txt = ("✓ reproduces crash" if ok else "✗ no crash in sim") + acc_txt
                    fill, col = ("#2a78d6", "#ffffff") if ok else ("#ecebe7", INK)
            ax.add_patch(plt.Rectangle((j + 0.03, i + 0.06), 0.94, 0.88, color=fill, lw=0))
            ax.text(j + 0.5, i + 0.5, txt, ha="center", va="center", fontsize=8.5, color=col)
    ax.set_xticks([j + 0.5 for j in range(len(order))])
    ax.set_xticklabels([b.replace("ground_truth", "manual (ground truth)").replace("rules", "no-LLM baseline")
                        for b in order])
    ax.xaxis.tick_top()
    ax.set_yticks([i + 0.5 for i in range(len(reports))]); ax.set_yticklabels(reports)
    ax.grid(False); ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.suptitle("Does the generated scenario reproduce the reported crash?", x=0.01, ha="left",
                 fontsize=13, fontweight="bold")
    fig.savefig(ROOT / "outputs" / "results_matrix.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return df


def main():
    (ROOT / "outputs").mkdir(exist_ok=True)
    cov, score = coverage_figure()
    res = results_matrix()
    lines = ["# crash2sim - results summary", "", "## Data coverage (data/coverage.csv)", "",
             cov.assign(coverage=[f"{v:.0%}" for v in score]).to_markdown(index=False), ""]
    if res is not None:
        cols = [c for c in ["backend", "report_id", "status", "scenario_type", "sim_collision",
                            "reproduces_report", "field_accuracy", "impact_speed_ego_kph",
                            "n_assumptions", "llm_seconds"] if c in res]
        lines += ["## Pipeline runs (outputs/*/summary.csv)", "", res[cols].to_markdown(index=False), ""]
    (ROOT / "outputs" / "SUMMARY.md").write_text("\n".join(lines))
    print("wrote outputs/data_coverage.png, outputs/results_matrix.png, outputs/SUMMARY.md")


if __name__ == "__main__":
    main()
