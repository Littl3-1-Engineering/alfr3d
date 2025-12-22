import os
import tempfile
from unittest.mock import patch, MagicMock
from services.service_speak.app import generate_tts, process_speak_message, cleanup_old_audio


class TestSpeakService:
    def test_generate_tts_success(self):
        """Test successful TTS generation"""
        with patch("services.service_speak.app.texttospeech.TextToSpeechClient") as mock_client:
            mock_response = MagicMock()
            mock_response.audio_content = b"fake_audio_data"
            mock_client.return_value.synthesize_speech.return_value = mock_response

            with tempfile.TemporaryDirectory() as temp_dir:
                with patch("services.service_speak.app.AUDIO_STORAGE_PATH", temp_dir):
                    filename = generate_tts("Hello world")

                    assert filename is not None
                    assert filename.endswith(".mp3")
                    assert os.path.exists(os.path.join(temp_dir, filename))

    def test_generate_tts_failure(self):
        """Test TTS generation failure"""
        with patch("services.service_speak.app.texttospeech.TextToSpeechClient") as mock_client:
            mock_client.return_value.synthesize_speech.side_effect = Exception("API Error")

            filename = generate_tts("Hello world")

            assert filename is None

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
