"""Pipeline orchestration: record → transcribe → refine → inject."""

from __future__ import annotations

import enum
import logging
import math
import threading
from typing import TYPE_CHECKING

import numpy as np

from voicebox.core.audio import AudioRecorder
from voicebox.core.refiner import Refiner
from voicebox.core.transcriber import Transcriber
from voicebox.data.dictionary import Dictionary
from voicebox.services.injector import Injector
from voicebox.services.niri import get_focused_window

if TYPE_CHECKING:
    from voicebox.config import Config
    from voicebox.services.overlay import Overlay

log = logging.getLogger(__name__)

# RMS → normalized level mapping
_DB_FLOOR = -60.0
_DB_CEIL = 0.0


class State(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


class Pipeline:
    """Owns all components and orchestrates the voice-to-text flow."""

    def __init__(self, config: Config, overlay: Overlay | None = None) -> None:
        self._config = config
        self._state = State.IDLE
        self._lock = threading.Lock()
        self._overlay = overlay

        # Core
        self._recorder = AudioRecorder(config.audio)
        self._transcriber = Transcriber(config.stt)
        self._refiner = Refiner(config.refiner)

        # Data
        self._dictionary = Dictionary(config.dictionary.path)

        # Services
        self._injector = Injector()

        # Check Ollama connectivity at startup
        self._refiner.check_connection()

    @property
    def state(self) -> State:
        return self._state

    def toggle(self) -> str:
        """Toggle between idle and recording. Returns new state description."""
        with self._lock:
            if self._state == State.IDLE:
                return self._start_recording()
            elif self._state == State.RECORDING:
                return self._stop_recording()
            else:
                return f"busy ({self._state.value})"

    def _start_recording(self) -> str:
        self._state = State.RECORDING
        if self._overlay:
            self._overlay.show_recording()
        self._recorder.start(on_chunk=self._on_audio_chunk)
        return "recording"

    def _on_audio_chunk(self, chunk: np.ndarray) -> None:
        """Compute RMS of audio chunk and forward to overlay as 0.0–1.0 level."""
        if self._overlay is None:
            return
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        if rms > 0:
            db = 20.0 * math.log10(rms)
        else:
            db = _DB_FLOOR
        level = (db - _DB_FLOOR) / (_DB_CEIL - _DB_FLOOR)
        level = max(0.0, min(1.0, level))
        self._overlay.update_audio_level(level)

    def _stop_recording(self) -> str:
        """Stop recording and kick off processing in a background thread."""
        self._recorder.stop()
        self._state = State.PROCESSING
        if self._overlay:
            self._overlay.show_processing()
        thread = threading.Thread(target=self._process, daemon=True)
        thread.start()
        return "processing"

    def _process(self) -> None:
        """Run the transcribe → refine → inject pipeline."""
        try:
            audio = self._recorder.get_audio()
            if audio.size == 0:
                log.warning("No audio captured")
                if self._overlay:
                    self._overlay.show_error()
                return

            duration = audio.size / self._recorder.sample_rate
            log.info("Processing %.1fs of audio", duration)

            # Transcribe
            whisper_prompt = self._dictionary.as_whisper_prompt()
            transcript = self._transcriber.transcribe(audio, initial_prompt=whisper_prompt)

            if not transcript.strip():
                log.warning("Empty transcription")
                if self._overlay:
                    self._overlay.show_error()
                return

            # Get window context for refinement
            window = get_focused_window()

            # Refine
            dict_context = self._dictionary.as_llm_context()
            text = self._refiner.refine(
                transcript,
                app_id=window["app_id"],
                window_title=window["title"],
                dictionary_context=dict_context,
            )

            # Inject
            success = self._injector.inject(text, app_id=window["app_id"])
            if self._overlay:
                if success:
                    self._overlay.show_done()
                else:
                    self._overlay.show_error()

        except Exception:
            log.exception("Pipeline error")
            if self._overlay:
                self._overlay.show_error()
        finally:
            with self._lock:
                self._state = State.IDLE

    def shutdown(self) -> None:
        """Clean shutdown."""
        if self._state == State.RECORDING:
            self._recorder.stop()
        log.info("Pipeline shut down")
