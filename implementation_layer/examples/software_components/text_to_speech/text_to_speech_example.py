from pathlib import Path

from gaik.software_components.text_to_speech import TextToSpeech, get_openai_config


def main() -> None:
    config = get_openai_config(use_azure=False)
    tts = TextToSpeech(api_config=config)

    result = tts.synthesize(
        "Tama on GAIKin tekstista puheeksi -esimerkki. Talla komponentilla voi tuottaa puhetta suomeksi tai englanniksi.",
        language="fi",
        voice="marin",
    )

    output_dir = Path("output")
    saved_path = result.save(output_dir)
    print(f"Saved audio to: {saved_path}")


if __name__ == "__main__":
    main()
