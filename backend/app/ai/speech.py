"""Provider-neutral speech-to-text boundary.

The transcription provider is configurable and optional: without credentials the
API fails closed with a clear 503 and the client falls back to typed text. Any
configured external provider processes audio outside this system, and callers
must disclose that to the user before upload. A transcript is never a source of
approved measurements; the deterministic parser only produces proposals.
"""
from typing import Protocol

import httpx

from app.core.config import settings

AUDIO_SUFFIX = {
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
}


class STTUnavailableError(RuntimeError):
    """Raised when speech recognition is disabled, unconfigured or failing."""


class STTProvider(Protocol):
    async def transcribe(self, audio: bytes, mime: str, *, language_hint: str = "fa,en") -> str:
        """Return the raw transcript text for the given audio bytes."""
        ...


class OpenAICompatibleSTT:
    """Audio transcription through an OpenAI-compatible HTTPS endpoint."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client

    async def transcribe(self, audio: bytes, mime: str, *, language_hint: str = "fa,en") -> str:
        base = (settings.stt_base_url or "").rstrip("/")
        api_key = settings.stt_api_key
        model = settings.stt_model or "whisper-1"
        if not base.startswith("https://") or not api_key:
            raise STTUnavailableError("Speech recognition is not fully configured")
        suffix = AUDIO_SUFFIX.get(mime, ".mp3")
        files = {"file": (f"audio{suffix}", audio, mime)}
        form: dict[str, str] = {"model": model}
        language = language_hint.split(",")[0].strip().lower()
        if language in {"fa", "en"}:
            form["language"] = language

        async def send(client: httpx.AsyncClient) -> str:
            response = await client.post(
                f"{base}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
                data=form,
            )
            if not response.is_success:
                raise STTUnavailableError("Speech recognition request failed")
            try:
                text = response.json()["text"]
            except (ValueError, KeyError, TypeError):
                raise STTUnavailableError("Speech recognition returned invalid data")
            if not isinstance(text, str) or not text.strip():
                raise STTUnavailableError("Speech recognition returned an empty transcript")
            return text

        if self.client is not None:
            return await send(self.client)
        async with httpx.AsyncClient(timeout=120) as client:
            return await send(client)


def get_stt_provider(client: httpx.AsyncClient | None = None) -> STTProvider:
    """Resolve the configured speech provider; fail closed when unconfigured."""
    name = settings.stt_provider
    if name == "disabled":
        raise STTUnavailableError(
            "Speech recognition is not configured. Type or paste the spoken measurements as text instead.")
    if name == "openai_compatible":
        if not settings.stt_base_url or not settings.stt_api_key:
            raise STTUnavailableError(
                "Speech recognition is not configured. Type or paste the spoken measurements as text instead.")
        return OpenAICompatibleSTT(client)
    raise STTUnavailableError(
        "Speech recognition is not configured. Type or paste the spoken measurements as text instead.")
