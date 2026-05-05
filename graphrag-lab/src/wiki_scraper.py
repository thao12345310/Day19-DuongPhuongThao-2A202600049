"""Wikipedia Corpus Scraper (v2 expansion).

Fetches the summary section of ~100 Wikipedia articles for the GraphRAG Lab
v2 corpus. Writes plain-text paragraphs (with [NN] index prefix matching
the existing corpus loader format) plus a metadata JSON for traceability.

Usage:
    python -m src.wiki_scraper

Output:
    data/wiki_corpus.txt
    data/wiki_metadata.json

Implemented in TIP-008a.
"""
from __future__ import annotations
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import wikipedia

from src.config import PROJECT_ROOT


# ----------------------------- Constants -----------------------------

CORPUS_PATH = PROJECT_ROOT / "data" / "wiki_corpus.txt"
METADATA_PATH = PROJECT_ROOT / "data" / "wiki_metadata.json"
SLEEP_BETWEEN_CALLS_SEC = 0.5  # be polite to Wikipedia API
MAX_RETRIES = 3                 # retry on transient errors (rate limits)
MAX_PARAGRAPHS_PER_ARTICLE = 5  # only the summary section
MIN_PARAGRAPH_WORDS = 15        # drop trivially short paragraphs (e.g., section headings)
MAX_PARAGRAPH_WORDS = 120       # truncate to keep extraction cost predictable

