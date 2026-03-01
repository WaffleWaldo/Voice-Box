"""Speech-to-text via faster-whisper (CUDA)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from faster_whisper import WhisperModel

if TYPE_CHECKING:
    from voicebox.config import STTConfig

log = logging.getLogger(__name__)


class Transcriber:
    """Loads a Whisper model once and transcribes audio arrays."""

    def __init__(self, config: STTConfig) -> None:
        self._language = config.language
        log.info(
            "Loading Whisper model %s on %s (%s)...",
            config.model, config.device, config.compute_type,
        )
        self._model = WhisperModel(
            config.model,
            device=config.device,
            compute_type=config.compute_type,
        )
        log.info("Whisper model loaded")

    def transcribe(self, audio: np.ndarray, initial_prompt: str = "") -> str:
        """Transcribe a float32 16 kHz mono audio array to text."""
        if audio.size == 0:
            return ""

        segments, info = self._model.transcribe(
            audio,
            language=self._language,
            initial_prompt=initial_prompt or None,
            vad_filter=True,
        )
        text = " ".join(seg.text.strip() for seg in segments)
        log.info("Transcribed (lang=%s, prob=%.2f): %s", info.language, info.language_probability, text)
        return text
