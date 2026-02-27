#!/usr/bin/env python3
"""
Speak Service for ALFR3D - Text-to-Speech using Google Cloud TTS
Consumes messages from 'speak' Kafka topic, generates audio, and notifies frontend
"""
# Standard libraries
import os
import sys
import logging
import threading
import time
import json
from datetime import datetime

# Third-party libraries
import schedule
import pymysql
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from gtts import gTTS

# Set up logging
logger = logging.getLogger("SpeakService")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Environment variables
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PSWD = os.environ.get("MYSQL_PSWD")
MYSQL_DB = os.environ.get("MYSQL_NAME")
KAFKA_URL = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
ENV_NAME = os.environ.get("ALFR3D_ENV_NAME")
AUDIO_STORAGE_PATH = os.environ.get("AUDIO_STORAGE_PATH", "/tmp/audio")
AUDIO_RETENTION_MINUTES = int(os.environ.get("AUDIO_RETENTION_MINUTES", "5"))

# Ensure audio directory exists
os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)

# Global producer
producer = None

# Global TTS instances (cache multiple models)
tts_instances = {}


def check_mute() -> bool:
    """
    Description:
             checks what time it is and decides if Alfr3d should be quiet
             - between wake-up time and bedtime
             - only when Athos is at home
             - only when 'owner' is at home
    """
    logger.info("Checking if Alfr3d should be mute")
    result = False

    if not ENV_NAME:
        logger.error("ALFR3D_ENV_NAME environment variable not set")
        return False

    try:
        db = pymysql.connect(host=MYSQL_DATABASE, user=MYSQL_USER, passwd=MYSQL_PSWD, db=MYSQL_DB)
        cursor = db.cursor()
    except Exception as e:
        logger.error("Failed to connect to database")
        logger.error("Traceback: " + str(e))
        return False

    # get environemnt id of current environment
    cursor.execute("SELECT * from environment WHERE name = %s;", (ENV_NAME,))
    data = cursor.fetchone()
    if not data:
        logger.error("Environment not found")
        db.close()
        return False
    env_id = data[0]

    cursor.execute(
        "SELECT * from routines WHERE environment_id = %s and name = %s;",
        (env_id, "Morning"),
    )
    morning = cursor.fetchone()
    if not morning:
        logger.error("Morning routine not found")
        db.close()
        return False
    morning_time = morning[2]

    cursor.execute(
        "SELECT * from routines WHERE environment_id = %s and name = %s;",
        (env_id, "Bedtime"),
    )
    bed = cursor.fetchone()
    if not bed:
        logger.error("Bedtime routine not found")
        db.close()
        return False
    bed_time = bed[2]

    cur_time = datetime.now()
    mor_time = datetime.now().replace(
        hour=int(morning_time.seconds / 3600),
        minute=int((morning_time.seconds // 60) % 60),
    )
    end_time = datetime.now().replace(
        hour=int(bed_time.seconds / 3600), minute=int((bed_time.seconds // 60) % 60)
    )

    # only speak between morning alarm and bedtime alarm...
    if cur_time > mor_time and cur_time < end_time:
        logger.info("Alfr3d is free to speak during this time of day")
    else:
        logger.info("Alfr3d should be quiet while we're sleeping")
        result = True

    # get state id of status "online"
    cursor.execute('SELECT * from states WHERE state = "online";')
    data = cursor.fetchone()
    if not data:
        logger.error("Online state not found")
        db.close()
        return False
    state_id = data[0]

    # get all user types which are god or owner type
    cursor.execute(
        'SELECT * from user_types WHERE type = "owner" or type = "technoking" or type = "resident";'
    )
    data = cursor.fetchall()
    if not data:
        logger.error("No user types found")
        db.close()
        return False
    types = []
    for item in data:
        types.append(item[0])

    # see if any users worth speaking to are online
    cursor.execute(
        "SELECT * from user WHERE state = %s and type IN (%s, %s, %s);",
        (state_id, types[0], types[1], types[2]),
    )
    data = cursor.fetchall()

    if not data:
        logger.info("Alfr3d should be quiet when no worthy ears are around")
        result = True
    else:
        logger.info("Alfr3d has worthy listeners:")
        for user in data:
            logger.info("    - " + user[1])

    if result:
        logger.info("Alfr3d is to be quiet")
    else:
        logger.info("Alfr3d is free to speak")

    return result


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


def get_producer():
    global producer
    if producer is None:
        try:
            producer = KafkaProducer(
                bootstrap_servers=[KAFKA_URL],
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            logger.info("Connected to Kafka producer")
        except KafkaError as e:
            logger.error("Failed to connect to Kafka producer: " + str(e))
            return None
    return producer


def send_event(event_type, message, audio_url=None, text=None):
    """Send event to event-stream topic"""
    p = get_producer()
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
            p.send("event-stream", event)
            p.flush()
            logger.info(f"Sent event: {event}")
        except Exception as e:
            logger.error(f"Failed to send event: {str(e)}")


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
                            text=text, file_path=filepath, speaker_wav=speaker_wav, language="en"
                        )
                    else:
                        # Use specified speaker or default to Claribel Dervla
                        speaker_to_use = speaker if speaker else "Claribel Dervla"
                        logger.info(f"Using speaker: {speaker_to_use}")
                        tts_instance.tts_to_file(
                            text=text, file_path=filepath, speaker=speaker_to_use, language="en"
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


def process_speak_message(message):
    """Process incoming speak message"""
    try:
        # Handle both string and bytes, and parse JSON if possible
        raw_value = message.value
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8")

        # Try to parse as JSON first
        try:
            message_data = json.loads(raw_value)
            text = message_data.get("text", str(raw_value))
            engine = message_data.get("engine", "Coqui")
            model = message_data.get("model", "tts_models/multilingual/multi-dataset/xtts_v2")
            speaker = message_data.get("speaker")  # Optional speaker parameter
            speaker_wav = message_data.get("speaker_wav")  # Optional voice file for XTTS
        except (json.JSONDecodeError, TypeError):
            # Not JSON, treat as plain text
            text = str(raw_value)
            engine = "Coqui"
            model = "tts_models/multilingual/multi-dataset/xtts_v2"
            speaker = None
            speaker_wav = None

        logger.info(
            f"Processing speak message: {text[:50]}... "
            f"(engine: {engine}, model: {model}, speaker: {speaker}, speaker_wav: {speaker_wav})"
        )

        if check_mute():
            logger.info("Alfr3d is muted, discarding speak request")
            return

        # Generate TTS
        filename = generate_tts(text, engine, model, speaker, speaker_wav)
        if filename:
            audio_url = f"/api/audio/{filename}"
            send_event("audio", f"Playing: {text[:50]}...", audio_url=audio_url, text=text)
        else:
            logger.error("Failed to generate audio for message")

    except Exception as e:
        logger.error(f"Error processing speak message: {str(e)}")
        send_event("warning", f"Speak processing failed: {str(e)}")


def consume_speak():
    """Consume messages from speak topic"""
    try:
        logger.info(f"Speak consumer bootstrap servers: {KAFKA_URL}")
        consumer = KafkaConsumer(
            "speak",
            bootstrap_servers=KAFKA_URL,
            auto_offset_reset="latest",
            group_id="speak-service",
        )
        logger.info("Connected to Kafka speak topic")

        while True:
            msg = consumer.poll(timeout_ms=1000)
            if msg:
                for tp, messages in msg.items():
                    for message in messages:
                        process_speak_message(message)

    except KafkaError as e:
        logger.error(f"Error connecting to Kafka for speak: {str(e)}")
        send_event("warning", f"Speak service Kafka error: {str(e)}")


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


def main():
    logger.info("Starting Speak Service")

    # Schedule cleanup every minute
    schedule.every(1).minutes.do(cleanup_old_audio)

    # Start consumer in thread
    consumer_thread = threading.Thread(target=consume_speak, daemon=True)
    consumer_thread.start()

    # Run scheduler
    while True:
        schedule.run_pending()
        time.sleep(30)


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
