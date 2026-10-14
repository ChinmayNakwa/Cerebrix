# backend/ingestion/ontology_stage.py
"""
Ontology stage: extracts the concepts, definitions, theorems, formulas, distributions, examples and
figures of every parent chunk, merges duplicates across the book and the lectures, and rebuilds the
nodes, edges and node_mentions tables.

    python -m backend.ingestion.ontology_stage
    python -m backend.ingestion.ontology_stage --spot-check "Bayes" "Central Limit" "Binomial"

Each extraction is cached on the parent's text, so running this after chunk_stage (whose store
replaces the chunk ids and so drops node_mentions) only redoes parents that changed. The graph itself
is rebuilt from the cached extractions on every run, which takes seconds.
"""

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Literal

import numpy as np
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from backend.config import settings
from backend.ingestion.chunk_stage import BOOK_TITLE, _Embedder, _location
from backend.ingestion.runner import CACHE_DIR, connect, run_many, run_stage, stage_key
from backend.ingestion.vision import ask, vision_client

NodeType = Literal["Concept", "Definition", "Theorem", "Formula", "Example", "Figure", "Distribution"]
EdgeType = Literal["prerequisite_of", "defined_in", "illustrates", "special_case_of", "uses", "related_to"]


class Entity(BaseModel):
    name: str
    type: NodeType
    description: str
    aliases: list[str] = []
    latex: str | None = None


class Relation(BaseModel):
    source: str
    type: EdgeType
    target: str


class Extraction(BaseModel):
    entities: list[Entity]
    relations: list[Relation]


# Bump when the prompt or schema changes, so cached extractions are redone.
EXTRACT_VERSION = "v3"
EXCERPT_MAX = 8000
EXTRACT_PROMPT = """You are building a concept graph for Stanford CS109, a probability course, from its course reader and lecture videos.

Document: {document}
Location: {location}
Summary: {context}

<excerpt>
{excerpt}
</excerpt>

List the course ideas this excerpt teaches or relies on, and how they relate. Answer in JSON.

Entities (at most 15; skip passing mentions and everyday words):
- Concept: an idea or term, e.g. "Conditional Probability", "Independence", "Expectation".
- Definition: a formal definition the excerpt states for a concept, named "Definition of <concept>".
- Theorem: a named result or law, e.g. "Bayes' Theorem", "Law of Total Probability", "Central Limit Theorem".
- Formula: a specific equation that is not a named theorem, e.g. "Binomial PMF", "Variance of a Sum". A theorem's own equation is not a separate Formula; put it in the theorem's latex.
- Distribution: a named probability distribution, named "<Name> Distribution", e.g. "Binomial Distribution".
- Example: a worked example or problem with its own scenario, named after that scenario, e.g. "Birthday Problem", "Netflix Movie Example".
- Figure: a specific plot, diagram or slide figure the excerpt describes, named after what it shows.
Use the standard textbook name in Title Case and singular, with no prefix such as "Formula:" and no parentheses;
abbreviations and other names go in aliases. description: one sentence in your own words.
aliases: other names for exactly the same thing, used in the excerpt or standard (e.g. "Bayes' Rule"); never a broader or narrower idea.
latex: the main equation of a Formula, Theorem or Definition, otherwise null.

Relations (at most 20), only between entity names from your list and only where the excerpt supports them.
Skip obvious links from basic terms such as Probability, Event or Random Variable to everything else.
- A prerequisite_of B: B cannot be understood without A.
- A special_case_of B: A is B with extra restrictions, e.g. "Bernoulli Distribution" special_case_of "Binomial Distribution".
- A uses B: theorem, formula or example A applies B.
- A illustrates B: example or figure A shows B.
- A defined_in B: concept A is formally defined by Definition or Formula B.
- A related_to B: a clear link that fits none of the above.

Answer with this JSON shape only:
{{"entities": [{{"name": "...", "type": "Concept", "description": "...", "aliases": ["..."], "latex": null}}],
 "relations": [{{"source": "<entity name>", "type": "uses", "target": "<entity name>"}}]}}"""

