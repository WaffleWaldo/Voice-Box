"""Voice activity detection via silero-vad."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable

import numpy as np
import torch
from silero_vad import load_silero_vad, get_speech_timestamps

if TYPE_CHECKING:
    from voicebox.config import VADConfig

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 480  # 30ms at 16kHz


class VAD:
    """Real-time voice activity detector that fires a callback on silence after speech."""

    def __init__(self, config: VADConfig, on_silence: Callable[[], None]) -> None:
        self._silence_threshold = config.silence_threshold_sec
        self._min_speech = config.min_speech_sec
        self._on_silence = on_silence

        self._model = load_silero_vad()
        self._speech_detected = False
        self._speech_start: float | None = None
        self._last_speech_time: float = 0.0
        self._fired = False
        log.info("VAD initialized (silence=%.1fs, min_speech=%.1fs)",
                 self._silence_threshold, self._min_speech)

    def reset(self) -> None:
        """Reset state for a new recording session."""
        self._model.reset_states()
        self._speech_detected = False
        self._speech_start = None
        self._last_speech_time = 0.0
        self._fired = False

    def process_chunk(self, chunk: np.ndarray) -> None:
        """Process a 30ms audio chunk. Fires on_silence when appropriate."""
        if self._fired:
            return

        tensor = torch.from_numpy(chunk).float()
        # silero-vad expects exactly 480 samples at 16kHz for 30ms
        if tensor.shape[0] != CHUNK_SAMPLES:
            return

        confidence = self._model(tensor, SAMPLE_RATE).item()
        now = time.monotonic()

        if confidence > 0.5:
            if not self._speech_detected:
                self._speech_detected = True
                self._speech_start = now
                log.debug("Speech started")
            self._last_speech_time = now
        elif self._speech_detected:
            silence_duration = now - self._last_speech_time
            speech_duration = (self._last_speech_time - self._speech_start
                               if self._speech_start else 0.0)

            if (silence_duration >= self._silence_threshold
                    and speech_duration >= self._min_speech):
                log.info("Silence detected after %.1fs of speech", speech_duration)
                self._fired = True
                self._on_silence()
