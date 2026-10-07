# backend/ingestion/runner.py
"""
Resumable stage runner. Each stage result is cached on disk under a key derived from its inputs,
and recorded in ingest_manifest, so a re-run only redoes work whose inputs changed.
"""

import hashlib
import json
import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable

import psycopg
from psycopg.types.json import Jsonb

from backend.config import settings

CACHE_DIR = Path(settings.INGEST_CACHE_DIR)
_SAMPLE_BYTES = 4 * 1024 * 1024


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.POSTGRES_DB_URL, autocommit=True, connect_timeout=10)


def fingerprint(path: Path) -> str:
    """
    Cheap content fingerprint: size plus the first and last 4 MB.
    Hashing 18 GB of lecture video in full on every run would defeat the point of resuming.
    """
    size = path.stat().st_size
    digest = hashlib.sha256(str(size).encode())
    with path.open("rb") as f:
        digest.update(f.read(_SAMPLE_BYTES))
        if size > 2 * _SAMPLE_BYTES:
            f.seek(-_SAMPLE_BYTES, os.SEEK_END)
            digest.update(f.read(_SAMPLE_BYTES))
    return digest.hexdigest()[:32]


def stage_key(stage: str, **inputs: Any) -> str:
    """Hash of everything that determines a stage's output: input fingerprints and parameters."""
    payload = json.dumps({"stage": stage, **inputs}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def cache_path(stage: str, key: str) -> Path:
    return CACHE_DIR / stage / f"{key}.json"


def upsert_source(conn: psycopg.Connection, source_id: str, kind: str, title: str,
                  uri: str | None = None, content_hash: str | None = None,
                  metadata: dict | None = None) -> None:
    conn.execute(
        """
        INSERT INTO sources (id, kind, title, uri, content_hash, metadata)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title, uri = EXCLUDED.uri,
            content_hash = EXCLUDED.content_hash, metadata = EXCLUDED.metadata
        """,
        (source_id, kind, title, uri, content_hash, Jsonb(metadata or {})),
    )


def run_stage(source_id: str, stage: str, key: str, fn: Callable[[], dict], force: bool = False) -> dict:
    """
    Runs fn() unless this (source, stage) already finished with the same key, in which case the
    cached result is returned. fn must return a JSON-serialisable dict.
    """
    path = cache_path(stage, key)

    with connect() as conn:
        row = conn.execute(
            "SELECT input_hash, status FROM ingest_manifest WHERE source_id = %s AND stage = %s",
            (source_id, stage),
        ).fetchone()
        if not force and row == (key, "done") and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

        conn.execute(
            """
            INSERT INTO ingest_manifest (source_id, stage, input_hash, status)
            VALUES (%s, %s, %s, 'running')
            ON CONFLICT (source_id, stage) DO UPDATE SET
                input_hash = EXCLUDED.input_hash, status = 'running', error = NULL,
                detail = '{}', started_at = now(), finished_at = NULL
            """,
            (source_id, stage, key),
        )

        try:
            result = fn()
        except Exception:
            conn.execute(
                "UPDATE ingest_manifest SET status = 'failed', error = %s, finished_at = now() "
                "WHERE source_id = %s AND stage = %s",
                (traceback.format_exc(limit=5), source_id, stage),
            )
            raise

        # Write to a temp file first so a crash never leaves a half-written cache entry.
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

        conn.execute(
            "UPDATE ingest_manifest SET status = 'done', detail = %s, finished_at = now() "
            "WHERE source_id = %s AND stage = %s",
            (Jsonb({"cache": str(path)}), source_id, stage),
        )
    return result


def run_many(items: Iterable[Any], worker: Callable[[Any], Any], max_workers: int = 4) -> tuple[list, list]:
    """
    Applies worker to every item with at most max_workers running at once.
    One failing item does not stop the rest. Returns (results, failures).
    """
    results, failures = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(worker, item): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                results.append((item, future.result()))
            except Exception as e:
                print(f"  - Failed: {item}: {e}")
                failures.append((item, e))
    return results, failures
