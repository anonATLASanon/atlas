

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