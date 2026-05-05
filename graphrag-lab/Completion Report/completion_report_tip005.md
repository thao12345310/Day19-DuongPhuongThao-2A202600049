## COMPLETION REPORT — TIP-005

**STATUS:** DONE

**FILES CHANGED:**
- Modified:
  - graphrag-lab/src/graph_rag.py — replaced stub with full pipeline (5 stages + orchestrator)
  - graphrag-lab/notebooks/lab19_main.ipynb — added §5 (7 new cells)

**TEST RESULTS:**
- AC-1 NER filters common nouns: PASS — entities=['Microsoft'] (no "CEO", "Who", or "the")
- AC-2 Alias resolution: PASS — input "OPENAI" → matched=['OpenAI']
- AC-3 Empty for nonsense: PASS — matched=[]
- AC-4 BFS around OpenAI: PASS — edge_count=193, sample=GraphEdge(src='OpenAI', relation='FOUNDED_IN', dst='December 2015', source_idx=1)
- AC-5 textualize format: PASS — exact output: 'Facts:\n- A REL_X B\n- B REL_Y C'
- AC-6 Single-hop end-to-end: PASS — answer='Satya Nadella is the CEO of Microsoft.', entities=['Microsoft']
- AC-7 Multi-hop end-to-end: PASS — answer="The CEO of OpenAI's largest corporate investor, Microsoft, is Satya Nadella.", matched=['OpenAI'], edges=193
- AC-8 Out-of-domain abstention: PASS — answer="I don't have enough information to answer this question."
- AC-9 Notebook executes: PASS — nbconvert exit code 0, all 4 §5 code cells have output, multi-hop demo answers "Satya Nadella"
- AC-10 No new deps: PASS — requirements.txt unchanged

**ISSUES DISCOVERED:**
- [Low] The `startswith` fallback in `match_entities_in_graph` matched the single-character entity "X" (formerly Twitter) against any input starting with "x". Fixed by adding a minimum key length guard (>2 chars) for both the input key and the graph node key in the startswith fallback.

**DEVIATIONS FROM SPEC:**
- Added `size(name_key) > 2` guard in the startswith Cypher query and `len(k) > 2` guard on the Python side. This prevents the trivial match bug without affecting legitimate entity resolution. The spec's startswith fallback was preserved in spirit — only trivially short keys are excluded.

**SUGGESTIONS FOR CHỦ THẦU:**
- The BFS subgraph for OpenAI returns 180–193 edges (near the 200 limit). If the benchmark has questions about high-degree hubs, consider whether the edge ordering matters (currently LIMIT without ORDER BY gives non-deterministic ordering). For TIP-007 benchmarking this should be fine since 2-hop coverage is comprehensive.
- Cost for the 3 demo queries: $0.0005 total (3 NER + 3 answer calls). Well within the $0.005 estimate.

**READY FOR NEXT TIP:** Yes

**ACTUAL DEMO OUTPUTS (paste from §5 cells):**

**§5.3 — Single-hop (Q01):**
```
================================================================================
[SINGLE-HOP — Q01] Who is the CEO of Microsoft?
================================================================================

→ Extracted entities:  ['Microsoft']
→ Matched in graph:    ['Microsoft']
→ Subgraph edges:      109

--- Context (first 12 lines) ---
Facts:
- Microsoft FOUNDED_IN 1975
- Bill Gates FOUNDED_AT 1975
- Microsoft USES Azure cloud platform
- Microsoft COMMITTED one billion dollars
- Meta ACQUIRED_FOR one billion dollars
- Microsoft FOUNDED_BY Bill Gates
- Bill Gates CEO_OF Microsoft
- Bill Gates LEFT_BOARD_IN 2020
- Bill Gates FORMER_EMPLOYER Microsoft
- Bill Gates WORKS_AT Bill & Melinda Gates Foundation
- Microsoft GRANTED_ACCESS_TO OpenAI's technology
... (70 more lines)

--- Answer ---
Satya Nadella is the CEO of Microsoft.

[latency: 1565 ms]
```

**§5.4 — Multi-hop (Q06):**
```
================================================================================
[MULTI-HOP — Q06] Who is the CEO of OpenAI's largest corporate investor?
================================================================================

→ Extracted entities:  ['OpenAI']
→ Matched in graph:    ['OpenAI']
→ Subgraph edges:      180

--- Context (first 12 lines) ---
Facts:
- OpenAI FOUNDED_IN December 2015
- OpenAI FOUNDED_AT San Francisco
- Anthropic FOUNDED_AT San Francisco
- OpenAI FOUNDED_BY Sam Altman
- Sam Altman REMOVED_FROM CEO role
- Sam Altman PRESIDENT_OF Y Combinator
- Sam Altman REINSTATED CEO role
- Sam Altman CEO_OF OpenAI
- OpenAI RUNS_ON Microsoft Azure
- OpenAI WORKS_AT Microsoft Azure
- Microsoft Azure HOSTS dedicated supercomputing clusters
... (70 more lines)

--- Answer ---
The CEO of OpenAI's largest corporate investor, Microsoft, is Satya Nadella.

[latency: 1986 ms]
```

**§5.5 — Out-of-domain (Q16):**
```
================================================================================
[OUT-OF-DOMAIN — Q16] What is OpenAI's office street address?
================================================================================

→ Extracted entities:  ['OpenAI']
→ Matched in graph:    ['OpenAI']
→ Subgraph edges:      180

--- Context (first 12 lines) ---
Facts:
- OpenAI FOUNDED_IN December 2015
- OpenAI FOUNDED_AT San Francisco
- Anthropic FOUNDED_AT San Francisco
- OpenAI FOUNDED_BY Sam Altman
- Sam Altman REMOVED_FROM CEO role
- Sam Altman PRESIDENT_OF Y Combinator
- Sam Altman REINSTATED CEO role
- Sam Altman CEO_OF OpenAI
- OpenAI RUNS_ON Microsoft Azure
- OpenAI WORKS_AT Microsoft Azure
- Microsoft Azure HOSTS dedicated supercomputing clusters
... (70 more lines)

--- Answer ---
I don't have enough information to answer this question.

[latency: 1648 ms]
```

**§5.6 — Cost summary:**
```
Total API calls so far:  66
Total cost so far:       $0.0157

By module:
  extractor            calls= 60  tokens_in= 53841  tokens_out=11706  cost=$0.0151
  graph_rag_ner        calls=  3  tokens_in=   634  tokens_out=   23  cost=$0.0001
  graph_rag_answer     calls=  3  tokens_in=  2837  tokens_out=   38  cost=$0.0004
```
