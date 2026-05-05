"""TIP-006 Acceptance Criteria Tests."""
import sys, re
sys.path.insert(0, ".")

from src.corpus_builder import load_corpus

# ===== AC-7: Fair-comparison invariant (static check — no API calls) =====
print("=" * 60)
print("AC-7 — Fair-comparison invariant (static)")
print("=" * 60)
import inspect
import src.flat_rag as fr_mod

source = inspect.getsource(fr_mod)

# Check import of ANSWER_SYSTEM_PROMPT from src.graph_rag
assert "from src.graph_rag import ANSWER_SYSTEM_PROMPT" in source, \
    "ANSWER_SYSTEM_PROMPT must be imported from src.graph_rag"

# Check _call_answer_api uses temperature=0.0
assert "temperature=0.0" in source, \
    "_call_answer_api must use temperature=0.0"

# Check uses settings.llm_model, not hardcoded model name
call_answer_source = inspect.getsource(fr_mod._call_answer_api)
assert "settings.llm_model" in call_answer_source, \
    "_call_answer_api must use settings.llm_model (no hardcoded model)"
assert '"gpt-4o-mini"' not in call_answer_source, \
    "_call_answer_api must not hardcode gpt-4o-mini"

print("  PASS — imports ANSWER_SYSTEM_PROMPT from src.graph_rag")
print("  PASS — uses temperature=0.0")
print("  PASS — uses settings.llm_model (no hardcode)")

# ===== AC-10: chromadb only (static check) =====
print("\n" + "=" * 60)
print("AC-10 — chromadb is the only vector/embedding dep")
print("=" * 60)
assert "import faiss" not in source and "from faiss" not in source, "Must not use faiss"
assert "sentence_transformers" not in source and "sentence-transformers" not in source, \
    "Must not use sentence-transformers"
assert "import langchain" not in source and "from langchain" not in source, \
    "Must not use langchain"
assert "import chromadb" in source, "Must import chromadb"
print("  PASS — only chromadb imported for vector store")

# ===== AC-4: assemble_context formatting =====
print("\n" + "=" * 60)
print("AC-4 — assemble_context format")
print("=" * 60)
from src.flat_rag import assemble_context

result = assemble_context([(1, "Hello world.", 0.1), (2, "Foo bar.", 0.2)])
expected = "Passages:\n[Paragraph 01] Hello world.\n[Paragraph 02] Foo bar."
assert result == expected, f"Expected:\n{expected}\nGot:\n{result}"
print(f"  PASS — output matches exactly:")
print(f"  {repr(result)}")

# Empty case
empty_result = assemble_context([])
assert "no relevant passages found" in empty_result
print("  PASS — empty input returns expected fallback")

# ===== AC-3: Empty collection raises clear error =====
print("\n" + "=" * 60)
print("AC-3 — Empty collection raises RuntimeError")
print("=" * 60)
from src.flat_rag import reset_collection, retrieve

reset_collection()
try:
    retrieve("anything")
    print("  FAIL — no exception raised!")
    sys.exit(1)
except RuntimeError as e:
    msg = str(e).lower()
    assert "empty" in msg, f"Error message should mention 'empty': {e}"
    assert "index_corpus" in msg, f"Error message should mention 'index_corpus': {e}"
    print(f"  PASS — RuntimeError: {e}")

# ===== AC-1: Indexing succeeds =====
print("\n" + "=" * 60)
print("AC-1 — Indexing 60 paragraphs")
print("=" * 60)
from src.flat_rag import index_corpus, get_collection

paragraphs = load_corpus()
reset_collection()
n = index_corpus(paragraphs)
assert n == 60, f"Expected 60, got {n}"
count = get_collection().count()
assert count == 60, f"Expected collection count 60, got {count}"
print(f"  PASS — n={n}, collection.count()={count}")

# ===== AC-2: retrieve returns top-k with valid distances =====
print("\n" + "=" * 60)
print("AC-2 — retrieve top-k with valid distances")
print("=" * 60)

