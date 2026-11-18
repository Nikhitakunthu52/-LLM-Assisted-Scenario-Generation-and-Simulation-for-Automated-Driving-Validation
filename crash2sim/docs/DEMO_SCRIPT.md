# Nov 20 demo run sheet (about 8 min)

## Before the meeting (Fri morning)
- [ ] `ollama pull llama3.1:8b` on the demo laptop, then run `ollama run llama3.1:8b "hi"` once to warm it up
- [ ] `python run_pipeline.py --backend ollama --video` → check that `outputs/ollama/summary.csv` exists
- [ ] `python make_summary.py` → the results matrix now has an LLM column
- [ ] Open in tabs: `outputs/data_coverage.png`, `outputs/results_matrix.png`,
      `outputs/ollama/CISS_A2/scenario.png`, `outputs/ground_truth/CISS_A2/scenario.mp4`
- [ ] Backup: screen-record steps 3–4 below in case the live run fails

## Flow
1. **Goal (30 s).** Can public crash reports plus an LLM produce runnable driving scenarios? Two weeks, two crash types.
2. **Data (1.5 min)** → `data_coverage.png`.
   CISS is about 80 % usable, the SGO/ADS reports about 50 %. No source gives distances or timing.
3. **Live pipeline (2 min)**
   ```bash
   cat data/reports/CIREN_8392_head_on.json            # REAL NHTSA case: narrative + EDR
   python run_pipeline.py --backend ollama --reports "data/reports/CIREN*.json" --video
   cat outputs/ollama/CIREN_8392/spec.json             # LLM output + its assumptions list
   cat outputs/ollama/CIREN_8392/validation.json       # sim vs EDR impact speeds
   head -30 scenarios/generated/ollama/CIREN_8392.xosc # generated OpenSCENARIO
   ```
4. **Simulation (1.5 min)**: play `outputs/ground_truth/CIREN_8392/scenario.mp4`, then show `scenario.png`.
   Key line: the simulated impact speeds of 70 / 43 km/h match the EDR's 70.6 and the reconstruction's ~41 km/h.
5. **Results (1.5 min)** → `results_matrix.png`. Compare manual, LLM and the keyword baseline. SGO_B2 doesn't reproduce: redacted reports leave the outcome to assumptions.
6. **Learned + next (1 min)**: spec-plus-template beats raw XML; distance/timing is the missing data; next steps are real cases, a model comparison, parameter sweeps and CARLA.

## If something breaks
- Ollama is slow or down → `--backend openai` (API key in `.env`), or show the committed `outputs/`.
- esmini viewer fails → the committed `outputs/ground_truth/*/scenario.mp4` files.
