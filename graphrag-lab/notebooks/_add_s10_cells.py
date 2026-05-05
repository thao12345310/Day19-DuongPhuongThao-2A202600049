#!/usr/bin/env python3
"""Append §10 cells (TIP-008b) to lab19_main.ipynb."""
import json
from pathlib import Path

NB_PATH = Path(__file__).parent / "lab19_main.ipynb"

new_cells = [
    # §10.1 — markdown
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## §10 — V2 Pipeline Re-run: Extract → Graph → Index\n",
            "\n",
            "Now we re-run the entire pipeline on the larger Wikipedia-derived corpus:\n",
            "\n",
            "1. Load `data/wiki_corpus.txt` (280 paragraphs)\n",
            "2. Extract triples (cached on disk to avoid re-spending API budget on re-runs)\n",
            "3. Clear the v1 Neo4j graph and rebuild from v2 triples\n",
            "4. Reset the Chroma collection and re-index with v2 paragraphs\n",
            "5. Display v1 vs v2 comparison stats and a fresh Matplotlib visualization\n",
            "\n",
            "> ⚠️ First-time execution: ~$0.10 + ~20 minutes wall time for extraction.\n",
            "> Re-runs: ~5 seconds (cache hit).",
        ],
    },
    # §10.2 — code: load v2 corpus
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Load v2 corpus (280 paragraphs)\n",
            'v2_corpus_path = PROJECT_ROOT / "data" / "wiki_corpus.txt"\n',
            "paragraphs_v2 = load_corpus(path=v2_corpus_path, expected_count=None)\n",
            "c2_stats = corpus_stats(paragraphs_v2)\n",
            'print("V2 corpus stats:")\n',
            "for k, v in c2_stats.items():\n",
            '    print(f"  {k}: {v}")\n',
            "print(f\"\\nv1 had {c_stats['n_paragraphs']} paragraphs / {c_stats['total_words']:,} words.\")\n",
            "print(f\"v2 has  {c2_stats['n_paragraphs']} paragraphs / {c2_stats['total_words']:,} words \"\n",
            "      f\"(~{c2_stats['total_words'] / c_stats['total_words']:.1f}× larger).\")",
        ],
    },
    # §10.3 — code: cached extraction
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Cached extraction\n",
            "from src.extractor import extract_corpus_cached\n",
            'v2_triples_cache = PROJECT_ROOT / "data" / "wiki_triples.json"\n',
            "\n",
            'print("V2 triple extraction (cached)...")\n',
            "triples_v2 = extract_corpus_cached(paragraphs_v2, cache_path=v2_triples_cache, verbose=True)\n",
            'print(f"\\n✓ V2 triples ready: {len(triples_v2)} (v1 had {len(triples)})")',
        ],
    },
    # §10.4 — code: rebuild Neo4j graph
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Rebuild Neo4j graph with v2 triples\n",
            "from src.graph_builder import clear_graph, build_graph, get_stats, export_matplotlib\n",
            "\n",
            "clear_graph()\n",
            'print("✓ V1 graph cleared.")\n',
            "v2_graph_stats = build_graph(triples_v2)\n",
            'print(f"\\n✓ V2 graph built: {v2_graph_stats.n_nodes} nodes, "\n',
            '      f"{v2_graph_stats.n_edges} edges, "\n',
            '      f"{v2_graph_stats.n_unique_relations} relation types")\n',
            'print(f"\\nEntity type distribution:")\n',
            "for k, v in sorted(v2_graph_stats.n_entity_types.items(), key=lambda kv: -kv[1]):\n",
            '    print(f"  {k:<10} {v}")\n',
            'print(f"\\nTop 10 entities by degree:")\n',
            "for name, deg in v2_graph_stats.top_entities_by_degree:\n",
            '    print(f"  {deg:>3}  {name}")',
        ],
    },
    # §10.5 — code: re-index Chroma
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Re-index Flat RAG ChromaDB with v2 corpus\n",
            "from src.flat_rag import reset_collection, index_corpus, log_indexing_cost\n",
            "\n",
            "reset_collection()\n",
            "n_indexed = index_corpus(paragraphs_v2)\n",
            "log_indexing_cost(paragraphs_v2)\n",
            'print(f"✓ V2 Flat RAG re-indexed: {n_indexed} paragraphs.")',
        ],
    },
    # §10.6 — code: visualization
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# V2 visualization (Matplotlib)\n",
            'v2_viz_path = PROJECT_ROOT / "screenshots" / "graph_matplotlib_v2.png"\n',
            "v2_viz_path = export_matplotlib(v2_viz_path, limit_nodes=40)\n",
            'print(f"✓ V2 visualization saved: {v2_viz_path}")\n',
            "from IPython.display import Image, display\n",
            "display(Image(filename=str(v2_viz_path)))",
        ],
    },
    # §10.7 — code: comparison table
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# V1 vs V2 comparison side-by-side\n",
            "print(f\"{'Metric':<30}  {'V1 (synthetic)':>15}  {'V2 (Wikipedia)':>15}\")\n",
            'print("-" * 65)\n',
            "print(f\"{'Paragraphs':<30}  {c_stats['n_paragraphs']:>15}  {c2_stats['n_paragraphs']:>15}\")\n",
            "print(f\"{'Total words':<30}  {c_stats['total_words']:>15,}  {c2_stats['total_words']:>15,}\")\n",
            "print(f\"{'Triples':<30}  {len(triples):>15}  {len(triples_v2):>15}\")\n",
            "# v1 graph stats are not in scope; recompute would require rebuilding v1.\n",
            "# Just show v2 alongside the v1 numbers we already printed in §4.\n",
            "print(f\"{'Graph nodes (v2)':<30}  {'(see §4)':>15}  {v2_graph_stats.n_nodes:>15}\")\n",
            "print(f\"{'Graph edges (v2)':<30}  {'(see §4)':>15}  {v2_graph_stats.n_edges:>15}\")\n",
            "print(f\"{'Relation types (v2)':<30}  {'(see §4)':>15}  {v2_graph_stats.n_unique_relations:>15}\")",
        ],
    },
    # §10.8 — markdown: milestone
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "---\n",
            "✅ **Milestone TIP-008b:** V2 pipeline complete. Larger graph from real Wikipedia text is now live in Neo4j and ChromaDB. Ready for v2 benchmark generation (TIP-008c).\n",
            "\n",
            "The v1 graph data is GONE from Neo4j (cleared by `clear_graph()`), but v1 results\n",
            "(`results/benchmark_table.csv`, `results/cost_analysis.md`) are preserved on disk.\n",
            "The v1 corpus and v1 triple count are still loaded in notebook variables (`paragraphs`,\n",
            "`triples`) for the §10.7 comparison cell to reference.\n",
            "\n",
            "---",
        ],
    },
]

# Read notebook
nb = json.loads(NB_PATH.read_text(encoding="utf-8"))

# Verify last cell is the TIP-008a milestone
last_src = "".join(nb["cells"][-1].get("source", []))
assert "TIP-008a" in last_src, f"Expected last cell to be TIP-008a milestone, got: {last_src[:100]}"

# Check if §10 already added
all_src = "".join("".join(c.get("source", [])) for c in nb["cells"])
if "TIP-008b" in all_src:
    print("§10 cells already present (TIP-008b marker found). Skipping.")
else:
    nb["cells"].extend(new_cells)
    NB_PATH.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✓ Appended {len(new_cells)} cells to {NB_PATH.name}")
    print(f"  Total cells now: {len(nb['cells'])}")
