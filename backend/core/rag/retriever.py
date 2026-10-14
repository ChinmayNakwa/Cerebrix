# backend/core/rag/retriever.py
"""
Hybrid retrieval over the ingested chunks. Child chunks are searched by pgvector similarity and by
Postgres full-text search, the two rankings are fused by reciprocal rank and grouped into their
parents, and the result is widened by one hop through the ontology graph.

Returns LangChain Documents holding the parent text with its page range, timestamps and slide images,
so the agent's nodes keep working on Documents.
"""

import re
from typing import Optional

from langchain_core.documents import Document
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from backend.config import settings

# bge models embed queries with this instruction; the documents were embedded without it.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CANDIDATES = 30       # children taken from each of the vector and full-text rankings
RRF_K = 60
RERANK_CANDIDATES = 20  # fused children re-scored when settings.RERANKER_MODEL is set
GRAPH_SEEDS = 3       # nodes of the top hits closest to the query
GRAPH_EXTRA = 2       # parents added through the graph
STRONG_EDGE_TYPES = ["prerequisite_of", "special_case_of"]
MIN_EDGE_WEIGHT = 2   # other edge types count only when two or more chunks support them

_LECTURE = re.compile(r"lecture\s*(\d+)", re.IGNORECASE)


def _configure(conn) -> None:
    register_vector(conn)
    # Filtered HNSW scans keep going until enough rows pass the filter (pgvector 0.8).
    conn.execute("SET hnsw.iterative_scan = relaxed_order")


class Retriever:
    def __init__(self):
        self._pool = ConnectionPool(settings.POSTGRES_DB_URL, min_size=1, max_size=4, open=False,
                                    configure=_configure, kwargs={"autocommit": True})
        self._model = None
        self._reranker = None

    def _embed(self, text: str):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(settings.VECTOR_EMBEDDING_MODEL, device="cpu")
        return self._model.encode(QUERY_PREFIX + text, normalize_embeddings=True)

    def search(self, query: str, filters: Optional[dict] = None, k: int = 5, expand: bool = True) -> list[Document]:
        """The k best parents for the query, then up to GRAPH_EXTRA more reached through the graph."""
        self._pool.open()
        where, params = _where(filters or {})
        vector = self._embed(query)
        with self._pool.connection() as conn:
            ranked = self._hybrid(conn, query, vector, where, params)
            top = list(ranked)[:k]
            extra = self._expand(conn, vector, top, where, params) if expand and top else {}
            parents = _load_parents(conn, top + list(extra))
        documents = []
        for parent_id in top:
            documents.append(_document(parents[parent_id], "search", ranked[parent_id]))
        for parent_id, node_name in extra.items():
            documents.append(_document(parents[parent_id], "graph", None, node_name))
        return documents

    def _hybrid(self, conn, query: str, vector, where: str, params: dict) -> dict[int, float]:
        """Parent id -> fused score, best first. A parent scores as its best child."""
        vector_hits = conn.execute(
            f"""
            WITH hits AS MATERIALIZED (
                SELECT c.id, c.parent_id, c.embedding <=> %(vector)s AS distance
                FROM chunks c JOIN sources s ON s.id = c.source_id
                WHERE c.level = 'child' {where}
                ORDER BY distance LIMIT %(n)s
            )
            SELECT id, parent_id FROM hits ORDER BY distance
            """,
            {**params, "vector": vector, "n": CANDIDATES},
        ).fetchall()
        # Any query word may match (OR), ranked by cover density, so a long question still finds hits.
        text_hits = conn.execute(
            f"""
            WITH q AS (SELECT to_tsquery('english', string_agg(lexeme, ' | ')) AS q
                       FROM unnest(to_tsvector('english', %(query)s)))
            SELECT c.id, c.parent_id
            FROM chunks c JOIN sources s ON s.id = c.source_id, q
            WHERE c.level = 'child' AND c.tsv @@ q.q {where}
            ORDER BY ts_rank_cd(c.tsv, q.q) DESC LIMIT %(n)s
            """,
            {**params, "query": query, "n": CANDIDATES},
        ).fetchall()

        child_scores, parent_of = {}, {}
        for hits in (vector_hits, text_hits):
            for rank, (child_id, parent_id) in enumerate(hits):
                child_scores[child_id] = child_scores.get(child_id, 0.0) + 1 / (RRF_K + rank + 1)
                parent_of[child_id] = parent_id
        if settings.RERANKER_MODEL and child_scores:
            child_scores = self._rerank(conn, query, child_scores)

        parents = {}
        for child_id, score in child_scores.items():
            parent_id = parent_of[child_id]
            parents[parent_id] = max(parents.get(parent_id, 0.0), score)
        return dict(sorted(parents.items(), key=lambda item: item[1], reverse=True))

    def _rerank(self, conn, query: str, child_scores: dict[int, float]) -> dict[int, float]:
        """Re-orders the best fused children by cross-encoder score; they then rank above all the others."""
        if self._reranker is None:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(settings.RERANKER_MODEL, device="cpu")
        best = sorted(child_scores, key=child_scores.get, reverse=True)[:RERANK_CANDIDATES]
        texts = dict(conn.execute("SELECT id, content FROM chunks WHERE id = ANY(%s)", (best,)).fetchall())
        scores = self._reranker.predict([(query, texts[child_id]) for child_id in best])
        order = sorted(zip(best, scores), key=lambda item: item[1], reverse=True)
        # Fused scores stay below 1, so 1 + 1/rank puts every reranked child first, in cross-encoder order.
        return {**child_scores, **{child_id: 1 + 1 / (rank + 1) for rank, (child_id, _) in enumerate(order)}}

    def _expand(self, conn, vector, top: list[int], where: str, params: dict) -> dict[int, str]:
        """
        Parent id -> node name for up to GRAPH_EXTRA parents about ideas next to the top hits'.
        The seeds are the top hits' nodes closest to the query. Their strong neighbours that the top hits
        do not already mention are followed, each to the parent mentioning it that best matches the query.
        """
        neighbours = conn.execute(
            """
            WITH hit_nodes AS (SELECT DISTINCT node_id FROM node_mentions WHERE chunk_id = ANY(%(top)s)),
            seeds AS (
                SELECT n.id FROM nodes n
                WHERE n.id IN (SELECT node_id FROM hit_nodes) AND n.type NOT IN ('Example', 'Figure')
                ORDER BY n.embedding <=> %(vector)s LIMIT %(seeds)s
            ),
            neighbours AS (
                SELECT CASE WHEN e.src_id = s.id THEN e.dst_id ELSE e.src_id END AS id, max(e.weight) AS weight
                FROM seeds s JOIN edges e ON s.id IN (e.src_id, e.dst_id)
                WHERE e.weight >= %(min_weight)s OR e.type = ANY(%(strong)s)
                GROUP BY 1
            )
            SELECT n.id, n.name
            FROM neighbours nb JOIN nodes n ON n.id = nb.id
            WHERE nb.id NOT IN (SELECT node_id FROM hit_nodes) AND n.type NOT IN ('Example', 'Figure')
            ORDER BY n.embedding <=> %(vector)s
            LIMIT %(extra)s
            """,
            {"top": top, "vector": vector, "seeds": GRAPH_SEEDS, "min_weight": MIN_EDGE_WEIGHT,
             "strong": STRONG_EDGE_TYPES, "extra": GRAPH_EXTRA},
        ).fetchall()

        extra = {}
        for node_id, name in neighbours:
            row = conn.execute(
                f"""
                SELECT c.parent_id
                FROM node_mentions m JOIN chunks c ON c.parent_id = m.chunk_id JOIN sources s ON s.id = c.source_id
                WHERE m.node_id = %(node)s AND c.level = 'child' AND NOT c.parent_id = ANY(%(exclude)s) {where}
                ORDER BY c.embedding <=> %(vector)s LIMIT 1
                """,
                {**params, "node": node_id, "vector": vector, "exclude": top + list(extra)},
            ).fetchone()
            if row:
                extra[row[0]] = name
        return extra


