"""Audio capture via sounddevice + PipeWire."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Callable

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from voicebox.config import AudioConfig

log = logging.getLogger(__name__)


class AudioRecorder:
    """Callback-based audio recorder at 16 kHz mono float32."""

    def __init__(self, config: AudioConfig) -> None:
        self._device = config.device or None
        self._sample_rate = config.sample_rate
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._on_chunk: Callable[[np.ndarray], None] | None = None

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def start(self, on_chunk: Callable[[np.ndarray], None] | None = None) -> None:
        """Start recording. Optional callback receives each chunk (float32, 16kHz mono)."""
        with self._lock:
            self._chunks.clear()
            self._on_chunk = on_chunk
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                blocksize=int(self._sample_rate * 0.03),  # 30ms chunks
                device=self._device,
                callback=self._audio_callback,
            )
            self._stream.start()
            log.info("Recording started (device=%s, rate=%d)", self._device, self._sample_rate)

    def stop(self) -> None:
        """Stop recording."""
        with self._lock:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
                log.info("Recording stopped (%d chunks captured)", len(self._chunks))

    def get_audio(self) -> np.ndarray:
        """Return captured audio as a flat float32 array. Call after stop()."""
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            return np.concatenate(self._chunks).flatten()

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: object, status: sd.CallbackFlags) -> None:
        if status:
            log.warning("Audio callback status: %s", status)
        chunk = indata[:, 0].copy()
        with self._lock:
            self._chunks.append(chunk)
        if self._on_chunk is not None:
            self._on_chunk(chunk)
