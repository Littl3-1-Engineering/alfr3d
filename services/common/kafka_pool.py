import os
import orjson
import logging

logger = logging.getLogger(__name__)

_producers = {}


def get_kafka_url():
    return os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def get_producer(use_json_serializer=True):
    from kafka import KafkaProducer
    from kafka.errors import KafkaError

    kafka_url = get_kafka_url()
    key = (kafka_url, use_json_serializer)

    if key not in _producers or _producers[key] is None:
        try:
            logger.info(f"Connecting to Kafka at: {kafka_url}")
            if use_json_serializer:

                def serialize_value(v):
                    if isinstance(v, bytes):
                        return v
                    return orjson.dumps(v)

                producer = KafkaProducer(
                    bootstrap_servers=[kafka_url],
                    value_serializer=serialize_value,
                )
            else:
                producer = KafkaProducer(bootstrap_servers=[kafka_url])
            _producers[key] = producer
            logger.info("Connected to Kafka")
        except KafkaError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    return _producers[key]


def close_producer(use_json_serializer=False):
    kafka_url = get_kafka_url()
    key = (kafka_url, use_json_serializer)

    if key in _producers and _producers[key] is not None:
        _producers[key].close()
        _producers[key] = None
        logger.info("Kafka producer closed")


def close_all_producers():
    for key, producer in _producers.items():
        if producer is not None:
            producer.close()
    _producers.clear()
    logger.info("All Kafka producers closed")
