"""Pipeline orchestration: record → transcribe → refine → inject."""

from __future__ import annotations

import enum
import logging
import threading
from typing import TYPE_CHECKING

from voicebox.core.audio import AudioRecorder
from voicebox.core.refiner import Refiner
from voicebox.core.transcriber import Transcriber
from voicebox.data.dictionary import Dictionary
from voicebox.services.injector import Injector
from voicebox.services.niri import get_focused_window
from voicebox.services.notifier import notify

if TYPE_CHECKING:
    from voicebox.config import Config

log = logging.getLogger(__name__)


class State(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


class Pipeline:
    """Owns all components and orchestrates the voice-to-text flow."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._state = State.IDLE
        self._lock = threading.Lock()

        # Core
        self._recorder = AudioRecorder(config.audio)
        self._transcriber = Transcriber(config.stt)
        self._refiner = Refiner(config.refiner)

        # Data
        self._dictionary = Dictionary(config.dictionary.path)

        # Services
        self._injector = Injector()
        self._notify = config.notifications.enabled

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
        self._recorder.start()
        if self._notify:
            notify("Recording...", "Speak now")
        return "recording"

    def _stop_recording(self) -> str:
        """Stop recording and kick off processing in a background thread."""
        self._recorder.stop()
        self._state = State.PROCESSING
        thread = threading.Thread(target=self._process, daemon=True)
        thread.start()
        return "processing"

    def _process(self) -> None:
        """Run the transcribe → refine → inject pipeline."""
        try:
            if self._notify:
                notify("Processing...", "Transcribing audio")

            audio = self._recorder.get_audio()
            if audio.size == 0:
                log.warning("No audio captured")
                if self._notify:
                    notify("No audio", "Nothing was recorded", urgency="low")
                return

            duration = audio.size / self._recorder.sample_rate
            log.info("Processing %.1fs of audio", duration)

            # Transcribe
            whisper_prompt = self._dictionary.as_whisper_prompt()
            transcript = self._transcriber.transcribe(audio, initial_prompt=whisper_prompt)

            if not transcript.strip():
                log.warning("Empty transcription")
                if self._notify:
                    notify("No speech detected", urgency="low")
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
            if self._notify:
                if success:
                    notify("Done", text[:100])
                else:
                    notify("Injection failed", "Could not type text", urgency="critical")

        except Exception:
            log.exception("Pipeline error")
            if self._notify:
                notify("Error", "Pipeline failed — check logs", urgency="critical")
        finally:
            with self._lock:
                self._state = State.IDLE

    def shutdown(self) -> None:
        """Clean shutdown."""
        if self._state == State.RECORDING:
            self._recorder.stop()
        log.info("Pipeline shut down")
