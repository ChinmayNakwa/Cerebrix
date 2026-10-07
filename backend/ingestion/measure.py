# backend/ingestion/measure.py
"""
Times each ingestion stage on a small sample so the pipeline is designed around measured costs.

    python -m backend.ingestion.measure pdf --pages 1 20
    python -m backend.ingestion.measure video "temp_videos/Lecture 18.mp4" --mode keyframes
    python -m backend.ingestion.measure embed BAAI/bge-m3
"""

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

import psutil

from backend.config import settings


def _rss_gb() -> float:
    return round(psutil.Process().memory_info().rss / 1024**3, 2)


def measure_pdf(first_page: int, last_page: int, formulas: bool, threads: int) -> dict:
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_formula_enrichment = formulas
    options.accelerator_options = AcceleratorOptions(num_threads=threads, device="cpu")

    start = time.perf_counter()
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    converter.initialize_pipeline(InputFormat.PDF)
    load_sec = time.perf_counter() - start

    start = time.perf_counter()
    result = converter.convert(settings.PDF_PATH, page_range=(first_page, last_page))
    convert_sec = time.perf_counter() - start

    doc = result.document
    pages = last_page - first_page + 1
    markdown = doc.export_to_markdown()
    return {
        "stage": "pdf",
        "pages": pages,
        "formulas": formulas,
        "threads": threads,
        "model_load_sec": round(load_sec, 1),
        "convert_sec": round(convert_sec, 1),
        "sec_per_page": round(convert_sec / pages, 2),
        "tables": len(doc.tables),
        "pictures": len(doc.pictures),
        "markdown_chars": len(markdown),
        "rss_gb": _rss_gb(),
    }


def measure_video(video_path: Path, mode: str, every_sec: float, hash_distance: int) -> dict:
    import imagehash
    from PIL import Image

    # keyframes: decode only I-frames. interval: decode everything, keep one frame every N seconds.
    # -discard nokey drops packets in the demuxer, so it works for VP9 too (-skip_frame nokey does not).
    if mode == "keyframes":
        decode_args = ["-discard", "nokey", "-i", str(video_path), "-vf", "scale=640:-2", "-fps_mode", "vfr"]
    else:
        decode_args = ["-i", str(video_path), "-vf", f"fps=1/{every_sec},scale=640:-2"]

    with tempfile.TemporaryDirectory() as tmp:
        start = time.perf_counter()
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *decode_args,
             "-q:v", "4", str(Path(tmp) / "f_%05d.jpg")],
            check=True,
        )
        extract_sec = time.perf_counter() - start

        frames = sorted(Path(tmp).glob("f_*.jpg"))

        # Keep a frame only when it differs from the last kept one: that is a slide change.
        start = time.perf_counter()
        kept, last_hash = 0, None
        for frame in frames:
            with Image.open(frame) as image:
                current = imagehash.phash(image)
            if last_hash is None or current - last_hash > hash_distance:
                kept += 1
                last_hash = current
        dedup_sec = time.perf_counter() - start

    return {
        "stage": "video",
        "video": video_path.name,
        "mode": mode,
        "extract_sec": round(extract_sec, 1),
        "dedup_sec": round(dedup_sec, 1),
        "frames_extracted": len(frames),
        "frames_kept": kept,
    }


def measure_embed(model_name: str, n_chunks: int, batch_size: int) -> dict:
    import pymupdf
    from sentence_transformers import SentenceTransformer

    # Real book text, cut into chunk-sized pieces, so token counts are representative.
    with pymupdf.open(settings.PDF_PATH) as pdf:
        text = " ".join(pdf[i].get_text() for i in range(20, 80))
    chunks = [text[i:i + 1200] for i in range(0, len(text), 1200)][:n_chunks]

    start = time.perf_counter()
    model = SentenceTransformer(model_name, device="cpu")
    load_sec = time.perf_counter() - start

    model.encode(chunks[:batch_size], batch_size=batch_size)  # warm-up

    start = time.perf_counter()
    vectors = model.encode(chunks, batch_size=batch_size, normalize_embeddings=True)
    encode_sec = time.perf_counter() - start

    return {
        "stage": "embed",
        "model": model_name,
        "dimension": int(vectors.shape[1]),
        "chunks": len(chunks),
        "batch_size": batch_size,
        "model_load_sec": round(load_sec, 1),
        "encode_sec": round(encode_sec, 1),
        "chunks_per_sec": round(len(chunks) / encode_sec, 2),
        "rss_gb": _rss_gb(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    stages = parser.add_subparsers(dest="stage", required=True)

    pdf = stages.add_parser("pdf")
    pdf.add_argument("--pages", type=int, nargs=2, default=(1, 20), metavar=("FIRST", "LAST"))
    pdf.add_argument("--formulas", action="store_true")
    pdf.add_argument("--threads", type=int, default=8)

    video = stages.add_parser("video")
    video.add_argument("path", type=Path)
    video.add_argument("--mode", choices=("keyframes", "interval"), default="keyframes")
    video.add_argument("--every-sec", type=float, default=2.0)
    video.add_argument("--hash-distance", type=int, default=8)

    embed = stages.add_parser("embed")
    embed.add_argument("model")
    embed.add_argument("--chunks", type=int, default=64)
    embed.add_argument("--batch-size", type=int, default=8)

    args = parser.parse_args()
    if args.stage == "pdf":
        report = measure_pdf(args.pages[0], args.pages[1], args.formulas, args.threads)
    elif args.stage == "video":
        report = measure_video(args.path, args.mode, args.every_sec, args.hash_distance)
    else:
        report = measure_embed(args.model, args.chunks, args.batch_size)

    print(json.dumps(report))


if __name__ == "__main__":
    main()
