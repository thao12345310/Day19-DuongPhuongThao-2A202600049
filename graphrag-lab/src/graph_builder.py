"""M2 — Graph Builder (Neo4j).

Pushes (subject, relation, object) triples into Neo4j with name-based
deduplication using MERGE. Entity type is inferred from the object_type
flag and from value-based heuristics (year, money, etc.).

Also provides a Matplotlib visualization as a backup for the Neo4j
Browser screenshot deliverable.

Implemented in TIP-004.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterable

from neo4j import GraphDatabase, Driver

from src.config import settings
from src.extractor import Triple


# ----------------------------- Constants -----------------------------

YEAR_RE = re.compile(r"^\s*(?:19|20)\d{2}\s*$")
MONEY_RE = re.compile(
    r"(\$|USD)|(\d+(\.\d+)?\s*(billion|million|thousand|trillion|dollars?))",
    re.IGNORECASE,
)

# Entity types we tag on nodes. The graph still works without these,
# but they help filtering and visualization legends.
ENTITY_TYPES = ("Company", "Person", "Product", "Year", "Money", "Location", "Other")


# ----------------------------- Data classes -----------------------------

@dataclass(frozen=True)
class GraphStats:
    n_nodes: int
    n_edges: int
    n_unique_relations: int
    n_entity_types: dict[str, int]
    top_entities_by_degree: tuple[tuple[str, int], ...]  # name, degree


# ----------------------------- Name normalization -----------------------------

def _normalize_key(name: str) -> str:
    """Dedup key: lowercased, all whitespace removed.

    "OpenAI", "openai", "Open AI", "  Open  AI  " → "openai"

    Removing spaces ensures that "OpenAI" and "Open AI" map to the same
    key, which is essential for name-based deduplication.
    """
    return name.strip().lower().replace(" ", "")


def _infer_entity_type(name: str, object_type: str) -> str:
    """Heuristic entity type. Falls back to 'Other'.

    object_type comes from the Triple ('entity' or 'literal') and gives
    us a coarse hint; we then refine using regex.
    """
    if object_type == "literal":
        if YEAR_RE.match(name):
            return "Year"
        if MONEY_RE.search(name):
            return "Money"
        return "Other"
    # object_type == "entity": guess Company/Person/Location/Product
    # Very simple heuristics — could be improved later
    if any(ch.isdigit() for ch in name):
        # entities with digits are usually products/versions
        return "Product"
    parts = name.split()
    if len(parts) == 2 and all(p[:1].isupper() for p in parts):
        return "Person"
    if len(parts) >= 3 and any(
        kw in name.lower()
        for kw in ("university", "city", "valley", "francisco", "york", "london", "paris")
    ):
        return "Location"
    if len(parts) <= 3 and name[:1].isupper():
        return "Company"
    return "Other"


# ----------------------------- Driver lifecycle -----------------------------

_driver: Optional[Driver] = None


def get_driver() -> Driver:
    """Lazy-init a singleton Neo4j driver."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