ARTICLE_TARGETS: list[tuple[str, str]] = [
    # (anchor_company, wikipedia_search_term)
    # OpenAI cluster (10)
    ("OpenAI", "OpenAI"),
    ("OpenAI", "Sam Altman"),
    ("OpenAI", "Greg Brockman"),
    ("OpenAI", "Ilya Sutskever"),
    ("OpenAI", "Mira Murati"),
    ("OpenAI", "ChatGPT"),
    ("OpenAI", "GPT-4"),
    ("OpenAI", "DALL-E"),
    ("OpenAI", "Whisper (speech recognition system)"),
    ("OpenAI", "Y Combinator"),
    # Anthropic cluster (10)
    ("Anthropic", "Anthropic"),
    ("Anthropic", "Dario Amodei"),
    ("Anthropic", "Daniela Amodei"),
    ("Anthropic", "Claude (language model)"),
    ("Anthropic", "Constitutional AI"),
    ("Anthropic", "Reinforcement learning from human feedback"),
    ("Anthropic", "Effective altruism"),
    ("Anthropic", "Superintelligence"),
    ("Anthropic", "AI safety"),
    ("Anthropic", "Center for AI Safety"),
    # Google cluster (10)
    ("Google", "Google"),
    ("Google", "Sundar Pichai"),
    ("Google", "Larry Page"),
    ("Google", "Sergey Brin"),
    ("Google", "Alphabet Inc."),
    ("Google", "DeepMind"),
    ("Google", "Demis Hassabis"),
    ("Google", "AlphaGo"),
    ("Google", "AlphaFold"),
    ("Google", "Gemini (chatbot)"),
    # Microsoft cluster (10)
    ("Microsoft", "Microsoft"),
    ("Microsoft", "Satya Nadella"),
    ("Microsoft", "Bill Gates"),
    ("Microsoft", "Steve Ballmer"),
    ("Microsoft", "Microsoft Azure"),
    ("Microsoft", "GitHub"),
    ("Microsoft", "GitHub Copilot"),
    ("Microsoft", "LinkedIn"),
    ("Microsoft", "Reid Hoffman"),
    ("Microsoft", "Mustafa Suleyman"),
    # Meta cluster (10)
    ("Meta", "Meta Platforms"),
    ("Meta", "Mark Zuckerberg"),
    ("Meta", "Yann LeCun"),
    ("Meta", "Llama (language model)"),
    ("Meta", "Facebook"),
    ("Meta", "Instagram"),
    ("Meta", "WhatsApp"),
    ("Meta", "Reality Labs"),
    ("Meta", "Sheryl Sandberg"),
    ("Meta", "FAIR (research lab)"),
    # NVIDIA cluster (10)
    ("NVIDIA", "Nvidia"),
    ("NVIDIA", "Jensen Huang"),
    ("NVIDIA", "CUDA"),
    ("NVIDIA", "Graphics processing unit"),
    ("NVIDIA", "Hopper (microarchitecture)"),
    ("NVIDIA", "Blackwell (microarchitecture)"),
    ("NVIDIA", "Ampere (microarchitecture)"),
    ("NVIDIA", "TSMC"),
    ("NVIDIA", "Mellanox Technologies"),
    ("NVIDIA", "Arm Holdings"),
    # Apple cluster (10)
    ("Apple", "Apple Inc."),
    ("Apple", "Tim Cook"),
    ("Apple", "Steve Jobs"),
    ("Apple", "Steve Wozniak"),
    ("Apple", "IPhone"),
    ("Apple", "Apple silicon"),
    ("Apple", "Siri"),
    ("Apple", "Apple Intelligence"),
    ("Apple", "NeXT"),
    ("Apple", "Macintosh"),
    # Amazon cluster (10)
    ("Amazon", "Amazon (company)"),
    ("Amazon", "Jeff Bezos"),
    ("Amazon", "Andy Jassy"),
    ("Amazon", "Amazon Web Services"),
    ("Amazon", "Amazon Bedrock"),
    ("Amazon", "Amazon Alexa"),
    ("Amazon", "Blue Origin"),
    ("Amazon", "Whole Foods Market"),
    ("Amazon", "Twitch (service)"),
    ("Amazon", "Ring (company)"),
    # Tesla cluster (10)
    ("Tesla", "Tesla, Inc."),
    ("Tesla", "Elon Musk"),
    ("Tesla", "SpaceX"),
    ("Tesla", "X (social network)"),
    ("Tesla", "XAI (company)"),
    ("Tesla", "Grok (chatbot)"),
    ("Tesla", "Neuralink"),
    ("Tesla", "The Boring Company"),
    ("Tesla", "Optimus (robot)"),
    ("Tesla", "Tesla Cybertruck"),
    # IBM cluster (10)
    ("IBM", "IBM"),
    ("IBM", "Arvind Krishna"),
    ("IBM", "Watson (computer)"),
    ("IBM", "IBM Quantum Platform"),
    ("IBM", "Red Hat"),
    ("IBM", "Louis V. Gerstner Jr."),
    ("IBM", "Ginni Rometty"),
    ("IBM", "Deep Blue (chess computer)"),
    ("IBM", "IBM Personal Computer"),
    ("IBM", "Linux Foundation"),
]


# ----------------------------- Data classes -----------------------------

@dataclass
class ArticleMeta:
    """Metadata for one Wikipedia article in the corpus."""
    cluster: str           # anchor company (e.g., "OpenAI")
    search_term: str       # input search string
    resolved_title: str    # title actually returned by Wikipedia
    url: str
    paragraph_idx_start: int  # inclusive
    paragraph_idx_end: int    # inclusive
    n_paragraphs: int
    skipped: bool = False
    skip_reason: Optional[str] = None


# ----------------------------- Cleaning -----------------------------

CITATION_RE = re.compile(r"\[\d+\]")              # [1], [12]
PARENTHETICAL_REFS_RE = re.compile(r"\(\s*\)")    # empty parens left after citation removal
MULTI_SPACE_RE = re.compile(r"\s+")


