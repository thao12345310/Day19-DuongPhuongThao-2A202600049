# GraphRAG Lab Day 19 — Tech Company Corpus

A hands-on lab comparing **Graph-based Retrieval-Augmented Generation (GraphRAG)** against a traditional **Flat RAG** baseline on a curated tech company corpus. The pipeline extracts knowledge triples, builds a Neo4j knowledge graph, and benchmarks answer quality, latency, and cost across both approaches.

---

## Prerequisites

| Requirement | Version |
|---|---|
| **Python** | 3.10+ |
| **Docker Desktop** | Latest (with Docker Compose v2) |
| **OpenAI API Key** | Active key with GPT-4o-mini access |

---

## Setup

### 1. Clone & configure environment

```bash
cp .env.example .env
```

Open `.env` in your editor and set your real `OPENAI_API_KEY`:

```
OPENAI_API_KEY=sk-your-real-key-here
```

### 2. Create a Python virtual environment

**macOS / Linux:**

```bash
python -m venv .venv && source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start Neo4j via Docker

```bash
docker compose up -d
```

Verify Neo4j is running by opening your browser at **[http://localhost:7474](http://localhost:7474)**.

- **Username:** `neo4j`
- **Password:** `graphrag-lab-pwd`

You should see the Neo4j Browser interface.

---

## Run

1. Start Jupyter:
   ```bash
   jupyter notebook
   ```
2. Open `notebooks/lab19_main.ipynb`
3. Click **"Run All"** (or run cells sequentially)

The notebook will:
- Load and chunk the tech corpus
- Extract knowledge triples via LLM
- Build the Neo4j knowledge graph
- Run both GraphRAG and Flat RAG pipelines
- Benchmark and compare results

---

## Project Structure

```
graphrag-lab/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── data/
│   ├── tech_corpus.txt          ← Tech company corpus
│   └── benchmark_questions.json ← Evaluation questions
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── corpus_builder.py
│   ├── extractor.py
│   ├── graph_builder.py
│   ├── graph_rag.py
│   ├── flat_rag.py
│   ├── benchmark.py
│   └── cost_tracker.py
├── notebooks/
│   └── lab19_main.ipynb
├── results/                      ← Created at runtime
│   └── .gitkeep
└── screenshots/                  ← Neo4j screenshots
    └── .gitkeep
```

---

## Troubleshooting

### Port conflict on 7474 or 7687

Another service is using the Neo4j ports. Find and stop it:

```bash
# Check what's using the port
lsof -i :7474
lsof -i :7687

# Kill the process (replace <PID>)
kill -9 <PID>
```

Or change the host ports in `docker-compose.yml`:

```yaml
ports:
  - "17474:7474"
  - "17687:7687"
```

Then update `NEO4J_URI` in `.env` accordingly.

### Docker not running

If `docker compose up -d` fails with a connection error:

1. Open **Docker Desktop** and ensure it is running
2. Wait for the Docker engine to fully start
3. Retry `docker compose up -d`

### OPENAI_API_KEY missing or invalid

If you see `RuntimeError: Missing required env var: OPENAI_API_KEY`:

1. Ensure you copied `.env.example` to `.env`: `cp .env.example .env`
2. Edit `.env` and replace `sk-...` with your actual OpenAI API key
3. Verify the key is valid at [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)

### Neo4j authentication failure

If you cannot log in to Neo4j Browser:

1. Ensure you are using the correct credentials: `neo4j` / `graphrag-lab-pwd`
2. If you changed the password in `docker-compose.yml`, update `.env` to match
3. To reset, remove the volume and restart:
   ```bash
   docker compose down -v
   docker compose up -d
   ```

---

## License

This project is for educational purposes as part of the VinUni Labs curriculum.
