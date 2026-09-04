#!/usr/bin/env python3
"""
Speak Service for ALFR3D - Text-to-Speech using Google Cloud TTS
Consumes messages from 'speak' Kafka topic, generates audio, and notifies frontend
"""

# Standard libraries
import os
import re
import sys
import logging
import random
import threading
import time
import orjson
from datetime import datetime

# Third-party libraries
import schedule
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from gtts import gTTS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../common"))
from common import get_producer as _get_producer, get_kafka_url, get_connection  # noqa: E402
from common import db_utils  # noqa: E402

# Local imports
from personality import (  # noqa: E402
    get_blended_personality,
    build_llm_system_prompt,
    get_quips_for_environment,
    select_quip_by_traits,
    track_speak_text,
)
from llm_client import call_claude_haiku, get_claude_config  # noqa: E402

# Set up logging
logger = logging.getLogger("SpeakService")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Environment variables
ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")
AUDIO_STORAGE_PATH = os.environ.get("AUDIO_STORAGE_PATH", "/tmp/audio")
AUDIO_RETENTION_MINUTES = int(os.environ.get("AUDIO_RETENTION_MINUTES", "5"))

# On the no-LLM path a matched quip *replaces* the spoken line entirely, so applying one
# every single time makes ALFR3D sound like it's performing a bit on every utterance (and
# drops the real message). Gate it: only roughly 1 in QUIP_ODDS speaks gets quip-substituted,
# the rest speak their original text. Mirrors personality.py's TICS_FREQUENCY gating of the
# LLM-path verbal tics.
QUIP_ODDS = int(os.environ.get("SPEAK_QUIP_ODDS", "8"))

# Heartbeat file the Kafka consumer touches on every connect attempt and poll cycle. A stale
# heartbeat means the consumer thread is stuck (e.g. hung inside a blocking Kafka connect at
# boot, racing the broker before it's healthy) even though the process itself looks alive -
# both main()'s watchdog and the Docker HEALTHCHECK key off this file.
HEARTBEAT_PATH = "/tmp/speak_heartbeat"
HEARTBEAT_STALE_SECONDS = 90
KAFKA_CONSUMER_RETRY_INITIAL_SECONDS = 5
KAFKA_CONSUMER_RETRY_MAX_SECONDS = 60

# Ensure audio directory exists
os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)

# Global TTS instances (cache multiple models)
tts_instances = {}


def check_mute() -> bool:
    """
    Description:
             checks what time it is and decides if Alfr3d should be quiet
             - between wake-up time and bedtime (the Morning..Bedtime routine window)
             - only when an owner/technoking/resident is online to hear it

    Delegates to the shared implementation in common.db_utils so the waking-hours
    window comes from one place (day_context) -- this used to be a ~110-line
    duplicate of check_mute_optimized().
    """
    logger.info("Checking if Alfr3d should be mute")

    if not ENV_NAME:
        logger.error("ALFR3D_ENV_NAME environment variable not set")
        return False

    return db_utils.check_mute_optimized(ENV_NAME)


def list_available_speakers(model_name="tts_models/multilingual/multi-dataset/xtts_v2"):
    """List available speakers for a given model"""
    try:
        tts_instance = get_tts(model_name)
        if tts_instance and hasattr(tts_instance, "speakers") and tts_instance.speakers:
            logger.info(f"Available speakers for {model_name}: {tts_instance.speakers}")
            return tts_instance.speakers
        else:
            logger.info(f"No speakers available for {model_name}")
            return []
    except Exception as e:
        logger.error(f"Failed to list speakers for {model_name}: {str(e)}")
        return []


def send_event(event_type, message, audio_url=None, text=None):
    """Send event to event-stream topic"""
    p = _get_producer()
    if p:
        event = {
            "id": f"speak_{datetime.utcnow().isoformat()}",
            "type": event_type,
            "message": message,
            "time": datetime.utcnow().isoformat() + "Z",
        }
        if audio_url:
            event["audio_url"] = audio_url
        if text:
            event["text"] = text
        try:
            p.send("event-stream", orjson.dumps(event))
            p.flush()
            logger.info(f"Sent event: {event}")
        except KafkaError as e:
            logger.error(f"Kafka error sending event: {e}")
        except Exception as e:
            logger.error(f"Failed to send event: {e}")


