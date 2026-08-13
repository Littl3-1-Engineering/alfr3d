import os
import tempfile
from unittest.mock import patch, MagicMock
import pytest
from services.service_speak.app import (
    generate_tts,
    process_speak_message,
    cleanup_old_audio,
    get_tts,
)


@pytest.fixture(autouse=True)
def reset_tts_instances():
    """Clear the module-level TTS cache between tests."""
    import services.service_speak.app as app

    app.tts_instances.clear()
    yield
    app.tts_instances.clear()


def _fake_tts_module(tts_class):
    """Build a fake top-level `TTS` module usable via sys.modules injection."""
    mock_module = MagicMock()
    mock_module.api.TTS = tts_class
    return mock_module, mock_module.api


class TestSpeakService:
    def test_get_tts_initialization(self):
        """Test TTS instance initialization"""
        mock_tts = MagicMock()
        mock_tts_class = MagicMock()
        mock_tts_class.return_value.to.return_value = mock_tts

        mock_module, mock_api = _fake_tts_module(mock_tts_class)
        with patch.dict("sys.modules", {"TTS": mock_module, "TTS.api": mock_api}):
            tts_instance = get_tts()

            assert tts_instance is mock_tts

    def test_get_tts_cached(self):
        """Test TTS instance caching"""
        mock_tts = MagicMock()
        mock_tts_class = MagicMock()
        mock_tts_class.return_value.to.return_value = mock_tts

        mock_module, mock_api = _fake_tts_module(mock_tts_class)
        with patch.dict("sys.modules", {"TTS": mock_module, "TTS.api": mock_api}):
            # First call initializes
            tts1 = get_tts()
            # Second call should return cached
            tts2 = get_tts()

        assert tts1 is tts2
        assert mock_tts_class.call_count == 1  # Only called once

    def test_generate_tts_success(self):
        """Test successful TTS generation with Coqui TTS"""
        with patch("services.service_speak.app.get_tts") as mock_get_tts:
            mock_tts = MagicMock()
            mock_get_tts.return_value = mock_tts

            with tempfile.TemporaryDirectory() as temp_dir:
                with patch("services.service_speak.app.AUDIO_STORAGE_PATH", temp_dir):
                    filename = generate_tts("Hello world", engine="Coqui")

                    assert filename is not None
                    assert filename.endswith(".wav")
                    # File existence check removed since TTS is mocked
                    mock_tts.tts_to_file.assert_called_once_with(
                        text="Hello world",
                        speaker="Claribel Dervla",
                        language="en",
                        file_path=os.path.join(temp_dir, filename),
                    )

    def test_generate_tts_failure_coqui(self):
        """Test TTS generation failure with Coqui TTS"""
        with patch("services.service_speak.app.get_tts") as mock_get_tts:
            mock_get_tts.return_value = None  # No TTS available

            with patch("services.service_speak.app.gTTS") as mock_gtts_class:
                with patch("services.service_speak.app.send_event") as mock_send:
                    mock_gtts = MagicMock()
                    mock_gtts_class.return_value = mock_gtts

                    with tempfile.TemporaryDirectory() as temp_dir:
                        with patch("services.service_speak.app.AUDIO_STORAGE_PATH", temp_dir):
                            filename = generate_tts("Hello world")

                            assert filename is not None
                            mock_gtts.save.assert_called_once()
                            mock_send.assert_not_called()

    def test_generate_tts_gtts_failure(self):
        """Test gTTS fallback failure"""
        with patch("services.service_speak.app.get_tts") as mock_get_tts:
            with patch("services.service_speak.app.gTTS") as mock_gtts_class:
                with patch("services.service_speak.app.send_event") as mock_send:
                    mock_get_tts.return_value = None
                    mock_gtts_class.side_effect = Exception("gTTS Error")

                    filename = generate_tts("Hello world")

                    assert filename is None
                    mock_send.assert_called_once()

    def _patch_pipeline(self, **kwargs):
        """Patch the DB/personality pipeline used by process_speak_message."""
        import contextlib
        from contextlib import ExitStack

        defaults = {
            "check_mute": lambda: False,
            "track_speak_text": MagicMock(),
            "get_blended_personality": lambda: {"name": "test", "mood": "happy", "blended": {}},
            "get_claude_config": lambda: {},
            "get_quips_for_environment": lambda: [],
            "send_personality_state": MagicMock(),
        }
        defaults.update(kwargs)

        @contextlib.contextmanager
        def _patched():
            with ExitStack() as stack:
                for name, value in defaults.items():
                    stack.enter_context(patch(f"services.service_speak.app.{name}", value))
                yield

        return _patched()

    def test_process_speak_message_string(self):
        """Test processing string message"""
        with patch("services.service_speak.app.generate_tts") as mock_generate:
            with patch("services.service_speak.app.send_event") as mock_send:
                mock_generate.return_value = "test.mp3"

                with self._patch_pipeline() as pipeline:
                    message = MagicMock()
                    message.value = "Test message"

                    process_speak_message(message)

                    mock_generate.assert_called_once_with(
                        "Test message",
                        "Coqui",
                        "tts_models/multilingual/multi-dataset/xtts_v2",
                        None,
                        None,
                    )
                    mock_send.assert_called_once()

    def test_process_speak_message_bytes(self):
        """Test processing bytes message"""
        with patch("services.service_speak.app.generate_tts") as mock_generate:
            with patch("services.service_speak.app.send_event") as mock_send:
                mock_generate.return_value = "test.mp3"

                with self._patch_pipeline() as pipeline:
                    message = MagicMock()
                    message.value = b"Test message"

                    process_speak_message(message)

                    mock_generate.assert_called_once_with(
                        "Test message",
                        "Coqui",
                        "tts_models/multilingual/multi-dataset/xtts_v2",
                        None,
                        None,
                    )
                    mock_send.assert_called_once()

    def test_process_speak_message_llm_success(self):
        """Claude success -> LLM text is spoken"""
        with patch("services.service_speak.app.generate_tts") as mock_generate:
            with patch("services.service_speak.app.send_event") as mock_send:
                mock_generate.return_value = "test.mp3"

                with self._patch_pipeline(
                    get_claude_config=lambda: {
                        "api_key": "sk-test",
                        "usage_limit": 10,
                        "model": "claude-haiku-4-5-20251001",
                    },
                    call_claude_haiku=lambda *args: "LLM enhanced response",
                ) as pipeline:
                    message = MagicMock()
                    message.value = "Test message"

                    process_speak_message(message)

                    mock_generate.assert_called_once_with(
                        "LLM enhanced response",
                        "Coqui",
                        "tts_models/multilingual/multi-dataset/xtts_v2",
                        None,
                        None,
                    )

    def test_process_speak_message_llm_failure_speaks_original(self):
        """Claude failure -> original text spoken, no quip swap"""
        with patch("services.service_speak.app.generate_tts") as mock_generate:
            with patch("services.service_speak.app.send_event") as mock_send:
                mock_generate.return_value = "test.mp3"

                with self._patch_pipeline(
                    get_claude_config=lambda: {
                        "api_key": "sk-test",
                        "usage_limit": 10,
                        "model": "claude-haiku-4-5-20251001",
                    },
                    call_claude_haiku=lambda *args: None,
                    get_quips_for_environment=lambda: [{"type": "smart", "quips": "random quip"}],
                ) as pipeline:
                    message = MagicMock()
                    message.value = "Test message"

                    process_speak_message(message)

                    mock_generate.assert_called_once_with(
                        "Test message",
                        "Coqui",
                        "tts_models/multilingual/multi-dataset/xtts_v2",
                        None,
                        None,
                    )

    def test_process_speak_message_no_key_uses_quip(self):
        """No API key -> personality quip spoken"""
        with patch("services.service_speak.app.generate_tts") as mock_generate:
            with patch("services.service_speak.app.send_event") as mock_send:
                mock_generate.return_value = "test.mp3"

                with self._patch_pipeline(
                    get_claude_config=lambda: {},
                    get_quips_for_environment=lambda: [{"type": "smart", "quips": "random quip"}],
                    select_quip_by_traits=lambda quips, traits: "random quip",
                ) as pipeline:
                    message = MagicMock()
                    message.value = "Test message"

                    process_speak_message(message)

                    mock_generate.assert_called_once_with(
                        "random quip",
                        "Coqui",
                        "tts_models/multilingual/multi-dataset/xtts_v2",
                        None,
                        None,
                    )

    def test_get_tts_failure(self):
        """Test TTS loading failure handling"""
        mock_tts_class = MagicMock(side_effect=ImportError("TTS not available"))
        mock_module, mock_api = _fake_tts_module(mock_tts_class)
        with patch.dict("sys.modules", {"TTS": mock_module, "TTS.api": mock_api}):
            tts_instance = get_tts()

        assert tts_instance is None

    def test_cleanup_old_audio(self):
        """Test cleanup of old audio files"""
        import time

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("services.service_speak.app.AUDIO_STORAGE_PATH", temp_dir):
                with patch("services.service_speak.app.AUDIO_RETENTION_MINUTES", 5):
                    # Create test files
                    old_file = os.path.join(temp_dir, "old.mp3")
                    new_file = os.path.join(temp_dir, "new.mp3")

                    with open(old_file, "w") as f:
                        f.write("old")
                    with open(new_file, "w") as f:
                        f.write("new")

                    # Make old file appear old
                    old_time = time.time() - (6 * 60)  # 6 minutes ago
                    os.utime(old_file, (old_time, old_time))

                    cleanup_old_audio()

                    assert not os.path.exists(old_file)
                    assert os.path.exists(new_file)
