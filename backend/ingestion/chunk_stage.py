# backend/ingestion/chunk_stage.py
"""
Chunk stage: turns the cached book pages and lecture captions/slides into parent and child chunks,
writes a short context line per parent, embeds the children and stores everything in Postgres.

    python -m backend.ingestion.chunk_stage --book --lectures 4 18
    python -m backend.ingestion.chunk_stage --lectures 18

Parents are what the answer step reads: a book section, or a few minutes of a lecture. Children are
what gets embedded and searched. Each step is cached, so a re-run only redoes what changed.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb

from backend.config import settings
from backend.ingestion.pdf_stage import SOURCE_ID as BOOK_SOURCE_ID, run_pdf_stage
from backend.ingestion.pdf_vision import run_vision_fallback
from backend.ingestion.runner import CACHE_DIR, connect, run_many, run_stage, stage_key
from backend.ingestion.video_stage import find_lectures, run_video_stage
from backend.ingestion.vision import ask, vision_client

BOOK_TITLE = "Probability for Computer Scientists (Stanford CS109 course reader)"
# Characters per chunk. Book sections longer than PARENT_MAX are split into several parents.
PARENT_MAX = 4000
CHILD_MAX = 1000
MIN_SECTION = 200
MIN_PIECE = 150
# Seconds per lecture parent: close at the first sentence end after TARGET, or at MAX regardless.
WINDOW_TARGET_SEC = 150
WINDOW_MAX_SEC = 240
CHILD_TARGET = 700
# Bump when the prompt changes, so cached context lines are redone.
CONTEXT_VERSION = "v1"
CONTEXT_PROMPT = (
    "Document: {document}\n"
    "Location: {location}\n\n"
    "<excerpt>\n{excerpt}\n</excerpt>\n\n"
    "Write one sentence of at most 30 words that situates this excerpt within the document, naming its "
    "topic and the main ideas it covers, to improve search retrieval. Output only the sentence."
)

_PAGE_MARKER = re.compile(r"<!-- page (\d+) -->")
_HEADING = re.compile(r"#{1,6}\s+(.+)")


def _chunk(content: str, **fields) -> dict:
    return {"content": content, "modality": "text", "heading_path": [], "page_start": None, "page_end": None,
            "start_sec": None, "end_sec": None, "image_url": None, "metadata": {}, **fields}


def _blocks(text: str) -> list[str]:
    """Paragraphs, keeping a $$...$$ equation or a ``` code block in one piece even if it has blank lines."""
    blocks, pending = [], []
    for paragraph in re.split(r"\n\s*\n", text):
        pending.append(paragraph)
        joined = "\n\n".join(pending)
        if joined.count("$$") % 2 == 0 and joined.count("```") % 2 == 0:
            blocks.append(joined.strip())
            pending = []
    if pending:
        blocks.append("\n\n".join(pending).strip())
    return [block for block in blocks if block]


def _pack(text: str, limit: int) -> list[str]:
    """Greedily packs paragraphs into pieces of at most limit characters, splitting long prose by sentence."""
    parts = []
    for block in _blocks(text):
        if len(block) <= limit or "$$" in block or "```" in block or block.lstrip().startswith("|"):
            parts.append(block)
        else:
            parts.extend(re.split(r"(?<=[.!?])\s+", block))

    pieces, current = [], ""
    for part in parts:
        if current and len(current) + len(part) + 2 > limit:
            pieces.append(current)
            current = part
        else:
            current = f"{current}\n\n{part}" if current else part
    if current:
        # A short leftover is too little to search on its own, so it joins the piece before it.
        if pieces and len(_PAGE_MARKER.sub("", current).strip()) < MIN_PIECE:
            pieces[-1] = f"{pieces[-1]}\n\n{current}"
        else:
            pieces.append(current)
    return pieces


def _with_pages(pieces: list[str], start_page: int) -> list[tuple[str, int, int]]:
    """Strips the page markers from each piece and returns (text, first page, last page)."""
    result, page = [], start_page
    for piece in pieces:
        first = page
        markers = [(m.start(), int(m.group(1))) for m in _PAGE_MARKER.finditer(piece)]
        if markers and not piece[:markers[0][0]].strip():
            first = markers[0][1]
        if markers:
            page = markers[-1][1]
        text = re.sub(r"\n{3,}", "\n\n", _PAGE_MARKER.sub("", piece)).strip()
        if text:
            result.append((text, first, page))
    return result


