"""Voice activity detection via silero-vad."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable

import numpy as np
import torch
from silero_vad import load_silero_vad

if TYPE_CHECKING:
    from voicebox.config import VADConfig

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
# silero-vad v6 requires sr / num_samples <= 31.25, so minimum 512 samples at 16kHz
MIN_CHUNK_SAMPLES = 512


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
        self._buffer = np.array([], dtype=np.float32)
        log.info("VAD initialized (silence=%.1fs, min_speech=%.1fs)",
                 self._silence_threshold, self._min_speech)

    def reset(self) -> None:
        """Reset state for a new recording session."""
        self._model.reset_states()
        self._speech_detected = False
        self._speech_start = None
        self._last_speech_time = 0.0
        self._fired = False
        self._buffer = np.array([], dtype=np.float32)

    def process_chunk(self, chunk: np.ndarray) -> None:
        """Process an audio chunk. Buffers until >= 512 samples then runs VAD."""
        if self._fired:
            return

        self._buffer = np.concatenate([self._buffer, chunk])

        # Process in 512-sample windows
        while len(self._buffer) >= MIN_CHUNK_SAMPLES and not self._fired:
            window = self._buffer[:MIN_CHUNK_SAMPLES]
            self._buffer = self._buffer[MIN_CHUNK_SAMPLES:]
            # silero-vad v6 expects shape (batch, samples)
            tensor = torch.from_numpy(window).float().unsqueeze(0)
            confidence = self._model(tensor, SAMPLE_RATE).item()
            self._update_state(confidence)

    def _update_state(self, confidence: float) -> None:
        """Update speech/silence state from a VAD confidence score."""
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
