"""Append §11 cells to lab19_main.ipynb for TIP-008c."""
import json, copy

NB_PATH = "notebooks/lab19_main.ipynb"

with open(NB_PATH) as f:
    nb = json.load(f)

def md_cell(source_lines):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source_lines,
    }

def code_cell(source_lines):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source_lines,
    }

new_cells = []

# §11.1 — markdown
new_cells.append(md_cell([
    "## §11 — V2 Benchmark Run (30 Questions)\n",
    "\n",
    "The v2 benchmark uses 30 carefully designed questions:\n",
    "- 7 single-hop (direct facts)\n",
    "- 10 multi-hop (require cross-document graph traversal — the centerpiece test)\n",
    "- 7 ambiguous (multiple valid answers)\n",
    "- 6 out-of-domain (must abstain)\n",
    "\n",
    "Questions are designed against entities actually present in the v2 graph\n",
    "(top hubs include Apple, Amazon, IBM, Google, Microsoft, NVIDIA, OpenAI,\n",
    "Meta, Facebook, Alphabet) — avoiding clusters with scrape gaps (Anthropic\n",
    "deep facts, Tesla periphery).\n",
    "\n",
    "> ⚠️ This cell makes ~180 API calls (~$0.06–0.10, ~6 minutes wall time)."
]))

# §11.2 — code: Load v2 questions
new_cells.append(code_cell([
    "# Load v2 questions (30 total, 7+10+7+6 distribution)\n",
    "v2_benchmark_path = PROJECT_ROOT / \"data\" / \"benchmark_questions_v2.json\"\n",
    "\n",
    "questions_v2 = load_benchmark(\n",
    "    path=v2_benchmark_path,\n",
    "    expected_count=30,\n",
    "    expected_distribution={\n",
    "        \"single_hop\": 7,\n",
    "        \"multi_hop\": 10,\n",
    "        \"ambiguous\": 7,\n",
    "        \"out_of_domain\": 6,\n",
    "    },\n",
    ")\n",
    "print(f\"✓ Loaded {len(questions_v2)} v2 benchmark questions.\")\n",
    "\n",
    "# Quick preview\n",
    "from collections import Counter\n",
    "cat_counts = Counter(q.category for q in questions_v2)\n",
    "print(f\"  Distribution: {dict(cat_counts)}\")\n",
    "print(f\"\\n  Sample questions:\")\n",
    "seen_cats = set()\n",
    "for q in questions_v2:\n",
    "    if q.category not in seen_cats:\n",
    "        seen_cats.add(q.category)\n",
    "        print(f\"  [{q.qid} | {q.category:14s}] {q.question}\")"
]))

# §11.3 — code: Run v2 benchmark
new_cells.append(code_cell([
    "# Run v2 benchmark\n",
    "from src.benchmark import run_benchmark, summarize, hallucination_examples\n",
    "\n",
    "v2_csv_path = PROJECT_ROOT / \"results\" / \"benchmark_table_v2.csv\"\n",
    "\n",
    "print(\"Running v2 benchmark on 30 questions × 2 systems...\")\n",
    "df_v2 = run_benchmark(\n",
    "    questions=questions_v2,\n",
    "    output_csv=v2_csv_path,\n",
    "    verbose=True,\n",
    ")\n",
    "print(f\"\\n✓ V2 benchmark complete. Saved to: {v2_csv_path}\")\n",
    "print(f\"  Shape: {df_v2.shape}\")"
]))

# §11.4 — code: V2 aggregate summary
new_cells.append(code_cell([
    "# V2 aggregate summary\n",
    "s2 = summarize(df_v2)\n",
    "print(f\"GraphRAG accuracy:           {s2['graph_accuracy']*100:5.1f}% \"\n",
    "      f\"({int(df_v2['graph_correct'].sum())}/{s2['n_questions']})\")\n",
    "print(f\"Flat RAG accuracy:           {s2['flat_accuracy']*100:5.1f}% \"\n",
    "      f\"({int(df_v2['flat_correct'].sum())}/{s2['n_questions']})\")\n",
    "print(f\"GraphRAG hallucination rate: {s2['graph_hallucination_rate']*100:5.1f}%\")\n",
    "print(f\"Flat RAG hallucination rate: {s2['flat_hallucination_rate']*100:5.1f}%\")\n",
    "print()\n",
    "print(\"By category (correct / hallucinated):\")\n",
    "for cat, vals in s2[\"by_category\"].items():\n",
    "    print(f\"  {cat:<14}  Graph: {int(vals['graph_correct'])}/{int(vals['n'])} correct, \"\n",
    "          f\"{int(vals['graph_hallucinated'])} halluc | \"\n",
    "          f\"Flat: {int(vals['flat_correct'])}/{int(vals['n'])} correct, \"\n",
    "          f\"{int(vals['flat_hallucinated'])} halluc\")"
]))