def _clean_paragraph(text: str) -> str:
    """Strip Wikipedia citation markers and collapse whitespace."""
    text = CITATION_RE.sub("", text)
    text = PARENTHETICAL_REFS_RE.sub("", text)
    text = MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def _split_into_paragraphs(summary: str) -> list[str]:
    """Split the Wikipedia summary into paragraphs (one per blank line / newline run).

    Drops paragraphs shorter than MIN_PARAGRAPH_WORDS. Truncates paragraphs
    longer than MAX_PARAGRAPH_WORDS at the nearest sentence boundary so
    we do not blow up extraction cost.
    """
    raw = re.split(r"\n+", summary)
    cleaned: list[str] = []
    for p in raw:
        p = _clean_paragraph(p)
        if not p:
            continue
        words = p.split()
        if len(words) < MIN_PARAGRAPH_WORDS:
            continue
        if len(words) > MAX_PARAGRAPH_WORDS:
            # truncate at sentence boundary near the limit
            truncated = " ".join(words[:MAX_PARAGRAPH_WORDS])
            last_period = truncated.rfind(". ")
            if last_period > 0:
                truncated = truncated[:last_period + 1]
            p = truncated
        cleaned.append(p)
    return cleaned


# ----------------------------- Fetch one article -----------------------------

def _fetch_single(search_term: str, auto_suggest: bool) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Low-level fetch: try once with given auto_suggest setting."""
    try:
        page = wikipedia.page(search_term, auto_suggest=auto_suggest, redirect=True)
        return page.title, page.url, page.summary, None
    except wikipedia.DisambiguationError as e:
        # Try the first disambiguation option
        if e.options:
            try:
                page = wikipedia.page(e.options[0], auto_suggest=False, redirect=True)
                return page.title, page.url, page.summary, None
            except Exception as e2:
                return None, None, None, f"disambig fallback failed: {e2}"
        return None, None, None, "disambig with no options"
    except wikipedia.PageError:
        return None, None, None, "__PAGE_ERROR__"  # sentinel for retry with suggest
    except Exception as e:
        return None, None, None, f"{type(e).__name__}: {e}"


def _fetch_article(search_term: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Fetch one Wikipedia article with retry and fallback logic.

    Strategy:
    1. Try exact match (auto_suggest=False) — avoids mangled suggestions.
    2. If PageError, retry with auto_suggest=True as fallback.
    3. On transient errors (JSONDecodeError from rate limits), retry
       up to MAX_RETRIES times with exponential backoff.

    Returns:
        (resolved_title, url, summary_text, error_or_none)
    """
    last_err = None
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            time.sleep(1.0 * (2 ** (attempt - 1)))  # exponential backoff: 1s, 2s

        # Try exact match first
        title, url, summary, err = _fetch_single(search_term, auto_suggest=False)
        if err == "__PAGE_ERROR__":
            # Exact title not found — try with auto_suggest
            title, url, summary, err = _fetch_single(search_term, auto_suggest=True)
            if err == "__PAGE_ERROR__":
                return None, None, None, f"PageError: page not found for {search_term!r}"

        if err is None:
            return title, url, summary, None

        # Check if it's a transient error worth retrying
        if "JSONDecodeError" in (err or ""):
            last_err = err
            continue  # retry
        else:
            return title, url, summary, err  # non-transient error, give up

    return None, None, None, f"max retries exceeded: {last_err}"


# ----------------------------- Top-level scrape -----------------------------

