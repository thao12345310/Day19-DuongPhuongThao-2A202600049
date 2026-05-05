"""M5 — Benchmark Runner + Auto-Grader + Cost Analysis.

Runs the 20-question benchmark across both systems (GraphRAG, Flat RAG),
auto-grades with a judge LLM, captures per-question cost via cost-log
deltas, and writes the two main lab deliverables:

  Deliverable #3: results/benchmark_table.csv
  Deliverable #4: results/cost_analysis.md

Implemented in TIP-007.
"""
from __future__ import annotations
import json
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import settings
from src.corpus_builder import BenchQuestion, load_benchmark
from src.cost_tracker import (
    track_llm_call, read_cost_log, cost_summary,
)
from src.extractor import get_client
from src.graph_rag import query as graph_rag_query
from src.flat_rag import query as flat_rag_query


# ----------------------------- Judge prompt -----------------------------

JUDGE_SYSTEM_PROMPT = """You are an impartial grader for a knowledge-base QA benchmark.

Given:
- A QUESTION
- A GOLD ANSWER (ground truth)
- A PREDICTED ANSWER from a system

Return ONLY a JSON object with these fields:
{"correct": true | false, "hallucinated": true | false, "note": "<one short sentence>"}

Rules:
- correct=true if the PREDICTED ANSWER conveys the same factual content as the GOLD ANSWER. Different phrasings, different orderings, partial but accurate answers, and answers with extra-but-true context all count as correct. Subset answers for AMBIGUOUS questions are correct if at least one valid item is given.
- correct=false if the PREDICTED ANSWER is factually wrong, contradicts the gold, or refuses to answer when the gold has a real answer.
- hallucinated=true if the PREDICTED ANSWER asserts a specific fact that is NOT supported by the gold (especially for OUT-OF-DOMAIN questions where the gold is "Not enough information"). Refusals like "I don't know" / "not enough information" are NOT hallucinations.
- For OUT-OF-DOMAIN questions, correct=true MEANS the system refused to answer (and is therefore not hallucinated). correct=false means it gave a specific made-up answer (and is therefore hallucinated).
- note: ONE short sentence explaining the verdict.
"""


def _build_judge_prompt(question: str, gold: str, predicted: str, category: str) -> str:
    return (
        f"CATEGORY: {category}\n"
        f"QUESTION: {question}\n"
        f"GOLD ANSWER: {gold}\n"
        f"PREDICTED ANSWER: {predicted}\n\n"
        f"Output:"
    )


@track_llm_call(module="judge")
def _call_judge_api(question: str, gold: str, predicted: str, category: str) -> object:
    return get_client().chat.completions.create(
        model=settings.llm_model,
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": _build_judge_prompt(question, gold, predicted, category)},
        ],
    )


@dataclass
class JudgeVerdict:
    correct: bool
    hallucinated: bool
    note: str


def grade(question: str, gold: str, predicted: str, category: str) -> JudgeVerdict:
    """Grade a predicted answer against gold. Defaults to a conservative verdict on parse failure."""
    try:
        resp = _call_judge_api(question, gold, predicted, category)
        content = resp.choices[0].message.content  # type: ignore
        data = json.loads(content) if content else {}
        return JudgeVerdict(
            correct=bool(data.get("correct", False)),
            hallucinated=bool(data.get("hallucinated", False)),
            note=str(data.get("note", ""))[:200],
        )
    except Exception as e:
        return JudgeVerdict(
            correct=False,
            hallucinated=False,
            note=f"[grading error: {e}]"[:200],
        )


# ----------------------------- Per-question cost delta -----------------------------

def _cost_log_snapshot() -> int:
    """Return the current row count of the cost log."""
    return len(read_cost_log())


