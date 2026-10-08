# backend/ingestion/pdf_vision.py
"""
Vision fallback for the PDF stage: re-reads the pages Docling flagged as hard (undecoded formulas,
little text) by rendering each one to an image and asking a vision model for markdown with LaTeX.

    python -m backend.ingestion.pdf_vision --pages 5 5
    python -m backend.ingestion.pdf_vision
"""

import argparse
import hashlib
import json
from pathlib import Path

import pymupdf

from backend.config import settings
from backend.ingestion.pdf_stage import SOURCE_ID, run_pdf_stage
from backend.ingestion.runner import run_many, run_stage, stage_key
from backend.ingestion.vision import read_image, vision_client

RENDER_DPI = 150
# Bump when the prompt changes, so cached vision pages are redone.
PROMPT_VERSION = "v1"
PROMPT = (
    "Transcribe this textbook page to markdown. Write every mathematical expression as LaTeX, "
    "inline as $...$ and display equations as $$...$$. Keep headings, lists and tables. "
    "For a figure or plot, write one line starting with 'Figure:' that says what it shows. "
    "Output only the transcription, with no commentary."
)


def _render_page(pdf_path: Path, page_no: int) -> bytes:
    with pymupdf.open(pdf_path) as pdf:
        return pdf[page_no - 1].get_pixmap(dpi=RENDER_DPI).tobytes("png")


def run_vision_fallback(pdf_path: Path, pages: list[dict], max_workers: int = 3) -> dict[int, str]:
    """Transcribes the hard pages among `pages`. Returns {page_no: markdown} for those that succeeded."""
    client = vision_client()

    def transcribe_page(page: dict) -> str:
        page_no = page["page"]
        docling_hash = hashlib.sha256(page["markdown"].encode()).hexdigest()
        key = stage_key("pdf_vision", docling=docling_hash, model=settings.OLLAMA_VISION_MODEL,
                        dpi=RENDER_DPI, prompt=PROMPT_VERSION)

        def call() -> dict:
            return {"page": page_no, "model": settings.OLLAMA_VISION_MODEL,
                    "markdown": read_image(client, _render_page(pdf_path, page_no), PROMPT)}

        return run_stage(SOURCE_ID, f"pdfvision_{page_no:04d}", key, call)["markdown"]

    hard = [p for p in pages if p["hard"]]
    results, failures = run_many(hard, transcribe_page, max_workers=max_workers)
    if failures:
        print(f"  {len(failures)} page(s) failed; re-run to retry them")
    return {page["page"]: markdown for page, markdown in results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=int, nargs=2, metavar=("FIRST", "LAST"))
    args = parser.parse_args()

    pdf_path = Path(settings.PDF_PATH)
    first, last = args.pages or (None, None)
    pages = run_pdf_stage(pdf_path, first, last)
    transcribed = run_vision_fallback(pdf_path, pages)
    print(json.dumps({"pages": len(pages), "hard_pages": sum(p["hard"] for p in pages),
                      "transcribed": len(transcribed)}))


if __name__ == "__main__":
    main()
