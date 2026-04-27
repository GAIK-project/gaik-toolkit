from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import requests

from gaik.software_components.config import create_openai_client, get_openai_config
from gaik.software_components.llm.factory import assert_openai_or_azure

SUPPORTED_LANGUAGES = {
    "fi": "Finnish",
    "en": "English",
}
SUPPORTED_RESPONSE_FORMATS = {
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "application/octet-stream",
}
DEFAULT_LANGUAGE = "fi"
DEFAULT_MODEL = "tts-hd"
DEFAULT_VOICE = "marin"
DEFAULT_RESPONSE_FORMAT = "mp3"


@dataclass
class SpeechSynthesisResult:
    audio_bytes: bytes
    job_id: str
    model: str
    voice: str
    language: str
    response_format: str = DEFAULT_RESPONSE_FORMAT
    content_type: str = SUPPORTED_RESPONSE_FORMATS[DEFAULT_RESPONSE_FORMAT]

    @property
    def filename(self) -> str:
        return f"{self.job_id}.{self.response_format}"

    def save(self, destination: str | Path) -> Path:
        target = Path(destination)
        if target.suffix:
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            target.mkdir(parents=True, exist_ok=True)
            target = target / self.filename
        target.write_bytes(self.audio_bytes)
        return target


class TextToSpeech:
    """Generate speech audio from text using OpenAI or Azure OpenAI."""

    def __init__(
        self,
        api_config: dict | None = None,
        *,
        use_azure: bool = True,
        model: str | None = None,
        language: Literal["fi", "en"] = DEFAULT_LANGUAGE,
        voice: str = DEFAULT_VOICE,
        response_format: Literal[
            "mp3", "opus", "aac", "flac", "wav", "pcm"
        ] = DEFAULT_RESPONSE_FORMAT,
        speed: float = 1.0,
        default_instructions: str | None = None,
    ) -> None:
        self.api_config = api_config or get_openai_config(use_azure=use_azure)
        assert_openai_or_azure(self.api_config, component="TextToSpeech")
        self.client = create_openai_client(self.api_config)
        self.model = model or self._resolve_default_model()
        if language not in SUPPORTED_LANGUAGES:
            supported = ", ".join(SUPPORTED_LANGUAGES)
            raise ValueError(f"Unsupported language '{language}'. Supported languages: {supported}")
        self.language = language
        self.voice = voice
        self.response_format = response_format
        self.speed = speed
        self.default_instructions = default_instructions

    def synthesize(
        self,
        text: str,
        *,
        language: Literal["fi", "en"] = DEFAULT_LANGUAGE,
        voice: str | None = None,
        instructions: str | None = None,
        speed: float | None = None,
        response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] | None = None,
    ) -> SpeechSynthesisResult:
        text = text.strip()
        if not text:
            raise ValueError("Text input cannot be empty.")
        resolved_language = language or self.language
        if resolved_language not in SUPPORTED_LANGUAGES:
            supported = ", ".join(SUPPORTED_LANGUAGES)
            raise ValueError(
                f"Unsupported language '{resolved_language}'. Supported languages: {supported}"
            )

        resolved_voice = voice or self.voice
        resolved_speed = self.speed if speed is None else speed
        resolved_format = response_format or self.response_format
        if resolved_format not in SUPPORTED_RESPONSE_FORMATS:
            supported = ", ".join(SUPPORTED_RESPONSE_FORMATS)
            raise ValueError(
                f"Unsupported response format '{resolved_format}'. Supported formats: {supported}"
            )

        resolved_instructions = self._build_instructions(
            language=resolved_language, instructions=instructions
        )

        if self.api_config.get("use_azure", False):
            audio_bytes = self._synthesize_with_azure_endpoint(
                text=text,
                voice=resolved_voice,
                instructions=resolved_instructions,
                response_format=resolved_format,
                speed=resolved_speed,
            )
        else:
            with self.client.audio.speech.with_streaming_response.create(
                model=self.model,
                voice=resolved_voice,
                input=text,
                instructions=resolved_instructions,
                response_format=resolved_format,
                speed=resolved_speed,
            ) as response:
                audio_bytes = b"".join(response.iter_bytes())

        return SpeechSynthesisResult(
            audio_bytes=audio_bytes,
            job_id=uuid.uuid4().hex,
            model=self.model,
            voice=resolved_voice,
            language=resolved_language,
            response_format=resolved_format,
            content_type=SUPPORTED_RESPONSE_FORMATS[resolved_format],
        )

    def _resolve_default_model(self) -> str:
        if self.api_config.get("use_azure", False):
            return os.getenv("AZURE_TTS_MODEL", DEFAULT_MODEL)
        return os.getenv("OPENAI_TTS_MODEL", DEFAULT_MODEL)

    def _synthesize_with_azure_endpoint(
        self,
        *,
        text: str,
        voice: str,
        instructions: str,
        response_format: str,
        speed: float,
    ) -> bytes:
        tts_endpoint = os.getenv("TTS_ENDPOINT")
        api_key = os.getenv("AZURE_API_KEY")
        if not tts_endpoint:
            raise ValueError("TTS_ENDPOINT is not set for Azure text-to-speech.")
        if not api_key:
            raise ValueError("AZURE_API_KEY is not set for Azure text-to-speech.")

        payload = {
            "model": self.model,
            "input": text,
            "voice": voice,
        }

        response = requests.post(
            tts_endpoint,
            headers={
                "Content-Type": "application/json",
                "api-key": api_key,
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.content

    def _build_instructions(self, *, language: str, instructions: str | None) -> str:
        language_instruction = {
            "fi": "Speak naturally in Finnish with clear pronunciation.",
            "en": "Speak naturally in English with clear pronunciation.",
        }[language]

        instruction_parts = [language_instruction]
        if self.default_instructions:
            instruction_parts.append(self.default_instructions.strip())
        if instructions:
            instruction_parts.append(instructions.strip())
        return " ".join(part for part in instruction_parts if part)
