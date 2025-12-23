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
        """Test TTS instance initialization and voice extraction"""
        with patch("services.service_speak.app.TTS") as mock_tts_class:
            with patch("services.service_speak.app.torch.load") as mock_torch_load:
                with patch("services.service_speak.app.os.path.exists") as mock_exists:
                    with patch("services.service_speak.app.os.makedirs") as _:
                        with patch("services.service_speak.app.torch.save") as mock_torch_save:
                            mock_tts = MagicMock()
                            mock_tts_class.return_value.to.return_value = mock_tts

                            # Mock speakers file exists and contains Claribel Dervox
                            mock_exists.side_effect = (
                                lambda path: "Claribel_Dervox.pth" not in path
                            )  # File doesn't exist initially
                            mock_speakers = {"Claribel Dervox": MagicMock()}
                            mock_torch_load.return_value = mock_speakers

                            tts_instance = get_tts()

                            assert tts_instance is mock_tts
                            mock_torch_load.assert_called_once()
                            mock_torch_save.assert_called_once()

    def test_get_tts_cached(self):
        """Test TTS instance caching"""
        with patch("services.service_speak.app.TTS") as mock_tts_class:
            mock_tts = MagicMock()
            mock_tts_class.return_value.to.return_value = mock_tts

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
                    filename = generate_tts("Hello world")

                    assert filename is not None
                    assert filename.endswith(".mp3")
                    assert os.path.exists(os.path.join(temp_dir, filename))
                    mock_tts.tts_to_file.assert_called_once_with(
                        text="Hello world",
                        speaker="Claribel Dervox",
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

                mock_generate.assert_called_once_with("Test message")
                mock_send.assert_called_once()

    def test_process_speak_message_bytes(self):
        """Test processing bytes message"""
        with patch("services.service_speak.app.generate_tts") as mock_generate:
            with patch("services.service_speak.app.send_event") as mock_send:
                mock_generate.return_value = "test.mp3"

                message = MagicMock()
                message.value = b"Test message"

                process_speak_message(message)

                mock_generate.assert_called_once_with("Test message")
                mock_send.assert_called_once()

    def test_get_tts_voice_extraction_failure(self):
        """Test voice extraction failure handling"""
        with patch("services.service_speak.app.TTS") as mock_tts_class:
            with patch("services.service_speak.app.torch.load") as mock_torch_load:
                with patch("services.service_speak.app.os.path.exists") as mock_exists:
                    with patch("services.service_speak.app.os.makedirs") as _:
                        with patch("services.service_speak.app.logger") as mock_logger:
                            mock_tts = MagicMock()
                            mock_tts_class.return_value.to.return_value = mock_tts

                            # Mock speakers file doesn't exist
                            mock_exists.side_effect = lambda path: False
                            mock_torch_load.side_effect = Exception("Load failed")

                            tts_instance = get_tts()

                            assert tts_instance is mock_tts
                            mock_logger.error.assert_called_once_with(
                                "speakers_xtts.pth not found; voice extraction failed."
                            )

    def test_get_tts_voice_not_found(self):
        """Test when Claribel Dervox is not in speakers"""
        with patch("services.service_speak.app.TTS") as mock_tts_class:
            with patch("services.service_speak.app.torch.load") as mock_torch_load:
                with patch("services.service_speak.app.os.path.exists") as mock_exists:
                    with patch("services.service_speak.app.os.makedirs") as _:
                        with patch("services.service_speak.app.logger") as mock_logger:
                            mock_tts = MagicMock()
                            mock_tts_class.return_value.to.return_value = mock_tts

                            mock_exists.side_effect = lambda path: "Claribel_Dervox.pth" not in path
                            mock_speakers = {"Other Speaker": MagicMock()}
                            mock_torch_load.return_value = mock_speakers

                            tts_instance = get_tts()

                            assert tts_instance is mock_tts
                            mock_logger.warning.assert_called_once_with(
                                "Claribel Dervox not found in speakers_xtts.pth."
                            )

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
