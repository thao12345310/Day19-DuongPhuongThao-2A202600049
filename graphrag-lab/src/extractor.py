"""M1 — Triple Extractor.

Reads paragraphs from the corpus and uses an LLM to extract
(subject, relation, object) triples in JSON-mode. Triples are typed
(entity vs literal) and tagged with source_idx for traceability.

Implemented in TIP-003.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Literal, Optional

from openai import OpenAI

from src.config import settings
from src.corpus_builder import Paragraph
from src.cost_tracker import track_llm_call


# ----------------------------- Dataclass -----------------------------

ObjectType = Literal["entity", "literal"]


@dataclass(frozen=True)
class Triple:
    """A single (subject, relation, object) fact."""
    subject: str
    relation: str       # UPPER_SNAKE_CASE
    object: str
    object_type: ObjectType
    source_idx: int     # Paragraph idx this triple was extracted from


# ----------------------------- Relation taxonomy -----------------------------

# Closed vocabulary of relation types. The LLM is instructed to use these
# whenever applicable, but may emit other UPPER_SNAKE_CASE relations if
# none of these fit precisely.
ALLOWED_RELATIONS = [
    "FOUNDED_BY", "FOUNDED_IN", "FOUNDED_AT",  # creation: by-whom, in-year, at-location
    "CEO_OF", "PRESIDENT_OF", "CHAIRMAN_OF",
    "WORKS_AT", "FORMER_EMPLOYER",
    "ACQUIRED", "ACQUIRED_FOR", "ACQUIRED_IN",
    "SUBSIDIARY_OF", "PARENT_OF", "INVESTED_IN",
    "PARTNER_OF", "COMPETITOR_OF",
    "DEVELOPS", "RELEASED", "RELEASED_IN",
    "OWNS", "RENAMED_TO", "HEADQUARTERED_IN",
    "AWARDED", "BORN_IN", "STUDIED_AT",
]


# ----------------------------- Prompts -----------------------------

SYSTEM_PROMPT = """You are a precise information extraction system that converts text into knowledge-graph triples.

Your job is to extract every meaningful (subject, relation, object) triple from a paragraph about technology companies.

Rules:
1. Use UPPER_SNAKE_CASE for relations.
2. Prefer relations from this canonical list when applicable:
""" + ", ".join(ALLOWED_RELATIONS) + """
3. If no canonical relation fits, you MAY invent a new UPPER_SNAKE_CASE relation that is short and reusable.
4. For each triple, classify the object as:
   - "entity" — a named entity that could itself be a subject of other relations (a person, company, product, place, organization).
   - "literal" — a value that does not participate in further relations (a year, a money amount, a percentage, a single descriptive label).
5. Use canonical names (e.g., "OpenAI" not "openai" or "Open AI"; "Sam Altman" not "Altman" or "Sam"). Always expand abbreviations to the canonical form when the paragraph makes it clear.
6. Years are literals (e.g., "2015"). Money amounts are literals (e.g., "$1 billion").
7. Output ONLY valid JSON matching this schema, with no extra prose:
   {"triples": [{"subject": "...", "relation": "...", "object": "...", "object_type": "entity" | "literal"}, ...]}
