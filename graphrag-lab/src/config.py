"""Centralized configuration loaded from .env."""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent

@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    llm_model: str
    embedding_model: str
    corpus_path: Path
    benchmark_path: Path
    results_dir: Path
    cost_log_path: Path

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}. Did you copy .env.example to .env?")
    return val

settings = Settings(
    openai_api_key=_require("OPENAI_API_KEY"),
    neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
    neo4j_password=_require("NEO4J_PASSWORD"),
    llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
    embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
    corpus_path=PROJECT_ROOT / os.getenv("CORPUS_PATH", "data/tech_corpus.txt"),
    benchmark_path=PROJECT_ROOT / os.getenv("BENCHMARK_PATH", "data/benchmark_questions.json"),
    results_dir=PROJECT_ROOT / os.getenv("RESULTS_DIR", "results"),
    cost_log_path=PROJECT_ROOT / os.getenv("COST_LOG_PATH", "results/cost_log.csv"),
)

# Ensure results dir exists
settings.results_dir.mkdir(parents=True, exist_ok=True)
