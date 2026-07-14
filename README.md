# Atlas: LLM-based Analyzer for State Independence Patterns in Web API Applications

## Installation

### With venv + pip

Requires Python 3.11 or higher.


```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```


## Environment variables

Copy the example file:

```bash
cp .env.example .env
```

Set at minimum:

- API_KEY – LLM provider API key
- BASE_URL – provider base URL

Optional overrides:

- LLM_MODEL – default: openai/gpt-4o
- EMBEDDINGS_MODEL – default: text-embedding-3-small
- LABELER_A_MODEL, LABELER_A_MODEL, ADJUDICATOR_MODEL

In our experiments, we used OpenRouter as the API provider.


## Datasets

Our datasets (the full dataset, the validation dataset, and the agent-generated tests for applications in the full dataset) are published on [Zenodo](https://doi.org/10.5281/zenodo.21185073).

Please download `full.zip`, `validation.zip` and `agent-generated.zip` to `./datasets`. Run `datasets/unzip_datasets.sh` to unzip them.

```bash
bash ./datasets/unzip_datasets.sh
```

Under `datasets/agent-prompts` are the prompts we used to generate tests for applications using Claude Code.

## Running Atlas

### Running one application

With the virtual environment activated, using the following command to run Atlas on a web API application.

```bash
atlas label-units \
  --config ./src/coaster_label/config/coaster_config.py \
  --project-path "root directory of the application, e.g., datasets/validation/catwatch" \
  --analysis-provider ./src/coaster_label/config/cldk_analysis_provider.py \
  --db labels.db \
  --index-dir vector_index \
  --clear-cache \
  --analysis-timeout 600 \
  --out results.json
```

For example, to run Atlas on `catwatch`:
```bash
atlas label-units --config ./src/coaster_label/config/coaster_config.py --project-path datasets/validation/catwatch --analysis-provider ./src/coaster_label/config/cldk_analysis_provider.py --db labels.db --index-dir vector_index --clear-cache --analysis-timeout 600 --out results/atlas_validation_runs/catwatch.json
```

Use `atlas label-units --help` to go through all the options.

### Running on the validation dataset

The following command will run Atlas on each application in the validation dataset (`datasets/validation`), and the outputs will be saved at `results/atlas_validation_runs/<app_name>.json`.
```bash
bash scripts/run_atlas_validation.sh
```

### Running on the full dataset

```bash
bash scripts/run_atlas_full.sh
```
The outputs go under `results/atlas_full_runs/<app_name>.json`.


### Running on the agent-generated tests

```bash
bash scripts/run_atlas_agent_generated.sh
```
The outputs go under `results/atlas_agent_generated_runs/<app_name>.json`.

## Empirical results

The empirical results are placed under directory `results`. The labeling results on the validation dataset are placed under `results/labels_validation_dataset`, and the labeling results on the full dataset are placed under `results/labels_validation_dataset`.

The spreadsheet `results/validation_dataset.xlsx` contains the verified results on the validation dataset. 

### RQ1

To calculate the prevalence of API integration tests in the validation dataset (Table II in the paper), run the following script.
```bash
python ./results/scripts/count_validation_integration_tests.py
```

To calculate the prevalence of API integration tests in the full dataset (Table III in the paper), run the following script.
```bash
python ./results/scripts/count_full_dataset_integration_tests.py
```

### RQ2

To find the cases of state independence in the validation dataset (12 tests as in Section V), run the following script.
```bash
python results/scripts/find_validation_required_but_not_present.py
```
The found cases and a summary are saved in `results/required_but_not_present`.

To find the cases of state independence in the full dataset (14 tests as in Section V), run the following script.
```bash
python results/scripts/results/scripts/find_full_dataset_required_but_not_present.py
```
The found cases and a summary are saved in `results/required_but_not_present_full_dataset`.

### RQ3

To calculate the labeling accuracy on the validation dataset (Table IV in the paper), run the following script. The results will be printed to stdout.
```bash
python ./results/scripts/analyze_validation_label_accuracy.py
```

To generate the heatmap for patterns used in the validation dataset (Figure 5 and 6), run the following script. The figures will be saved to `/home/rkh/26summer/atlas_artifact/results/RQ3/heatmaps`.
```bash
python results/scripts/RQ3/patterns_heatmap_location_side_by_side.py
```

To generate the alluvial graphs for patterns used in the validation dataset (Figure 7), run the following script. The figures will be saved to `results/RQ3/alluvial`.
```bash
python ./results/scripts/RQ3/patterns_alluvial.py --min-percent 1.0
```

To generate the alluvial graphs for patterns used in the full dataset (Figure 8), run the following script. The figures will be saved to `results/RQ3/full_dataset_alluvial`.
```bash
python ./results/scripts/RQ3/analyze_json_patterns_alluvial.py  --labels-dir results/labels_full_dataset --output-dir results/RQ3/full_dataset_alluvial --location-min-percent 1 --mechanism-min-percent 1
```

### RQ4

The labeling results on the agent-generated tests are placed in `results/agent_labels`. Note that we have results for 44 out of the 50 applications because the agent did not generate any API-level integration tests for the remaining 6 applications.

To generate the alluvial graphs for patterns used in the agent-generated tests (Figure 9), run the following command. The figures will be saved to `results/RQ4`.
```bash
python ./results/scripts/RQ3/analyze_json_patterns_alluvial.py --labels-dir results/agent_labels --output-dir results/RQ4/
```