# §11.5 — code: Truncated v2 benchmark table view
new_cells.append(code_cell([
    "# Truncated v2 benchmark table view\n",
    "view_cols = [\"qid\", \"category\", \"graph_answer\", \"graph_correct\",\n",
    "             \"flat_answer\", \"flat_correct\"]\n",
    "view_v2 = df_v2[view_cols].copy()\n",
    "view_v2[\"graph_answer\"] = view_v2[\"graph_answer\"].str.slice(0, 60)\n",
    "view_v2[\"flat_answer\"]  = view_v2[\"flat_answer\"].str.slice(0, 60)\n",
    "view_v2"
]))

# §11.6 — code: Bar chart v2
new_cells.append(code_cell([
    "# Bar chart: v2 accuracy per category\n",
    "import matplotlib.pyplot as plt\n",
    "import numpy as np\n",
    "\n",
    "cats_v2 = list(s2[\"by_category\"].keys())\n",
    "g_acc_v2 = [s2[\"by_category\"][c][\"graph_correct\"] / s2[\"by_category\"][c][\"n\"] * 100\n",
    "            for c in cats_v2]\n",
    "f_acc_v2 = [s2[\"by_category\"][c][\"flat_correct\"] / s2[\"by_category\"][c][\"n\"] * 100\n",
    "            for c in cats_v2]\n",
    "\n",
    "x = np.arange(len(cats_v2))\n",
    "w = 0.38\n",
    "\n",
    "fig, ax = plt.subplots(figsize=(10, 5))\n",
    "b1 = ax.bar(x - w/2, g_acc_v2, w, label=\"GraphRAG\", color=\"#4F8DFD\")\n",
    "b2 = ax.bar(x + w/2, f_acc_v2, w, label=\"Flat RAG\", color=\"#F7B538\")\n",
    "for bars in (b1, b2):\n",
    "    for b in bars:\n",
    "        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1,\n",
    "                f\"{b.get_height():.0f}%\", ha=\"center\", fontsize=9)\n",
    "ax.set_xticks(x)\n",
    "ax.set_xticklabels(cats_v2, rotation=15)\n",
    "ax.set_ylabel(\"Accuracy (%)\")\n",
    "ax.set_ylim(0, 110)\n",
    "ax.set_title(\"V2 Wikipedia Corpus — Accuracy by Category (GraphRAG vs Flat RAG, 30 Q)\")\n",
    "ax.legend()\n",
    "ax.grid(axis=\"y\", alpha=0.3)\n",
    "plt.tight_layout()\n",
    "chart_v2_path = PROJECT_ROOT / \"screenshots\" / \"accuracy_by_category_v2.png\"\n",
    "plt.savefig(chart_v2_path, dpi=150, bbox_inches=\"tight\")\n",
    "plt.show()\n",
    "print(f\"✓ Chart saved to: {chart_v2_path}\")"
]))

# §11.7 — code: Hallucination examples
new_cells.append(code_cell([
    "# Hallucination examples — Flat RAG halluc, GraphRAG not (the lab's \"wow\" moments)\n",
    "examples_v2 = hallucination_examples(df_v2, max_each=8)\n",
    "if examples_v2:\n",
    "    print(f\"Found {len(examples_v2)} cases where Flat RAG hallucinated and GraphRAG did not:\\n\")\n",
    "    for ex in examples_v2:\n",
    "        print(f\"[{ex['qid']} | {ex['category']}] {ex['question']}\")\n",
    "        print(f\"  Gold:      {ex['gold_answer']}\")\n",
    "        print(f\"  Flat RAG:  {ex['flat_answer'][:200]}\")\n",
    "        print(f\"  GraphRAG:  {ex['graph_answer'][:200]}\")\n",
    "        print()\n",
    "else:\n",
    "    print(\"No cases found where Flat RAG hallucinated but GraphRAG did not.\")\n",
    "    print(\"(This may be a valid result if both systems abstained appropriately.)\")"
]))

# §11.8 — code: Write v2 cost analysis MD
new_cells.append(code_cell([
    "# Write v2 cost analysis MD\n",
    "from src.benchmark import write_cost_analysis\n",
    "\n",
    "v2_md_path = PROJECT_ROOT / \"results\" / \"cost_analysis_v2.md\"\n",
    "write_cost_analysis(df_v2, output_md=v2_md_path)\n",
    "print(f\"✓ V2 cost analysis written to: {v2_md_path}\\n\")\n",
    "print(v2_md_path.read_text()[:3000])\n",
    "print(\"\\n... (truncated; full file on disk)\")"
]))