results = retrieve("Who founded Microsoft?", top_k=5)
assert len(results) == 5, f"Expected 5 results, got {len(results)}"

# Check distances are sorted ascending
distances = [r[2] for r in results]
for i in range(len(distances) - 1):
    assert distances[i] <= distances[i+1], \
        f"Distances not sorted: {distances}"

# Check at least one relevant paragraph (Microsoft/Bill Gates paragraphs at idx 8,9,10)
returned_idxs = [r[0] for r in results]
relevant = set(returned_idxs) & {8, 9, 10}
assert len(relevant) > 0, f"Expected at least one of idx 8/9/10, got {returned_idxs}"

print(f"  PASS — 5 results returned")
print(f"  PASS — distances sorted ascending: {[f'{d:.4f}' for d in distances]}")
print(f"  PASS — relevant idxs found: {returned_idxs} (intersection with {{8,9,10}}: {relevant})")

# ===== AC-5: Single-hop end-to-end =====
print("\n" + "=" * 60)
print("AC-5 — Single-hop end-to-end (CEO of Microsoft)")
print("=" * 60)
from src.flat_rag import query as flat_rag_query

r = flat_rag_query("Who is the CEO of Microsoft?")
assert "satya nadella" in r.answer.lower(), \
    f"Answer must contain 'Satya Nadella': {r.answer}"
assert len(r.retrieved_paragraphs) == 5, \
    f"Expected 5 retrieved paragraphs, got {len(r.retrieved_paragraphs)}"
print(f"  PASS — answer: {r.answer}")
print(f"  PASS — retrieved_paragraphs count: {len(r.retrieved_paragraphs)}")

# ===== AC-6: Out-of-domain abstention =====
print("\n" + "=" * 60)
print("AC-6 — Out-of-domain abstention")
print("=" * 60)

r = flat_rag_query("What is OpenAI's office street address?")
answer_lower = r.answer.lower()
abstention_phrases = ["don't have", "not enough information", "cannot answer", "no information", "unable to"]
found_abstention = any(p in answer_lower for p in abstention_phrases)
assert found_abstention, f"Answer should abstain, got: {r.answer}"

# Check no fabricated address
fabricated_pattern = re.compile(r'\d+\s+(Street|Avenue|Road|Boulevard)', re.IGNORECASE)
assert not fabricated_pattern.search(r.answer), \
    f"Answer should not contain fabricated address: {r.answer}"
print(f"  PASS — answer: {r.answer}")
print(f"  PASS — no fabricated address found")

# ===== AC-8: Cost log captures Flat RAG =====
print("\n" + "=" * 60)
print("AC-8 — Cost log entries")
print("=" * 60)
from src.flat_rag import log_indexing_cost
from src.cost_tracker import cost_summary

log_indexing_cost(paragraphs)  # ensure at least one indexing record
s = cost_summary()
by_mod = s["by_module"]
assert "flat_rag_index" in by_mod, f"Missing 'flat_rag_index' in by_module: {list(by_mod.keys())}"
assert "flat_rag_answer" in by_mod, f"Missing 'flat_rag_answer' in by_module: {list(by_mod.keys())}"
assert by_mod["flat_rag_index"]["calls"] >= 1, "flat_rag_index should have >= 1 call"
assert by_mod["flat_rag_index"]["cost_usd"] > 0, "flat_rag_index cost should be > 0"
print(f"  PASS — by_module keys: {list(by_mod.keys())}")
print(f"  PASS — flat_rag_index: calls={by_mod['flat_rag_index']['calls']}, cost=${by_mod['flat_rag_index']['cost_usd']:.6f}")
print(f"  PASS — flat_rag_answer: calls={by_mod['flat_rag_answer']['calls']}, cost=${by_mod['flat_rag_answer']['cost_usd']:.6f}")

print("\n" + "=" * 60)
print("ALL ACCEPTANCE CRITERIA PASSED ✅")
print("=" * 60)
