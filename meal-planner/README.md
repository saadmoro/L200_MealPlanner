# meal-planner — Grocery Store Recipe Planner & Shopping List Agent

Google ADK 2.0 (`google.adk.workflow.Workflow`) agentic workflow for healthy meal planning, nutrition guidance, deterministic dietary/allergen safety enforcement, and store-grounded shopping list generation.

Generated with `agents-cli` (`adk_python`, `--prototype`) and designed according to [`../.agents-cli-spec.md`](../.agents-cli-spec.md) and [`../docs/design_document.html`](../docs/design_document.html).

## Project Structure

```text
meal-planner/
├── app/
│   ├── agent.py                 # ADK App + root_agent (Workflow) + Plugins + OTel setup
│   ├── workflow.py              # ADK 2.0 graph Workflow DAG (FunctionNodes + scoped LlmAgents)
│   ├── schemas.py               # Pydantic v2 I/O & state schemas
│   ├── plugins.py               # Runner-wide DietarySafetyPlugin & ObservabilityPlugin
│   ├── memory.py                # SqliteMemoryService (ADK BaseMemoryService) + callback
│   ├── observability.py         # Local OpenTelemetry JSONL + optional OTLP HTTP exporter
│   ├── fast_api_app.py          # FastAPI + ADK Web + A2A server
│   ├── app_utils/               # Shared session, artifact, memory, and A2A wiring
│   ├── db/                      # SQLite connection helper & migration runner
│   ├── prompts/                 # Version-controlled system prompts (*.v1.md)
│   └── tools/                   # Deterministic profile, catalog, nutrition, safety, shopping tools
├── data/
│   ├── migrations/001_init.sql  # Version-controlled SQLite DDL
│   └── seed.py                  # Idempotent seeder (76 SKUs + nutrition + inventory + fixture users)
├── tests/
│   ├── unit/                    # Deterministic pytest suite (tools, plugins, memory, workflow, OTel)
│   ├── integration/             # Live stream & FastAPI/A2A tests
│   └── eval/                    # agents-cli eval datasets & config (response quality + safety)
├── GEMINI.md                    # Coding agent guidance
└── pyproject.toml               # uv-managed dependencies (google-adk >= 2.12, sqlalchemy[asyncio], etc.)
```

## Quick Start

### 1. Configure LLM Credentials (`.env`)
Update `meal-planner/.env` with either:
- **Vertex AI / Gemini platform:** Set `GOOGLE_CLOUD_PROJECT=<your-gcp-project-with-aiplatform-enabled>` (and `GOOGLE_CLOUD_LOCATION=global`, `GOOGLE_GENAI_USE_ENTERPRISE=true`), **or**
- **Google AI Studio:** Comment out the `GOOGLE_*` lines and set `GEMINI_API_KEY=<your-key>`.

### 2. Seed the Store SQLite Database
```bash
cd meal-planner
uv run python data/seed.py
```
This populates `data/grocery_store.db` with 76 SKUs (including gluten-free, low-sodium, and vegetarian options), 1:1 `nutritional_facts`, `inventory` with aisle locations, and 4 fixture customers including `cust_malcom_munson` (celiac disease, hypertension, Mediterranean preference, prefers chicken over fish, dislikes eggplant).

### 3. Run Deterministic Unit & Workflow Tests
```bash
uv run pytest tests/unit -v
uv run ruff check app data tests/unit
```

### 4. Interactive Testing & Smoke Tests
```bash
# Quick CLI smoke test
agents-cli run "Hello!"

# Interactive ADK Web playground
agents-cli playground
```

### 5. Run Evaluations
```bash
agents-cli eval run
```

## Observability & Tracing
- Every workflow run writes OpenTelemetry spans (`node.load_user_context`, `node.workflow_router`, `node.compute_nutrition_and_scale`, `node.map_inventory_skus`, `node.persist_meal_order`, `workflow.state_transition`, plus native ADK `invoke_agent`/`call_llm`/`execute_tool` spans) to `logs/traces.jsonl`.
- Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces` to stream live traces to Arize Phoenix or Jaeger.

## Promoting to GCP & CI/CD
When ready to deploy beyond the local prototype:
```bash
agents-cli scaffold enhance . --deployment-target cloud_run --cicd-runner github_actions
```
