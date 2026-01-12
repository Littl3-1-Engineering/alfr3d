import os
import tempfile
from unittest.mock import patch, MagicMock
from services.service_speak.app import (
    generate_tts,
    process_speak_message,
    cleanup_old_audio,
    get_tts,
)


class TestSpeakService:
    def test_get_tts_initialization(self):
        """Test TTS instance initialization"""
        mock_tts_module = MagicMock()
        mock_tts_class = MagicMock()
        mock_tts_module.api.TTS = mock_tts_class
        mock_tts = MagicMock()
        mock_tts_class.return_value.to.return_value = mock_tts

        with patch.dict("sys.modules", {"TTS": mock_tts_module, "TTS.api": mock_tts_module.api}):
            tts_instance = get_tts()

            assert tts_instance is mock_tts

    def test_get_tts_cached(self):
        """Test TTS instance caching"""
        mock_tts_module = MagicMock()
        mock_tts_class = MagicMock()
        mock_tts_module.api.TTS = mock_tts_class
        mock_tts = MagicMock()
        mock_tts_class.return_value.to.return_value = mock_tts

        with patch.dict("sys.modules", {"TTS": mock_tts_module, "TTS.api": mock_tts_module.api}):
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
                    assert os.path.exists(os.path.join(temp_dir, filename))
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

    def test_process_speak_message_string(self):
        """Test processing string message"""
        with patch("services.service_speak.app.generate_tts") as mock_generate:
            with patch("services.service_speak.app.send_event") as mock_send:
                mock_generate.return_value = "test.mp3"

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

    def test_get_tts_failure(self):
        """Test TTS loading failure handling"""
        with patch.dict("sys.modules", {"TTS": None, "TTS.api": None}):
            tts_instance = get_tts()

            assert tts_instance is None

    # Removed outdated test for voice extraction

    def test_cleanup_old_audio(self):
        """Test cleanup of old audio files"""
        import time

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("services.service_speak.app.AUDIO_STORAGE_PATH", temp_dir):
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