# Same-type entries whose name embeddings reach MERGE_CHECK go to the text model, which decides.
# There is no automatic merge: bge-base scores names sharing most words (Normal CDF / Standard Normal
# CDF, Likelihood / Log-Likelihood) above 0.95. Different types are never merged.
MERGE_CHECK = 0.85
MERGE_VERSION = "v1"
MERGE_PROMPT = """Two entries of type {type} in the concept graph of a probability course:
A: {a} - {a_description}
B: {b} - {b_description}
Do A and B name exactly the same {type}, so that they should be one entry? A broader or narrower idea, or a different variant, is not the same. Answer yes or no."""


# --- Extraction ---------------------------------------------------------------------------------------

def load_parents() -> list[dict]:
    """Every parent chunk with its source kind and, for lectures, the text of the slides shown in it."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.source_id, s.kind, p.ordinal, p.content, p.context, p.heading_path,
                   p.page_start, p.page_end, p.start_sec, p.end_sec,
                   (SELECT string_agg(c.content, E'\\n\\n' ORDER BY c.ordinal) FROM chunks c
                    WHERE c.parent_id = p.id AND c.modality = 'slide_caption') AS slides
            FROM chunks p JOIN sources s ON s.id = p.source_id
            WHERE p.level = 'parent'
            ORDER BY s.kind, p.source_id, p.ordinal
            """
        ).fetchall()
    columns = ["id", "source_id", "kind", "ordinal", "content", "context", "heading_path",
               "page_start", "page_end", "start_sec", "end_sec", "slides"]
    return [dict(zip(columns, row)) for row in rows]


def _prompt(parent: dict) -> str:
    if parent["kind"] == "book":
        document, excerpt = BOOK_TITLE, parent["content"]
    else:
        document = f"Stanford CS109 lecture video, {parent['heading_path'][0]}"
        excerpt = f"Transcript:\n{parent['content']}"
        if parent["slides"]:
            excerpt += f"\n\nSlides shown:\n{parent['slides']}"
    return EXTRACT_PROMPT.format(document=document, location=_location(parent), context=parent["context"] or "",
                                 excerpt=excerpt[:EXCERPT_MAX])


# Relation types the model invents in place of ours, mapped to (our type, whether to swap the ends).
_INVERSE_RELATIONS = {"used_in": ("uses", True), "defines": ("defined_in", True), "requires": ("prerequisite_of", True),
                      "illustrated_by": ("illustrates", True), "generalization_of": ("special_case_of", True),
                      "generalisation_of": ("special_case_of", True), "has_special_case": ("special_case_of", True)}


def _parse(answer: str) -> dict:
    # Ollama Cloud does not enforce the format schema: it wraps the JSON in a ``` fence, sometimes leaves
    # LaTeX backslashes unescaped, writes null aliases and invents relation types, so all are repaired here.
    answer = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip())
    try:
        data = json.loads(answer)
    except json.JSONDecodeError:
        data = json.loads(re.sub(r'(?<!\\)\\(?![\\"])', r"\\\\", answer))
    relations = []
    for relation in data.get("relations", []):
        source, target = relation.get("source", relation.get("from")), relation.get("target", relation.get("to"))
        relation_type, swap = _INVERSE_RELATIONS.get(relation.get("type"), (relation.get("type"), False))
        if relation_type in EdgeType.__args__ and source and target:
            relations.append({"source": target if swap else source, "type": relation_type,
                              "target": source if swap else target})
    entities = [{**entity, "aliases": entity.get("aliases") or []} for entity in data.get("entities", [])]
    return Extraction.model_validate({**data, "entities": entities, "relations": relations}).model_dump()


def extract(parents: list[dict]) -> int:
    """Extracts every parent's entities and relations, one cached step each. Returns how many failed."""
    client = vision_client()
    schema = Extraction.model_json_schema()
    by_id = {parent["id"]: parent for parent in parents}

    def run(chunk_id: int) -> dict:
        parent = by_id[chunk_id]
        prompt = _prompt(parent)
        key = stage_key("ontology", prompt=hashlib.sha256(prompt.encode()).hexdigest(),
                        model=settings.OLLAMA_TEXT_MODEL, version=EXTRACT_VERSION)
        return run_stage(parent["source_id"], f"ontology_{parent['ordinal']:04d}", key,
                         lambda: _parse(ask(client, prompt, schema)))

    results, failures = run_many(list(by_id), run, max_workers=4)
    for chunk_id, extraction in results:
        by_id[chunk_id]["extraction"] = Extraction.model_validate(extraction)
    return len(failures)


