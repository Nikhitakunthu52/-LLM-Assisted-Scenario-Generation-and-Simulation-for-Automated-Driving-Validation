# CIREN crash reconstructions (cases 11 and 189)

Two real crashes from NHTSA's **CIREN** database, rebuilt by hand as esmini scenarios
(OpenSCENARIO 1.1 + OpenDRIVE). Each case has its own road, and each vehicle follows a
time-stamped path, so the impact happens at the reported location, heading and speed.

These were built separately from the LLM pipeline in `crash2sim/`. They can serve as
**ground-truth references** for real (non-synthetic) cases.

| Case | NHTSA case | What happens | Length | Impact |
|---|---|---|---|---|
| [11](https://crashviewer.nhtsa.dot.gov/ciren/details/11) | 3-C4-2017-002 | Head-on. A 2014 Ford Focus (red, westbound) drifts across the double yellow line into a 2010 Honda Civic (blue, eastbound). Straight 3-lane road, 80 km/h limit, 4% grade. | 12.5 s | t = 9.0 s, ~55 km/h each |
| [189](https://crashviewer.nhtsa.dot.gov/ciren/details/189) | 3-C1-2018-032 | Run-off-road. The driver of a 2013 Ford F-150 falls asleep on a right-hand curve, drifts off the left side and hits a concrete overpass support. The path is driven by the EDR speed and steering record. | 8.0 s | t = 5.0 s, ~76 km/h |

## Files

| File | What it is |
|---|---|
| `ciren_caseNN.xosc` | The scenario. Open this one in esmini. |
| `ciren_caseNN.xodr` | The road it runs on. It must stay in the same folder as the `.xosc`. |
| `ciren_caseNN.py` | The script that generated both files. It lists every value taken from the case and every assumption. |

## Run a case

You need the **esmini demo package** (`esmini-demo_<OS>.zip` from
[esmini releases](https://github.com/esmini/esmini/releases)), because it includes the
3D car models in `resources/models/`. The scenarios look for those models at
`../models/`, and `--path` tells esmini where they actually are.

**Windows (PowerShell):**

```powershell
cd crash2sim\ciren_reconstructions
$ESMINI = "C:\path\to\esmini-demo"          # the folder that contains bin\esmini.exe

& "$ESMINI\bin\esmini.exe" --window 60 60 1280 720 --trail_mode 1 --path "$ESMINI\resources\models" --osc ciren_case11.xosc
& "$ESMINI\bin\esmini.exe" --window 60 60 1280 720 --trail_mode 1 --path "$ESMINI\resources\models" --osc ciren_case189.xosc
```

**Linux / macOS:**

```bash
cd crash2sim/ciren_reconstructions
ESMINI=/path/to/esmini-demo

$ESMINI/bin/esmini --window 60 60 1280 720 --trail_mode 1 --path $ESMINI/resources/models --osc ciren_case11.xosc
```

If `ESMINI_BIN` is already set for the pipeline (see `../.env.example`), use
`--path "$ESMINI_BIN/../resources/models"`. Without the models, esmini still runs
the scenario, but the vehicles won't have their car models.

**Alternative:** copy both the `.xosc` and the `.xodr` into `esmini-demo/resources/xosc/`.
Then `--path` isn't needed, because `../models/` resolves on its own.

### In the viewer

| Key | Action |
|---|---|
| Space | Pause / resume (pause at the impact to inspect it) |
| Tab | Move the camera to the next vehicle |
| j | Cycle the trail display (none, dots, lines, both) |
| 1–9 | Camera modes |
| Esc | Quit |

Mouse: left drag rotates, right drag zooms, middle drag pans.

### Headless check (no window)

```powershell
& "$ESMINI\bin\esmini.exe" --headless --fixed_timestep 0.05 --osc ciren_case11.xosc
```

The log should show the collision condition firing (`V1_hits_V2` for case 11 at 9.0 s,
`Truck_hits_support` for case 189 at 5.0 s), followed by `Closing`. The warning
`Parameter SetAction deprecated from OSC 1.2` is expected and harmless.

## Regenerate a scenario

Edit the constants at the top of the script, then run it inside this folder. It
overwrites the `.xosc` and `.xodr` next to it.

```bash
python ciren_case11.py                                      # standard library only
pip install openpyxl
python ciren_case189.py CrashExport-189-11-20-2026.xlsx     # needs the CIREN case export
```

Case 189 reads its EDR data (speed, steering, throttle, brake) from the case's Excel
export from the CIREN case viewer. That export is **not** in this repo, so download it
first. Case 11 needs no input file, because its values are written into the script.

## What is real and what is assumed

Both scripts list their sources and assumptions in their docstrings. In short:

- **Case 11.** From the case: road layout, speed limit, grade, the vehicles and their
  sizes, headings at impact, and rest positions. Assumed: both vehicles at 80 km/h
  beforehand, the timing of the drift and of braking (0.7 g), impact speeds of ~55 km/h
  (chosen to be consistent with the reported 52 km/h delta-V), and post-impact motion.
- **Case 189.** From the case: the 5 s EDR record, road type, the truck's dimensions,
  the impact location (CDC 12FLAW06) and the rest heading. Assumed: a 20:1 steering
  ratio with a kinematic bicycle model, shoulder widths, and post-impact motion. The
  curve radius (492 m) is *solved*, so that the EDR-driven path reaches the support
  at the moment of impact.
- **Models.** The demo package has no pickup truck or concrete pier. The F-150 is
  shown as `car_red` and the support as a box, each scaled to its real dimensions.
