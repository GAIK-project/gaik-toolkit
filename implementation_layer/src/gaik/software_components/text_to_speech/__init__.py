"""Text-to-Speech generation using OpenAI or Azure OpenAI.

Main Classes:
    - TextToSpeech: High-level text-to-speech API
    - SpeechSynthesisResult: Container for generated audio bytes

Configuration:
    - get_openai_config: Get OpenAI/Azure configuration
    - create_openai_client: Create OpenAI client from config

Example:
    >>> from gaik.software_components.text_to_speech import TextToSpeech, get_openai_config
    >>> config = get_openai_config(use_azure=True)
    >>> tts = TextToSpeech(api_config=config)
    >>> result = tts.synthesize("Hei maailma", language="fi")
    >>> result.save("output")
"""

__all__ = []

try:
    from gaik.software_components.config import create_openai_client, get_openai_config

    __all__.extend(["get_openai_config", "create_openai_client"])
except ImportError:
    pass

try:
    from .text_to_speech import (
        DEFAULT_LANGUAGE,
        DEFAULT_MODEL,
        DEFAULT_RESPONSE_FORMAT,
        DEFAULT_VOICE,
        SUPPORTED_LANGUAGES,
        SpeechSynthesisResult,
        TextToSpeech,
    )

    __all__.extend(
        [
            "TextToSpeech",
            "SpeechSynthesisResult",
            "SUPPORTED_LANGUAGES",
            "DEFAULT_LANGUAGE",
            "DEFAULT_MODEL",
            "DEFAULT_VOICE",
            "DEFAULT_RESPONSE_FORMAT",
        ]
    )
except ImportError:
    pass
