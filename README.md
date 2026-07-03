# ✿ 𝓐𝓷𝓰𝓮𝓵𝓲𝓬𝓪 ✿: Library for Agent-based Labeling

This project provides a **library and CLI** for building **agentic labeling systems** with:

- Multiple independent angelicas
- Optional adjudication on disagreement
- Persistent storage of documents and labels
- Retrieval-augmented prompting via embeddings
- Support static analysis using CLDK
- Agreement metrics (rolling Cohen's kappa)
- **🆕 Enhanced vector matching with confidence scores**
- **🆕 Automatic pattern learning for unmatched cases**
- **🆕 Pattern evolution based on accumulated examples**

The system is **fully configurable** and **analysis-tool-agnostic**.
You can label entire files, individual methods, classes, or any custom “unit” you define.

---

## Key features

- Plug-in Pydantic output schema
- Plug-in pattern / taxonomy text
- Custom prompt templates (angelicas + adjudicator)
- Optional custom agreement logic
- Optional retrieval example formatting
- SQLite persistence (documents, per-agent labels, final labels)
- FAISS vector index for similarity retrieval
- Rolling Cohen's kappa over any JSON field path
- File-based and unit-based labeling (methods, classes, IDs, etc.)
- Tool-agnostic analysis support via shared context
- **🆕 Enhanced vector matching with configurable confidence thresholds**
- **🆕 Automatic pattern storage and learning**
- **🆕 Pattern evolution and statistics tracking**

---

## Installation

### With uv

```bash
uv sync
source .venv/bin/activate
```

### With venv + pip

Replace `pyproject.toml` with `pyproject.toml.venv`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e ".[dev]"
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
- angelica_A_MODEL, angelica_B_MODEL, ADJUDICATOR_MODEL

---

## Quickstart (CLI)

### CLI overview

```bash
angelica --help
```

Commands:

- label-dir
- label-units
- plot-kappa

---

## File-based labeling (label-dir)
Use ``angelica label-dir --help`` to go through all the options.

```bash
angelica label-dir \
  --config ./coaster_label/config/coaster_config.py \
  --path ./resources/datasets/spring-petclinic/src/test/java \
  --suffix .java \
  --db labels.db \
  --index-dir vector_index \
  --parallel
  --out results.json
```

---

## Unit-based labeling (label-units)
Use ``angelica label-units --help`` to go through all the options.

```bash
angelica label-units \
  --config ./coaster_label/config/coaster_config.py \
  --project-path ./resources/datasets/spring-petclinic \
  --analysis-provider ./coaster_label/config/cldk_analysis_provider.py \
  --db labels.db \
  --index-dir vector_index \
  --parallel
  --out results.json
```

---

## Rolling Cohen's kappa

The `plot-kappa` command works with any database (enhanced or original mode):

```bash
# Plot kappa for a single field
angelica plot-kappa \
  --config coaster_label/config/coaster_config.py \
  --db labels.db \
  --field pattern_name \
  --window 50

# Plot kappa for multiple fields
angelica plot-kappa \
  --config coaster_label/config/coaster_config_enhanced.py \
  --db labels.db \
  --field pattern_name \
  --field fit_assessment \
  --field is_self_contained \
  --window 50

# Works with databases created in enhanced mode
angelica plot-kappa \
  --config coaster_label/config/coaster_config_enhanced.py \
  --db labels_enhanced.db \
  --field pattern_name \
  --window 50
```

**Note**: The `plot-kappa` command reads from the database and works regardless of whether enhanced mode was used during labeling. It analyzes agreement between labelers based on stored labels.

---

## Library usage (Python)

```python
from pydantic import BaseModel, Field
from angelica.agents.system import AgenticLabelingSystem
from angelica.models.config import AgenticConfig, PromptSpec, StoreSpec
from angelica.storage.sqlite.store_sqlite import SQLiteStore
from angelica.storage.faiss.vector_faiss import FaissVectorIndex

class MyLabel(BaseModel):
    label: str
    reasoning: str
    confidence_score: float

cfg = AgenticConfig(
    schema=MyLabel,
    patterns="...",
    angelica_a_prompt=PromptSpec("...", "..."),
    angelica_b_prompt=PromptSpec("...", "..."),
    adjudicator_prompt=PromptSpec("...", "..."),
)

store = SQLiteStore("labels.db", schema=MyLabel, store_spec=cfg.store_spec)
index = FaissVectorIndex("vector_index")

system = AgenticLabelingSystem(store=store, index=index, config=cfg)
```

---


## 🚀 Parallel Processing Mode

Angelica supports parallel processing using Ray for significant performance improvements. Enable parallel mode to process multiple documents concurrently across multiple workers.



### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `--parallel` | False | Enable parallel processing |
| `--num-workers` | 4 | Number of parallel workers |
| `--batch-size` | 10 | Batch size for FAISS updates |
| `--rate-limit-rpm` | None | API rate limit (requests/min) |

### Example: High-Throughput Processing

```bash
angelica label-units \
  --config config.py \
  --project-path ./project \
  --parallel \
  --num-workers 8 \
  --batch-size 20 \
  --rate-limit-rpm 5000 \
  --out results.json
```

### Programmatic Usage

```python
from angelica.parallel import RayLabelingOrchestrator

orchestrator = RayLabelingOrchestrator(
    db_path="labels.db",
    index_dir="vector_index",
    config=config,
    context=context,
    num_workers=4,
    rate_limit_rpm=1000,
)

results = orchestrator.label_documents_parallel(documents)
orchestrator.shutdown()
```

### Performance Guidelines

- **Start with 4 workers** for testing
- **Use 6-8 workers** for production
- **Set rate limits** based on your API tier
- **Monitor memory usage** with large batch sizes


## Cache

```
# View cache size
du -sh .llm_cache/

# Clear cache
rm -rf .llm_cache/

# Cache statistics (in logs)
✓ LLM caching enabled: .llm_cache/langchain.db
```

---

## Project structure

```
angelica/
├── cli.py
├── agents/
├── models/
├── prompts/
├── storage/
├── metrics/
└── llm_client/
```
