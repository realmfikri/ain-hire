"""Speech-to-text and text-to-speech provider interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ioh_hire.config import Settings


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    confidence: float | None = None
    raw: object | None = None


@dataclass(frozen=True)
class SynthesizedAudio:
    audio_bytes: bytes
    mime_type: str = "audio/mpeg"


class VoiceProvider(Protocol):
    def transcribe(self, audio_bytes: bytes, mime_type: str | None = None) -> TranscriptionResult:
        ...

    def synthesize(self, text: str, persona: bool = False) -> SynthesizedAudio:
        ...


class StubVoiceProvider:
    """Local demo provider.

    For seed tests, `audio_bytes` may contain UTF-8 text. In Streamlit local mode
    the UI also offers a text fallback because real browser audio needs Cloud STT.
    """

    def transcribe(self, audio_bytes: bytes, mime_type: str | None = None) -> TranscriptionResult:
        try:
            text = audio_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            text = ""
        return TranscriptionResult(text=text, confidence=1.0 if text else 0.0)

    def synthesize(self, text: str, persona: bool = False) -> SynthesizedAudio:
        return SynthesizedAudio(audio_bytes=b"", mime_type="audio/mpeg")


class GoogleCloudVoiceProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

        from google.cloud import speech_v2, texttospeech

        self._speech_v2 = speech_v2
        self._stt_client = speech_v2.SpeechClient()
        self._tts = texttospeech
        self._tts_client = texttospeech.TextToSpeechClient()

    def transcribe(self, audio_bytes: bytes, mime_type: str | None = None) -> TranscriptionResult:
        if not audio_bytes:
            return TranscriptionResult(text="", confidence=0.0)

        recognizer = (
            f"projects/{self.settings.project_id}/locations/{self.settings.stt_location}"
            f"/recognizers/{self.settings.stt_recognizer}"
        )
        config = self._speech_v2.RecognitionConfig(
            auto_decoding_config=self._speech_v2.AutoDetectDecodingConfig(),
            language_codes=[self.settings.stt_language],
            model=self.settings.stt_model,
        )
        request = self._speech_v2.RecognizeRequest(
            recognizer=recognizer,
            config=config,
            content=audio_bytes,
        )
        response = self._stt_client.recognize(request=request)
        transcripts: list[str] = []
        confidences: list[float] = []
        for result in response.results:
            if not result.alternatives:
                continue
            alt = result.alternatives[0]
            transcripts.append(alt.transcript)
            if alt.confidence:
                confidences.append(float(alt.confidence))
        text = " ".join(part.strip() for part in transcripts if part.strip())
        confidence = sum(confidences) / len(confidences) if confidences else None
        return TranscriptionResult(text=text, confidence=confidence, raw=response)

    def synthesize(self, text: str, persona: bool = False) -> SynthesizedAudio:
        voice_name = (
            self.settings.tts_voice_persona if persona else self.settings.tts_voice_interviewer
        )
        synthesis_input = self._tts.SynthesisInput(text=text)
        voice = self._tts.VoiceSelectionParams(
            language_code=self.settings.tts_language,
            name=voice_name,
        )
        audio_config = self._tts.AudioConfig(
            audio_encoding=self._tts.AudioEncoding.MP3
        )
        response = self._tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )
        return SynthesizedAudio(audio_bytes=response.audio_content, mime_type="audio/mpeg")


def build_voice_provider(settings: Settings) -> VoiceProvider:
    if settings.use_stubs:
        return StubVoiceProvider()
    return GoogleCloudVoiceProvider(settings)
