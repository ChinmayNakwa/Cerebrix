# backend/utils/voice_service.py

import io
import struct
from functools import lru_cache
from typing import Iterator

import numpy as np

from ..config import settings

KOKORO_SAMPLE_RATE = 24000


@lru_cache(maxsize=1)
def _whisper():
    # Loaded on first use; small.en takes ~2.5 s for a 6 s clip on this CPU
    from faster_whisper import WhisperModel
    print(f"VoiceService: Loading Whisper model {settings.WHISPER_MODEL}...")
    return WhisperModel(settings.WHISPER_MODEL, device="cpu", compute_type="int8")


@lru_cache(maxsize=1)
def _kokoro():
    from kokoro import KPipeline
    print("VoiceService: Loading Kokoro TTS pipeline...")
    return KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")


def transcribe_audio(audio_data: bytes) -> str:
    """
    Transcribes recorded audio (any format ffmpeg can decode, e.g. webm/opus) with local Whisper.
    Raises on failure so the caller can return a real HTTP error.
    """
    segments, _ = _whisper().transcribe(io.BytesIO(audio_data), beam_size=1, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


def load_tts():
    """Loads the TTS pipeline up front, so load errors surface before the response starts."""
    _kokoro()


def _wav_header() -> bytes:
    # 16-bit mono PCM with unknown length (0xFFFFFFFF sizes), so the audio can be streamed
    return (b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, KOKORO_SAMPLE_RATE, KOKORO_SAMPLE_RATE * 2, 2, 16)
            + b"data" + struct.pack("<I", 0xFFFFFFFF))


def text_to_speech(text: str) -> Iterator[bytes]:
    """
    Synthesises speech with local Kokoro and streams WAV audio, one sentence-sized segment at a time.
    """
    yield _wav_header()
    for result in _kokoro()(text, voice=settings.KOKORO_VOICE):
        audio = result.audio.numpy()
        yield (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
