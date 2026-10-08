# backend/ingestion/vision.py
"""
Ollama Cloud vision calls shared by the ingestion stages. Image requests sometimes stall after a
burst while the service stays up, so each call has a short timeout and is retried.
"""

import base64
import time

import httpx
import ollama

from backend.config import settings

TIMEOUT_SEC = 120
RETRIES = 2
RETRY_PAUSE_SEC = 10


def vision_client() -> ollama.Client:
    if not settings.OLLAMA_API_KEY:
        raise RuntimeError("OLLAMA_API_KEY is not set")
    return ollama.Client(host=settings.OLLAMA_HOST,
                         headers={"Authorization": f"Bearer {settings.OLLAMA_API_KEY}"},
                         timeout=TIMEOUT_SEC)


def _retryable(error: Exception) -> bool:
    if isinstance(error, ollama.ResponseError):
        return error.status_code == 429 or error.status_code >= 500
    return isinstance(error, (httpx.TransportError, ConnectionError))


def read_image(client: ollama.Client, image: bytes, prompt: str) -> str:
    """Sends one image with a prompt to the vision model and returns its answer."""
    for attempt in range(RETRIES + 1):
        try:
            response = client.chat(
                model=settings.OLLAMA_VISION_MODEL,
                messages=[{"role": "user", "content": prompt, "images": [base64.b64encode(image).decode()]}],
                options={"temperature": 0},
            )
            return response.message.content.strip()
        except Exception as e:
            if attempt == RETRIES or not _retryable(e):
                raise
            time.sleep(RETRY_PAUSE_SEC * (attempt + 1))