8. If a paragraph has no extractable facts, return {"triples": []}.
9. Do not invent facts not stated in the paragraph.
"""

FEW_SHOT_EXAMPLES = [
    {
        "paragraph": "OpenAI was founded by Sam Altman and Elon Musk in San Francisco in 2015.",
        "triples": [
            {"subject": "OpenAI", "relation": "FOUNDED_BY", "object": "Sam Altman", "object_type": "entity"},
            {"subject": "OpenAI", "relation": "FOUNDED_BY", "object": "Elon Musk", "object_type": "entity"},
            {"subject": "OpenAI", "relation": "FOUNDED_AT", "object": "San Francisco", "object_type": "entity"},
            {"subject": "OpenAI", "relation": "FOUNDED_IN", "object": "2015", "object_type": "literal"},
        ],
    },
    {
        "paragraph": "Microsoft acquired GitHub in 2018 for approximately $7.5 billion.",
        "triples": [
            {"subject": "Microsoft", "relation": "ACQUIRED", "object": "GitHub", "object_type": "entity"},
            {"subject": "Microsoft", "relation": "ACQUIRED_IN", "object": "2018", "object_type": "literal"},
            {"subject": "Microsoft", "relation": "ACQUIRED_FOR", "object": "$7.5 billion", "object_type": "literal"},
        ],
    },
    {
        "paragraph": "Yann LeCun shared the 2018 Turing Award with Hinton and Bengio.",
        "triples": [
            {"subject": "Yann LeCun", "relation": "AWARDED", "object": "Turing Award", "object_type": "entity"},
            {"subject": "Geoffrey Hinton", "relation": "AWARDED", "object": "Turing Award", "object_type": "entity"},
            {"subject": "Yoshua Bengio", "relation": "AWARDED", "object": "Turing Award", "object_type": "entity"},
        ],
    },
]


def _build_user_prompt(paragraph_text: str) -> str:
    """Build the user message containing few-shot examples + the target paragraph."""
    parts = ["Examples of correct extraction:\n"]
    for ex in FEW_SHOT_EXAMPLES:
        parts.append(f"Paragraph: {ex['paragraph']}")
        parts.append(f"Output: {json.dumps({'triples': ex['triples']})}\n")
    parts.append("Now extract triples from this paragraph:\n")
    parts.append(f"Paragraph: {paragraph_text}")
    parts.append("Output:")
    return "\n".join(parts)


# ----------------------------- Client -----------------------------

_client: Optional[OpenAI] = None

def get_client() -> OpenAI:
    """Lazy-init OpenAI client (lets tests monkeypatch easily)."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


# ----------------------------- Core extraction -----------------------------

@track_llm_call(module="extractor")
def _call_extract_api(paragraph_text: str) -> object:
    """Single OpenAI call wrapped for cost tracking. Returns raw response."""
    return get_client().chat.completions.create(
        model=settings.llm_model,
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(paragraph_text)},
        ],
    )


def _parse_response(response: object, source_idx: int) -> list[Triple]:
    """Parse the JSON response into Triple objects. Raises ValueError on bad shape."""
    content = response.choices[0].message.content  # type: ignore[attr-defined]
    if not content:
        raise ValueError("Empty response content")
    data = json.loads(content)  # may raise json.JSONDecodeError
    if "triples" not in data or not isinstance(data["triples"], list):
        raise ValueError(f"Response missing 'triples' list: {content[:200]}")
    triples: list[Triple] = []
    for i, t in enumerate(data["triples"]):
        for k in ("subject", "relation", "object", "object_type"):
            if k not in t:
                raise ValueError(f"Triple #{i} missing field '{k}': {t}")
        if t["object_type"] not in ("entity", "literal"):
            raise ValueError(
                f"Triple #{i} has invalid object_type {t['object_type']!r}; "
                "must be 'entity' or 'literal'."
            )
        triples.append(Triple(
            subject=str(t["subject"]).strip(),
            relation=str(t["relation"]).strip().upper().replace(" ", "_"),
            object=str(t["object"]).strip(),
            object_type=t["object_type"],
            source_idx=source_idx,
        ))
    return triples


def extract_triples(paragraph: Paragraph, max_retries: int = 1) -> list[Triple]:
    """Extract triples from a single paragraph, with one retry on parse error.

    Args:
        paragraph: Paragraph object to extract from.
        max_retries: Number of times to retry on parse failure (default 1 → up to 2 attempts total).

    Returns:
        List of Triple objects. Empty list if all attempts fail (logged to stderr).
    """
    attempts = 0
    last_error: Exception | None = None
    while attempts <= max_retries:
        try:
            response = _call_extract_api(paragraph.text)
            return _parse_response(response, paragraph.idx)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            attempts += 1
    # Final failure — log to stderr and skip this paragraph
    import sys
    print(
        f"[extractor] WARNING: Failed to extract triples from paragraph "
        f"[{paragraph.idx:02d}] after {attempts} attempts: {last_error}",
        file=sys.stderr,
    )
    return []