# --- Entity resolution ---------------------------------------------------------------------------------

def normalise(name: str, node_type: str | None = None) -> str:
    """Lower-case ASCII words: "Bayes' Theorem" and "Bayes Theorem" both become "bayes theorem"."""
    text = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)).lower()
    text = re.sub(r"^\s*(concept|definition|theorem|formula|example|figure|distribution)\s*:", "", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"['’`]s\b|['’`]", "", text)
    # Any other symbol, including a non-breaking hyphen, separates words rather than vanishing.
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    text = re.sub(r"^(the|a|an) ", "", text)
    if node_type == "Distribution":
        text = re.sub(r" (distribution|random variable|rv)$", "", text)
    return text


def _key(node_type: str, name: str, source_id: str) -> tuple[str, str]:
    """Resolution key. Figures are tied to the page or slide they come from, so they never merge across sources."""
    key = normalise(name, node_type)
    if node_type == "Figure" and key:
        key = f"{key} @{source_id}"
    return node_type, key


class _Sets:
    """Union-find over (type, normalised name) keys."""

    def __init__(self):
        self.parent = {}

    def find(self, key):
        self.parent.setdefault(key, key)
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def union(self, a, b) -> bool:
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[a] = b
        return a != b


def _cached(stage: str, key: str, fn):
    """File cache for steps that span all sources and so have no manifest row of their own."""
    path = CACHE_DIR / stage / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return result


def _vectors(texts: list[str], embedder: _Embedder) -> np.ndarray:
    key = stage_key("ontology_embed", texts=hashlib.sha256(json.dumps(texts).encode()).hexdigest(),
                    model=settings.VECTOR_EMBEDDING_MODEL)
    path = CACHE_DIR / "ontology_embed" / f"{key}.npy"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, embedder.encode(texts).astype(np.float32))
    return np.load(path)


def _collect(parents: list[dict]) -> dict:
    """Groups every extracted entity by (type, normalised name)."""
    groups = defaultdict(lambda: {"names": Counter(), "book_names": Counter(), "descriptions": [],
                                  "aliases": set(), "chunks": set(), "latex": None, "sources": set()})
    for parent in parents:
        for entity in parent["extraction"].entities:
            key = _key(entity.type, entity.name, parent["source_id"])
            if not key[1]:
                continue
            group = groups[key]
            group["names"][entity.name.strip()] += 1
            if parent["kind"] == "book":
                group["book_names"][entity.name.strip()] += 1
            group["descriptions"].append((parent["kind"] != "book", entity.description.strip()))
            group["aliases"].update(alias.strip() for alias in entity.aliases if alias.strip())
            group["chunks"].add(parent["id"])
            group["sources"].add(parent["source_id"])
            group["latex"] = group["latex"] or entity.latex
    return groups


def _label(group: dict) -> str:
    return group["names"].most_common(1)[0][0]


def _description(group: dict) -> str:
    # Book descriptions first, since the book is the canonical source for names and wording.
    return min(group["descriptions"], key=lambda d: d[0])[1]


