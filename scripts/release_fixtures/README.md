# Release check fixtures

`transcription_fi.mp3` is the audio of the `transcription` live check in
`scripts/release_smoke.py`. It is AI-generated, synthetic speech, made on 2026-11-14 with
gaik's `TextToSpeech` (Azure OpenAI text-to-speech deployment `tts-hd`, voice `nova`)
from two invented sentences:

1. Huoltoteknikko Matti Virtanen ilmoittaa, että pumppu vuotaa kattilahuoneessa.
2. Vuoto havaittiin maanantaina kello yhdeksän, ja kiireellisyys on korkea.

The two sentences are padded to the same length and separated by a 1.6-second pause, so
splitting the 12.8-second file in two halves cuts it in that pause. The check looks for
words of each sentence in the transcripts. If you replace the file, update
`TRANSCRIPTION_FIXTURE_SHA256` and the anchor words in `release_smoke.py`.

The robotic eSpeak recording in the Solution Wizard evaluation fixtures is not used here:
`gpt-4o-transcribe` sometimes skipped its first sentences, which would make the release
gate fail at random.