# §11.9 — code: V1 vs V2 accuracy side-by-side
new_cells.append(code_cell([
    "# V1 vs V2 accuracy side-by-side\n",
    "import pandas as pd\n",
    "\n",
    "v1_csv = PROJECT_ROOT / \"results\" / \"benchmark_table.csv\"\n",
    "df_v1 = pd.read_csv(v1_csv)\n",
    "\n",
    "s1 = summarize(df_v1)\n",
    "s2 = summarize(df_v2)\n",
    "\n",
    "print(f\"{'Metric':<35}  {'V1 (synthetic, 20 Q)':>22}  {'V2 (Wikipedia, 30 Q)':>22}\")\n",
    "print(\"-\" * 85)\n",
    "print(f\"{'GraphRAG accuracy':<35}  \"\n",
    "      f\"{s1['graph_accuracy']*100:>20.1f}%  \"\n",
    "      f\"{s2['graph_accuracy']*100:>20.1f}%\")\n",
    "print(f\"{'Flat RAG accuracy':<35}  \"\n",
    "      f\"{s1['flat_accuracy']*100:>20.1f}%  \"\n",
    "      f\"{s2['flat_accuracy']*100:>20.1f}%\")\n",
    "print(f\"{'GraphRAG hallucination rate':<35}  \"\n",
    "      f\"{s1['graph_hallucination_rate']*100:>20.1f}%  \"\n",
    "      f\"{s2['graph_hallucination_rate']*100:>20.1f}%\")\n",
    "print(f\"{'Flat RAG hallucination rate':<35}  \"\n",
    "      f\"{s1['flat_hallucination_rate']*100:>20.1f}%  \"\n",
    "      f\"{s2['flat_hallucination_rate']*100:>20.1f}%\")\n",
    "print(f\"{'GraphRAG avg latency / Q (s)':<35}  \"\n",
    "      f\"{s1['graph_avg_latency_ms']/1000:>21.2f}  \"\n",
    "      f\"{s2['graph_avg_latency_ms']/1000:>21.2f}\")\n",
    "print(f\"{'Flat RAG avg latency / Q (s)':<35}  \"\n",
    "      f\"{s1['flat_avg_latency_ms']/1000:>21.2f}  \"\n",
    "      f\"{s2['flat_avg_latency_ms']/1000:>21.2f}\")\n",
    "print()\n",
    "print(f\"{'Multi-hop GraphRAG correct':<35}  \"\n",
    "      f\"{int(s1['by_category'].get('multi_hop', {}).get('graph_correct', 0)):>21}/\"\n",
    "      f\"{int(s1['by_category'].get('multi_hop', {}).get('n', 0)):<2}  \"\n",
    "      f\"{int(s2['by_category'].get('multi_hop', {}).get('graph_correct', 0)):>21}/\"\n",
    "      f\"{int(s2['by_category'].get('multi_hop', {}).get('n', 0)):<2}\")\n",
    "print(f\"{'Multi-hop Flat RAG correct':<35}  \"\n",
    "      f\"{int(s1['by_category'].get('multi_hop', {}).get('flat_correct', 0)):>21}/\"\n",
    "      f\"{int(s1['by_category'].get('multi_hop', {}).get('n', 0)):<2}  \"\n",
    "      f\"{int(s2['by_category'].get('multi_hop', {}).get('flat_correct', 0)):>21}/\"\n",
    "      f\"{int(s2['by_category'].get('multi_hop', {}).get('n', 0)):<2}\")"
]))

# §11.10 — markdown: Milestone
new_cells.append(md_cell([
    "---\n",
    "✅ **Milestone TIP-008c:** V2 benchmark complete. Results saved to:\n",
    "- `results/benchmark_table_v2.csv` — DELIVERABLE #3 v2\n",
    "- `results/cost_analysis_v2.md` — DELIVERABLE #4 v2\n",
    "- `screenshots/accuracy_by_category_v2.png` — bar chart v2\n",
    "\n",
    "Ready for final polish + conclusions (TIP-008d).\n",
    "---"
]))

nb["cells"].extend(new_cells)

with open(NB_PATH, "w") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f"✓ Appended {len(new_cells)} cells to {NB_PATH}")
print(f"  Total cells now: {len(nb['cells'])}")
