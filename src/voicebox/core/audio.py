"""Audio capture via sounddevice + PipeWire."""

from __future__ import annotations

import logging
import queue
import threading
from typing import TYPE_CHECKING, Callable

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from voicebox.config import AudioConfig

log = logging.getLogger(__name__)


class AudioRecorder:
    """Callback-based audio recorder at 16 kHz mono float32.

    Audio chunks are buffered in a queue and forwarded to on_chunk
    via a separate thread so the sounddevice C callback stays fast.
    """

    def __init__(self, config: AudioConfig) -> None:
        self._device = config.device or None
        self._sample_rate = config.sample_rate
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._forwarder: threading.Thread | None = None

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def start(self, on_chunk: Callable[[np.ndarray], None] | None = None) -> None:
        """Start recording. Optional callback receives each chunk (float32, 16kHz mono)."""
        self._chunks.clear()
        # Drain any leftover items
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        # Start forwarder thread that reads from queue and calls on_chunk
        if on_chunk is not None:
            self._forwarder = threading.Thread(
                target=self._forward_loop, args=(on_chunk,), daemon=True,
            )
            self._forwarder.start()

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
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        # Signal forwarder to stop
        self._queue.put(None)
        if self._forwarder is not None:
            self._forwarder.join(timeout=2)
            self._forwarder = None

        log.info("Recording stopped (%d chunks captured)", len(self._chunks))

    def get_audio(self) -> np.ndarray:
        """Return captured audio as a flat float32 array. Call after stop()."""
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            return np.concatenate(self._chunks).flatten()

    def _audio_callback(self, indata: np.ndarray, _frames: int, _time_info: object, status: sd.CallbackFlags) -> None:
        """Called from the sounddevice C thread — must be fast, no locks, no exceptions."""
        if status:
            log.warning("Audio callback status: %s", status)
        chunk = indata[:, 0].copy()
        with self._lock:
            self._chunks.append(chunk)
        self._queue.put_nowait(chunk)

    def _forward_loop(self, on_chunk: Callable[[np.ndarray], None]) -> None:
        """Runs in a separate thread, forwarding audio chunks to on_chunk (e.g. VAD)."""
        while True:
            chunk = self._queue.get()
            if chunk is None:
                break
            try:
                on_chunk(chunk)
            except Exception:
                log.exception("on_chunk callback error")
