"""M3 — GraphRAG Querier.

Five-stage pipeline for multi-hop question answering over a Neo4j graph:

  1. extract_question_entities(question) — LLM-based NER, narrow to named entities
  2. match_entities_in_graph(entities)   — exact + alias lookup against the graph
  3. bfs_subgraph(matched, max_hops=2)   — Cypher path query, deduplicated edges
  4. textualize(edges)                   — structured "S REL O" triples
  5. answer_with_context(question, ctx)  — LLM answer with strict no-fabrication prompt

The strict answer prompt must cause the model to abstain ("not enough
information") when the context is insufficient. This is the key behavior
that distinguishes a sound GraphRAG from one that hallucinates.

Implemented in TIP-005.
"""
from __future__ import annotations
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from src.config import settings
from src.cost_tracker import track_llm_call
from src.extractor import get_client
from src.graph_builder import get_driver, _normalize_key


# ----------------------------- Data classes -----------------------------

@dataclass(frozen=True)
class GraphEdge:
    """One directed edge retrieved from the graph during BFS."""
    src: str
    relation: str
    dst: str
    source_idx: Optional[int] = None  # paragraph idx of provenance, if available


@dataclass
class GraphRAGResult:
    """Bundle of everything the query produced — useful for inspection + benchmarking."""
    question: str
    answer: str
    extracted_entities: list[str]
    matched_entity_names: list[str]
    edges: list[GraphEdge]
    context: str
    latency_ms: int = 0
    # Cost stats are read from the cost log per question via wall-clock
    # delineation in the benchmark; this dataclass stays cost-agnostic.


# ----------------------------- Stage 1: Entity NER -----------------------------

NER_SYSTEM_PROMPT = """You extract named entities from a question.

Return ONLY a JSON object: {"entities": ["...", "..."]}

Rules:
1. Include proper nouns: companies, people, products, places, organizations.
2. EXCLUDE common nouns ("CEO", "founder", "company"), question words ("who", "what"), and roles.
3. Use the canonical form a knowledge graph would store ("OpenAI" not "openai", "Sam Altman" not "Altman").
4. If no named entities are found, return {"entities": []}.
"""

NER_FEW_SHOT = [
    {"q": "Who is the CEO of Microsoft?",
     "out": {"entities": ["Microsoft"]}},
    {"q": "Which AI company did Dario Amodei work at before founding Anthropic?",
     "out": {"entities": ["Dario Amodei", "Anthropic"]}},
    {"q": "What year was the company headquartered in Cupertino founded?",
     "out": {"entities": ["Cupertino"]}},
]


def _build_ner_prompt(question: str) -> str:
    parts = ["Examples:"]
    for ex in NER_FEW_SHOT:
        parts.append(f"Question: {ex['q']}")
        parts.append(f"Output: {json.dumps(ex['out'])}")
    parts.append(f"\nQuestion: {question}")
    parts.append("Output:")
    return "\n".join(parts)


@track_llm_call(module="graph_rag_ner")
def _call_ner_api(question: str) -> object:
    return get_client().chat.completions.create(
        model=settings.llm_model,
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": NER_SYSTEM_PROMPT},
            {"role": "user", "content": _build_ner_prompt(question)},
        ],
    )


def extract_question_entities(question: str) -> list[str]:
    """Stage 1: LLM-based entity extraction. Returns [] on parse failure."""
    try:
        resp = _call_ner_api(question)
        content = resp.choices[0].message.content  # type: ignore
        data = json.loads(content) if content else {}
        ents = data.get("entities", [])
        # Defensive: must be a list of non-empty strings
        return [str(e).strip() for e in ents if isinstance(e, str) and e.strip()]
    except Exception:
        return []


# ----------------------------- Stage 2: Graph entity matching -----------------------------

def match_entities_in_graph(entities: list[str]) -> list[str]:
    """Stage 2: For each input entity name, find the canonical name in the graph.

    Matching strategy (in priority order):
      a) exact match on Entity.name
      b) match against Entity.aliases (any alias's normalized key equals input's key)
      c) startswith match on normalized name (last-resort fuzzy fallback)

    Returns:
      Deduplicated list of canonical Entity.name values that matched.
    """
    if not entities:
        return []

    # Normalize once
    keys_to_input = {_normalize_key(e): e for e in entities if e.strip()}
    keys = list(keys_to_input.keys())

    found: dict[str, None] = {}  # ordered dedup of matched canonical names
    with get_driver().session() as s:
        # Strategy (a) + (b): exact + alias match in one Cypher pass
        rows = s.run(
            """
            MATCH (n:Entity)
            WITH n,
                 toLower(replace(n.name, ' ', '')) AS name_key,
                 [a IN coalesce(n.aliases, []) | toLower(replace(a, ' ', ''))] AS alias_keys
            WHERE name_key IN $keys OR ANY(k IN alias_keys WHERE k IN $keys)
            RETURN DISTINCT n.name AS name
            """,
            keys=keys,
        ).data()
        for r in rows:
            found.setdefault(r["name"], None)

        # Strategy (c): startswith fallback ONLY for unmatched inputs
        # Guard: only use keys/matches with length > 2 to prevent trivial matches
        # (e.g. entity "X" matching "xyzcorpthatdoesnotexist")
        if len(found) < len(keys):
            still_missing_keys = [
                k for k in keys
                if len(k) > 2 and not any(
                    _normalize_key(name).startswith(k) or k.startswith(_normalize_key(name))
                    for name in found
                )
            ]
            if still_missing_keys:
                rows = s.run(
                    """
                    MATCH (n:Entity)
                    WITH n, toLower(replace(n.name, ' ', '')) AS name_key
                    WHERE size(name_key) > 2
                      AND ANY(k IN $keys WHERE name_key STARTS WITH k OR k STARTS WITH name_key)
                    RETURN DISTINCT n.name AS name
                    LIMIT 10
                    """,
                    keys=still_missing_keys,
                ).data()
                for r in rows:
                    found.setdefault(r["name"], None)

    return list(found.keys())


