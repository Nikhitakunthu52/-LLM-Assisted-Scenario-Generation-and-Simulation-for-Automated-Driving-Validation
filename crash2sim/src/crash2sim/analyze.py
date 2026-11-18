"""Metrics + figures for a simulated scenario, and LLM-vs-ground-truth scoring."""
from __future__ import annotations

import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import simulate
from .build import ASSETS

# Palette (validated categorical slots 1-2 + neutral inks)
EGO_C, OTHER_C = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
ROAD_C, MARK_C = "#d9d8d3", "#ffffff"

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "lines.linewidth": 2,
})


# ---------------------------------------------------------------- metrics
def metrics(csv: Path, other: str, collision_time: float | None) -> dict:
    d = simulate.load_csv(csv)
    e = d[d.name == "Ego"].set_index("time")
    o = d[d.name == other].set_index("time")
    t = e.index.intersection(o.index)
    e, o = e.loc[t], o.loc[t]
    dist = np.hypot(e.x - o.x, e.y - o.y)
    # first moment ego starts braking (speed drops > 0.3 m/s below its initial value)
    v0 = e.speed.iloc[0]
    brake_idx = e.index[e.speed < v0 - 0.3]
    res = {
        "sim_collision": collision_time is not None,
        "collision_time_s": collision_time,
        "min_center_distance_m": round(float(dist.min()), 2),
        "ego_brake_start_s": round(float(brake_idx[0]), 2) if len(brake_idx) else None,
        "duration_s": round(float(t.max()), 2),
    }
    if collision_time is not None:
        tc = t[np.argmin(np.abs(t - collision_time))]
        res["impact_speed_ego_kph"] = round(float(e.speed.loc[tc]) * 3.6, 1)
        res["impact_speed_other_kph"] = round(float(o.speed.loc[tc]) * 3.6, 1)
        if other == "Lead":
            res["delta_v_kph"] = round(abs(res["impact_speed_ego_kph"] - res["impact_speed_other_kph"]), 1)
        elif other == "Other":
            res["closing_speed_kph"] = round(res["impact_speed_ego_kph"] + res["impact_speed_other_kph"], 1)
    return res


# ---------------------------------------------------------------- road outline
_road_cache: dict[str, list[np.ndarray]] = {}


def road_lines(xodr: str) -> list[np.ndarray]:
    if xodr in _road_cache:
        return _road_cache[xodr]
    out = Path("/tmp") / f"crash2sim_{Path(xodr).stem}_track.csv"
    try:
        subprocess.run([simulate._exe("odrplot"), str(ASSETS / "xodr" / xodr), str(out)],
                       capture_output=True, timeout=60)
        lines, cur = [], []
        for row in out.read_text().splitlines():
            if row.startswith("lane"):
                if cur:
                    lines.append(np.array(cur))
                cur = []
            else:
                vals = row.split(",")
                cur.append([float(vals[0]), float(vals[1])])
        if cur:
            lines.append(np.array(cur))
    except Exception:
        lines = []
    _road_cache[xodr] = lines
    return lines