def close_driver() -> None:
    """Close the global driver (call on shutdown / between test runs)."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def test_connection() -> bool:
    """Ping Neo4j with a trivial query. Returns True if reachable."""
    try:
        with get_driver().session() as s:
            return s.run("RETURN 1 AS x").single()["x"] == 1
    except Exception:
        return False


# ----------------------------- Graph operations -----------------------------

def clear_graph() -> None:
    """Delete all nodes and relationships. Used between re-runs."""
    with get_driver().session() as s:
        s.run("MATCH (n) DETACH DELETE n")


def ensure_constraints() -> None:
    """Create uniqueness constraint on Entity.name. Idempotent."""
    with get_driver().session() as s:
        s.run(
            "CREATE CONSTRAINT entity_name IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
        )


def _build_canonical_name_map(triples: Iterable[Triple]) -> dict[str, str]:
    """For each dedup key, choose the longest seen surface form as canonical.

    Why longest? "OpenAI Inc." is more informative than "OpenAI" but they
    share key "openai" / "openai inc." — we pick the first form that maps
    to a key, but if a longer form arrives later we upgrade. This is a
    pragmatic choice that keeps display names reasonable without an LLM.
    """
    canonical: dict[str, str] = {}
    for t in triples:
        for raw in (t.subject, t.object):
            if not raw:
                continue
            k = _normalize_key(raw)
            if not k:
                continue
            existing = canonical.get(k)
            # Compare by non-space character count so "OpenAI" (6) and
            # "Open AI" (6) tie — first-seen wins on tie.
            raw_stripped = raw.strip()
            if existing is None or len(raw_stripped.replace(" ", "")) > len(existing.replace(" ", "")):
                canonical[k] = raw_stripped
    return canonical


def build_graph(triples: list[Triple]) -> GraphStats:
    """Push every triple into Neo4j with deduplication.

    Pre-conditions:
      - clear_graph() has been called if a clean slate is desired
      - ensure_constraints() has been called

    Behavior:
      - Subjects always become entity nodes.
      - Objects become entity nodes regardless of object_type, but the
        type label differs (Year/Money for literals, Company/Person/etc.
        for entities). This keeps the graph traversable for queries that
        ask about literals (e.g., "founded in what year?").
      - Uses apoc.merge.relationship to MERGE relationships with dynamic
        types and a source_idx property.

    Returns:
      GraphStats with counts and top entities by degree.
    """
    if not triples:
        raise ValueError("Cannot build graph from empty triple list")

    canonical = _build_canonical_name_map(triples)
    driver = get_driver()

    # Insert in batches for performance and atomicity per batch
    BATCH = 50
    with driver.session() as s:
        for start in range(0, len(triples), BATCH):
            batch = triples[start:start + BATCH]
            params = []
            for t in batch:
                if not t.subject or not t.object:
                    continue
                s_key = _normalize_key(t.subject)
                o_key = _normalize_key(t.object)
                if not s_key or not o_key:
                    continue
                params.append({
                    "s_name": canonical[s_key],
                    "s_alias": t.subject.strip(),
                    "s_type": _infer_entity_type(canonical[s_key], "entity"),
                    "o_name": canonical[o_key],
                    "o_alias": t.object.strip(),
                    "o_type": _infer_entity_type(canonical[o_key], t.object_type),
                    "rel_type": t.relation,
                    "source_idx": t.source_idx,
                })
            if not params:
                continue
            s.run(
                """
                UNWIND $rows AS row
                MERGE (s:Entity {name: row.s_name})
                  ON CREATE SET s.type = row.s_type, s.aliases = [row.s_alias]
                  ON MATCH SET s.aliases =
                    CASE WHEN row.s_alias IN coalesce(s.aliases, [])
                         THEN s.aliases
                         ELSE coalesce(s.aliases, []) + row.s_alias END
                MERGE (o:Entity {name: row.o_name})
                  ON CREATE SET o.type = row.o_type, o.aliases = [row.o_alias]
                  ON MATCH SET o.aliases =
                    CASE WHEN row.o_alias IN coalesce(o.aliases, [])
                         THEN o.aliases
                         ELSE coalesce(o.aliases, []) + row.o_alias END
                WITH s, o, row
                CALL apoc.merge.relationship(
                  s, row.rel_type, {}, {source_idx: row.source_idx}, o
                ) YIELD rel
                RETURN count(rel)
                """,
                rows=params,
            )

    return get_stats()


# ----------------------------- Stats & queries -----------------------------

def get_stats(top_n: int = 10) -> GraphStats:
    """Compute summary stats from the live graph."""
    with get_driver().session() as s:
        n_nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        n_edges = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        rel_types = s.run(
            "MATCH ()-[r]->() RETURN count(DISTINCT type(r)) AS c"
        ).single()["c"]
        type_dist_rows = s.run(
            "MATCH (n) RETURN coalesce(n.type, 'Other') AS type, count(*) AS c"
        ).data()
        top_rows = s.run(
            "MATCH (n)-[r]-() "
            "RETURN n.name AS name, count(r) AS deg "
            "ORDER BY deg DESC LIMIT $k",
            k=top_n,
        ).data()
    return GraphStats(
        n_nodes=int(n_nodes),
        n_edges=int(n_edges),
        n_unique_relations=int(rel_types),
        n_entity_types={r["type"]: int(r["c"]) for r in type_dist_rows},
        top_entities_by_degree=tuple((r["name"], int(r["deg"])) for r in top_rows),
    )


def fetch_subgraph(
    seed_names: Optional[list[str]] = None,
    limit_nodes: int = 40,
) -> tuple[list[dict], list[dict]]:
    """Fetch a small subgraph for visualization.

    If seed_names is provided, returns nodes within 1 hop of any seed.
    Otherwise returns the top `limit_nodes` highest-degree nodes
    plus all relationships between them.

    Returns:
      (nodes, edges) where:
        nodes = [{"name": str, "type": str, "degree": int}, ...]
        edges = [{"src": str, "dst": str, "type": str}, ...]
    """
    with get_driver().session() as s:
        if seed_names:
            data = s.run(
                """
                UNWIND $seeds AS seed
                MATCH (n:Entity {name: seed})-[r]-(m:Entity)
                RETURN DISTINCT n.name AS src_name, n.type AS src_type,
                       type(r) AS rel_type,
                       m.name AS dst_name, m.type AS dst_type
                """,
                seeds=seed_names,
            ).data()
        else:
            top = s.run(
                "MATCH (n) WITH n, size([(n)--() | 1]) AS deg "
                "ORDER BY deg DESC LIMIT $k RETURN n.name AS name",
                k=limit_nodes,
            ).data()
            top_names = [r["name"] for r in top]
            data = s.run(
                """
                MATCH (n:Entity)-[r]->(m:Entity)
                WHERE n.name IN $names AND m.name IN $names
                RETURN n.name AS src_name, n.type AS src_type,
                       type(r) AS rel_type,
                       m.name AS dst_name, m.type AS dst_type
                """,
                names=top_names,
            ).data()

    nodes_seen: dict[str, dict] = {}
    edges: list[dict] = []
    for row in data:
        for nm, tp in (
            (row["src_name"], row["src_type"]),
            (row["dst_name"], row["dst_type"]),
        ):
            if nm not in nodes_seen:
                nodes_seen[nm] = {"name": nm, "type": tp or "Other"}
        edges.append({"src": row["src_name"], "dst": row["dst_name"], "type": row["rel_type"]})
    return list(nodes_seen.values()), edges


# ----------------------------- Visualization -----------------------------

def export_matplotlib(
    output_path: Path,
    seed_names: Optional[list[str]] = None,
    limit_nodes: int = 30,
    figsize: tuple[int, int] = (16, 12),
) -> Path:
    """Render a subgraph to a PNG using NetworkX + Matplotlib.

    This is a backup deliverable for cases where the Homeowner cannot
    produce a Neo4j Browser screenshot. The view is small (~30 nodes)
    intentionally to remain readable on a printed page.

    Args:
        output_path: Where to save the PNG.
        seed_names: If provided, focus on these nodes and their neighbors.
        limit_nodes: Max nodes to render (only when no seeds).
        figsize: Matplotlib figure size in inches.

    Returns:
        The output_path (so callers can present it).
    """
    import matplotlib
    matplotlib.use("Agg")  # headless safe
    import matplotlib.pyplot as plt
    import networkx as nx

    nodes, edges = fetch_subgraph(seed_names=seed_names, limit_nodes=limit_nodes)
    if not nodes:
        raise ValueError("Subgraph is empty — did you build the graph first?")

    G = nx.MultiDiGraph()
    for n in nodes:
        G.add_node(n["name"], type=n["type"])
    for e in edges:
        G.add_edge(e["src"], e["dst"], label=e["type"])

    type_to_color = {
        "Company":  "#4F8DFD",
        "Person":   "#F7B538",
        "Product":  "#7AC74F",
        "Year":     "#B0B0B0",
        "Money":    "#22A39F",
        "Location": "#E76F51",
        "Other":    "#CDB4DB",
    }
    node_colors = [type_to_color.get(G.nodes[n]["type"], "#CDB4DB") for n in G.nodes()]

    fig, ax = plt.subplots(figsize=figsize)
    pos = nx.spring_layout(G, seed=42, k=1.5, iterations=80)
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=1400, alpha=0.9, ax=ax)
    nx.draw_networkx_labels(G, pos, font_size=8, font_weight="bold", ax=ax)
    nx.draw_networkx_edges(
        G, pos, edge_color="#888", arrows=True, arrowsize=12,
        connectionstyle="arc3,rad=0.08", alpha=0.6, ax=ax,
    )
    edge_labels = {(u, v): d["label"] for u, v, d in G.edges(data=True)}
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=6, ax=ax)

    # Legend
    handles = [
        plt.Line2D([0], [0], marker="o", linestyle="",
                   markerfacecolor=color, markersize=10, label=tp)
        for tp, color in type_to_color.items()
        if any(G.nodes[n]["type"] == tp for n in G.nodes())
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=8)
    ax.set_title(f"Knowledge Graph — {len(G.nodes())} entities, {len(G.edges())} relations")
    ax.axis("off")
    plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ----------------------------- Suggested Cypher queries -----------------------------

def suggested_browser_queries() -> list[tuple[str, str]]:
    """Cypher queries the Homeowner can paste into Neo4j Browser to
    produce the Deliverable #2 screenshot. Returned as (label, cypher).
    """
    return [
        ("Full graph (use only if the graph is small enough)",
         "MATCH (n)-[r]->(m) RETURN n, r, m"),
        ("OpenAI ego network (1 hop)",
         "MATCH (n {name: 'OpenAI'})-[r]-(m) RETURN n, r, m"),
        ("OpenAI 2-hop neighborhood",
         "MATCH p = (n {name: 'OpenAI'})-[*1..2]-(m) RETURN p LIMIT 100"),
        ("Top 30 most connected entities",
         "MATCH (n)-[r]-() WITH n, count(r) AS deg ORDER BY deg DESC LIMIT 30 "
         "MATCH (n)-[r2]-(m) RETURN n, r2, m"),
        ("All companies and their CEOs",
         "MATCH (p)-[r:CEO_OF]->(c) RETURN p, r, c"),
    ]