# ----------------------------- Stage 3: BFS subgraph -----------------------------

def bfs_subgraph(
    matched_names: list[str],
    max_hops: int = 2,
    edge_limit: int = 200,
) -> list[GraphEdge]:
    """Stage 3: Collect all edges within `max_hops` of any matched node.

    The path is undirected for traversal (we don't know which way the answer
    sits relative to the question entity), but each returned edge preserves
    its stored direction so textualization reads naturally.

    Args:
        matched_names: Canonical Entity.name values from match_entities_in_graph.
        max_hops: Path length. 2 covers the vast majority of multi-hop questions.
        edge_limit: Cap on returned edges to keep context size bounded.

    Returns:
        Deduplicated list of GraphEdge objects.
    """
    if not matched_names:
        return []

    cypher = f"""
    MATCH (start:Entity)
    WHERE start.name IN $names
    WITH collect(DISTINCT start) AS starts
    UNWIND starts AS s
    MATCH p = (s)-[*1..{max_hops}]-(neighbor:Entity)
    UNWIND relationships(p) AS r
    WITH DISTINCT
         startNode(r).name AS src,
         type(r)            AS rel,
         endNode(r).name    AS dst,
         r.source_idx       AS source_idx
    RETURN src, rel, dst, source_idx
    LIMIT $limit
    """
    edges: list[GraphEdge] = []
    seen: set[tuple[str, str, str]] = set()
    with get_driver().session() as s:
        for row in s.run(cypher, names=matched_names, limit=edge_limit):
            key = (row["src"], row["rel"], row["dst"])
            if key in seen:
                continue
            seen.add(key)
            edges.append(GraphEdge(
                src=row["src"],
                relation=row["rel"],
                dst=row["dst"],
                source_idx=row["source_idx"],
            ))
    return edges


# ----------------------------- Stage 4: Textualization -----------------------------

def textualize(edges: list[GraphEdge], max_lines: int = 80) -> str:
    """Stage 4: Convert edges into structured triple lines.

    We keep structure (uppercase relation between named entities) rather
    than humanizing, because gpt-4o-mini reasons better over explicit
    triples than over awkward auto-generated prose.

    Output format:
      Facts:
      - OpenAI FOUNDED_BY Sam Altman
      - OpenAI FOUNDED_BY Elon Musk
      - Microsoft INVESTED_IN OpenAI
      ...
    """
    if not edges:
        return "Facts:\n(no relevant facts found in the knowledge graph)"
    lines = ["Facts:"]
    for e in edges[:max_lines]:
        lines.append(f"- {e.src} {e.relation} {e.dst}")
    if len(edges) > max_lines:
        lines.append(f"... ({len(edges) - max_lines} more facts truncated)")
    return "\n".join(lines)


# ----------------------------- Stage 5: Answer with context -----------------------------

ANSWER_SYSTEM_PROMPT = """You answer questions using ONLY the facts provided.

Rules:
1. Use ONLY information present in the Facts section. Do not use outside knowledge.
2. If the Facts do not contain enough information to answer, respond exactly:
   "I don't have enough information to answer this question."
3. Be concise — give the shortest accurate answer. One sentence is usually enough.
4. If multiple valid answers exist, list all of them.
5. Do not speculate, infer beyond the facts, or add caveats.
"""


@track_llm_call(module="graph_rag_answer")
def _call_answer_api(question: str, context: str) -> object:
    return get_client().chat.completions.create(
        model=settings.llm_model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\nQuestion: {question}\n\nAnswer:"},
        ],
    )


def answer_with_context(question: str, context: str) -> str:
    """Stage 5: Final answer call. Returns answer text only."""
    try:
        resp = _call_answer_api(question, context)
        content = resp.choices[0].message.content  # type: ignore
        return (content or "").strip()
    except Exception as e:
        return f"[ERROR] Answer generation failed: {e}"


# ----------------------------- Orchestrator -----------------------------

def query(question: str, max_hops: int = 2) -> GraphRAGResult:
    """Run the full GraphRAG pipeline for a question.

    Args:
        question: Natural-language question.
        max_hops: BFS depth (default 2 — covers most lab benchmarks).

    Returns:
        GraphRAGResult with answer + every intermediate artifact.
    """
    t0 = time.time()

    extracted = extract_question_entities(question)
    matched = match_entities_in_graph(extracted)
    edges = bfs_subgraph(matched, max_hops=max_hops)
    context = textualize(edges)
    answer = answer_with_context(question, context)

    return GraphRAGResult(
        question=question,
        answer=answer,
        extracted_entities=extracted,
        matched_entity_names=matched,
        edges=edges,
        context=context,
        latency_ms=int((time.time() - t0) * 1000),
    )