def resolve(parents: list[dict], embedder: _Embedder) -> tuple[_Sets, dict, dict]:
    """Merges groups that are the same entity: shared aliases, then close names the text model confirms."""
    groups = _collect(parents)
    sets = _Sets()
    keys = list(groups)
    for key in keys:
        sets.find(key)

    # Candidate pairs: one names the other as an alias, or their names embed close together. Aliases are
    # checked like the rest because the model lists broader ideas ("Parameter" with alias "Mean") and
    # bare symbols ("X"), and one bad alias would chain unrelated nodes together.
    candidates = {}

    def add(a, b) -> None:
        candidates.setdefault(frozenset((a, b)), (a, b))

    vectors = _vectors([_label(groups[k]) for k in keys], embedder)
    for node_type in sorted({k[0] for k in keys} - {"Figure"}):
        index = [i for i, k in enumerate(keys) if k[0] == node_type]
        similarity = vectors[index] @ vectors[index].T
        for a, b in zip(*np.nonzero(np.triu(similarity >= MERGE_CHECK, k=1))):
            add(keys[index[a]], keys[index[b]])
    for key in keys:
        if key[0] == "Figure":
            continue
        for alias in groups[key]["aliases"]:
            other = (key[0], normalise(alias, key[0]))
            if other != key and other in groups and len(other[1].replace(" ", "")) > 2:
                add(key, other)

    client = vision_client()
    stats = Counter()

    def check(pair) -> bool:
        a, b = (groups[k] for k in pair)
        prompt = MERGE_PROMPT.format(type=pair[0][0], a=_label(a), a_description=_description(a),
                                     b=_label(b), b_description=_description(b))
        key = stage_key("ontology_merge", prompt=prompt, model=settings.OLLAMA_TEXT_MODEL, version=MERGE_VERSION)
        return _cached("ontology_merge", key, lambda: {"answer": ask(client, prompt)})["answer"]

    results, failures = run_many(list(candidates.values()), check, max_workers=4)
    if failures:
        raise RuntimeError(f"{len(failures)} merge check(s) failed; re-run to retry them")
    for pair, answer in results:
        if answer.strip().lower().startswith("yes"):
            stats["checked_yes"] += sets.union(*pair)
        else:
            stats["checked_no"] += 1
    return sets, groups, dict(stats)


def build_graph(parents: list[dict], sets: _Sets, groups: dict) -> tuple[dict, dict, Counter]:
    """Turns the merged groups into nodes, and every extraction's relations into weighted edges."""
    members = defaultdict(list)
    owners = defaultdict(set)  # normalised entity name -> the nodes that use it as a name
    for key in groups:
        members[sets.find(key)].append(key)
        for name in groups[key]["names"]:
            owners[normalise(name)].add(sets.find(key))

    nodes = {}
    for root, cluster_keys in members.items():
        cluster = [groups[k] for k in cluster_keys]
        book_names = sum((g["book_names"] for g in cluster), Counter())
        names = book_names or sum((g["names"] for g in cluster), Counter())
        name = names.most_common(1)[0][0]
        canonical = next(k[1] for k in cluster_keys if name in groups[k]["names"])
        best = max(cluster, key=lambda g: (bool(g["book_names"]), sum(g["names"].values())))
        # An alias that is another node's own name ("Bayes' Theorem" listed under Bayesian Inference) is dropped.
        aliases = {n for g in cluster for n in g["names"]}
        aliases |= {a for g in cluster for a in g["aliases"] if root in owners.get(normalise(a), {root})}
        seen, unique = {normalise(name, root[0])}, []
        for alias in sorted(aliases):
            if normalise(alias, root[0]) not in seen:
                seen.add(normalise(alias, root[0]))
                unique.append(alias)
        nodes[root] = {
            "type": root[0], "name": name, "canonical_name": canonical,
            "description": _description(best), "aliases": unique,
            "chunks": set().union(*(g["chunks"] for g in cluster)),
            "metadata": {"latex": next((g["latex"] for g in cluster if g["latex"]), None),
                         "sources": sorted(set().union(*(g["sources"] for g in cluster)))},
        }

    edges, unresolved = {}, Counter()
    for parent in parents:
        local = {}
        for entity in parent["extraction"].entities:
            key = _key(entity.type, entity.name, parent["source_id"])
            if key in groups:
                for name in [entity.name, *entity.aliases]:
                    local.setdefault(normalise(name), sets.find(key))
        for relation in parent["extraction"].relations:
            src, dst = local.get(normalise(relation.source)), local.get(normalise(relation.target))
            if src is None or dst is None:
                unresolved[relation.type] += 1
                continue
            if src == dst:
                continue
            if relation.type == "defined_in" and src[0] == "Definition" and dst[0] != "Definition":
                src, dst = dst, src  # the model sometimes writes "Definition of X defined_in X"
            edge = edges.setdefault((src, dst, relation.type), {"weight": 0, "evidence": parent["id"],
                                                                "book": parent["kind"] == "book"})
            edge["weight"] += 1
            if parent["kind"] == "book" and not edge["book"]:
                edge.update(evidence=parent["id"], book=True)
    return nodes, edges, unresolved