def scrape_all(verbose: bool = True) -> tuple[list[str], list[ArticleMeta]]:
    """Scrape every target article, return (all_paragraphs, metadata_list).

    Paragraphs are flat across all articles; their original article ownership
    is recorded in metadata via paragraph_idx_start..paragraph_idx_end.

    The 1-based paragraph index matches the existing corpus format
    [01], [02], ..., so that downstream loaders can treat both v1 and v2
    corpora identically.
    """
    if len(ARTICLE_TARGETS) != 100:
        raise RuntimeError(
            f"ARTICLE_TARGETS must contain exactly 100 entries, got {len(ARTICLE_TARGETS)}. "
            "Did you forget to paste the full list from §2?"
        )

    all_paragraphs: list[str] = []
    metadata: list[ArticleMeta] = []

    for i, (cluster, term) in enumerate(ARTICLE_TARGETS, start=1):
        title, url, summary, err = _fetch_article(term)
        if err is not None or not summary:
            if verbose:
                print(f"  [{i:3d}/100] SKIP {term!r}: {err}", file=sys.stderr)
            metadata.append(ArticleMeta(
                cluster=cluster, search_term=term,
                resolved_title=title or "",
                url=url or "",
                paragraph_idx_start=-1, paragraph_idx_end=-1,
                n_paragraphs=0, skipped=True, skip_reason=err,
            ))
            time.sleep(SLEEP_BETWEEN_CALLS_SEC)
            continue

        paragraphs = _split_into_paragraphs(summary)[:MAX_PARAGRAPHS_PER_ARTICLE]
        if not paragraphs:
            if verbose:
                print(f"  [{i:3d}/100] SKIP {term!r}: no usable paragraphs after cleaning",
                      file=sys.stderr)
            metadata.append(ArticleMeta(
                cluster=cluster, search_term=term,
                resolved_title=title, url=url,
                paragraph_idx_start=-1, paragraph_idx_end=-1,
                n_paragraphs=0, skipped=True, skip_reason="no usable paragraphs",
            ))
            time.sleep(SLEEP_BETWEEN_CALLS_SEC)
            continue

        idx_start = len(all_paragraphs) + 1
        all_paragraphs.extend(paragraphs)
        idx_end = len(all_paragraphs)

        metadata.append(ArticleMeta(
            cluster=cluster, search_term=term,
            resolved_title=title, url=url,
            paragraph_idx_start=idx_start,
            paragraph_idx_end=idx_end,
            n_paragraphs=len(paragraphs),
            skipped=False,
        ))

        if verbose and i % 10 == 0:
            print(f"  [{i:3d}/100] {len(all_paragraphs)} paragraphs collected so far")

        time.sleep(SLEEP_BETWEEN_CALLS_SEC)

    return all_paragraphs, metadata


# ----------------------------- Output writers -----------------------------

def write_corpus_file(paragraphs: list[str], path: Path = CORPUS_PATH) -> Path:
    """Write paragraphs to text file with [NN] prefix matching v1 format."""
    if not paragraphs:
        raise ValueError("Cannot write empty paragraph list")
    width = max(2, len(str(len(paragraphs))))
    lines = [
        "# Wikipedia Tech Company Corpus (v2)",
        f"# {len(paragraphs)} paragraphs scraped from ~100 Wikipedia articles",
        "# Generated by src/wiki_scraper.py",
        "# ====================================================",
        "",
    ]
    for i, p in enumerate(paragraphs, start=1):
        lines.append(f"[{i:0{width}d}] {p}")
        lines.append("")  # blank line separator
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_metadata_file(metadata: list[ArticleMeta], path: Path = METADATA_PATH) -> Path:
    """Write per-article metadata JSON for traceability + later analysis."""
    payload = {
        "version": 2,
        "n_articles_targeted": len(ARTICLE_TARGETS),
        "n_articles_succeeded": sum(1 for m in metadata if not m.skipped),
        "n_articles_skipped": sum(1 for m in metadata if m.skipped),
        "articles": [asdict(m) for m in metadata],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def scrape_and_write(verbose: bool = True) -> dict:
    """Top-level convenience: scrape, write both files, return summary stats."""
    paragraphs, metadata = scrape_all(verbose=verbose)
    if not paragraphs:
        raise RuntimeError("Scrape produced 0 usable paragraphs — check network or target list.")
    corpus_path = write_corpus_file(paragraphs)
    meta_path = write_metadata_file(metadata)
    return {
        "n_paragraphs": len(paragraphs),
        "n_articles_succeeded": sum(1 for m in metadata if not m.skipped),
        "n_articles_skipped": sum(1 for m in metadata if m.skipped),
        "corpus_path": str(corpus_path),
        "metadata_path": str(meta_path),
        "skipped_titles": [m.search_term for m in metadata if m.skipped],
    }


if __name__ == "__main__":
    stats = scrape_and_write(verbose=True)
    print(json.dumps(stats, indent=2))
