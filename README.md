# Atlas: LLM-based Analyzer for State Independence Patterns in Web API Applications

## Installation

### With venv + pip

Requires Python 3.11 or higher.


```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

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

---

## Datasets

Our datasets (the full dataset, the validation dataset, and the agent-generated tests for applications in the full dataset) are published on [Zenodo](https://doi.org/10.5281/zenodo.21185073).

Please download `full.zip`, `validation.zip` and `agent-generated.zip` to `./datasets`. Run `datasets/unzip_datasets.sh` to unzip them.

```bash
bash ./datasets/unzip_datasets.sh
```

## Running Atlas on an application

With the virtual environment activated, using the following command to run Atlas on a web API application.

```bash
angelica label-units \
  --config ./coaster_label/config/coaster_config.py \
  --project-path "root directory of the application, e.g., datasets/validation/catwatch" \
  --analysis-provider ./coaster_label/config/cldk_analysis_provider.py \
  --db labels.db \
  --index-dir vector_index \
  --clear-cache \
  --analysis-timeout 600 \
  --out results.json
```

Use `angelica label-units --help` to go through all the options.