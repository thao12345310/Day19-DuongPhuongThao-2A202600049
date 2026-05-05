## COMPLETION REPORT — TIP-006

**STATUS:** DONE

**FILES CHANGED:**
- Modified:
  - graphrag-lab/src/flat_rag.py — replaced stub with full ChromaDB pipeline
  - graphrag-lab/notebooks/lab19_main.ipynb — added §6 (7 new cells: §6.1–§6.7)

**TEST RESULTS:**
- AC-1 Indexing: **PASS** — n=60, collection.count()=60
- AC-2 retrieve top-k: **PASS** — 5 results returned, distances sorted ascending ['0.3163', '0.4090', '0.5214', '0.5270', '0.5975'], relevant idxs {8, 9, 10} all found
- AC-3 Empty collection error: **PASS** — RuntimeError: "Collection is empty. Call index_corpus(paragraphs) first."
- AC-4 assemble_context format: **PASS** — exact output matches `Passages:\n[Paragraph 01] Hello world.\n[Paragraph 02] Foo bar.`
- AC-5 Single-hop end-to-end: **PASS** — answer: "Satya Nadella is the CEO of Microsoft.", retrieved_paragraphs count: 5
- AC-6 Out-of-domain abstention: **PASS** — answer: "I don't have enough information to answer this question." No fabricated address found.
- AC-7 Fair-comparison invariant: **PASS** — imports `ANSWER_SYSTEM_PROMPT` from `src.graph_rag`, uses `temperature=0.0`, uses `settings.llm_model` (no hardcode)
- AC-8 Cost log entries: **PASS** — by_module contains both `flat_rag_index` (calls=1, cost=$0.000085) and `flat_rag_answer` (calls=6, cost=$0.0004)
- AC-9 Notebook executes: **PASS** — `jupyter nbconvert --execute` exit code 0, all 4 §6 code cells have output, side-by-side table prints all 3 questions
- AC-10 chromadb only: **PASS** — only chromadb imported for vector store; no faiss, sentence-transformers, or langchain

**ISSUES DISCOVERED:**
- None.

**DEVIATIONS FROM SPEC:**
- None.

**SUGGESTIONS FOR CHỦ THẦU:**
- The multi-hop question Q06 ("Who is the CEO of OpenAI's largest corporate investor?") is the perfect showcase question for TIP-007's benchmark — Flat RAG fails it (abstains) while GraphRAG answers correctly. This validates the experimental design.
- Cost is very low for Flat RAG indexing (~$0.0001 for 60 paragraphs) — the embedding model is extremely cheap relative to the extraction phase ($0.0154).

**READY FOR NEXT TIP:** Yes

---

**ACTUAL DEMO OUTPUTS (from §6 cells):**

**§6.3 — Three Flat RAG demo answers:**