def store(nodes: dict, edges: dict, embedder: _Embedder) -> None:
    """Replaces the whole graph in one transaction."""
    roots = list(nodes)
    vectors = _vectors([f"{nodes[r]['name']}: {nodes[r]['description']}" for r in roots], embedder)
    with connect() as conn:
        register_vector(conn)
        with conn.transaction():
            conn.execute("DELETE FROM nodes")  # cascades to edges and node_mentions
            ids = {}
            for root, vector in zip(roots, vectors):
                node = nodes[root]
                ids[root] = conn.execute(
                    """
                    INSERT INTO nodes (type, name, canonical_name, description, aliases, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """,
                    (node["type"], node["name"], node["canonical_name"], node["description"], node["aliases"],
                     Jsonb(node["metadata"]), vector),
                ).fetchone()[0]
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO edges (src_id, dst_id, type, weight, evidence_chunk_id) VALUES (%s, %s, %s, %s, %s)",
                    [(ids[s], ids[d], t, e["weight"], e["evidence"]) for (s, d, t), e in edges.items()],
                )
                cur.executemany(
                    "INSERT INTO node_mentions (node_id, chunk_id) VALUES (%s, %s)",
                    [(ids[root], chunk) for root, node in nodes.items() for chunk in node["chunks"]],
                )


def run_ontology_stage() -> dict:
    parents = load_parents()
    failed = extract(parents)
    if failed:
        raise RuntimeError(f"{failed} extraction(s) failed; re-run to retry them")
    embedder = _Embedder()
    sets, groups, merges = resolve(parents, embedder)
    nodes, edges, unresolved = build_graph(parents, sets, groups)
    store(nodes, edges, embedder)
    return {"parents": len(parents), "entities": sum(len(p["extraction"].entities) for p in parents),
            "groups": len(groups), "merges": merges, "nodes": dict(Counter(n["type"] for n in nodes.values())),
            "edges": dict(Counter(t for _, _, t in edges)), "unresolved_relations": dict(unresolved)}


# --- Spot check ----------------------------------------------------------------------------------------

def spot_check(terms: list[str]) -> None:
    with connect() as conn:
        for term in terms:
            rows = conn.execute(
                """
                SELECT n.id, n.type, n.name, n.aliases, n.description,
                       (SELECT count(*) FROM node_mentions m WHERE m.node_id = n.id) AS mentions,
                       n.metadata->'sources'
                FROM nodes n
                WHERE n.name ILIKE %(t)s OR EXISTS (SELECT 1 FROM unnest(n.aliases) a WHERE a ILIKE %(t)s)
                ORDER BY mentions DESC
                """,
                {"t": f"%{term}%"},
            ).fetchall()
            print(f"\n=== {term}: {len(rows)} node(s)")
            for node_id, node_type, name, aliases, description, mentions, sources in rows:
                print(f"- [{node_type}] {name}  ({mentions} mentions, {len(sources)} sources)  aliases={aliases}")
                print(f"    {description}")
                for direction, sql in (("->", "SELECT e.type, n.name, e.weight FROM edges e JOIN nodes n ON n.id = e.dst_id "
                                               "WHERE e.src_id = %s ORDER BY e.weight DESC"),
                                       ("<-", "SELECT e.type, n.name, e.weight FROM edges e JOIN nodes n ON n.id = e.src_id "
                                              "WHERE e.dst_id = %s ORDER BY e.weight DESC")):
                    for edge_type, other, weight in conn.execute(sql, (node_id,)).fetchall()[:8]:
                        print(f"    {direction} {edge_type} {other} (x{weight:g})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spot-check", nargs="+", metavar="TERM", help="only print the nodes matching each term")
    args = parser.parse_args()
    if args.spot_check:
        spot_check(args.spot_check)
    else:
        print(json.dumps(run_ontology_stage(), indent=2))


if __name__ == "__main__":
    main()
