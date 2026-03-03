"""AI text refinement via Ollama HTTP API."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from echoflow.config import RefinerConfig

log = logging.getLogger(__name__)


class Refiner:
    """Refines raw transcripts using a local LLM via Ollama."""

    def __init__(self, config: RefinerConfig) -> None:
        self._enabled = config.enabled
        self._url = config.ollama_url.rstrip("/")
        self._model = config.model
        self._temperature = config.temperature

    def check_connection(self) -> bool:
        """Check if Ollama is reachable. Logs a warning if not."""
        if not self._enabled:
            return True
        try:
            resp = httpx.get(f"{self._url}/api/tags", timeout=5)
            resp.raise_for_status()
            log.info("Ollama connected (%s)", self._url)
            return True
        except httpx.HTTPError as e:
            log.warning("Ollama unreachable at %s: %s", self._url, e)
            return False

    def refine(
        self,
        transcript: str,
        app_id: str = "",
        window_title: str = "",
        dictionary_context: str = "",
    ) -> str:
        """Refine a transcript. Returns raw transcript on failure."""
        if not self._enabled or not transcript.strip():
            return transcript

        nonce = secrets.token_hex(4)
        user_msg = (
            f"App: {app_id or 'unknown'} | Window: {window_title or 'unknown'}\n\n"
            f"---TRANSCRIPT-{nonce}---\n"
            f"{transcript}\n"
            f"---END-{nonce}---"
        )

        messages: list[dict[str, str]] = [{"role": "user", "content": user_msg}]
        if dictionary_context:
            messages.insert(0, {"role": "system", "content": dictionary_context})

        try:
            resp = httpx.post(
                f"{self._url}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": self._temperature},
                },
                timeout=30,
            )
            resp.raise_for_status()
            refined = resp.json()["message"]["content"].strip()
            refined = self._validate_output(refined, transcript)
            log.info("Refined: %r → %r", transcript, refined)
            return refined
        except (httpx.HTTPError, KeyError) as e:
            log.warning("Refinement failed, using raw transcript: %s", e)
            return transcript

    def _validate_output(self, output: str, original: str) -> str:
        """Validate refiner output. Falls back to original on failure."""
        if len(original) > 0 and len(output) > 2 * len(original):
            log.warning(
                "Refiner output too long (%d chars vs %d input), using raw transcript",
                len(output), len(original),
            )
            return original
        if output.startswith("App:") or output.startswith("---TRANSCRIPT"):
            log.warning("Refiner echoed context metadata, using raw transcript")
            return original
        return output
