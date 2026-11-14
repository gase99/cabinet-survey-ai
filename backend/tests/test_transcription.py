"""Speech-to-text ingestion: provider-neutral, fail-closed, disclosure-carrying."""
import io
import pytest
from app.core.config import settings
from app.ai import speech


def wav_bytes() -> bytes:
    return b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 16


def test_transcription_text_path_returns_proposals(client, auth_headers):
    response = client.post(
        "/api/v1/ai/transcription",
        headers=auth_headers,
        data={"text": "طول دیوار سه متر و بیست سانتی‌متر"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "طول دیوار سه متر و بیست سانتی‌متر"
    assert body["external_transmission"] is False
    values = [o["value_mm"] for o in body["extraction"]["observations"]]
    assert values == [3200]
    assert all(o["needs_review"] for o in body["extraction"]["observations"])


def test_transcription_requires_audio_or_text(client, auth_headers):
    assert client.post("/api/v1/ai/transcription", headers=auth_headers).status_code == 400


def test_audio_upload_validates_content(client, auth_headers):
    not_audio = client.post(
        "/api/v1/ai/transcription", headers=auth_headers,
        files={"file": ("x.wav", b"definitely not audio", "audio/wav")})
    assert not_audio.status_code == 422
    wrong_type = client.post(
        "/api/v1/ai/transcription", headers=auth_headers,
        files={"file": ("x.exe", wav_bytes(), "application/octet-stream")})
    assert wrong_type.status_code == 415


def test_audio_without_provider_fails_closed_with_clear_error(client, auth_headers):
    assert settings.stt_provider == "disabled"
    response = client.post(
        "/api/v1/ai/transcription", headers=auth_headers,
        files={"file": ("note.wav", wav_bytes(), "audio/wav")})
    assert response.status_code == 503
    assert "text" in response.json()["detail"].lower()


class StubSTT(speech.STTProvider):
    async def transcribe(self, audio, mime, *, language_hint="fa,en"):
        return "طول دیوار سه متر و بیست سانتی‌متر"


def test_audio_with_provider_returns_transcript_and_disclosure(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.api.v1.ai.speech.get_stt_provider", lambda client=None: StubSTT())
    response = client.post(
        "/api/v1/ai/transcription", headers=auth_headers,
        files={"file": ("note.wav", wav_bytes(), "audio/wav")})
    assert response.status_code == 200
    body = response.json()
    assert body["external_transmission"] is True
    assert "external speech recognition" in body["notice"]
    assert [o["value_mm"] for o in body["extraction"]["observations"]] == [3200]


def test_openai_compatible_stt_posts_audio_and_requires_https(monkeypatch):
    import httpx

    settings.stt_provider = "openai_compatible"
    settings.stt_base_url = "https://stt.example.invalid/v1"
    settings.stt_api_key = "test-key"
    settings.stt_model = "test-whisper"
    try:
        provider = speech.OpenAICompatibleSTT()
        with pytest.raises(speech.STTUnavailableError):
            settings.stt_base_url = "http://insecure.example.invalid/v1"
            provider = speech.OpenAICompatibleSTT()
            __import__("asyncio").run(provider.transcribe(b"RIFF....WAVE", "audio/wav"))
        settings.stt_base_url = "https://stt.example.invalid/v1"

        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"text": "دیوار سه متر"})

        transport = httpx.MockTransport(handler)
        import asyncio
        provider = speech.OpenAICompatibleSTT(client=httpx.AsyncClient(transport=transport))
        transcript = asyncio.run(provider.transcribe(wav_bytes(), "audio/wav", language_hint="fa,en"))
        assert transcript == "دیوار سه متر"
        assert seen["url"].endswith("/audio/transcriptions")
        assert seen["auth"] == "Bearer test-key"
    finally:
        settings.stt_provider = "disabled"
        settings.stt_base_url = None
        settings.stt_api_key = None


def test_unknown_stt_provider_fails_closed():
    settings.stt_provider = "unknown_provider"
    try:
        with pytest.raises(speech.STTUnavailableError):
            speech.get_stt_provider()
    finally:
        settings.stt_provider = "disabled"
