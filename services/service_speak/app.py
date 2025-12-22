#!/usr/bin/env python3
"""
Speak Service for ALFR3D - Text-to-Speech using Google Cloud TTS
Consumes messages from 'speak' Kafka topic, generates audio, and notifies frontend
"""

import os
import sys
import logging
import threading
import time
import json
import schedule
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from TTS.api import TTS
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
AUDIO_STORAGE_PATH = os.environ.get("AUDIO_STORAGE_PATH", "/tmp/audio")
AUDIO_RETENTION_MINUTES = int(os.environ.get("AUDIO_RETENTION_MINUTES", "5"))

# Ensure audio directory exists
os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)

# Global producer
producer = None

# Global TTS instance
tts = None


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
            "id": f"speak_{datetime.now().isoformat()}",
            "type": event_type,
            "message": message,
            "time": datetime.now().isoformat(),
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


def get_tts():
    """Get or initialize TTS instance"""
    global tts
    if tts is None:
        try:
            logger.info("Initializing Coqui TTS model...")
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
            logger.info("Coqui TTS model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Coqui TTS model: {str(e)}")
            tts = None
    return tts


def generate_tts(text):
    """Generate TTS audio using Coqui TTS with UK female voice, fallback to gTTS"""
    try:
        # Try Coqui TTS first
        tts_instance = get_tts()
        if tts_instance:
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            filename = f"speech_{timestamp}.mp3"
            filepath = os.path.join(AUDIO_STORAGE_PATH, filename)

            # Generate speech with UK female voice (Claribel Dervox)
            tts_instance.tts_to_file(
                text=text, speaker="Claribel Dervox", language="en", file_path=filepath
            )

            logger.info(f"Generated Coqui TTS audio: {filepath}")
            return filename
        else:
            logger.warning("Coqui TTS not available, falling back to gTTS")

    except Exception as e:
        logger.error(f"Coqui TTS generation failed: {str(e)}, falling back to gTTS")

    # Fallback to gTTS
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
        # Handle both string and bytes
        if isinstance(message.value, bytes):
            text = message.value.decode("utf-8")
        else:
            text = str(message.value)

        logger.info(f"Processing speak message: {text}")

        # Generate TTS
        filename = generate_tts(text)
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


if __name__ == "__main__":
    main()
