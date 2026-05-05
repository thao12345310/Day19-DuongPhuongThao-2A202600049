"""M0 — Corpus Loader & Validator.

Loads tech_corpus.txt and benchmark_questions.json, validates structure,
returns typed dataclass objects. No LLM calls in this module.

Implemented in TIP-002.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from src.config import settings


# ----------------------------- Dataclasses -----------------------------

@dataclass(frozen=True)
class Paragraph:
    """A single paragraph from the corpus."""
    idx: int             # Original [NN] prefix number, 1-indexed
    text: str            # Cleaned text (prefix stripped, whitespace normalized)


Category = Literal["single_hop", "multi_hop", "ambiguous", "out_of_domain"]


@dataclass(frozen=True)
class BenchQuestion:
    """A single benchmark question with gold answer."""
    qid: str
    category: Category
    question: str
    gold_answer: str
    gold_entities: tuple[str, ...]      # tuple for hashability
    source_paragraphs: tuple[int, ...]
    expected_hops: int
    reasoning_path: Optional[str] = None
    ambiguity_note: Optional[str] = None
    hallucination_check: Optional[str] = None


# ----------------------------- Constants -----------------------------

VALID_CATEGORIES = {"single_hop", "multi_hop", "ambiguous", "out_of_domain"}
PARAGRAPH_PREFIX_RE = re.compile(r"^\[(\d+)\]\s*(.+)$", re.DOTALL)
EXPECTED_PARAGRAPH_COUNT = 60
EXPECTED_QUESTION_COUNT = 20
EXPECTED_DISTRIBUTION = {"single_hop": 5, "multi_hop": 5, "ambiguous": 5, "out_of_domain": 5}


# ----------------------------- Loaders -----------------------------

def load_corpus(
    path: Optional[Path] = None,
    expected_count: Optional[int] = EXPECTED_PARAGRAPH_COUNT,
) -> list[Paragraph]:
    """Load and parse the corpus file.

    Args:
        path: Override the default path from settings. If None, uses settings.corpus_path.
        expected_count: Strict count to validate. Defaults to EXPECTED_PARAGRAPH_COUNT (60)
            for v1 backwards compatibility. Pass an explicit integer for v2 (e.g., 280)
            or ``None`` to disable count validation entirely.

    Returns:
        List of Paragraph objects, ordered by idx ascending.

    Raises:
        FileNotFoundError: if corpus file does not exist.
        ValueError: if no valid paragraphs are found, or duplicate idx detected,
                    or paragraph count != expected_count (when expected_count is not None).
    """
    path = path or settings.corpus_path
    if not path.exists():
        raise FileNotFoundError(f"Corpus file not found: {path}")

    raw = path.read_text(encoding="utf-8")

    paragraphs: list[Paragraph] = []
    seen_idx: set[int] = set()

    # Split on blank lines (one or more empty lines)
    blocks = re.split(r"\n\s*\n", raw)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # Skip header comment blocks (every line starts with #)
        lines = block.split("\n")
        if all(line.lstrip().startswith("#") for line in lines if line.strip()):
            continue

        # The block may contain '#' header lines mixed with paragraph — drop comment lines first
        cleaned_block = "\n".join(line for line in lines if not line.lstrip().startswith("#")).strip()
        if not cleaned_block:
            continue

        match = PARAGRAPH_PREFIX_RE.match(cleaned_block)
        if not match:
            # Skip blocks that don't have [NN] prefix — they are not paragraphs
            continue

        idx = int(match.group(1))
        text = " ".join(match.group(2).split())  # normalize internal whitespace

        if idx in seen_idx:
            raise ValueError(f"Duplicate paragraph index in corpus: [{idx:02d}]")
        seen_idx.add(idx)

        paragraphs.append(Paragraph(idx=idx, text=text))

    if not paragraphs:
        raise ValueError(f"No paragraphs found in {path}. Check file format.")

    if expected_count is not None and len(paragraphs) != expected_count:
        raise ValueError(
            f"Expected {expected_count} paragraphs, found {len(paragraphs)}. "
            f"Indices loaded: {sorted(seen_idx)}"
        )

    paragraphs.sort(key=lambda p: p.idx)
    return paragraphs


def load_benchmark(
    path: Optional[Path] = None,
    expected_count: Optional[int] = EXPECTED_QUESTION_COUNT,
    expected_distribution: Optional[dict[str, int]] = None,
) -> list[BenchQuestion]:
    """Load and validate the benchmark questions JSON.

    Args:
        path: Override the default path from settings.
        expected_count: Strict count to validate. Defaults to EXPECTED_QUESTION_COUNT (20)
            for v1 backwards compatibility. Pass ``None`` to disable count validation.
        expected_distribution: Strict per-category counts. Defaults to EXPECTED_DISTRIBUTION
            (5 × 4 categories) for v1. Pass ``None`` to disable distribution validation.

    Returns:
        List of BenchQuestion objects in source order.

    Raises:
        FileNotFoundError: if benchmark file does not exist.
        ValueError: if structure is invalid, qid duplicates exist,
                    count != expected_count (when set), or category distribution wrong.
    """
    # Default distribution: v1 5×4 unless caller overrides or disables
    if expected_distribution is None and expected_count == EXPECTED_QUESTION_COUNT:
        expected_distribution = EXPECTED_DISTRIBUTION

    path = path or settings.benchmark_path
    if not path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if "questions" not in data:
        raise ValueError(f"Benchmark JSON missing top-level 'questions' key: {path}")

    raw_questions = data["questions"]
    if not isinstance(raw_questions, list):
        raise ValueError("'questions' must be a list")

    questions: list[BenchQuestion] = []
    seen_qid: set[str] = set()
    distribution: dict[str, int] = {cat: 0 for cat in VALID_CATEGORIES}

    for i, q in enumerate(raw_questions):
        # Required fields (source_paragraphs is optional for v2 questions)
        for required in ("qid", "category", "question", "gold_answer",
                         "gold_entities", "expected_hops"):
            if required not in q:
                raise ValueError(f"Question #{i} missing required field: {required}")

        category = q["category"]
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Question {q['qid']}: invalid category '{category}'")

        qid = q["qid"]
        if qid in seen_qid:
            raise ValueError(f"Duplicate qid: {qid}")
        seen_qid.add(qid)
        distribution[category] += 1

        questions.append(BenchQuestion(
            qid=qid,
            category=category,
            question=q["question"],
            gold_answer=q["gold_answer"],
            gold_entities=tuple(q["gold_entities"]),
            source_paragraphs=tuple(q.get("source_paragraphs", [])),
            expected_hops=int(q["expected_hops"]),
            reasoning_path=q.get("reasoning_path"),
            ambiguity_note=q.get("ambiguity_note"),
            hallucination_check=q.get("hallucination_check"),
        ))

    if expected_count is not None and len(questions) != expected_count:
        raise ValueError(
            f"Expected {expected_count} questions, found {len(questions)}"
        )

    if expected_distribution is not None and distribution != expected_distribution:
        raise ValueError(
            f"Category distribution mismatch. Expected {expected_distribution}, "
            f"got {distribution}"
        )

    return questions


# ----------------------------- Helpers -----------------------------

def corpus_stats(paragraphs: list[Paragraph]) -> dict:
    """Return summary stats about the corpus."""
    if not paragraphs:
        return {"n_paragraphs": 0}
    word_counts = [len(p.text.split()) for p in paragraphs]
    char_counts = [len(p.text) for p in paragraphs]
    return {
        "n_paragraphs": len(paragraphs),
        "total_words": sum(word_counts),
        "avg_words_per_paragraph": round(sum(word_counts) / len(paragraphs), 1),
        "total_chars": sum(char_counts),
        "min_words": min(word_counts),
        "max_words": max(word_counts),
    }


def benchmark_stats(questions: list[BenchQuestion]) -> dict:
    """Return summary stats about the benchmark."""
    distribution: dict[str, int] = {cat: 0 for cat in VALID_CATEGORIES}
    for q in questions:
        distribution[q.category] += 1
    return {
        "n_questions": len(questions),
        "by_category": distribution,
        "n_with_reasoning_path": sum(1 for q in questions if q.reasoning_path),
        "avg_expected_hops": round(
            sum(q.expected_hops for q in questions) / max(len(questions), 1), 2
        ),
    }