def send_personality_state(personality, llm_used=False):
    """Send personality state to personality Kafka topic and event-stream"""
    p = _get_producer()
    if p:
        blended = personality.get("blended", {})
        state = {
            "id": f"personality_{datetime.utcnow().isoformat()}",
            "type": "personality_state",
            "sarcasm": blended.get("sarcasm", 0.5),
            "formality": blended.get("formality", 0.5),
            "warmth": blended.get("warmth", 0.5),
            "patience": blended.get("patience", 1.0),
            "mood": personality.get("mood", "neutral"),
            "llm_used": llm_used,
            "time": datetime.utcnow().isoformat() + "Z",
        }
        try:
            p.send("personality", orjson.dumps(state))
            p.send(
                "event-stream",
                orjson.dumps({"id": state["id"], "type": "personality_state", **state}),
            )
            p.flush()
            logger.info(f"Sent personality state: {state['mood']}")
        except Exception as e:
            logger.error(f"Failed to send personality state: {str(e)}")


def get_tts(model_name="tts_models/multilingual/multi-dataset/xtts_v2"):
    """Get or initialize TTS instance for specified model"""
    if model_name not in tts_instances:
        try:
            from TTS.api import TTS  # Lazy import to handle CUDA issues

            logger.info(f"Initializing Coqui TTS model: {model_name}")
            tts_instances[model_name] = TTS(model_name).to("cpu")
            logger.info(f"Coqui TTS model {model_name} loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Coqui TTS model {model_name}: {str(e)}")
            tts_instances[model_name] = None
    return tts_instances[model_name]


def generate_tts(
    text,
    engine="gTTS",
    model="tts_models/multilingual/multi-dataset/xtts_v2",
    speaker=None,
    speaker_wav=None,
):
    """Generate TTS audio using specified engine and model, with fallback"""
    if engine == "Coqui":
        try:
            # Try Coqui TTS first
            tts_instance = get_tts(model)
            if tts_instance:
                # Generate unique filename
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
                filename = f"speech_{timestamp}.wav"  # XTTS outputs WAV
                filepath = os.path.join(AUDIO_STORAGE_PATH, filename)

                # Generate speech
                if "xtts" in model:
                    # XTTS v2 supports built-in speakers and voice cloning
                    if speaker_wav:
                        # Use specified voice file for cloning
                        logger.info(f"Using voice cloning with speaker_wav: {speaker_wav}")
                        tts_instance.tts_to_file(
                            text=text,
                            file_path=filepath,
                            speaker_wav=speaker_wav,
                            language="en",
                        )
                    else:
                        # Use specified speaker or default to Claribel Dervla
                        speaker_to_use = speaker if speaker else "Claribel Dervla"
                        logger.info(f"Using speaker: {speaker_to_use}")
                        tts_instance.tts_to_file(
                            text=text,
                            file_path=filepath,
                            speaker=speaker_to_use,
                            language="en",
                        )
                elif "vits" in model and speaker:
                    # VITS models support speaker_idx for multi-speaker models
                    tts_instance.tts_to_file(
                        text=text, file_path=filepath, speaker_idx=int(speaker)
                    )
                else:
                    # Single-speaker models
                    tts_instance.tts_to_file(text=text, file_path=filepath)

                logger.info(f"Generated Coqui TTS audio: {filepath}")
                return filename
            else:
                logger.warning("Coqui TTS not available, falling back to gTTS")
        except Exception as e:
            logger.error(f"Coqui TTS generation failed: {str(e)}, falling back to gTTS")

    # Fallback to gTTS (or primary if gTTS was requested)
    try:
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        filename = f"speech_{timestamp}.mp3"
        filepath = os.path.join(AUDIO_STORAGE_PATH, filename)

        # Use gTTS with UK voice
        tts_gtts = gTTS(text=text, lang="en", tld="co.uk", slow=False)
        tts_gtts.save(filepath)

        logger.info(f"Generated gTTS audio: {filepath}")
        return filename

    except Exception as e:
        logger.error(f"gTTS generation failed: {str(e)}")
        send_event("warning", f"TTS failed: {str(e)}")
        return None


_ALFR3D_NAME_RE = re.compile(r"\balfr3d\b", re.IGNORECASE)


def normalize_pronunciation(text):
    """Rewrite the leetspeak 'alfr3d' to 'Alfred' so TTS pronounces it correctly."""
    return _ALFR3D_NAME_RE.sub("Alfred", text)