def _lecture_number(keyword: Optional[str]) -> Optional[int]:
    match = _LECTURE.search(keyword or "")
    return int(match.group(1)) if match else None


def _where(filters: dict) -> tuple[str, dict]:
    """
    Turns the agent's filters into SQL over chunks c joined with sources s. A page number matches the
    book chunks whose page range covers it; "Lecture N" matches that lecture's chunks; any other title
    keyword matches source titles. With both a page and a lecture, either may match.
    """
    clauses, params = [], {}
    if filters.get("page_number"):
        clauses.append("(s.kind = 'book' AND c.page_start <= %(page)s AND c.page_end >= %(page)s)")
        params["page"] = int(filters["page_number"])
    keyword = filters.get("title_keyword")
    lecture = _lecture_number(keyword)
    if lecture is not None:
        clauses.append("(s.kind = 'video' AND (s.metadata->>'lecture')::int = %(lecture)s)")
        params["lecture"] = lecture
    elif keyword:
        clauses.append("s.title ILIKE %(title)s")
        params["title"] = f"%{keyword}%"
    return (f"AND ({' OR '.join(clauses)})" if clauses else ""), params


def _load_parents(conn, parent_ids: list[int]) -> dict[int, dict]:
    rows = conn.execute(
        """
        SELECT p.id, p.source_id, s.kind, s.title, s.uri, (s.metadata->>'lecture')::int, p.content, p.context,
               p.heading_path, p.page_start, p.page_end, p.start_sec, p.end_sec,
               ARRAY(SELECT c.image_url FROM chunks c WHERE c.parent_id = p.id AND c.image_url IS NOT NULL
                     GROUP BY c.image_url ORDER BY min(c.ordinal))
        FROM chunks p JOIN sources s ON s.id = p.source_id
        WHERE p.id = ANY(%s)
        """,
        (parent_ids,),
    ).fetchall()
    columns = ["id", "source_id", "kind", "title", "uri", "lecture", "content", "context", "heading_path",
               "page_start", "page_end", "start_sec", "end_sec", "image_urls"]
    return {row[0]: dict(zip(columns, row)) for row in rows}


def _document(parent: dict, retrieved_by: str, score: Optional[float], graph_node: Optional[str] = None) -> Document:
    metadata = {
        "chunk_id": parent["id"], "source_id": parent["source_id"], "source": parent["kind"],
        "section": " > ".join(parent["heading_path"]), "context": parent["context"],
        "page_start": parent["page_start"], "page_end": parent["page_end"],
        "start_sec": parent["start_sec"], "end_sec": parent["end_sec"], "image_urls": parent["image_urls"],
        "retrieved_by": retrieved_by, "score": score, "graph_node": graph_node,
    }
    if parent["kind"] == "video":
        metadata.update(title=parent["title"], lecture=parent["lecture"],
                        video_id=parent["source_id"].removeprefix("video:"),
                        video_url=f"{parent['uri']}&t={int(parent['start_sec'])}s")
    return Document(page_content=parent["content"], metadata=metadata)