def _delta_cost_and_tokens(start_row: int) -> tuple[float, int, int, int]:
    """Compute (cost_usd, tokens_in, tokens_out, latency_ms) over rows
    appended since start_row.
    """
    rows = read_cost_log()[start_row:]
    cost = sum(float(r["cost_usd"]) for r in rows)
    t_in = sum(int(r["tokens_in"]) for r in rows)
    t_out = sum(int(r["tokens_out"]) for r in rows)
    lat = sum(int(r["latency_ms"]) for r in rows)
    return cost, t_in, t_out, lat


# ----------------------------- Benchmark runner -----------------------------

def run_one_question(q: BenchQuestion) -> dict:
    """Run both systems on one question and return a flat dict row.

    Cost / latency are captured via cost-log deltas around each call,
    so per-question numbers are precise even when the global cost log
    is shared with extraction + indexing rows.
    """
    # ---- GraphRAG
    snap_g = _cost_log_snapshot()
    t0 = time.time()
    g_result = graph_rag_query(q.question)
    g_wall_ms = int((time.time() - t0) * 1000)
    g_cost, g_in, g_out, g_lat = _delta_cost_and_tokens(snap_g)

    # ---- Flat RAG
    snap_f = _cost_log_snapshot()
    t0 = time.time()
    f_result = flat_rag_query(q.question)
    f_wall_ms = int((time.time() - t0) * 1000)
    f_cost, f_in, f_out, f_lat = _delta_cost_and_tokens(snap_f)

    # ---- Judge each prediction
    g_verdict = grade(q.question, q.gold_answer, g_result.answer, q.category)
    f_verdict = grade(q.question, q.gold_answer, f_result.answer, q.category)

    return {
        "qid": q.qid,
        "category": q.category,
        "question": q.question,
        "gold_answer": q.gold_answer,
        "expected_hops": q.expected_hops,
        # GraphRAG outputs
        "graph_answer": g_result.answer,
        "graph_correct": g_verdict.correct,
        "graph_hallucinated": g_verdict.hallucinated,
        "graph_judge_note": g_verdict.note,
        "graph_n_edges": len(g_result.edges),
        "graph_matched_entities": "; ".join(g_result.matched_entity_names),
        "graph_tokens_in": g_in,
        "graph_tokens_out": g_out,
        "graph_cost_usd": round(g_cost, 6),
        "graph_wall_ms": g_wall_ms,
        # Flat RAG outputs
        "flat_answer": f_result.answer,
        "flat_correct": f_verdict.correct,
        "flat_hallucinated": f_verdict.hallucinated,
        "flat_judge_note": f_verdict.note,
        "flat_top_idxs": "; ".join(str(idx) for idx, _, _ in f_result.retrieved_paragraphs),
        "flat_tokens_in": f_in,
        "flat_tokens_out": f_out,
        "flat_cost_usd": round(f_cost, 6),
        "flat_wall_ms": f_wall_ms,
    }


