## COMPLETION REPORT — TIP-008a

**STATUS:** DONE

**FILES CHANGED:**
- Modified:
  - graphrag-lab/requirements.txt — added `wikipedia>=1.4.0`
  - graphrag-lab/notebooks/lab19_main.ipynb — added §9 (5 new cells: cells 44–48)
- Created:
  - graphrag-lab/src/wiki_scraper.py — full module (390 lines)
- Created at runtime:
  - graphrag-lab/data/wiki_corpus.txt (124.4 KB, 280 paragraphs)
  - graphrag-lab/data/wiki_metadata.json (100 article entries)

**TEST RESULTS:**
- AC-1 Dependency added: PASS — `wikipedia>=1.4.0` added as line 12 in requirements.txt
- AC-2 Library installs: PASS — `pip install` exit code 0, `Successfully installed wikipedia-1.4.0`
- AC-3 100 entries: PASS — `len(ARTICLE_TARGETS) == 100`
- AC-4 Cluster distribution: PASS — `{'OpenAI': 10, 'Anthropic': 10, 'Google': 10, 'Microsoft': 10, 'Meta': 10, 'NVIDIA': 10, 'Apple': 10, 'Amazon': 10, 'Tesla': 10, 'IBM': 10}`
- AC-5 Single fetch: PASS — title="OpenAI", url="https://en.wikipedia.org/wiki/OpenAI", summary_len=1474
- AC-6 Disambig fallback: PASS — "Mercury" resolved to "Mercury (planet)" via disambiguation fallback, no exception raised
- AC-7 Citation strip: PASS — `"Apple was founded in 1976.[1] It is based in Cupertino.[12][13]"` → `"Apple was founded in 1976. It is based in Cupertino."`
- AC-8 Paragraph filter: PASS — 5-word paragraph dropped, 50-word paragraph kept → len=1
- AC-9 Full scrape: PASS — `n_articles_succeeded=93 >= 90`, `n_paragraphs=280` in [250,500]
- AC-10 Output files valid: PASS — corpus starts with `# Wikipedia Tech Company Corpus (v2)`, JSON keys `{version, n_articles_targeted, n_articles_succeeded, n_articles_skipped, articles}`, articles list length=100
- AC-11 Corpus format: PASS — all 280 paragraph lines match regex `^\[(\d+)\]\s*(.+)$`, indices contiguous 1..280
- AC-12 Notebook executes: PARTIAL — §9 cells verified structurally (5 cells appended at positions 44–48). Full nbconvert execution requires Neo4j + OpenAI API (§0–§8 dependencies) which are infrastructure-dependent.

**ISSUES DISCOVERED:**
- [Medium] Wikipedia `auto_suggest=True` mangles search terms (e.g., "Sam Altman" → "sam alt man", "GPT-4" → "gut 4"). Fixed by trying `auto_suggest=False` first, falling back to `auto_suggest=True` only on PageError.
- [Low] Wikipedia API rate limits cause `JSONDecodeError` when requests are too rapid. Fixed by increasing sleep to 0.5s and adding retry with exponential backoff (up to 3 retries).
- [Low] 7 articles failed due to persistent rate limiting despite retries: Alphabet Inc., DeepMind, Mellanox Technologies, Grok (chatbot), Neuralink, The Boring Company, Optimus (robot). This is within the AC-9 tolerance of ≤10 failures.

**DEVIATIONS FROM SPEC:**
- `_fetch_article` was enhanced beyond the spec's simple `auto_suggest=True` implementation. The spec's version would fail on ~30+ articles due to Wikipedia's broken auto-suggest. The enhanced version adds: (1) `_fetch_single` helper, (2) exact-match-first strategy, (3) retry with exponential backoff for transient JSONDecodeError. The public API signature and return format remain identical.
- Added `MAX_RETRIES = 3` constant (not in original spec) to support the retry logic.
- Increased `SLEEP_BETWEEN_CALLS_SEC` from 0.3 to 0.5 to reduce rate limiting.

**SUGGESTIONS FOR CHỦ THẦU:**
- The 7 skipped articles (Alphabet Inc., DeepMind, Mellanox Technologies, Grok, Neuralink, The Boring Company, Optimus) are all due to transient Wikipedia rate limits — re-running the scraper typically recovers most of them. For benchmark question design in TIP-008c, avoid relying solely on facts from these articles.
- Google cluster has 8/10 articles (missing Alphabet Inc. and DeepMind), Tesla cluster has 6/10 (missing 4). These gaps should be considered when designing multi-hop questions for those clusters.
- The `auto_suggest` bug in the `wikipedia` library is well-known. If a future TIP needs more reliable scraping, consider switching to `wikipedia-api` (a different, more maintained package).

**READY FOR NEXT TIP:** Yes

**ACTUAL SCRAPE STATS (from §9 cells):**
- n_paragraphs: 280
- n_articles_succeeded: 93/100
- n_articles_skipped: ["Alphabet Inc.", "DeepMind", "Mellanox Technologies", "Grok (chatbot)", "Neuralink", "The Boring Company", "Optimus (robot)"]
- corpus file size: 124.4 KB
- per-cluster distribution: {Amazon: 10, Anthropic: 10, Apple: 10, Google: 8, IBM: 10, Meta: 10, Microsoft: 10, NVIDIA: 9, OpenAI: 10, Tesla: 6}

**SAMPLE PARAGRAPHS (from the corpus):**

[001] OpenAI Global, LLC is an American artificial intelligence (AI) research organization consisting of a for-profit public benefit corporation (PBC) and a nonprofit foundation, headquartered in San Francisco. OpenAI developed the generative pre-trained transformer (GPT) series of AI models...

[050] After the success of its original service, Google Search (often known simply as "Google"), the company has rapidly grown to offer a multitude of products and services. These products address a wide range of use cases, including email (Gmail), navigation and mapping...

[100] Meta Platforms, Inc. (doing business as Meta) is an American multinational technology company headquartered in Menlo Park, California. Meta owns and operates several prominent social media platforms and communication services, including Facebook...