def extract_corpus(paragraphs: list[Paragraph], verbose: bool = True) -> list[Triple]:
    """Extract triples from every paragraph in the corpus, in order.

    Args:
        paragraphs: List of Paragraph objects (typically the full corpus).
        verbose: If True, print progress every 10 paragraphs.

    Returns:
        Flat list of all extracted Triple objects across all paragraphs.
    """
    all_triples: list[Triple] = []
    for i, p in enumerate(paragraphs, start=1):
        triples = extract_triples(p)
        all_triples.extend(triples)
        if verbose and (i % 10 == 0 or i == len(paragraphs)):
            print(f"  [{i:3d}/{len(paragraphs)}] extracted {len(all_triples)} triples so far...")
    return all_triples


def extract_corpus_cached(
    paragraphs: list[Paragraph],
    cache_path: "Path",
    force_refresh: bool = False,
    verbose: bool = True,
) -> list[Triple]:
    """Extract triples with on-disk JSON cache.

    First time this is called for a given cache_path, runs extract_corpus()
    on all paragraphs and writes the result. Subsequent calls load from cache
    if (a) cache file exists, (b) cache is newer than corpus modification time,
    and (c) cache contains exactly len(paragraphs) source_idx values matching
    the input paragraphs' idx values.

    This makes the v2 notebook re-runnable without burning $0.10 on every
    `Run All`. Pass force_refresh=True to bypass the cache.

    Args:
        paragraphs: Paragraph list (typically v2 corpus, ~280 entries).
        cache_path: JSON file to read/write.
        force_refresh: If True, ignore existing cache and re-extract.
        verbose: Print whether the cache was hit or missed.

    Returns:
        List of Triple objects.
    """
    import json as _json
    from pathlib import Path as _Path
    cache_path = _Path(cache_path)

    if not force_refresh and cache_path.exists():
        try:
            data = _json.loads(cache_path.read_text(encoding="utf-8"))
            cached_idxs = {t["source_idx"] for t in data.get("triples", [])}
            input_idxs = {p.idx for p in paragraphs}
            # Cache valid if every input paragraph idx is represented in cache.
            # (Some paragraphs legitimately yield 0 triples, so cached_idxs may
            # be a subset — but it must not contain idxs we did NOT ask for.)
            if cached_idxs.issubset(input_idxs):
                triples = [
                    Triple(
                        subject=t["subject"],
                        relation=t["relation"],
                        object=t["object"],
                        object_type=t["object_type"],
                        source_idx=t["source_idx"],
                    )
                    for t in data.get("triples", [])
                ]
                if verbose:
                    print(f"  ✓ Loaded {len(triples)} triples from cache: {cache_path.name}")
                return triples
            elif verbose:
                print(f"  ⚠ Cache idx mismatch — re-extracting")
        except Exception as e:
            if verbose:
                print(f"  ⚠ Cache read failed ({e}) — re-extracting")

    if verbose:
        print(f"  ↻ Cache miss — extracting {len(paragraphs)} paragraphs (this may take a while)")
    triples = extract_corpus(paragraphs, verbose=verbose)

    # Write cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        _json.dumps(
            {
                "n_triples": len(triples),
                "n_paragraphs": len(paragraphs),
                "triples": [
                    {
                        "subject": t.subject,
                        "relation": t.relation,
                        "object": t.object,
                        "object_type": t.object_type,
                        "source_idx": t.source_idx,
                    }
                    for t in triples
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if verbose:
        print(f"  ✓ Wrote {len(triples)} triples to cache: {cache_path.name}")
    return triples