# --- Book -------------------------------------------------------------------------------------------

def _page_number(docling_markdown: str) -> int | None:
    """The page number Docling read at the top of the page. Each article of the reader restarts at 1."""
    match = re.match(r"\s*(?:This is a header\s+)?(\d+)\s*\n", docling_markdown)
    return int(match.group(1)) if match else None


def _clean_page(markdown: str) -> str:
    text = re.sub(r"\s*(?:This is a header\s+)?\d+\s*\n", "", markdown, count=1) if _page_number(markdown) else markdown
    text = text.replace("<!-- image -->", "")
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    # Keep link text only: the URLs are localhost or invented by the vision model.
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).strip()


def _book_sections(pages: list[dict], vision: dict[int, str]) -> list[dict]:
    """Splits the book at headings. A page whose article page number is 1 (or missing) starts an article."""
    sections: list[dict] = []
    article, current = None, None
    for page in pages:
        page_no = page["page"]
        new_article = _page_number(page["markdown"]) in (None, 1)
        for line in _clean_page(vision.get(page_no) or page["markdown"]).splitlines():
            if re.fullmatch(r"#+\s*", line):
                continue
            heading = _HEADING.match(line)
            if heading:
                title = heading.group(1).strip().strip("*").strip()
                if new_article or article is None:
                    article, new_article = title, False
                current = {"heading_path": [article] if title == article else [article, title],
                           "lines": [], "page_start": page_no, "page_end": page_no}
                sections.append(current)
                continue
            if current is None:
                current = {"heading_path": [], "lines": [], "page_start": page_no, "page_end": page_no}
                sections.append(current)
            if current["page_end"] != page_no:
                current["lines"] += ["", f"<!-- page {page_no} -->", ""]
                current["page_end"] = page_no
            current["lines"].append(line)

    # Fold sections too short to stand alone (a heading straight before a subheading) into the next one.
    merged: list[dict] = []
    carry = None
    for section in sections:
        content = "\n".join(section["lines"]).strip()
        if carry and carry["heading_path"][:1] == section["heading_path"][:1]:
            content = f"{carry['content']}\n\n{content}".strip()
            section["page_start"] = carry["page_start"]
        elif carry and _PAGE_MARKER.sub("", carry["content"]).strip():
            merged.append(carry)
        carry = None
        if len(_PAGE_MARKER.sub("", content).strip()) < MIN_SECTION:
            # Keep the folded section's heading as text, since the next section's heading replaces it.
            heading = section["heading_path"][-1] if len(section["heading_path"]) > 1 else ""
            carry = {**section, "content": f"{heading}\n\n{content}".strip()}
            continue
        merged.append({**section, "content": content})
    if carry and _PAGE_MARKER.sub("", carry["content"]).strip():
        merged.append(carry)
    return merged


def book_plan() -> list[dict]:
    pdf_path = Path(settings.PDF_PATH)
    pages = run_pdf_stage(pdf_path)
    vision = run_vision_fallback(pdf_path, pages)

    parents = []
    for section in _book_sections(pages, vision):
        page = section["page_start"]
        # Pieces keep their page markers until split into children, so each child gets its own page range.
        for piece in _pack(section["content"], PARENT_MAX):
            cleaned = _with_pages([piece], page)
            if not cleaned:
                continue
            text, page, last = cleaned[0]
            children = [_chunk(child, heading_path=section["heading_path"], page_start=first, page_end=end)
                        for child, first, end in _with_pages(_pack(piece, CHILD_MAX), page)]
            parents.append(_chunk(text, heading_path=section["heading_path"], page_start=page, page_end=last,
                                  children=children))
            page = last
    return parents


# --- Lectures -----------------------------------------------------------------------------------------

def _lecture_title(lecture: dict) -> str:
    parts = [part.strip() for part in lecture["title"].split(" I ")]
    topic = parts[-3] if len(parts) >= 3 else lecture["title"]
    return f"CS109 Lecture {lecture['lecture']}: {topic}"


def _group(snippets: list[dict], done) -> list[list[dict]]:
    groups, current = [], []
    for snippet in snippets:
        current.append(snippet)
        if done(current):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _sentence_end(snippet: dict) -> bool:
    return snippet["text"].rstrip().endswith((".", "?", "!"))


