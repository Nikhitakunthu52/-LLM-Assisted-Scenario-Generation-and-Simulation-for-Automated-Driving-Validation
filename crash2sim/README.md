# crash2sim: Crash reports → LLM → OpenSCENARIO → esmini

UGA Engineering Capstone (Fall 2026), part of the Bosch-sponsored project *LLM-Assisted Scenario Generation and Simulation for Automated Driving Validation*.
**Two-week milestone demo, Nov 20, 2026.**

The pipeline takes a written crash report (narrative plus coded fields), uses an LLM to extract a small, typed **scenario spec**, renders that spec into an **OpenSCENARIO 1.2** file from a template, and runs it in **esmini**. It then checks whether the simulation reproduces the reported crash.

```mermaid
flowchart LR
  A[Crash report<br/>narrative + coded fields] --> B[LLM<br/>Ollama / API]
  B --> C[Scenario spec JSON<br/>schema-validated]
  C --> D[Sanitize<br/>fill + log assumptions]
  D --> E[Template → .xosc]
  E --> F[esmini headless run]
  F --> G[Metrics<br/>collision, impact speed]
  F --> H[Plots + video]
  G --> I{Reproduces<br/>the report?}
```

**Why a spec and not raw XML?** LLMs write invalid OpenSCENARIO easily. Here the LLM only fills about 15 typed fields, which are checked against a JSON Schema (`src/crash2sim/schema.py`). Templates (`templates/`) guarantee that the generated `.xosc` is valid and runnable. Every value the LLM had to guess is recorded in `assumptions`.

---

## Quick start

```bash
git clone <this repo> && cd crash2sim
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
./scripts/setup_esmini.sh                              # esmini demo package: simulator + 3D models
cp .env.example .env                                   # set ESMINI_BIN

# LLM (local, free): install Ollama from https://ollama.com, then
ollama pull llama3.1:8b

python run_pipeline.py --backend ollama --video        # LLM-generated scenarios
python run_pipeline.py --backend ground_truth --video  # hand-built reference scenarios
python run_pipeline.py --backend rules                 # no-LLM baseline
python make_summary.py                                 # comparison figures + outputs/SUMMARY.md
pytest -q
```

Other LLMs: `--model qwen2.5:7b`, or `--backend openai` with any OpenAI-compatible endpoint configured in `.env` (OpenAI, Groq, Together, a Hugging Face Inference Endpoint, vLLM).

Each report produces:

| Path | What it is |
|---|---|
| `outputs/<backend>/<report>/spec_raw.json` | raw LLM output |
| `outputs/<backend>/<report>/spec.json` | validated + sanitized spec |
| `scenarios/generated/<backend>/<report>.xosc` | OpenSCENARIO file (opens in esmini) |
| `outputs/<backend>/<report>/scenario.png` | top-down path, speed and distance over time |
| `outputs/<backend>/<report>/scenario.mp4` | esmini render (`--video`) |
| `outputs/<backend>/<report>/metrics.json` | collision, impact speeds, brake onset, min distance |
| `outputs/<backend>/summary.csv` | one row per report |

To watch a scenario interactively: `$ESMINI_BIN/esmini --window 60 60 1024 576 --osc scenarios/generated/ground_truth/CISS_A2.xosc`

---

## Scenarios in scope

| Template | Crash type | Road | Ego | Other vehicle |
|---|---|---|---|---|
| `rear_end` | Lead vehicle decelerating or stopped | `straight_500m` | follows and strikes | brakes at t = 2 s |
| `ltap_od` | Left turn across path, opposite direction | `fabriksgatan` (4-leg intersection) | goes straight | turns left, timed to the conflict point |
| `head_on` | Lane departure into oncoming traffic | `straight_500m` (2 lanes, opposite directions) | stays in its lane, brakes | drifts over the center line, brakes at a set time to collision (from EDR) |

Ego braking is triggered by **hazard onset + reaction time**: the lead vehicle's brake event, a time to collision under 4 s, the turning vehicle getting within 25–35 m, or the oncoming vehicle starting to drift. Lighting, weather and surface go into an `EnvironmentAction`, and road friction is scaled.

## Data

| Type | Source | Why |
|---|---|---|
| A: in-depth investigation | NHTSA **CISS** case viewer (crashviewer.nhtsa.dot.gov) | narrative, EDR speeds, scaled scene diagrams |
| B: ADS incident report | NHTSA **Standing General Order 2021-01** CSVs | real automated-vehicle crashes; narratives often redacted |