```
================================================================================
[SINGLE-HOP — Q01] Who is the CEO of Microsoft?
================================================================================

→ Top retrieved paragraphs (idx, distance):
   [10]  distance=0.3217
   [09]  distance=0.3303
   [08]  distance=0.4595
   [24]  distance=0.4905
   [26]  distance=0.5480

--- Context (first 8 lines) ---
Passages:
[Paragraph 10] Satya Nadella has been the chief executive officer of Microsoft since February 2014. Under Nadella's leadership, Microsoft pi...
[Paragraph 09] Bill Gates served as chief executive officer of Microsoft from 1975 to 2000 before transitioning into a chairman role. Steve ...
[Paragraph 08] Microsoft was founded in 1975 by Bill Gates and Paul Allen in Albuquerque, New Mexico. The company later moved its headquarte...
[Paragraph 24] Mustafa Suleyman, a co-founder of DeepMind, left to start Inflection AI in 2022. He joined Microsoft in March 2024 as chief e...
[Paragraph 26] Mark Zuckerberg has served as chief executive officer of Meta since the company's founding. He retains majority voting contro...

--- Answer ---
Satya Nadella is the CEO of Microsoft.

[latency: 2471 ms]

================================================================================
[MULTI-HOP — Q06] Who is the CEO of OpenAI's largest corporate investor?
================================================================================

→ Top retrieved paragraphs (idx, distance):
   [02]  distance=0.2983
   [03]  distance=0.3322
   [04]  distance=0.3697
   [07]  distance=0.3901
   [01]  distance=0.4089

--- Context (first 8 lines) ---
Passages:
[Paragraph 02] In 2019, OpenAI created a capped-profit subsidiary called OpenAI LP to attract larger investments. Microsoft became OpenAI's ...
[Paragraph 03] Sam Altman is the chief executive officer of OpenAI. Before leading OpenAI, Altman served as president of the startup acceler...
[Paragraph 04] Elon Musk co-founded OpenAI but resigned from its board of directors in February 2018, citing potential conflicts of interest...
[Paragraph 07] Greg Brockman serves as president of OpenAI and was one of its co-founders. Ilya Sutskever, another co-founder, worked as chi...
[Paragraph 01] OpenAI was founded in December 2015 in San Francisco, California. The founding team included Sam Altman, Elon Musk, Greg Broc...

--- Answer ---
I don't have enough information to answer this question.

[latency: 1355 ms]

================================================================================
[OUT-OF-DOMAIN — Q16] What is OpenAI's office street address?
================================================================================

→ Top retrieved paragraphs (idx, distance):
   [01]  distance=0.4020
   [03]  distance=0.4784
   [07]  distance=0.4947
   [11]  distance=0.5242
   [38]  distance=0.5252

--- Context (first 8 lines) ---
Passages:
[Paragraph 01] OpenAI was founded in December 2015 in San Francisco, California. The founding team included Sam Altman, Elon Musk, Greg Broc...
[Paragraph 03] Sam Altman is the chief executive officer of OpenAI. Before leading OpenAI, Altman served as president of the startup acceler...
[Paragraph 07] Greg Brockman serves as president of OpenAI and was one of its co-founders. Ilya Sutskever, another co-founder, worked as chi...
[Paragraph 11] Microsoft's Azure cloud division provides the computing infrastructure for OpenAI's model training and deployment. The deep p...
[Paragraph 38] Anthropic was founded in 2021 in San Francisco by Dario Amodei, Daniela Amodei, Tom Brown, and several other former OpenAI re...

--- Answer ---
I don't have enough information to answer this question.

[latency: 1030 ms]
```

**§6.5 — Side-by-side comparison table:**

```
qid                    | GraphRAG                                                | Flat RAG
--------------------------------------------------------------------------------------------------------------------------------------------
Q01 (single-hop)       | Satya Nadella is the CEO of Microsoft.                  | Satya Nadella is the CEO of Microsoft.
Q06 (multi-hop)        | The CEO of OpenAI's largest corporate investor, Micr... | I don't have enough information to answer this quest...
Q16 (out-of-domain)    | I don't have enough information to answer this quest... | I don't have enough information to answer this quest...
```

**§6.6 — Cumulative cost summary:**

```
Cumulative API calls:  79
Cumulative cost:       $0.0171

By module:
  extractor              calls= 60  tokens_in= 53841  tokens_out=12256  cost=$0.0154
  graph_rag_ner          calls=  6  tokens_in=  1268  tokens_out=   46  cost=$0.0002
  graph_rag_answer       calls=  6  tokens_in=  5668  tokens_out=   76  cost=$0.0009
  flat_rag_index         calls=  1  tokens_in=  4236  tokens_out=    0  cost=$0.0001
  flat_rag_answer        calls=  6  tokens_in=  2722  tokens_out=   60  cost=$0.0004
```

**KEY OBSERVATIONS:**
- **Multi-hop failure confirmed:** Flat RAG correctly retrieved OpenAI-related paragraphs (§02 mentions "Microsoft became OpenAI's largest investor") but the top-5 did NOT include paragraph 10 (Satya Nadella = CEO of Microsoft). Without the graph's ability to traverse `OpenAI → investor → Microsoft → CEO → Nadella`, Flat RAG abstained — exactly as expected.
- **Both systems abstain on out-of-domain:** Neither hallucinated an address for Q16. The strict `ANSWER_SYSTEM_PROMPT` works identically in both pipelines.
- **Retrieval quality is reasonable:** For Q01 (single-hop), Flat RAG pulled the exactly right paragraphs (10, 9, 8) with good cosine distances (0.32–0.46), showing that vector retrieval works well for direct factual lookups.
