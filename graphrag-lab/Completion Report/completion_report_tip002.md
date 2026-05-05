## COMPLETION REPORT — TIP-002

**STATUS:** DONE

**FILES CHANGED:**
- Modified:
  - `graphrag-lab/src/corpus_builder.py` — replaced stub with full loader/validator
  - `graphrag-lab/notebooks/lab19_main.ipynb` — added §0, §1, §2 sections (7 new cells)

**TEST RESULTS:**
- **AC-1** 60 paragraphs: **PASS** — output: `60 1 60`
- **AC-2** Prefix stripped: **PASS** — `ps[0].text` starts with `OpenAI was founded`, not `[01]`
- **AC-3** Stats correct: **PASS** — `{'n_paragraphs': 60, 'total_words': 2558, 'avg_words_per_paragraph': 42.6, 'total_chars': 17022, 'min_words': 35, 'max_words': 58}` — all values non-None, total_words 2558 ∈ [1500, 4000]
- **AC-4** 20 questions, correct distribution: **PASS** — `len=20`, distribution `{'single_hop': 5, 'multi_hop': 5, 'ambiguous': 5, 'out_of_domain': 5}`
- **AC-5** Optional fields handled: **PASS** — Q01 `reasoning_path is None: True`, Q06 `reasoning_path: 'OpenAI -[INVESTED_BY]-> Microsoft -[CEO]-> Satya Nadella'`
- **AC-6** Validation catches malformed: **PASS** — `ValueError raised: Expected 60 paragraphs, found 2. Indices loaded: [1, 2]`; temp file cleaned up
- **AC-7** Notebook executes: **PASS** — `jupyter nbconvert` exit code 0, all 3 code cells have output
- **AC-8** No new deps: **PASS** — `requirements.txt` unchanged

**ISSUES DISCOVERED:**
- None.

**DEVIATIONS FROM SPEC:**
- None.

**SUGGESTIONS FOR CHỦ THẦU:**
- None.

**READY FOR NEXT TIP:** Yes

**NOTEBOOK EXECUTION OUTPUT (from §0 + §2 cells):**
```
✓ Project root: /Users/duongtphuongthao/Documents/VinUni_Labs/Lab19/graphrag-lab
✓ LLM model:    gpt-4o-mini
✓ Neo4j URI:    bolt://localhost:7687

Corpus stats:
  n_paragraphs: 60
  total_words: 2558
  avg_words_per_paragraph: 42.6
  total_chars: 17022
  min_words: 35
  max_words: 58

First 3 paragraphs (truncated):
  [01] OpenAI was founded in December 2015 in San Francisco, California. The founding team included Sam Altman, Elon Musk, Greg...
  [02] In 2019, OpenAI created a capped-profit subsidiary called OpenAI LP to attract larger investments. Microsoft became Open...
  [03] Sam Altman is the chief executive officer of OpenAI. Before leading OpenAI, Altman served as president of the startup ac...

Benchmark stats:
  n_questions: 20
  by_category: {'multi_hop': 5, 'ambiguous': 5, 'single_hop': 5, 'out_of_domain': 5}
  n_with_reasoning_path: 5
  avg_expected_hops: 1.05

Sample question per category:
  [Q01 | single_hop    ] Who is the CEO of Microsoft?
     gold: Satya Nadella
  [Q06 | multi_hop     ] Who is the CEO of OpenAI's largest corporate investor?
     gold: Satya Nadella (CEO of Microsoft, which is OpenAI's largest corporate investor)
  [Q11 | ambiguous     ] Who founded Apple?
     gold: Steve Jobs, Steve Wozniak, and Ronald Wayne
  [Q16 | out_of_domain ] What is OpenAI's office street address?
     gold: Not enough information in the corpus
```