**Real case: `CIREN_8392`** (NHTSA CIREN 3-C4-2017-002, head-on, 2017). Converted from a Crash Viewer export with
`python scripts/ciren_to_report.py data/raw/<export>.xlsx --id CIREN_8392`. The converter keeps only crash, roadway and vehicle fields plus EDR pre-crash data. Occupant, medical and demographic data are dropped, and raw exports in `data/raw/` are gitignored.

> ⚠️ **The 4 `CISS_*` / `SGO_*` reports are still illustrative placeholders** (`"synthetic": true`). Replace them with real cases (see `docs/FRIDAY_GUIDE.md`) before the results are cited.

### Finding 1: in-depth reports have enough detail; ADS reports mostly don't

![data coverage](outputs/data_coverage.png)

- CISS-style reports cover about **80 %** of the scenario elements. Speeds come from EDR data, and the maneuvers and environment are stated.
- SGO reports cover **50–55 %**. Narratives are redacted, and there are no distances or timing.
- **No report type gives initial distances or positions.** The simulation always has to assume them.

### Finding 2: a real case with EDR data can be reproduced quantitatively

CIREN_8392: a Ford Focus drifts over the center line at night and hits an oncoming Honda Civic. After setting the Focus speed and brake timing from its EDR, and assuming the Civic's speed and reaction time:

| Check | Simulation | Report |
|---|---|---|
| Focus (encroaching) impact speed | **70.0 km/h** | 70.6 km/h (EDR) |
| Focus brake onset before impact | 1.5 s | 1.5 s (EDR) |
| Civic impact speed | **42.6 km/h** | ~41 km/h (from delta-V + masses) |
| Closing speed | **112.6 km/h** | ~112 km/h (ΔV₁ + ΔV₂, momentum) |

The no-LLM baseline also "reproduces" this crash, but at a **177 km/h** closing speed. A yes/no crash match isn't enough; impact speeds are the real test (`outputs/<backend>/CIREN_8392/validation.json`).
Data quality note: the narrative says the limit is 80 km/h (55 mph), but 55 mph is 89 km/h, which is what the coded field says.

### Finding 3: the simulation reproduces the crash when the timing assumptions are right

![results matrix](outputs/results_matrix.png)

- With hand-built specs, 4 of 5 scenarios reproduce the reported crash. In **CISS_A2** the simulated impact speed is **32.6 km/h vs. 32 km/h** on the EDR.
- **SGO_B2** (fully redacted) does *not* reproduce: with the assumed values, the ADS stops in time. This is the key limitation: when the report lacks timing, the outcome depends on assumptions.
- The no-LLM keyword baseline gets 73–91 % of the fields right but reproduces only 2 of 5 crashes, one of them at unrealistic speeds. It can't infer reaction behavior or headway. **That gap is what the LLM column has to close.**

## Repo layout

```
run_pipeline.py          CLI: report → spec → xosc → esmini → metrics/figures
make_summary.py          cross-backend figures + outputs/SUMMARY.md
src/crash2sim/
  schema.py              JSON Schema for the scenario spec + sanitize()
  extract.py             LLM backends (ollama, openai-compatible) + rules baseline; prompt
  build.py               spec → .xosc via templates
  simulate.py            esmini runner, dat→csv, video capture
  analyze.py             metrics, figures, scoring against ground truth
templates/               OpenSCENARIO templates with {{placeholders}}
sim_assets/              esmini road networks + catalogs (MPL-2.0, see LICENSE file there)
data/reports/            crash reports (JSON)
data/raw/                raw Crash Viewer exports (gitignored - personal data)
scripts/ciren_to_report.py   CIREN/CISS .xlsx export -> report JSON (privacy allowlist)
data/ground_truth/       hand-built specs (manual recreation)
data/coverage.csv        per-report data coverage assessment
tests/                   pytest
```

## Limitations and next steps

- 3 crash types. Next candidates: cut-in, pedestrian crossing, straight crossing path.
- No crash physics after impact (vehicles are stopped). Initial distances are always assumed.
- Videos are rendered by esmini's own 3D viewer, with esmini's car and road models (from the demo package `setup_esmini.sh` downloads). Without the models, esmini falls back to boxes; the simulation results are identical either way. Videos render in daylight for readability.
- Next: real CISS/SGO cases, LLM model comparison (llama3.1 vs. qwen2.5 vs. an API model), automatic sweeps over assumed parameters (reaction time, gap) to show which assumptions decide the outcome, and CARLA export.

## Team

Nikhita Kunthu (lead), Joshua Oh: data processing · Marco Walther, Ansley Purdue: simulation & visualization
Supervisor: Dr. Yunli Shao (UGA) · Sponsor: Dr. Jian Tang (Bosch)

Simulator: [esmini](https://github.com/esmini/esmini) (MPL-2.0). Files under `sim_assets/` come from esmini's `resources/`.