def process_speak_message(message):
    """Process incoming speak message with personality enhancement"""
    try:
        # Handle both string and bytes, and parse JSON if possible
        raw_value = message.value
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8")

        # Try to parse as JSON first
        try:
            message_data = orjson.loads(raw_value)
            text = message_data.get("text", str(raw_value))
            engine = message_data.get("engine", "Coqui")
            model = message_data.get("model", "tts_models/multilingual/multi-dataset/xtts_v2")
            speaker = message_data.get("speaker")
            speaker_wav = message_data.get("speaker_wav")
            skip_personality = message_data.get("skip_personality", False)
        except (orjson.JSONDecodeError, TypeError):
            text = str(raw_value)
            engine = "Coqui"
            model = "tts_models/multilingual/multi-dataset/xtts_v2"
            speaker = None
            speaker_wav = None
            skip_personality = False

        logger.info(
            f"Processing speak message: {text[:50]}... "
            f"(engine: {engine}, model: {model}, speaker: {speaker}, speaker_wav: {speaker_wav})"
        )

        if check_mute():
            logger.info("Alfr3d is muted, discarding speak request")
            return

        track_speak_text(text)

        llm_used = False
        if not skip_personality:
            try:
                personality = get_blended_personality()
                blended = personality.get("blended", {})

                config = get_claude_config()
                if config.get("api_key"):
                    logger.info(
                        f"Using personality: {personality.get('name')}, "
                        f"mood: {personality.get('mood')}"
                    )

                    system_prompt = build_llm_system_prompt(personality)
                    llm_text = call_claude_haiku(system_prompt, text, config)

                    if llm_text:
                        text = llm_text
                        llm_used = True
                        logger.info(f"LLM enhanced text: {text[:50]}...")
                    else:
                        logger.warning("Claude call failed, speaking original text")
                elif QUIP_ODDS > 0 and random.randint(1, QUIP_ODDS) == 1:
                    quips = get_quips_for_environment()
                    if quips:
                        selected_quip = select_quip_by_traits(quips, blended)
                        if selected_quip:
                            text = selected_quip
                            logger.info(f"Selected quip: {text[:50]}...")

                send_personality_state(personality, llm_used)

            except Exception as e:
                logger.warning(f"Personality processing failed: {str(e)}, using original text")

        # Generate TTS
        text = normalize_pronunciation(text)
        filename = generate_tts(text, engine, model, speaker, speaker_wav)
        if filename:
            audio_url = f"/api/audio/{filename}"
            send_event("audio", f"Playing: {text[:50]}...", audio_url=audio_url, text=text)
        else:
            logger.error("Failed to generate audio for message")

    except Exception as e:
        logger.error(f"Error processing speak message: {str(e)}")
        send_event("warning", f"Speak processing failed: {str(e)}")


def touch_heartbeat():
    """Record that the consumer is making progress (connecting or actively polling)."""
    try:
        with open(HEARTBEAT_PATH, "w") as f:
            f.write(str(time.time()))
    except OSError as e:
        logger.warning(f"Failed to write heartbeat: {e}")


def consume_speak():
    """Consume messages from the speak topic, retrying with backoff on any failure.

    Bounds the Kafka connect itself (fixed api_version skips the broker version auto-probe,
    request_timeout_ms caps each round trip) so a broker that isn't ready yet - e.g. right
    after a host reboot, racing service-speak's own restart - fails fast instead of hanging
    the thread forever. touch_heartbeat() lets main()'s watchdog catch it either way.
    """
    backoff = KAFKA_CONSUMER_RETRY_INITIAL_SECONDS

    while True:
        touch_heartbeat()
        try:
            kafka_url = get_kafka_url()
            logger.info(f"Speak consumer bootstrap servers: {kafka_url}")
            consumer = KafkaConsumer(
                "speak",
                bootstrap_servers=kafka_url,
                auto_offset_reset="latest",
                group_id="speak-service",
                api_version=(2, 5, 0),
                request_timeout_ms=30000,
                reconnect_backoff_ms=1000,
                reconnect_backoff_max_ms=10000,
            )
            logger.info("Connected to Kafka speak topic")
            backoff = KAFKA_CONSUMER_RETRY_INITIAL_SECONDS

            while True:
                touch_heartbeat()
                msg = consumer.poll(timeout_ms=1000)
                if msg:
                    for tp, messages in msg.items():
                        for message in messages:
                            process_speak_message(message)

        except Exception as e:
            logger.error(f"Speak consumer error: {e}; retrying in {backoff}s")
            send_event("warning", f"Speak service Kafka error: {str(e)}")
            time.sleep(backoff)
            backoff = min(backoff * 2, KAFKA_CONSUMER_RETRY_MAX_SECONDS)


