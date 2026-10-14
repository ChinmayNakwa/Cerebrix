# backend/core/rag/evaluate.py
"""
Scores the retriever against the golden set: hit rate at 1, 3 and 5 (3 and 5 are the k of retrieve_context
and simple_rag) and mean reciprocal rank, for each retrieval configuration.

    python -m backend.core.rag.evaluate
    python -m backend.core.rag.evaluate --configs hybrid graph --show-misses

Graph parents come after the k search results, so they can only add hits past rank k; "hit@all" counts them.
Their relevance is also compared with that of the search parents ranked just below k.
"""

import argparse
import json
import time
from pathlib import Path

from backend.config import settings
from backend.core.rag.retriever import GRAPH_EXTRA, Retriever

GOLDEN_SET = Path(__file__).with_name("golden_set.json")
MINILM = "cross-encoder/ms-marco-MiniLM-L-6-v2"
CONFIGS = {
    "hybrid": {"expand": False, "reranker": ""},
    "graph": {"expand": True, "reranker": ""},
    "rerank": {"expand": False, "reranker": MINILM},
    "rerank+graph": {"expand": True, "reranker": MINILM},
}
K = 5


def _matches(metadata: dict, expected: dict) -> bool:
    if "book" in expected:
        first, last = expected["book"]
        return metadata["source"] == "book" and metadata["page_start"] <= last and metadata["page_end"] >= first
    if metadata["source"] != "video" or metadata["lecture"] != expected["lecture"]:
        return False
    if "window" not in expected:
        return True
    start, end = expected["window"]
    return metadata["start_sec"] < end and metadata["end_sec"] > start


def _relevant(document, question: dict) -> bool:
    return any(_matches(document.metadata, entry) for entry in question["expected"])


def _first_hit(documents: list, question: dict):
    """1-based rank of the first relevant document and how it was retrieved, or (None, None)."""
    for rank, document in enumerate(documents, start=1):
        if _relevant(document, question):
            return rank, document.metadata["retrieved_by"]
    return None, None


def evaluate(retriever: Retriever, questions: list[dict], expand: bool, reranker: str) -> dict:
    settings.RERANKER_MODEL = reranker
    # Loads the embedding model (and the cross-encoder) outside the timings.
    retriever.search(questions[0]["question"], k=K, expand=expand)
    ranks, seconds = {}, []
    graph_added = graph_relevant = below_k_added = below_k_relevant = 0
    for question in questions:
        started = time.perf_counter()
        documents = retriever.search(question["question"], question.get("filters"), k=K, expand=expand)
        seconds.append(time.perf_counter() - started)
        ranks[question["id"]] = _first_hit(documents, question)
        if not expand:
            continue
        # First-hit ranks cannot credit a graph parent once search has hit, so count its relevance separately,
        # against the search parents ranked just below k that a larger k would have added instead.
        graph = [document for document in documents if document.metadata["retrieved_by"] == "graph"]
        below_k = retriever.search(question["question"], question.get("filters"), k=K + GRAPH_EXTRA,
                                   expand=False)[K:]
        graph_added += len(graph)
        graph_relevant += sum(_relevant(document, question) for document in graph)
        below_k_added += len(below_k)
        below_k_relevant += sum(_relevant(document, question) for document in below_k)

    found = [rank for rank, _ in ranks.values() if rank is not None]
    count = len(questions)
    return {
        "hit@1": sum(rank == 1 for rank in found) / count,
        "hit@3": sum(rank <= 3 for rank in found) / count,
        "hit@5": sum(rank <= K for rank in found) / count,
        "hit@all": len(found) / count,
        "mrr": sum(1 / rank for rank in found) / count,
        "ms_per_query": 1000 * sum(seconds) / count,
        "graph_added": graph_added,
        "graph_relevant": graph_relevant,
        "below_k_added": below_k_added,
        "below_k_relevant": below_k_relevant,
        "ranks": ranks,
    }


def _rank_label(rank, retrieved_by) -> str:
    if rank is None:
        return "-"
    return f"{rank}g" if retrieved_by == "graph" else str(rank)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--configs", nargs="+", choices=list(CONFIGS), default=list(CONFIGS))
    parser.add_argument("--show-misses", action="store_true",
                        help="list only the questions some configuration does not hit in the top 3")
    parser.add_argument("--json", type=Path, help="also write the results to this file")
    args = parser.parse_args()

    questions = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))["questions"]
    retriever = Retriever()
    results = {name: evaluate(retriever, questions, **CONFIGS[name]) for name in args.configs}

    print(f"{len(questions)} questions, k={K}")
    print(f"{'config':<14}{'hit@1':>7}{'hit@3':>7}{'hit@5':>7}{'hit@all':>9}{'MRR':>7}{'ms/q':>8}"
          f"  relevant: graph parents / search ranks {K + 1}-{K + GRAPH_EXTRA}")
    for name, result in results.items():
        extras = (f"  {result['graph_relevant']}/{result['graph_added']} / "
                  f"{result['below_k_relevant']}/{result['below_k_added']}") if result["below_k_added"] else ""
        print(f"{name:<14}{result['hit@1']:>7.2f}{result['hit@3']:>7.2f}{result['hit@5']:>7.2f}{result['hit@all']:>9.2f}"
              f"{result['mrr']:>7.3f}{result['ms_per_query']:>8.0f}{extras}")

    print("\nrank of the first relevant parent (g = added by the graph, - = missed)")
    print(f"{'id':<5}{'kind':<11}" + "".join(f"{name:>14}" for name in results))
    for question in questions:
        ranks = [result["ranks"][question["id"]] for result in results.values()]
        if args.show_misses and all(rank is not None and rank <= 3 for rank, _ in ranks):
            continue
        print(f"{question['id']:<5}{question['kind']:<11}" + "".join(f"{_rank_label(*rank):>14}" for rank in ranks))

    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
