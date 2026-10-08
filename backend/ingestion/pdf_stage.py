# backend/ingestion/pdf_stage.py
"""
PDF stage: converts the book to per-page markdown with Docling, in resumable page batches.

    python -m backend.ingestion.pdf_stage
    python -m backend.ingestion.pdf_stage --pages 1 40

Formula enrichment is off (it does not finish on this CPU), so Docling leaves a placeholder where
a formula was not decoded. Pages with those, or with almost no text, are flagged hard=True for the
vision fallback to pick up.
"""

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import pymupdf

from backend.config import settings
from backend.ingestion.runner import connect, fingerprint, run_stage, stage_key, upsert_source

SOURCE_ID = "book:probability-for-computer-scientists"
BATCH_PAGES = 20
FORMULA_PLACEHOLDER = "<!-- formula-not-decoded -->"
MIN_TEXT_CHARS = 200
# Bump when the conversion options change, so cached batches are redone.
PIPELINE_VERSION = "docling-2.135-noformula-1"


def _build_converter():
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_formula_enrichment = False
    options.accelerator_options = AcceleratorOptions(num_threads=8, device="cpu")

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    converter.initialize_pipeline(InputFormat.PDF)
    return converter


def _convert_batch(converter, pdf_path: Path, first: int, last: int) -> dict:
    doc = converter.convert(str(pdf_path), page_range=(first, last)).document

    pictures, tables = Counter(), Counter()
    for item in doc.pictures:
        pictures.update(p.page_no for p in item.prov)
    for item in doc.tables:
        tables.update(p.page_no for p in item.prov)

    pages = []
    for page_no in range(first, last + 1):
        markdown = doc.export_to_markdown(page_no=page_no)
        undecoded = markdown.count(FORMULA_PLACEHOLDER)
        text_chars = len(markdown.replace(FORMULA_PLACEHOLDER, "").replace("<!-- image -->", "").strip())
        pages.append({
            "page": page_no,
            "markdown": markdown,
            "formulas_undecoded": undecoded,
            "pictures": pictures[page_no],
            "tables": tables[page_no],
            "hard": undecoded > 0 or text_chars < MIN_TEXT_CHARS,
        })
    return {"first": first, "last": last, "pages": pages}


def run_pdf_stage(pdf_path: Path, first_page: int | None = None, last_page: int | None = None) -> list[dict]:
    """Returns the per-page records for the requested range, converting only batches not already cached."""
    with pymupdf.open(pdf_path) as pdf:
        total_pages = pdf.page_count
    first_page = first_page or 1
    last_page = min(last_page or total_pages, total_pages)

    content_hash = fingerprint(pdf_path)
    with connect() as conn:
        upsert_source(conn, SOURCE_ID, "book", pdf_path.stem, uri=str(pdf_path),
                      content_hash=content_hash, metadata={"pages": total_pages})

    converter = None
    pages: list[dict] = []
    for first in range(first_page, last_page + 1, BATCH_PAGES):
        last = min(first + BATCH_PAGES - 1, last_page)

        def convert(first=first, last=last) -> dict:
            nonlocal converter
            converter = converter or _build_converter()
            start = time.perf_counter()
            batch = _convert_batch(converter, pdf_path, first, last)
            print(f"  pages {first}-{last}: {time.perf_counter() - start:.0f}s")
            return batch

        key = stage_key("pdf", file=content_hash, first=first, last=last, version=PIPELINE_VERSION)
        batch = run_stage(SOURCE_ID, f"pdf_{first:04d}-{last:04d}", key, convert)
        pages.extend(batch["pages"])
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=int, nargs=2, metavar=("FIRST", "LAST"))
    args = parser.parse_args()

    first, last = args.pages or (None, None)
    pages = run_pdf_stage(Path(settings.PDF_PATH), first, last)
    hard = [p["page"] for p in pages if p["hard"]]
    print(json.dumps({
        "pages": len(pages),
        "hard_pages": len(hard),
        "hard_page_numbers": hard,
        "pictures": sum(p["pictures"] for p in pages),
        "tables": sum(p["tables"] for p in pages),
        "formulas_undecoded": sum(p["formulas_undecoded"] for p in pages),
    }))


if __name__ == "__main__":
    main()