def cleanup_old_audio():
    """Clean up audio files older than retention period"""
    try:
        import glob

        cutoff_time = time.time() - (AUDIO_RETENTION_MINUTES * 60)

        for filepath in glob.glob(os.path.join(AUDIO_STORAGE_PATH, "*.mp3")):
            if os.path.getmtime(filepath) < cutoff_time:
                os.remove(filepath)
                logger.info(f"Cleaned up old audio file: {filepath}")

    except Exception as e:
        logger.error(f"Audio cleanup failed: {str(e)}")


def reset_inactive_repeat_count():
    """Reset repeat_count for contexts with stale last_spoke_time (>5 minutes)"""
    from personality import get_environment_id

    try:
        env_id = get_environment_id()
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "INSERT IGNORE INTO context (environment_id, repeat_count, last_spoke_time, "
            "updated_at) "
            "VALUES (%s, 0, NOW(), NOW())",
            (env_id,),
        )
        cursor.execute(
            "UPDATE context SET repeat_count = 0, updated_at = NOW() "
            "WHERE environment_id = %s AND "
            "(last_spoke_time < DATE_SUB(NOW(), INTERVAL 5 MINUTE) OR last_spoke_time IS NULL)",
            (env_id,),
        )
        db.commit()
        if cursor.rowcount > 0:
            logger.info("Reset repeat_count for inactive context")
        db.close()
    except Exception as e:
        logger.error(f"Reset inactive repeat count failed: {str(e)}")


def reset_daily_llm_calls():
    """Reset LLM calls counter at midnight"""
    from personality import get_environment_id

    try:
        env_id = get_environment_id()
        db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO context (environment_id, llm_calls_today, updated_at) "
            "VALUES (%s, 0, NOW()) "
            "ON DUPLICATE KEY UPDATE llm_calls_today = 0, updated_at = NOW()",
            (env_id,),
        )
        db.commit()
        if cursor.rowcount > 0:
            logger.info("Reset daily LLM call counter")
        db.close()
    except Exception as e:
        logger.error(f"Reset daily LLM calls failed: {str(e)}")


def main():
    logger.info("Starting Speak Service")
    touch_heartbeat()

    schedule.every(1).minutes.do(cleanup_old_audio)
    schedule.every(1).minutes.do(reset_inactive_repeat_count)
    schedule.every(1).day.do(reset_daily_llm_calls)

    shutdown_event = threading.Event()

    consumer_thread = threading.Thread(target=consume_speak, daemon=True)
    consumer_thread.start()

    while not shutdown_event.is_set():
        schedule.run_pending()

        try:
            heartbeat_age = time.time() - os.path.getmtime(HEARTBEAT_PATH)
        except OSError:
            heartbeat_age = float("inf")

        if heartbeat_age > HEARTBEAT_STALE_SECONDS:
            # The consumer thread is stuck (e.g. hung inside a blocking Kafka connect) even
            # though this scheduler loop is still ticking fine. Exit so the container's
            # `restart: unless-stopped` policy gives it a clean restart instead of it sitting
            # silently dead for hours.
            logger.critical(
                f"Speak consumer heartbeat stale for {heartbeat_age:.0f}s "
                f"(> {HEARTBEAT_STALE_SECONDS}s); exiting for container restart"
            )
            os._exit(1)

        shutdown_event.wait(timeout=1)


def test_xtts_speakers():
    """Test function to list XTTS speakers and provide usage info"""
    print("=== XTTS v2 Speaker Information ===")
    print("XTTS v2 is a voice cloning model that can:")
    print("1. Clone voices from audio samples (recommended)")
    print("2. Use built-in speakers if available")
    print()

    speakers = list_available_speakers("tts_models/multilingual/multi-dataset/xtts_v2")
    if speakers and speakers != ["voice_cloning_required"]:
        print("Available built-in speakers:")
        for i, speaker in enumerate(speakers):
            print(f"  {i}: {speaker}")
        print()
        print("Usage examples:")
        print('  {"text": "Hello", "speaker": "Ana Florence"}')
    else:
        print("No built-in speakers found.")
        print("XTTS v2 primarily uses voice cloning.")
    print()
    print("Voice cloning usage:")
    print('  {"text": "Hello", "speaker_wav": "/path/to/voice_sample.wav"}')
    print("  (voice_sample.wav should be 3-6 seconds of the target voice)")
    print()
    print(
        "Supported languages: en, es, fr, de, it, pt, pl, tr, ru, nl, cs, ar, zh-cn, hu, ko, ja, hi"
    )
    return speakers


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--list-speakers":
        test_xtts_speakers()
    else:
        main()