def run_benchmark(
    questions: list[BenchQuestion] | None = None,
    output_csv: Path | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Run the full benchmark and write a CSV (Deliverable #3).

    Args:
        questions: Override list. If None, loaded via load_benchmark().
        output_csv: Override path. If None, settings.results_dir / "benchmark_table.csv".
        verbose: Print progress per question.

    Returns:
        DataFrame with one row per question.
    """
    questions = questions or load_benchmark()
    output_csv = output_csv or (settings.results_dir / "benchmark_table.csv")

    rows = []
    for i, q in enumerate(questions, start=1):
        row = run_one_question(q)
        rows.append(row)
        if verbose:
            g_mark = "✓" if row["graph_correct"] else "✗"
            f_mark = "✓" if row["flat_correct"] else "✗"
            print(f"  [{i:2d}/{len(questions)}] {q.qid} {q.category:14s} "
                  f"GraphRAG:{g_mark} FlatRAG:{f_mark}")

    df = pd.DataFrame(rows)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    return df


# ----------------------------- Aggregation & reporting -----------------------------

def summarize(df: pd.DataFrame) -> dict:
    """Compute aggregate metrics from the benchmark DataFrame."""
    n = len(df)
    g_correct = int(df["graph_correct"].sum())
    f_correct = int(df["flat_correct"].sum())
    g_halluc = int(df["graph_hallucinated"].sum())
    f_halluc = int(df["flat_hallucinated"].sum())

    by_category = (
        df.groupby("category")
          .agg(
              graph_correct=("graph_correct", "sum"),
              flat_correct=("flat_correct", "sum"),
              graph_hallucinated=("graph_hallucinated", "sum"),
              flat_hallucinated=("flat_hallucinated", "sum"),
              n=("qid", "count"),
          )
          .to_dict(orient="index")
    )
    return {
        "n_questions": n,
        "graph_accuracy": g_correct / max(n, 1),
        "flat_accuracy": f_correct / max(n, 1),
        "graph_hallucination_rate": g_halluc / max(n, 1),
        "flat_hallucination_rate": f_halluc / max(n, 1),
        "graph_total_cost_usd": float(df["graph_cost_usd"].sum()),
        "flat_total_cost_usd": float(df["flat_cost_usd"].sum()),
        "graph_avg_latency_ms": float(df["graph_wall_ms"].mean()),
        "flat_avg_latency_ms": float(df["flat_wall_ms"].mean()),
        "by_category": by_category,
    }


def hallucination_examples(df: pd.DataFrame, max_each: int = 3) -> list[dict]:
    """Return the rows where Flat RAG hallucinated AND GraphRAG did not.

    These are the headline examples for the lab's writeup — they
    directly demonstrate the GraphRAG advantage.
    """
    mask = (df["flat_hallucinated"] == True) & (df["graph_hallucinated"] == False)
    rows = df[mask].head(max_each)
    return [
        {
            "qid": r["qid"],
            "category": r["category"],
            "question": r["question"],
            "gold_answer": r["gold_answer"],
            "flat_answer": r["flat_answer"],
            "graph_answer": r["graph_answer"],
        }
        for _, r in rows.iterrows()
    ]


# ----------------------------- Cost analysis writer -----------------------------

def write_cost_analysis(
    df: pd.DataFrame,
    output_md: Path | None = None,
) -> Path:
    """Write Deliverable #4: results/cost_analysis.md.

    Pulls from:
      - the benchmark DataFrame (per-question cost from cost-log deltas)
      - the global cost log (for the indexing/extraction one-time costs)
    """
    output_md = output_md or (settings.results_dir / "cost_analysis.md")
    s = summarize(df)
    cs = cost_summary()  # global by-module breakdown

    extractor_row = cs["by_module"].get("extractor", {})
    flat_index_row = cs["by_module"].get("flat_rag_index", {})
    judge_row = cs["by_module"].get("judge", {})

    lines: list[str] = []
    lines.append("# Cost Analysis — GraphRAG Lab Day 19")
    lines.append("")
    lines.append("This file is auto-generated by `src/benchmark.py:write_cost_analysis()`.")
    lines.append("")
    lines.append("## 1. One-time indexing costs")
    lines.append("")
    lines.append("| Stage | Calls | Tokens in | Tokens out | Cost (USD) | Latency (s) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    lines.append(
        f"| GraphRAG triple extraction | "
        f"{extractor_row.get('calls', 0)} | "
        f"{extractor_row.get('tokens_in', 0):,} | "
        f"{extractor_row.get('tokens_out', 0):,} | "
        f"${extractor_row.get('cost_usd', 0):.4f} | "
        f"{extractor_row.get('latency_ms', 0) / 1000:.1f} |"
    )
    lines.append(
        f"| Flat RAG embedding indexing | "
        f"{flat_index_row.get('calls', 0)} | "
        f"{flat_index_row.get('tokens_in', 0):,} | "
        f"{flat_index_row.get('tokens_out', 0):,} | "
        f"${flat_index_row.get('cost_usd', 0):.4f} | "
        f"{flat_index_row.get('latency_ms', 0) / 1000:.1f} |"
    )
    lines.append("")
    lines.append("## 2. Per-question runtime cost (20 questions)")
    lines.append("")
    lines.append("| System | Total cost | Avg cost / Q | Avg latency / Q | Tokens in (sum) | Tokens out (sum) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    lines.append(
        f"| GraphRAG | "
        f"${s['graph_total_cost_usd']:.4f} | "
        f"${s['graph_total_cost_usd'] / max(s['n_questions'], 1):.5f} | "
        f"{s['graph_avg_latency_ms'] / 1000:.2f} s | "
        f"{int(df['graph_tokens_in'].sum()):,} | "
        f"{int(df['graph_tokens_out'].sum()):,} |"
    )
    lines.append(
        f"| Flat RAG | "
        f"${s['flat_total_cost_usd']:.4f} | "
        f"${s['flat_total_cost_usd'] / max(s['n_questions'], 1):.5f} | "
        f"{s['flat_avg_latency_ms'] / 1000:.2f} s | "
        f"{int(df['flat_tokens_in'].sum()):,} | "
        f"{int(df['flat_tokens_out'].sum()):,} |"
    )
    lines.append("")
    lines.append("## 3. Auto-grading overhead (judge model)")
    lines.append("")
    lines.append(
        f"- Judge calls: {judge_row.get('calls', 0)}\n"
        f"- Judge cost: ${judge_row.get('cost_usd', 0):.4f}\n"
        f"- Judge latency: {judge_row.get('latency_ms', 0) / 1000:.1f}s"
    )
    lines.append("")
    lines.append("## 4. Grand total")
    lines.append("")
    lines.append(
        f"- **All API calls:** {cs['total_calls']}\n"
        f"- **Total tokens in:** {cs['total_tokens_in']:,}\n"
        f"- **Total tokens out:** {cs['total_tokens_out']:,}\n"
        f"- **Total cost (USD):** ${cs['total_cost_usd']:.4f}\n"
        f"- **Total wall-clock latency (sum across all calls):** {cs['total_latency_ms'] / 1000:.0f}s"
    )
    lines.append("")
    lines.append("## 5. Headline observations")
    lines.append("")
    lines.append(
        f"- GraphRAG accuracy: **{s['graph_accuracy'] * 100:.0f}%** "
        f"({sum(int(v['graph_correct']) for v in s['by_category'].values())}/{s['n_questions']})"
    )
    lines.append(
        f"- Flat RAG accuracy: **{s['flat_accuracy'] * 100:.0f}%** "
        f"({sum(int(v['flat_correct']) for v in s['by_category'].values())}/{s['n_questions']})"
    )
    lines.append(
        f"- GraphRAG hallucination rate: **{s['graph_hallucination_rate'] * 100:.0f}%**"
    )
    lines.append(
        f"- Flat RAG hallucination rate: **{s['flat_hallucination_rate'] * 100:.0f}%**"
    )
    lines.append("")
    lines.append("## 6. Per-category breakdown")
    lines.append("")
    lines.append("| Category | n | GraphRAG correct | Flat RAG correct | GraphRAG halluc | Flat RAG halluc |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cat, vals in s["by_category"].items():
        lines.append(
            f"| {cat} | {int(vals['n'])} | "
            f"{int(vals['graph_correct'])} | "
            f"{int(vals['flat_correct'])} | "
            f"{int(vals['graph_hallucinated'])} | "
            f"{int(vals['flat_hallucinated'])} |"
        )
    lines.append("")

    examples = hallucination_examples(df, max_each=3)
    if examples:
        lines.append("## 7. Cases where Flat RAG hallucinated and GraphRAG did not")
        lines.append("")
        for ex in examples:
            lines.append(f"### {ex['qid']} ({ex['category']})")
            lines.append(f"**Question:** {ex['question']}")
            lines.append(f"**Gold:** {ex['gold_answer']}")
            lines.append(f"**Flat RAG (hallucinated):** {ex['flat_answer']}")
            lines.append(f"**GraphRAG:** {ex['graph_answer']}")
            lines.append("")

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines), encoding="utf-8")
    return output_md
