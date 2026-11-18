# Getting crash2sim demo-ready by Friday, Nov 20

Branch: `nov20-demo` (main is untouched until you merge).
Order: **1 Setup → 2 Smoke test → 3 Replace data → 4 Run LLM → 5 Commit → 6 Merge + go public.**

---

## 1. Setup (once per laptop, ~15 min)

```bash
git clone https://github.com/Nikhitakunthu52/-LLM-Assisted-Scenario-Generation-and-Simulation-for-Automated-Driving-Validation.git capstone
cd capstone
git checkout nov20-demo
cd crash2sim

python -m venv .venv
# Mac/Linux:  source .venv/bin/activate
# Windows:    .venv\Scripts\activate
pip install -r requirements.txt
```

**esmini (simulator; runs every scenario)**
- Mac/Linux: `./scripts/setup_esmini.sh` downloads esmini's **demo package** (simulator + 3D cars and road scenes, ~150 MB).
- Windows: download `esmini-demo_Windows.zip` from https://github.com/esmini/esmini/releases and unzip it into `crash2sim/tools/`.
- The 3D models are found automatically in `<esmini>/resources/models`. Without them, videos show boxes, but the results are the same.

**Ollama (LLM)**: install from https://ollama.com, then:
```bash
ollama pull llama3.1:8b          # ~5 GB; needs ~8 GB free RAM. Smaller: qwen2.5:3b
```

**.env**
```bash
cp .env.example .env             # Windows: copy .env.example .env
```
Set `ESMINI_BIN` to the folder that contains `esmini` / `esmini.exe`, for example
`ESMINI_BIN=./tools/esmini-demo/bin` or `ESMINI_BIN=C:\Users\you\capstone\crash2sim\tools\esmini-demo\bin`.

## 2. Smoke test (2 min)

```bash
pytest -q                                          # 4 passed
python run_pipeline.py --backend ground_truth --video
```
You should see 5 reports with `reproduces report: True/False` and new files in `outputs/ground_truth/`.
Open one scenario in esmini's viewer (mouse to orbit; `k` changes the camera, Tab switches vehicles):
`tools/esmini-demo/bin/esmini --window 60 60 1024 576 --path tools/esmini-demo/resources/models --osc scenarios/generated/ground_truth/CIREN_8392.xosc`

## 3. Replace the placeholder crash reports (Data team, Thu)

The 4 files in `data/reports/` are **synthetic placeholders**. Replace them with 2 real cases of each type: 1 rear-end + 1 left turn across path per type.

**Type A: CISS / CIREN** (https://crashviewer.nhtsa.dot.gov). Use the export, not copy-paste:
1. Open a case (rear-end; left turn across path / opposite direction; head-on). Prefer cases with EDR data.
2. Export the case to Excel and save it in `data/raw/` (gitignored: exports contain medical and personal data).
3. Convert it: `python scripts/ciren_to_report.py data/raw/<export>.xlsx --id CISS_A1`
   This writes `data/reports/CISS_A1.json` with the narrative (personal details removed), the coded fields and the EDR series.
   Delete the placeholder file it replaces.
4. Example already done: `CIREN_8392` (head-on), from the export Bala uploaded.

**Type B: Standing General Order** (nhtsa.gov → Standing General Order on Crash Reporting → ADS incident report CSV)
1. Open the CSV and filter `Crash With` / `SV Pre-Crash Movement` / `CP Pre-Crash Movement` for one rear-end and one left-turn case. Prefer rows where `Narrative` is not fully redacted.
2. Copy `Narrative` and the relevant columns into the JSON.

**File format** (keep the file names, or keep `report_id` matching the file in `data/ground_truth/`):
```json
{
  "report_id": "CISS_A1",
  "source_type": "CISS in-depth investigation",
  "synthetic": false,
  "case_id": "<real CISS case number or SGO Report ID>",
  "narrative": "...",
  "coded_fields": { "light_condition": "...", "speed_limit_kph": 72 }
}
```

Then, for each new report:
- **Ground truth:** edit `data/ground_truth/<report_id>.json` by hand (what the team believes the scenario is). This is the manual "recreate the scenario from the data" step, and it's what the LLM gets scored against.
- **Coverage:** update that row of `data/coverage.csv` (`stated` / `partial` / `missing` per column).
- Remove the "placeholder" warning in `README.md` and update the two "Finding" sections with the new numbers.

Optional: add `"validation_targets"` to the ground truth (see `data/ground_truth/CIREN_8392.json`) so the pipeline compares simulated impact speeds against EDR values.

Check: `python run_pipeline.py --backend ground_truth` → does each one reproduce the crash? If not, adjust the assumptions in the ground truth file (gap, reaction time) and note why. That's a finding, too.

## 4. Run the LLM (Thu evening)

```bash
ollama serve                     # if Ollama isn't already running in the background
python run_pipeline.py --backend ollama --video
python run_pipeline.py --backend rules
python make_summary.py
```
- Look at `outputs/ollama/summary.csv`, plus each `spec.json` and its `assumptions`.
- `schema_invalid` or `extract_failed` → try `--model qwen2.5:7b`, or rerun. Model output can vary.
- Optional extra column: `python run_pipeline.py --backend ollama --model qwen2.5:7b`, then `make_summary.py` again.
- API instead of local: fill `LLM_API_KEY` etc. in `.env`, then run `--backend openai`.

## 5. Commit results

```bash
cd ..                            # repo root
git add crash2sim
git commit -m "Real crash reports + LLM results for Nov 20 demo"
git push
```
`.gitignore` keeps `.env`, `tools/` and the large `sim.dat` recordings out. Commit `outputs/` (PNGs, MP4s, CSVs) so reviewers can see results without running anything.

## 6. Friday morning: merge + make public

1. Open a pull request `nov20-demo → main` on GitHub and merge it.
2. **Before switching to public:**
   - Get Dr. Shao's OK (NDA/IP).
   - **Remove the Google Drive link from the root `README.md`.** Otherwise it becomes public too.
   - Check that there's no Bosch material and no `.env` in the repo: `git ls-files | grep -iE "\.env$|bosch"` should print nothing.
3. GitHub → Settings → General → Danger Zone → Change visibility → Public.
4. Dry run with `docs/DEMO_SCRIPT.md`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `esmini not found` | `ESMINI_BIN` in `.env` must point to the folder with the `esmini` executable |
| `Connection refused localhost:11434` | Ollama isn't running: start the app or run `ollama serve` |
| LLM is very slow | use `qwen2.5:3b`, or `--backend openai` with an API key |
| `video: not rendered` | needs a display (normal laptop) and ffmpeg (`brew install ffmpeg` / `winget install ffmpeg`) |
| Mac: "esmini can't be opened" | `xattr -dr com.apple.quarantine tools/esmini-demo` |
| videos show boxes, not cars | models not found: set `ESMINI_MODELS=<esmini-demo>/resources/models` in `.env` |
| `sim_failed` | open the `.xosc` in esmini with a window; `outputs/<backend>/<id>/esmini_log.txt` has the error |