def _end(snippets: list[dict]) -> float:
    return snippets[-1]["start"] + snippets[-1]["duration"]


def _best_slide(slides: list[dict], start: float, end: float) -> dict | None:
    """The slide on screen for most of [start, end], if any."""
    best, best_overlap = None, 0.0
    for slide in slides:
        overlap = sum(max(0.0, min(end, s_end) - max(start, s_start)) for s_start, s_end in slide["spans"])
        if overlap > best_overlap:
            best, best_overlap = slide, overlap
    return best


def lecture_plan(lecture: dict) -> list[dict]:
    video = run_video_stage(lecture)
    title = _lecture_title(lecture)
    slides = [s for s in video["slides"] if s["text"] and len(s["text"].strip()) >= 20 and s["image_url"]]

    windows = _group(video["captions"]["snippets"], lambda g: (
        _end(g) - g[0]["start"] >= WINDOW_MAX_SEC
        or (_end(g) - g[0]["start"] >= WINDOW_TARGET_SEC and _sentence_end(g[-1]))))

    parents = []
    for window in windows:
        start, end = window[0]["start"], _end(window)
        children = []
        for piece in _group(window, lambda g: (
                sum(len(s["text"]) + 1 for s in g) >= CHILD_MAX
                or (sum(len(s["text"]) + 1 for s in g) >= CHILD_TARGET and _sentence_end(g[-1])))):
            p_start, p_end = piece[0]["start"], _end(piece)
            slide = _best_slide(slides, p_start, p_end)
            children.append(_chunk(" ".join(s["text"] for s in piece), modality="transcript", heading_path=[title],
                                   start_sec=round(p_start, 2), end_sec=round(p_end, 2),
                                   image_url=slide["image_url"] if slide else None,
                                   metadata={"slide_keyframe": slide["keyframe"]} if slide else {}))
        parents.append(_chunk(" ".join(s["text"] for s in window), modality="transcript", heading_path=[title],
                              start_sec=round(start, 2), end_sec=round(end, 2), children=children))

    # Each slide becomes a child of the window where it first appears.
    for slide in slides:
        parent = next((p for p in parents if p["start_sec"] <= slide["start_sec"] < p["end_sec"]), None)
        parent = parent or min(parents, key=lambda p: abs(p["start_sec"] - slide["start_sec"]))
        parent["children"].append(_chunk(slide["text"], modality="slide_caption", heading_path=[title],
                                         start_sec=slide["start_sec"], end_sec=slide["spans"][0][1],
                                         image_url=slide["image_url"],
                                         metadata={"keyframe": slide["keyframe"], "spans": slide["spans"]}))
    for parent in parents:
        parent["children"].sort(key=lambda c: c["start_sec"])
    return parents


# --- Context, embedding and storage --------------------------------------------------------------------

def _location(parent: dict) -> str:
    if parent["start_sec"] is not None:
        start, end = (f"{int(t) // 60}:{int(t) % 60:02d}" for t in (parent["start_sec"], parent["end_sec"]))
        return f"{parent['heading_path'][0]}, transcript from {start} to {end}"
    pages = f"page {parent['page_start']}" if parent["page_start"] == parent["page_end"] \
        else f"pages {parent['page_start']}-{parent['page_end']}"
    return f"{' > '.join(parent['heading_path']) or 'front matter'}, {pages}"


def add_context(source_id: str, document: str, parents: list[dict]) -> int:
    """Writes the context line of every parent, one cached step each. Returns how many failed."""
    client = vision_client()

    def write(item: tuple[int, dict]) -> str:
        ordinal, parent = item
        prompt = CONTEXT_PROMPT.format(document=document, location=_location(parent),
                                       excerpt=parent["content"][:6000])
        key = stage_key("context", prompt=hashlib.sha256(prompt.encode()).hexdigest(),
                        model=settings.OLLAMA_TEXT_MODEL, version=CONTEXT_VERSION)
        return run_stage(source_id, f"context_{ordinal:04d}", key,
                         lambda: {"context": ask(client, prompt)})["context"]

    results, failures = run_many(list(enumerate(parents)), write, max_workers=4)
    for (ordinal, parent), context in results:
        parent["context"] = context
    return len(failures)


