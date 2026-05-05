"""Script to add §7 and §8 cells to lab19_main.ipynb for TIP-007."""
import json
from pathlib import Path

NB_PATH = Path(__file__).parent / "notebooks" / "lab19_main.ipynb"

nb = json.loads(NB_PATH.read_text(encoding="utf-8"))

# New cells to add — §7 (6 cells) + §8 (3 cells) = 9 cells total
new_cells = [
    # §7.1 — markdown
    {
        "cell_type": "markdown",
        "id": "tip007_s7_md",
        "metadata": {},
        "source": [
            "## §7 — Full 20-Question Benchmark\n",
            "\n",
            "We now run the full 20-question benchmark across both systems with auto-grading\n",
            "by a third LLM (`gpt-4o-mini`) acting as judge. Each row of the resulting CSV\n",
            "includes both system answers, correctness flags, hallucination flags, and\n",
            "per-question cost / latency.\n",
            "\n",
            "> ⚠️ This cell makes ~80 API calls (20 Q × 4 = NER + answer + judge × 2 systems, minus shared judge).\n",
            "> Estimated runtime: 2–4 minutes. Estimated cost: $0.03–0.05."
        ]
    },
    # §7.2 — code: run benchmark
    {
        "cell_type": "code",
        "execution_count": None,
        "id": "tip007_s72_run",
        "metadata": {},
        "outputs": [],
        "source": [
            "from src.benchmark import run_benchmark, summarize, hallucination_examples\n",
            "import pandas as pd\n",
            "\n",
            "df = run_benchmark(questions=questions, verbose=True)\n",
            "print(f\"\\n✓ Benchmark complete. Saved to: {PROJECT_ROOT / 'results' / 'benchmark_table.csv'}\")"
        ]
    },
    # §7.3 — code: aggregate summary
    {
        "cell_type": "code",
        "execution_count": None,
        "id": "tip007_s73_summary",
        "metadata": {},
        "outputs": [],
        "source": [
            "# Aggregate summary\n",
            "s = summarize(df)\n",
            "print(f\"GraphRAG accuracy:           {s['graph_accuracy']*100:5.1f}% \"\n",
            "      f\"({int(df['graph_correct'].sum())}/{s['n_questions']})\")\n",
            "print(f\"Flat RAG accuracy:           {s['flat_accuracy']*100:5.1f}% \"\n",
            "      f\"({int(df['flat_correct'].sum())}/{s['n_questions']})\")\n",
            "print(f\"GraphRAG hallucination rate: {s['graph_hallucination_rate']*100:5.1f}%\")\n",
            "print(f\"Flat RAG hallucination rate: {s['flat_hallucination_rate']*100:5.1f}%\")\n",
            "print()\n",
            "print(\"By category (correct / hallucinated, out of 5):\")\n",
            "for cat, vals in s[\"by_category\"].items():\n",
            "    print(f\"  {cat:<14}  Graph: {int(vals['graph_correct'])}/{int(vals['n'])} correct, \"\n",
            "          f\"{int(vals['graph_hallucinated'])} halluc | \"\n",
            "          f\"Flat: {int(vals['flat_correct'])}/{int(vals['n'])} correct, \"\n",
            "          f\"{int(vals['flat_hallucinated'])} halluc\")"
        ]
    },
    # §7.4 — code: quick view table
    {
        "cell_type": "code",
        "execution_count": None,
        "id": "tip007_s74_table",
        "metadata": {},
        "outputs": [],
        "source": [
            "# Quick view of the table — qid, category, both answers truncated, both correct flags\n",
            "view_cols = [\"qid\", \"category\", \"graph_answer\", \"graph_correct\",\n",
            "             \"flat_answer\", \"flat_correct\"]\n",
            "view = df[view_cols].copy()\n",
            "view[\"graph_answer\"] = view[\"graph_answer\"].str.slice(0, 60)\n",
            "view[\"flat_answer\"]  = view[\"flat_answer\"].str.slice(0, 60)\n",
            "view"
        ]
    },
    # §7.5 — code: bar chart
    {
        "cell_type": "code",
        "execution_count": None,
        "id": "tip007_s75_chart",
        "metadata": {},
        "outputs": [],
        "source": [
            "# Bar chart: accuracy per category\n",
            "import matplotlib.pyplot as plt\n",
            "import numpy as np\n",
            "\n",
            "cats = list(s[\"by_category\"].keys())\n",
            "g_acc = [s[\"by_category\"][c][\"graph_correct\"] / s[\"by_category\"][c][\"n\"] * 100 for c in cats]\n",
            "f_acc = [s[\"by_category\"][c][\"flat_correct\"] / s[\"by_category\"][c][\"n\"] * 100 for c in cats]\n",
            "\n",
            "x = np.arange(len(cats))\n",
            "w = 0.38\n",
            "\n",
            "fig, ax = plt.subplots(figsize=(10, 5))\n",
            "b1 = ax.bar(x - w/2, g_acc, w, label=\"GraphRAG\", color=\"#4F8DFD\")\n",
            "b2 = ax.bar(x + w/2, f_acc, w, label=\"Flat RAG\", color=\"#F7B538\")\n",
            "for bars in (b1, b2):\n",
            "    for b in bars:\n",
            "        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1,\n",
            "                f\"{b.get_height():.0f}%\", ha=\"center\", fontsize=9)\n",
            "ax.set_xticks(x)\n",
            "ax.set_xticklabels(cats, rotation=15)\n",
            "ax.set_ylabel(\"Accuracy (%)\")\n",
            "ax.set_ylim(0, 110)\n",
            "ax.set_title(\"Accuracy by question category — GraphRAG vs Flat RAG\")\n",
            "ax.legend()\n",
            "ax.grid(axis=\"y\", alpha=0.3)\n",
            "plt.tight_layout()\n",
            "chart_path = PROJECT_ROOT / \"screenshots\" / \"accuracy_by_category.png\"\n",
            "plt.savefig(chart_path, dpi=150, bbox_inches=\"tight\")\n",
            "plt.show()\n",
            "print(f\"✓ Chart saved to: {chart_path}\")"
        ]
    },
    # §7.6 — code: hallucination examples
    {
        "cell_type": "code",
        "execution_count": None,
        "id": "tip007_s76_examples",
        "metadata": {},
        "outputs": [],
        "source": [
            "# Headline examples: cases where Flat RAG hallucinated but GraphRAG did not\n",
            "examples = hallucination_examples(df, max_each=5)\n",
            "if examples:\n",
            "    print(f\"Found {len(examples)} cases where Flat RAG hallucinated and GraphRAG did not:\\n\")\n",
            "    for ex in examples:\n",
            "        print(f\"[{ex['qid']} | {ex['category']}] {ex['question']}\")\n",
            "        print(f\"  Gold:      {ex['gold_answer']}\")\n",
            "        print(f\"  Flat RAG:  {ex['flat_answer']}\")\n",
            "        print(f\"  GraphRAG:  {ex['graph_answer']}\")\n",
            "        print()\n",
            "else:\n",
            "    print(\"No cases found where Flat RAG hallucinated but GraphRAG did not.\")\n",
            "    print(\"(This may happen if Flat RAG also abstained reliably — still a valid result.)\")"
        ]
    },
    # §8.1 — markdown
    {
        "cell_type": "markdown",
        "id": "tip007_s81_md",
        "metadata": {},
        "source": [
            "## §8 — Cost Analysis (Deliverable #4)\n",
            "\n",
            "We use the cost log accumulated across every API call to produce a\n",
            "detailed Markdown breakdown of token usage, cost, and latency by phase."
        ]
    },
    # §8.2 — code: write cost analysis
    {
        "cell_type": "code",
        "execution_count": None,
        "id": "tip007_s82_cost",
        "metadata": {},
        "outputs": [],
        "source": [
            "from src.benchmark import write_cost_analysis\n",
            "md_path = write_cost_analysis(df)\n",
            "print(f\"✓ Cost analysis written to: {md_path}\\n\")\n",
            "print(md_path.read_text())"
        ]
    },
    # §8.3 — markdown milestone
    {
        "cell_type": "markdown",
        "id": "tip007_s83_milestone",
        "metadata": {},
        "source": [
            "---\n",
            "✅ **Milestone TIP-007:** Benchmark CSV (Deliverable #3) and Cost Analysis MD (Deliverable #4) generated. Ready for final notebook polish (TIP-008).\n",
            "\n",
            "---"
        ]
    },
]

nb["cells"].extend(new_cells)

NB_PATH.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"✓ Added {len(new_cells)} cells to {NB_PATH}")
print(f"  Total cells now: {len(nb['cells'])}")
