"""Import tests for audio_to_structured_data pipeline."""

def test_pipeline_import():
    from gaik.software_components.audio_to_structured_data import AudioToStructuredData

    pipeline = AudioToStructuredData(use_azure=False)
    assert pipeline is not None
