"""M6 — Cost & Latency Tracker.

Decorator-based logging of OpenAI API calls. Every wrapped function
appends one row to a CSV with timestamp, module, model, tokens_in,
tokens_out, latency_ms, and estimated_cost_usd.

Implemented in TIP-003.
"""
from __future__ import annotations
import csv
import functools
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

from src.config import settings


# Pricing per 1M tokens (USD) — gpt-4o-mini and text-embedding-3-small
# Source: OpenAI public pricing (verify before final report).
PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.150, "output": 0.600},
    "gpt-4o": {"input": 2.500, "output": 10.000},
    "text-embedding-3-small": {"input": 0.020, "output": 0.0},
    "text-embedding-3-large": {"input": 0.130, "output": 0.0},
}

CSV_HEADER = [
    "timestamp", "module", "function", "model",
    "tokens_in", "tokens_out", "latency_ms", "cost_usd", "status",
]


@dataclass
class CallRecord:
    """One row in the cost log."""
    timestamp: str
    module: str
    function: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float
    status: str  # "ok" | "error"

    def to_csv_row(self) -> list[str]:
        return [
            self.timestamp, self.module, self.function, self.model,
            str(self.tokens_in), str(self.tokens_out),
            str(self.latency_ms), f"{self.cost_usd:.6f}", self.status,
        ]


def _resolve_model(model: str) -> str | None:
    """Resolve a versioned model name to a known pricing key via prefix match."""
    if model in PRICING:
        return model
    # Try prefix matching (e.g., "gpt-4o-mini-2024-07-18" → "gpt-4o-mini")
    # Sort by longest prefix first to avoid "gpt-4o" matching before "gpt-4o-mini"
    for key in sorted(PRICING.keys(), key=len, reverse=True):
        if model.startswith(key):
            return key
    return None


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate USD cost for a single call. Returns 0.0 if model unknown."""
    resolved = _resolve_model(model)
    if resolved is None:
        return 0.0
    p = PRICING[resolved]
    return (tokens_in * p["input"] + tokens_out * p["output"]) / 1_000_000


def _ensure_csv_with_header(path: Path) -> None:
    """Create the CSV with header if it does not exist."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADER)


def _append_record(record: CallRecord, path: Path | None = None) -> None:
    """Append a single record to the cost log CSV."""
    path = path or settings.cost_log_path
    _ensure_csv_with_header(path)
    with path.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(record.to_csv_row())


def track_llm_call(module: str, model_attr: str = "model") -> Callable:
    """Decorator factory: wraps a function that calls the OpenAI API.

    The wrapped function MUST return an OpenAI response object that has:
      - .usage.prompt_tokens
      - .usage.completion_tokens
      - .model

    OR a tuple (result, usage_dict) where usage_dict has
      "model", "prompt_tokens", "completion_tokens".

    Args:
        module: Logical module name to record (e.g., "extractor", "graph_rag").
        model_attr: Attribute name used to read the model from the response.

    Returns:
        Decorator. Adds one row to the cost log per call (success or failure).
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.time()
            status = "ok"
            tokens_in = 0
            tokens_out = 0
            model = "unknown"
            result = None
            error: Exception | None = None
            try:
                result = fn(*args, **kwargs)
                # Two return-shape conventions accepted:
                if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
                    inner, usage = result
                    tokens_in = int(usage.get("prompt_tokens", 0))
                    tokens_out = int(usage.get("completion_tokens", 0))
                    model = str(usage.get("model", "unknown"))
                    result = inner  # unwrap
                else:
                    # Assume OpenAI SDK response object
                    usage = getattr(result, "usage", None)
                    if usage is not None:
                        tokens_in = int(getattr(usage, "prompt_tokens", 0))
                        tokens_out = int(getattr(usage, "completion_tokens", 0))
                    model = str(getattr(result, model_attr, "unknown"))
            except Exception as e:
                status = "error"
                error = e
            finally:
                latency_ms = int((time.time() - t0) * 1000)
                record = CallRecord(
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                    module=module,
                    function=fn.__name__,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    cost_usd=estimate_cost(model, tokens_in, tokens_out),
                    status=status,
                )
                try:
                    _append_record(record)
                except Exception:
                    pass  # Never let logging failure crash the caller
            if error is not None:
                raise error
            return result
        return wrapper
    return decorator


def read_cost_log(path: Path | None = None) -> list[dict]:
    """Read the entire cost log as a list of dicts. Empty list if no log yet."""
    path = path or settings.cost_log_path
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cost_summary(path: Path | None = None) -> dict:
    """Aggregate the cost log: totals by module + grand total."""
    rows = read_cost_log(path)
    if not rows:
        return {
            "total_calls": 0, "total_tokens_in": 0, "total_tokens_out": 0,
            "total_cost_usd": 0.0, "total_latency_ms": 0, "by_module": {},
        }
    by_module: dict[str, dict] = {}
    total_in = total_out = total_lat = 0
    total_cost = 0.0
    for row in rows:
        m = row["module"]
        slot = by_module.setdefault(m, {
            "calls": 0, "tokens_in": 0, "tokens_out": 0,
            "cost_usd": 0.0, "latency_ms": 0,
        })
        slot["calls"] += 1
        slot["tokens_in"] += int(row["tokens_in"])
        slot["tokens_out"] += int(row["tokens_out"])
        slot["cost_usd"] += float(row["cost_usd"])
        slot["latency_ms"] += int(row["latency_ms"])
        total_in += int(row["tokens_in"])
        total_out += int(row["tokens_out"])
        total_cost += float(row["cost_usd"])
        total_lat += int(row["latency_ms"])
    return {
        "total_calls": len(rows),
        "total_tokens_in": total_in,
        "total_tokens_out": total_out,
        "total_cost_usd": round(total_cost, 6),
        "total_latency_ms": total_lat,
        "by_module": by_module,
    }


def reset_cost_log(path: Path | None = None) -> None:
    """Delete the cost log file (used between benchmark runs)."""
    path = path or settings.cost_log_path
    if path.exists():
        path.unlink()
