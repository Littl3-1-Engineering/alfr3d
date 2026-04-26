import os
from unittest.mock import patch, MagicMock

os.environ["MYSQL_DATABASE"] = "mysql"
os.environ["MYSQL_USER"] = "user"
os.environ["MYSQL_PSWD"] = "password"
os.environ["MYSQL_NAME"] = "alfr3d_db"
os.environ["ALFR3D_ENV_NAME"] = "Test-Env"

from services.service_speak.personality import (
    get_personality_by_environment,
    get_context_by_environment,
    get_blended_personality,
    get_quips_for_environment,
    get_default_personality,
    get_default_context,
    calculate_mood_offset,
    blend_traits,
    determine_mood,
)


class TestPersonalityFunctions:
    def test_get_default_personality_returns_dict(self):
        result = get_default_personality()
        assert isinstance(result, dict)
        assert "name" in result
        assert "sarcasm" in result
        assert result["name"] == "Butler"

    def test_get_default_context_returns_dict(self):
        result = get_default_context()
        assert isinstance(result, dict)
        assert "mood" in result
        assert result["mood"] == "neutral"

    def test_get_blended_personality_returns_dict(self):
        mock_personality_db = {
            "id": 1,
            "name": "Test",
            "sarcasm": 0.5,
            "formality": 0.5,
            "warmth": 0.5,
            "patience": 0.8,
            "linguistic_style": "test",
            "forbidden_words": "",
            "verbal_tics": "",
        }
        mock_context_db = {
            "repeat_count": 0,
            "hour": 12,
            "weather": "clear",
            "mood": "neutral",
            "last_error_count": 0,
            "llm_calls_today": 0,
            "last_text": "",
            "last_spoke_time": None,
        }

        with patch(
            "services.service_speak.personality.get_personality_by_environment",
            return_value=mock_personality_db,
        ):
            with patch(
                "services.service_speak.personality.get_context_by_environment",
                return_value=mock_context_db,
            ):
                result = get_blended_personality()
                assert isinstance(result, dict)
                assert "blended" in result
                assert "mood" in result
                assert isinstance(result["blended"], dict)

    def test_get_blended_personality_handles_list_from_db(self):
        with patch(
            "services.service_speak.personality.get_personality_by_environment",
            return_value=[],
        ):
            with patch(
                "services.service_speak.personality.get_context_by_environment",
                return_value={"mood": "neutral"},
            ):
                result = get_blended_personality()
                assert isinstance(result, dict)
                assert "blended" in result
                assert result["name"] == "Butler"

    def test_calculate_mood_offset_increases_sarcasm_on_repeat(self):
        context = {
            "repeat_count": 5,
            "hour": 12,
            "weather": "clear",
            "last_error_count": 0,
        }
        offset = calculate_mood_offset(context)
        assert offset["sarcasm"] > 0
        assert offset["patience"] < 0

    def test_calculate_mood_offset_late_night_coldness(self):
        context = {
            "repeat_count": 0,
            "hour": 3,
            "weather": "clear",
            "last_error_count": 0,
        }
        offset = calculate_mood_offset(context)
        assert offset["warmth"] < 0

    def test_determine_mood_snarky_high_sarcasm_low_patience(self):
        traits = {"sarcasm": 0.8, "patience": 0.2, "warmth": 0.5}
        context = {"repeat_count": 0, "last_error_count": 0}
        mood = determine_mood(traits, context)
        assert mood == "snarky"

    def test_determine_mood_cheerful_warm_patient(self):
        traits = {"sarcasm": 0.3, "patience": 0.8, "warmth": 0.8}
        context = {"repeat_count": 0, "last_error_count": 0}
        mood = determine_mood(traits, context)
        assert mood == "cheerful"

    def test_determine_mood_exasperated_on_repeat(self):
        traits = {"sarcasm": 0.5, "patience": 0.5, "warmth": 0.5}
        context = {"repeat_count": 5, "last_error_count": 0}
        mood = determine_mood(traits, context)
        assert mood == "exasperated"

    def test_blend_traits_clamps_values(self):
        base = {"sarcasm": 0.5, "patience": 0.5}
        offset = {"sarcasm": 0.6, "patience": -0.6}
        result = blend_traits(base, offset)
        assert result["sarcasm"] == 1.0
        assert result["patience"] == 0.0


class TestDatabaseFunctions:
    def test_get_personality_by_environment_handles_null_values(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "id": 1,
            "name": "Current",
            "sarcasm": None,
            "formality": None,
            "warmth": None,
            "patience": None,
            "linguistic_style": None,
            "forbidden_words": None,
            "verbal_tics": None,
        }

        mock_db = MagicMock()
        mock_db.cursor.return_value = mock_cursor

        with patch("services.service_speak.personality.get_db_connection", return_value=mock_db):
            result = get_personality_by_environment(env_id=1)
            assert isinstance(result, dict)
            assert result["sarcasm"] == 0.0
            assert result["formality"] == 0.5
            assert result["patience"] == 1.0

    def test_get_context_by_environment_handles_null_weather(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "repeat_count": 0,
            "hour": None,
            "weather": None,
            "mood": None,
            "last_error_count": None,
            "llm_calls_today": None,
            "last_text": None,
            "last_spoke_time": None,
        }

        mock_db = MagicMock()
        mock_db.cursor.return_value = mock_cursor

        with patch("services.service_speak.personality.get_db_connection", return_value=mock_db):
            result = get_context_by_environment(env_id=1)
            assert isinstance(result, dict)
            assert result["weather"] == "clear"
            assert result["hour"] is not None

    def test_get_quips_for_environment_returns_list_of_dicts(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"type": "formal", "quips": "At your service"},
            {"type": "casual", "quips": "Hey there"},
        ]

        mock_db = MagicMock()
        mock_db.cursor.return_value = mock_cursor

        with patch("services.service_speak.personality.get_db_connection", return_value=mock_db):
            result = get_quips_for_environment(env_id=1)
            assert isinstance(result, list)
            assert len(result) == 2
            assert isinstance(result[0], dict)
            assert result[0]["type"] == "formal"