# ---------------------------------------------------------------- figures
def scenario_figure(csv: Path, other: str, spec: dict, m: dict, title: str, out_png: Path) -> Path:
    d = simulate.load_csv(csv)
    e, o = d[d.name == "Ego"], d[d.name == other]
    other_label = {"Lead": "Lead vehicle", "NPC": "Turning vehicle", "Other": "Encroaching vehicle"}[other]
    fig = plt.figure(figsize=(12, 4.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.35, 1, 1], wspace=0.28)

    # 1) top-down trajectories
    ax = fig.add_subplot(gs[0])
    xodr = "fabriksgatan.xodr" if spec["scenario_type"] == "ltap_od" else "straight_500m.xodr"
    for ln in road_lines(xodr):
        ax.plot(ln[:, 0], ln[:, 1], color=ROAD_C, lw=1, zorder=1)
    ax.plot(e.x, e.y, color=EGO_C, lw=2, zorder=3)
    ax.plot(o.x, o.y, color=OTHER_C, lw=2, zorder=3)
    for df, c in ((e, EGO_C), (o, OTHER_C)):
        ax.scatter(df.x.iloc[0], df.y.iloc[0], s=40, color=c, edgecolor=SURF, linewidth=2, zorder=4)
    ct = m.get("collision_time_s")
    if ct is not None:
        ei = e.iloc[(e.time - ct).abs().argmin()]
        ax.scatter(ei.x, ei.y, s=140, marker="X", color=INK, edgecolor=SURF, linewidth=2, zorder=5)
        ax.annotate("impact", (ei.x, ei.y), xytext=(8, 8), textcoords="offset points", color=INK, fontsize=9)
    allx = pd.concat([e.x, o.x]); ally = pd.concat([e.y, o.y])
    pad = 15
    ax.set_xlim(allx.min() - pad, allx.max() + pad)
    ax.set_ylim(ally.min() - pad, ally.max() + pad)
    if spec["scenario_type"] in ("rear_end", "head_on"):
        ax.set_ylim(ally.mean() - 25, ally.mean() + 25)
    else:
        ax.set_aspect("equal", adjustable="box")
    ax.set_title("Top-down path (dots = start)")
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")

    # 2) speed over time
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(e.time, e.speed * 3.6, color=EGO_C)
    ax2.plot(o.time, o.speed * 3.6, color=OTHER_C)
    vmax = max(e.speed.max(), o.speed.max()) * 3.6
    ax2.set_ylim(0, vmax * 1.25)
    hi_ego = e.speed.iloc[0] >= o.speed.iloc[0]
    ax2.text(e.time.iloc[0], e.speed.iloc[0] * 3.6 + (2 if hi_ego else -2), "Ego", color=INK, fontsize=9,
             va="bottom" if hi_ego else "top")
    ax2.text(o.time.iloc[0], o.speed.iloc[0] * 3.6 + (-2 if hi_ego else 2), other_label, color=INK, fontsize=9,
             va="top" if hi_ego else "bottom")
    if m.get("ego_brake_start_s") is not None:
        ax2.axvline(m["ego_brake_start_s"], color=INK2, lw=1, ls="--")
        ax2.text(m["ego_brake_start_s"], ax2.get_ylim()[1] * 0.97, " ego brakes", color=INK2, fontsize=8, va="top")
    if ct is not None:
        ax2.axvline(ct, color=INK, lw=1)
        ax2.text(ct, ax2.get_ylim()[1] * 0.85, " impact", color=INK, fontsize=8, va="top")
    ax2.set_title("Speed (km/h)"); ax2.set_xlabel("time (s)")

    # 3) distance over time
    ax3 = fig.add_subplot(gs[2])
    t = e.time.values
    ov = o.set_index("time").reindex(t)
    dist = np.hypot(e.x.values - ov.x.values, e.y.values - ov.y.values)
    ax3.plot(t, dist, color=INK2)
    ax3.set_ylim(bottom=0)
    ax3.set_title("Distance between vehicles (m)"); ax3.set_xlabel("time (s)")
    if ct is not None:
        ax3.axvline(ct, color=INK, lw=1)

    # legend (identity never color-alone: also labeled in the speed panel)
    from matplotlib.lines import Line2D
    fig.legend([Line2D([], [], color=EGO_C), Line2D([], [], color=OTHER_C)], ["Ego", other_label],
               loc="upper right", ncol=2, frameon=False, bbox_to_anchor=(0.99, 1.0))
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold")
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_png


# ---------------------------------------------------------------- LLM vs ground truth
def _close(a, b, rel=0.15, abs_=5.0):
    if a is None or b is None:
        return a == b
    return abs(float(a) - float(b)) <= max(abs_, rel * abs(float(b)))


FIELDS = [
    ("scenario_type", lambda s: s["scenario_type"], "exact"),
    ("light", lambda s: s["environment"]["light"], "exact"),
    ("weather", lambda s: s["environment"]["weather"], "exact"),
    ("surface", lambda s: s["environment"]["surface"], "exact"),
    ("ego_vehicle", lambda s: s["ego"]["vehicle"], "exact"),
    ("ego_speed_kph", lambda s: s["ego"]["speed_kph"], "num"),
    ("ego_reacts", lambda s: s["ego"]["reacts"], "exact"),
    ("other_vehicle", lambda s: s["other"]["vehicle"], "exact"),
    ("other_maneuver", lambda s: s["other"]["maneuver"], "exact"),
    ("other_speed_kph", lambda s: s["other"]["speed_kph"], "num"),
    ("collision_reported", lambda s: s["collision_reported"], "exact"),
]


def score(pred: dict, truth: dict) -> dict:
    truth = {k: v for k, v in truth.items() if k != "validation_targets"}
    out = {}
    for name, get, kind in FIELDS:
        p, t = get(pred), get(truth)
        out[name] = bool(_close(p, t) if kind == "num" else p == t)
    out["accuracy"] = round(sum(out.values()) / len(FIELDS), 2)
    return out
