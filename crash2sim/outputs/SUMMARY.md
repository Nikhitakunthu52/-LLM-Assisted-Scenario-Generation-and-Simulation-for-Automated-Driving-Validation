# crash2sim - results summary

## Data coverage (data/coverage.csv)

| report_id   | source   | crash_type   | road_geometry   | light_weather   | vehicle_types   | ego_speed   | other_speed   | maneuvers   | timing_reaction   | distances_positions   | outcome_impact   | coverage   |
|:------------|:---------|:-------------|:----------------|:----------------|:----------------|:------------|:--------------|:------------|:------------------|:----------------------|:-----------------|:-----------|
| CISS_A1     | CISS     | stated       | stated          | stated          | stated          | stated      | partial       | stated      | partial           | missing               | stated           | 80%        |
| CISS_A2     | CISS     | stated       | partial         | stated          | stated          | stated      | stated        | stated      | partial           | missing               | stated           | 80%        |
| SGO_B1      | SGO      | stated       | partial         | stated          | partial         | partial     | partial       | stated      | missing           | missing               | partial          | 55%        |
| SGO_B2      | SGO      | partial      | partial         | stated          | partial         | stated      | missing       | stated      | missing           | missing               | partial          | 50%        |

## Pipeline runs (outputs/*/summary.csv)

| backend      | report_id   | status   | scenario_type   | sim_collision   | reproduces_report   |   field_accuracy |   impact_speed_ego_kph |   n_assumptions |   llm_seconds |
|:-------------|:------------|:---------|:----------------|:----------------|:--------------------|-----------------:|-----------------------:|----------------:|--------------:|
| ground_truth | CISS_A1     | ok       | rear_end        | True            | True                |           nan    |                   47.8 |               4 |             0 |
| ground_truth | CISS_A2     | ok       | ltap_od         | True            | True                |           nan    |                   32.6 |               3 |             0 |
| ground_truth | SGO_B1      | ok       | rear_end        | True            | True                |           nan    |                   40   |               4 |             0 |
| ground_truth | SGO_B2      | ok       | ltap_od         | False           | False               |           nan    |                  nan   |               3 |             0 |
| rules        | CISS_A1     | ok       | rear_end        | False           | False               |             0.82 |                  nan   |               2 |             0 |
| rules        | CISS_A2     | ok       | ltap_od         | False           | False               |             0.91 |                  nan   |               1 |             0 |
| rules        | SGO_B1      | ok       | rear_end        | True            | True                |             0.82 |                   40   |               2 |             0 |
| rules        | SGO_B2      | ok       | ltap_od         | False           | False               |             0.73 |                  nan   |               1 |             0 |
