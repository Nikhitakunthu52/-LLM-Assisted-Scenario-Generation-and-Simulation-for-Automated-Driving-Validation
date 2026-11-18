"""Run a scenario in esmini and collect trajectories (+ optional video)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd


def esmini_bin_dir() -> Path:
    d = os.getenv("ESMINI_BIN")
    if d:
        return Path(d)
    exe = shutil.which("esmini")
    if exe:
        return Path(exe).parent
    raise RuntimeError("esmini not found: set ESMINI_BIN to the folder containing esmini and dat2csv")


def _exe(name: str) -> str:
    p = esmini_bin_dir() / (name + (".exe" if os.name == "nt" else ""))
    if not p.exists():
        raise RuntimeError(f"{p} not found")
    return str(p)


def run(xosc: Path, out_dir: Path, dt: float = 0.05) -> dict:
    """Headless run. Returns {'csv': Path, 'log': str, 'collision_time': float|None, 'ok': bool}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dat = out_dir / "sim.dat"
    cmd = [_exe("esmini"), "--headless", "--osc", str(xosc.resolve()), "--fixed_timestep", str(dt),
           "--record", str(dat.resolve()), "--logfile_path", str((out_dir / "esmini_log.txt").resolve())]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    log = p.stdout + p.stderr
    subprocess.run([_exe("dat2csv"), str(dat.resolve())], capture_output=True, text=True, timeout=120)
    csv = dat.with_suffix(".csv")
    errors = [l for l in log.splitlines() if "[error]" in l.lower()]
    m = re.search(r"\[(\d+\.\d+)\] \[info\] ImpactDetected: true", log)
    return {"csv": csv, "log": log, "ok": p.returncode == 0 and csv.exists() and not errors,
            "errors": errors, "collision_time": float(m.group(1)) if m else None}


def load_csv(csv: Path) -> pd.DataFrame:
    return pd.read_csv(csv, skipinitialspace=True)


def record_video(xosc: Path, out_mp4: Path, dt: float = 0.05, size=(960, 540),
                 daylight: bool = True, camera: str = "orbit") -> Path | None:
    """Render with the esmini viewer (needs a display; uses xvfb-run on Linux if available).

    daylight=True renders without the report's lighting/weather so the video is readable;
    the simulation itself (incl. road friction) is unchanged.
    """
    with tempfile.TemporaryDirectory() as tmp:
        src = xosc.resolve()
        if daylight:
            txt = re.sub(r"<GlobalAction>\s*<EnvironmentAction>.*?</GlobalAction>", "", src.read_text(), flags=re.S)
            src = xosc.resolve().with_name(xosc.stem + "_render.xosc")
            src.write_text(txt)
        cmd = [_exe("esmini"), "--window", "0", "0", str(size[0]), str(size[1]), "--osc", str(src),
               "--fixed_timestep", str(dt), "--capture_screen", "--disable_log", "--camera_mode", camera,
               "--follow_object", "0", "--info_text", "0"]
        if os.name != "nt" and not os.getenv("DISPLAY") and shutil.which("xvfb-run"):
            cmd = ["xvfb-run", "-a", "-s", f"-screen 0 {size[0]+100}x{size[1]+100}x24"] + cmd
        subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=600)
        frames = sorted(Path(tmp).glob("screen_shot_*.*"))
        if not frames or not shutil.which("ffmpeg"):
            return None
        ext = frames[0].suffix
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(round(1 / dt)),
                        "-i", str(Path(tmp) / f"screen_shot_%05d{ext}"), "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out_mp4)],
                       capture_output=True, timeout=600)
        if daylight and src != xosc.resolve():
            src.unlink(missing_ok=True)
    return out_mp4 if out_mp4.exists() else None
