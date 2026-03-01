"""Personal dictionary loading and formatting."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


class Dictionary:
    """Loads a personal dictionary for Whisper biasing and LLM context."""

    def __init__(self, path: str) -> None:
        self._words: list[str] = []
        expanded = Path(path).expanduser()
        if expanded.exists():
            self._words = [
                line.strip()
                for line in expanded.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            log.info("Loaded %d dictionary entries from %s", len(self._words), expanded)
        else:
            log.debug("Dictionary file not found: %s", expanded)

    @property
    def words(self) -> list[str]:
        return self._words

    def as_whisper_prompt(self) -> str:
        """Format as an initial prompt to bias Whisper transcription."""
        if not self._words:
            return ""
        return ", ".join(self._words)

    def as_llm_context(self) -> str:
        """Format as a bullet list for the LLM refiner system prompt."""
        if not self._words:
            return ""
        lines = ["Domain-specific terms (use exact spelling):"]
        lines.extend(f"- {w}" for w in self._words)
        return "\n".join(lines)