def _embedding_text(chunk: dict, context: str | None) -> str:
    heading = " > ".join(chunk["heading_path"])
    return "\n".join(part for part in (context, heading, chunk["content"]) if part)


class _Embedder:
    """Loads the embedding model only when some source actually needs embedding."""

    def __init__(self):
        self._model = None

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(settings.VECTOR_EMBEDDING_MODEL, device="cpu")
        return self._model.encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=True)


def embed(source_id: str, parents: list[dict], embedder: _Embedder) -> np.ndarray:
    texts = [_embedding_text(child, parent.get("context")) for parent in parents for child in parent["children"]]
    key = stage_key("embed", texts=hashlib.sha256(json.dumps(texts).encode()).hexdigest(),
                    model=settings.VECTOR_EMBEDDING_MODEL)
    path = CACHE_DIR / "embed" / f"{key}.npy"

    def call() -> dict:
        vectors = embedder.encode(texts)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, vectors.astype(np.float32))
        return {"file": str(path), "count": len(texts)}

    return np.load(run_stage(source_id, "embed", key, call)["file"])


def store(source_id: str, parents: list[dict], vectors: np.ndarray) -> dict:
    """Replaces the source's chunks in one transaction."""
    key = stage_key("store", plan=hashlib.sha256(json.dumps(parents, sort_keys=True).encode()).hexdigest(),
                    vectors=hashlib.sha256(vectors.tobytes()).hexdigest())

    def insert(conn, chunk: dict, level: str, ordinal: int, parent_id, context, embedding) -> int:
        return conn.execute(
            """
            INSERT INTO chunks (source_id, parent_id, level, modality, ordinal, content, context, heading_path,
                                page_start, page_end, start_sec, end_sec, image_url, metadata, content_hash, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, level, content_hash) DO UPDATE SET ordinal = chunks.ordinal
            RETURNING id
            """,
            (source_id, parent_id, level, chunk["modality"], ordinal, chunk["content"], context,
             chunk["heading_path"], chunk["page_start"], chunk["page_end"], chunk["start_sec"], chunk["end_sec"],
             chunk["image_url"], Jsonb(chunk["metadata"]), hashlib.sha256(chunk["content"].encode()).hexdigest(),
             embedding),
        ).fetchone()[0]

    def call() -> dict:
        with connect() as conn:
            register_vector(conn)
            with conn.transaction():
                conn.execute("DELETE FROM chunks WHERE source_id = %s", (source_id,))
                child_ordinal = 0
                for parent_ordinal, parent in enumerate(parents):
                    parent_id = insert(conn, parent, "parent", parent_ordinal, None, parent.get("context"), None)
                    for child in parent["children"]:
                        insert(conn, child, "child", child_ordinal, parent_id, parent.get("context"),
                               vectors[child_ordinal])
                        child_ordinal += 1
        return {"parents": len(parents), "children": child_ordinal}

    return run_stage(source_id, "store", key, call)


def run_chunk_stage(source_id: str, document: str, build_plan, embedder: _Embedder) -> dict:
    # The plan is rebuilt every run from the cached pages and lecture stages, which takes seconds;
    # the context lines, embeddings and the write are each cached on their exact inputs.
    parents = build_plan()
    failed = add_context(source_id, document, parents)
    if failed:
        raise RuntimeError(f"{source_id}: {failed} context line(s) failed; re-run to retry them")
    vectors = embed(source_id, parents, embedder)
    stored = store(source_id, parents, vectors)
    return {"source": source_id, **stored, "longest_child": max(len(c["content"]) for p in parents for c in p["children"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--book", action="store_true")
    parser.add_argument("--lectures", type=int, nargs="*", metavar="N", help="lecture numbers; none means all")
    args = parser.parse_args()

    embedder = _Embedder()
    if args.book:
        print(json.dumps(run_chunk_stage(BOOK_SOURCE_ID, BOOK_TITLE, book_plan, embedder)))
    if args.lectures is not None:
        for lecture in find_lectures():
            if not args.lectures or lecture["lecture"] in args.lectures:
                source_id = f"video:{lecture['video_id']}"
                document = f"Stanford CS109 lecture video, {_lecture_title(lecture)}"
                print(json.dumps(run_chunk_stage(source_id, document, lambda l=lecture: lecture_plan(l), embedder)))


if __name__ == "__main__":
    main()
