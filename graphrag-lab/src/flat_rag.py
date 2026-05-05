"""M4 — Flat RAG Baseline (ChromaDB vector store).

Vector-based retrieval baseline for head-to-head comparison with GraphRAG.

Design principle: ONLY the retrieval strategy differs from GraphRAG.
The answer model, temperature, and system prompt are imported directly
from src.graph_rag to guarantee a fair comparison.

Implemented in TIP-006.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from src.config import settings
from src.cost_tracker import track_llm_call
from src.extractor import get_client
from src.corpus_builder import Paragraph
from src.graph_rag import ANSWER_SYSTEM_PROMPT  # FAIR COMPARISON: same prompt as GraphRAG


# ----------------------------- Data classes -----------------------------

@dataclass
class FlatRAGResult:
    """Bundle of everything Flat RAG produced — mirrors GraphRAGResult shape."""
    question: str
    answer: str
    retrieved_paragraphs: list[tuple[int, str, float]]  # (idx, text, distance)
    context: str
    latency_ms: int = 0


# ----------------------------- Collection lifecycle -----------------------------

_collection: Optional[chromadb.Collection] = None
_chroma_client: Optional[chromadb.Client] = None
COLLECTION_NAME = "tech_corpus_flat_rag"


def _get_embedding_fn() -> OpenAIEmbeddingFunction:
    """Build the OpenAI embedding function from settings."""
    return OpenAIEmbeddingFunction(
        api_key=settings.openai_api_key,
        model_name=settings.embedding_model,
    )


def get_collection() -> chromadb.Collection:
    """Lazy-init an in-memory ChromaDB collection.

    We use an EphemeralClient (in-memory only) because the lab does not
    require persistence between runs — re-indexing the 60-paragraph
    corpus takes < 5 seconds.
    """
    global _collection, _chroma_client
    if _collection is None:
        _chroma_client = chromadb.EphemeralClient()
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=_get_embedding_fn(),
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def reset_collection() -> None:
    """Drop the collection (used when re-indexing or between tests)."""
    global _collection, _chroma_client
    if _chroma_client is not None and _collection is not None:
        try:
            _chroma_client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass  # collection may not exist yet
    _collection = None
    _chroma_client = None


# ----------------------------- Indexing -----------------------------

def index_corpus(paragraphs: list[Paragraph], verbose: bool = True) -> int:
    """Embed every paragraph and add to the ChromaDB collection.

    The collection's embedding function calls OpenAI's
    text-embedding-3-small in batch internally. This call is NOT routed
    through our cost_tracker decorator (because Chroma controls the
    request shape), so we estimate the cost manually after indexing.

    Args:
        paragraphs: List of Paragraph objects (typically the full corpus).
        verbose: Print progress.

    Returns:
        Number of documents indexed.
    """
    if not paragraphs:
        raise ValueError("Cannot index empty paragraph list")

    coll = get_collection()
    ids = [f"para_{p.idx:02d}" for p in paragraphs]
    docs = [p.text for p in paragraphs]
    metadatas = [{"idx": p.idx} for p in paragraphs]

    # Chroma upserts — re-running this TIP is idempotent
    coll.upsert(ids=ids, documents=docs, metadatas=metadatas)
    if verbose:
        print(f"  Indexed {len(docs)} paragraphs into Chroma collection '{COLLECTION_NAME}'")
    return len(docs)


def estimate_indexing_cost(paragraphs: list[Paragraph]) -> float:
    """Estimate the embedding cost manually (not auto-tracked by Chroma).

    Approximates token count as len(text)/4 (a known rough rule for
    English text). Real token counts will be slightly different but the
    estimate is within ~15% — sufficient for the cost analysis section.
    """
    from src.cost_tracker import estimate_cost
    approx_tokens = sum(max(1, len(p.text) // 4) for p in paragraphs)
    return estimate_cost(settings.embedding_model, approx_tokens, 0)


def log_indexing_cost(paragraphs: list[Paragraph]) -> None:
    """Append one synthetic record to the cost log for the indexing step.

    This mirrors the way GraphRAG's extraction is logged — without it,
    the deliverable #4 cost analysis would underreport Flat RAG's true
    indexing overhead.
    """
    from src.cost_tracker import CallRecord, _append_record
    approx_tokens = sum(max(1, len(p.text) // 4) for p in paragraphs)
    cost = estimate_indexing_cost(paragraphs)
    record = CallRecord(
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        module="flat_rag_index",
        function="index_corpus",
        model=settings.embedding_model,
        tokens_in=approx_tokens,
        tokens_out=0,
        latency_ms=0,  # Chroma doesn't expose per-call latency cleanly
        cost_usd=cost,
        status="ok",
    )
    _append_record(record)


# ----------------------------- Retrieval -----------------------------

def retrieve(question: str, top_k: int = 5) -> list[tuple[int, str, float]]:
    """Retrieve top-k most similar paragraphs.

    Returns:
        List of (paragraph_idx, paragraph_text, cosine_distance) tuples,
        ordered by ascending distance (most similar first).
    """
    coll = get_collection()
    if coll.count() == 0:
        raise RuntimeError("Collection is empty. Call index_corpus(paragraphs) first.")

    res = coll.query(
        query_texts=[question],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    out: list[tuple[int, str, float]] = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append((int(meta["idx"]), str(doc), float(dist)))
    return out


# ----------------------------- Context assembly -----------------------------

def assemble_context(retrieved: list[tuple[int, str, float]]) -> str:
    """Concatenate top-k paragraphs into a single context block.

    Format mirrors GraphRAG's "Facts:" header so the answer model sees
    a comparably-shaped input. We label as "Passages:" because that's
    semantically what they are.
    """
    if not retrieved:
        return "Passages:\n(no relevant passages found)"
    lines = ["Passages:"]
    for idx, text, _dist in retrieved:
        lines.append(f"[Paragraph {idx:02d}] {text}")
    return "\n".join(lines)


# ----------------------------- Answer (mirrors GraphRAG) -----------------------------

@track_llm_call(module="flat_rag_answer")
def _call_answer_api(question: str, context: str) -> object:
    """Same model, same temperature, same system prompt as GraphRAG."""
    return get_client().chat.completions.create(
        model=settings.llm_model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\nQuestion: {question}\n\nAnswer:"},
        ],
    )


def answer_with_context(question: str, context: str) -> str:
    """Final answer call. Returns text only."""
    try:
        resp = _call_answer_api(question, context)
        content = resp.choices[0].message.content  # type: ignore
        return (content or "").strip()
    except Exception as e:
        return f"[ERROR] Answer generation failed: {e}"


# ----------------------------- Orchestrator -----------------------------

def query(question: str, top_k: int = 5) -> FlatRAGResult:
    """Run the full Flat RAG pipeline for a question.

    Args:
        question: Natural-language question.
        top_k: Number of paragraphs to retrieve (default 5).

    Returns:
        FlatRAGResult with answer + every intermediate artifact.
    """
    t0 = time.time()
    retrieved = retrieve(question, top_k=top_k)
    context = assemble_context(retrieved)
    answer = answer_with_context(question, context)
    return FlatRAGResult(
        question=question,
        answer=answer,
        retrieved_paragraphs=retrieved,
        context=context,
        latency_ms=int((time.time() - t0) * 1000),
    )
