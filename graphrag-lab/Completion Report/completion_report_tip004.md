# COMPLETION REPORT — TIP-004

**STATUS:** DONE

**FILES CHANGED:**
- Modified:
  - graphrag-lab/src/graph_builder.py — replaced stub with full implementation (connection management, MERGE-based dedup, entity type inference, stats, Matplotlib visualization, suggested Cypher queries)
  - graphrag-lab/notebooks/lab19_main.ipynb — added §4 (7 new cells: §4.1–§4.7)
- Created at runtime (artifacts):
  - graphrag-lab/screenshots/graph_matplotlib.png — Matplotlib backup viz

**TEST RESULTS:**
- AC-1 Connection works: **PASS** — `test_connection()` returned `True`
- AC-2 clear_graph empties: **PASS** — after `clear_graph()`, `get_stats()` returned `n_nodes=0, n_edges=0`
- AC-3 Dedup fixture (4 nodes, 3 edges, 2 aliases): **PASS** — `n_nodes=4, n_edges=3`, OpenAI aliases = `['OpenAI', 'Open AI']`
- AC-4 Full corpus build: **PASS** — `n_nodes=279` (in [100,350] ✓), `n_edges=417` (≥350 ✓), `n_unique_relations=83` (≥15 ✓), "OpenAI" in top entities (degree 50, rank #1 ✓)
- AC-5 Year/Money inference: **PASS** — Year nodes = 30 (≥5 ✓), Money nodes = 3
- AC-6 PNG saved: **PASS** — file exists, 538.7 KB (>30 KB ✓), valid PNG magic bytes `\x89PNG\r\n\x1a\n`
- AC-7 Notebook executes: **PASS** — `nbconvert --execute` exit code 0, all §4 code cells have output, `screenshots/graph_matplotlib.png` exists
- AC-8 No new deps: **PASS** — `requirements.txt` unchanged

**ISSUES DISCOVERED:**
- [Minor] The spec's `_normalize_key` function used whitespace-collapsing (`" ".join(name.strip().lower().split())`) which does NOT merge "OpenAI" (key: `"openai"`) with "Open AI" (key: `"open ai"`) — these are different keys. This caused AC-3 to fail (5 nodes instead of 4). Fixed by using space-removal normalization (`name.strip().lower().replace(" ", "")`), which maps both to `"openai"`.
- [Minor] The spec's `_build_canonical_name_map` used `len(raw)` to pick the longest surface form, but "Open AI" (7 chars) is longer than "OpenAI" (6 chars) due to the space, causing the canonical name to be "Open AI" instead of the expected "OpenAI". Fixed by comparing non-space character count (`len(raw.replace(" ", ""))`) where ties favor first-seen.

**DEVIATIONS FROM SPEC:**
- `_normalize_key` — Changed from whitespace-collapsing to space-removal normalization. This was necessary to make AC-3 pass (the spec's docstring examples implied this behavior but the implementation didn't achieve it). Impact: improves dedup quality.
- `_build_canonical_name_map` — Changed length comparison from raw length to non-space character count. This was necessary to make AC-3's alias check pass with canonical name "OpenAI". Impact: canonical names now prefer the compact form, which is more readable.

**SUGGESTIONS FOR CHỦ THẦU:**
- The 83 unique relation types suggest the LLM invented many ad-hoc relations beyond the canonical list. If this causes issues in TIP-005 GraphRAG (too many edge types to match against), consider adding a relation normalization step.
- "Other" is the most common entity type (85 nodes). The heuristic rules are conservative — some of these could be companies or products. This may affect visualization filtering but shouldn't impact query accuracy.

**READY FOR NEXT TIP:** Yes

**ACTUAL GRAPH STATS (from notebook §4 execution):**
- Total nodes: 279
- Total edges: 417
- Unique relation types: 83
- Entity type distribution: {Other: 85, Person: 79, Company: 69, Year: 30, Product: 12, Money: 3, Location: 1}
- Top 5 hubs: [(OpenAI, 50), (Anthropic, 32), (Microsoft, 30), (Meta, 28), (Google, 27)]

**REMINDER FOR HOMEOWNER:**
After this TIP completes, the Homeowner should:
1. Open http://localhost:7474, log in with neo4j / graphrag-lab-pwd
2. Run the "OpenAI 2-hop neighborhood" Cypher query
3. Take a screenshot and save it as screenshots/graph_neo4j.png
This is Deliverable #2 of the lab.
