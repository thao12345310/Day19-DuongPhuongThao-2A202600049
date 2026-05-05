## COMPLETION REPORT — TIP-003

**STATUS:** DONE

**FILES CHANGED:**
- Modified:
  - graphrag-lab/src/cost_tracker.py — replaced stub with full implementation
  - graphrag-lab/src/extractor.py — replaced stub with full implementation
  - graphrag-lab/notebooks/lab19_main.ipynb — added §3 (6 new cells)

**TEST RESULTS:**
- AC-1 Cost tracker basic flow: PASS — output: `3 300 150 0.000135` (exact match)
- AC-2 Cost tracker logs errors: PASS — exception propagated ("boom"), CSV has 1 row with status=error
- AC-3 Extractor returns Triple for [01]: PASS — 9 triples, subject="OpenAI" present, both entity and literal types present. Sample: `Triple(subject='OpenAI', relation='FOUNDED_IN', object='December 2015', object_type='literal', source_idx=1)`
- AC-4 Full corpus extraction: PASS — 408 triples (≥180), all source_idx in [1,60], all relations match `^[A-Z][A-Z0-9_]*$`
- AC-5 Cost log populated: PASS — total_calls=60, total_cost_usd=$0.0151 (>0 and <0.10), by_module["extractor"]["calls"]=60
- AC-6 Notebook §3 executes: PASS — `jupyter nbconvert --execute` exit code 0, all 4 §3 code cells have output, cost summary shows total_calls: 60
- AC-7 Idempotent retry: PASS — monkeypatched _call_extract_api: first call returns `{"bad": true}` (missing 'triples'), second call returns valid JSON → function returns 1 parsed triple, call_count=2
- AC-8 No new deps: PASS — requirements.txt unchanged (identical content)

**ISSUES DISCOVERED:**
- [Minor] OpenAI API returns versioned model names (e.g., `gpt-4o-mini-2024-07-18`) that don't match the exact pricing dictionary keys. Added `_resolve_model()` helper with prefix matching to handle this. Sorts by longest prefix first to prevent `gpt-4o` from matching before `gpt-4o-mini`.

**DEVIATIONS FROM SPEC:**
- Added `_resolve_model()` helper function to `cost_tracker.py` — required because the spec's `estimate_cost` used exact string matching which would always return $0.00 with real API responses. The fix is backward-compatible: exact matches still work (AC-1 passes unchanged), and versioned model names now resolve correctly.

**SUGGESTIONS FOR CHỦ THẦU:**
- The `_resolve_model()` prefix-matching approach means future models with naming patterns like `gpt-4o-mini-2025-xx-xx` will automatically resolve. However, if OpenAI introduces models with shared prefixes but different pricing tiers, the longest-prefix-first sort handles this correctly.
- Triple count varies slightly between runs (408–425 typical) due to LLM non-determinism even at temperature=0. All runs comfortably exceed the 180-triple minimum.
- Wall time for 60 API calls is ~5 minutes (avg ~5s/call) — sequential as required. TIP-004 and beyond should not need this level of API call volume.

**READY FOR NEXT TIP:** Yes

**ACTUAL EXTRACTION STATS (from notebook §3 execution):**
- Total triples: 408
- Total API cost: $0.0151
- Total wall time: ~344 seconds (5.7 min)
- Top 3 relations: DEVELOPS (42), FOUNDED_BY (38), FOUNDED_IN (37)
- Object type distribution: {entity: 305, literal: 103}

**NOTEBOOK §3 STDOUT (from executed notebook):**

**§3.2 — Extraction:**
```
Extracting triples from 60 paragraphs...
  [ 10/60] extracted 69 triples so far...
  [ 20/60] extracted 131 triples so far...
  [ 30/60] extracted 197 triples so far...
  [ 40/60] extracted 265 triples so far...
  [ 50/60] extracted 326 triples so far...
  [ 60/60] extracted 408 triples so far...
✓ Extracted 408 triples total.
```

**§3.3 — Preview:**
```
idx  subject                   relation               object                         type    
-----------------------------------------------------------------------------------------------
[01]  OpenAI                    FOUNDED_IN             December 2015                  literal 
[01]  OpenAI                    FOUNDED_AT             San Francisco                  entity  
[01]  OpenAI                    FOUNDED_AT             California                     entity  
[01]  OpenAI                    FOUNDED_BY             Sam Altman                     entity  
[01]  OpenAI                    FOUNDED_BY             Elon Musk                      entity  
[01]  OpenAI                    FOUNDED_BY             Greg Brockman                  entity  
[01]  OpenAI                    FOUNDED_BY             Ilya Sutskever                 entity  
[01]  OpenAI                    FOUNDED_BY             Wojciech Zaremba               entity  
[01]  OpenAI                    FOUNDED_BY             John Schulman                  entity  
[01]  OpenAI                    RENAMED_TO             non-profit research laborator  literal 
[02]  OpenAI                    CREATED                OpenAI LP                      entity  
[02]  OpenAI LP                 SUBSIDIARY_OF          OpenAI                         entity  
[02]  Microsoft                 INVESTED_IN            OpenAI                         entity  
[02]  Microsoft                 COMMITTED              one billion dollars            literal 
[02]  Microsoft                 PARTNER_OF             OpenAI                         entity  
```

**§3.4 — Distribution:**
```
Triples per paragraph — min: 3, max: 24, mean: 6.8
Object types: {'literal': 103, 'entity': 305}

Top 10 relations:
  DEVELOPS                  42
  FOUNDED_BY                38
  FOUNDED_IN                37
  COMPETITOR_OF             26
  FORMER_EMPLOYER           20
  FOUNDED_AT                18
  CEO_OF                    17
  WORKS_AT                  17
  RELEASED_IN               14
  RELEASED                  12
```

**§3.5 — Cost Summary:**
```
Extraction cost summary:
  Total API calls:      60
  Total tokens in:      53,841
  Total tokens out:     11,698
  Total cost (USD):     $0.0151
  Total latency (ms):   344,401
  Avg latency / call:   5740 ms
```
